"""What Monte Carlo search cost in one or more runs: rollouts and time per game and per rollout.

usage: python3 tools/mc_cost.py RUN_DIR [RUN_DIR ...]
Reads ``games.jsonl`` (engine time per game, and the ``mc`` counters the driver adds to games
with Monte Carlo) and ``logs/worker-*.log`` (the FLATMC-STATS line the driver prints after each
such game: decisions and their mean time, which gives the time spent searching). Times depend on
the machine and its load; the counters of ``--mc fixed`` games do not.
"""
import json
import re
import statistics
import sys
from pathlib import Path

GAME = re.compile(r"^\[mtgsim\] Monte Carlo in game (\S+) \((\d+) ms")
STATS = re.compile(r"^FLATMC-STATS decisions=(\d+) byRollouts=(\d+) rollouts=(\d+) .*?avgMs=([0-9.]+)")
SPLIT = re.compile(r"^FLATMC-REACTIVE mode=(\w+) .*?decisions=(\d+) changed=(\d+) .*?rollouts=(\d+) avgMs=([0-9.]+)")


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))] if values else 0


def main():
    for run in sys.argv[1:]:
        run = Path(run)
        games = {}
        for line in (run / "games.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                games[record["id"]] = record
        ok = [g for g in games.values() if g["status"] == "ok"]
        searched = [g for g in ok if g.get("mc")]
        print(f"{run.name}: {len(games)} games, {len(ok)} ok, {len(searched)} with search counters, "
              f"{sum(1 for g in games.values() if g['status'] == 'timeout')} timeouts")
        secs = [g["ms"] / 1000 for g in ok]
        if secs:
            print(f"  engine time per game: mean {statistics.mean(secs):.1f} s, median {statistics.median(secs):.1f} s, "
                  f"95th percentile {pct(secs, 0.95):.1f} s, longest {max(secs):.1f} s; total {sum(secs) / 60:.1f} min")
        if not searched:
            continue
        rollouts = [g["mc"]["rollouts"] for g in searched]
        decisions = [g["mc"]["decisions"] for g in searched]
        print(f"  rollouts per game: mean {statistics.mean(rollouts):.0f}, median {statistics.median(rollouts):.0f}, "
              f"95th percentile {pct(rollouts, 0.95)}, most {max(rollouts)}; "
              f"decisions per game: mean {statistics.mean(decisions):.0f}; "
              f"rollouts per decision {sum(rollouts) / max(1, sum(decisions)):.1f}; "
              f"failed rollouts {sum(g['mc']['failures'] for g in searched)}")
        search_ms = total_rollouts = 0.0
        modes = {}
        seen = set()
        current = None
        for log in sorted((run / "logs").glob("worker-*.log")):
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                m = GAME.match(line)
                if m:
                    current = m.group(1) if m.group(1) not in seen else None
                    seen.add(m.group(1))
                    continue
                if current is None:
                    continue
                m = STATS.match(line)
                if m:
                    search_ms += int(m.group(1)) * float(m.group(4))
                    total_rollouts += int(m.group(3))
                    continue
                m = SPLIT.match(line)
                if m:
                    row = modes.setdefault(m.group(1), [0, 0, 0, 0.0])
                    row[0] += int(m.group(2))
                    row[1] += int(m.group(3))
                    row[2] += int(m.group(4))
                    row[3] += int(m.group(2)) * float(m.group(5))
        if total_rollouts:
            game_ms = sum(g["ms"] for g in searched)
            print(f"  from the worker logs ({len(seen)} games): {search_ms / total_rollouts / 1000:.3f} s of search per rollout "
                  f"({total_rollouts / (search_ms / 1000):.1f} rollouts/s); search is "
                  f"{100 * search_ms / game_ms:.0f}% of the engine time of these games")
            for mode, (n, changed, r, ms) in sorted(modes.items()):
                print(f"    {mode:9s} decisions {n:6d}  changed the play {changed:5d}  rollouts {r:7d}  "
                      f"mean {ms / max(1, n):7.0f} ms")


if __name__ == "__main__":
    main()
