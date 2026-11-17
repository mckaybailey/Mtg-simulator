"""How far an outside field could move a matrix run's meta decks towards their real win rates.

usage: python3 tools/field_bound.py RUN_DIR [gauntlet.json]

A deck's real win rate is against the whole field. If the meta decks in RUN_DIR make up a share S
of it, a deck's field win rate is S * (its share-weighted rate against those decks) + (1 - S) *
(its rate against everything else). The run fixes the first term; this prints what the second
would have to be for each deck to land on its real win rate (the "needed" column; outside 0-100
means no field can do it), and the spread (population SD) and mean gap of the decks for:
equal-weighted opponents, share-weighted opponents, and share-weighted plus a field that every
deck beats exactly 50% of the time.
"""
import json
import statistics as st
import sys
from pathlib import Path


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    run = Path(argv[0])
    gpath = Path(argv[1]) if len(argv) > 1 else Path("decks/standard/meta/gauntlet.json")
    summary = json.loads((run / "summary.json").read_text())
    g = json.loads(gpath.read_text())
    info = {}
    for d in g.get("decks", g):
        slug = Path(d.get("file", "")).stem or d["name"].lower().replace(" ", "-")
        info[slug] = d
    wr = {}
    for p in summary["pairings"]:
        if p.get("win_rate") is None:
            continue
        wr[(p["a"], p["b"])] = p["win_rate"]
        wr[(p["b"], p["a"])] = 1 - p["win_rate"]
    names = sorted({a for a, _ in wr if a in info and info[a].get("real_win_rate") is not None})
    real = {n: info[n]["real_win_rate"] / 100 for n in names}
    inside = sum(info[n]["meta_share"] for n in names) / 100
    outside = 1 - inside

    def equal(n):
        return st.mean(wr[(n, o)] for o in names if o != n)

    def weighted(n):
        ops = [o for o in names if o != n]
        ws = [info[o]["meta_share"] for o in ops]
        return sum(wr[(n, o)] * w for o, w in zip(ops, ws)) / sum(ws)

    def with_even_field(n):
        return inside * weighted(n) + outside * 0.5

    def stats(f):
        vals = [f(n) * 100 for n in names]
        gaps = [abs(f(n) - real[n]) * 100 for n in names]
        return st.mean(vals), st.pstdev(vals), st.mean(gaps)

    print(f"{len(names)} decks, {inside * 100:.1f}% of the real field; outside field {outside * 100:.1f}%")
    print(f"{'deck':28s} {'real':>6s} {'sim':>6s} {'needed':>7s}")
    for n in names:
        need = (real[n] - inside * weighted(n)) / outside if outside > 0 else float("nan")
        print(f"{n:28s} {real[n] * 100:6.1f} {weighted(n) * 100:6.1f} {need * 100:7.0f}")
    rv = [real[n] * 100 for n in names]
    print(f"\n{'':42s} {'mean':>6s} {'SD':>6s} {'gap':>6s}")
    print(f"{'real':42s} {st.mean(rv):6.1f} {st.pstdev(rv):6.1f}")
    for label, f in (("equal-weighted opponents", equal), ("share-weighted opponents", weighted),
                     ("share-weighted + field beaten 50% by all", with_even_field)):
        m, sd, gap = stats(f)
        print(f"{label:42s} {m:6.1f} {sd:6.1f} {gap:6.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
