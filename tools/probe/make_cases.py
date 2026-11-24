"""Probe step C: sample decision cases from a snapshot run and write them as plain text.

Reads every `snapshots/*.jsonl` under the given run folders (the step B run, `runs/probe-b`),
picks close decisions stratified by deck and decision kind, and writes:

- OUT/batches/batch-NN.txt: about ten cases each, as the answerer sees them: the deciding
  player's visible state, both decklists, the decision and its options, and the Oracle text of
  every card named (from Forge's card database). Nothing in a batch says which program made
  the original choice, the game's result, or that the cases come from a simulation.
- OUT/key.jsonl: one line per case with where it came from and Forge's choice (raw and in
  words). Never shown to the answerers.
- OUT/cases.jsonl: one line per case with its text, for the grading sheet (step D).

Usage: python3 tools/probe/make_cases.py runs/probe-b --out probe --n 200 --seed 1
"""

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mtgsim.carddb import load_database  # noqa: E402
from mtgsim.forge import find_install  # noqa: E402

PLANNING = ["Azorius Control", "Four-Color Control", "Izzet Spellementals", "Dimir Midrange",
            "Jund Sacrifice", "Dimir Uldaros", "Dimir Excruciator"]
CREATURE = ["Boros Dwarves", "Boros Dragons", "Mono-Green Landfall", "Mono-Black Aggro",
            "Orzhov Lifegain", "Rakdos Lizards"]

# Cases per planning deck by kind (25 a deck, 175 in all), and for the creature decks together
# (25, a comparison group). A kind short of candidates hands its places to the fallback kinds.
PLANNING_QUOTA = {"main": 7, "block": 4, "attack": 3, "mulligan": 3, "main2": 2, "counter": 2,
                  "endstep": 2, "upkeep": 1, "draw": 1}
CREATURE_QUOTA = {"main": 7, "attack": 6, "block": 5, "mulligan": 3, "main2": 2, "endstep": 1,
                  "upkeep": 1}
FALLBACK = ["main", "block", "attack", "main2", "mulligan"]
PER_GAME = 2  # at most this many cases from one game

PHASES = {"UPKEEP": "upkeep", "DRAW": "draw step", "MAIN1": "first main phase",
          "MAIN2": "second main phase", "COMBAT_DECLARE_ATTACKERS": "declare attackers step",
          "COMBAT_DECLARE_BLOCKERS": "declare blockers step", "END_OF_TURN": "end step",
          "COMBAT_BEGIN": "beginning of combat", "COMBAT_END": "end of combat",
          "COMBAT_FIRST_STRIKE_DAMAGE": "first-strike damage step", "COMBAT_DAMAGE": "combat damage step",
          "CLEANUP": "cleanup step", "UNTAP": "untap step"}


class Cards:
    def __init__(self):
        self.db = load_database(find_install())

    def get(self, name):
        return self.db.get(name)

    def cmc(self, name):
        card = self.get(name)
        if card is None:
            return 99
        if card.has_land_face:  # a modal spell // land: its spell face may be the cheaper option
            return card.front.cost.cmc
        return card.cmc

    def is_land(self, name):
        card = self.get(name)
        return card is not None and card.is_land

    def token_text(self, name):
        """Oracle text of a token, when Forge's token scripts have exactly one token of that name."""
        if not hasattr(self, "_tokens"):
            self._tokens = collections.defaultdict(list)
            folder = find_install().res / "tokenscripts"
            for path in sorted(folder.glob("*.txt")):
                fields = {}
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    key, sep, value = line.partition(":")
                    if sep and key in ("Name", "Types", "PT", "Oracle"):
                        fields[key] = value
                if "Name" in fields:
                    self._tokens[fields["Name"]].append(fields)
        found = self._tokens.get(name, [])
        if len(found) != 1 or not found[0].get("Oracle", "").strip():
            return None
        f = found[0]
        return "%s — token %s%s\n%s" % (name, f.get("Types", ""), (" " + f["PT"]) if f.get("PT") else "",
                                        f["Oracle"].replace("\\n", "\n").strip())

    def text(self, name):
        card = self.get(name)
        if card is None:
            return self.token_text(name)
        parts = []
        for face in card.faces:
            cost = "".join("{%s}" % t for t in face.mana_cost.split()) if face.mana_cost and face.mana_cost != "no cost" else ""
            head = face.name + (" " + cost if cost else "") + " — " + face.type_line
            if face.pt:
                head += " " + face.pt
            body = re.sub(r"\\n", "\n", face.oracle or "").strip()
            parts.append(head + ("\n" + body if body else ""))
        joiner = {"modal": "\n  (other face) ", "transform": "\n  (back face) ", "split": "\n  (split) ",
                  "adventure": "\n  (adventure) "}.get(card.layout, "\n  (other face) ")
        return joiner.join(parts)


