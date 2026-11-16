#!/bin/bash
# Each meta deck against the 13 'Other' decks, best-of-one, 30 games per pairing, seed 1. Re-run to continue.
cd "$(dirname "$0")/.."
for f in decks/standard/meta/*.txt; do
  h=$(basename $f .txt); out=$PWD/runs/field/$h
  [ -f $out/summary.json ] && continue
  if [ -f $out/run.json ]; then r="--resume $out"; else r="--out $out"; fi
  echo "=== $h"
  python3 -m mtgsim gauntlet $f --vs decks/standard/fracture-2026-field -n 30 --seed 1 $r || echo "FAILED $h"
done
echo "ALL DONE"
