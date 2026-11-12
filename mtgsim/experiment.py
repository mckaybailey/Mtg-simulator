"""Planning and executing a batch of games, and keeping the results on disk.

A run lives in its own directory::

    run.json      what was asked for: decks, options, seed, engine version
    games.jsonl   one line per finished game (appended as games finish, so a run can be resumed)
    decks/        the exact .dck files handed to Forge
    logs/         worker output, and per-game logs when --save-logs is used
    summary.json  the analysed results (written by the commands, see analysis.py)
    report.html   the human-readable report
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .decks import Deck
from .forge import ForgeInstall
from .runner import Job, run_jobs


class RunError(RuntimeError):
    """A run could not be carried out as asked; the message is meant for the user."""


@dataclass
class Entrant:
    """A deck taking part in a run, under a unique key."""

    key: str
    deck: Deck
    role: str = "opponent"  # "hero", "variant" or "opponent"
    weight: Optional[float] = None  # share of the metagame, used to weight gauntlet results
    category: str = ""
    pilot: str = ""  # how well the AI plays this deck compared with people: "weak", "fair", "strong" or unknown
    dck_path: str = ""

    def describe(self) -> dict:
        return {
            "key": self.key,
            "name": self.deck.name,
            "role": self.role,
            "weight": self.weight,
            "category": self.category,
            "ai_pilot": self.pilot,
            "source": str(self.deck.path) if self.deck.path else None,
            "fingerprint": self.deck.fingerprint(),
            "main_count": self.deck.main_count,
            "side_count": self.deck.side_count,
            "main": dict(sorted(self.deck.main.items())),
            "side": dict(sorted(self.deck.side.items())),
        }


@dataclass
class RunOptions:
    games: int = 100  # games per pairing
    seed: int = 1
    timeout: int = 180
    workers: Optional[int] = None
    heap: str = "2g"
    monte_carlo: str = "off"
    ai_profile: str = ""
    save_logs: bool = False

    def describe(self) -> dict:
        return {
            "games_per_pairing": self.games, "seed": self.seed, "timeout": self.timeout,
            "monte_carlo": self.monte_carlo, "ai_profile": self.ai_profile or "Default",
        }


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "deck"


def unique_keys(names: Iterable[str]) -> List[str]:
    """Turn deck names into distinct, filesystem-safe keys."""
    used: set = set()
    keys = []
    for name in names:
        base = slug(name)
        key, n = base, 1
        while key in used:
            n += 1
            key = f"{base}-{n}"
        used.add(key)
        keys.append(key)
    return keys


def game_seed(base_seed: int, first: Deck, second: Deck, index: int) -> int:
    """A reproducible per-game seed.

    It depends on the decks' contents rather than their names or the order they were given in, so
    the same matchup always replays the same games, and editing a deck gives it fresh ones.
    """
    prints = sorted([first.fingerprint(), second.fingerprint()])
    digest = hashlib.sha256(f"{base_seed}|{prints[0]}|{prints[1]}|{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def plan_pairing(a: Entrant, b: Entrant, options: RunOptions, run_dir: Path) -> List[Job]:
    """Jobs for ``options.games`` games between two entrants.

    Seats alternate every game so that neither deck is systematically listed first; who actually
    takes the first turn is decided by the engine's coin flip and recorded in the result.
    """
    jobs = []
    for i in range(options.games):
        seats = [a, b] if i % 2 == 0 else [b, a]
        job_id = f"{a.key}|{b.key}|{i}"
        log_path = ""
        if options.save_logs:
            log_path = str(run_dir / "logs" / "games" / f"{a.key}__{b.key}__{i:04d}.log")
        jobs.append(Job(
            id=job_id,
            seed=game_seed(options.seed, a.deck, b.deck, i),
            decks=[s.dck_path for s in seats],
            timeout=options.timeout,
            monte_carlo=options.monte_carlo,
            log_path=log_path,
            profiles=[options.ai_profile, options.ai_profile] if options.ai_profile else [],
            meta={"a": a.key, "b": b.key, "game": i, "seats": [s.key for s in seats]},
        ))
    return jobs


def write_decks(entrants: List[Entrant], run_dir: Path) -> None:
    deck_dir = run_dir / "decks"
    deck_dir.mkdir(parents=True, exist_ok=True)
    for entrant in entrants:
        path = deck_dir / f"{entrant.key}.dck"
        path.write_text(entrant.deck.to_dck(), encoding="utf-8")
        entrant.dck_path = str(path.resolve())


def read_games(run_dir: Path) -> List[dict]:
    path = Path(run_dir) / "games.jsonl"
    games: Dict[str, dict] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue  # a line cut short by an interrupted run
                games[record["id"]] = record
    return list(games.values())


def _record(job: Job, result: dict) -> dict:
    """Combine what was asked for with what the engine reported into one stored record."""
    record = {k: v for k, v in job.meta.items() if not k.startswith("_")}
    record["id"] = job.id
    record["seed"] = job.seed
    record["status"] = result.get("status", "error")
    record["winner_seat"] = result.get("winner", -1)
    record["first_seat"] = result.get("first", -1)
    record["turns"] = result.get("turns")
    record["end_reason"] = result.get("endReason")
    record["ms"] = result.get("ms")
    record["players"] = result.get("players", [])
    if result.get("error"):
        record["error"] = str(result["error"])[:2000]
    return record


class Progress:
    """A single-line progress display on a terminal, periodic lines otherwise."""

    def __init__(self, total: int, already: int = 0, stream=None, quiet: bool = False):
        self.total, self.done, self.quiet = total, already, quiet
        self.stream = stream or sys.stderr
        self.started = time.time()
        self.fresh = 0
        self._last_print = 0.0
        self._tty = hasattr(self.stream, "isatty") and self.stream.isatty()

    def tick(self) -> None:
        self.done += 1
        self.fresh += 1
        if self.quiet:
            return
        now = time.time()
        interval = 0.5 if self._tty else 30.0
        if now - self._last_print < interval and self.done < self.total:
            return
        self._last_print = now
        elapsed = now - self.started
        rate = self.fresh / elapsed if elapsed > 0 else 0.0
        remaining = (self.total - self.done) / rate if rate > 0 else 0.0
        text = (f"  {self.done}/{self.total} games  "
                f"{rate * 60:.0f} games/min  about {_duration(remaining)} left")
        if self._tty:
            self.stream.write("\r" + text.ljust(70))
            if self.done >= self.total:
                self.stream.write("\n")
        else:
            self.stream.write(text + "\n")
        self.stream.flush()


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60} min"
    return f"{seconds / 3600:.1f} h"


def execute(
    install: ForgeInstall,
    run_dir: Path,
    entrants: List[Entrant],
    pairings: List[Tuple[Entrant, Entrant]],
    options: RunOptions,
    meta: Optional[dict] = None,
    quiet: bool = False,
) -> List[dict]:
    """Play every pairing, skipping games already recorded in ``run_dir``, and return all records."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_decks(entrants, run_dir)

    jobs: List[Job] = []
    for a, b in pairings:
        jobs.extend(plan_pairing(a, b, options, run_dir))
    wanted = {job.id for job in jobs}
    have = {g["id"] for g in read_games(run_dir) if g["status"] in ("ok", "timeout")}
    todo = [job for job in jobs if job.id not in have]

    run_info = dict(meta or {})
    run_info.update({
        "options": options.describe(),
        "entrants": [e.describe() for e in entrants],
        "pairings": [[a.key, b.key] for a, b in pairings],
        "forge": {"version": install.version, "path": str(install.root)},
        "created": run_info.get("created") or time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=1), encoding="utf-8")

    expected_main = {e.key: e.deck.main_count for e in entrants}
    progress = Progress(len(jobs), already=len(jobs) - len(todo), quiet=quiet)
    started = time.time()

    with open(run_dir / "games.jsonl", "a", encoding="utf-8") as out:
        def on_result(job: Job, result: dict) -> None:
            record = _record(job, result)
            for seat, player in enumerate(record["players"]):
                key = record["seats"][seat]
                loaded = player.get("mainCount")
                if loaded is not None and loaded != expected_main[key]:
                    raise RunError(
                        f"Forge loaded {loaded} main-deck cards for \"{key}\" but the list has "
                        f"{expected_main[key]}: the engine did not recognise some card names. "
                        "Results for this deck would be wrong, so the run was stopped."
                    )
            out.write(json.dumps(record, separators=(",", ":")) + "\n")
            out.flush()
            progress.tick()

        engine = run_jobs(install, todo, on_result, workers=options.workers, heap=options.heap,
                          log_dir=run_dir / "logs")

    if engine:
        run_info["forge"].update(engine)
    run_info["elapsed_seconds"] = round(run_info.get("elapsed_seconds", 0) + time.time() - started, 1)
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=1), encoding="utf-8")
    return [g for g in read_games(run_dir) if g["id"] in wanted]
