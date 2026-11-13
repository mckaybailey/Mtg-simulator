"""Compare gauntlet runs of one hero deck played on different engines (same seeds).

usage: python3 tools/compare_arms.py HERO_KEY RUN_DIR [RUN_DIR ...] [--cards "A,B,C"]
Prints, per run: overall win rate (decided games, equal weight per opponent as in the gauntlet
summary, plus pooled) with 95% Wilson interval; per-opponent win rates; how often the named cards
were seen and cast. For each later run vs the first: the pooled difference with a 95% interval
(unpaired), and a paired view on the games both runs share (same id => same seed and seats).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mtgsim import stats  # noqa: E402


def load(run):
    games = {}
    for line in open(Path(run) / "games.jsonl", encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            games[r["id"]] = r
    return games


def hero_result(r, hero):
    """1 win, 0 loss, None undecided, for the hero deck."""
    if r["status"] != "ok" or r["winner_seat"] < 0:
        return None
    seat = r["seats"].index(hero)
    return 1 if r["winner_seat"] == seat else 0


def hero_player(r, hero):
    return r["players"][r["seats"].index(hero)] if r.get("players") else {}


def main():
    args = sys.argv[1:]
    cards = []
    if "--cards" in args:
        i = args.index("--cards")
        cards = [c.strip() for c in args[i + 1].split(",") if c.strip()]
        del args[i:i + 2]
    hero, runs = args[0], args[1:]
    data = [load(r) for r in runs]
    base = data[0]
    for run, games in zip(runs, data):
        res = [(r, hero_result(r, hero)) for r in games.values()]
        dec = [(r, x) for r, x in res if x is not None]
        wins = sum(x for _, x in dec)
        lo, hi = stats.wilson(wins, len(dec))
        opps = sorted({r["b"] if r["a"] == hero else r["a"] for r, _ in dec})
        per = []
        for o in opps:
            xs = [x for r, x in dec if o in (r["a"], r["b"])]
            per.append((o, sum(xs), len(xs)))
        eq = sum(w / n for _, w, n in per) / len(per)
        undecided = len(res) - len(dec)
        print(f"== {run}: pooled {100 * wins / len(dec):.1f}% ({100 * lo:.0f}-{100 * hi:.0f}), "
              f"{wins}-{len(dec) - wins}, equal-weight {100 * eq:.1f}%, undecided {undecided}")
        print("   " + "  ".join(f"{o[:14]} {100 * w / n:.0f}" for o, w, n in per))
        for c in cards:
            seen = cast = casts = 0
            for r in games.values():
                p = hero_player(r, hero)
                if not p:
                    continue
                s = p.get("opening", {}).get(c, 0) + p.get("drawn", {}).get(c, 0)
                k = p.get("played", {}).get(c, 0)
                seen += s > 0
                cast += k > 0
                casts += k
            print(f"   {c}: seen in {seen} games, cast in {cast} ({casts} casts)")
    for run, games in zip(runs[1:], data[1:]):
        shared = [i for i in games if i in base]
        a = [hero_result(base[i], hero) for i in shared]
        b = [hero_result(games[i], hero) for i in shared]
        pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
        wa, wb, n = sum(x for x, _ in pairs), sum(y for _, y in pairs), len(pairs)
        diff = (wb - wa) / n
        test = stats.diff_test(wb, n, wa, n)
        same = sum(1 for x, y in pairs if x == y)
        gained = sum(1 for x, y in pairs if x == 0 and y == 1)
        lost = sum(1 for x, y in pairs if x == 1 and y == 0)
        # paired interval for the difference in proportions (Wald on discordant pairs)
        se = math.sqrt(max(gained + lost - (gained - lost) ** 2 / n, 0)) / n
        print(f"-- {run} vs {runs[0]} on {n} shared decided games: {100 * diff:+.1f} points; "
              f"unpaired 95% CI {100 * test['ci'][0]:+.1f}..{100 * test['ci'][1]:+.1f} (p={test['p']:.4f}); "
              f"paired 95% CI {100 * (diff - 1.96 * se):+.1f}..{100 * (diff + 1.96 * se):+.1f}; "
              f"same result {same}, loss->win {gained}, win->loss {lost}")


if __name__ == "__main__":
    main()
