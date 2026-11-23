"""Calibration metrics for a matrix run: sim vs real win rate per deck, with a game-noise range.

usage: python3 tools/calibration.py RUN_DIR [gauntlet.json] [--game1] [--only SLUG,SLUG,...] [--reps 2000]

--game1  read `pairings_game1` (the game 1s of a best-of-three run, i.e. its best-of-one round
         robin) instead of `pairings` (match results in a best-of-three run).
--only   restrict to these decks (entrant keys, the deck file names without .txt) and the
         pairings among them, e.g. the original twelve meta decks.

Each deck's simulated rate is printed two ways: the plain average over its opponents ("sim") and
the average weighted by the opponents' `meta_share` ("wtd"; the real rates are against the field,
so this is the closer comparison). Spread is the population SD of the decks' rates.
Noise range: parametric bootstrap. Each pairing's wins are redrawn from Binomial(decided, observed
rate), deck averages and the metrics are recomputed; the 2.5-97.5 percentiles are reported.
"""
import json
import random
import statistics as st
import sys
from pathlib import Path


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else float("nan")


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


class Calib:
    """One run's pairing cells and the real figures of its decks that have a real win rate."""

    def __init__(self, run, gauntlet="decks/standard/meta/gauntlet.json", game1=False, only=None):
        run = Path(run)
        summary = json.loads((run if run.is_file() else run / "summary.json").read_text())
        field = "pairings_game1" if game1 else "pairings"
        if field not in summary:
            raise SystemExit(f"{run}: summary.json has no {field!r} (--game1 needs a best-of-three matrix run)")
        decks = json.loads(Path(gauntlet).read_text())["decks"]
        by_name = {d["name"]: d for d in decks}
        self.names = {k: e["name"] for k, e in summary["entrants"].items()}
        self.keys = sorted(k for k in self.names
                           if by_name.get(self.names[k], {}).get("real_win_rate") is not None
                           and (only is None or k in only))
        if only is not None and set(only) - set(self.keys):
            raise SystemExit(f"--only: not in the run (or no real win rate): {sorted(set(only) - set(self.keys))}")
        self.real = [by_name[self.names[k]]["real_win_rate"] for k in self.keys]
        self.share = {k: by_name[self.names[k]].get("meta_share") or 0.0 for k in self.keys}
        inside = set(self.keys)
        self.cells = {(p["a"], p["b"]): (p["wins"], p["decided"]) for p in summary[field]
                      if p["a"] in inside and p["b"] in inside}
        self.problems = summary.get("problems")
        self.source = field

    def rates(self, cells, weighted=False):
        out = []
        for k in self.keys:
            num = den = 0.0
            for (a, b), (w, d) in cells.items():
                if not d or k not in (a, b):
                    continue
                opp, r = (b, w / d) if a == k else (a, 1 - w / d)
                wt = self.share[opp] if weighted else 1.0
                num += wt * r
                den += wt
            out.append(100 * num / den)
        return out

    def metrics(self, cells):
        """(Spearman, Pearson, mean abs gap, SD) for equal weights, then the same four weighted."""
        out = []
        for weighted in (False, True):
            s = self.rates(cells, weighted)
            out += [spearman(s, self.real), pearson(s, self.real),
                    sum(abs(x - y) for x, y in zip(s, self.real)) / len(s), st.pstdev(s)]
        return out

    def resample(self, rng):
        return {k: (sum(1 for _ in range(d) if rng.random() < w / d), d) for k, (w, d) in self.cells.items()}


METRICS = ("Spearman", "Pearson", "mean abs gap", "SD")


def parse_args(argv):
    opts = {"reps": 2000, "game1": False, "only": None}
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--reps":
            opts["reps"] = int(argv[i + 1]); i += 1
        elif a == "--only":
            opts["only"] = set(argv[i + 1].split(",")); i += 1
        elif a == "--game1":
            opts["game1"] = True
        else:
            pos.append(a)
        i += 1
    return pos, opts


def q(xs):
    xs = sorted(xs)
    return xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]


def main():
    pos, opts = parse_args(sys.argv[1:])
    if not pos:
        print(__doc__)
        return 2
    run = Path(pos[0])
    c = Calib(run, *(pos[1:2] or []), game1=opts["game1"], only=opts["only"])
    sim, wtd = c.rates(c.cells), c.rates(c.cells, weighted=True)
    m = c.metrics(c.cells)
    rng = random.Random(12345)
    boot = [c.metrics(c.resample(rng)) for _ in range(opts["reps"])]
    noise = [q([b[i] for b in boot]) for i in range(len(m))]

    print(f"{len(c.keys)} decks, from {c.source}")
    print(f"{'Deck':26s} {'Real':>6s} {'Sim':>6s} {'Gap':>6s} {'Wtd':>6s} {'Gap':>6s}")
    for k, s, w, r in sorted(zip(c.keys, sim, wtd, c.real), key=lambda t: -(t[1] - t[3])):
        print(f"{c.names[k]:26s} {r:6.1f} {s:6.1f} {s - r:+6.1f} {w:6.1f} {w - r:+6.1f}")
    print(f"\nReal SD {st.pstdev(c.real):.1f}")
    for j, label in enumerate(("equal-weighted opponents", "share-weighted opponents")):
        print(f"{label}:")
        for i, name in enumerate(METRICS):
            v, (lo, hi) = m[4 * j + i], noise[4 * j + i]
            print(f"  {name:13s} {v:6.2f}  noise range {lo:.2f}..{hi:.2f}")
    games = sum(d for _, d in c.cells.values())
    print(f"Decided games/matches: {games}; problems: {c.problems}")
    out = {"source": c.source, "spearman": m[0], "pearson": m[1], "mae": m[2], "sd": m[3],
           "spearman_noise": noise[0], "pearson_noise": noise[1], "mae_noise": noise[2], "sd_noise": noise[3],
           "weighted": {"spearman": m[4], "pearson": m[5], "mae": m[6], "sd": m[7],
                        "spearman_noise": noise[4], "pearson_noise": noise[5], "mae_noise": noise[6],
                        "sd_noise": noise[7]},
           "real_sd": st.pstdev(c.real),
           "decks": {c.names[k]: {"real": r, "sim": s, "weighted": w}
                     for k, s, w, r in zip(c.keys, sim, wtd, c.real)}}
    name = "calibration" + ("-game1" if opts["game1"] else "") + ("-subset" if opts["only"] else "") + ".json"
    (run / name).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
