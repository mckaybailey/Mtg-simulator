"""Probe step C: pull the blind answers out of the answerers' transcripts and check what each one read.

Each answerer is a Claude subagent given `answer_prompt.txt` with the path of one batch file. Its
transcript (one JSON object per line) is read for (1) every tool call it made, which must be
Reads of its own batch file only (plus the hand-back of its answer), and (2) its hand-back or last message, which must hold a JSON array of
{"case", "choice", "reason"}. Answers are written as OUT/answers.jsonl with the batch number; a
transcript that breaks either rule is reported and its answers are still written, flagged.

Usage: python3 tools/probe/extract_answers.py --out probe/round2 TRANSCRIPT.jsonl ...
"""

import argparse
import json
import re
import sys
from pathlib import Path


def messages(path):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def content_of(m):
    msg = m.get("message", m)
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []


def read_transcript(path):
    tools, texts = [], []
    for m in messages(path):
        role = m.get("type") or m.get("message", {}).get("role")
        if role != "assistant":
            continue
        for part in content_of(m):
            if part.get("type") == "tool_use":
                tools.append((part.get("name"), part.get("input", {})))
            elif part.get("type") == "text":
                texts.append(part["text"])
    return tools, texts


def answers_from(texts, tools):
    for name, inp in reversed(tools):  # an answer handed back through the subagent hand-back tool
        if name == "SubagentHandback":
            texts = texts + [inp.get("message", "")]
            break
    for text in reversed(texts):
        m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)
        if m:
            return json.loads(m.group(0))
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("transcripts", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows, problems = {}, []
    for t in args.transcripts:
        tools, texts = read_transcript(t)
        reads = [i.get("file_path", "") for n, i in tools if n == "Read"]
        batch = None
        if reads:
            m = re.search(r"batch-(\d+)\.txt$", reads[0])
            batch = int(m.group(1)) if m else None
        others = [n for n, i in tools if n not in ("Read", "SubagentHandback")]
        clean = bool(reads) and len(set(reads)) == 1 and not others and batch is not None
        if not clean:
            problems.append("%s: reads %s, other tools %s" % (t, sorted(set(reads)), others))
        got = answers_from(texts, tools)
        if got is None:
            problems.append("%s: no JSON answer array" % t)
            continue
        for a in got:
            row = {"case": a["case"], "choice": a["choice"], "reason": a.get("reason", ""), "batch": batch}
            if not clean:
                row["note"] = "transcript did not read only its own batch file"
            rows[a["case"]] = row
    out = Path(args.out) / "answers.jsonl"
    with open(out, "w") as fh:
        for case in sorted(rows):
            fh.write(json.dumps(rows[case], ensure_ascii=False) + "\n")
    print("%d answers from %d transcripts -> %s" % (len(rows), len(args.transcripts), out))
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)


if __name__ == "__main__":
    main()
