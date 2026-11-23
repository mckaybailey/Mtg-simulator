"""How closely a round robin's meta win rates match the real ones, round robin and Swiss.

The real win rates in a ``gauntlet.json`` (``real_win_rate``) are match win rates from Swiss
events: players are paired by record, so a deck that keeps winning meets stronger opposition, and
mirrors and byes are left out. A round robin's average win rate is a different quantity, so it is
compared with the real figures in four ways, each giving the same four metrics:

* ``games``    every opponent counted equally, game win rates (the matrix ranking's number);
* ``weighted`` opponents weighted by ``meta_share``, game win rates;
* ``matches``  each pairing's game rate p turned into a best-of-three match rate p^2 (3 - 2p)
               (a ``--bo3`` run's own match results instead), weighted by share, with the rest of the
               field (100 minus the decks' shares) as "other", beaten at ``other_rate``;
* ``swiss``    the same match rates played out in simulated Swiss events: players get decks drawn
               by ``meta_share``, each round pairs equal records (no rematches where avoidable), and a
               deck's rate is its match wins over matches played, mirrors and byes left out.

The metrics are the spread (population SD of the decks' rates), the mean absolute gap to the real
rates, Spearman's rank correlation and the sign errors (decks on the other side of 50% from their
real rate). ``swiss`` is the like-for-like comparison with real event results; ``swiss`` minus
``matches`` is what the pairing alone does. Noise ranges come from a parametric bootstrap of the
run's games (each pairing's wins redrawn from its observed rate). ``tools/swiss_check.py`` is the
research front end with more event options; both share this code, so they give the same numbers.

Event structures are strings ``N:R[:cR/L][:wW][:lL]`` joined by commas: N players, R rounds;
``cR/L`` after round R only players with at most L losses play on (a day-two cut); ``wW`` / ``lL`` a
player stops at W wins / L losses. A gauntlet gives the structure of the events behind its real
win rates as ``real_events``; :data:`DEFAULT_EVENTS` is used when it does not.
"""
import random
import statistics
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .tune import spearman

OTHER = "other"

# The three events behind decks/standard/meta's real win rates (its gauntlet.json repeats this
# as "real_events"): Arena Championship 13, 176 players, nine rounds of modified Swiss in which a
# player stops at 7 wins or 3 losses; Magic Spotlight: Fracture in Hartford (775 players) and
# Beijing (865), nine rounds, at most 3 losses to day two, fifteen rounds in all.
FRACTURE_2026_EVENTS = "176:9:w7:l3,775:15:c9/3,865:15:c9/3"
# For a gauntlet that does not say: one large open event.
DEFAULT_EVENTS = "600:12"

VIEWS = ("games", "weighted", "matches", "swiss")
VIEW_LABELS = {
    "games": "Round robin, game win rates",
    "weighted": "Round robin, weighted by meta share",
    "matches": "Round robin, best-of-three matches, weighted",
    "swiss": "Simulated Swiss events",
}
METRICS = ("sd", "mean_gap", "spearman", "sign_errors")

Cells = Dict[Tuple[str, str], Tuple[int, int]]  # (a, b) -> (a's wins, decided)


def bo3(p: float) -> float:
    """Best-of-three match win rate of a player who wins each game with probability p."""
    return p * p * (3 - 2 * p)


def parse_event(spec: str) -> dict:
    parts = spec.strip().split(":")
    try:
        e = {"n": int(parts[0]), "rounds": int(parts[1]), "cut": None, "win_cap": None, "loss_cap": None}
        for p in parts[2:]:
            if p[:1] == "c":
                r, l = p[1:].split("/")
                e["cut"] = (int(r), int(l))
            elif p[:1] == "w":
                e["win_cap"] = int(p[1:])
            elif p[:1] == "l":
                e["loss_cap"] = int(p[1:])
            else:
                raise ValueError(p)
    except (ValueError, IndexError):
        raise ValueError(f"bad event structure {spec!r}: expected N:R[:cR/L][:wW][:lL]")
    if e["n"] < 2 or e["rounds"] < 1:
        raise ValueError(f"bad event structure {spec!r}: needs at least 2 players and 1 round")
    return e


def parse_events(spec: str) -> List[dict]:
    return [parse_event(s) for s in spec.split(",") if s.strip()]


