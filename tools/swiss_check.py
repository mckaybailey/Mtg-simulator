"""Would Swiss pairing pull a matrix run's meta win rates towards the real ones?

usage: python3 tools/swiss_check.py RUN_DIR|TABLE.json [gauntlet.json] [options]

TABLE.json is a pairing table such as decks/standard/meta/sim-matchups.json (the summary.json
fields "entrants" and "pairings"), so no run folder is needed.

The real win rates come from Swiss events, not a round robin: players are paired by record, so
a deck that wins meets stronger opposition, and the real figures are match results. This takes
a matrix run's pairing results, turns each game win rate p into a best-of-three match win rate
(p^2 (3 - 2p), unless --games), and plays simulated events: players get decks drawn by meta
share, each round pairs players with equal records (no rematches where avoidable), matches are
decided by the converted rates. A deck's win rate is its match wins over matches played, mirror
matches and byes left out (as the real figures are). It prints, for every deck and as SD, mean
gap, Spearman and sign errors against the real rates:

  rr-games    share-weighted game win rates against the meta decks (the calibration's "wtd")
  rr-matches  share-weighted match win rates, the rest of the field included as "other"
  swiss       the simulated events

swiss minus rr-matches is the pairing effect; the noise ranges come from a parametric bootstrap
of the run's games (each pairing's wins redrawn), with --boot-events events per replicate.

options:
  --events E[,E...]      events per simulated "season" (default 600:12). E is N:R[:cR/L][:wW][:lL]:
                         N players, R Swiss rounds; cR/L: after round R only players with at most
                         L losses play on (day-2 cut); wW / lL: a player stops on reaching W wins /
                         L losses. --events real is the three real events (see REAL_EVENTS).
  --cut R:L              cut for events that give none
  --drop L               stop at L losses for events that give none (default: nobody drops)
  --seasons K            seasons to simulate for the point estimate (default 200)
  --other-rate X         match win rate of every meta deck against the rest of the field (default 0.5)
  --no-other             the field is the meta decks only, shares rescaled to 100%
  --games                use game win rates as match rates (no best-of-three conversion)
  --reps B               bootstrap replicates (default 100; 0 skips the noise ranges)
  --boot-seasons K       seasons per replicate (default 10)
  --seed S               (default 1)
  --json PATH            also write the results there
"""
import json
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from calibration import Calib  # noqa: E402
from mtgsim.calibration import FRACTURE_2026_EVENTS, Field, parse_event, swiss  # noqa: E402
from mtgsim.calibration import metrics as _metrics  # noqa: E402

# The three events of the Magic.gg article (checked 23 Nov 2026): Arena Championship 13, 176
# players, nine rounds of modified Swiss in which a player stops at 7 wins or 3 losses (magic.gg
# viewer's guide); Magic Spotlight: Fracture in Hartford (775 players) and Beijing (865), nine
# rounds, 18+ match points (at most 3 losses without draws) to day two, six more rounds
# (melee.gg tournaments 440878 and 457663). Top 16 / top 8 playoffs are left out.
REAL_EVENTS = FRACTURE_2026_EVENTS


def parse_args(argv):
    o = {"events": "600:12", "cut": None, "drop": None, "seasons": 200, "other_rate": 0.5,
         "no_other": False, "games": False, "reps": 100, "boot_seasons": 10, "seed": 1, "json": None}
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a == "--events":
            o["events"] = REAL_EVENTS if nxt == "real" else nxt; i += 1
        elif a == "--cut":
            o["cut"] = tuple(int(x) for x in nxt.split(":")); i += 1
        elif a == "--drop":
            o["drop"] = int(nxt); i += 1
        elif a in ("--seasons", "--reps", "--boot-seasons", "--seed"):
            o[a[2:].replace("-", "_")] = int(nxt); i += 1
        elif a == "--other-rate":
            o["other_rate"] = float(nxt); i += 1
        elif a == "--json":
            o["json"] = nxt; i += 1
        elif a == "--no-other":
            o["no_other"] = True
        elif a == "--games":
            o["games"] = True
        elif a.startswith("--"):
            raise SystemExit(f"unknown option {a}")
        else:
            pos.append(a)
        i += 1
    o["event_list"] = [parse_event(e) for e in o["events"].split(",")]
    for e in o["event_list"]:
        if e["cut"] is None:
            e["cut"] = o["cut"]
        if e["loss_cap"] is None:
            e["loss_cap"] = o["drop"]
    return pos, o


