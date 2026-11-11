"""The small amount of statistics the reports need: intervals and tests for win rates.

Win rates from a few hundred games are noisy (the 95% interval at 200 games is about +/-7
points), so every number mtgsim shows comes with an interval or a p-value from here.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

Z95 = 1.959963984540054


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_sided_p(z: float) -> float:
    return max(0.0, min(1.0, 2.0 * (1.0 - normal_cdf(abs(z)))))


def rate(wins: int, games: int) -> Optional[float]:
    return wins / games if games else None


def wilson(wins: int, games: int, z: float = Z95) -> Tuple[Optional[float], Optional[float]]:
    """Wilson score interval for a proportion; well behaved near 0%, 100% and for small samples."""
    if games <= 0:
        return (None, None)
    p = wins / games
    denom = 1.0 + z * z / games
    centre = (p + z * z / (2 * games)) / denom
    half = z * math.sqrt(p * (1 - p) / games + z * z / (4.0 * games * games)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def binomial_p_even(wins: int, games: int) -> Optional[float]:
    """Exact two-sided p-value for "this matchup is 50/50"."""
    if games <= 0:
        return None
    k = min(wins, games - wins)
    if games > 2000:  # the exact sum is slow and the normal approximation is excellent here
        z = (abs(wins - games / 2.0) - 0.5) / math.sqrt(games / 4.0)
        return two_sided_p(max(z, 0.0))
    tail = sum(math.comb(games, i) for i in range(0, k + 1)) / (2.0 ** games)
    return min(1.0, 2.0 * tail)


def diff_test(w1: int, n1: int, w2: int, n2: int) -> dict:
    """Compare two win rates: difference (1 minus 2), its 95% interval and a two-sided p-value.

    The interval is Newcombe's hybrid score interval; the p-value is the pooled two-proportion
    z-test. Returns ``None`` values when either sample is empty.
    """
    if n1 <= 0 or n2 <= 0:
        return {"diff": None, "ci": [None, None], "p": None}
    p1, p2 = w1 / n1, w2 / n2
    l1, u1 = wilson(w1, n1)
    l2, u2 = wilson(w2, n2)
    diff = p1 - p2
    lo = diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    pooled = (w1 + w2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1.0 / n1 + 1.0 / n2))
    p_value = two_sided_p(diff / se) if se > 0 else 1.0
    return {"diff": diff, "ci": [lo, hi], "p": p_value}


def weighted_rate(samples: Sequence[Tuple[int, int]], weights: Optional[Sequence[float]] = None) -> dict:
    """A weighted average of several win rates with a normal-approximation 95% interval.

    ``samples`` is a list of (wins, games); matchups without games are left out and the remaining
    weights are renormalised. With no weights every matchup counts equally, which answers "how does
    this deck do against the field" without letting the most-played matchup dominate.
    """
    rows = []
    for i, (wins, games) in enumerate(samples):
        if games > 0:
            w = 1.0 if weights is None else float(weights[i] or 0.0)
            if w > 0:
                rows.append((wins, games, w))
    total = sum(w for _, _, w in rows)
    if not rows or total <= 0:
        return {"rate": None, "ci": [None, None], "se": None}
    mean = sum(w * wins / games for wins, games, w in rows) / total
    var = 0.0
    for wins, games, w in rows:
        # Agresti-Coull style variance keeps a 0% or 100% matchup from claiming zero uncertainty.
        p = (wins + 2.0) / (games + 4.0)
        var += (w / total) ** 2 * p * (1 - p) / games
    se = math.sqrt(var)
    return {"rate": mean, "ci": [max(0.0, mean - Z95 * se), min(1.0, mean + Z95 * se)], "se": se}


def weighted_diff(
    first: Sequence[Tuple[int, int]],
    second: Sequence[Tuple[int, int]],
    weights: Optional[Sequence[float]] = None,
) -> dict:
    """Difference between two decks' weighted win rates over the same opponents, with a z-test."""
    keep = [i for i in range(len(first)) if first[i][1] > 0 and second[i][1] > 0]
    if not keep:
        return {"diff": None, "ci": [None, None], "p": None}
    w = None if weights is None else [weights[i] for i in keep]
    a = weighted_rate([first[i] for i in keep], w)
    b = weighted_rate([second[i] for i in keep], w)
    if a["rate"] is None or b["rate"] is None:
        return {"diff": None, "ci": [None, None], "p": None}
    diff = a["rate"] - b["rate"]
    se = math.sqrt(a["se"] ** 2 + b["se"] ** 2)
    p_value = two_sided_p(diff / se) if se > 0 else 1.0
    return {"diff": diff, "ci": [diff - Z95 * se, diff + Z95 * se], "p": p_value}


def games_to_detect(delta: float, base: float = 0.5, power: float = 0.8) -> Optional[int]:
    """Games needed per deck to detect a win-rate difference of ``delta`` at 5% significance."""
    if delta <= 0:
        return None
    z_beta = {0.8: 0.8416212335729143, 0.9: 1.2815515655446004}.get(power, 0.8416212335729143)
    p1 = min(max(base + delta / 2.0, 0.01), 0.99)
    p2 = min(max(base - delta / 2.0, 0.01), 0.99)
    n = (Z95 + z_beta) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (delta * delta)
    return int(math.ceil(n))


def mean(values: Iterable[float]) -> Optional[float]:
    items: List[float] = list(values)
    return sum(items) / len(items) if items else None
