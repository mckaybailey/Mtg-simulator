# Resume notes: making mtgsim's AI pilot play more like people

State as of 2026-11-13 19:45 UTC, branch `claude/ai-decision-engine` (pushed). The brief is the
original task: items 1–4 (misplay report, card-hint fixes via Forge patches, profile tuning, design
note), measured against a baseline re-run here, merged with the other session's `main`, finished
with a summary for the user. Delete `wip/` once everything below is integrated.

Paths: repo `/home/user/Mtg-simulator`; scratchpad
`SP=/tmp/claude-0/-home-user-Mtg-simulator/ac175026-a9a0-5278-9b10-d7c0563130a0/scratchpad`.
**Every engine command runs as `flock $SP/engine.lock <cmd>`** (4 cores, one job at a time).
Agent handles for resuming subagents are in `$SP/RESUME-agents.txt` (not in the repo).

## Merged and pushed

| Item | What | Commit |
|---|---|---|
| 4 | `docs/stronger-ai.md` design note (recommends a deterministic, rollout-counted Flat Monte Carlo as the first prototype; API facts checked) | 930ecb0 |
| 2 | Forge patch mechanism: `mtgsim/forge_patches/*.patch` applied by `setup --build`, recorded in `run.json` `forge.patches`; fresh build verified | 350169f |
| – | `main` 56151e6 (other session): per-deck Cautious/Hardest/MC settings do not fix the ranking; gauntlet.json ai_* fields stay unset | 7fec8a1 |
| 3 | Tuning harness: per-run profile folder `RUN_DIR/ai/` (`-Dmtgsim.aiProfileDir`), `mtgsim/profiles/`, `python3 -m mtgsim tune` (holdout, LOO CV, noise ranges, successive halving, cache keyed on engine + patch set) | 3dd3ed9 |
| 1 | Misplay report: 7 new per-player driver fields, `mtgsim/misplay.py`, `misplays RUN_DIR`, report section; 60/60 games unchanged vs original driver | 8a9d3f7 |

Tests on the merged tree: 279 (273 unit, 6 integration); unit tests pass
(`MTGSIM_HOME=$(mktemp -d) python3 -m unittest discover -s tests`). The full suite with
integration tests has not been run on the merged tree yet — run it under the lock.
`wip/agents/misplay-report.patch` and `tuning-harness.patch` are now obsolete (merged); delete them.

## Baseline (re-run here, identical to VALIDATION.md)

`matrix decks/standard/meta -n 30 --seed 1` → `runs/baseline-rr-n30-s1` (1,650 games):
Spearman 0.236 (noise 0.12–0.35), Pearson 0.228 (0.14–0.32), mean abs gap 13.0 (11.8–14.5).
Tool: `python3 wip/tools/calib.py RUN_DIR`. Vs the unverified matchup data
(`wip/tools/matchcheck.py RUN_DIR wip/real-matchups.json`): 24 pairings, Pearson 0.20, Spearman 0.11.

## Running now (started ~19:40 UTC; all resume from recorded games if killed)

1. **Measurement of patches 0001/0002** — `SP=$SP wip/tools/fix-arms.sh`, log
   `$SP/fix-arms.log`. Azorius Control vs the other 10 meta decks, 100 games each, seed 1, on a
   private Forge copy (`$SP/fixhome`): arm0 no patches (DONE), arm1 = 0001 (in progress, ~300/1000),
   arm2 = 0001+0002, then a 200-game AC mirror. Results: `runs/fix-arm{0,1,2}`, `runs/fix-mirror-ac`.
   **arm0: 22.4% (20–25), 224–776; Countersculpt seen 865 / cast 0; Jace's Machinations seen 791 /
   cast 0; No More Lies seen 764 / cast 524.** Compare: `python3 wip/tools/arms.py azorius-control
   runs/fix-arm0 runs/fix-arm1 runs/fix-arm2 --cards "Countersculpt,Jace's Machinations,No More Lies"`.
   While it runs, the script copies 0001/0002 into `mtgsim/forge_patches/` (excluded locally in
   `.git/info/exclude`; the sources are in `forge_patches/pending/`). Don't commit those copies
   until measured.