class Field:
    """Archetypes (``keys``, plus "other" unless ``include_other`` is false), shares and win rates.

    ``game_cells`` hold game results; ``match_cells`` match results (a best-of-three run's), or
    None to convert the game rates with :func:`bo3`, or ``game_cells`` itself to use game rates
    as match rates.
    """

    def __init__(self, keys: Sequence[str], shares: Mapping[str, float], game_cells: Cells,
                 match_cells: Optional[Cells] = None, other_rate: float = 0.5, include_other: bool = True):
        self.keys = list(keys)
        share = [float(shares[k]) for k in self.keys]
        if include_other:
            self.keys.append(OTHER)
            share.append(max(0.0, 100.0 - sum(share)))
        total = sum(share)
        self.share = [s / total for s in share]
        n = len(self.keys)
        idx = {k: i for i, k in enumerate(self.keys)}
        self.m = [[0.5] * n for _ in range(n)]
        self.game = [[0.5] * n for _ in range(n)]
        for (a, b), (w, d) in game_cells.items():
            if d:
                p = w / d
                self.game[idx[a]][idx[b]], self.game[idx[b]][idx[a]] = p, 1 - p
                if match_cells is None:
                    self.m[idx[a]][idx[b]], self.m[idx[b]][idx[a]] = bo3(p), bo3(1 - p)
        for (a, b), (w, d) in (match_cells or {}).items():
            if d:
                p = w / d
                self.m[idx[a]][idx[b]], self.m[idx[b]][idx[a]] = p, 1 - p
        if OTHER in idx:
            j = idx[OTHER]
            for i in range(n):
                if i != j:
                    self.m[i][j], self.m[j][i] = other_rate, 1 - other_rate
        self.cum = []
        acc = 0.0
        for s in self.share:
            acc += s
            self.cum.append(acc)

    def draw(self, rng: random.Random) -> int:
        x = rng.random()
        for i, c in enumerate(self.cum):
            if x < c:
                return i
        return len(self.cum) - 1

    def rr(self, matrix: List[List[float]], k: int, among: Optional[int] = None) -> float:
        """Share-weighted rate of deck k against the first ``among`` archetypes (all), mirror left out."""
        num = den = 0.0
        for j, s in enumerate(self.share[:among]):
            if j != k:
                num += s * matrix[k][j]
                den += s
        return num / den


def pair(players: list, rng: random.Random, played: set) -> Tuple[list, Optional[list]]:
    """Swiss pairing: sort by points (random order within a score group), pair down greedily
    avoiding rematches; an odd player out gets a bye. Returns (pairs, bye or None)."""
    unpaired = sorted(players, key=lambda p: (-p[1], rng.random()))
    pairs, bye = [], None
    while unpaired:
        a, rest = unpaired[0], unpaired[1:]
        if not rest:
            bye = a
            break
        pick = 0
        for j, b in enumerate(rest):
            if (a[0], b[0]) not in played:
                pick = j
                break
        pairs.append((a, rest[pick]))
        unpaired = rest[:pick] + rest[pick + 1:]
    return pairs, bye


def play_event(field: Field, e: dict, rng: random.Random, wins: List[int], games: List[int]) -> None:
    players = [[i, 0, 0, field.draw(rng)] for i in range(e["n"])]  # id, points, losses, deck
    played = set()
    for r in range(1, e["rounds"] + 1):
        active = [p for p in players
                  if (e["loss_cap"] is None or p[2] < e["loss_cap"])
                  and (e["win_cap"] is None or p[1] < e["win_cap"])]
        if e["cut"] and r > e["cut"][0]:
            active = [p for p in active if p[2] <= e["cut"][1]]
        if len(active) < 2:
            break
        pairs, bye = pair(active, rng, played)
        if bye is not None:
            bye[1] += 1
        for a, b in pairs:
            played.add((a[0], b[0]))
            played.add((b[0], a[0]))
            da, db = a[3], b[3]
            w, l = (a, b) if rng.random() < field.m[da][db] else (b, a)
            w[1] += 1
            l[2] += 1
            if da != db:
                games[da] += 1
                games[db] += 1
                wins[w[3]] += 1


