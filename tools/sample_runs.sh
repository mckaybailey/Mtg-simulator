#!/bin/bash
# Each meta deck against the 100-list random sample of the field (decks/standard/fracture-2026-sample),
# best-of-three with Forge's sideboarding, N matches per pairing (default 6), seed 1, into runs/sample/<deck>.
# Skips finished decks and resumes a half-done one, so run it again after a restart.
cd "$(dirname "$0")/.."
N=${N:-6}
for f in decks/standard/meta/*.txt; do
  h=$(basename $f .txt); out=$PWD/runs/sample/$h
  [ -f $out/summary.json ] && continue
  if [ -f $out/run.json ]; then r="--resume $out"; else r="--out $out"; fi
  echo "=== $h"
  python3 -m mtgsim gauntlet $f --vs decks/standard/fracture-2026-sample -n $N --seed 1 --bo3 $r || echo "FAILED $h"
done
echo "ALL DONE"