def load_decisions(run_dirs):
    games, decisions = {}, []
    for run in run_dirs:
        for path in sorted(Path(run).glob("**/snapshots/*.jsonl")):
            with open(path) as fh:
                for line in fh:
                    d = json.loads(line)
                    if d["type"] == "game":
                        games[d["game"]] = d
                    else:
                        d["_file"] = str(path)
                        decisions.append(d)
    return games, decisions


def untapped_creatures(side):
    return [p for p in side["battlefield"] if "Creature" in p["types"] and not p["tapped"]]


def close_spot(d, cards):
    """True for a decision with more than one sensible option (forced or empty ones are skipped)."""
    fo, st, ctx, kind = d["forge"], d["state"], d["context"], d["kind"]
    if "unresolved" in fo:
        return False
    you, opp = st["you"], st["opponent"]
    if kind == "mulligan":
        lands = sum(cards.is_land(c) for c in you["hand"])
        return lands in (2, 5) or ctx["mulligansSoFar"] > 0 or fo["action"] == "mulligan"
    if kind == "main":
        if st["turn"] < 2:
            return False
        land_in_hand = any(cards.is_land(c) for c in you["hand"])
        mana = you["manaOpen"] + (1 if land_in_hand and you["landsPlayedThisTurn"] == 0 else 0)
        options = {c for c in you["hand"] if not cards.is_land(c) and cards.cmc(c) <= mana}
        return len(options) >= 2
    if kind == "attack":
        return len(ctx["canAttack"]) >= 2 or bool(untapped_creatures(opp))
    if kind == "block":
        mine = untapped_creatures(you)
        return bool(mine) and (len(mine) >= 2 or len(ctx["attackers"]) >= 2)
    if kind in ("main2", "upkeep", "draw", "endstep"):
        return bool(ctx.get("castable"))
    if kind == "counter":
        return True
    return False


def sample(decisions, cards, n, seed):
    rng = random.Random(seed)
    pool = collections.defaultdict(list)  # (deck, kind) -> candidates
    for d in decisions:
        if d["deck"] in PLANNING or d["deck"] in CREATURE:
            if close_spot(d, cards):
                pool[(d["deck"], d["kind"])].append(d)
    for key in pool:
        rng.shuffle(pool[key])
    per_game = collections.Counter()
    chosen = []

    def take(deck, kind, k):
        got = 0
        for d in pool.get((deck, kind), []):
            if got >= k:
                break
            if d.get("_taken") or per_game[(d["game"], d["seat"])] >= PER_GAME:
                continue
            d["_taken"] = True
            per_game[(d["game"], d["seat"])] += 1
            chosen.append(d)
            got += 1
        return got

    def fill(deck, quota):
        short = 0
        for kind, k in quota.items():
            short += k - take(deck, kind, k)
        for kind in FALLBACK:
            if short <= 0:
                break
            short -= take(deck, kind, short)

    for deck in PLANNING:
        fill(deck, PLANNING_QUOTA)
    # creature decks: spread the comparison group's quota over the six decks in turn
    order = list(CREATURE)
    rng.shuffle(order)
    i = 0
    for kind, k in CREATURE_QUOTA.items():
        for _ in range(k):
            for _try in range(len(order)):
                deck = order[i % len(order)]
                i += 1
                if take(deck, kind, 1):
                    break
    rng.shuffle(chosen)
    return chosen[:n]


def chosen_text(chosen):
    """The choices made for a permanent as it entered or resolved (the driver's `chosen` object)."""
    words = []
    for key, label in (("type", "type"), ("type2", "second type"), ("colors", "colour"), ("player", "player"),
                       ("number", "number"), ("cards", "card"), ("named", "card name"), ("mode", "mode"),
                       ("direction", "direction"), ("evenOdd", "odd or even"), ("sector", "sector")):
        v = chosen.get(key)
        if v is None:
            continue
        if isinstance(v, list):
            v = ", ".join(v)
        words.append("%s %s" % (label, v))
    return "chose " + "; ".join(words)


