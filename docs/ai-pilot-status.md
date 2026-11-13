# AI pilot project: where it stands

Handoff note for the next agent. Written 2026-11-13 at commit f587046 on branch
`claude/ai-decision-engine`. The goal of the project: make mtgsim's Forge AI play more like real
players, so simulated meta win rates track real ones. Numbers and methods are in `VALIDATION.md`;
this note says what is done, what was learned and what to do next.

## Branch state

- All work is on `claude/ai-decision-engine`, pushed. It contains `main` as of 56151e6 (the other
  session's per-deck Cautious/Hardest/Monte Carlo experiment, which changed nothing in
  `gauntlet.json`). **It has not been merged into `main` and no pull request exists**: the session
  that did this work was only allowed to push this branch. Ask the user before merging or opening
  a PR.
- The working tree was clean. `runs/` is git-ignored and lived in a container that is gone; every
  run below can be replayed from its command and seed.

## Done

| Item | Where | Result |
|---|---|---|
| Misplay report | `mtgsim/misplay.py`, `misplays RUN_DIR`, report section | games unchanged by the tracking (1,650 of 1,650 identical); ranked every later-fixed card at the top of its deck |
| Forge patch mechanism | `mtgsim/forge.py`, `mtgsim/forge_patches/README.md` | `setup --build` applies, records and rebuilds as designed |
| Eight patches | `mtgsim/forge_patches/0001`–`0008` | Azorius Control +25.4 points (CI +21.3 to +29.4), Azorius Momo +9.3 (+4.9 to +13.6), Dimir Uldaros +3.8 (−0.3 to +7.9, not reliable); mirrors 50–54% |
| Recalibration | `decks/standard/meta/gauntlet.json`, its README | patched round robin (`matrix decks/standard/meta -n 30 --seed 1`): mean gap 13.0 → 10.8 points (clears noise), rank correlation 0.24 → 0.11 (within noise: ranking not improved) |
| Tuning harness | `mtgsim/tune.py`, `mtgsim/profiles/spaces/default.json` | works; the full meta search (16 candidates, 12,010 games) found no profile beating Default beyond noise, so none shipped and `ai_profile` is unset |
| Design note | `docs/stronger-ai.md` | recommends a deterministic, rollout-counted Flat Monte Carlo (`--mc fixed`) as first prototype; not built |
| Analysis scripts | `tools/` | reproduce the calibration and patch-comparison numbers |

Tests: 279 (273 unit, 6 integration), all passing on the patched engine.

## What was learned

- Fixing cards the AI never cast raises those decks a lot, but the ranking stays wrong: Boros
  Dwarves (+19.8) and Boros Dragons (+18.7) are still overrated, Jund Sacrifice (−19.9), Dimir
  Uldaros (−16.5) and Izzet Spellementals (−10.6) underrated.
- AI profile settings (counter chances, trading, aggression) move no deck by more than 4 points.
  Do not repeat the profile search on the default space; the gaps come from things no profile key
  controls.
- Eleven real win rates cannot validate a calibration: a rank correlation of 0.22 over 9 decks has
  an interval of −0.54 to +0.78. About 94 decks would be needed for ±0.2.
- Real deck-vs-deck data could not be verified: the network blocked every MTG site.
  `decks/standard/meta/real-matchups-unverified.json` holds search-summary numbers only; do not
  feed it to `tune --matchups` before verifying and de-duplicating it.

## Next steps, in order of expected value

1. **Read the AI logic for the other cards the misplay report flags** (hits per 100 games on the
   unpatched round robin): Pinnacle Starcage (Azorius Artifacts, 22), Nova Hellkite (Boros
   Dragons, 21), Torch the Tower (Jund Sacrifice, 17), Seam Rip (Azorius Control, 15). Re-run
   `misplays` on a fresh patched round robin first; the list changes once dead cards are cast.
   Each fix is a patch, measured as in `mtgsim/forge_patches/README.md` (deck vs the other ten,
   100 games each, seed 1, with and without; plus a mirror).
2. **Find out why the creature decks are overrated.** Nothing so far touches it. Look at how the
   opposing AI blocks and spends removal against Dwarves and Dragons (`--save-logs`).
3. **Build the `--mc fixed` prototype** from `docs/stronger-ai.md`.
4. **Verify the matchup data** from a network that reaches mtgdecks.net and similar, and gather
   more decks with real win rates.
5. Merge into `main` or open a PR when the user asks.

## Practical notes

- Run one engine job at a time (4 cores). A 1,650-game round robin takes about 20 minutes; a
  1,000-game gauntlet arm about 12.
- If the other session changes `gauntlet.json` `ai_*` fields, re-run the round robin with the
  combined settings and update the calibration (`tools/update_calibration.py`, the meta README
  table, `VALIDATION.md`).
- Delete this file once the branch is merged and the next steps have moved elsewhere.
