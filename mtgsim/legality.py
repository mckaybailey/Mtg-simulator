"""Deck construction and format legality checks, using Forge's own format definitions.

Forge keeps one file per format under ``res/formats`` listing the legal set codes and the
banned/restricted cards, so the checks here agree with what the engine itself considers legal
and move with it when the Forge checkout is updated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .carddb import CardDatabase
from .decks import Deck, DeckIssue

MIN_MAIN = 60
MAX_SIDE = 15


@dataclass
class Format:
    name: str
    sets: Set[str] = field(default_factory=set)  # empty means every set is allowed
    banned: Set[str] = field(default_factory=set)
    restricted: Set[str] = field(default_factory=set)
    rarities: Set[str] = field(default_factory=set)  # empty means every rarity is allowed
    additional: Set[str] = field(default_factory=set)  # cards legal regardless of set


def load_formats(res: Path) -> Dict[str, Format]:
    """Read every format Forge defines, keyed by lower-case name."""
    formats: Dict[str, Format] = {}
    root = Path(res) / "formats"
    for path in sorted(root.glob("*/*.txt")):
        if path.parent.name not in ("Sanctioned", "Casual"):
            continue
        fields: Dict[str, str] = {}
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = raw.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        if "Name" not in fields:
            continue

        def names(key: str) -> Set[str]:
            return {n.strip() for n in fields.get(key, "").split(";") if n.strip()}

        formats[fields["Name"].lower()] = Format(
            name=fields["Name"],
            sets={s.strip() for s in fields.get("Sets", "").split(",") if s.strip()},
            banned=names("Banned"),
            restricted=names("Restricted"),
            rarities={r.strip() for r in fields.get("Rarities", "").split(",") if r.strip()},
            additional=names("Additional"),
        )
    return formats


def get_format(res: Path, name: Optional[str]) -> Optional[Format]:
    """Look a format up by name; ``None``, "casual", "any" and "none" mean no format restrictions."""
    if not name or name.lower() in ("casual", "any", "none"):
        return None
    formats = load_formats(res)
    fmt = formats.get(name.lower())
    if fmt is None:
        known = ", ".join(sorted(f.name for f in formats.values()))
        raise ValueError(f"unknown format \"{name}\". Known formats: {known}, or \"casual\" for no restrictions.")
    return fmt


def check_deck(deck: Deck, db: CardDatabase, fmt: Optional[Format] = None) -> List[DeckIssue]:
    """Return construction and legality problems for a 60-card constructed deck.

    With a format, breaking a rule is an error. Without one (casual play) only cards the engine
    does not know are errors; size and copy-count problems are reported as warnings, because a
    casual deck is allowed to ignore them and Forge will still play it.
    """
    strict = "error" if fmt is not None else "warning"
    label = fmt.name if fmt is not None else "constructed"
    issues: List[DeckIssue] = []

    if deck.main_count < MIN_MAIN:
        issues.append(DeckIssue(strict, f"main deck has {deck.main_count} cards; {label} decks need at least {MIN_MAIN}"))
    if deck.side_count > MAX_SIDE:
        issues.append(DeckIssue(strict, f"sideboard has {deck.side_count} cards; the maximum is {MAX_SIDE}"))

    totals = deck.main + deck.side
    banned = {n.lower() for n in fmt.banned} if fmt else set()
    restricted = {n.lower() for n in fmt.restricted} if fmt else set()
    additional = {n.lower() for n in fmt.additional} if fmt else set()

    for name in sorted(totals):
        copies = totals[name]
        card = db.get(name)
        if card is None:
            continue  # reported as an unknown card when the deck was loaded
        if not card.is_basic_land and card.deck_limit is not None and copies > card.deck_limit:
            issues.append(DeckIssue(strict, f"{copies} copies of {name}; the limit is {card.deck_limit}"))
        if fmt is None:
            continue
        lowered = name.lower()
        if lowered in banned:
            issues.append(DeckIssue("error", f"{name} is banned in {fmt.name}"))
            continue
        if lowered in restricted and copies > 1:
            issues.append(DeckIssue("error", f"{name} is restricted in {fmt.name} (1 copy allowed, deck has {copies})"))
        if lowered in additional:
            continue
        printings = card.sets
        if fmt.sets:
            printings = {code: rarity for code, rarity in card.sets.items() if code in fmt.sets}
            if not printings:
                issues.append(DeckIssue("error", f"{name} is not legal in {fmt.name} (no printing in a legal set)"))
                continue
        if fmt.rarities and not any(r in fmt.rarities for r in printings.values()):
            allowed = "/".join(sorted(fmt.rarities))
            issues.append(DeckIssue("error", f"{name} has no {allowed} printing, so it is not legal in {fmt.name}"))
    return issues