def perm_text(p, controller_you):
    bits = [p["name"]]
    if p.get("token"):
        if "text" in p:
            bits.append("(token: %s)" % (p["text"].replace("\\n", " ").replace("\n", " ") if p["text"] else "no abilities"))
        else:
            bits.append("(token)")
    if "power" in p:
        bits.append("%s/%s" % (p["power"], p["toughness"]))
    flags = []
    flags.append("tapped" if p["tapped"] else "untapped")
    if p.get("sick"):
        flags.append("summoning sick")
    if p.get("damage"):
        flags.append("%d damage marked" % p["damage"])
    if p.get("counters"):
        flags.append(", ".join("%d %s counter%s" % (v, k.lower().replace("_", " "), "" if v == 1 else "s")
                               for k, v in p["counters"].items()))
    if p.get("attachedTo") is not None:
        flags.append("attached to #%s" % p["attachedTo"])
    if p.get("chosen"):
        flags.append(chosen_text(p["chosen"]))
    return "#%s %s [%s] — %s" % (p["id"], " ".join(bits), p["types"], "; ".join(flags))


def side_text(label, side, is_you):
    lines = ["%s: life %d%s, library %d cards, %s." % (
        label, side["life"], (", %d poison" % side["poison"]) if side.get("poison") else "",
        side["library"],
        "hand (%d): %s" % (side["handCount"], ", ".join(side["hand"]) if side["hand"] else "empty")
        if is_you else "%d cards in hand" % side["handCount"])]
    lines.append("  Lands played this turn: %d. Untapped mana available: %d (counting mana that can be spent only "
                 "on some spells, such as Cavern of Souls' or a restricted Treasure's)." % (
                     side["landsPlayedThisTurn"], side["manaOpen"]))
    lands = [p for p in side["battlefield"] if p["types"].split(" - ")[0].endswith("Land") and "Creature" not in p["types"]]
    others = [p for p in side["battlefield"] if p not in lands]
    lines.append("  Lands: " + ("; ".join(
        "#%s %s (%s%s)" % (p["id"], p["name"], "tapped" if p["tapped"] else "untapped",
                           "; " + chosen_text(p["chosen"]) if p.get("chosen") else "") for p in lands) or "none"))
    lines.append("  Other permanents:" + ("" if others else " none"))
    for p in others:
        lines.append("    " + perm_text(p, is_you))
    lines.append("  Graveyard: " + (", ".join(side["graveyard"]) or "empty"))
    if side["exile"]:
        lines.append("  Exile (face up): " + ", ".join(side["exile"]))
    return lines


def decklist_text(main):
    return ", ".join("%d %s" % (v, k) for k, v in sorted(main.items()))


