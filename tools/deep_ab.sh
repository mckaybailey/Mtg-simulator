#!/bin/bash
# One-seat A/B of the Monte Carlo pilots for one hero deck against the default-piloted meta field:
# default, --mc fixed and --mc deep on the hero's seat only, same seeds. Resumes each arm on restart.
# usage: tools/deep_ab.sh HERO_FILE GAMES OUT_DIR   (hero dirs OUT_DIR/hero-ARM/ with gauntlet.json made beforehand)
cd "$(dirname "$0")/.." || exit 1
hero=$1; n=$2; out=$3
for arm in default fixed deep; do
  run=$out/$arm
  if [ -f "$run/summary.json" ]; then echo "$arm done"; continue; fi
  if [ -f "$run/run.json" ]; then extra=(--resume "$run"); else extra=(); fi
  echo "$(date -u +%FT%TZ) start $arm"
  python3 -m mtgsim gauntlet "$out/hero-$arm/$hero" --vs decks/standard/meta -n "$n" --seed 1 -j 4 --out "$run" "${extra[@]}"
  echo "$(date -u +%FT%TZ) end $arm status $?"
done
echo DONE
