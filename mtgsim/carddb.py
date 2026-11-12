"""A card database built from Forge's own card scripts and edition files.

Using Forge's data (rather than an external card API) guarantees that a name which resolves
here is a card the engine can actually play, under exactly the name the engine uses.
The parsed database is cached under ``MTGSIM_HOME/cache`` because reading ~34,000 scripts
takes a few seconds.
"""

from __future__ import annotations

import difflib
import gzip
import json
import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from .forge import ForgeInstall, home_dir

CACHE_VERSION = 5
COLORS = "WUBRG"
BASIC_LAND_COLORS = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
CARD_TYPES = {
    "Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land",
    "Planeswalker", "Sorcery", "Tribal",
}
SUPERTYPES = {"Basic", "Legendary", "Snow", "World", "Ongoing"}
# Rarity letters used in Forge edition files (L = basic land, S = special).
_EDITION_CARD = re.compile(r"^\S+ ([LCURMSTB]) (.+?)(?:\s+@.*)?$")


def norm_name(name: str) -> str:
    """A forgiving lookup key: case, accents, apostrophe style and split-card separators are ignored."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = re.sub(r"\s*/{1,3}\s*", " // ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass(frozen=True)
class ManaCost:
    """A mana cost reduced to what matters for curve and colour analysis."""

    generic: int = 0
    pips: Tuple[str, ...] = ()  # each entry is the set of colours that can pay that symbol, e.g. "R" or "BG"
    cmc: int = 0
    has_x: bool = False

    @staticmethod
    def parse(text: str) -> "ManaCost":
        generic, cmc, has_x = 0, 0, False
        pips: List[str] = []
        if not text or text.strip().lower() == "no cost":
            return ManaCost()
        for token in text.split():
            if token.isdigit():
                generic += int(token)
                cmc += int(token)
            elif token == "X":
                has_x = True
            elif token == "S":  # snow mana: any one mana in practice
                generic += 1
                cmc += 1
            elif token.startswith("2") and len(token) >= 2:  # "2R" or "2/R": two generic or one coloured
                generic += 2
                cmc += 2
            elif "P" in token:  # Phyrexian: payable with life, so it constrains nothing
                cmc += 1
            else:
                colours = "".join(ch for ch in token if ch in COLORS + "C")
                if colours:
                    pips.append(colours)
                    cmc += 1
        return ManaCost(generic=generic, pips=tuple(pips), cmc=cmc, has_x=has_x)

    def colours(self) -> str:
        return "".join(c for c in COLORS if any(c in pip for pip in self.pips))


@dataclass(frozen=True)
class Face:
    name: str
    mana_cost: str = ""
    types: Tuple[str, ...] = ()
    pt: str = ""
    oracle: str = ""
    keywords: Tuple[str, ...] = ()

    @property
    def cost(self) -> ManaCost:
        return ManaCost.parse(self.mana_cost)

    @property
    def is_land(self) -> bool:
        return "Land" in self.types

    @property
    def card_types(self) -> Tuple[str, ...]:
        return tuple(t for t in self.types if t in CARD_TYPES)

    @property
    def type_line(self) -> str:
        main = [t for t in self.types if t in SUPERTYPES or t in CARD_TYPES]
        sub = [t for t in self.types if t not in SUPERTYPES and t not in CARD_TYPES]
        return " ".join(main) + (" — " + " ".join(sub) if sub else "")


@dataclass
class Card:
    name: str
    layout: str = "normal"
    faces: List[Face] = field(default_factory=list)
    sets: Dict[str, str] = field(default_factory=dict)  # set code -> rarity letter
    deck_limit: Optional[int] = 4  # None means any number
    produces: str = ""  # colours of mana this card can make (lands, mana creatures, mana rocks)
    enters_tapped: bool = False
    mana_source: bool = False  # a nonland permanent with a free "tap: add mana" ability

    @property
    def front(self) -> Face:
        return self.faces[0]

    @property
    def is_land(self) -> bool:
        return self.front.is_land

    @property
    def is_basic_land(self) -> bool:
        return self.front.is_land and "Basic" in self.front.types

    @property
    def is_creature(self) -> bool:
        return "Creature" in self.front.types

    @property
    def has_land_face(self) -> bool:
        """True for spell/land modal cards, which can be played as a land when one is needed."""
        return self.layout == "modal" and any(f.is_land for f in self.faces[1:]) and not self.is_land

    @property
    def cost(self) -> ManaCost:
        """The cost used for curve analysis: the cheaper half of a split card, otherwise the front face."""
        if self.layout == "split" and len(self.faces) > 1:
            return min((f.cost for f in self.faces), key=lambda c: c.cmc)
        return self.front.cost

    @property
    def cmc(self) -> int:
        return self.cost.cmc

    @property
    def colours(self) -> str:
        found = set()
        for face in self.faces if self.layout == "split" else self.faces[:1]:
            found.update(face.cost.colours())
        return "".join(c for c in COLORS if c in found)

    @property
    def oracle(self) -> str:
        return "\n//\n".join(f.oracle for f in self.faces if f.oracle)

    def to_json(self) -> dict:
        return {
            "n": self.name,
            "l": self.layout,
            "f": [[f.name, f.mana_cost, list(f.types), f.pt, f.oracle, list(f.keywords)] for f in self.faces],
            "s": self.sets,
            "d": self.deck_limit,
            "p": self.produces,
            "t": self.enters_tapped,
            "m": self.mana_source,
        }

    @staticmethod
    def from_json(data: dict) -> "Card":
        return Card(
            name=data["n"],
            layout=data["l"],
            faces=[Face(f[0], f[1], tuple(f[2]), f[3], f[4], tuple(f[5])) for f in data["f"]],
            sets=data["s"],
            deck_limit=data["d"],
            produces=data["p"],
            enters_tapped=data["t"],
            mana_source=data["m"],
        )


@dataclass(frozen=True)
class Edition:
    code: str
    name: str
    date: str
    type: str


# ----------------------------------------------------------- script parsing

_LAYOUTS = {
    "Split": "split", "DoubleFaced": "transform", "Modal": "modal", "Adventure": "adventure",
    "Flip": "flip", "Meld": "meld", "Omen": "omen", "Prepare": "prepare",
}


def parse_card_script(text: str) -> Optional[Card]:
    """Turn one Forge card script into a Card (without set information)."""
    faces: List[Face] = []
    layout = "normal"
    deck_limit: Optional[int] = 4
    produces: set = set()
    enters_tapped = False
    mana_source = False

    current: Dict[str, object] = {}
    keywords: List[str] = []
    abilities: List[str] = []

    def flush() -> None:
        nonlocal current, keywords, abilities, produces, enters_tapped, mana_source
        if current.get("Name"):
            face = Face(
                name=str(current["Name"]),
                mana_cost=str(current.get("ManaCost", "")),
                types=tuple(str(current.get("Types", "")).split()),
                pt=str(current.get("PT", "")),
                oracle=str(current.get("Oracle", "")).replace("\\n", "\n"),
                keywords=tuple(keywords),
            )
            if not faces:  # mana production and tapped-ness describe the front face only
                made, free_tap, fetches = _mana_production(face, abilities)
                produces = made
                enters_tapped = _enters_tapped(face.oracle) or fetches
                mana_source = bool(made) and free_tap and not face.is_land
            faces.append(face)
        current, keywords, abilities = {}, [], []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "ALTERNATE":
            flush()
            continue
        if line.startswith("SPECIALIZE:"):  # digital-only alternate versions; not separate faces
            flush()
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        if key == "K":
            keywords.append(value)
            if value.startswith("A deck can have any number of cards named"):
                deck_limit = None
            elif value.startswith("DeckLimit:"):
                try:
                    deck_limit = int(value.split(":")[1])
                except (IndexError, ValueError):
                    pass
        elif key == "A":
            abilities.append(value)
        elif key == "AlternateMode":
            layout = _LAYOUTS.get(value.strip(), value.strip().lower())
        elif key in ("Name", "ManaCost", "Types", "PT", "Oracle") and key not in current:
            current[key] = value.strip()
    flush()

    if not faces:
        return None
    name = " // ".join(f.name for f in faces[:2]) if layout == "split" and len(faces) > 1 else faces[0].name
    return Card(
        name=name,
        layout=layout,
        faces=faces,
        deck_limit=deck_limit,
        produces="".join(c for c in COLORS + "C" if c in produces),
        enters_tapped=enters_tapped,
        mana_source=mana_source,
    )


def _mana_production(face: Face, abilities: Iterable[str]) -> Tuple[set, bool, bool]:
    """Colours a card can produce, whether it does so for just tapping, and whether it fetches a tapped basic."""
    made: set = set()
    free_tap = False
    fetches = False
    if face.is_land:
        for subtype, colour in BASIC_LAND_COLORS.items():
            if subtype in face.types:
                made.add(colour)
                free_tap = True
    for ability in abilities:
        params = _params(ability)
        if params.get("AB") == "Mana":
            value = params.get("Produced", "")
            colours = {tok for tok in value.split() if tok in tuple(COLORS + "C")}
            if re.search(r"Any|Chosen|ColorIdentity", value):
                colours.update(COLORS)
            made.update(colours)
            if params.get("Cost", "").strip() == "T":
                free_tap = True
        elif (
            face.is_land
            and params.get("AB") == "ChangeZone"
            and "Land.Basic" in params.get("ChangeType", "")
            and params.get("Destination") == "Battlefield"
        ):
            made.update(COLORS)  # Evolving Wilds and friends: any basic the deck plays
            # Only fetches that put the land onto the battlefield tapped cost a turn of mana;
            # Prismatic Vista's basic arrives untapped.
            fetches = fetches or params.get("Tapped") == "True"
    return made, free_tap, fetches


def _params(ability: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in ability.split("|"):
        key, sep, value = part.partition("$")
        if sep:
            out[key.strip()] = value.strip()
    return out


def _enters_tapped(oracle: str) -> bool:
    """True only for lands that always enter tapped; conditional ones are treated as untapped."""
    for sentence in re.split(r"[.\n]", oracle):
        low = sentence.lower()
        if re.search(r"enters (the battlefield )?tapped", low) and not re.search(r"\bunless\b|\bmay\b|\bif\b", low):
            return True
    return False


# ------------------------------------------------------------------ database


class CardDatabase:
    def __init__(self, cards: Iterable[Card], editions: Iterable[Edition] = ()):
        self.cards: Dict[str, Card] = {}
        self._index: Dict[str, str] = {}
        self.editions: Dict[str, Edition] = {e.code: e for e in editions}
        for card in cards:
            self.cards[card.name] = card
        for card in self.cards.values():
            self._index[norm_name(card.name)] = card.name
        for card in self.cards.values():  # aliases never override a real card name
            if len(card.faces) > 1:
                aliases = [f.name for f in card.faces]
                aliases.append(" // ".join(f.name for f in card.faces[:2]))
                for alias in aliases:
                    self._index.setdefault(norm_name(alias), card.name)

    def __len__(self) -> int:
        return len(self.cards)

    def __iter__(self) -> Iterator[Card]:
        return iter(self.cards.values())

    def get(self, name: str) -> Optional[Card]:
        """Look a card up by any reasonable spelling of its name."""
        key = norm_name(name)
        canonical = self._index.get(key)
        if canonical is None and " // " in key:
            canonical = self._index.get(key.split(" // ")[0])
        return self.cards.get(canonical) if canonical else None

    def suggest(self, name: str, n: int = 3) -> List[str]:
        matches = difflib.get_close_matches(norm_name(name), list(self._index), n=n, cutoff=0.72)
        seen: List[str] = []
        for match in matches:
            canonical = self._index[match]
            if canonical not in seen:
                seen.append(canonical)
        return seen


def _iter_scripts(cardsfolder: Path) -> Iterator[str]:
    zipped = cardsfolder / "cardsfolder.zip"
    found_any = False
    for root, dirs, files in os.walk(cardsfolder):
        dirs.sort()
        for filename in sorted(files):
            if filename.endswith(".txt"):
                found_any = True
                with open(os.path.join(root, filename), encoding="utf-8", errors="replace") as fh:
                    yield fh.read()
    if not found_any and zipped.is_file():
        with zipfile.ZipFile(zipped) as archive:
            for info in archive.infolist():
                if info.filename.endswith(".txt"):
                    yield archive.read(info).decode("utf-8", errors="replace")


def _parse_edition(text: str) -> Tuple[Optional[Edition], List[Tuple[str, str]]]:
    meta: Dict[str, str] = {}
    cards: List[Tuple[str, str]] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].lower()
            continue
        if section == "metadata":
            key, sep, value = line.partition("=")
            if sep:
                meta[key.strip()] = value.strip()
        elif section not in ("tokens", "other"):
            m = _EDITION_CARD.match(line)
            if m:
                name = re.sub(r"\s*\{.*$", "", m.group(2)).strip()
                cards.append((name, m.group(1)))
    if "Code" not in meta:
        return None, []
    edition = Edition(meta["Code"], meta.get("Name", meta["Code"]), meta.get("Date", ""), meta.get("Type", ""))
    return edition, cards


def build_database(install: ForgeInstall) -> CardDatabase:
    cards: Dict[str, Card] = {}
    for script in _iter_scripts(install.cardsfolder):
        card = parse_card_script(script)
        if card is not None:
            cards.setdefault(card.name, card)
    db = CardDatabase(cards.values())

    editions: List[Edition] = []
    editions_dir = install.res / "editions"
    if editions_dir.is_dir():
        for path in sorted(editions_dir.glob("*.txt")):
            edition, listed = _parse_edition(path.read_text(encoding="utf-8", errors="replace"))
            if edition is None:
                continue
            editions.append(edition)
            for name, rarity in listed:
                card = db.get(name)
                if card is not None:
                    # keep the lowest rarity a card was printed at in this set
                    previous = card.sets.get(edition.code)
                    if previous is None or "LCURMSTB".index(rarity) < "LCURMSTB".index(previous):
                        card.sets[edition.code] = rarity
    return CardDatabase(db.cards.values(), editions)


def load_database(install: ForgeInstall, refresh: bool = False) -> CardDatabase:
    """Load the card database, building and caching it on first use."""
    cache_dir = home_dir() / "cache"
    cache_file = cache_dir / f"carddb-v{CACHE_VERSION}-{install.fingerprint()}.json.gz"
    if cache_file.is_file() and not refresh:
        try:
            with gzip.open(cache_file, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            return CardDatabase(
                (Card.from_json(c) for c in data["cards"]),
                (Edition(*e) for e in data["editions"]),
            )
        except (OSError, ValueError, KeyError, EOFError):
            pass  # a damaged cache is simply rebuilt
    db = build_database(install)
    if len(db) == 0:
        raise RuntimeError(f"No card scripts were found under {install.cardsfolder}.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for stale in cache_dir.glob("carddb-*.json.gz"):
        try:
            stale.unlink()
        except OSError:
            pass
    tmp = cache_file.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=3) as fh:
        json.dump(
            {
                "cards": [c.to_json() for c in db],
                "editions": [[e.code, e.name, e.date, e.type] for e in db.editions.values()],
            },
            fh,
        )
    tmp.replace(cache_file)
    return db