def decision_text(d, game):
    kind, st, ctx = d["kind"], d["state"], d["context"]
    you = st["you"]
    if kind == "mulligan":
        m = ctx["mulligansSoFar"]
        q = ("This is your opening hand of seven%s. You are %s. London mulligan rules: if you keep "
             "after %d mulligan%s, you put %d card%s from this hand on the bottom of your library.") % (
            "" if m == 0 else " after %d mulligan%s" % (m, "" if m == 1 else "s"),
            "on the play" if ctx["onThePlay"] else "on the draw", m, "" if m == 1 else "s", m, "" if m == 1 else "s")
        if m == 0:
            q = ("This is your opening hand of seven. You are %s. London mulligan rules apply."
                 % ("on the play" if ctx["onThePlay"] else "on the draw"))
        opts = "KEEP or MULLIGAN." + (" If KEEP, also name the %d card%s you put on the bottom." % (m, "" if m == 1 else "s") if m else "")
        return q, opts
    if kind == "main":
        q = ("Your first main phase is beginning (you have drawn for the turn). Plan the rest of your turn: "
             "which land you play (if any) and which spells you cast this turn, each marked "
             "before combat, during combat or after combat. Cards you do not name are held. "
             "(Attacks are decided separately; you may say in a few words whether you intend to attack.)")
        opts = ("Any land you may play (one per turn unless an effect allows more) and any spells you can pay "
                "for, or casting nothing. "
                "Answer as: Land: <name or none>; Cast: <spell (timing)>, ... or none.")
        return q, opts
    if kind == "main2":
        q = "It is your second main phase (combat is over this turn)."
        opts = ("Castable now (as far as mana and targets go; spells that cost less because of a cost reduction "
                "may be missing from this list): %s. You may cast any of these (and play a land if you "
                "have not this turn), or cast nothing and hold them. Answer as: Land: <name or none>; Cast: ... or none."
                % ", ".join(ctx["castable"]))
        return q, opts
    if kind in ("upkeep", "draw", "endstep"):
        where = {"upkeep": "It is your upkeep (you have not drawn yet this turn).",
                 "draw": "It is your draw step; you have just drawn your card for the turn.",
                 "endstep": "It is the end step of your opponent's turn; your turn is next."}[kind]
        opts = ("Castable now at instant speed (spells that cost less because of a cost reduction may be missing "
                "from this list): %s. Cast one or more of them now (say what and on what target), "
                "or cast nothing now. Answer as: Cast: <spell (target)>, ... or none." % ", ".join(ctx["castable"]))
        return where, opts
    if kind == "attack":
        cands = {p["id"]: p for p in you["battlefield"]}
        names = ["#%s %s %s/%s" % (i, cands[i]["name"], cands[i].get("power"), cands[i].get("toughness"))
                 if i in cands else "#%s" % i for i in ctx["canAttack"]]
        walkers = [p for p in st["opponent"]["battlefield"] if "Planeswalker" in p["types"]]
        q = "It is your declare attackers step."
        opts = ("Creatures that can attack: %s. Choose which of them attack (any subset, or none)%s. "
                "Answer as: Attack: #id, #id ... or none."
                % ("; ".join(names), ", and whether each attacks the opponent or one of their planeswalkers (%s)"
                   % ", ".join("#%s %s" % (p["id"], p["name"]) for p in walkers) if walkers else ""))
        return q, opts
    if kind == "block":
        opp = {p["id"]: p for p in st["opponent"]["battlefield"]}
        atk = []
        for a in ctx["attackers"]:
            p = opp.get(a["id"], {})
            atk.append("#%s %s %s/%s attacking %s" % (a["id"], a["name"], p.get("power"), p.get("toughness"),
                                                      "you" if a["attacking"] == "you" else a["attacking"]))
        mine = untapped_creatures(you)
        q = "Your opponent has declared attackers; it is your declare blockers step."
        opts = ("Attacking: %s. Your untapped creatures: %s. Choose blocks (each blocker blocks one attacker; several "
                "may block the same attacker), or no blocks. Answer as: Blocks: #blocker -> #attacker, ... or none."
                % ("; ".join(atk), "; ".join("#%s %s %s/%s" % (p["id"], p["name"], p["power"], p["toughness"]) for p in mine)))
        return q, opts
    if kind == "counter":
        sp = ctx["spell"]
        q = "Your opponent has just cast %s (mana value %s); it is on the stack." % (sp["name"], sp["manaValue"])
        opts = ("Counterspells you can cast at it now: %s. Counter it (say with which card), or let it resolve. "
                "Answer as: Counter with <card> / Let it resolve." % ", ".join(ctx["castableCounters"]))
        return q, opts
    raise ValueError(kind)


def case_text(cid, d, game):
    st = d["state"]
    seat = d["seat"]
    went_first = game["first"] == seat
    deck_you = game["seats"][seat]["main"]
    deck_opp = game["seats"][1 - seat]["main"]
    lines = ["=== CASE %s ===" % cid,
             "You are playing %s against %s (Standard, best-of-one, both decklists are open)." % (d["deck"], d["opponentDeck"]),
             "Your decklist (60): " + decklist_text(deck_you),
             "Opponent's decklist (60): " + decklist_text(deck_opp)]
    if d["kind"] != "mulligan":
        whose = "your" if st["activePlayer"] == "you" else "your opponent's"
        lines.append("Turn %d of the game (turns of both players counted together; %s), %s %s." % (
            st["turn"], "you went first" if went_first else "your opponent went first", whose,
            PHASES.get(st["phase"], st["phase"])))
        lines += side_text("YOU", st["you"], True)
        lines += side_text("OPPONENT", st["opponent"], False)
        if "spellsThisTurn" in st:
            for key, label in (("spellsLastTurn", "Spells cast last turn"), ("spellsThisTurn", "Spells cast so far this turn")):
                sp = st[key]
                lines.append("%s: you %s; opponent %s." % (label, ", ".join(sp["you"]) or "none",
                                                          ", ".join(sp["opponent"]) or "none"))
            lines.append("(No other history is shown: abilities activated, cards revealed, or whether a condition "
                         "such as a crime has been met this turn.)")
        if st["stack"]:
            lines.append("STACK (top first): " + "; ".join(
                "%s (%s's %s%s)" % (s["name"], "your" if s["controller"] == "you" else "opponent",
                                    s["kind"], (", targeting " + ", ".join(map(str, s["targets"]))) if s.get("targets") else "")
                for s in reversed(st["stack"])))
    else:
        lines.append("Your hand: " + ", ".join(st["you"]["hand"]))
    q, opts = decision_text(d, game)
    lines.append("DECISION: " + q)
    lines.append("OPTIONS: " + opts)
    return "\n".join(lines)


