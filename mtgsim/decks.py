"""Reading decklists (Arena export, MTGO/plain text, Forge .dck) and writing Forge .dck files."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .carddb import CardDatabase

_SECTION_HEADERS = {
    "deck": "main", "main": "main", "maindeck": "main", "main deck": "main", "mainboard": "main",
    "sideboard": "side", "side": "side", "sb": "side",
    "commander": "commander", "companion": "companion",
    "about": "about", "metadata": "about", "shop": "skip", "avatar": "skip", "planes": "skip",
    "schemes": "skip", "conspiracy": "skip", "dungeon": "skip", "attractions": "skip",
    "contraptions": "skip", "maybeboard": "skip", "considering": "skip", "tokens": "skip",
}
_ENTRY = re.compile(r"^(?:(\d+)\s*[xX]?\s+)?(.+)$")


@dataclass
class DeckIssue:
    severity: str  # "error" or "warning"
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: {self.message}"


@dataclass
class Deck:
    name: str
    main: Counter = field(default_factory=Counter)
    side: Counter = field(default_factory=Counter)
    path: Optional[Path] = None
    issues: List[DeckIssue] = field(default_factory=list)

    @property
    def main_count(self) -> int:
        return sum(self.main.values())

    @property
    def side_count(self) -> int:
        return sum(self.side.values())

    @property
    def errors(self) -> List[DeckIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def fingerprint(self) -> str:
        """Identifies the main deck's contents (the sideboard is never played in best-of-one)."""
        text = "\n".join(f"{n} {name}" for name, n in sorted(self.main.items()))
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]

    def to_dck(self) -> str:
        lines = ["[metadata]", f"Name={self.name}", "[Main]"]
        lines += [f"{n} {name}" for name, n in sorted(self.main.items())]
        lines.append("[Sideboard]")
        lines += [f"{n} {name}" for name, n in sorted(self.side.items())]
        return "\n".join(lines) + "\n"

    def to_text(self) -> str:
        lines = ["Deck"] + [f"{n} {name}" for name, n in sorted(self.main.items())]
        if self.side:
            lines += ["", "Sideboard"] + [f"{n} {name}" for name, n in sorted(self.side.items())]
        return "\n".join(lines) + "\n"


def _clean_card_name(text: str) -> str:
    """Strip printing details: ``(SET) 123``, ``[SET]``, ``|SET|2``, foil markers, trailing tags."""
    text = text.split("|")[0]
    text = re.sub(r"\s+#.*$", "", text)
    text = re.sub(r"\s*\*[A-Za-z]+\*\s*$", "", text)
    text = re.sub(r"\s*[\(\[][A-Za-z0-9]{2,6}[\)\]]\s*[\w★-]*\s*$", "", text)
    return text.strip()


def parse_deck_text(text: str, name: str = "deck") -> Tuple[str, List[Tuple[str, int, str]]]:
    """Split a decklist into (deck name, [(section, count, raw card name)]).

    Sections are taken from headers when present. A headerless list with a blank line before a
    final block of at most 15 cards is read the way MTGO exports are: that block is the sideboard.
    """
    entries: List[Tuple[str, int, str]] = []
    section = "main"
    saw_header = False
    block = 0
    block_of: List[int] = []
    pending_blank = False

    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line:
            pending_blank = True
            continue
        if line.startswith("#") or line.startswith("//"):
            m = re.match(r"^(?:#|//)\s*name\s*[:=]\s*(.+)$", line, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
            continue
        header = line.strip("[]").rstrip(":").strip().lower()
        if header in _SECTION_HEADERS and not re.match(r"^\d", line):
            section = _SECTION_HEADERS[header]
            saw_header = True
            pending_blank = False
            continue
        if section == "about":
            m = re.match(r"^name[\s=:]+(.+)$", line, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
            continue
        if section == "skip":
            continue

        target = section
        m = re.match(r"^SB:\s*(.+)$", line, re.IGNORECASE)
        if m:
            line, target = m.group(1), "side"
        m = _ENTRY.match(line)
        if not m:
            continue
        count = int(m.group(1)) if m.group(1) else 1
        card = _clean_card_name(m.group(2))
        if not card or count <= 0:
            continue
        if pending_blank and entries:
            block += 1
        pending_blank = False
        entries.append((target, count, card))
        block_of.append(block)

    if not saw_header and block > 0:
        last = [i for i, b in enumerate(block_of) if b == block and entries[i][0] == "main"]
        rest = sum(e[1] for i, e in enumerate(entries) if i not in last and e[0] == "main")
        if last and sum(entries[i][1] for i in last) <= 15 and rest >= 40:
            for i in last:
                entries[i] = ("side", entries[i][1], entries[i][2])
    return name, entries


def load_deck(path: Path, db: Optional[CardDatabase] = None) -> Deck:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return deck_from_text(text, name=path.stem, db=db, path=path)


def deck_from_text(text: str, name: str = "deck", db: Optional[CardDatabase] = None, path: Optional[Path] = None) -> Deck:
    """Parse a decklist and, when a card database is given, resolve every name against it."""
    name, entries = parse_deck_text(text, name)
    deck = Deck(name=name, path=path)
    for section, count, raw in entries:
        resolved = raw
        if db is not None:
            card = db.get(raw)
            if card is None:
                hint = db.suggest(raw)
                deck.issues.append(DeckIssue(
                    "error",
                    f"unknown card \"{raw}\"" + (f" (did you mean: {', '.join(hint)}?)" if hint else ""),
                ))
                continue
            resolved = card.name
        if section in ("main", "commander"):
            deck.main[resolved] += count
        elif section in ("side", "companion"):
            deck.side[resolved] += count
    if not deck.main:
        deck.issues.append(DeckIssue("error", "no main-deck cards were found in the list"))
    return deck


def find_deck_files(path: Path) -> List[Path]:
    """A single deck file, or every .txt/.dck/.dec decklist directly inside a folder."""
    path = Path(path)
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in (".txt", ".dck", ".dec") and p.is_file())
    return [path]
