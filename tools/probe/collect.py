"""Probe step C: merge the blind answers with the key and measure agreement with Forge.

Reads OUT/key.jsonl and OUT/answers.jsonl (one line per case: `case`, `choice`, `reason`) and
writes OUT/merged.jsonl (key, case text and answer side by side, plus `agree`: true, false or
null when the comparison is not mechanical) and prints agreement by decision kind and group.

Agreement is mechanical: mulligan keep/mulligan (and, after a mulligan, the same
cards on the bottom); counter or not (and with which card); the same set of attackers; the same
blocker -> attacker pairs; for spell decisions, the same set of spells cast and the same land (parenthetical
notes such as targets, discards or cards held are ignored; whether a spell is cast before or
after combat is reported separately as `timing`).
Two choices that agree need no grading in step D; the rest go to the grading sheet.

Usage: python3 tools/probe/collect.py --out probe
"""

import argparse
import collections
import json
import math
import re
from pathlib import Path


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("’", "'")).strip()


def names_in(text, candidates):
    """The candidate card names that occur in an answer, by normalised substring."""
    t = " " + norm(text) + " "
    return {c for c in candidates if (" " + norm(c) + " ") in t}


def strip_notes(text):
    """Drop parenthetical remarks, which name targets, discards and held cards, not casts."""
    prev = None
    while prev != text:
        prev, text = text, re.sub(r"\([^()]*\)", " ", text)
    return text


HELD = re.compile(r"\bhold\b|\bif (?:needed|unused|not needed|nothing)\b|\botherwise\b|\bkeep\b.*\bup\b", re.I)
LATER = re.compile(r"opponent's (?:turn|upkeep|draw|end step|combat)|their (?:turn|upkeep|end step)|next turn", re.I)


