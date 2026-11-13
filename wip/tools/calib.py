"""Calibration metrics for a matrix run: sim vs real win rate per deck, with a game-noise range.

usage: python3 calib.py RUN_DIR [gauntlet.json] [--reps 2000]
Noise range: parametric bootstrap. Each pairing's wins are redrawn from Binomial(decided, observed
rate), deck averages and the correlations are recomputed; the 2.5-97.5 percentiles are reported.
"""
import json
import random
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


def main():
    args = [a for i, a in enumerate(sys.argv[1:]) if not a.startswith("--") and sys.argv[i] != "--reps"]
    reps = 2000
    if "--reps" in sys.argv:
        reps = int(sys.argv[sys.argv.index("--reps") + 1])
    run = Path(args[0])
    gauntlet = Path(args[1]) if len(args) > 1 else Path("decks/standard/meta/gauntlet.json")
    summary = json.loads((run / "summary.json").read_text())
    real_by_name = {d["name"]: d.get("real_win_rate") for d in json.loads(gauntlet.read_text())["decks"]}
    keys = [k for k, e in summary["entrants"].items()]
    names = {k: summary["entrants"][k]["name"] for k in keys}
    cells = {}
    for p in summary["pairings"]:
        cells[(p["a"], p["b"])] = (p["wins"], p["decided"])
    keys = [k for k in keys if real_by_name.get(names[k]) is not None]

    def deck_rates(cellmap):
        out = []
        for k in keys:
            rates = []
            for (a, b), (w, d) in cellmap.items():
                if d == 0:
                    continue
                if a == k:
                    rates.append(w / d)
                elif b == k:
                    rates.append(1 - w / d)
            out.append(100 * sum(rates) / len(rates))
        return out

    sim = deck_rates(cells)
    real = [real_by_name[names[k]] for k in keys]
    gaps = [s - r for s, r in zip(sim, real)]
    sp, pe = spearman(sim, real), pearson(sim, real)
    mae = sum(abs(g) for g in gaps) / len(gaps)
    rng = random.Random(12345)
    boot_sp, boot_pe, boot_mae = [], [], []
    for _ in range(reps):
        cm = {}
        for key, (w, d) in cells.items():
            p = w / d if d else 0.5
            cm[key] = (sum(1 for _ in range(d) if rng.random() < p), d)
        s2 = deck_rates(cm)
        boot_sp.append(spearman(s2, real))
        boot_pe.append(pearson(s2, real))
        boot_mae.append(sum(abs(a - b) for a, b in zip(s2, real)) / len(real))

    def q(xs):
        xs = sorted(xs)
        return xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]

    print(f"{'Deck':24s} {'Real':>6s} {'Sim':>6s} {'Gap':>6s}")
    for k, s, r, g in sorted(zip(keys, sim, real, gaps), key=lambda t: -t[3]):
        print(f"{names[k]:24s} {r:6.1f} {s:6.1f} {g:+6.1f}")
    print(f"\nSpearman {sp:.3f}  noise range {q(boot_sp)[0]:.2f}..{q(boot_sp)[1]:.2f}")
    print(f"Pearson  {pe:.3f}  noise range {q(boot_pe)[0]:.2f}..{q(boot_pe)[1]:.2f}")
    print(f"Mean abs gap {mae:.1f} points  noise range {q(boot_mae)[0]:.1f}..{q(boot_mae)[1]:.1f}")
    games = sum(d for _, d in cells.values())
    print(f"Decided games: {games}; problems: {summary.get('problems')}")
    out = {"spearman": sp, "pearson": pe, "mae": mae, "spearman_noise": q(boot_sp), "pearson_noise": q(boot_pe),
           "mae_noise": q(boot_mae), "decks": {names[k]: {"real": r, "sim": s} for k, s, r in zip(keys, sim, real)}}
    (run / "calibration.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