2. **New-driver round robin on the unpatched shared Forge** (queued behind 1) —
   `matrix decks/standard/meta -n 30 --seed 1 --out runs/rr-newdriver-n30-s1`, log
   `$SP/rr-newdriver.log`. Purpose: (a) check all 1,650 games identical to the baseline with
   `python3 wip/agents/misplay-baseline/compare.py runs/baseline-rr-n30-s1 runs/rr-newdriver-n30-s1`;
   (b) full misplay report before any fix: `python3 -m mtgsim misplays runs/rr-newdriver-n30-s1`.
   (It warns that patches are "out of date" because of the temporary copies; the shared Forge
   really is unpatched, and run.json records that.)
3. **Dead-card subagent** (worktree `.claude/worktrees/agent-aa70316c921c8d2b6`, branch
   `worktree-agent-aa70316c921c8d2b6`, last commit dc94741). Patches 0003–0008 in its
   `mtgsim/forge_patches/pending/`; its runs `runs/dc-*` in that worktree look complete (before/after
   1,000 games each for Azorius Momo and Dimir Uldaros, mirrors 200 each, 0008 extra arm). Causes:
   0003 Springleaf Drum (`AI:RemoveDeck:All` filtered by default AI), 0004 Practiced Offense
   (forge-ai ignores KWChoice → Pump refused; `AILogic$ ContinuousBonus`), 0005 Nurturing Pixie and
   0006 Uldaros Theorix (ETB refused by checkETBEffects; `OptionalDecider$ You`), 0007 Seasoned
   Cryomancer (`AILogic$ Always` on the ImmediateTrigger), 0008 (pump KWChoice lost target; new).
   Expect its report; then merge its branch and take its Measured: numbers.

## Next steps, in order

1. When arm1/arm2/mirror finish: fill `Measured:` in `pending/0001`, `0002` from arms.py output
   (win rate + interval per arm, paired diff, cast counts, mirror result); judge whether each patch
   clears noise (report negative results honestly).
2. Merge the dead-card branch; review patches 0003–0008 and their numbers.
3. Promote measured patches from `pending/` to `mtgsim/forge_patches/` (remove the
   `.git/info/exclude` lines first), commit, then install into the shared Forge:
   `flock $SP/engine.lock python3 -m mtgsim setup --build` (Java patch 0001 → Maven rebuild ~1–2 min),
   then `doctor`.
4. Patched round robin: `matrix decks/standard/meta -n 30 --seed 1 --out runs/rr-patched-n30-s1`
   (~20 min) → `calib.py` metrics, `misplays` after the fixes, matchcheck. Compare with baseline.
5. Tuning on the patched engine (pilot, ~75 min with the import; `--dry-run` first):
   `setsid nohup flock $SP/engine.lock python3 -m mtgsim tune --holdout "Dimir Uldaros" "Boros Dragons" --tune reactive --profiles 6 --rounds 10,20 --confirm 20 --import runs/rr-patched-n30-s1 --out runs/tune-pilot-s1 > runs/tune-pilot-s1.log 2>&1 &`
   (full search: drop `--tune/--profiles/--rounds/--confirm`, ~2.5 h). Ship a profile into
   `mtgsim/profiles/` + `ai_profile` in gauntlet.json only if it beats baseline beyond noise on
   training AND held-out decks; then re-run the round robin with that setting.
6. Update `decks/standard/meta/gauntlet.json` `sim_win_rate`/`ai_pilot` and the calibration
   string, `decks/standard/meta/README.md` table, `VALIDATION.md` (patches, misplay findings,
   tuning result, final metrics), README/AGENTS as needed; full test suite under the lock.
7. Optional, if time: `--mc fixed` prototype from `docs/stronger-ai.md` (not started).
8. Delete `wip/`, merge latest `main` again (`git fetch origin main`), push; final summary for the
   user: what was built, each measurement with intervals, what didn't work, next steps.
