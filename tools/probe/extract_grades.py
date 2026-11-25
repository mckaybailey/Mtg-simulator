"""Probe step D: pull the judges' grades out of their transcripts and check what each one read.

Each judge is a Claude subagent given `grade_prompt.txt` with the path of one grading sheet. Its
transcript must show Reads of that sheet only (plus the hand-back of its grades); its grades are
written to OUT/judgements/<sheet>.json. A transcript that breaks the rule is reported.

Usage: python3 tools/probe/extract_grades.py --out probe/round3/grading TRANSCRIPT.jsonl ...
"""
import argparse
import json
import re
from pathlib import Path

from extract_answers import answers_from, read_transcript


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("transcripts", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out) / "judgements"
    out.mkdir(parents=True, exist_ok=True)
    for t in args.transcripts:
        tools, texts = read_transcript(t)
        reads = sorted({i.get("file_path", "") for n, i in tools if n == "Read"})
        m = re.search(r"(pass\d-\d+)\.txt$", reads[0]) if len(reads) == 1 else None
        if not m:
            continue  # not a judge
        sheet = m.group(1)
        others = [n for n, i in tools if n not in ("Read", "SubagentHandback")]
        grades = answers_from(texts, tools)
        want = re.findall(r"^=== CASE (C\d+)", (Path(args.out) / "sheets" / (sheet + ".txt")).read_text(), re.M)
        got = [g["case"] for g in grades or []]
        problems = []
        if others:
            problems.append("other tools %s" % others)
        if got != want:
            problems.append("cases %s, sheet has %s" % (got, want))
        if grades:
            (out / (sheet + ".json")).write_text(json.dumps(grades, indent=0, ensure_ascii=False) + "\n")
        print(sheet, "ok" if not problems else "; ".join(problems))


if __name__ == "__main__":
    main()
