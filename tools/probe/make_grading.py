"""Build the blind grading sheets of probe step D from a round's merged.jsonl.

Every disagreeing case is shown with its two choices, Forge's and the answerer's, as an unnamed
A and B. Each case is graded twice by different judges: pass 1 with a seeded random order, pass 2
with A and B swapped and the cases regrouped, so no judge sees a case twice and a preference for
a position or for one judge's mood shows as a split verdict. The answer's reason is never shown.

Writes OUT/sheets/pass{1,2}-NN.txt (a card reference for the cases in the file, then the cases)
and OUT/grading-key.jsonl (which letter is Forge's in each pass).
"""
import argparse
import json
import random
import re
from pathlib import Path

REF_HEAD = "CARD REFERENCE (Oracle text of every card named in this batch)"


def load_reference(batches):
    """Card name -> Oracle entry, from the case batches' card references."""
    ref = {}
    for path in sorted(batches.glob("batch-*.txt")):
        body = path.read_text()
        head = body.split("\n\n\nCASES\n\n")[0]
        for entry in head[len(REF_HEAD):].strip().split("\n\n"):
            first = entry.split("\n")[0]
            name = re.split(r" \{| — ", first)[0].strip()
            ref.setdefault(name, entry)
    return ref


def plain(kind, choice):
    """Write both sides alike, so the format does not tell which is Forge's."""
    choice = choice.strip().replace("Let it resolve (resolved)", "Let it resolve")
    m = re.match(r"KEEP\s*(?:\(bottom: (.*)\)|[,;]\s*bottom:?\s*(.*))$", choice)
    if m:
        return "KEEP, bottom: " + (m.group(1) or m.group(2)).strip().rstrip(".")
    if kind in ("attack", "block"):
        head, _, rest = choice.partition(":")
        if rest.strip().lower().startswith("none"):
            return head + ": none"
        if kind == "attack":
            ids = re.findall(r"#\d+", rest)
            return head + ": " + ", ".join(ids)
        pairs = re.findall(r"(#\d+)[^,#]*?->\s*(#\d+)", rest)
        return head + ": " + ", ".join("%s -> %s" % p for p in pairs)
    return choice


def sheet(cases, ref):
    blob = "\n".join(c["text"] + "\n" + c["forge"] + "\n" + c["model"] for c in cases)
    names = sorted(n for n in ref if n in blob)
    parts = []
    for c in cases:
        text = c["text"].rstrip()
        text = re.sub(r"\nOPTIONS: .*$", lambda m: m.group(0).replace("Answer as:", "Choices are written as:"), text)
        parts.append(text + "\n\nCHOICE A: " + c["A"] + "\nCHOICE B: " + c["B"])
    return (REF_HEAD + "\n\n" + "\n\n".join(ref[n] for n in names)
            + "\n\n\nCASES\n\n" + "\n\n".join(parts) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--round", default="probe/round3")
    ap.add_argument("--out", default="probe/round3/grading")
    ap.add_argument("--per-sheet", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    rnd, out = Path(args.round), Path(args.out)
    ref = load_reference(rnd / "batches")
    merged = [json.loads(l) for l in open(rnd / "merged.jsonl")]
    cases = [m for m in merged if m["agree"] is False]
    rng = random.Random(args.seed)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    key = []
    for c in cases:
        forge_first = rng.random() < 0.5
        key.append({"case": c["case"], "kind": c["kind"], "deck": c["deck"], "group": c["group"],
                    "forge_letter": {"1": "A" if forge_first else "B", "2": "B" if forge_first else "A"}})
    with open(out / "grading-key.jsonl", "w") as fh:
        for k in key:
            fh.write(json.dumps(k) + "\n")
    letters = {k["case"]: k["forge_letter"] for k in key}
    n = args.per_sheet
    order2 = cases[n // 2:] + cases[:n // 2]  # pass 2 groups the cases differently
    for p, seq in (("1", cases), ("2", order2)):
        for i in range(0, len(seq), n):
            chunk = []
            for c in seq[i:i + n]:
                f = letters[c["case"]][p]
                forge, model = plain(c["kind"], c["forge"]), plain(c["kind"], c["model"])
                chunk.append(dict(c, A=forge if f == "A" else model, B=model if f == "A" else forge))
            (out / "sheets" / ("pass%s-%02d.txt" % (p, i // n + 1))).write_text(sheet(chunk, ref))
    print("%d cases, %d sheets a pass, %d card entries known" % (len(cases), -(-len(cases) // n), len(ref)))


if __name__ == "__main__":
    main()
