"""Searching Forge AI profile settings that make simulated win rates track real ones.

Forge's AI pilots every deck, and it pilots creature decks better than control and value decks:
in a round robin of the meta decks, simulated win rates barely tracked real ones. ``tune`` asks
whether changing the AI's profile settings (``AiProps``) closes that gap, and how far the answer
can be trusted.

What is searched
    A *space* file lists AI settings and alternative values (``profiles/spaces/default.json``).
    Decks are put into *groups* by their ``category`` in ``gauntlet.json`` (default: reactive =
    control, midrange, tempo; proactive = aggro, ramp, combo). Every deck of a group plays with
    that group's profile, so a profile is a knob shared by several decks, not one free knob per
    deck. For each tuned group ``--profiles K`` random profiles are drawn (each setting changed
    from the base with the space's ``change_probability``); a *candidate* is one profile per
    group, and the candidates are every combination of them, including the base profile. The
    candidate with every group on the base profile is the baseline.

What is measured
    Each candidate plays the full round robin. A deck's simulated win rate is its average over
    its opponents; the objective is the Spearman rank correlation between simulated and real win
    rates over the *training* decks (Pearson and the mean absolute gap are reported too). An
    optional matchup file of real deck-vs-deck win rates adds matchup-level data points.

Guards against fooling ourselves
    * ``--holdout`` decks play in every game but their real win rates are never used to choose
      anything; their metrics are reported separately.
    * ``--cv`` cross-validates the selection step over the training decks (each deck's simulated
      win rate is taken from the candidate chosen without that deck), on the first round's games.
    * Every metric comes with a game-noise range: pairing results are resampled (binomially,
      around (wins + 0.5) / (decided + 1)) and the metrics recomputed. Pairings two candidates
      share are the same games, so they are resampled identically and differences are paired.
    * The winner is re-played with the baseline on fresh games (``--confirm``), which were not
      used for selection, so its reported improvement is not inflated by having been picked.
    * A plain statement of how much real-world data would be needed to trust the result.

Saving compute
    A game's outcome depends only on the two decks (contents and name), each seat's effective
    profile settings, the seed, the game index, Monte Carlo and the time limit. Results are
    cached under exactly that key (``pairing_key`` plus the game index), so a pairing in which
    neither deck's profile changed is never replayed, and later rounds only play the extra games.
    The search is successive halving: every candidate plays the first ``--rounds`` number of
    games per pairing, the best 1/``--eta`` (plus the baseline) the next number, and so on.

Run directory::

    tune.json    settings, decks, space, profiles, candidates, every round's metrics, the result
    cache.jsonl  one line per game played or imported: the cache
    ai/          the profile folder handed to Forge (Forge's, mtgsim's, the user's, the candidates)
    best/        the winning profiles as override files, usable from MTGSIM_HOME/profiles
    decks/, logs/
"""

from __future__ import annotations

import bisect
import hashlib
import itertools
import json
import math
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import ai_profiles, experiment, forge, runner, stats
from .experiment import Entrant, RunError
from .forge import ForgeInstall
from .runner import Job

TUNE_VERSION = 1
CACHE_VERSION = 1
DEFAULT_SPACE = Path(__file__).resolve().parent / "profiles" / "spaces" / "default.json"
DEFAULT_GROUPS: Dict[str, Tuple[str, ...]] = {
    "reactive": ("control", "midrange", "tempo"),
    "proactive": ("aggro", "ramp", "combo"),
}
GAMES_PER_MINUTE = 85.0  # measured on 4 cores with the meta decks (VALIDATION.md)
ROUND_OVERHEAD_MINUTES = 0.5  # every batch starts fresh JVMs, which load the card database
GAME_FORMAT = "Constructed"
GROUP_RE = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
FISHER_SPEARMAN = 1.06  # variance factor of Fisher's z for Spearman's rho (Fieller, Hartley & Pearson 1957)


# ===================================================================== the space


@dataclass
class Param:
    """One searchable setting (or several settings changed together)."""

    name: str
    keys: Tuple[str, ...]
    values: List[Tuple[str, ...]]
    groups: Optional[Tuple[str, ...]] = None  # None: every group
    why: str = ""

    def applies_to(self, group: str) -> bool:
        return self.groups is None or group in self.groups

    def to_json(self) -> dict:
        out: dict = {"name": self.name, "keys": list(self.keys), "values": [list(v) for v in self.values]}
        if self.groups is not None:
            out["groups"] = list(self.groups)
        if self.why:
            out["why"] = self.why
        return out


@dataclass
class Space:
    base: str
    change_probability: float
    params: List[Param]
    description: str = ""

    def to_json(self) -> dict:
        return {"description": self.description, "base": self.base,
                "change_probability": self.change_probability, "params": [p.to_json() for p in self.params]}


def parse_space(data, known: Optional[Set[str]] = None) -> Space:
    """Validate a space definition (see profiles/spaces/default.json for the format)."""
    if not isinstance(data, dict):
        raise RunError("a parameter space must be a JSON object with \"base\" and \"params\"")
    base = data.get("base", "Default")
    if not isinstance(base, str) or not base:
        raise RunError("the space's \"base\" must be a profile name")
    p = data.get("change_probability", 0.3)
    if not isinstance(p, (int, float)) or not 0 < p <= 1:
        raise RunError("\"change_probability\" must be a number in (0, 1]")
    raw = data.get("params")
    if not isinstance(raw, list) or not raw:
        raise RunError("the space needs a non-empty \"params\" list")
    params: List[Param] = []
    for i, entry in enumerate(raw):
        where = f"param {i + 1}"
        if not isinstance(entry, dict):
            raise RunError(f"{where} must be an object")
        if ("key" in entry) == ("keys" in entry):
            raise RunError(f"{where} needs exactly one of \"key\" or \"keys\"")
        try:
            keys = tuple(ai_profiles.check_key(k, known) for k in ([entry["key"]] if "key" in entry else entry["keys"]))
            if not keys or len(set(keys)) != len(keys):
                raise RunError(f"{where}: \"keys\" must name distinct settings")
            values_raw = entry.get("values")
            if not isinstance(values_raw, list) or not values_raw:
                raise RunError(f"{where} ({'+'.join(keys)}) needs a non-empty \"values\" list")
            values = []
            for value in values_raw:
                if "key" in entry:
                    value = [value]
                if not isinstance(value, list) or len(value) != len(keys):
                    raise RunError(f"{where} ({'+'.join(keys)}): every value must list {len(keys)} settings")
                values.append(tuple(ai_profiles.format_value(v) for v in value))
        except ai_profiles.ProfileError as exc:
            raise RunError(f"{where}: {exc}")
        groups = entry.get("groups")
        if groups is not None:
            if not isinstance(groups, list) or not groups or not all(isinstance(g, str) for g in groups):
                raise RunError(f"{where}: \"groups\" must be a list of group names")
            groups = tuple(groups)
        name = str(entry.get("name") or (keys[0] if len(keys) == 1 else "+".join(keys)))
        params.append(Param(name, keys, list(dict.fromkeys(values)), groups, str(entry.get("why") or "")))
    for a, b in itertools.combinations(params, 2):
        shared = set(a.keys) & set(b.keys)
        overlap = a.groups is None or b.groups is None or set(a.groups) & set(b.groups)
        if shared and overlap:
            raise RunError(f"setting {sorted(shared)[0]} appears in two parameters for the same group "
                           f"({a.name}, {b.name}); give them disjoint \"groups\"")
    return Space(base, float(p), params, str(data.get("description") or ""))


def load_space(path: Path, known: Optional[Set[str]] = None) -> Space:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunError(f"cannot read the parameter space {path}: {exc}")
    except ValueError as exc:
        raise RunError(f"{path} is not valid JSON: {exc}")
    return parse_space(data, known)


