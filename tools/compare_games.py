"""Compare two runs game by game: winner, turns, first seat and every player's card logs."""
import json
import sys
from pathlib import Path

FIELDS = ("status", "winner_seat", "turns", "first_seat", "seats", "seed")
PLAYER = ("opening", "drawn", "played", "mulligans", "turns", "life", "lossReason")


def load(path):
    return {r["id"]: r for r in (json.loads(l) for l in Path(path, "games.jsonl").read_text().splitlines() if l.strip())}


total = same = 0
for base, new in zip(sys.argv[1::2], sys.argv[2::2]):
    a, b = load(base), load(new)
    for gid in sorted(a, key=lambda k: int(k.rsplit("|", 1)[1])):
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
