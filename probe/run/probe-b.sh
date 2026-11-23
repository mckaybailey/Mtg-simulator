#!/bin/bash
cd /home/user/Mtg-simulator
M=decks/standard/meta
VS="$M/boros-dwarves.txt $M/boros-dragons.txt $M/mono-green-landfall.txt $M/mono-black-aggro.txt $M/orzhov-lifegain.txt $M/rakdos-lizards.txt"
for d in azorius-control four-color-control izzet-spellementals dimir-midrange jund-sacrifice dimir-uldaros dimir-excruciator; do
  out=runs/probe-b/$d
  if [ -f "$out/report.html" ]; then continue; fi
  if [ -d "$out" ]; then
    python3 -m mtgsim gauntlet $M/$d.txt --vs $VS -n 10 --seed 1 --snapshots --resume "$out"
  else
    python3 -m mtgsim gauntlet $M/$d.txt --vs $VS -n 10 --seed 1 --snapshots --out "$out"
  fi
done
echo ALLDONE