def swiss(field: Field, events: Sequence[dict], seasons: int, rng: random.Random) -> List[float]:
    """Match win rate of every archetype over ``seasons`` repetitions of ``events``."""
    n = len(field.keys)
    wins, games = [0] * n, [0] * n
    for _ in range(seasons):
        for e in events:
            play_event(field, e, rng, wins, games)
    return [wins[i] / games[i] if games[i] else float("nan") for i in range(n)]


def metrics(sim: Sequence[float], real: Sequence[float]) -> dict:
    gaps = [abs(s - r) for s, r in zip(sim, real)]
    return {"sd": statistics.pstdev(sim), "mean_gap": sum(gaps) / len(gaps), "spearman": spearman(sim, real),
            "sign_errors": sum(1 for s, r in zip(sim, real) if (s - 50) * (r - 50) < 0)}


def resample(cells: Cells, rng: random.Random) -> Cells:
    return {k: (sum(1 for _ in range(d) if rng.random() < w / d), d) for k, (w, d) in cells.items()}


def _equal_rate(cells: Cells, k: str) -> float:
    rates = [(w / d if a == k else 1 - w / d) for (a, b), (w, d) in cells.items() if d and k in (a, b)]
    return 100 * sum(rates) / len(rates)


def evaluate(keys: Sequence[str], shares: Mapping[str, float], game_cells: Cells, match_cells: Optional[Cells],
             events: Sequence[dict], seasons: int, rng: random.Random, other_rate: float = 0.5) -> Dict[str, List[float]]:
    """Every deck's rate (percent, in ``keys`` order) in each of :data:`VIEWS`."""
    f = Field(keys, shares, game_cells, match_cells, other_rate)
    n = len(keys)
    out = {"games": [_equal_rate(game_cells, k) for k in keys],
           "weighted": [100 * f.rr(f.game, i, n) for i in range(n)],
           "matches": [100 * f.rr(f.m, i) for i in range(n)]}
    out["swiss"] = [100 * x for x in swiss(f, events, seasons, rng)[:n]]
    return out


def _quantiles(xs: List[float]) -> List[float]:
    xs = sorted(x for x in xs if x is not None)
    return [xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]] if xs else [None, None]


def _cells(pairings: Sequence[dict], inside: set) -> Cells:
    return {(p["a"], p["b"]): (int(p["wins"]), int(p["decided"])) for p in pairings
            if p.get("a") in inside and p.get("b") in inside and p.get("decided") is not None}


