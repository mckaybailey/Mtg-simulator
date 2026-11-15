# AI pilot project: where it stands

Handoff note for the next agent. Rewritten 2026-11-15 on branch `claude/ai-decision-engine`. The
goal of the project: make mtgsim's Forge AI play more like real players, so simulated meta win
rates track real ones. Numbers and methods are in `VALIDATION.md`; this note says what is done,
what was learned and what to do next.

## Branch state

- All work is on `claude/ai-decision-engine`, pushed. It contains `main` as of 56151e6. **It has
  not been merged into `main` and no pull request exists**: the sessions that did this work were
  only allowed to push this branch. Ask the user before merging or opening a PR.
- `runs/` is git-ignored and does not survive the cloud container; every run below can be
  replayed from its command and seed.
- The cloud environment "Mtg-simulator" now allows `magic.gg` and `mtgdecks.net`. magic.gg works
  with `curl`; mtgdecks.net answers automated requests with a Cloudflare 403.

## Done

| Item | Where | Result |
|---|---|---|
| Misplay report | `mtgsim/misplay.py`, `misplays RUN_DIR`, report section | games unchanged by the tracking; ranked every later-fixed dead card at the top of its deck |
| Forge patch mechanism | `mtgsim/forge.py`, `mtgsim/forge_patches/README.md` | `setup --build` applies, records and rebuilds as designed |
| Patches 0001–0008 | `mtgsim/forge_patches/` | Azorius Control +25.4 points (CI +21.3 to +29.4), Azorius Momo +9.3 (+4.9 to +13.6), Dimir Uldaros +3.8 (not reliable) |
| Patches 0009–0011 | same | Nova Hellkite and Chainsaw are now cast, no win-rate change (+1.5 and −0.1, both inside noise); the Ba Sing Se fix gives Mono-Green Landfall +20.3 (+16.0 to +24.5) |
| The other flagged cards read | `VALIDATION.md`, "More card fixes…" | Pinnacle Starcage, Day of Judgment, Torch the Tower, Seam Rip: the AI's rule is sensible, no patch |
| Why creature decks win | same section, `tools/log_analysis/` | no blocking, removal or card-script flaw; results turn on how much removal the opponent draws, in game one without sideboards |
| Source check | `decks/standard/meta/README.md` | real win rates, shares and the aggregate lists match the Magic.gg article; Four-Color Control added as a twelfth deck |
| Recalibration | `decks/standard/meta/gauntlet.json`, its README | twelve decks, eleven patches (`matrix decks/standard/meta -n 30 --seed 1`, 1,980 games): rank correlation 0.23 (noise 0.08–0.36), mean gap 11.4 points; on the eleven shared decks no change beyond noise from the eight-patch run |
| Tuning harness | `mtgsim/tune.py`, `mtgsim/profiles/spaces/default.json` | works; the full meta search found no profile beating Default beyond noise, none shipped |
| Design note | `docs/stronger-ai.md` | recommends a deterministic Flat Monte Carlo (`--mc fixed`) as first prototype |
| `--mc fixed` prototype | Forge patch 0020, `mtgsim/bridge/ForgeBridge.java`, `--mc fixed` / `ai_mc: fixed`, `tools/mc_cost.py` | replays from the seed (40 of 40 games across worker counts), games without Monte Carlo unchanged, mirror 50.0%; one searching seat costs about 9 times the default AI. Azorius Control vs Boros Dwarves: 32.0% against 26.0% with the default pilot, +6.0 points (−2.9 to +14.8), not reliable at 200 games per arm |

Tests: 284 (277 unit, 7 integration), all passing on the patched engine.

## What was learned

- Fixing what the AI cannot do raises the affected deck a lot (Azorius Control +25, Landfall +20)
  but does not make the ranking more real. Landfall went from 4 points under its real win rate to
  14 over: a creature deck the AI pilots properly is a creature deck the simulation overrates.
  Overrated now: Boros Dragons (+18.9), Boros Dwarves (+18.6), Mono-Green Landfall (+13.6), Orzhov
  Lifegain (+12.5). Underrated: Jund Sacrifice (−19.4), Dimir Uldaros (−17.4), Izzet
  Spellementals (−13.4), Four-Color Control (−10.3).
