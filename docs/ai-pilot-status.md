# AI pilot project: where it stands

Handoff note for the next agent. Rewritten 2026-11-15 on branch `claude/ai-decision-engine`. The
goal of the project: make mtgsim's Forge AI play more like real players, so simulated meta win
rates track real ones. Numbers and methods are in `VALIDATION.md`; this note says what is done,
what was learned and what to do next.

## CHECKPOINT 16 Nov 2026: best-of-three with sideboards, in progress

**Read this section first; it is where the last session stopped.**

**The goal (stated by the user, 16 Nov 2026): the simulations must give reasonable win rates, ones
that look like the real ones.** Everything below serves that. Best-of-three with sideboards tests one
explanation of why they do not (game one without sideboards favours creature decks). The extra decks
are **not a goal in themselves**: they are there to test a second explanation, that a small closed field
forces the results into a zero-sum game. In a round robin of 12 or 18 decks the deck averages must
average 50%, every point one deck gains is taken from the few others, and a deck that beats or loses
to two or three neighbours swings far. The real decks play a field of 1,810 lists, 18.6% of them
"Other", so their win rates sit between 44% and 58% (Izzet Prowess's 30.6% is the exception, from
about 25 players). If the simulator is sound, adding a wide, realistically weighted field should
pull the simulated win rates of the 18 meta decks towards those values (a smaller spread and a
smaller mean gap); if they stay as far apart, the problem is the pilot or the format, not the field.
Judge every run by that: the spread and the gap of the 18 decks with real win rates, not by how
many decks were added.

The user asked for **about 100 more decks before running anything** (see "Next" below). Nothing
below has been run at scale yet.

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

### Next, in order

1. **Verify the bo3 mechanics on real games** (the last command was interrupted before it ran):
   `python3 -m mtgsim match decks/standard/meta/azorius-control.txt decks/standard/meta/boros-dwarves.txt
   -n 8 --seed 1 --bo3 --out $PWD/runs/chk-bo3`, then check that its game 1s equal the same ids in a
   best-of-one run with the same seed (`runs/rr-final-12` has them if it survived), that every game 2/3
   has `first_seat` 0 and `seats[0]` = previous loser, and that the match counts add up. Then add unit
   tests (`tests/test_experiment.py`: planning of games 2/3 from fake records, seats, resume
   re-planning; `tests/test_analysis*`: `summarize_matches`; job line with `first=0`/`sideboard=1`) and
   an integration test (one bo3 match replays). Update `mtgsim/bridge/AGENTS.md` (protocol),
   `mtgsim/AGENTS.md` (invariants: seats in games 2/3 are not by parity; game 1 = bo1 game), README
   (`--bo3`), `tests/AGENTS.md`.
2. **About 100 more decks, as a field (the user's request; purpose above).** They are opponents that
   make the field look like the real one; they do not need real win rates of their own, and the
   calibration is still measured on the 18 decks that have one. So pick them for coverage and weight
   them by how often they were played:
   - Source: the three events' melee.gg standings (tournaments 472270 Arena Championship 13,
     440878 Spotlight Hartford, 457663 Spotlight Beijing; links in the Magic.gg article), which list
     every player's decklist. Check how the standings page loads (it may be filled by a JSON
     endpoint; read the page's scripts), stay polite (one request a second).
   - Take several lists per big archetype (variation within an archetype matters too) and lists from
     the "Other" 18.6% (Sultai Reanimator, Izzet Fling, Jeskai Planeswalkers, Jeskai Artifacts, Boros
     Mobilize, Selesnya Offense, Dimir Control, Mardu Discard, Temur Omniscience, Azorius Prison,
     Mono-Red Aggro, Dimir Oculus, Jeskai Control and more; the Magic.gg article links one list for
     each). Give each list a `meta_share` so that the field's archetype shares match the real table.
   - Keep each list's own match record from the standings as optional metadata (secondary check only:
     ±12 points from ~15 matches).
   - Run `mtgsim check` on every list; resolve unknown card names, never guess. Put them in a separate
     folder (e.g. `decks/standard/fracture-2026-field/`) with its own `gauntlet.json`, so the 18-deck
     meta gauntlet stays the default.
   - Design: a gauntlet of each of the 18 meta decks against the whole field (18 x ~118 pairings,
     linear) rather than a full round robin (6,903 pairings), and report each meta deck's
     **meta-share-weighted** win rate (`summarize_field` already weights by `meta_share`). At 10 bo3
     matches per pairing that is about 21,000 matches (~50,000 games, ~10 hours on 4 cores); 10
     best-of-one games per pairing is ~21,000 games (~4 hours). Start with best-of-one, so the field
     effect and the format effect can be told apart.
3. **The experiments, each judged by the spread and the mean gap of the 18 meta decks against their
   real win rates (and the rank correlation, with its noise range):**
   (a) the 18-deck best-of-one round robin, the baseline (game 1s of (b));
   (b) the 18-deck best-of-three round robin with sideboards: does the format move them towards the
   real values?
   (c) the 18 meta decks against the ~118-deck weighted field, best-of-one: does a realistic field
   flatten the win rates (the zero-sum question)?
   (d) if (b) or (c) helps, the two together.
   For (b): `matrix decks/standard/meta -n 30 --seed 1 --bo3` (18 decks, 153 pairings; about
   4,600 game 1s, which are the best-of-one round robin, plus about 6,700 later games; roughly 3 hours),
   detached with `setsid nohup`, `--out` set, resumable. Then compare calibration of `matrix_game1`
   (best-of-one) with the match results (`tools/calibration.py` reads `summary["pairings"]`; add a
   switch for `pairings_game1`, and give `calibration_diff.py` both from one run). Also a
   `--no-sideboard` bo3 run if time allows: best-of-three alone stretches win rates away from 50%,
   so it separates the format from the sideboards. Report equal-weight and meta-share-weighted deck
   averages (the real figures are against the field).

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
