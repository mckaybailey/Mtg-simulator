"""Write sim_win_rate / ai_pilot into a gauntlet.json from a matrix run, and print the README table.

usage: python3 update_calibration.py RUN_DIR [GAUNTLET_JSON]
ai_pilot: simulated minus real below -10 -> weak, within +-10 -> fair, above +10 -> strong.
The "calibration" description string is left for the caller to edit.
"""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
gpath = Path(sys.argv[2] if len(sys.argv) > 2 else "decks/standard/meta/gauntlet.json")
summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
names = {k: e["name"] for k, e in summary["entrants"].items()}
sim = {names[r["key"]]: round(100 * r["mean_win_rate"], 1) for r in summary["matrix"]["ranking"]}
data = json.loads(gpath.read_text(encoding="utf-8"))
rows = []
for deck in data["decks"]:
    if deck["name"] not in sim:
        continue
    deck["sim_win_rate"] = sim[deck["name"]]
    gap = sim[deck["name"]] - deck["real_win_rate"]
    deck["ai_pilot"] = "weak" if gap < -10 else "strong" if gap > 10 else "fair"
    rows.append((gap, deck["name"], deck["real_win_rate"], sim[deck["name"]], deck["ai_pilot"]))
gpath.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("| Deck | Real win rate | Simulated | Gap | AI pilot |")
print("|---|---|---|---|---|")
for gap, name, real, s, pilot in sorted(rows, reverse=True):
    sign = "+" if gap >= 0 else "−"
    print(f"| {name} | {real:.1f}% | {s:.1f}% | {sign}{abs(gap):.1f} | {pilot} |")
