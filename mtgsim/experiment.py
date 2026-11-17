"""Planning and executing a batch of games, and keeping the results on disk.

A run lives in its own directory::

    run.json      what was asked for: decks, options, seed, engine version
    games.jsonl   one line per finished game (appended as games finish, so a run can be resumed)
    decks/        the exact .dck files handed to Forge
    ai/           the AI profiles Forge loads for this run (see ai_profiles.py)
    logs/         worker output, and per-game logs when --save-logs is used
    summary.json  the analysed results (written by the commands, see analysis.py)
    report.html   the human-readable report
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from . import ai_profiles
from .decks import Deck
from .forge import ForgeInstall, patches_for_run
from .runner import COUNTED_MODES, DEFAULT_TIMEOUT, FIXED_TIMEOUT, Job, run_jobs


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
    ai_profile: str = ""  # Forge AI profile for this deck's seat ("" = the run's default)
    ai_mc: str = ""  # Monte Carlo search for this deck's seat: "off", "on", "max", "fixed", "deep" ("" = the run's default)
    dck_path: str = ""

    def describe(self) -> dict:
        return {
            "key": self.key,
            "name": self.deck.name,
            "role": self.role,
            "weight": self.weight,
            "category": self.category,
            "ai_pilot": self.pilot,
            "ai_profile": self.ai_profile or None,
            "ai_mc": self.ai_mc or None,
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
    timeout: int = DEFAULT_TIMEOUT
    fixed_timeout: int = FIXED_TIMEOUT  # for games in which a seat plays Monte Carlo "fixed"
    workers: Optional[int] = None
    heap: str = "2g"
    monte_carlo: str = "off"
    ai_profile: str = ""
    # When set (--ai-profile / --mc given), they apply to every seat and override per-deck settings.
    force_profile: bool = False
    force_monte_carlo: bool = False
    save_logs: bool = False
    # "bo1": every game is its own match. "bo3": ``games`` matches per pairing, each played to two game wins
    # (see execute_matches); ``sideboard`` lets both decks sideboard before games 2 and 3.
    match_format: str = "bo1"
    sideboard: bool = True

    def describe(self) -> dict:
        info = {
            "games_per_pairing": self.games, "seed": self.seed, "timeout": self.timeout,
            "monte_carlo": self.monte_carlo, "ai_profile": self.ai_profile or "Default",
        }
        if self.match_format != "bo1":  # best-of-one runs keep the description they always had
            info.update({"match_format": self.match_format, "sideboard": self.sideboard,
                         "matches_per_pairing": self.games})
        if self.monte_carlo in COUNTED_MODES:  # execute() also adds it when only a deck's ai_mc asks for one
            info["timeout_fixed"] = self.fixed_timeout
        return info


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
            # absolute: the Forge JVMs run in Forge's own folder, where a relative path would land
            log_path = str(Path(run_dir).resolve() / "logs" / "games" / f"{a.key}__{b.key}__{i:04d}.log")
        job = Job(
            id=job_id,
            seed=game_seed(options.seed, a.deck, b.deck, i),
            decks=[s.dck_path for s in seats],
            timeout=options.timeout,
            monte_carlo=options.monte_carlo,
            log_path=log_path,
            profiles=_seat_profiles(seats, options),
            seat_monte_carlo=[] if options.force_monte_carlo else [s.ai_mc for s in seats],
            meta={"a": a.key, "b": b.key, "game": i, "seats": [s.key for s in seats]},
        )
        if job.uses_fixed_search():
            # No clock cuts a counted search short, so the game takes as long as it takes; stopping it at
            # the usual limit would record a timeout where a replay is expected.
            job.timeout = options.fixed_timeout
        jobs.append(job)
    return jobs


def match_game_seed(base_seed: int, first: Deck, second: Deck, match: int, number: int) -> int:
    """Seed of game ``number`` (2 or 3) of a best-of-three match. Game 1 uses ``game_seed``, so it is the
    best-of-one game with the same index."""
    prints = sorted([first.fingerprint(), second.fingerprint()])
    digest = hashlib.sha256(f"{base_seed}|{prints[0]}|{prints[1]}|{match}|g{number}".encode()).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def match_game_number(record: dict) -> int:
    """Which game of its match a record is (1 for best-of-one games and for game 1 of a match)."""
    return int(record.get("match_game") or 1)


def plan_match_game(a: Entrant, b: Entrant, match: int, number: int, previous: dict,
                    options: RunOptions, run_dir: Path) -> Job:
    """Game ``number`` (2 or 3) of best-of-three match ``match`` between ``a`` and ``b``.

    The loser of the previous game starts (Forge's AI always chooses to play first, as most players do): it gets
    seat 0 and the driver is told that seat 0 starts. After a game without a winner (a draw, a time-out or an engine
    error) the player who started that game starts again. With ``options.sideboard`` both decks sideboard against
    each other's main deck before the game (the driver uses Forge's SideboardAdvisor).
    """
    by_key = {a.key: a, b.key: b}
    seats_before = previous["seats"]
    winner = previous.get("winner_seat", -1) if previous.get("status") == "ok" else -1
    if winner in (0, 1):
        starter = seats_before[1 - winner]
    elif previous.get("first_seat") in (0, 1):
        starter = seats_before[previous["first_seat"]]
    else:
        starter = seats_before[0]
    other = b.key if starter == a.key else a.key
    seats = [by_key[starter], by_key[other]]
    log_path = ""
    if options.save_logs:
        log_path = str(Path(run_dir).resolve() / "logs" / "games" / f"{a.key}__{b.key}__{match:04d}_g{number}.log")
    job = Job(
        id=f"{a.key}|{b.key}|{match}|g{number}",
        seed=match_game_seed(options.seed, a.deck, b.deck, match, number),
        decks=[s.dck_path for s in seats],
        timeout=options.timeout,
        monte_carlo=options.monte_carlo,
        log_path=log_path,
        profiles=_seat_profiles(seats, options),
        seat_monte_carlo=[] if options.force_monte_carlo else [s.ai_mc for s in seats],
        first_seat=0,
        sideboard=options.sideboard,
        meta={"a": a.key, "b": b.key, "game": match, "match_game": number, "seats": [s.key for s in seats]},
    )
    if job.uses_fixed_search():
        job.timeout = options.fixed_timeout
    return job


def next_match_games(a: Entrant, b: Entrant, by_id: Dict[str, dict], options: RunOptions,
                     run_dir: Path, number: int) -> List[Job]:
    """The game-``number`` jobs still needed for the pairing's matches, given the games recorded so far.

    A match goes on while neither deck has two wins and fewer than three games were played; a match whose
    previous game is missing (not played yet) gets nothing yet.
    """
    jobs = []
    for i in range(options.games):
        games = []
        for n in range(1, number):
            rid = f"{a.key}|{b.key}|{i}" if n == 1 else f"{a.key}|{b.key}|{i}|g{n}"
            if rid not in by_id:
                break
            games.append(by_id[rid])
        if len(games) != number - 1:
            continue
        wins = Counter()
        for g in games:
            w = g.get("winner_seat", -1)
            if g.get("status") == "ok" and w in (0, 1):
                wins[g["seats"][w]] += 1
        if max(wins.values(), default=0) >= 2:
            continue
        jobs.append(plan_match_game(a, b, i, number, games[-1], options, run_dir))
    return jobs


def _seat_profiles(seats: List[Entrant], options: RunOptions) -> List[str]:
    if options.force_profile or not any(s.ai_profile for s in seats):
        return [options.ai_profile] * len(seats) if options.ai_profile else []
    return [s.ai_profile or options.ai_profile for s in seats]


def prepare_profiles(install: ForgeInstall, run_dir: Path, jobs: Iterable[Job],
                     extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Write the run's AI profile folder and check that every profile a job names is in it.

    Returns the settings hash of each profile the jobs use ("Default" stands for a seat with none),
    so run.json records exactly which AI settings played.
    """
    hashes = ai_profiles.prepare_dir(install, Path(run_dir) / "ai", extra)
    named = {p for job in jobs for p in job.profiles if p}
    missing = sorted(p for p in named if p not in hashes)
    if missing:
        raise RunError(f"unknown AI profile(s): {', '.join(missing)}. Available: {', '.join(sorted(hashes))}")
    if any(not p for job in jobs for p in (job.profiles or [""])) and "Default" in hashes:
        named.add("Default")  # a seat without a profile plays Forge's preferred one, which the driver pins to Default
    return {p: hashes[p] for p in sorted(named)}


