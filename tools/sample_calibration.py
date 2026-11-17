"""Calibration of the meta decks against a random sample of the real field.

usage: python3 tools/sample_calibration.py MATRIX_RUN[#game1] SAMPLE_RUNS [--sample GAUNTLET_JSON]
           [--meta GAUNTLET_JSON] [--reps 2000]

SAMPLE_RUNS is a folder of gauntlet runs (tools/sample_runs.sh writes runs/sample/<deck>), each one
meta deck against the decks of --sample (default decks/standard/fracture-2026-sample/gauntlet.json):
lists drawn at random from the events behind the real win rates, so every list counts once and the
sample stands for the field by its real composition. A deck's sample win rate is its plain average
over the sampled lists; "no mirror" leaves out the lists whose `archetype` is the deck's own name, as
the real win rates do. MATRIX_RUN (the meta decks against each other) gives the comparison: each
deck's rate against the other meta decks weighted by `meta_share`, as calibration.py prints it.

Printed for the meta decks with a real win rate and sample games: real, meta-only, sample, sample
without mirrors; Spearman, mean absolute gap and SD (population SD of the decks' rates) of each,
with game-noise ranges (every pairing's wins redrawn from its observed rate).
"""
import json
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibration import q, spearman  # noqa: E402


def main(argv):
    opts = {"meta": "decks/standard/meta/gauntlet.json", "sample": "decks/standard/fracture-2026-sample/gauntlet.json",
            "reps": 2000}
    pos = []
    i = 0
    while i < len(argv):
        if argv[i] in ("--meta", "--sample", "--reps"):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            pos.append(argv[i])
            i += 1
    if len(pos) != 2:
        print(__doc__)
        return 2
    meta = {Path(d["file"]).stem: d for d in json.loads(Path(opts["meta"]).read_text())["decks"]}
    sample_by_file = {d["file"]: d for d in json.loads(Path(opts["sample"]).read_text())["decks"]}

    mpath, _, tag = pos[0].partition("#")
    msum = json.loads((Path(mpath) / "summary.json").read_text())
    mcells = {(p["a"], p["b"]): (p["wins"], p["decided"])
              for p in msum["pairings_game1" if tag == "game1" else "pairings"]}

    scells = {}      # (meta key, sample key) -> (wins, decided)
    arche = {}       # sample key -> archetype
    for summ in sorted(Path(pos[1]).glob("*/summary.json")):
        run = summ.parent
        for e in json.loads((run / "run.json").read_text())["entrants"]:
            if e["role"] != "hero":
                arche[e["key"]] = sample_by_file[Path(e["source"]).name].get("archetype", "other")
        for p in json.loads(summ.read_text())["pairings"]:
            if p["a"] in meta and p["b"] in arche:
                scells[(p["a"], p["b"])] = (p["wins"], p["decided"])

    keys = sorted(k for k in meta if meta[k].get("real_win_rate") is not None and any(a == k for a, _ in scells))
    real = [meta[k]["real_win_rate"] for k in keys]

    def meta_rate(k, cm):
        num = den = 0.0
        for (a, b), (w, d) in cm.items():
            if d and k in (a, b):
                opp, r = (b, w / d) if a == k else (a, 1 - w / d)
                num += meta[opp]["meta_share"] * r
                den += meta[opp]["meta_share"]
        return 100 * num / den

    def sample_rate(k, cm, mirrors):
        rs = [w / d for (a, b), (w, d) in cm.items()
              if a == k and d and (mirrors or arche[b] != meta[k]["name"])]
        return 100 * st.mean(rs)

    def all_rates(mc, sc):
        return ([meta_rate(k, mc) for k in keys], [sample_rate(k, sc, True) for k in keys],
                [sample_rate(k, sc, False) for k in keys])

    def metrics(rates):
        return [v for s in rates for v in (spearman(s, real), sum(abs(x - y) for x, y in zip(s, real)) / len(s),
                                           st.pstdev(s))]

    base = all_rates(mcells, scells)
    m = metrics(base)
    rng = random.Random(12345)

    def redraw(cells):
        return {key: (sum(1 for _ in range(d) if rng.random() < w / d), d) for key, (w, d) in cells.items()}

    boot = [metrics(all_rates(redraw(mcells), redraw(scells))) for _ in range(int(opts["reps"]))]
    noise = [q([b[j] for b in boot]) for j in range(len(m))]

    n_opp = len(arche)
    matches = sum(d for d in (v[1] for v in scells.values()))
    print(f"{len(keys)} meta decks rated against {n_opp} sampled lists ({matches} decided matches); "
          f"{sum(1 for a in arche.values() if a in {d['name'] for d in meta.values()})} of the lists are meta archetypes")
    print(f"{'Deck':24s} {'Real':>6s} {'Meta':>6s} {'Gap':>6s} {'Sample':>7s} {'Gap':>6s} {'NoMirr':>7s} {'Gap':>6s}")
    rows = sorted(zip(keys, real, *base), key=lambda t: -(t[4] - t[1]))
    for k, r, a, b, c in rows:
        print(f"{meta[k]['name']:24s} {r:6.1f} {a:6.1f} {a - r:+6.1f} {b:7.1f} {b - r:+6.1f} {c:7.1f} {c - r:+6.1f}")
    print(f"\nReal SD {st.pstdev(real):.1f}")
    for j, label in enumerate(("meta decks only (share-weighted)", "random field sample (all lists)",
                               "random field sample, mirrors excluded")):
        print(f"{label}:")
        for i, name in enumerate(("Spearman", "mean abs gap", "SD")):
            v, (lo, hi) = m[3 * j + i], noise[3 * j + i]
            print(f"  {name:13s} {v:6.2f}  noise range {lo:.2f}..{hi:.2f}")
    diffs = {}
    for j, label in ((1, "sample"), (2, "sample_no_mirror")):
        print(f"{label} minus meta-only (95% range of the difference over the same resamples):")
        for i, name in enumerate(("Spearman", "mean abs gap", "SD")):
            v = m[3 * j + i] - m[i]
            lo, hi = q([b[3 * j + i] - b[i] for b in boot])
            diffs.setdefault(label, {})[("spearman", "mae", "sd")[i]] = [v, lo, hi]
            print(f"  {name:13s} {v:+6.2f}  ({lo:+.2f} to {hi:+.2f})")
    out = {"diff_vs_meta": diffs, "decks":{meta[k]["name"]: {"real": r, "meta": a, "sample": b, "sample_no_mirror": c}
                     for k, r, a, b, c in rows},
           "real_sd": st.pstdev(real),
           "metrics": {label: dict(zip(("spearman", "mae", "sd"), m[3 * j:3 * j + 3]))
                       for j, label in enumerate(("meta", "sample", "sample_no_mirror"))},
           "noise": {label: dict(zip(("spearman", "mae", "sd"), noise[3 * j:3 * j + 3]))
                     for j, label in enumerate(("meta", "sample", "sample_no_mirror"))}}
    (Path(pos[1]) / "sample_calibration.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
