"""Calibration of the meta decks against a wider field: a matrix run plus gauntlet runs against outside decks.

usage: python3 tools/field_calibration.py MATRIX_RUN[#game1] GAUNTLET_RUN... [--meta GAUNTLET_JSON]
           [--field GAUNTLET_JSON] [--only SLUG,...] [--reps 2000]

MATRIX_RUN holds the meta decks against each other (RUN#game1 reads a best-of-three run's game 1s).
Each GAUNTLET_RUN (or a folder of them) holds one meta deck against the outside decks. A meta deck's
field win rate is its win rate against every other deck, weighted by that deck's `meta_share`
(from --meta, default decks/standard/meta/gauntlet.json, and --field, default
decks/standard/fracture-2026-field/gauntlet.json). This is how the real win rates are measured:
against the whole field, mirrors excluded. Printed for the meta decks with a real win rate: real,
simulated against the meta decks only, simulated against the meta plus the field, and the
Spearman correlation, mean absolute gap and SD of both, with game-noise ranges (parametric
bootstrap, as in calibration.py). --only restricts the meta decks being rated (their opponents stay).
"""
import json
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibration import q, spearman  # noqa: E402


def shares(path):
    g = json.loads(Path(path).read_text())
    return {Path(d["file"]).stem: d for d in g["decks"]}


def main(argv):
    opts = {"meta": "decks/standard/meta/gauntlet.json", "field": "decks/standard/fracture-2026-field/gauntlet.json",
            "reps": 2000, "only": None}
    pos = []
    i = 0
    while i < len(argv):
        if argv[i] in ("--meta", "--field", "--reps", "--only"):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            pos.append(argv[i])
            i += 1
    if len(pos) < 2:
        print(__doc__)
        return 2
    meta, field = shares(opts["meta"]), shares(opts["field"])
    info = {**field, **meta}
    mpath, _, tag = pos[0].partition("#")
    summary = json.loads((Path(mpath) / "summary.json").read_text())
    cells = {}
    for p in summary["pairings_game1" if tag == "game1" else "pairings"]:
        cells[(p["a"], p["b"])] = (p["wins"], p["decided"])
    runs = []
    for arg in pos[1:]:
        path = Path(arg)
        runs += [path] if (path / "summary.json").is_file() else sorted(x.parent for x in path.glob("*/summary.json"))
    outside = set()
    for run in runs:
        s = json.loads((run / "summary.json").read_text())
        for p in s["pairings"]:
            if p["b"] in meta or p["a"] not in meta:
                continue  # a meta deck against an outside deck only
            cells[(p["a"], p["b"])] = (p["wins"], p["decided"])
            outside.add(p["b"])
    missing = outside - set(field)
    if missing:
        raise SystemExit(f"outside decks without a meta_share in {opts['field']}: {sorted(missing)}")
    keys = sorted(k for k in meta if meta[k].get("real_win_rate") is not None
                  and any(k in c for c in cells) and (opts["only"] is None or k in opts["only"].split(",")))
    real = [meta[k]["real_win_rate"] for k in keys]
    have_field = [k for k in keys if any(a == k and b in outside for a, b in cells)]

    def rate(k, cm, with_field):
        num = den = 0.0
        for (a, b), (w, d) in cm.items():
            if not d or k not in (a, b):
                continue
            opp, r = (b, w / d) if a == k else (a, 1 - w / d)
            if opp in outside and not with_field:
                continue
            wt = info[opp].get("meta_share") or 0.0
            num += wt * r
            den += wt
        return 100 * num / den

    def metrics(cm):
        out = []
        for wf in (False, True):
            s = [rate(k, cm, wf) for k in keys]
            out += [spearman(s, real), sum(abs(x - y) for x, y in zip(s, real)) / len(s), st.pstdev(s)]
        return out

    m = metrics(cells)
    rng = random.Random(12345)
    boot = []
    for _ in range(int(opts["reps"])):
        cm = {key: (sum(1 for _ in range(d) if rng.random() < w / d), d) for key, (w, d) in cells.items()}
        boot.append(metrics(cm))
    noise = [q([b[i] for b in boot]) for i in range(len(m))]
    share_in = sum(meta[k]["meta_share"] for k in meta)
    share_out = sum(field[k]["meta_share"] for k in outside)
    print(f"{len(keys)} meta decks rated; opponents: {len(meta)} meta decks ({share_in:.1f}% of the field) "
          f"+ {len(outside)} outside decks ({share_out:.1f}%); {len(have_field)} meta decks have field games")
    print(f"{'Deck':26s} {'Real':>6s} {'Meta':>6s} {'Gap':>6s} {'+Field':>7s} {'Gap':>6s} {'vsField':>8s}")
    rows = []
    for k, r in zip(keys, real):
        a, b = rate(k, cells, False), rate(k, cells, True)
        fr = [(w / d) for (x, y), (w, d) in cells.items() if x == k and y in outside and d]
        rows.append((b - r, f"{meta[k]['name']:26s} {r:6.1f} {a:6.1f} {a - r:+6.1f} {b:7.1f} {b - r:+6.1f} "
                            f"{(100 * st.mean(fr)) if fr else float('nan'):8.1f}"))
    for _, line in sorted(rows, key=lambda t: -t[0]):
        print(line)
    print(f"\nReal SD {st.pstdev(real):.1f}   (all rates weighted by opponent meta_share; vsField = plain average "
          f"against the outside decks)")
    for j, label in enumerate(("meta decks only", "meta decks + field")):
        print(f"{label}:")
        for i, name in enumerate(("Spearman", "mean abs gap", "SD")):
            v, (lo, hi) = m[3 * j + i], noise[3 * j + i]
            print(f"  {name:13s} {v:6.2f}  noise range {lo:.2f}..{hi:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