def compare(entrants: Mapping[str, dict], pairings: Sequence[dict], game1: Optional[Sequence[dict]] = None, *,
            events: str = DEFAULT_EVENTS, seasons: int = 200, reps: int = 100, boot_seasons: int = 10,
            seed: int = 1, other_rate: float = 0.5) -> Optional[dict]:
    """The calibration block of a matrix summary, or None with fewer than three usable decks.

    ``entrants`` maps keys to dicts with ``name``, ``real_win_rate`` (percent) and ``weight``
    (``meta_share``); only decks with both numbers take part. ``pairings`` are the run's pairing
    results; for a best-of-three run they are matches and ``game1`` holds its game 1s.
    """
    keys = sorted(k for k, e in entrants.items()
                  if isinstance(e.get("real_win_rate"), (int, float)) and isinstance(e.get("weight"), (int, float))
                  and e["weight"] > 0)
    inside = set(keys)
    if game1 is not None:
        game_cells, match_cells = _cells(game1, inside), _cells(pairings, inside)
    else:
        game_cells, match_cells = _cells(pairings, inside), None
    played = {k for pair_ in game_cells for k in pair_}
    keys = [k for k in keys if k in played]
    if len(keys) < 3:
        return None
    inside = set(keys)
    game_cells = {k: v for k, v in game_cells.items() if set(k) <= inside}
    if match_cells is not None:
        match_cells = {k: v for k, v in match_cells.items() if set(k) <= inside}
    shares = {k: float(entrants[k]["weight"]) for k in keys}
    real = [float(entrants[k]["real_win_rate"]) for k in keys]
    event_list = parse_events(events)

    rng = random.Random(seed)
    rates = evaluate(keys, shares, game_cells, match_cells, event_list, seasons, rng, other_rate)
    point = {v: metrics(rates[v], real) for v in VIEWS}
    noise: Dict[str, Dict[str, List[float]]] = {}
    pairing_effect = {x: point["swiss"][x] - point["matches"][x] for x in ("sd", "mean_gap", "spearman")
                      if point["swiss"][x] is not None and point["matches"][x] is not None}
    pairing_noise: Dict[str, List[float]] = {}
    if reps > 0:
        draws = []
        for _ in range(reps):
            g = resample(game_cells, rng)
            m = resample(match_cells, rng) if match_cells is not None else None
            b = evaluate(keys, shares, g, m, event_list, boot_seasons, rng, other_rate)
            draws.append({v: metrics(b[v], real) for v in VIEWS})
        noise = {v: {x: _quantiles([d[v][x] for d in draws]) for x in ("sd", "mean_gap", "spearman")} for v in VIEWS}
        pairing_noise = {x: _quantiles([d["swiss"][x] - d["matches"][x] for d in draws
                                        if d["swiss"][x] is not None and d["matches"][x] is not None])
                         for x in pairing_effect}
    flat = metrics([50.0] * len(real), real)
    return {
        "events": events, "seasons": seasons, "seed": seed, "other_rate": other_rate,
        "reps": reps, "boot_seasons": boot_seasons,
        "match_rates": "bo3 matches played" if match_cells is not None else "game rates converted to best-of-three",
        "other_share": max(0.0, 100.0 - sum(shares.values())),
        "real_sd": statistics.pstdev(real), "flat": flat,
        "decks": [{"key": k, "name": entrants[k].get("name", k), "real": real[i],
                   **{v: rates[v][i] for v in VIEWS}} for i, k in enumerate(keys)],
        "metrics": point, "noise": noise,
        "pairing_effect": pairing_effect, "pairing_effect_noise": pairing_noise,
    }


def format_text(cal: dict) -> str:
    """The terminal table: one line per deck, then the four metrics for each view."""
    lines = [f"Against real win rates ({len(cal['decks'])} decks; Swiss events {cal['events']}, "
             f"{cal['seasons']} seasons; rest of the field {cal['other_share']:.1f}% at {cal['other_rate']:.0%}):",
             f"{'Deck':26s} {'Real':>6s} {'Games':>6s} {'Wtd':>6s} {'Match':>6s} {'Swiss':>6s} {'Gap':>6s}"]
    for d in sorted(cal["decks"], key=lambda d: -(d["swiss"] - d["real"])):
        lines.append(f"{str(d['name'])[:26]:26s} {d['real']:6.1f} {d['games']:6.1f} {d['weighted']:6.1f} "
                     f"{d['matches']:6.1f} {d['swiss']:6.1f} {d['swiss'] - d['real']:+6.1f}")
    lines.append(f"\nReal SD {cal['real_sd']:.1f}; every deck at 50% would have mean gap {cal['flat']['mean_gap']:.1f}.")
    for v in VIEWS:
        m, nz = cal["metrics"][v], cal["noise"].get(v, {})
        parts = []
        for x, label, fmt in (("sd", "SD", ".1f"), ("mean_gap", "gap", ".1f"), ("spearman", "Spearman", ".2f")):
            val = m[x]
            s = f"{label} {val:{fmt}}" if val is not None else f"{label} -"
            if nz.get(x) and nz[x][0] is not None:
                s += f" ({nz[x][0]:{fmt}}..{nz[x][1]:{fmt}})"
            parts.append(s)
        parts.append(f"sign errors {m['sign_errors']}")
        lines.append(f"  {v:9s} " + "  ".join(parts))
    pe, pn = cal["pairing_effect"], cal["pairing_effect_noise"]
    if "sd" in pe:
        rng_s = f" ({pn['sd'][0]:+.1f} to {pn['sd'][1]:+.1f})" if pn.get("sd") and pn["sd"][0] is not None else ""
        lines.append(f"Swiss minus round-robin matches: SD {pe['sd']:+.1f}{rng_s}, gap {pe['mean_gap']:+.1f}.")
    lines.append("The Swiss line is the one to compare with the real figures (they come from Swiss events); "
                 "noise ranges are 95% from redrawing the run's games.")
    return "\n".join(lines)
