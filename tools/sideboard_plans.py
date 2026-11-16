"""Print the sideboard plan Forge's SideboardAdvisor makes for every pairing of a deck folder, without playing.

usage: python3 tools/sideboard_plans.py [FOLDER] [--json OUT]   (default folder: decks/standard/meta)

Uses the driver's plan-only job (`sideboard=1 planonly=1`), so it shows exactly the swaps that games 2 and 3 of
`--bo3` runs are played with. Each swap is printed as "out>in".
"""
import collections
import itertools
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mtgsim import decks, forge  # noqa: E402
from mtgsim.carddb import load_database  # noqa: E402
from mtgsim.runner import Job, run_jobs  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
folder = Path(args[0] if args else "decks/standard/meta")
out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
install = forge.find_install(None)
db = load_database(install)
work = Path(tempfile.mkdtemp(prefix="mtgsim-plans-"))
paths = {}
for f in sorted(decks.find_deck_files(folder)):
    d = decks.load_deck(f, db)
    p = work / f"{f.stem}.dck"
    p.write_text(d.to_dck(), encoding="utf-8")
    paths[f.stem] = str(p.resolve())
jobs = [Job(id=f"{a}|{b}", seed=1, decks=[paths[a], paths[b]], sideboard=True, plan_only=True)
        for a, b in itertools.combinations(paths, 2)]
results = {}
run_jobs(install, jobs, lambda j, r: results.__setitem__(j.id, r), workers=2, log_dir=work / "logs")
plans = {}
for key, r in results.items():
    a, b = key.split("|")
    if r.get("status") != "plan":
        print(f"error for {key}: {str(r.get('error'))[:300]}")
        continue
    plans[f"{a}|{b}"], plans[f"{b}|{a}"] = r["sideboard"]
for a in paths:
    print(f"== {a}")
    for b in paths:
        if a != b and f"{a}|{b}" in plans:
            swaps = collections.Counter(plans[f"{a}|{b}"])
            print(f"  vs {b:24s} " + (", ".join(f"{n}x {s}" for s, n in swaps.items()) or "no changes"))
if out_json:
    Path(out_json).write_text(json.dumps(plans, indent=1), encoding="utf-8")
