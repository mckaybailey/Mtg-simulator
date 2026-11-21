"""Would Swiss pairing pull a matrix run's meta win rates towards the real ones?

usage: python3 tools/swiss_check.py RUN_DIR [gauntlet.json] [options]

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
  --events N:R[,N:R...]  events per simulated "season": N players, R Swiss rounds (default 600:12)
  --cut R:L              after round R only players with at most L losses play on (day-2 cut)
  --drop L               a player drops on reaching L losses (default: nobody drops)
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
from calibration import Calib, spearman  # noqa: E402

OTHER = "other"


def bo3(p):
    return p * p * (3 - 2 * p)


def parse_args(argv):
    o = {"events": [(600, 12)], "cut": None, "drop": None, "seasons": 200, "other_rate": 0.5,
         "no_other": False, "games": False, "reps": 100, "boot_seasons": 10, "seed": 1, "json": None}
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a == "--events":
            o["events"] = [tuple(int(x) for x in e.split(":")) for e in nxt.split(",")]; i += 1
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
    return pos, o


class Field:
    """Archetypes (the meta decks, plus "other" unless --no-other), shares and match win rates."""

    def __init__(self, c, cells, o):
        self.keys = list(c.keys)
        shares = [c.share[k] for k in self.keys]
        if not o["no_other"]:
            self.keys.append(OTHER)
            shares.append(max(0.0, 100.0 - sum(shares)))
        tot = sum(shares)
        self.share = [s / tot for s in shares]
        n = len(self.keys)
        idx = {k: i for i, k in enumerate(self.keys)}
        conv = (lambda p: p) if o["games"] else bo3
        self.m = [[0.5] * n for _ in range(n)]
        self.game = [[0.5] * n for _ in range(n)]
        for (a, b), (w, d) in cells.items():
            if not d:
                continue
            p = w / d
            ia, ib = idx[a], idx[b]
            self.game[ia][ib], self.game[ib][ia] = p, 1 - p
            self.m[ia][ib], self.m[ib][ia] = conv(p), conv(1 - p)
        if OTHER in idx:
            j = idx[OTHER]
            for i in range(n):
                if i != j:
                    self.m[i][j], self.m[j][i] = o["other_rate"], 1 - o["other_rate"]
        self.cum = []
        acc = 0.0
        for s in self.share:
            acc += s
            self.cum.append(acc)

    def draw(self, rng):
        x = rng.random()
        for i, c in enumerate(self.cum):
            if x < c:
                return i
        return len(self.cum) - 1

    def rr(self, matrix, k):
        """Share-weighted rate of deck k against the other archetypes (mirrors left out)."""
        num = den = 0.0
        for j, s in enumerate(self.share):
            if j != k:
                num += s * matrix[k][j]
                den += s
        return num / den


def pair(players, rng, played):
    """Swiss pairing: sort by points (random order within a score group), pair down greedily
    avoiding rematches; an odd player out gets a bye. Returns (pairs, bye or None)."""
    order = sorted(players, key=lambda p: (-p[1], rng.random()))
    pairs, bye = [], None
    unpaired = order
    while unpaired:
        a = unpaired[0]
        rest = unpaired[1:]
        if not rest:
            bye = a
            break
        pick = 0
        for j, b in enumerate(rest):
            if (a[0], b[0]) not in played:
                pick = j
                break
        b = rest[pick]
        pairs.append((a, b))
        unpaired = rest[:pick] + rest[pick + 1:]
    return pairs, bye


def play_event(field, n_players, rounds, o, rng, wins, games):
    # player: [id, points, losses, deck]
    players = [[i, 0, 0, field.draw(rng)] for i in range(n_players)]
    played = set()
    for r in range(1, rounds + 1):
        active = [p for p in players if (o["drop"] is None or p[2] < o["drop"])]
        if o["cut"] and r > o["cut"][0]:
            active = [p for p in active if p[2] <= o["cut"][1]]
        if len(active) < 2:
            break
        pairs, bye = pair(active, rng, played)
        if bye is not None:
            bye[1] += 1
        for a, b in pairs:
            played.add((a[0], b[0]))
            played.add((b[0], a[0]))
            da, db = a[3], b[3]
            a_wins = rng.random() < field.m[da][db]
            w, l = (a, b) if a_wins else (b, a)
            w[1] += 1
            l[2] += 1
            if da != db:
                games[da] += 1
                games[db] += 1
                wins[w[3]] += 1


def swiss(field, o, seasons, rng):
    n = len(field.keys)
    wins, games = [0] * n, [0] * n
    for _ in range(seasons):
        for n_players, rounds in o["events"]:
            play_event(field, n_players, rounds, o, rng, wins, games)
    return [wins[i] / games[i] if games[i] else float("nan") for i in range(n)]


def metrics(sim, real):
    gaps = [abs(s - r) for s, r in zip(sim, real)]
    signs = sum(1 for s, r in zip(sim, real) if (s - 50) * (r - 50) < 0)
    return {"sd": st.pstdev(sim), "mae": sum(gaps) / len(gaps), "spearman": spearman(sim, real),
            "sign_errors": signs}


def evaluate(c, cells, o, seasons, rng):
    f = Field(c, cells, o)
    nm = len(c.keys)
    rows = {
        "rr-games": [100 * f.rr(f.game, k) if o["no_other"] else 100 * rr_meta(f, k, nm) for k in range(nm)],
        "rr-matches": [100 * f.rr(f.m, k) for k in range(nm)],
    }
    sw = swiss(f, o, seasons, rng)
    rows["swiss"] = [100 * x for x in sw[:nm]]
    return rows


def rr_meta(f, k, nm):
    """Share-weighted game win rate against the meta decks only, as calibration.py's "wtd"."""
    num = den = 0.0
    for j in range(nm):
        if j != k:
            num += f.share[j] * f.game[k][j]
            den += f.share[j]
    return num / den


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

    ev = ", ".join(f"{n} players x {r} rounds" for n, r in o["events"])
    print(f"{len(c.keys)} decks; events: {ev}; seasons {o['seasons']}; cut {o['cut']}; drop {o['drop']}; "
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
        out = {"options": {k: v for k, v in o.items() if k != "json"}, "metrics": m, "flat": flat,
               "decks": {c.names[k]: {"real": c.real[i], **{r: rows[r][i] for r in rows}}
                         for i, k in enumerate(c.keys)}}
        Path(o["json"]).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
