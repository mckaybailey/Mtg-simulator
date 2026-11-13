"""Difference in calibration metrics between two matrix runs, with a bootstrap interval.

usage: python3 tools/calibration_diff.py RUN_A RUN_B [--reps 2000]
Each run's pairing results are resampled independently (binomial, observed rates), the deck averages,
Spearman, Pearson and mean absolute gap are recomputed for both, and B minus A is summarised.
"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibration import spearman, pearson  # noqa: E402

def load(run, gauntlet="decks/standard/meta/gauntlet.json"):
    s = json.loads((Path(run) / "summary.json").read_text())
    real = {d["name"]: d["real_win_rate"] for d in json.loads(Path(gauntlet).read_text())["decks"]}
    names = {k: e["name"] for k, e in s["entrants"].items()}
    cells = {(p["a"], p["b"]): (p["wins"], p["decided"]) for p in s["pairings"]}
    keys = sorted(k for k in names if names[k] in real)
    return keys, names, cells, [real[names[k]] for k in keys]

def rates(keys, cells):
    out = []
    for k in keys:
        r = [w / d if a == k else 1 - w / d for (a, b), (w, d) in cells.items() if d and k in (a, b)]
        out.append(100 * sum(r) / len(r))
    return out

def metrics(keys, cells, real):
    s = rates(keys, cells)
    return spearman(s, real), pearson(s, real), sum(abs(x - y) for x, y in zip(s, real)) / len(s)

def resample(cells, rng):
    return {k: (sum(1 for _ in range(d) if rng.random() < w / d), d) for k, (w, d) in cells.items()}

reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 2000
a, b = sys.argv[1], sys.argv[2]
ka, _, ca, ra = load(a); kb, _, cb, rb = load(b)
assert ka == kb
ma, mb = metrics(ka, ca, ra), metrics(kb, cb, rb)
rng = random.Random(7)
diffs = []
for _ in range(reps):
    x, y = metrics(ka, resample(ca, rng), ra), metrics(kb, resample(cb, rng), rb)
    diffs.append([y[i] - x[i] for i in range(3)])
for i, name in enumerate(("Spearman", "Pearson", "mean abs gap")):
    ds = sorted(d[i] for d in diffs)
    lo, hi = ds[int(0.025 * reps)], ds[int(0.975 * reps) - 1]
    print(f"{name:13s} A {ma[i]:.3f}  B {mb[i]:.3f}  B-A {mb[i] - ma[i]:+.3f}  95% interval {lo:+.3f}..{hi:+.3f}")