def top_level_parts(text):
    """Split on commas and semicolons outside brackets."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch in ",;" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


# A part that opens with how a spell is paid for or what is chosen for it ("collecting evidence with Duress,
# Duress and Superior Spider-Man and naming Kili"): it and the parts after it name cards, not casts.
NOTE = re.compile(r"^\s*(?:and\s+)?(?:collect|discard|nam(?:e|ing)\b|sacrific|pay(?:ing)?\b|copy|copying|exil)", re.I)


def drop_held(cast, own_turn_only):
    """Leave out the spells an answer only holds, or (in a decision about this turn) casts on a later turn."""
    keep = []
    for part in top_level_parts(cast):
        if NOTE.search(part):
            break
        if HELD.search(part) or (own_turn_only and LATER.search(part)):
            continue
        keep.append(part)
    return ",".join(keep)


def split_fields(choice, own_turn_only=False):
    land, cast = "", choice
    m = re.search(r"cast\s*:\s*(.*)$", choice, re.I | re.S)
    if m:
        cast = drop_held(m.group(1), own_turn_only)
        choice = choice[:m.start()] + "Cast: " + cast
    choice = strip_notes(choice)
    land, cast = "", choice
    m = re.search(r"land\s*:\s*(.*?)(;|$)", choice, re.I)
    if m:
        land = m.group(1)
    m = re.search(r"cast\s*:\s*(.*)$", choice, re.I)
    if m:
        cast = m.group(1)
    return land, cast


def agree(key, case_text, choice):
    kind, fo = key["kind"], key["forge"]
    c = choice.strip()
    low = c.lower()
    if kind == "mulligan":
        model = "mulligan" if low.startswith("mull") else "keep" if low.startswith("keep") else None
        if model is None:
            return None
        if model != fo["action"]:
            return False
        if model == "keep" and fo.get("bottom"):
            return names_in(c, set(key["hand"])) == set(fo["bottom"])
        return True
    if kind == "counter":
        model_counters = not low.startswith("let") and "counter" in low
        if model_counters != (fo["action"] == "counter"):
            return False
        return (not model_counters) or norm(fo["with"]) in norm(c)
    if kind == "attack":
        ids = set(map(int, re.findall(r"#(\d+)", c)))
        if re.search(r"\bnone\b", low) and not ids:
            ids = set()
        return ids == {a["id"] for a in fo["attackers"]}
    if kind == "block":
        pairs = set((int(a), int(b)) for a, b in re.findall(r"#(\d+)\s*(?:->|→|blocks?)\s*#(\d+)", c))
        return pairs == {(b["blocker"], b["attacker"]) for b in fo["blocks"]}
    # spell decisions: compare the sets of spells cast (and, where asked, the land played);
    # when to cast them (before or after combat) is not compared, see timing()
    hand = set(key["hand"])
    forge_cast = {x["name"] if isinstance(x, dict) else x for x in fo.get("cast", [])}
    land_text, cast_text = split_fields(c, own_turn_only=kind in ("main", "main2"))
    model_cast = names_in(cast_text, hand | forge_cast)
    same_cast = {norm(x) for x in model_cast} == {norm(x) for x in forge_cast & (hand | forge_cast)}
    if kind in ("main", "main2"):
        forge_land = {norm(x) for x in fo.get("lands", [])}
        model_land = {norm(x) for x in names_in(land_text, hand)} if land_text else set()
        return same_cast and model_land == forge_land
    return same_cast


def timing(key, choice):
    """For a `main` case both players cast the same spells in: "same", "differs" or None."""
    if key["kind"] != "main" or not key["forge"].get("cast"):
        return None
    differs = False
    for c in key["forge"]["cast"]:
        m = re.search(re.escape(c["name"]) + r"\s*\(([^)]*)\)", choice, re.I)
        if not m:
            return None
        said = m.group(1).lower()
        model_phase = "MAIN1" if "before" in said else "MAIN2" if "after" in said else None
        if model_phase and c.get("phase") in ("MAIN1", "MAIN2") and model_phase != c["phase"]:
            differs = True
    return "differs" if differs else "same"


def targets_named(key, choice):
    """For a spell case that agrees: whether the answer names each of Forge's targets ("same", "differs", None)."""
    casts = [x for x in key["forge"].get("cast", []) if isinstance(x, dict) and x.get("targets")]
    if not casts:
        return None
    for c in casts:
        for t in c["targets"]:
            m = re.match(r"(.*) \((\d+)\)$", t)
            if m:
                if "#" + m.group(2) not in choice and norm(m.group(1)) not in norm(choice):
                    return "differs"
            elif t in ("you", "opponent"):
                continue  # a player target is rarely written out
            elif norm(t) not in norm(choice):
                return "differs"
    return "same"


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="probe")
    args = ap.parse_args(argv)
    out = Path(args.out)
    keys = {k["case"]: k for k in map(json.loads, open(out / "key.jsonl"))}
    texts = {c["case"]: c["text"] for c in map(json.loads, open(out / "cases.jsonl"))}
    answers = {a["case"]: a for a in map(json.loads, open(out / "answers.jsonl"))}
    tally = collections.defaultdict(lambda: [0, 0, 0])  # agree, disagree, unclear
    timings = collections.Counter()
    targets = collections.Counter()
    with open(out / "merged.jsonl", "w") as fh:
        for cid in sorted(keys):
            k = keys[cid]
            a = answers.get(cid)
            res = agree(k, texts[cid], a["choice"]) if a else None
            fh.write(json.dumps({"case": cid, "kind": k["kind"], "deck": k["deck"], "group": k["group"],
                                 "forge": k["forge_text"], "model": a["choice"] if a else None,
                                 "reason": a.get("reason") if a else None, "agree": res,
                                 "timing": timing(k, a["choice"]) if a and res else None,
                                 "targets": targets_named(k, a["choice"]) if a and res else None,
                                 "text": texts[cid]}) + "\n")
            if a and res:
                timings[timing(k, a["choice"])] += 1
                targets[targets_named(k, a["choice"])] += 1
            for bucket in ("all", k["group"], k["kind"]):
                tally[bucket][0 if res is True else 1 if res is False else 2] += 1
    print("answers: %d of %d cases" % (len(answers), len(keys)))
    print("%-10s %5s %6s %8s %7s  %s" % ("", "cases", "agree", "differ", "unclear", "agreement (95% CI)"))
    for bucket in ["all", "planning", "creature"] + sorted(b for b in tally if b not in ("all", "planning", "creature")):
        a, d, u = tally[bucket]
        lo, hi = wilson(a, a + d)
        print("%-10s %5d %6d %8d %7d  %s" % (bucket, a + d + u, a, d, u,
                                            "%.0f%% (%.0f-%.0f%%)" % (100 * a / (a + d), 100 * lo, 100 * hi) if a + d else "-"))
    print("main cases that agree on the spells: timing the same %d, differs (before / after combat) %d"
          % (timings["same"], timings["differs"]))
    print("spell cases that agree and where Forge targeted something: answer names the same targets %d, others %d"
          % (targets["same"], targets["differs"]))


if __name__ == "__main__":
    main()