def metrics(sim, real):
    m = _metrics(sim, real)
    return {"sd": m["sd"], "mae": m["mean_gap"], "spearman": m["spearman"], "sign_errors": m["sign_errors"]}


def evaluate(c, cells, o, seasons, rng):
    """The tool's three rows; the field and the events are mtgsim.calibration's."""
    nm = len(c.keys)
    f = Field(c.keys, c.share, cells, cells if o["games"] else None, o["other_rate"], not o["no_other"])
    rows = {"rr-games": [100 * f.rr(f.game, k, nm) for k in range(nm)],
            "rr-matches": [100 * f.rr(f.m, k) for k in range(nm)]}
    rows["swiss"] = [100 * x for x in swiss(f, o["event_list"], seasons, rng)[:nm]]
    return rows


def q(xs):
    xs = sorted(xs)
    return xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]


def main():
    pos, o = parse_args(sys.argv[1:])
    if not pos:
        print(__doc__)
        return 2
    c = Calib(pos[0], *(pos[1:2] or []))
    rng = random.Random(o["seed"])
    rows = evaluate(c, c.cells, o, o["seasons"], rng)
    m = {k: metrics(v, c.real) for k, v in rows.items()}

    boot = []
    for _ in range(o["reps"]):
        b = evaluate(c, c.resample(rng), o, o["boot_seasons"], rng)
        bm = {k: metrics(v, c.real) for k, v in b.items()}
        bm["diff"] = {x: bm["swiss"][x] - bm["rr-matches"][x] for x in ("sd", "mae", "spearman")}
        boot.append(bm)

    print(f"{len(c.keys)} decks; events: {o['events']}; seasons {o['seasons']}; "
          f"{'game rates' if o['games'] else 'best-of-three'}; "
          f"{'meta decks only' if o['no_other'] else f'rest of field as other at {o['other_rate']:.2f}'}")
    print(f"{'Deck':26s} {'Real':>6s} {'RR-g':>6s} {'RR-m':>6s} {'Swiss':>6s} {'Sw-RRm':>7s}")
    order = sorted(range(len(c.keys)), key=lambda i: -(rows["swiss"][i] - c.real[i]))
    for i in order:
        print(f"{c.names[c.keys[i]]:26s} {c.real[i]:6.1f} {rows['rr-games'][i]:6.1f} "
              f"{rows['rr-matches'][i]:6.1f} {rows['swiss'][i]:6.1f} {rows['swiss'][i] - rows['rr-matches'][i]:+7.1f}")
    flat = metrics([50.0] * len(c.real), c.real)
    print(f"\nReal SD {st.pstdev(c.real):.1f}; every deck at 50%: mean gap {flat['mae']:.1f}, "
          f"sign errors {flat['sign_errors']} (ties count as none)")
    for k in ("rr-games", "rr-matches", "swiss"):
        line = f"{k:11s}"
        for x, fmt in (("sd", ".1f"), ("mae", ".1f"), ("spearman", ".2f")):
            v = m[k][x]
            rng_s = ""
            if boot:
                lo, hi = q([b[k][x] for b in boot])
                rng_s = f" ({lo:{fmt}}..{hi:{fmt}})"
            line += f"  {x} {v:{fmt}}{rng_s}"
        line += f"  sign errors {m[k]['sign_errors']}"
        print(line)
    if boot:
        line = "swiss - rr-matches"
        for x, fmt in (("sd", "+.1f"), ("mae", "+.1f"), ("spearman", "+.2f")):
            lo, hi = q([b["diff"][x] for b in boot])
            line += f"  {x} {m['swiss'][x] - m['rr-matches'][x]:{fmt}} ({lo:{fmt}}..{hi:{fmt}})"
        print(line)
        print(f"(noise ranges: {o['reps']} bootstrap replicates of the run's games, {o['boot_seasons']} seasons each)")
    if o["json"]:
        out = {"options": {k: v for k, v in o.items() if k not in ("json", "event_list")}, "metrics": m, "flat": flat,
               "decks": {c.names[k]: {"real": c.real[i], **{r: rows[r][i] for r in rows}}
                         for i, k in enumerate(c.keys)}}
        Path(o["json"]).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
