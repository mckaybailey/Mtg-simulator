"""Compare a matrix run's pairing win rates with the (unverified) real matchup rows."""
import json, sys
from pathlib import Path
run = Path(sys.argv[1]); real = json.load(open(sys.argv[2]))
s = json.loads((run / "summary.json").read_text())
names = {k: e["name"] for k, e in s["entrants"].items()}
key = {v: k for k, v in names.items()}
cell = {}
for p in s["pairings"]:
    if p["decided"]:
        cell[(names[p["a"]], names[p["b"]])] = (p["wins"] / p["decided"], p["decided"])
        cell[(names[p["b"]], names[p["a"]])] = (1 - p["wins"] / p["decided"], p["decided"])
# one row per unordered pairing: weighted mean of the unambiguous real rows, oriented a->b
agg = {}
for m in real["matchups"]:
    if m["ambiguous"] or m["a_win_rate"] is None or m["a"] not in key or m["b"] not in key or not m["matches"]:
        continue
    a, b, r, n = m["a"], m["b"], m["a_win_rate"] / 100, m["matches"]
    if a > b: a, b, r = b, a, 1 - r
    agg.setdefault((a, b), []).append((r, n))
rows = []
for (a, b), xs in agg.items():
    n = sum(x[1] for x in xs); r = sum(x[0] * x[1] for x in xs) / n
    rows.append((a, b, r, n, cell[(a, b)][0]))
def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0]*len(v)
    for i, j in enumerate(o): r[j] = i
    return r
def pear(x, y):
    mx, my = sum(x)/len(x), sum(y)/len(y)
    sxy = sum((a-mx)*(b-my) for a, b in zip(x, y)); sxx = sum((a-mx)**2 for a in x); syy = sum((b-my)**2 for b in y)
    return sxy/(sxx*syy)**.5
for a, b, r, n, sim in sorted(rows):
    print(f"{a:22s} vs {b:22s} real {r*100:5.1f} (n~{n:4d})  sim {sim*100:5.1f}  gap {100*(sim-r):+6.1f}")
x = [r[2] for r in rows]; y = [r[4] for r in rows]
print(f"{len(rows)} pairings; Pearson {pear(x,y):.2f}, Spearman {pear(ranks(x),ranks(y)):.2f}, mean abs gap {100*sum(abs(a-b) for a,b in zip(x,y))/len(x):.1f}")