def _engine_fingerprint(install: ForgeInstall) -> Optional[str]:
    """Identifies the Forge build, so later runs (``tune --import``) can tell whether games are comparable."""
    try:
        return install.fingerprint()
    except OSError:
        return None


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
    if result.get("mc") is not None:  # search counters, only reported for games with Monte Carlo
        record["mc"] = result["mc"]
    if result.get("sideboard") is not None:  # each seat's "out>in" swaps, only for sideboarded games
        record["sideboard"] = result["sideboard"]
    if result.get("error"):
        record["error"] = str(result["error"])[:2000]
    return record


class Progress:
    """A single-line progress display on a terminal, periodic lines otherwise."""

    def __init__(self, total: int, already: int = 0, stream=None, quiet: bool = False, label: str = "games"):
        self.total, self.done, self.quiet, self.label = total, already, quiet, label
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
        text = (f"  {self.done}/{self.total} {self.label}  "
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
    profiles: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """Play every pairing, skipping games already recorded in ``run_dir``, and return all records.

    ``profiles`` adds run-generated AI profiles (name -> full profile text) to the run's profile folder.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_decks(entrants, run_dir)

    jobs: List[Job] = []
    for a, b in pairings:
        jobs.extend(plan_pairing(a, b, options, run_dir))
    used_profiles = prepare_profiles(install, run_dir, jobs, profiles)
    wanted = {job.id for job in jobs}
    have = {g["id"] for g in read_games(run_dir) if g["status"] in ("ok", "timeout")}
    todo = [job for job in jobs if job.id not in have]

    previous = run_dir / "run.json"
    if previous.is_file():
        try:
            before = json.loads(previous.read_text(encoding="utf-8")).get("options", {})
        except ValueError:
            before = {}
        def played_as(fmt: str, sideboard: bool) -> tuple:
            return (fmt, sideboard if fmt == "bo3" else None)  # best-of-one games never sideboard
        if played_as(before.get("match_format", "bo1"), before.get("sideboard", True)) != \
                played_as(options.match_format, options.sideboard):
            raise RunError(f"{run_dir} was played as {before.get('match_format', 'bo1')}"
                           + ("" if before.get("match_format", "bo1") == "bo1" else
                              " with" + ("" if before.get("sideboard", True) else "out") + " sideboarding")
                           + "; resume it with the same --bo3 / --no-sideboard options")
    patches = patches_for_run(install, run_dir / "run.json", quiet=quiet)  # warns if not what mtgsim ships
    run_info = dict(meta or {})
    described = options.describe()
    if any(job.uses_fixed_search() for job in jobs):
        described["timeout_fixed"] = options.fixed_timeout
    run_info.update({
        "options": described,
        "entrants": [e.describe() for e in entrants],
        "pairings": [[a.key, b.key] for a, b in pairings],
        "forge": {"version": install.version, "path": str(install.root), "fingerprint": _engine_fingerprint(install),
                  "patches": patches},
        "ai_profiles": used_profiles,
        "created": run_info.get("created") or time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=1), encoding="utf-8")

    expected_main = {e.key: e.deck.main_count for e in entrants}
    started = time.time()
    engine: dict = {}

    def run_round(round_jobs: List[Job], todo_jobs: List[Job], label: str = "games") -> None:
        progress = Progress(len(round_jobs), already=len(round_jobs) - len(todo_jobs), quiet=quiet, label=label)
        if not todo_jobs:
            return
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

            info = run_jobs(install, todo_jobs, on_result, workers=options.workers, heap=options.heap,
                            log_dir=run_dir / "logs", profile_dir=run_dir / "ai")
            if info:
                engine.update(info)

    run_round(jobs, todo, "games" if options.match_format == "bo1" else "games 1 of each match")
    if options.match_format == "bo3":
        # Games 2 and 3 depend on the results before them (who starts, whether game 3 is needed), so they are
        # played in two more rounds; a resumed run re-plans them from the games already recorded.
        for number in (2, 3):
            by_id = {g["id"]: g for g in read_games(run_dir)}
            round_jobs: List[Job] = []
            for a, b in pairings:
                round_jobs.extend(next_match_games(a, b, by_id, options, run_dir, number))
            wanted.update(job.id for job in round_jobs)
            have = {g["id"] for g in read_games(run_dir) if g["status"] in ("ok", "timeout")}
            run_round(round_jobs, [job for job in round_jobs if job.id not in have], f"games {number} of the matches")

    if engine:
        run_info["forge"].update(engine)
    run_info["elapsed_seconds"] = round(run_info.get("elapsed_seconds", 0) + time.time() - started, 1)
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=1), encoding="utf-8")
    return [g for g in read_games(run_dir) if g["id"] in wanted]
