"""Compare two runs game by game: winner, turns, first seat and every player's card logs.

usage: python3 tools/compare_games.py BASE NEW [BASE2 NEW2 ...] [--game1]
Ids are "a|b|i" (best-of-one, or game 1 of best-of-three match i) and "a|b|i|g2" / "a|b|i|g3".
--game1 compares only the "a|b|i" games, e.g. two best-of-three runs that share their game 1s.
"""
import json
import sys
from pathlib import Path

FIELDS = ("status", "winner_seat", "turns", "first_seat", "seats", "seed")
PLAYER = ("opening", "drawn", "played", "mulligans", "turns", "life", "lossReason")


def load(path):
    return {r["id"]: r for r in (json.loads(l) for l in Path(path, "games.jsonl").read_text().splitlines() if l.strip())}


def order(gid):
    parts = gid.split("|")
    return parts[0], parts[1], int(parts[2]), parts[3] if len(parts) > 3 else ""


game1 = "--game1" in sys.argv
args = [x for x in sys.argv[1:] if x != "--game1"]
total = same = 0
for base, new in zip(args[0::2], args[1::2]):
    a, b = load(base), load(new)
    if game1:
        a = {k: v for k, v in a.items() if k.count("|") == 2}
    for gid in sorted(a, key=order):
        total += 1
        ra, rb = a[gid], b.get(gid)
        diffs = []
        if rb is None:
            diffs.append("missing")
        else:
            diffs += [f for f in FIELDS if ra.get(f) != rb.get(f)]
            for seat, (pa, pb) in enumerate(zip(ra["players"], rb["players"])):
                diffs += [f"p{seat}.{f}" for f in PLAYER if pa.get(f) != pb.get(f)]
        if diffs:
            print(f"DIFF {gid}: {diffs}")
        else:
            same += 1
    print(f"{Path(base).name} vs {Path(new).name}: {len(a)} baseline games, {len(b)} new")
print(f"identical: {same} of {total}")