def sample_overrides(space: Space, group: str, base: Mapping[str, str], rng: random.Random,
                     taken: Iterable[str] = ()) -> Dict[str, str]:
    """A random profile for one group, as the settings that differ from the base's effective ones.

    Each applicable parameter changes with the space's probability (at least one always changes);
    a draw that repeats a profile in ``taken`` (override keys, see ``overrides_id``) is redrawn.
    """
    params = [p for p in space.params if p.applies_to(group)]

    def alternatives(p: Param) -> List[Tuple[str, ...]]:
        current = tuple(base.get(k) for k in p.keys)
        return [v for v in p.values if v != current]

    usable = [p for p in params if alternatives(p)]
    if not usable:
        raise RunError(f"the space has nothing to change for group \"{group}\"")
    taken = set(taken)
    for _attempt in range(200):
        chosen: Dict[str, str] = {}
        for p in usable:
            if rng.random() < space.change_probability:
                chosen.update(zip(p.keys, rng.choice(alternatives(p))))
        if not chosen:
            p = rng.choice(usable)
            chosen.update(zip(p.keys, rng.choice(alternatives(p))))
        overrides = {k: v for k, v in sorted(chosen.items()) if base.get(k) != v}
        if overrides and overrides_id(overrides) not in taken:
            return overrides
    raise RunError(f"could not draw enough distinct profiles for group \"{group}\"; "
                   "the space is too small for this --profiles")


def overrides_id(overrides: Mapping[str, str]) -> str:
    return hashlib.sha256(json.dumps(sorted(overrides.items())).encode("utf-8")).hexdigest()[:10]


def profile_name(group: str, base: str, overrides: Mapping[str, str]) -> str:
    return base if not overrides else f"tune-{group}-{overrides_id(overrides)}"


def make_candidates(space: Space, tuned: Sequence[str], all_groups: Sequence[str], per_group: int,
                    base_settings: Mapping[str, str], rng: random.Random) -> Tuple[Dict[str, dict], List[dict]]:
    """Profiles per tuned group (the base plus ``per_group`` random ones) and every combination of them.

    Returns (profiles by name, candidates). Candidate ``c00`` is the baseline. Factorial
    combinations share pairings: two candidates that give a group the same profile replay none of
    that group's internal games.
    """
    profiles: Dict[str, dict] = {}
    pools: Dict[str, List[str]] = {}
    for group in all_groups:
        base_name = profile_name(group, space.base, {})
        profiles.setdefault(base_name, {"group": None, "base": space.base, "overrides": {}, "label": "base"})
        pools[group] = [base_name]
        if group not in tuned:
            continue
        taken: List[str] = []
        for i in range(per_group):
            overrides = sample_overrides(space, group, base_settings, rng, taken)
            taken.append(overrides_id(overrides))
            name = profile_name(group, space.base, overrides)
            profiles[name] = {"group": group, "base": space.base, "overrides": overrides, "label": f"{group}#{i + 1}"}
            pools[group].append(name)
    candidates = []
    order = list(all_groups)
    for n, combo in enumerate(itertools.product(*(pools[g] for g in order))):
        candidates.append({"id": f"c{n:02d}", "profiles": dict(zip(order, combo)), "baseline": n == 0})
    return profiles, candidates


# ======================================================================= decks


@dataclass
class TuneDeck:
    entrant: Entrant
    group: str
    real: Optional[float]  # real win rate as a fraction, or None when unknown
    holdout: bool = False

    @property
    def key(self) -> str:
        return self.entrant.key

    @property
    def name(self) -> str:
        return self.entrant.deck.name


def parse_groups(values: Optional[Sequence[str]]) -> Dict[str, Tuple[str, ...]]:
    """``["reactive=control,midrange", ...]`` -> {group: categories}; the default when none are given."""
    if not values:
        return dict(DEFAULT_GROUPS)
    groups: Dict[str, Tuple[str, ...]] = {}
    seen: Dict[str, str] = {}
    for value in values:
        name, sep, cats = value.partition("=")
        name = name.strip().lower()
        if not sep or not GROUP_RE.match(name):
            raise RunError(f"--group takes NAME=CATEGORY,CATEGORY (lower-case name), not {value!r}")
        categories = tuple(c.strip().lower() for c in cats.split(",") if c.strip())
        if not categories:
            raise RunError(f"--group {name} lists no categories")
        for c in categories:
            if c in seen:
                raise RunError(f"category {c} is in two groups ({seen[c]} and {name})")
            seen[c] = name
        groups[name] = categories
    return groups


def make_decks(entrants: Sequence[Entrant], real_rates: Mapping[str, Optional[float]],
               groups: Mapping[str, Sequence[str]], holdout: Sequence[str] = ()) -> List[TuneDeck]:
    """Attach group, real win rate (percent in, fraction out) and hold-out flag to each deck."""
    by_category = {c: g for g, cats in groups.items() for c in cats}
    held = resolve_decks(holdout, entrants, "--holdout")
    decks = []
    for e in entrants:
        category = (e.category or "").lower()
        if category not in by_category:
            raise RunError(f"{e.deck.name} has category {category or '(none)'!r}, which no group covers; "
                           "set its category in gauntlet.json or add it with --group")
        real = real_rates.get(e.key)
        if real is not None:
            if not isinstance(real, (int, float)) or not 0 <= real <= 100:
                raise RunError(f"real_win_rate of {e.deck.name} must be a percentage, not {real!r}")
            real = float(real) / 100.0
        decks.append(TuneDeck(e, by_category[category], real, e.key in held))
    return decks


def resolve_decks(names: Sequence[str], entrants: Sequence[Entrant], option: str) -> Set[str]:
    """Deck keys for names given on the command line: display name, key, file name or file stem."""
    keys: Set[str] = set()
    for name in names:
        wanted = name.strip().lower()
        hits = [e.key for e in entrants if wanted in {
            e.key.lower(), e.deck.name.lower(),
            (e.deck.path.name.lower() if e.deck.path else ""), (e.deck.path.stem.lower() if e.deck.path else "")}]
        if len(hits) != 1:
            known = ", ".join(e.deck.name for e in entrants)
            raise RunError(f"{option} {name!r} matches {'no' if not hits else 'more than one'} deck. Decks: {known}")
        keys.add(hits[0])
    return keys


@dataclass
class Matchup:
    a: str  # deck keys, in the run's pairing orientation
    b: str
    real: float  # a's real win rate against b, as a fraction
    games: Optional[int]
    source: str = ""


def load_matchups(path: Path, decks: Sequence[TuneDeck]) -> Tuple[List[Matchup], List[str]]:
    """Real deck-vs-deck win rates: a JSON list (or {"matchups": [...]}) of
    {"a", "b", "real_win_rate" (percent, a's), "games", "source"}. Entries for decks outside the run
    are skipped; several entries for one pair are pooled by their games."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunError(f"cannot read the matchup file {path}: {exc}")
    entries = data.get("matchups") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise RunError(f"{path} must be a list of matchups or an object with a \"matchups\" list")
    order = {d.key: i for i, d in enumerate(decks)}
    entrants = [d.entrant for d in decks]
    notes: List[str] = []
    pooled: Dict[Tuple[str, str], List] = {}
    for n, entry in enumerate(entries):
        if not isinstance(entry, dict) or not all(k in entry for k in ("a", "b", "real_win_rate")):
            raise RunError(f"{path}, entry {n + 1}: needs \"a\", \"b\" and \"real_win_rate\"")
        try:
            a = next(iter(resolve_decks([str(entry["a"])], entrants, "matchup deck")))
            b = next(iter(resolve_decks([str(entry["b"])], entrants, "matchup deck")))
        except RunError:
            notes.append(f"skipped {entry['a']} vs {entry['b']}: not both in this run")
            continue
        rate = entry["real_win_rate"]
        games = entry.get("games")
        if a == b or not isinstance(rate, (int, float)) or not 0 <= rate <= 100:
            raise RunError(f"{path}, entry {n + 1}: real_win_rate must be a percentage for two different decks")
        if games is not None and (not isinstance(games, int) or games < 1):
            raise RunError(f"{path}, entry {n + 1}: games must be a positive whole number")
        rate = float(rate) / 100.0
        if order[a] > order[b]:
            a, b, rate = b, a, 1.0 - rate
        pooled.setdefault((a, b), []).append((rate, games, str(entry.get("source") or "")))
    out = []
    for (a, b), rows in pooled.items():
        if len(rows) == 1:
            rate, games, source = rows[0]
        else:
            if any(g is None for _, g, _ in rows):
                raise RunError(f"{path}: several entries for {a} vs {b}; all of them need \"games\" to be pooled")
            games = sum(g for _, g, _ in rows)
            rate = sum(r * g for r, g, _ in rows) / games
            source = "; ".join(s for _, _, s in rows if s)
        out.append(Matchup(a, b, rate, games, source))
    return out, notes


# ===================================================================== metrics


def ranks(values: Sequence[float]) -> List[float]:
    """1-based ranks, ties sharing their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return out


def pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    n = len(x)
    if n < 3 or n != len(y):
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    return pearson(ranks(x), ranks(y)) if len(x) >= 3 and len(x) == len(y) else None


def compare(sim: Mapping[str, Optional[float]], real: Mapping[str, Optional[float]], keys: Iterable[str]) -> dict:
    """Agreement of simulated and real win rates over ``keys`` (those with both numbers)."""
    keys = [k for k in keys if sim.get(k) is not None and real.get(k) is not None]
    x = [sim[k] for k in keys]
    y = [real[k] for k in keys]
    return {"n": len(keys), "spearman": spearman(x, y), "pearson": pearson(x, y),
            "mae": sum(abs(a - b) for a, b in zip(x, y)) / len(keys) if keys else None}


def spearman_interval(r: Optional[float], n: int, z: float = stats.Z95) -> Optional[Tuple[float, float]]:
    """95% interval of a rank correlation over n independent data points (Fisher's z)."""
    if r is None or n < 4:
        return None
    r = max(-0.999, min(0.999, r))
    se = math.sqrt(FISHER_SPEARMAN / (n - 3))
    centre = math.atanh(r)
    return (math.tanh(centre - z * se), math.tanh(centre + z * se))


def points_needed(r: float, half_width: float, limit: int = 100000) -> Optional[int]:
    """Data points needed for the 95% interval of a rank correlation near ``r`` to be +/-half_width."""
    def half(n: int) -> float:
        lo, hi = spearman_interval(r, n)
        return (hi - lo) / 2.0

    lo, hi = 4, limit
    if half(hi) > half_width:
        return None
    while lo < hi:  # the half-width shrinks as n grows
        mid = (lo + hi) // 2
        if half(mid) <= half_width:
            hi = mid
        else:
            lo = mid + 1
    return lo


def matches_for_margin(margin: float, p: float = 0.5) -> int:
    """Real matches needed for a matchup win rate's 95% interval to be +/-margin."""
    return int(math.ceil((stats.Z95 ** 2) * p * (1 - p) / (margin * margin)))


def data_needed(train_n: int, r: Optional[float], deck_count: int, matchups_given: int = 0) -> dict:
    """How much real-world data it would take to trust a correlation measured on ``train_n`` decks."""
    r_used = 0.5 if r is None else max(-0.95, min(0.95, r))
    iv = spearman_interval(r, train_n)
    need = {f"{w:.2f}": points_needed(r_used, w) for w in (0.1, 0.15, 0.2)}
    at_half = {f"{w:.2f}": points_needed(0.5, w) for w in (0.1, 0.2)}

    def round_robin_decks(points: Optional[int]) -> Optional[int]:
        return None if points is None else int(math.ceil((1 + math.sqrt(1 + 8 * points)) / 2))

    lines = []
    if iv is not None:
        lines.append(f"With {train_n} training decks, a rank correlation of {r:.2f} has a 95% interval of "
                     f"{iv[0]:+.2f} to {iv[1]:+.2f} from the choice of decks alone, before any game noise: "
                     "the real-world data cannot tell a good calibration from a useless one.")
    else:
        lines.append(f"With {train_n} training decks no interval can be given for the rank correlation.")
    lines.append(f"Pinning it to +/-0.2 would take about {need['0.20']} decks with real win rates, +/-0.1 about "
                 f"{need['0.10']} (near r = {r_used:.2f}; near r = 0.5: {at_half['0.20']} and {at_half['0.10']}).")
    full = deck_count * (deck_count - 1) // 2
    lines.append(
        f"Matchup-level real data (deck-vs-deck win rates) gives up to {full} data points for these {deck_count} decks"
        + (f" ({matchups_given} supplied)" if matchups_given else "")
        + f". Even treated as independent (they are not: each deck is in {deck_count - 1} of them), +/-0.2 needs "
        f"about {need['0.20']} matchups, a full round robin of about {round_robin_decks(need['0.20'])} decks, and "
        f"each real matchup win rate needs about {matches_for_margin(0.10)} matches to be known to +/-10 points "
        f"({matches_for_margin(0.05)} for +/-5).")
    lines.append("The real deck win rates' own sampling error is not included (their match counts are not recorded); "
                 "it can only widen these intervals.")
    return {"train_decks": train_n, "spearman": r, "interval": list(iv) if iv else None,
            "points_needed": need, "points_needed_at_0.5": at_half, "text": lines}


# ===================================================================== the cache


def engine_identity(install: ForgeInstall, patches: Mapping) -> str:
    """What counts as "the same engine" for the cache: the Forge build and the Forge patch set applied
    to it. A game played on a patched Forge (a fixed card script, a changed AI rule) is a different
    game; a card-script patch changes neither the jar nor the folder timestamps, so the patch set
    is named explicitly here even though the fingerprint also folds it in."""
    return f"{install.fingerprint()}|patches={patches.get('combined_sha256') or 'none'}"


def pairing_key(engine: str, seed: int, a: Entrant, b: Entrant, hash_a: str, hash_b: str,
                mc: str, timeout: int) -> str:
    """Everything that decides a pairing's games except the game index.

    ``engine`` is ``engine_identity`` (Forge build plus applied patch set). Deck names are included
    because Forge reads them (a deck whose name contains "Control" is piloted as a non-aggro deck);
    profiles enter by their effective settings, not their names (Forge's own profiles are copied
    from the patched checkout, so a patch to them changes their hash too).
    """
    payload = [CACHE_VERSION, engine, seed, GAME_FORMAT, mc, timeout,
               a.deck.fingerprint(), a.deck.name, hash_a, b.deck.fingerprint(), b.deck.name, hash_b]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


