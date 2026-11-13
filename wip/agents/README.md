# Subagent work in progress (paused 2026-11-13)

Each subagent worked in its own git worktree, which only existed in the container. Their WIP
commits are saved here as `git format-patch` files; the commit messages carry each agent's full
status, findings and next steps. Apply one on a scratch branch with `git am <file>`.

| File | Base commit | What it is | State |
|---|---|---|---|
| `misplay-report.patch` | f8d0f28 | Misplay report: 7 new per-player driver fields (`endHand`, `endHandLands`, `idleOwn`, `idleOpp`, `counter`, `removal`, `roles`; definitions in its `mtgsim/bridge/AGENTS.md`), `mtgsim/misplay.py`, `misplays RUN_DIR` command, `misplays` summary key and report section, `tests/test_misplay.py` | Builds; 206 unit tests pass. First tracker version left 60 of 60 games unchanged; the refined tracker still needs the same check (`misplay-baseline/` has the 60 original-driver games and `compare.py`). Then README/VALIDATION entries and report screenshots. |
| `tuning-harness.patch` | f8d0f28 | Per-run AI profile folder (`RUN_DIR/ai/`, `-Dmtgsim.aiProfileDir`), `mtgsim/profiles/`, `python3 -m mtgsim tune` (`mtgsim/tune.py`: per-archetype-group profiles, 21-setting search space, holdout + leave-one-out, noise ranges, successive halving, game cache, resume/import) | Complete; full suite 235 tests pass under the engine lock. Smoke run verified profiles reach the engine and the cache. Real experiment not started (command and ~2.5 h estimate in its commit message). |
| `dead-cards.patch` | 82cf96f | Investigation of Momo/Uldaros cards the AI never casts; draft `forge_patches/pending/0003-springleaf-drum-ai-playable.patch` | Nothing measured. Springleaf Drum: `AI:RemoveDeck:All` filters it out in `AiController` before play decisions. Pixie, Theorix, Cryomancer: probably an ETB trigger the AI rejects (hypothesis). Practiced Offense not looked at. |

## Merge notes

- `misplay-report.patch` and `tuning-harness.patch` both edit `mtgsim/bridge/ForgeBridge.java`
  (Tracker/result JSON vs `main()`/`createAi`/profile loading), `mtgsim/cli.py` (new commands)
  and docs; expect small conflicts in the import block and docs. The tuning harness also edits
  `mtgsim/forge.py`, `experiment.py` and `runner.py`, which the patch mechanism (already merged)
  touched too.
- The tuning harness's game cache is keyed on everything that decides a game; when the misplay
  tracker is merged, only bump `tune.CACHE_VERSION` if the unchanged-games check fails.
- Forge treats a deck whose name contains "Control" (or average mana value above 3) as a
  non-aggro deck, so deck names change play (found by the tuning agent).
