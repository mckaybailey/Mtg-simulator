# Forge patches

mtgsim's own changes to Forge: unified diffs against the pinned Forge commit
(`FORGE_PINNED_REF` in `mtgsim/forge.py`). `python3 -m mtgsim setup --build` applies every
`*.patch` file in this folder, in file-name order, after checking out that commit. A Forge you
supply with `setup --forge-dir` is never modified.

The folder ships empty apart from this README until a patch has been measured (see the last
section).

## What `setup --build` does with them

1. Tries the whole series on a scratch git index built from the pinned commit. If a patch does
   not apply on top of the ones before it, setup stops with an error naming it and changes
   nothing.
2. If the series differs from what the checkout carries (names or contents), restores every
   file touched by the old or the new series to the pinned commit (files a patch created are
   deleted) and applies the new series with `git apply`. An unchanged series is left alone,
   unless a patched file was edited by hand, in which case it is put back.
3. Records the result in `mtgsim-patches.json` in the root of the checkout: each patch's name,
   sha256 and the files it touches, a combined hash of the series, the expected content of
   every touched file, and what the Forge jar was built from.
4. Runs Maven (after emptying the modules' `target/` folders) only when the jar was not built
   from this commit with these code patches. A code patch is one that touches anything outside
   `forge-gui/res/`. Card scripts (`forge-gui/res/cardsfolder/`), AI profiles
   (`forge-gui/res/ai/*.ai`), formats and editions are read from disk when Forge starts, so a
   series that only changes those takes effect without a rebuild. Patches to `forge-ai/`,
   `forge-game/` and other Java code need one (about 2 minutes). Adding a code patch to a series
   that already has it compiled in (for example a new card-script patch next to an existing
   Java patch) needs no rebuild either.

The combined hash is part of `ForgeInstall.fingerprint()`, so a patched card script gives a new
card-database cache and a freshly compiled driver. Every run records the applied series in
`run.json` (and `summary.json`) under `forge.patches`. `doctor` prints the status, and commands
that play games warn on stderr when the installed series is not the one this folder holds.
`setup --build --no-patches` builds the pinned commit without any of them, for comparisons.

## File format

`NNNN-short-name.patch`: a four-digit number that fixes the order, then a short lowercase name.
The file starts with a description, then a blank line, then the output of `git diff`. `git apply`
skips everything above the first `diff --git` line.

```
Subject: Llanowar Elves: let the AI cast it before combat
Why: Forge's AI held Llanowar Elves until its second main phase, so it never attacked with
  the mana it could have made on turn two. Adds SVar:PlayMain1:TRUE.
Measured: `mtgsim match decks/standard/casual/green.txt decks/standard/casual/red.txt -n 400
  --seed 1`: 48.0% (43-53) before, 53.5% (49-58) after; 400 games each, Forge 7db198d72e.

diff --git a/forge-gui/res/cardsfolder/l/llanowar_elves.txt b/forge-gui/res/cardsfolder/l/llanowar_elves.txt
index 8898419..8c4e131 100644
--- a/forge-gui/res/cardsfolder/l/llanowar_elves.txt
+++ b/forge-gui/res/cardsfolder/l/llanowar_elves.txt
@@ -3,4 +3,5 @@ ManaCost:G
...
```

(The numbers above are made up to show the format.)

- `Subject:`, `Why:` and `Measured:` are required (`tests/test_forge_patches.py` checks every
  shipped patch). Indent continuation lines.
- No line of the description may start with `diff `, `--- `, `+++ ` or `@@`; `git apply` would
  read it as part of the diff.
- Paths are relative to the Forge checkout root with `a/` and `b/` prefixes, as plain `git diff`
  writes them.
- Patches are byte-exact (`.gitattributes` here turns off line-ending conversion), and the
  sha256 covers the description too, so editing the text re-applies the series (and rebuilds
  Forge if it is a code patch).
- Keep one concern per patch. A file should belong to one patch: `git diff` in a patched
  checkout shows a file's changes from every patch, so a second patch made that way would
  repeat the first one's hunks and fail to apply. To change a file an earlier patch already
  touches, edit that patch instead.

## Making a patch

Do not edit the shared checkout at `~/.mtgsim/forge` while games are running on it: Forge reads
card scripts whenever a worker starts.

**A card script or AI profile change, without touching any checkout.** Take the file as it is at
the pinned commit, edit a copy, and diff the two:

```
F=~/.mtgsim/forge
P=forge-gui/res/cardsfolder/l/llanowar_elves.txt
W=$(mktemp -d); mkdir -p "$W/a/$(dirname $P)" "$W/b/$(dirname $P)"
git -C "$F" show HEAD:$P > "$W/a/$P"; cp "$W/a/$P" "$W/b/$P"
$EDITOR "$W/b/$P"
$EDITOR mtgsim/forge_patches/0001-llanowar-elves-main-one.patch   # the description, then a blank line
(cd "$W" && git diff --no-index --no-prefix a/$P b/$P) >> mtgsim/forge_patches/0001-llanowar-elves-main-one.patch
```

(`git diff --no-index` exits with status 1 when the files differ; that is expected.)

**Anything else, including Java.** Work in a private build so other runs are not affected:

```
export MTGSIM_HOME=/tmp/mtgsim-patching          # private config, Forge build and caches
python3 -m mtgsim setup --build                  # ~2 minutes
cd $MTGSIM_HOME/forge
$EDITOR forge-ai/src/main/java/forge/ai/...      # edit in place
git add -N path/of/any/new/file                  # so git diff includes new files
git diff -- forge-ai/src/main/java/forge/ai/... >> /path/to/mtgsim/forge_patches/0002-....patch
```

Then `python3 -m mtgsim setup --build` (same `MTGSIM_HOME`) puts the checkout back to the pinned
commit, applies the new series and rebuilds if the series has code changes. If the patch does not
apply, the error names it. `git -C $MTGSIM_HOME/forge diff --stat` shows what the checkout
carries now.

## Measuring a patch

Every patch must be measured before it is committed, and its `Measured:` field says how. Play the
same command with the same seed on an install without the patch and on one with it, enough games
that the difference can show (100 games pin a win rate to about ±10 points; see `AGENTS.md`),
for example:

```
python3 -m mtgsim match DECK OPPONENT -n 400 --seed 1 --out runs/before   # without the patch
# add the patch file, then: python3 -m mtgsim setup --build
python3 -m mtgsim match DECK OPPONENT -n 400 --seed 1 --out runs/after
```

Each run's `run.json` names the patch series it was played with (`forge.patches`). A patch whose
effect stays inside the noise is still recorded with its numbers, and the description says what
it fixes in the AI's play (a game log from `--save-logs` showing the misplay is the best
evidence).