class GameCache:
    """Game results keyed by (pairing key, game index), kept in an append-only JSONL file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.games: Dict[Tuple[str, int], dict] = {}
        if self.path.is_file():
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        self.games[(record["pk"], int(record["g"]))] = record
                    except (ValueError, KeyError, TypeError):
                        continue  # a line cut short by an interrupted run

    def __contains__(self, item: Tuple[str, int]) -> bool:
        return item in self.games

    def __len__(self) -> int:
        return len(self.games)

    def get(self, pk: str, g: int) -> Optional[dict]:
        return self.games.get((pk, g))

    def add(self, record: dict) -> None:
        self.games[(record["pk"], int(record["g"]))] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")


# ================================================================= evaluation


@dataclass
class PairResult:
    a: str
    b: str
    pk: str
    wins: int = 0  # a's wins
    decided: int = 0
    found: int = 0  # games in the cache (decided, drawn or timed out)
    wanted: int = 0


def collect(cache: GameCache, pk: str, a: str, b: str, games: range) -> PairResult:
    result = PairResult(a, b, pk, wanted=len(games))
    for g in games:
        record = cache.get(pk, g)
        if record is None:
            continue
        result.found += 1
        if record.get("status") == "ok" and record.get("winner") in ("a", "b"):
            result.decided += 1
            result.wins += 1 if record["winner"] == "a" else 0
    return result


def deck_rates(pairs: Iterable[Tuple[str, str, int, int]], keys: Iterable[str]) -> Dict[str, Optional[float]]:
    """Each deck's average win rate over its opponents, from (a, b, a's wins, decided) per pairing."""
    samples: Dict[str, List[Tuple[int, int]]] = {k: [] for k in keys}
    for a, b, wins, decided in pairs:
        if decided > 0:
            samples[a].append((wins, decided))
            samples[b].append((decided - wins, decided))
    return {k: stats.weighted_rate(s)["rate"] if s else None for k, s in samples.items()}


def binomial_draws(n: int, p: float, count: int, rng: random.Random) -> List[int]:
    """``count`` draws from Binomial(n, p) by inverting the exact distribution."""
    if n <= 0:
        return [0] * count
    p = min(max(p, 1e-9), 1 - 1e-9)
    logs = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log(1 - p)
            for k in range(n + 1)]
    top = max(logs)
    weights = [math.exp(v - top) for v in logs]
    cumulative = list(itertools.accumulate(weights))
    total = cumulative[-1]
    return [min(n, bisect.bisect_left(cumulative, rng.random() * total)) for _ in range(count)]


class Resampler:
    """Game-noise resampling. Draws are kept per (pairing key, game range), so every candidate that
    shares a pairing's games sees the same resampled result, which makes differences paired."""

    def __init__(self, draws: int, seed: int):
        self.draws = max(0, draws)
        self.rng = random.Random(f"tune-bootstrap-{seed}")
        self._sim: Dict[tuple, List[int]] = {}
        self._real: Dict[tuple, List[float]] = {}

    def sim(self, pair: PairResult, games: range) -> List[int]:
        key = (pair.pk, games.start, games.stop)
        if key not in self._sim:
            p = (pair.wins + 0.5) / (pair.decided + 1.0)
            self._sim[key] = binomial_draws(pair.decided, p, self.draws, self.rng)
        return self._sim[key]

    def real(self, m: Matchup) -> List[float]:
        key = (m.a, m.b)
        if key not in self._real:
            if m.games:
                self._real[key] = [w / m.games for w in binomial_draws(m.games, m.real, self.draws, self.rng)]
            else:
                self._real[key] = [m.real] * self.draws
        return self._real[key]


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    pos = q * (len(values) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def noise_range(values: Sequence[Optional[float]]) -> Optional[List[float]]:
    lo, hi = percentile(values, 0.025), percentile(values, 0.975)
    return None if lo is None else [lo, hi]


# ===================================================================== the search


def successive_halving_keep(ranked: Sequence[str], eta: int, baseline: str) -> List[str]:
    """The candidates that go on to the next round: the best ceil(n / eta), and always the baseline."""
    keep = list(ranked[:max(1, int(math.ceil(len(ranked) / float(eta))))])
    if baseline not in keep:
        keep.append(baseline)
    return keep


def parse_rounds(text: str) -> List[int]:
    try:
        rounds = [int(x) for x in str(text).split(",") if x.strip()]
    except ValueError:
        raise RunError(f"--rounds takes games per pairing for each round, like 10,30, not {text!r}")
    if not rounds or any(g < 1 for g in rounds) or any(b <= a for a, b in zip(rounds, rounds[1:])):
        raise RunError("--rounds must be increasing positive numbers of games per pairing, like 10,30")
    return rounds


def parse_cv(text) -> int:
    """0 = off, -1 = leave one deck out, k >= 2 = k folds."""
    text = str(text).strip().lower()
    if text in ("off", "0", "none", ""):
        return 0
    if text == "loo":
        return -1
    try:
        k = int(text)
    except ValueError:
        k = 0
    if k < 2:
        raise RunError("--cv takes loo, a number of folds (2 or more), or off")
    return k


class Tuner:
    """One tuning run: decks, candidates, the cache and the engine, and every round's results."""

    def __init__(self, install: ForgeInstall, run_dir: Path, decks: List[TuneDeck], space: Space,
                 settings: dict, profiles: Dict[str, dict], candidates: List[dict],
                 matchups: Optional[List[Matchup]] = None, engine_id: Optional[str] = None,
                 say: Callable[[str], None] = print, workers: Optional[int] = None, heap: str = "2g",
                 patches: Optional[dict] = None):
        self.install, self.run_dir, self.decks, self.space = install, Path(run_dir), decks, space
        self.settings, self.profiles, self.candidates = settings, profiles, candidates
        self.matchups = matchups or []
        # The Forge patch set (as run.json records it) and the engine identity the cache keys use.
        self.patches = patches if patches is not None else (
            {"state": "not-managed", "applied": [], "combined_sha256": ""} if engine_id is not None
            else forge.patch_status(install).record())
        self.engine_id = engine_id if engine_id is not None else engine_identity(install, self.patches)
        self.build_fingerprint = engine_id if engine_id is not None else install.fingerprint()
        self.say, self.workers, self.heap = say, workers, heap
        self.by_key = {d.key: d for d in decks}
        self.index = {d.key: i for i, d in enumerate(decks)}
        self.pairs = [(decks[i].key, decks[j].key) for i in range(len(decks)) for j in range(i + 1, len(decks))]
        self.cache = GameCache(self.run_dir / "cache.jsonl")
        self.resampler = Resampler(settings.get("bootstrap", 1000), settings["seed"])
        self.train = [d.key for d in decks if not d.holdout and d.real is not None]
        self.held = [d.key for d in decks if d.holdout and d.real is not None]
        self.real = {d.key: d.real for d in decks}
        self._fold: Set[str] = set()  # decks a cross-validation fold hides from selection
        self.texts: Dict[str, str] = {}
        self.hashes: Dict[str, str] = {}
        self.log: dict = {}

    # --------------------------------------------------------------- set-up

    def prepare(self) -> None:
        """Write decks and profiles, and work out every profile's effective settings hash."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        experiment.write_decks([d.entrant for d in self.decks], self.run_dir)
        for name, info in self.profiles.items():
            if info["overrides"]:
                header = [f"mtgsim tune candidate {info['label']}: {info['base']} with "
                          f"{len(info['overrides'])} setting(s) changed"]
                self.texts[name] = ai_profiles.build(self.install, info["base"], info["overrides"], header)
        hashes = ai_profiles.prepare_dir(self.install, self.run_dir / "ai", self.texts)
        for name in self.profiles:
            if name not in hashes:
                raise RunError(f"AI profile \"{name}\" is not available")
            self.profiles[name]["hash"] = hashes[name]
        self.hashes = hashes

    def profile_of(self, cand: dict, deck: str) -> str:
        return cand["profiles"][self.by_key[deck].group]

    def pk(self, cand: dict, a: str, b: str) -> str:
        return pairing_key(self.engine_id, self.settings["seed"], self.by_key[a].entrant, self.by_key[b].entrant,
                           self.hashes[self.profile_of(cand, a)], self.hashes[self.profile_of(cand, b)],
                           self.settings["mc"], self.settings["timeout"])

    def cand(self, cid: str) -> dict:
        return next(c for c in self.candidates if c["id"] == cid)

    # ---------------------------------------------------------------- games

    def needed(self, cids: Iterable[str], games: range) -> Tuple[List[tuple], int]:
        """Games still to play for these candidates, each once, and how many game results they use."""
        todo: Dict[Tuple[str, int], tuple] = {}
        used = 0
        for cid in cids:
            cand = self.cand(cid)
            for a, b in self.pairs:
                pk = self.pk(cand, a, b)
                for g in games:
                    used += 1
                    if (pk, g) not in self.cache and (pk, g) not in todo:
                        todo[(pk, g)] = (pk, g, a, b, self.profile_of(cand, a), self.profile_of(cand, b))
        return list(todo.values()), used

    def play(self, todo: List[tuple]) -> Counter:
        """Play games on the engine and add them to the cache."""
        counts: Counter = Counter()
        if not todo:
            return counts
        jobs = []
        for pk, g, a, b, prof_a, prof_b in todo:
            da, db = self.by_key[a], self.by_key[b]
            a_seat = 0 if g % 2 == 0 else 1  # seats alternate by game index, as in experiment.plan_pairing
            seats = [da, db] if a_seat == 0 else [db, da]
            profs = [prof_a, prof_b] if a_seat == 0 else [prof_b, prof_a]
            jobs.append(Job(
                id=f"{pk}|{g}", seed=experiment.game_seed(self.settings["seed"], da.entrant.deck, db.entrant.deck, g),
                decks=[s.entrant.dck_path for s in seats], timeout=self.settings["timeout"],
                monte_carlo=self.settings["mc"], profiles=profs,
                meta={"pk": pk, "g": g, "a_seat": a_seat, "seats": [s.key for s in seats]},
            ))
        progress = experiment.Progress(len(jobs))

        def on_result(job: Job, result: dict) -> None:
            seats = job.meta["seats"]
            players = result.get("players") or []
            for seat, player in enumerate(players):
                key = seats[seat]
                loaded = player.get("mainCount")
                expected = self.by_key[key].entrant.deck.main_count
                if loaded is not None and loaded != expected:
                    raise RunError(f"Forge loaded {loaded} main-deck cards for \"{key}\" but the list has {expected}: "
                                   "the engine did not recognise some card names, so the run was stopped.")
            status = result.get("status", "error")
            counts[status] += 1
            progress.tick()
            if status not in ("ok", "timeout"):
                return  # not cached: an engine failure is retried on the next run
            a_seat = job.meta["a_seat"]
            side = {a_seat: "a", 1 - a_seat: "b"}
            mull = [(players[s].get("mulligans") if s < len(players) else None) for s in (a_seat, 1 - a_seat)]
            self.cache.add({
                "pk": job.meta["pk"], "g": job.meta["g"], "status": status,
                "winner": side.get(result.get("winner", -1)), "first": side.get(result.get("first", -1)),
                "turns": result.get("turns"), "ms": result.get("ms"), "mull": mull, "seed": job.seed, "src": "play",
            })

        runner.run_jobs(self.install, jobs, on_result, workers=self.workers, heap=self.heap,
                        log_dir=self.run_dir / "logs", profile_dir=self.run_dir / "ai")
        return counts

    # ----------------------------------------------------------- evaluation

    def results(self, cid: str, games: range) -> List[PairResult]:
        cand = self.cand(cid)
        return [collect(self.cache, self.pk(cand, a, b), a, b, games) for a, b in self.pairs]

    def _metric_set(self, pairs: Sequence[Tuple[str, str, int, int]], real_matchups: Optional[Sequence[float]]) -> dict:
        rates = deck_rates(pairs, self.by_key)
        out = {"train": compare(rates, self.real, self.train), "holdout": compare(rates, self.real, self.held),
               "all": compare(rates, self.real, self.train + self.held)}
        if self.matchups:
            sim_m = {}
            lookup = {(a, b): (w, n) for a, b, w, n in pairs}
            for m in self.matchups:
                w, n = lookup.get((m.a, m.b), (0, 0))
                sim_m[(m.a, m.b)] = w / n if n else None
            real_m = {(m.a, m.b): (real_matchups[i] if real_matchups is not None else m.real)
                      for i, m in enumerate(self.matchups)}
            hidden = {d.key for d in self.decks if d.holdout} | self._fold
            train_m = [(m.a, m.b) for m in self.matchups if m.a not in hidden and m.b not in hidden]
            held_m = [(m.a, m.b) for m in self.matchups if (m.a in hidden or m.b in hidden)
                      and m.a not in self._fold and m.b not in self._fold]
            out["matchup_train"] = compare(sim_m, real_m, train_m)
            out["matchup_holdout"] = compare(sim_m, real_m, held_m)
        out["objective"] = self.objective(out)
        return out

    def objective(self, metrics: dict) -> Optional[float]:
        kind = self.settings.get("objective", "deck")
        deck = metrics["train"]["spearman"]
        match = metrics.get("matchup_train", {}).get("spearman")
        if kind == "deck":
            return deck
        if kind == "matchup":
            return match
        both = [v for v in (deck, match) if v is not None]
        return sum(both) / len(both) if both else None

    def evaluate(self, cid: str, games: range, noise: bool = True) -> dict:
        results = self.results(cid, games)
        pairs = [(r.a, r.b, r.wins, r.decided) for r in results]
        point = self._metric_set(pairs, None)
        rates = deck_rates(pairs, self.by_key)
        out = {"candidate": cid, "games": [games.start, games.stop],
               "played": sum(r.found for r in results), "wanted": sum(r.wanted for r in results),
               "decided": sum(r.decided for r in results), "deck_rates": rates, "metrics": point,
               "objective": point["objective"]}
        if noise and self.resampler.draws:
            out["draws"] = self.resample(results, games)
            out["noise"] = self.noise_of(out["draws"])
        return out

    def resample(self, results: List[PairResult], games: range) -> List[dict]:
        draws = [self.resampler.sim(r, games) for r in results]
        real_draws = [self.resampler.real(m) for m in self.matchups]
        sets = []
        for b in range(self.resampler.draws):
            pairs = [(r.a, r.b, d[b], r.decided) for r, d in zip(results, draws)]
            real_m = [rd[b] for rd in real_draws] if self.matchups else None
            sets.append(self._metric_set(pairs, real_m))
        return sets

    @staticmethod
    def noise_of(draws: List[dict]) -> dict:
        out: dict = {"objective": noise_range([d["objective"] for d in draws])}
        for part in draws[0] if draws else {}:
            if part == "objective":
                continue
            out[part] = {m: noise_range([d[part][m] for d in draws]) for m in ("spearman", "pearson", "mae")}
        return out

    @staticmethod
    def paired_difference(first: dict, second: dict) -> dict:
        """first minus second, metric by metric, with the paired game-noise range."""
        out: dict = {}
        for part, metrics in first["metrics"].items():
            if part == "objective":
                continue
            out[part] = {}
            for m in ("spearman", "pearson", "mae"):
                a, b = metrics.get(m), second["metrics"][part].get(m)
                entry = {"diff": None if a is None or b is None else a - b, "noise": None, "clears_noise": False}
                if first.get("draws") and second.get("draws"):
                    deltas = [x[part][m] - y[part][m] for x, y in zip(first["draws"], second["draws"])
                              if x[part][m] is not None and y[part][m] is not None]
                    entry["noise"] = noise_range(deltas)
                    if entry["noise"] and entry["diff"] is not None:
                        better_up = m != "mae"
                        entry["clears_noise"] = entry["noise"][0] > 0 if better_up else entry["noise"][1] < 0
                out[part][m] = entry
        return out

    # --------------------------------------------------------- cross-validation

    def folds(self) -> List[List[str]]:
        k = self.settings.get("cv", 0)
        train = sorted(self.train)
        if k == 0 or len(train) < 4:
            return []
        if k < 0 or k >= len(train):
            return [[d] for d in train]
        random.Random(f"tune-cv-{self.settings['seed']}").shuffle(train)
        return [train[i::k] for i in range(k)]

    def cross_validate(self, evals: Mapping[str, dict], baseline: str) -> Optional[dict]:
        """Each training deck's simulated win rate taken from the candidate chosen without it."""
        folds = self.folds()
        if not folds:
            return None
        chosen: Dict[str, str] = {}
        oof: Dict[str, Optional[float]] = {}
        saved_train = self.train
        try:
            for fold in folds:
                self.train = [d for d in saved_train if d not in fold]
                self._fold = set(fold)
                scored = []
                for cid, ev in evals.items():
                    results = self.results(cid, range(*ev["games"]))
                    value = self._metric_set([(r.a, r.b, r.wins, r.decided) for r in results], None)["objective"]
                    scored.append((-(value if value is not None else -9.0), cid))
                best = min(scored)[1]
                for d in fold:
                    chosen[d] = best
                    oof[d] = evals[best]["deck_rates"].get(d)
        finally:
            self.train = saved_train
            self._fold = set()
        return {"folds": len(folds), "games_per_pairing": evals[baseline]["games"][1] - evals[baseline]["games"][0],
                "chosen": chosen, "out_of_fold": compare(oof, self.real, self.train),
                "baseline": evals[baseline]["metrics"]["train"],
                "in_sample_best": max((ev["metrics"]["train"] for ev in evals.values()),
                                      key=lambda m: m["spearman"] if m["spearman"] is not None else -9.0)}

    # --------------------------------------------------------------- import

    def import_run(self, run_dir: Path) -> Counter:
        """Add the games of an earlier mtgsim run (match, matrix, gauntlet, ...) to the cache.

        Only games that are exactly the ones this run would play are taken: same Forge build, seed,
        decks and deck names, time limit, Monte Carlo setting, seat order and AI settings.
        """
        run_dir = Path(run_dir)
        counts: Counter = Counter()
        try:
            info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RunError(f"cannot import {run_dir}: {exc}")
        opts = info.get("options", {})
        problems = []
        if opts.get("seed") != self.settings["seed"]:
            problems.append(f"seed {opts.get('seed')} (this run: {self.settings['seed']})")
        if opts.get("timeout") != self.settings["timeout"]:
            problems.append(f"time limit {opts.get('timeout')}s")
        if (opts.get("monte_carlo") or "off") != self.settings["mc"]:
            problems.append(f"Monte Carlo {opts.get('monte_carlo')}")
        forge_info = info.get("forge", {})
        ours = self.patches.get("combined_sha256") or ""
        recorded_patches = forge_info.get("patches")
        if isinstance(recorded_patches, dict):
            if (recorded_patches.get("combined_sha256") or "") != ours:
                problems.append(f"Forge patch set {(recorded_patches.get('combined_sha256') or 'none')[:12]} "
                                f"(this Forge: {(ours or 'none')[:12]})")
        elif ours:
            # A run from before patches were recorded was played on an unpatched Forge. A card-script
            # patch leaves the jar and its timestamp alone, so the checks below would not notice.
            problems.append(f"an unpatched Forge (this Forge has patch set {ours[:12]})")
        if forge_info.get("fingerprint"):
            if forge_info["fingerprint"] != self.build_fingerprint:
                problems.append("a different Forge build")
        elif forge_info.get("path") != str(self.install.root) or forge_info.get("version") != self.install.version:
            problems.append("a different Forge installation")
        else:
            created = info.get("created")
            try:
                stamp = time.mktime(time.strptime(created, "%Y-%m-%d %H:%M:%S"))
                if self.install.jar.stat().st_mtime > stamp:
                    problems.append("a Forge build that has since been rebuilt")
            except (TypeError, ValueError, OSError):
                problems.append("no record of which Forge build played it")
        if problems:
            raise RunError(f"cannot import {run_dir}: it used " + "; ".join(problems))

        forced = opts.get("ai_profile") not in (None, "", "Default")
        entrants = {e["key"]: e for e in info.get("entrants", [])}
        recorded = info.get("ai_profiles") or {}
        defaults, _ = ai_profiles.known_settings(self.install)

        def seat_hash(entry: dict) -> Optional[str]:
            if entry.get("ai_mc"):
                return None  # per-deck Monte Carlo: not comparable
            if entry.get("ai_profile") and opts.get("ai_profile") == "Default":
                return None  # cannot tell whether --ai-profile Default overrode it
            name = opts["ai_profile"] if forced else (entry.get("ai_profile") or "Default")
            if name in recorded:
                return recorded[name]
            path = ai_profiles.builtin_dir(self.install) / (name + ai_profiles.EXT)
            if not path.is_file():
                return None
            return ai_profiles.settings_hash(path.read_text(encoding="utf-8", errors="replace"), defaults)

        ours = {(d.entrant.deck.fingerprint(), d.name): d for d in self.decks}
        for record in experiment.read_games(run_dir):
            ea, eb = entrants.get(record.get("a")), entrants.get(record.get("b"))
            if record.get("status") not in ("ok", "timeout") or ea is None or eb is None:
                counts["skipped: not a finished game"] += 1
                continue
            da, db = ours.get((ea.get("fingerprint"), ea.get("name"))), ours.get((eb.get("fingerprint"), eb.get("name")))
            if da is None or db is None:
                counts["skipped: deck not in this run"] += 1
                continue
            if self.index[da.key] > self.index[db.key]:
                counts["skipped: pairing played the other way round"] += 1
                continue
            g = int(record["game"])
            ha, hb = seat_hash(ea), seat_hash(eb)
            seats = record.get("seats") or []
            if ha is None or hb is None:
                counts["skipped: AI settings not comparable"] += 1
                continue
            if record.get("seed") != experiment.game_seed(self.settings["seed"], da.entrant.deck, db.entrant.deck, g) \
                    or seats != ([record["a"], record["b"]] if g % 2 == 0 else [record["b"], record["a"]]):
                counts["skipped: seed or seats differ"] += 1
                continue
            pk = pairing_key(self.engine_id, self.settings["seed"], da.entrant, db.entrant, ha, hb,
                             self.settings["mc"], self.settings["timeout"])
            if (pk, g) in self.cache:
                counts["already cached"] += 1
                continue
            a_seat = seats.index(record["a"])
            side = {a_seat: "a", 1 - a_seat: "b"}
            players = record.get("players") or []
            mull = [(players[s].get("mulligans") if s < len(players) else None) for s in (a_seat, 1 - a_seat)]
            self.cache.add({"pk": pk, "g": g, "status": record["status"], "winner": side.get(record.get("winner_seat", -1)),
                            "first": side.get(record.get("first_seat", -1)), "turns": record.get("turns"),
                            "ms": record.get("ms"), "mull": mull, "seed": record.get("seed"),
                            "src": f"import:{run_dir.name}"})
            counts["imported"] += 1
        return counts

    # -------------------------------------------------------------- planning

    def plan(self) -> dict:
        """Games the run will need: exact for the first round, an upper estimate for the rest."""
        rounds = self.settings["rounds"]
        alive = [c["id"] for c in self.candidates]
        baseline = self.candidates[0]["id"]
        planned: Set[Tuple[str, int]] = set(self.cache.games)
        steps = []
        start = 0
        for r, games in enumerate(rounds):
            if r > 0:  # worst case: the baseline survives on top of the best 1/eta
                alive = self._costliest(alive, min(len(alive), int(math.ceil(len(alive) / self.settings["eta"])) + 1))
            todo, used = self._count(alive, range(games), planned)
            steps.append({"round": r + 1, "candidates": len(alive), "games_per_pairing": games,
                          "new_games": todo, "results_used": used, "exact": r == 0})
            start = games
        confirm = self.settings.get("confirm_games", 0)
        if confirm:
            pick = self._costliest(alive, 2)
            todo, used = self._count(pick, range(start, start + confirm), planned)
            steps.append({"round": "confirm", "candidates": len(set(pick)), "games_per_pairing": confirm,
                          "new_games": todo, "results_used": used, "exact": False})
        total = sum(s["new_games"] for s in steps)
        minutes = total / GAMES_PER_MINUTE + ROUND_OVERHEAD_MINUTES * len(steps)
        return {"steps": steps, "games": total, "minutes": minutes}

    def _count(self, cids: Sequence[str], games: range, planned: Set[Tuple[str, int]]) -> Tuple[int, int]:
        new = used = 0
        for cid in dict.fromkeys(cids):
            cand = self.cand(cid)
            for a, b in self.pairs:
                pk = self.pk(cand, a, b)
                for g in games:
                    used += 1
                    if (pk, g) not in planned:
                        planned.add((pk, g))
                        new += 1
        return new, used

    def _costliest(self, pool: Sequence[str], count: int) -> List[str]:
        """The baseline and ``count - 1`` others from ``pool``, chosen to share as few pairings as possible."""
        baseline = self.candidates[0]["id"]
        chosen = [baseline]
        keys = {self.pk(self.cand(baseline), a, b) for a, b in self.pairs}
        while len(chosen) < count:
            options = [c for c in pool if c not in chosen]
            if not options:
                break
            best = max(options, key=lambda c: (len({self.pk(self.cand(c), a, b) for a, b in self.pairs} - keys), c))
            chosen.append(best)
            keys |= {self.pk(self.cand(best), a, b) for a, b in self.pairs}
        return chosen

    # ----------------------------------------------------------------- run

    def run(self, imports: Sequence[Path] = ()) -> dict:
        self.prepare()
        state = self._load_state()
        for path in imports:
            counts = self.import_run(path)
            state.setdefault("imports", []).append({"run": str(path), "counts": dict(counts)})
            self.say(f"Imported from {path}: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
        baseline = self.candidates[0]["id"]
        alive = [c["id"] for c in self.candidates]
        rounds_out = []
        evals_round0: Dict[str, dict] = {}
        last: Dict[str, dict] = {}
        start = 0
        for r, games in enumerate(self.settings["rounds"]):
            span = range(0, games)
            todo, used = self.needed(alive, span)
            self.say(f"\nRound {r + 1}: {len(alive)} candidate(s), {games} games per pairing: "
                     f"{len(todo)} new games, {used - len(todo)} of {used} game results reused "
                     f"(about {len(todo) / GAMES_PER_MINUTE:.0f} min)")
            counts = self.play(todo)
            self._note_failures(counts)
            evals = {cid: self.evaluate(cid, span) for cid in alive}
            ranked = sorted(alive, key=lambda c: (-(evals[c]["objective"] if evals[c]["objective"] is not None else -9.0), c))
            keep = successive_halving_keep(ranked, self.settings["eta"], baseline) \
                if r + 1 < len(self.settings["rounds"]) else ranked
            rounds_out.append({"round": r + 1, "games_per_pairing": games, "candidates": alive, "ranking": ranked,
                               "kept": keep if r + 1 < len(self.settings["rounds"]) else None,
                               "new_games": len(todo), "results_used": used, "engine": dict(counts),
                               "results": {cid: _public(ev) for cid, ev in evals.items()}})
            if r == 0:
                evals_round0 = evals
            last = evals
            state["rounds"] = rounds_out
            self._save(state, "running")
            self._print_round(rounds_out[-1], evals)
            alive = keep
            start = games

        ranked = rounds_out[-1]["ranking"]
        best = next((c for c in ranked if c != baseline), baseline)
        state["best"] = best
        state["baseline_won_selection"] = ranked[0] == baseline
        state["selection"] = {"best": _public(last[best]), "baseline": _public(last[baseline]),
                              "difference": self.paired_difference(last[best], last[baseline])}

        confirm = self.settings.get("confirm_games", 0)
        confirmed = None
        if confirm and best != baseline:
            span = range(start, start + confirm)
            todo, used = self.needed([best, baseline], span)
            self.say(f"\nConfirmation: {self.label(best)} and the baseline on {confirm} fresh games per pairing "
                     f"(games {span.start}-{span.stop - 1}, not used for selection): {len(todo)} new games")
            counts = self.play(todo)
            self._note_failures(counts)
            ev_best, ev_base = self.evaluate(best, span), self.evaluate(baseline, span)
            confirmed = {"games": [span.start, span.stop], "engine": dict(counts), "best": _public(ev_best),
                         "baseline": _public(ev_base), "difference": self.paired_difference(ev_best, ev_base)}
            state["confirm"] = confirmed
        cv = self.cross_validate(evals_round0, baseline) if evals_round0 else None
        state["cv"] = cv
        final = confirmed["best"] if confirmed else _public(last[best])
        r_train = final["metrics"]["train"]["spearman"]
        state["data_needed"] = data_needed(len(self.train), r_train, len(self.decks), len(self.matchups))
        self._write_best(best)
        self._save(state, "done")
        self._print_summary(state)
        return state

    def _note_failures(self, counts: Counter) -> None:
        failed = sum(n for status, n in counts.items() if status not in ("ok", "timeout"))
        if failed:
            self.say(f"Note: {failed} game(s) failed in the engine and are left out (see {self.run_dir / 'logs'}); "
                     f"--resume {self.run_dir} replays them.")

    # ---------------------------------------------------------- persistence

    def describe(self) -> dict:
        return {
            "version": TUNE_VERSION, "settings": self.settings, "engine": self.engine_id,
            "forge": {"version": self.install.version, "path": str(self.install.root),
                      "fingerprint": self.build_fingerprint, "patches": self.patches},
            "decks": [{"key": d.key, "name": d.name,
                       "file": str(Path(d.entrant.deck.path).resolve()) if d.entrant.deck.path else None,
                       "fingerprint": d.entrant.deck.fingerprint(), "category": d.entrant.category, "group": d.group,
                       "real_win_rate": d.real, "holdout": d.holdout} for d in self.decks],
            "matchups": [m.__dict__ for m in self.matchups],
            "space": self.space.to_json(), "profiles": self.profiles, "candidates": self.candidates,
        }

    def _load_state(self) -> dict:
        state = self.describe()
        path = self.run_dir / "tune.json"
        if path.is_file():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                state["imports"] = old.get("imports", [])
                state["created"] = old.get("created")
            except ValueError:
                pass
        state.setdefault("created", time.strftime("%Y-%m-%d %H:%M:%S"))
        return state

    def _save(self, state: dict, status: str) -> None:
        state["status"] = status
        state["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["cache_games"] = len(self.cache)
        path = self.run_dir / "tune.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(path)

    def _write_best(self, cid: str) -> None:
        folder = self.run_dir / "best"
        folder.mkdir(parents=True, exist_ok=True)
        for group, name in self.cand(cid)["profiles"].items():
            info = self.profiles[name]
            out = {"base": info["base"], "overrides": info["overrides"],
                   "note": f"mtgsim tune {self.run_dir.name}, candidate {cid}, group {group}. "
                           "Copy into MTGSIM_HOME/profiles/ and name it in gauntlet.json's ai_profile."}
            (folder / f"tuned-{group}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")

    # --------------------------------------------------------------- output

    def label(self, cid: str) -> str:
        cand = self.cand(cid)
        if cand.get("baseline"):
            return f"{cid} (baseline)"
        parts = [self.profiles[name]["label"] for name in cand["profiles"].values() if self.profiles[name]["overrides"]]
        return f"{cid} ({' x '.join(parts)})"

    def _print_round(self, rnd: dict, evals: Mapping[str, dict]) -> None:
        from .cli import _table

        rows = []
        for cid in rnd["ranking"]:
            ev = evals[cid]
            m = ev["metrics"]
            noise = (ev.get("noise") or {}).get("train", {}).get("spearman")
            rows.append([
                self.label(cid) + (" *" if rnd["kept"] and cid in rnd["kept"] else ""),
                _fmt(m["train"]["spearman"]) + (f" ({_fmt(noise[0])} to {_fmt(noise[1])})" if noise else ""),
                _fmt(m["holdout"]["spearman"]), _pts(m["train"]["mae"]),
                _fmt(m["matchup_train"]["spearman"]) if "matchup_train" in m else "-",
                f"{ev['decided']}/{ev['wanted']}",
            ])
        print(_table(["Candidate", f"Train rank corr. (noise, {len(self.train)} decks)", "Held out",
                      "Train gap", "Matchups", "Decided games"], rows, right=(2, 3, 4, 5)))
        if rnd["kept"]:
            print("* goes on to the next round")

    def _print_summary(self, state: dict) -> None:
        best, base = state["best"], self.candidates[0]["id"]
        print(f"\nBest candidate: {self.label(best)}")
        for group, name in self.cand(best)["profiles"].items():
            overrides = self.profiles[name]["overrides"]
            print(f"  {group}: " + (", ".join(f"{k}={v}" for k, v in overrides.items()) if overrides else "base profile"))
        if state.get("baseline_won_selection"):
            print("  (the baseline ranked first in the final round: no candidate beat it on the training decks)")
        block = state.get("confirm") or state["selection"]
        where = (f"fresh games {block['games'][0]}-{block['games'][1] - 1}" if state.get("confirm")
                 else "the selection games (inflated by the choice; use --confirm for an honest number)")
        print(f"\nBest vs baseline on {where}:")
        for part, label in (("train", "training decks"), ("holdout", "held-out decks"),
                            ("matchup_train", "training matchups")):
            if part not in block["difference"]:
                continue
            d = block["difference"][part]["spearman"]
            b = block["baseline"]["metrics"][part]
            if d["diff"] is None:
                continue
            verdict = "clears game noise" if d["clears_noise"] else "within game noise"
            noise = f", noise {_fmt(d['noise'][0])} to {_fmt(d['noise'][1])}" if d["noise"] else ""
            print(f"  {label} ({b['n']}): rank corr. {_fmt(block['best']['metrics'][part]['spearman'])} vs "
                  f"{_fmt(b['spearman'])}: {d['diff']:+.2f}{noise} -> {verdict}; "
                  f"gap {_pts(block['best']['metrics'][part]['mae'])} vs {_pts(b['mae'])}")
        cv = state.get("cv")
        if cv:
            print(f"\nCross-validation ({'leave one deck out' if cv['folds'] == len(self.train) else str(cv['folds']) + ' folds'}, "
                  f"round 1 games): out-of-fold rank corr. {_fmt(cv['out_of_fold']['spearman'])} vs baseline "
                  f"{_fmt(cv['baseline']['spearman'])} (the best in-sample was {_fmt(cv['in_sample_best']['spearman'])}; "
                  "a large drop from in-sample to out-of-fold means the search fits noise)")
        print("\nHow far the real-world data can take this:")
        for line in state["data_needed"]["text"]:
            print("  " + line)
        print(f"\nResults: {self.run_dir / 'tune.json'}  (winning profiles: {self.run_dir / 'best'})")


def _public(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if k != "draws"}


def _fmt(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:+.2f}"


def _pts(value: Optional[float]) -> str:
    return "-" if value is None else f"{value * 100:.1f} pts"


# =================================================================== the command


def settings_from_args(args) -> dict:
    if args.eta < 2:
        raise RunError("--eta must be at least 2")
    if args.profiles < 1:
        raise RunError("--profiles must be at least 1")
    if args.confirm < 0 or args.bootstrap < 0:
        raise RunError("--confirm and --bootstrap cannot be negative")
    return {
        "seed": args.seed, "search_seed": args.search_seed if args.search_seed is not None else args.seed,
        "rounds": parse_rounds(args.rounds), "eta": args.eta, "profiles_per_group": args.profiles,
        "groups": {g: list(c) for g, c in parse_groups(args.group).items()},
        "tune_groups": [g.lower() for g in args.tune] if args.tune else None,
        "holdout": list(args.holdout or []), "confirm_games": args.confirm, "cv": parse_cv(args.cv),
        "objective": args.objective, "bootstrap": args.bootstrap, "timeout": args.timeout, "mc": args.mc or "off",
        "space": str(Path(args.space).expanduser().resolve()) if args.space else str(DEFAULT_SPACE),
        "matchups": str(Path(args.matchups).expanduser().resolve()) if args.matchups else None,
    }


def stored_run(run_dir: str) -> dict:
    path = Path(run_dir).expanduser() / "tune.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunError(f"{run_dir} is not a tuning run directory (no readable tune.json): {exc}")


def command(install: ForgeInstall, run_dir: Path, entrants: List[Entrant], real_rates: Mapping[str, Optional[float]],
            args, stored: Optional[dict] = None, say: Callable[[str], None] = print) -> int:
    """``python -m mtgsim tune``: set up (or resume) a tuning run, then run it or print its plan."""
    known, exact = ai_profiles.known_keys(install)
    if stored:
        settings = stored["settings"]
        if [d["fingerprint"] for d in stored["decks"]] != [e.deck.fingerprint() for e in entrants]:
            raise RunError("the decklists changed since this tuning run started; start a new run")
        space = parse_space(stored["space"], known if exact else None)
        holdout = [d["key"] for d in stored["decks"] if d["holdout"]]
    else:
        settings = settings_from_args(args)
        space = load_space(Path(settings["space"]), known if exact else None)
        holdout = settings["holdout"]
    groups = {g: tuple(c) for g, c in settings["groups"].items()}
    decks = make_decks(entrants, real_rates, groups, holdout)
    present = sorted({d.group for d in decks}, key=list(groups).index)
    tuned = settings["tune_groups"] or present
    unknown = [g for g in tuned if g not in groups]
    if unknown:
        raise RunError(f"--tune names unknown group(s) {', '.join(unknown)}; groups: {', '.join(groups)}")
    tuned = [g for g in present if g in tuned]
    if not tuned:
        raise RunError("no deck belongs to a group that is being tuned")
    if sum(1 for d in decks if not d.holdout and d.real is not None) < 3:
        raise RunError("tuning needs at least three training decks with real_win_rate in gauntlet.json")
    ignored = [e.deck.name for e in entrants if e.ai_profile or e.ai_mc]
    if ignored:
        say("Note: per-deck ai_profile / ai_mc from gauntlet.json are ignored while tuning: " + ", ".join(ignored))
    matchups: List[Matchup] = []
    if settings.get("matchups"):
        matchups, notes = load_matchups(Path(settings["matchups"]), decks)
        for note in notes:
            say("Note: " + note)
    if settings["objective"] != "deck" and not matchups:
        raise RunError(f"--objective {settings['objective']} needs --matchups with entries for these decks")

    if stored:
        profiles, candidates = stored["profiles"], stored["candidates"]
    else:
        base_text = ai_profiles.text_of(install, space.base)
        defaults, _ = ai_profiles.known_settings(install)
        base_settings = ai_profiles.effective(base_text, defaults)
        rng = random.Random(f"tune-search-{settings['search_seed']}")
        profiles, candidates = make_candidates(space, tuned, present, settings["profiles_per_group"], base_settings, rng)
        settings["tune_groups"] = tuned
        settings["holdout"] = sorted(d.key for d in decks if d.holdout)

    dry_run = getattr(args, "dry_run", False)
    scratch = None
    if dry_run and not stored:
        import tempfile

        scratch = tempfile.TemporaryDirectory(prefix="mtgsim-tune-plan-")  # a plan writes nothing to keep
        run_dir = Path(scratch.name)
    status = forge.patch_status(install)
    if status.warning():
        say(status.warning())
    tuner = Tuner(install, run_dir, decks, space, settings, profiles, candidates, matchups, say=say,
                  workers=getattr(args, "workers", None), heap=getattr(args, "heap", "2g"), patches=status.record())
    if stored and stored.get("engine") and stored["engine"] != tuner.engine_id:
        say("warning: Forge or its patch set changed since this tuning run started; games cached on the earlier "
            "engine do not count for this one and will be replayed.")
    try:
        return _start(tuner, decks, tuned, present, candidates, profiles, args, dry_run, say)
    finally:
        if scratch is not None:
            scratch.cleanup()


def _start(tuner: Tuner, decks: List[TuneDeck], tuned: Sequence[str], present: Sequence[str], candidates: List[dict],
           profiles: Dict[str, dict], args, dry_run: bool, say: Callable[[str], None]) -> int:
    n_train = sum(1 for d in decks if not d.holdout and d.real is not None)
    say(f"Tuning AI profiles: {len(decks)} decks ({n_train} training, "
        f"{sum(1 for d in decks if d.holdout)} held out), {len(tuner.pairs)} pairings, "
        f"{len(candidates)} candidates; groups: "
        + "; ".join(f"{g} ({sum(1 for d in decks if d.group == g)} decks{', tuned' if g in tuned else ''})" for g in present))
    for name, info in profiles.items():
        if info["overrides"]:
            say(f"  {info['label']}: " + ", ".join(f"{k}={v}" for k, v in info["overrides"].items()))
    if dry_run:
        tuner.prepare()
        for path in getattr(args, "import_runs", None) or []:
            counts = tuner.import_run(Path(path))
            say(f"Imported from {path}: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
        plan = tuner.plan()
        say("\nPlan (later rounds assume the survivors share as few pairings as possible):")
        for step in plan["steps"]:
            say(f"  round {step['round']}: {step['candidates']} candidate(s) x {step['games_per_pairing']} games "
                f"per pairing: {step['new_games']} new games ({step['results_used']} results used)"
                + ("" if step["exact"] else ", estimate"))
        say(f"  total about {plan['games']} games, {plan['minutes']:.0f} minutes at {GAMES_PER_MINUTE:.0f} games/min "
            f"(4 cores)")
        return 0
    tuner.run([Path(p) for p in (getattr(args, "import_runs", None) or [])])
    return 0