def names_in(d, game):
    st = d["state"]
    names = set(game["seats"][0]["main"]) | set(game["seats"][1]["main"])
    for side in ("you", "opponent"):
        s = st.get(side, {})
        names |= set(s.get("hand", [])) | set(s.get("graveyard", [])) | set(s.get("exile", []))
        names |= {p["name"] for p in s.get("battlefield", [])}
        for p in s.get("battlefield", []):  # cards named or chosen for a permanent (ids stripped)
            ch = p.get("chosen", {})
            names |= set(ch.get("named", [])) | {re.sub(r" \(\d+\)$", "", c) for c in ch.get("cards", [])}
    names |= {s["name"] for s in st.get("stack", [])}
    return names


def forge_words(d):
    fo, kind = d["forge"], d["kind"]
    if kind == "mulligan":
        return "MULLIGAN" if fo["action"] == "mulligan" else "KEEP" + (
            " (bottom: %s)" % ", ".join(fo["bottom"]) if fo.get("bottom") else "")
    if kind in ("main", "main2", "upkeep", "draw", "endstep"):
        phase = {"MAIN1": "before combat", "MAIN2": "after combat", "END_OF_TURN": "end step", "UPKEEP": "upkeep",
                 "DRAW": "draw step"}
        def one(c):
            if not isinstance(c, dict):
                return c
            notes = []
            if kind == "main":
                notes.append(phase.get(c.get("phase"), "during combat" if "COMBAT" in str(c.get("phase"))
                                       else str(c.get("phase")).lower()))
            if c.get("targets"):
                notes.append("targeting " + ", ".join(c["targets"]))
            return c["name"] + (" (%s)" % "; ".join(notes) if notes else "")
        cast = ", ".join(one(c) for c in fo.get("cast", [])) or "none"
        land = ", ".join(fo.get("lands", [])) or "none"
        return ("Land: %s; Cast: %s" % (land, cast)) if kind in ("main", "main2") else "Cast: %s" % cast
    if kind == "attack":
        return "Attack: " + (", ".join("#%s %s%s" % (a["id"], a["name"], "" if a["attacking"] == "opponent" else " -> " + a["attacking"])
                                       for a in fo["attackers"]) or "none")
    if kind == "block":
        return "Blocks: " + (", ".join("#%s %s -> #%s" % (b["blocker"], b["name"], b["attacker"]) for b in fo["blocks"]) or "none")
    if kind == "counter":
        return "Counter with %s" % fo["with"] if fo["action"] == "counter" else "Let it resolve (%s)" % fo.get("result")
    return json.dumps(fo)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default="probe")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    cards = Cards()
    games, decisions = load_decisions(args.runs)
    chosen = sample(decisions, cards, args.n, args.seed)
    out = Path(args.out)
    (out / "batches").mkdir(parents=True, exist_ok=True)
    with open(out / "key.jsonl", "w") as key, open(out / "cases.jsonl", "w") as cases:
        for b in range(0, len(chosen), args.batch):
            batch = chosen[b:b + args.batch]
            texts, names = [], set()
            for j, d in enumerate(batch):
                cid = "C%03d" % (b + j + 1)
                game = games[d["game"]]
                text = case_text(cid, d, game)
                texts.append(text)
                names |= names_in(d, game)
                key.write(json.dumps({"case": cid, "batch": b // args.batch + 1, "game": d["game"], "n": d["n"],
                                      "file": d["_file"], "kind": d["kind"], "deck": d["deck"],
                                      "opponentDeck": d["opponentDeck"],
                                      "group": "planning" if d["deck"] in PLANNING else "creature",
                                      "hand": d["state"]["you"].get("hand", []),
                                      "forge": d["forge"], "forge_text": forge_words(d)}) + "\n")
                cases.write(json.dumps({"case": cid, "kind": d["kind"], "deck": d["deck"], "text": text}) + "\n")
            gloss = []
            for name in sorted(names):
                t = cards.text(name)
                if t:
                    gloss.append(t)
            body = ("CARD REFERENCE (Oracle text of every card named in this batch)\n\n" + "\n\n".join(gloss)
                    + "\n\n\nCASES\n\n" + "\n\n".join(texts) + "\n")
            (out / "batches" / ("batch-%02d.txt" % (b // args.batch + 1))).write_text(body)
    c = collections.Counter((d["deck"] in PLANNING, d["kind"]) for d in chosen)
    print("%d cases in %d batches" % (len(chosen), -(-len(chosen) // args.batch)))
    print("planning:", {k: v for (p, k), v in sorted(c.items()) if p})
    print("creature:", {k: v for (p, k), v in sorted(c.items()) if not p})
    print("by deck:", dict(collections.Counter(d["deck"] for d in chosen)))


if __name__ == "__main__":
    main()