- The opposing AI does not misblock or waste removal against Dwarves and Dragons. Dwarves win 72%
  of games in which at most one removal spell is aimed at them and 45% with three or more. The
  best-supported explanation for their excess is the format: game one, no sideboards. A 70%
  game-one rate and 40% after sideboarding is a 50% match win rate. This is a hypothesis; it has
  not been tested.
- A mana sink activated before spells is invisible to the misplay report (nothing is "castable"
  at cleanup). Ba Sing Se was found by comparing a deck's games with and without one of its own
  cards on the battlefield; that comparison is worth running for every deck.
- AI profile settings move no deck by more than 4 points. Do not repeat the profile search on the
  default space.
- Twelve real win rates cannot validate a calibration: the rank correlation's noise range from
  the games alone is 0.08–0.36, and from the choice of decks far wider. About 94 decks would be
  needed for ±0.2. The Magic.gg table has six more archetypes with win rates but no lists.
- `real-matchups-unverified.json` is still unverified (mtgdecks.net refuses automated requests).
  Do not feed it to `tune --matchups`.

## Next steps, in order of expected value

1. **Test the sideboard explanation.** Build post-board lists by hand for Boros Dwarves and its
   five or six most-played opponents (their own 15 cards), run `match` at 200+ games per pairing
   with main decks and with post-board lists (seed 1), and put the two rates into
   p2·(2·p1 + p2 − 2·p1·p2). If post-board Dwarves fall towards 40–45%, most of the gap is the
   format and the honest fix is a best-of-three mode with sideboard plans, not an AI change.
   Check first that the AI casts the sweepers it is given (Day of Judgment sat castable in 43% of
   Azorius Control's games).
2. **Look for more mana sinks and wrong-phase activations** in the underrated decks: for each
   deck, compare play rates of its spells in games with and without each of its permanents that
   has an activated ability (the Ba Sing Se method), and read `logs/games/` where they differ.
3. **Find out whether `--mc fixed` helps.** It is reproducible now, so it can be A/B tested:
   Azorius Control with `ai_mc: fixed` against the default-piloted field needs about 1,000 games
   per arm to tell 6 points from zero (roughly 3 hours for the fixed arm on 4 cores), then the
   same for Jund Sacrifice and Dimir Uldaros. Only if the weak decks gain is a round robin with
   `fixed` for them worth its 10+ hours. The search can still loop on a play that cannot be put
   on the stack; the per-turn budget of 100 rollouts bounds that, it does not fix it.
4. **Smaller AI leads from the logs** (each a Forge patch, measured as in
   `mtgsim/forge_patches/README.md`): the AI targets creatures with ward without keeping mana to
   pay (21 of 119 spells lost to Lavaspur Boots); `ComputerUtil.predictNextCombat` ignores
   equipment that is on the battlefield but not attached, so the AI attacks into a lethal
   re-equip; instant-speed removal is cast in the AI's own upkeep instead of in response to an
   equip; 20- to 22-land decks mulligan in 51–63% of games (`simulation/OpeningHand.java`).
5. **Verify the matchup data** by hand in a browser, and gather lists for the six extra
   archetypes (melee.gg links are in the Magic.gg article).
6. Merge into `main` or open a PR when the user asks.

## Practical notes

- `--mc fixed` games take 20–45 s each and have a 1,800 s time limit; a timed-out game is not a
  replay.
- Run one engine job at a time (4 cores). A 1,980-game round robin takes about 30 minutes; a
  1,000-game gauntlet arm about 15.
- Pass an absolute `--out` or rely on the default; `--save-logs` now resolves the path itself.
- `--resume RUN_DIR` needs the original positional arguments again.
- Java patches are developed in a private `MTGSIM_HOME` (see the patches README); after pulling a
  new Java patch, `setup --build` rebuilds the shared Forge (about 2 minutes).
- If `gauntlet.json` `ai_*` fields change, re-run the round robin and update the calibration
  (`tools/update_calibration.py`, the meta README table, `VALIDATION.md`).
- Delete this file once the branch is merged and the next steps have moved elsewhere.
