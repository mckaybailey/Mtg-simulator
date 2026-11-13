#!/bin/bash
# Measure Forge patches 0001 (EmpowerAi) and 0002 (Jace's Machinations AtOppEOT) for Azorius Control.
# Arms: no patches, 0001 only, 0001+0002; then an Azorius Control mirror on the patched engine.
# Runs on a private copy of the Forge checkout so other runs on ~/.mtgsim/forge are unaffected,
# and takes the shared engine lock around every engine command. About 45 minutes on 4 cores.
# Usage (from the repository root): SP=<scratch dir> wip/tools/fix-arms.sh
set -ex
SP=${SP:?set SP to a scratch directory}
LOCK=${LOCK:-$SP/engine.lock}
export MTGSIM_HOME=$SP/fixhome
M=decks/standard/meta
P=mtgsim/forge_patches
OPP=$(ls $M/*.txt | grep -v azorius-control.txt)
run() { flock $LOCK python3 -m mtgsim gauntlet $M/azorius-control.txt --vs $OPP -n 100 --seed 1 --out runs/$1; }

if [ ! -d $MTGSIM_HOME/forge ]; then
  mkdir -p $MTGSIM_HOME
  cp -a ~/.mtgsim/forge $MTGSIM_HOME/forge
  printf '{\n  "forge_dir": "%s/forge"\n}\n' $MTGSIM_HOME > $MTGSIM_HOME/config.json
fi
rm -f $P/0001-empower-ai.patch $P/0002-jaces-machinations-eot.patch
flock $LOCK python3 -m mtgsim setup --build
run fix-arm0
cp $P/pending/0001-empower-ai.patch $P/
flock $LOCK python3 -m mtgsim setup --build && flock $LOCK python3 -m mtgsim doctor
run fix-arm1
cp $P/pending/0002-jaces-machinations-eot.patch $P/
flock $LOCK python3 -m mtgsim setup --build && flock $LOCK python3 -m mtgsim doctor
run fix-arm2
flock $LOCK python3 -m mtgsim match $M/azorius-control.txt $M/azorius-control.txt -n 200 --seed 1 --out runs/fix-mirror-ac
python3 wip/tools/arms.py azorius-control runs/fix-arm0 runs/fix-arm1 runs/fix-arm2 \
  --cards "Countersculpt,Jace's Machinations,Theorist's Sanctum"
echo ALLDONE
