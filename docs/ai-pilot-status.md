# AI pilot project: where it stands

Handoff note for the next agent. Rewritten 2026-11-15 on branch `claude/ai-decision-engine`. The
goal of the project: make mtgsim's Forge AI play more like real players, so simulated meta win
rates track real ones. Numbers and methods are in `VALIDATION.md`; this note says what is done,
what was learned and what to do next.

## CHECKPOINT 16 Nov 2026: best-of-three with sideboards, in progress (plan revised)

**Read this section first; it is where the last session stopped.**

**The goal (stated by the user, 16 Nov 2026): the simulations must give reasonable win rates, ones
that look like the real ones.** Judge every run by the spread (SD) and the mean gap of the 18 meta
decks against their real win rates, plus the rank correlation with its noise range. Real: SD 4.0
points (12 decks). Simulated now: SD 13.3, mean gap 11.4.

**Plan revised 16 Nov 2026 (later the same day): best-of-three first, and a small field instead of
100 decks.** The earlier plan added about 100 decks to test whether the small, closed field forces a
zero-sum game that pushes win rates apart. `tools/field_bound.py runs/rr-final-12` shows that no
field can fix it:

- The zero-sum rule fixes the average, not the spread. The real win rates are zero-sum too (the
  whole field averages 50%). The simulated spread comes from lopsided matchups (Dwarves win about
  70% of their game ones), not from too few opponents. Game noise explains about 3 points of SD, not 13.
- An outside field only changes the games played against it: 26.3% of real play for the 12 decks,
  18.7% for the 18. Weighting the opponents by meta share alone gives SD 14.2 and gap 12.0, slightly
  worse than equal weights. Adding a field that every deck beats exactly 50% of the time gives
  SD 10.5 and gap 8.8, still more than double the real spread.
- A perfect fit would need Boros Dragons and Boros Dwarves to win less than 0% of their games against
  the field (−14 and −6) and Jund Sacrifice and Dimir Uldaros more than 100% (118 and 103). No set of
  decks does that.
- Several lists per big archetype add little: they play almost like the lists already in the gauntlet.

So the field is kept small (about 25 decks, step 3 below) and the format is tested first. The
user approved this plan and will run the steps one at a time.

### Done in this session (committed as work in progress, untested on full runs)

- **Six decks added** to `decks/standard/meta/` (now 18, 81.3% of the field): Dimir Excruciator,
  Rakdos Lizards, Izzet Prowess, Mono-Black Aggro, Golgari Midrange, Grixis Reanimator, with
  `meta_share` and `real_win_rate` from the Magic.gg Metagame Mentor table (5 Nov 2026) in
  `gauntlet.json`. Their lists are the melee.gg decklists that article links per archetype; all pass
  `mtgsim check`. Their real win rates rest on roughly 20–25 players each (1.0–1.4% of 1,810), so
  they are noisy (about ±7 points). They have no `sim_win_rate` / `ai_pilot` yet.
