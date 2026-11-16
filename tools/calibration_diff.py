"""Difference in calibration metrics between two matrix runs, with a bootstrap interval.

usage: python3 tools/calibration_diff.py RUN_A RUN_B [--only SLUG,...] [--reps 2000]

A run written as RUN_DIR#game1 is read from its `pairings_game1` (the game 1s of a best-of-three
run), so `RUN#game1 RUN` compares one run's best-of-one games with its match results.
Each side's pairing results are resampled independently (binomial, observed rates), the deck
averages and Spearman, Pearson, mean absolute gap and SD are recomputed for both, with equal and
with meta-share weights on the opponents, and B minus A is summarised. Only the decks both sides
have (or those in --only), and the pairings among them, are used. Resampling both sides
independently overstates the noise when both come from the same games (a game 1 is also part of
its match), so the interval is conservative for `RUN#game1 RUN`.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibration import Calib, METRICS, parse_args  # noqa: E402


def side(arg, only):
    path, _, tag = arg.partition("#")
    if tag not in ("", "game1"):
        raise SystemExit(f"{arg}: the only suffix is #game1")
    return path, tag == "game1"


def main():
    pos, opts = parse_args(sys.argv[1:])
    if len(pos) < 2:
        print(__doc__)
        return 2
    (pa, ga), (pb, gb) = side(pos[0], opts["only"]), side(pos[1], opts["only"])
    a0, b0 = Calib(pa, game1=ga), Calib(pb, game1=gb)
    shared = set(a0.keys) & set(b0.keys)
    if opts["only"] is not None:
        shared &= opts["only"]
    if set(a0.keys) != shared or set(b0.keys) != shared:
        print(f"Comparing the {len(shared)} decks both sides share (pairings among those only).")
    a, b = Calib(pa, game1=ga, only=shared), Calib(pb, game1=gb, only=shared)
    ma, mb = a.metrics(a.cells), b.metrics(b.cells)
    rng = random.Random(7)
    diffs = []
    for _ in range(opts["reps"]):
        x, y = a.metrics(a.resample(rng)), b.metrics(b.resample(rng))
        diffs.append([y[i] - x[i] for i in range(len(x))])
    reps = opts["reps"]
    print(f"A = {pos[0]} ({a.source}), B = {pos[1]} ({b.source}), {len(shared)} decks")
    for j, label in enumerate(("equal-weighted opponents", "share-weighted opponents")):
        print(f"{label}:")
        for i, name in enumerate(METRICS):
            n = 4 * j + i
            ds = sorted(d[n] for d in diffs)
            lo, hi = ds[int(0.025 * reps)], ds[int(0.975 * reps) - 1]
            print(f"  {name:13s} A {ma[n]:6.3f}  B {mb[n]:6.3f}  B-A {mb[n] - ma[n]:+.3f}  "
                  f"95% interval {lo:+.3f}..{hi:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
