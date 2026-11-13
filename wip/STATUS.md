# Work in progress: making the AI pilot play more like people (paused 2026-11-13)

This folder holds unfinished work from the `claude/ai-decision-engine` session so it survives the
container being reclaimed. Delete `wip/` once everything in it is integrated.

## Done and merged on this branch

- `docs/stronger-ai.md`: design note comparing a search-based player, a learned player and LLM
  decisions (recommends a deterministic, rollout-counted Flat Monte Carlo as the first prototype).
- Forge patch mechanism (`mtgsim/forge_patches/`, applied by `setup --build`, recorded in
  `run.json`; verified on a fresh build; see `VALIDATION.md`). No patch ships yet.

## Baseline, re-run in this environment

`python3 -m mtgsim matrix decks/standard/meta -n 30 --seed 1` (1,650 games, 0 timeouts/errors)
reproduced the numbers in `VALIDATION.md` exactly. Against `real_win_rate`:
Spearman 0.236 (game-noise range 0.12–0.35, parametric bootstrap, 1,000 resamples),
Pearson 0.228 (0.14–0.32), mean absolute gap 13.0 points (11.8–14.5). Tools: `wip/tools/calib.py`.

## Finding: cards the AI holds but never casts (baseline round robin)

| Deck | Card | Games seen | Games cast | Cause |
|---|---|---|---|---|
| Azorius Control | Countersculpt | 259 | 0 | `ApiType.Empower` has no AI → `CannotPlayAi` refuses any spell with an Empower rider |
| Azorius Control | Jace's Machinations | 228 | 0 | same, plus `EffectAi` refuses Effect spells without `AILogic` |
| Azorius Momo | Practiced Offense | 184 | 0 | not yet investigated |
| Azorius Momo | Springleaf Drum | 230 | 0 | script has `AI:RemoveDeck:All` |
| Azorius Momo | Nurturing Pixie | 165 | 5 | not yet investigated |
| Dimir Uldaros | Uldaros Theorix | 188 | 3 | not yet investigated |
| Dimir Uldaros | Seasoned Cryomancer | 209 | 7 | not yet investigated |

Theorist's Sanctum (Azorius Control) and Vraska's Final Mercy (Dimir Uldaros) also use Empower.

Draft patches, **not yet measured, so parked in `mtgsim/forge_patches/pending/`** (setup does not
apply files in that subfolder):
- `0001-empower-ai.patch`: new `forge.ai.ability.EmpowerAi` (rider always accepted; stand-alone
  Empower used at the opponent's end step), mapped in `SpellApiToAi`. Compiles against the jar.
- `0002-jaces-machinations-eot.patch`: `AILogic$ AtOppEOT` on Jace's Machinations.

To measure them: `SP=<scratch dir> wip/tools/fix-arms.sh` (three arms of Azorius Control vs the
other ten decks, 100 games each, seed 1, plus a 200-game mirror; ~45 min), then fill each
patch's `Measured:` line from `wip/tools/arms.py` output and move the patches up into
`mtgsim/forge_patches/`.

## Unverified real matchup data

`wip/real-matchups.json` (built by `wip/tools/build_real_matchups.py`): 58 matchup rows, 37
unambiguous numbers covering 26 of the 55 pairings, gathered from web-search summaries only (the
network blocks MTG sites, so no page could be opened and checked). Mostly mtgdecks.net archetype
pages; window, platform and Bo1/Bo3 unknown. Use only as a secondary check, never as tuning data
until verified. Baseline vs these rows (`wip/tools/matchcheck.py`): 24 pairings, Pearson 0.20,
Spearman 0.11, mean absolute gap 19.3 points.

## Subagent work in progress

See `wip/agents/README.md` for each agent's WIP commit (saved as a patch; apply with `git am`)
and status: misplay report (built, needs the final unchanged-games check), tuning harness
(complete, experiment not started), dead-card investigation (one cause found, nothing measured).

## Resume order

1. `python3 -m mtgsim doctor` (Forge is rebuilt by the environment setup script).
2. Integrate the misplay report (agent A WIP), then re-run the round robin with the new driver and
   check games are identical to the baseline; run `misplays` on it.
3. Measure patches 0001/0002 (above); finish the dead-card investigation (agent B WIP).
4. Integrate the tuning harness (agent C WIP), run the real tuning experiment.
5. `main` (56151e6, the other session's results) is already merged: per-deck Cautious/Hardest
   profiles and Monte Carlo do not fix the ranking (best rank corr 0.25; `ai_mc: max` for the
   three weak decks cuts the mean gap to 9.1 but costs 3x and reproducibility), and
   `gauntlet.json`'s ai_* fields stay unset. Note: Monte Carlo lifted Azorius Control from 20% to
   46%, plausibly because it also tries plays the heuristics refuse, such as the Empower cards;
   compare that with patch 0001's effect. Final step: re-run the round robin with this branch's
   patches (and any shipped tuned profile), update calibration fields and docs, push.
