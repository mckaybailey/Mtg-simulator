"""Tally probe step D: the judges' grades of the disagreements, unblinded with grading-key.jsonl.

Reads OUT/judgements/pass{1,2}-NN.json (each a judge's JSON array) and prints, overall, for the
planning and creature decks and by kind:
- per case, the verdict of the two passes together: answerer (both passes, or one with the
  other equal), Forge (likewise), or no preference (both equal, or the passes disagree);
- the answerer's share of the cases with a verdict, with a 95% Wilson interval (the gate);
- position bias: how often a judge picked A, and how often the two passes disagree.
Writes OUT/grades.jsonl, one line per case.
"""
import argparse
import collections
import json
from pathlib import Path

from collect import wilson


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="probe/round3/grading")
    args = ap.parse_args(argv)
    out = Path(args.out)
    key = {k["case"]: k for k in map(json.loads, open(out / "grading-key.jsonl"))}
    grades = collections.defaultdict(dict)  # case -> pass -> (side, margin, reason)
    letters = collections.Counter()
    for path in sorted((out / "judgements").glob("pass*.json")):
        p = path.name[4]
        for g in json.load(open(path)):
            k = key[g["case"]]
            b = g["better"].strip()
            letters[b] += 1
            side = "equal" if b == "equal" else ("forge" if b == k["forge_letter"][p] else "model")
            grades[g["case"]][p] = (side, g.get("margin"), g.get("reason"))
    missing = [(c, p) for c in key for p in "12" if p not in grades[c]]
    if missing:
        print("missing grades:", missing)
    rows = []
    with open(out / "grades.jsonl", "w") as fh:
        for c, k in key.items():
            s = [grades[c][p][0] for p in "12" if p in grades[c]]
            sides = set(s) - {"equal"}
            verdict = sides.pop() if len(sides) == 1 else "none"
            split = len(set(s)) > 1
            row = dict(k, pass1=grades[c].get("1"), pass2=grades[c].get("2"), verdict=verdict, split=split)
            rows.append(row)
            fh.write(json.dumps(row) + "\n")

    def line(label, rs):
        v = collections.Counter(r["verdict"] for r in rs)
        n = v["model"] + v["forge"]
        lo, hi = wilson(v["model"], n)
        share = "%3.0f%% (%2.0f-%3.0f%%)" % (100 * v["model"] / n, 100 * lo, 100 * hi) if n else "  -"
        both = sum(1 for r in rs if r["pass1"] and r["pass2"] and r["pass1"][0] == r["pass2"][0] == r["verdict"])
        print("%-16s %5d %7d %7d %6d   %s   %4d %6d" % (label, len(rs), v["model"], v["forge"], v["none"],
                                                        share, both, sum(r["split"] for r in rs)))

    print("%-16s %5s %7s %7s %6s   %-17s %4s %6s" % ("", "cases", "answer", "Forge", "none",
                                                     "answerer's share", "both", "split"))
    line("all", rows)
    for g in ("planning", "creature"):
        line(g, [r for r in rows if r["group"] == g])
    for kind in sorted({r["kind"] for r in rows}):
        line("  " + kind, [r for r in rows if r["kind"] == kind])
    total = sum(letters.values())
    print("\njudges picked A %d, B %d, equal %d of %d grades" % (letters["A"], letters["B"], letters["equal"], total))
    margins = collections.Counter((g[0], g[1]) for c in grades for g in grades[c].values())
    print("grades by side and margin:", dict(sorted(margins.items(), key=str)))


if __name__ == "__main__":
    main()