- **melee.gg is reachable** (allowed in the environment's network policy this session). Plain `curl`
  works; a browser `User-Agent` got 403 once. A decklist page holds the Arena text in
  `<pre ... id="decklist-mtga-text">`, the pilot in `<meta name="description">` ("Deck - Player -
  ...") and the event in the first `href="/Tournament/View/<id>"`. With it the three tournament
  lists (Mono-Green Landfall, Orzhov Lifegain, Jund Sacrifice) were checked: identical, main and
  sideboard. The meta README and `decks/AGENTS.md` still say twelve decks and "melee lists not
  checked": update them.
- **Driver** (`mtgsim/bridge/ForgeBridge.java`), three new job fields, all off by default so old job
  lines and games are unchanged:
  - `first=0`: seat 0 starts. Done by setting `Match.lastOutcome` (reflection) to an empty
    `GameOutcome(Draw, [])`: Forge then lets the first non-winner in seat order, seat 0, choose,
    and its AI always chooses to play. Tested: 6 of 6 games had seat 0 first.
  - `sideboard=1`: before the game each seat sideboards against the other seat's main deck with
    Forge's own `forge.ai.SideboardAdvisor` (card roles read from Oracle text, at most 7 swaps,
    creature for creature, cost within 1). Built on copies of the cached decks in a throwaway
    `Match`, then `MyRandom` is re-seeded. The result line gets `"sideboard":[[seat 0 "out>in"...],[...]]`.
  - `planonly=1` (with `sideboard=1`): return only the swaps, status `"plan"`, no game.
- **Python**: `runner.Job.first_seat / sideboard / plan_only`; `experiment.RunOptions.match_format`
  (`bo1`/`bo3`) and `.sideboard`; `plan_match_game`, `next_match_games`, `match_game_seed`;
  `execute()` plays bo3 in three rounds (all game 1s, then the game 2s, then the game 3s still
  needed) and re-plans rounds 2–3 from `games.jsonl` on `--resume`, and refuses to resume a run
  under a different format. Game 1 of match *i* has id `a|b|i` and the best-of-one seed, so it **is**
  best-of-one game *i* (copy an old run's `games.jsonl` into a new bo3 run directory to reuse them);
  games 2/3 have ids `a|b|i|g2`, `a|b|i|g3`, their own seeds, `match_game` 2/3 and explicit
  `seats` (loser of the previous game in seat 0). `analysis.seat_of_a` now reads `seats`;
  `analysis.summarize_matches` gives match-level wins (two game wins; three games without that is a
  draw) plus `game1`, `later_games`, `game_wins`, `match_lengths`; `analysis.first_games` feeds
  card statistics and misplays (later games are sideboarded). CLI: `--bo3` and `--no-sideboard`
  on `match`, `gauntlet`, `matrix`; `matrix --bo3` also stores `matrix_game1` / `pairings_game1`
  (the best-of-one numbers from the same run). The report states the format.
- `tools/sideboard_plans.py [FOLDER]` prints the advisor's plan for every pairing.
- 277 unit tests pass. The integration tests were not re-run.

### What the sideboard plans look like (18 decks, `tools/sideboard_plans.py`)

1–6 swaps per matchup. Against Boros Dwarves most decks bring in removal or sweepers (Azorius
Artifacts 2 Day of Judgment and 2 Seam Rip, Orzhov Lifegain 2 Seam Rip and 2 Pyrrhic Strike, Izzet
decks Fire Magic and Broadside Barrage), which is what the hypothesis needs. Weak spots, all from
the advisor's text patterns: Azorius Control makes no change against Dwarves (Pinnacle Starcage's
"exile all artifacts and creatures with mana value 2 or less" matches none of its patterns, but it
does come in against Dragons); Rest in Peace comes in whenever the opponent has four cards that
mention a graveyard, which is often (Azorius Control and Azorius Momo bring it against half the
field). A result from these runs is "with Forge's sideboarding", not with a person's. Improving the
advisor would be a Forge patch, measured like any other.

### Step 1 done (16 Nov 2026, later session): bo3 mechanics checked, tests and docs added

- `runs/chk-bo3` was empty (no games); deleted and rerun: Azorius Control vs Boros Dwarves, 8 matches,
  seed 1, 20 games. Dwarves won 6 matches, Control 2, no draws; 4 matches went to game 3.
- **Game 1s are the best-of-one games:** all 8 identical (`tools/compare_games.py`) to a fresh
  best-of-one run with the same seed (`runs/chk-bo1`), and to the same ids in `runs/rr-final-12`
  (played before patch 0020, which only touches `--mc fixed`).
- Every game 2 and 3 had `first_seat` 0 and the previous game's loser in seat 0; match counts add up.
- **Bug found and fixed:** `experiment._record` dropped the driver's `sideboard` field, so the swaps
  were never stored. Records of sideboarded games now carry them.
- **Fixed:** the resume check compared `sideboard` for best-of-one runs too, so a bo1 run planned
  with `sideboard=False` (not possible from the CLI) would have refused its own resume.
- What the advisor did in that pairing: Azorius Control made no change (as `sideboard_plans.py`
  showed); **Boros Dwarves took out 2 Chainsaw and 2 Basilisk Collar for 2 Rest in Peace and 2 Seam
  Rip** against Azorius Control. Rest in Peace in an aggro deck against a control deck is the
  advisor's graveyard pattern misfiring. Keep it in mind when reading step 2; an advisor patch
  would be measured like any other.
- Tests: `BestOfThreeTest` in `tests/test_experiment.py` (9 tests), `MatchTest` in
  `tests/test_analysis.py` (4), `helpers.later_game`, and the integration test
  `test_best_of_three_matches_replay_and_seat_the_loser_first` (three bo3 matches replay with 1 and
  2 workers; game 1s equal best-of-one). 298 tests pass.
- Docs updated: `mtgsim/bridge/AGENTS.md` (protocol fields, `sideboard` result, how `first=0` and
  sideboarding work), `mtgsim/AGENTS.md` (bo3 invariants), `README.md` (`--bo3`, `--no-sideboard`,
  18 decks), `tests/AGENTS.md`, the meta README and `decks/AGENTS.md` (18 decks; melee.gg lists checked).

**Start the next session at step 2.**

### Step 2 (16 Nov 2026, later session): best-of-three run done, no-sideboard arm running

- `tools/calibration.py` takes `--game1` (reads `pairings_game1`) and `--only SLUGS`; it and
  `calibration_diff.py` (which reads `RUN#game1`) print SD and meta-share-weighted figures.
- `runs/rr18-bo3` finished: 4,590 matches, 11,174 games, 2.3 h, 0 errors. Numbers in
  `VALIDATION.md`, "Best-of-three with sideboards". In short: **the sideboards change nothing
  beyond noise.** Game-level SD in the sideboarded games 2/3 is 14.2 against 14.5 in game 1s (gap
  11.5 vs 12.1); Dwarves, Dragons, Landfall stay where they were; Jund Sacrifice falls. Matches
  widen the spread as the format must (12 decks: SD 13.3 → 19.0, gap 11.4 → 16.7).
- Game 1s on the 12 original decks equal `runs/rr-final-12` exactly.
- `runs/rr18-bo3-nosb` (`--no-sideboard`, same seed) was started after it, with the 4,020 game 1s
  copied (a filter bug skipped the 570 whose ids contain "|g" for Golgari/Grixis; those replay,
  which checks determinism). If the container restarted, continue it with
  `python3 -m mtgsim matrix decks/standard/meta -n 30 --seed 1 --bo3 --no-sideboard --resume runs/rr18-bo3-nosb`.
  Then compare its later games and matches with `rr18-bo3`'s (`calibration_diff.py runs/rr18-bo3-nosb runs/rr18-bo3`)
  and fill the PENDING line in `VALIDATION.md`.
- Unless the no-sideboard arm changes the picture, best-of-three is not the explanation: the leading
  hypothesis is weakened (with Forge's sideboarding). Step 3 (the field) cannot lower the spread
  much (`field_bound.py`), so step 4 (the pilot) is where the gap is.

### Next, in order (revised plan; one step per session is fine)

1. **(Done, see above.) Check the bo3 mechanics on real games, then add tests and docs.** `runs/chk-bo3` exists from an
   earlier attempt; look at it, and if it is incomplete delete it and rerun:
   `python3 -m mtgsim match decks/standard/meta/azorius-control.txt decks/standard/meta/boros-dwarves.txt
   -n 8 --seed 1 --bo3 --out $PWD/runs/chk-bo3`. Check that:
   - its game 1s equal the games with the same ids in a best-of-one run with the same seed
     (`runs/rr-final-12` has them; `tools/compare_games.py` compares runs game by game);
   - every game 2 or 3 has `first_seat` 0 and `seats[0]` = the previous game's loser;
   - the match counts add up (two game wins take a match; three games without one are a draw).
   Then add unit tests (`tests/test_experiment.py`: planning games 2/3 from fake records, seats,
   resume re-planning, refusal to resume under another format; `tests/test_analysis*`:
   `summarize_matches`; the job line with `first=0` / `sideboard=1`) and an integration test (one
   bo3 match replays from its seed). Update `mtgsim/bridge/AGENTS.md` (protocol: `first`,
   `sideboard`, `planonly`, the `sideboard` result field), `mtgsim/AGENTS.md` (invariants: seats in
   games 2/3 are not by parity; game 1 of match *i* is best-of-one game *i*), `README.md` (`--bo3`,
   `--no-sideboard`), `tests/AGENTS.md`, and the meta README and `decks/AGENTS.md` (18 decks; the
   melee.gg lists are checked). Run the full test suite. Commit.

2. **Experiments (a) and (b) in one run: the 18-deck round robin, best-of-three with sideboards.**
   - Before starting, give `tools/calibration.py` a switch to read `pairings_game1` instead of
     `pairings`, let `calibration_diff.py` compare the two from one run, and make both print the
     SD and the meta-share-weighted deck averages next to the equal-weighted ones (the real figures
     are against the field). `tools/field_bound.py` already prints SD and both weightings.
   - Run detached, about 3 hours (153 pairings; about 4,600 game 1s plus about 6,700 later games):
     `setsid nohup python3 -m mtgsim matrix decks/standard/meta -n 30 --seed 1 --bo3 --out $PWD/runs/rr18-bo3 > runs/rr18-bo3.log 2>&1 &`
     and continue with `--resume runs/rr18-bo3` (same arguments) if the container restarts.
   - (a) = the game 1s (`matrix_game1`): the 18-deck best-of-one baseline. (b) = the match results.
     Report SD, mean gap and rank correlation for both, on the 18 decks and on the original 12.
   - The question: do the creature decks (Dwarves, Dragons, Landfall, Lifegain) fall and the
     underrated decks (Jund Sacrifice, Dimir Uldaros, Izzet Spellementals, Four-Color Control) rise?
     Expect best-of-three alone to stretch win rates away from 50% (a 60% game rate is about a 65%
     match rate), so a smaller spread in (b) is evidence for the sideboards, not the format.
   - If time allows, the same run with `--no-sideboard` (`--out runs/rr18-bo3-nosb`): it separates
     the format from the sideboards. Its game 1s equal (a)'s, so copy `games.jsonl` from
     `runs/rr18-bo3` into the new run directory first and only the later games are played.
   - Record the numbers in `VALIDATION.md` and here. Keep in mind the sideboards are Forge's
     `SideboardAdvisor` (weak spots below): the result is "with Forge's sideboarding".

3. **A small field of about 25 decks (experiment (c)), only after step 2.** It makes the field
   realistic and answers the field question at a fraction of the cost; `field_bound.py` says it can
   lower the spread a few points at most.
   - Source: melee.gg (allowed in the network policy; plain `curl`, one request a second). The
     Magic.gg article links one list for each "Other" archetype: Sultai Reanimator, Izzet Fling,
     Jeskai Planeswalkers, Jeskai Artifacts, Boros Mobilize, Selesnya Offense, Dimir Control, Mardu
     Discard, Temur Omniscience, Azorius Prison, Mono-Red Aggro, Dimir Oculus, Jeskai Control and
     more. Take one list each, up to about 25; no extra lists of archetypes already in the gauntlet.
     Only if those links are not enough, use the tournament standings (472270, 440878, 457663;
     check whether the page is filled by a JSON endpoint).
   - Give each a `meta_share` so the field's archetype shares match the real table (the "Other"
     18.6%, split by the article's numbers or evenly if it gives none). They need no real win rate.
   - `mtgsim check` every list; resolve unknown card names with the user, never guess. Put them in
     `decks/standard/fracture-2026-field/` with its own `gauntlet.json`, so the 18-deck meta gauntlet
     stays the default.
   - Run each of the 18 meta decks against the 18 + 25 decks, best-of-one, about 30 games per
     pairing, and report each meta deck's meta-share-weighted win rate (`summarize_field` weights by
     `meta_share`): 18 x ~42 pairings x 30 = about 23,000 games, about 4.5 hours. Fewer games per
     pairing against the field decks is fine (their shares are small).
   - Judge by the SD and the mean gap against (a). If (b) helped, (d) = the same in best-of-three.

4. **If neither the format nor the field closes the gap**, the problem is the pilot: go back to
   "Next steps, in order of expected value" below (mana sinks and wrong-phase activations in the
   underrated decks, then `--mc fixed`), and improve the sideboard advisor's weak spots as measured
   Forge patches.

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

1. *(Superseded by `--bo3`, step 2 of the checkpoint plan.)* **Test the sideboard explanation.** Build post-board lists by hand for Boros Dwarves and its
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
