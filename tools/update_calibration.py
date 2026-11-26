"""Write sim_win_rate, sim_swiss_win_rate and ai_pilot into a gauntlet.json from a matrix run,
and print the README table.

usage: python3 tools/update_calibration.py RUN_DIR [GAUNTLET_JSON]

sim_win_rate is the deck's mean game win rate in the round robin; sim_swiss_win_rate is its
match win rate when the round robin's pairing results are played out as simulated Swiss events
of the real events' structure (the run's calibration block; `python3 -m mtgsim calibrate RUN_DIR`
writes it for older runs). The real rates come from Swiss events, so ai_pilot is judged on the
Swiss rate: simulated minus real below -10 -> weak, within +-10 -> fair, above +10 -> strong.
The "calibration" description string is left for the caller to edit.
"""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
gpath = Path(sys.argv[2] if len(sys.argv) > 2 else "decks/standard/meta/gauntlet.json")
summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
cal = summary.get("calibration")
if not cal and (run / "calibration.json").exists():
    cal = json.loads((run / "calibration.json").read_text(encoding="utf-8"))
if not cal or not cal.get("decks"):
    sys.exit(f"{run} has no calibration block; run python3 -m mtgsim calibrate {run} first")
names = {k: e["name"] for k, e in summary["entrants"].items()}
sim = {names[r["key"]]: round(100 * r["mean_win_rate"], 1) for r in summary["matrix"]["ranking"]}
swiss = {d["name"]: round(d["swiss"], 1) for d in cal["decks"]}
data = json.loads(gpath.read_text(encoding="utf-8"))
rows = []
for deck in data["decks"]:
    if deck["name"] not in sim:
        continue
    deck["sim_win_rate"] = sim[deck["name"]]
    if deck["name"] in swiss:
        deck["sim_swiss_win_rate"] = swiss[deck["name"]]
        gap = swiss[deck["name"]] - deck["real_win_rate"]
        deck["ai_pilot"] = "weak" if gap < -10 else "strong" if gap > 10 else "fair"
    else:  # no real rate or share, so not in the Swiss comparison
        deck.pop("sim_swiss_win_rate", None)
        deck.pop("ai_pilot", None)
        continue
    rows.append((gap, deck["name"], deck["real_win_rate"], sim[deck["name"]], swiss[deck["name"]], deck["ai_pilot"]))
gpath.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("| Deck | Real win rate | Simulated (round robin) | Simulated (Swiss) | Gap (Swiss) | AI pilot |")
print("|---|---|---|---|---|---|")
for gap, name, real, s, sw, pilot in sorted(rows, reverse=True):
    sign = "+" if gap >= 0 else "−"
    print(f"| {name} | {real:.1f}% | {s:.1f}% | {sw:.1f}% | {sign}{abs(gap):.1f} | {pilot} |")
