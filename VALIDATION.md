# Validation

What was checked before mtgsim was handed over, how, and what came out. Engine runs used
Forge commit `7db198d72e` on a 4-core cloud machine; raw game files are not kept in the
repository, but every run can be reproduced with the commands and seeds below.

## Summary

| Check | Result |
|---|---|
| Unit tests (no Forge needed) | 277 pass |
| Integration tests (real games) | 7 pass |
| `--mc fixed` (counted Monte Carlo) | replays: 40 of 40 games identical across 1 and 2 workers and on a second run; games without Monte Carlo unchanged (200 of 200); mirror 50.0% (40–60%); Azorius Control vs Boros Dwarves 32.0% against 26.0% with the default pilot, +6.0 points (−2.9 to +14.8), not reliable; about 9 times the engine time per searching seat; see below |
| Same seed, different worker count | 40 of 40 games identical |
| Interrupted run, then `--resume` | 80 of 80 games identical to an uninterrupted run; no orphan processes |
| Mirror match (identical decks, 400 games) | 48.9%, 95% CI 44–54% (expected 50%) |
| Lopsided match (meta deck vs 40 lands + 20 Llanowar Elves) | 93.3%, CI 84–97% |
| A/B with a deliberately worse variant | detected: +12.5 points, CI +6.8 to +18.2, p < 0.001 |
| Simulated vs real meta win rates | weak agreement: rank correlation 0.14 over eighteen decks with all fourteen Forge patches (noise 0.04–0.19), mean gap 11.4 points, SD 14.0 against a real 6.0 ("Calibration" below); 0.23 and 11.4 over twelve decks with eleven patches; 0.24 and 13.0 on unpatched Forge with eleven decks |
| Simulated vs real meta win rates, as simulated Swiss events (the reference metric since 23 Nov) | `calibrate` on the same run: SD 11.4 (10.6–12.2) against a real 6.0, mean gap 9.4 (8.5–10.1), Spearman 0.11 (0.01–0.18), 8 sign errors of 18 ("Swiss pairing" below) |
| Engine failures | 0 crashes in about 4,100 recorded games; 1 time-out (a board stall in the mirror match), plus 1 in an early integration-test run |
| Fresh install (`setup --build` in an empty home, then `doctor`) | passes in about 2 minutes |
| Forge patches (fresh build with patches, then changed patch sets) | applied, recorded and rebuilt exactly as designed; see below |
| Misplay tracking does not change games (same seed, original vs new driver) | 60 of 60 games identical, then 1,650 of 1,650 over the whole round robin; see below |
| Decision snapshots do not change games (`--snapshots`, 23 Nov) | 90 of 90 games identical to the old driver's (three pairings, seed 1), three times (as the kinds were added), 40 of 40 with and without snapshots; see "Decision snapshots" |
| Decision probe, steps B and C (23 Nov): 200 blind cases | a Claude subagent's choice and Forge's agree on 51% (44–58%) of cases, 49% (41–56%) of the planning decks' 175; least on spell decisions (main phase 32%, second main 19%), where the answer usually casts more. Which is better is step D's grading; see "Decision probe" |
| Decision probe, round 2 (24 Nov): the same decisions with the case gaps fixed | 420 of 420 step B games replay identically with the new tracker; 198 of the 200 decisions found again (two existed only through a spree-cost bug); fresh answerers agree with Forge on 102 of 198, 52% (45–58%), planning decks 49% (42–57%): no change. 183 of 198 cases get the same verdict in both rounds; see "Decision probe" |
| Decision probe, round 3 (24 Nov): cost reductions, restricted mana and turn history added | 419 of 420 step B games replay identically (the other does not replay on the old driver either); all 198 decisions found again; fresh answerers agree with Forge on 105 of 198, 53% (46–60%), planning decks 52% (45–59%): no change. 173 of 198 cases get the same verdict as in round 2; see "Decision probe" |
| Decision probe, step D (25 Nov): round 3's 93 disagreements graded blind by Claude subagent judges, twice each with A and B swapped | Answerer judged better in 69, Forge in 10, no preference in 14; planning decks 63 to 9, 88% (78–93%) of decided cases (7 cases regraded on corrected text, 26 Nov). The judges are the same model family as the answerer, so this is an upper bound; see "Decision probe" |
| Forge patches for cards the AI never cast | Azorius Control +25.4 points (CI +21.3 to +29.4), Azorius Momo +9.3 (+4.9 to +13.6), Dimir Uldaros +3.8 (not reliable); mirrors 50–54% |
| Three more patches (14 Nov) | Mono-Green Landfall +20.3 points (CI +16.0 to +24.5) from the Ba Sing Se fix; Nova Hellkite and Chainsaw are now cast but move no win rate (+1.5 and −0.1, not reliable); mirrors 48–55% |
| Why the creature decks win (1,650 game logs read) | no blocking, removal or card-script flaw found; games turn on how much removal the opponent draws, in game one without sideboards; see below |
| Profile tuning on the meta (16 candidates, 12,010 games, 2 decks held out) | no profile beats Forge's default beyond noise (training rank correlation +0.18, noise −0.20 to +0.43; held-out gap −0.8 points, noise −5.8 to +4.7); none shipped |
| The meta decks against the whole field (13 "Other" decks added, 7,020 games, 16 Nov) | spread 14.9 → 14.5 and mean gap 12.2 → 12.0 (18 decks, share-weighted; real SD 6.0), within noise; the field decks show the same creature-deck bias; see below |
| Best-of-three with Forge's sideboarding, 18-deck round robin (16 Nov) | matches spread wider than games, all from the format: 18 decks SD 19.1 with sideboards, 19.6 without (difference −0.5, −1.5 to +0.4), against 14.5 in game 1s (real 6.0); sideboarded games 2 and 3 have SD 14.2, unsideboarded 14.6; the creature decks do not fall; game 1s replay 4,588 of 4,590 (both differences in Four-Color Control vs Grixis Reanimator); see below |

## The pipeline behaves correctly

**Reproducibility.** Mono-Red Burn vs Mono-Green Stompy, 40 games with seed 11, once with 4
workers and once with 3: every game had the same winner, turn count, starting player and card
log. An 80-game match interrupted after 9 games and finished with `--resume` was identical,
game for game, to the same match run without interruption.

**No bias between the two sides.** Two copies of the same deck, 400 games: 195–204 (48.9%,
interval 44–54%, p = 0.69). Play/draw split 48% / 50%. The seat each deck sits in alternates,
and who goes first comes from a fresh coin flip every game; Forge's built-in simulator instead
lets the previous loser go first, which would have pulled every win rate towards 50%.

**Sensitivity.** A tournament deck against a pile of lands and Llanowar Elves won 56 of 60. In
the A/B test, Mono-Red Burn was compared with a copy that swaps its eight burn spells for eight
Mountains, over 100 games against each of four casual decks (900 games including the head to
head). The tool found the original better by 12.5 points and called it reliable, and the head
to head went 65–35 to the original.

**Deck loading.** Every run checks that Forge loaded exactly as many cards as the list has;
all 16 included decks load completely.

## How far to trust the numbers

**The AI pilot dominates the result for some decks.** All eleven meta decks were played against
each other (1,650 games, 30 per pairing, 19 minutes) and compared with each archetype's real
match win rate from the Magic.gg metagame table of 5 November 2026:

| Deck | Real | Simulated | Gap |
|---|---|---|---|
| Boros Dwarves | 50.2% | 74.7% | +24.5 |
| Boros Dragons | 45.0% | 68.3% | +23.3 |
| Orzhov Lifegain | 53.6% | 66.3% | +12.7 |
| Dimir Midrange | 54.5% | 61.3% | +6.8 |
| Azorius Artifacts | 54.8% | 52.7% | −2.1 |
| Mono-Green Landfall | 53.4% | 52.0% | −1.4 |
| Azorius Momo | 48.8% | 45.0% | −3.8 |
| Izzet Spellementals | 44.3% | 37.7% | −6.6 |
| Jund Sacrifice | 57.6% | 41.0% | −16.6 |
| Dimir Uldaros | 49.2% | 31.3% | −17.9 |
| Azorius Control | 46.6% | 19.7% | −26.9 |

Pearson correlation 0.23, rank correlation 0.24. Creature decks are overrated and decks that
need planning are underrated. Each meta deck now carries an `ai_pilot` rating (weak / fair /
strong) in `decks/standard/meta/gauntlet.json`, and reports name the opponents to discount.

**A stronger AI helps, at a price.** Azorius Control vs Boros Dwarves, 40 games per setting:

| AI | Control's win rate (W–L, 95% CI) | Time |
|---|---|---|
| Default | 17.5% (7–33, 9–32%) | 1.3 min |
| `--mc max` (Monte Carlo look-ahead) | 32.5% (13–27, 20–48%) | 7.5 min |

That closes part of the gap for the control deck at about six times the run time. Monte Carlo
mode thinks against a clock, so its games are not exactly reproducible from the seed.

**Per-deck AI settings do not fix the ranking.** The full round robin (1,650 games, 30 per
pairing) was repeated with four settings applied through `ai_profile` / `ai_mc` in
`gauntlet.json`. Ranges are 95% bootstrap intervals (games resampled within each pairing):

| Setting | Rank corr. | Mean gap | Time | s/game |
|---|---|---|---|---|
| Default AI for every deck (baseline) | 0.24 (0.12–0.35) | 13.0 pts (11.9–14.5) | 19 min | 2.8 |
| `Cautious` profile for the three control decks | 0.24 (0.12–0.34) | 12.7 pts (11.7–14.3) | 16 min | 2.3 |
| `ai_mc: max` for the three `weak` decks | 0.21 (0.05–0.42) | 9.1 pts (8.2–11.1) | 63 min | 9.1 |
| `Hardest` + `ai_mc: max` for the `weak` decks | 0.25 (0.08–0.40) | 9.4 pts (8.4–11.1) | ~60 min | 9.0 |
| `--mc max` for every deck | 0.16 (−0.09–0.33) | 11.6 pts (10.2–12.9) | 167 min | 24.2 |

Monte Carlo for the weak decks lifts them to realistic levels (Jund Sacrifice 41→50%, Dimir
Uldaros 31→48%, Azorius Control 20→46%) and cuts the average gap by about four points, beyond
the noise. The ranking does not improve: Azorius Artifacts, Azorius Momo and Izzet
Spellementals lose ground, and Boros Dwarves (72%) and Boros Dragons (62%) stay overrated.
Monte Carlo for everyone is worse on both measures and nine times slower. The `Cautious` and
`Hardest` profiles change nothing measurable. The shipped gauntlet therefore keeps the
default AI, and its games stay reproducible. Setting `ai_mc: max` on the three `weak` decks
is a reasonable opt-in when realistic opponents matter more than speed and exact replays.

**Card statistics are noisy.** In the 400-game mirror, the two identical decks' cards should
have scored the same; Giant Growth came out at +18.7 points in one copy and −1.3 in the other.
Reports now show a 95% interval for every card and mark only the differences that exclude zero.

**Sample size.** A 100-game matchup is known to about ±10 points. Detecting a 5-point
improvement in an A/B test needs about 1,500 games per version.

## The profile-tuning harness (`tune`)

The harness was checked first on an unpatched Forge (no Forge patches shipped yet). The full
search was then run on the meta with all eight patches: no profile it found beats Forge's
default settings beyond game noise ([below](#the-search-on-the-meta-no-profile-shipped)).

**The metrics reproduce the baseline.** The 1,650-game round robin above (seed 1, 30 games per
pairing) was imported into `tune` (all 1,650 games qualified as identical to the games `tune` would
play) and scored by its code: rank correlation 0.236, game-noise range 0.12–0.35, Pearson 0.23,
mean gap 13.0 points, and every deck's simulated win rate as in the table above. On the first 10
games per pairing only, the same baseline scores 0.29 with a noise range of 0.06–0.41: the first
round of a search separates only large effects.

**Generated profiles reach the engine, and unchanged pairings are not replayed.** Smoke run on four
meta decks (Boros Dwarves, Mono-Green Landfall, Dimir Midrange, Orzhov Lifegain) with a one-setting
space, `MULLIGAN_THRESHOLD=8` (a seven-card hand is already below it, so the AI never mulligans),
one profile per group, four candidates, rounds of 4 and 8 games per pairing and 4 confirmation games
(168 games, about 5 minutes including JVM starts):

| Check | Result |
|---|---|
| Seats playing the generated profile that mulliganed | 0 of 232 seat-games (Default: 76 of 256, 30%) |
| Same seed, one deck's profile changed | 44 of 112 games came out differently; the other 68 are games in which Default kept its hand anyway |
| Baseline games played through the run's own profile folder vs the round robin above (Forge's folder, older driver) | 60 of 60 comparable games identical |
| Round 1 / round 2 | 80 / 44 games played for 96 / 96 game results used: shared pairings and earlier games were not replayed |
| `--resume` of the finished run | 0 games played, same result |

`tests/test_integration_profiles.py` repeats the first check on every full test run (60 Forests
mulligan under Default, never under the generated profile) and checks that an unknown profile name
is an engine error rather than Forge's silent fallback to its enum defaults.

**How much a tuning result can show.** Over eleven decks, a rank correlation's 95% interval from
the choice of decks alone is about −0.44 to 0.74 at the baseline's 0.24 (Fisher z, variance
1.06/(n−3)). Narrowing it to ±0.2 would take about 90 decks with real win rates at a correlation
of 0.24, 60 at 0.5 and 30 at 0.7; ±0.1 about 360, 230 and 110. Matchup-level data adds points
only where each matchup has roughly 100 real matches (±10 points). `tune` prints this for every
run.

### The search on the meta: no profile shipped

`python3 -m mtgsim tune --holdout "Dimir Uldaros" "Boros Dragons" --import runs/rr-patched-n30-s1`
on the patched engine (seed 1, the default 21-setting space, 3 profiles per group, 16 candidates:
Default or one of 3 generated profiles for the reactive decks, times the same for the proactive decks). Boros Dragons and Dimir
Uldaros, two of the worst-calibrated decks, were held out and played but never used to choose.
Round 1 played 10 games per pairing, round 2 30 for the best 7; the winner and Default were then
replayed on 30 fresh games per pairing (games 30–59) that took no part in the choice. 12,010 new
games plus the 1,650 imported, about 2 hours.

| Stage (games per pairing) | Default | Best | Best minus Default |
|---|---|---|---|
| Round 1 (10), training rank correlation | 0.28 | 0.42 (five candidates tied) | |
| Round 2 (30, games 0–29), training rank correlation | 0.13 | 0.18 | |
| **Confirmation (30 fresh)**, training rank correlation | 0.03 | 0.22 | +0.18, noise −0.20 to +0.43 |
| Confirmation, training mean gap | 10.1 points | 10.1 points | −0.0, noise −2.3 to +2.2 |
| Confirmation, held-out mean gap (2 decks) | 19.9 points | 19.1 points | −0.8, noise −5.8 to +4.7 |
| Confirmation, all 11 decks | rank corr. 0.03, gap 11.9 | 0.16, 11.7 | +0.14 (noise −0.13 to +0.30), −0.2 |
| Leave-one-deck-out (round 1 games) | 0.28 | 0.40 out of fold (0.42 in sample) | |

The winner (c06) sets, for the control, midrange and tempo decks, counter chances of 0% / 50% for
1- and 2-drops with no minimum mana value, the default sacrifice preference on, and no avoiding of
attacks into certain blocks; for the aggro and ramp decks it holds combat tricks until blocks,
plays aggressively and trades even when behind on creatures. **None of its differences from
Default clears the noise range**, on training or held-out decks, so nothing was put into
`mtgsim/profiles/` and `gauntlet.json` keeps `ai_profile` unset.

What the run shows:

- **The search mostly picked up noise.** The round-1 leaders (0.42) fell back to 0.13–0.18 once
  each pairing had 30 games, and Default itself scored 0.28, 0.13 and 0.03 on three disjoint sets of
  games. With nine decks, game noise alone moves the rank correlation by about ±0.2.
- **These settings barely move the decks that are wrong.** On the confirmation games no deck's win
  rate changed by more than 4 points between Default and the winner (300 games each; a difference
  between two such rates needs about 8 points to show):
  Boros Dwarves 77.3% both, Boros Dragons 66.3% → 65.3% (real 45.0%), Jund Sacrifice 38.0% →
  38.7% (real 57.6%), Dimir Uldaros 30.7% → 31.3% (real 49.2%). The 16–20-point gaps come from
  things no profile key controls (card-specific AI logic such as the cards patched above, holding
  mana for instants, sequencing), not from how often the AI counters or trades.
- With nine training decks the rank correlation's interval from the choice of decks alone is
  −0.54 to +0.78 at 0.22 (`tune`'s own statement): even a winner that cleared game noise could not
  be told apart from a useless one by these eleven real win rates.

## Speed

Average engine time per game was 2.8 s across the meta round robin (slowest deck, Azorius
Artifacts, 4.1 s). With four workers that is about 85 games a minute: the 550-game sample
gauntlet (a casual deck against all eleven meta decks, 50 games each) took 6 minutes. Each worker
uses about 0.9–1.2 GB of memory.

## Forge patches

`setup --build` applies the patches in `mtgsim/forge_patches/` (eleven ship; see "Fixing the cards the
AI never cast"). The mechanism
was checked on 13 November 2026 in an empty `MTGSIM_HOME`, with throwaway patches that were not
committed: a card-script hint for Grizzly Bears, a second one for Raging Goblin, and a Java patch
that adds a new class to `forge-ai`. Maven had the shared `~/.m2` cache; times are wall clock on
the 4-core machine.

| Step | Result | Time |
|---|---|---|
| Fresh build with the Grizzly Bears patch (fetch, apply, Maven, driver, card database) | applied; `doctor` passes: "1 applied, up to date" | 70 s |
| Add the Java patch | Maven rebuild; the new class is in the jar; card cache and driver get new names | 28 s |
| Change the Grizzly Bears patch's content and add the Raging Goblin one | both card scripts re-patched, no Maven run (jar unchanged) | 4 s |
| Remove the Java patch | Maven rebuild; the class and its source are gone | 28 s |
| Add a patch to the folder without running setup | `doctor` plays its games and then exits 1, saying which patch is missing; `match` warns on stderr; `run.json` records `"state": "out-of-date"` and the applied set | 8–9 s |
| Add a patch that does not apply | setup stops with an error naming it and the patches it was tried on top of; checkout and `mtgsim-patches.json` unchanged | 1 s |
| `setup --build --no-patches`, then `setup --build` | card scripts back to the pinned commit ("disabled", `doctor` passes), then re-applied; no Maven run | 3 s, 4 s |

`doctor` took 9 s each time. Afterwards `git status` in the checkout showed only the two patched
card scripts and the marker file. The unit tests in `tests/test_forge_patches.py` cover the same
cases on a miniature git repository (plus interrupted applies, a damaged marker, patches that
create or delete files, and moving to another Forge commit).

## Decision snapshots

`--snapshots` (23 Nov 2026) makes the driver's tracker write one line per decision point with the
deciding player's visible state and Forge's choice (`mtgsim/bridge/AGENTS.md`). It runs in the
game thread like the misplay tracking, so it was checked the same way: seed 1, every game compared
on status, winner, turns, who went first, seats, seed and every player field (misplay fields
included).

| Pairing (seed 1) | Against the old driver (`runs/rr18-cal`, 30 games) | Snapshot lines (all kinds) |
|---|---|---|
| Azorius Control vs Boros Dwarves | 30 of 30 identical; 40 of 40 also identical to a run without snapshots, record for record | 1,225 in 40 games: 739 main, 218 attack, 146 counter, 88 mulligan, 34 block |
| Jund Sacrifice vs Mono-Green Landfall | 30 of 30 identical | 829: 383 main, 263 attack, 112 block, 71 mulligan |
| Dimir Uldaros vs Orzhov Lifegain | 30 of 30 identical | 998: 559 main, 257 attack, 91 block, 82 mulligan, 9 counter |

After the second main phase (`main2`) and the opponent's end step (`endstep`) were added, the same
three pairings, 30 games each, were replayed: 90 of 90 identical to the old driver again, no tracker
errors, nothing unresolved. New lines in those 90 games: Azorius Control vs Boros Dwarves 355
`main2` and 70 `endstep` (47 in which something was cast), Jund Sacrifice vs Mono-Green Landfall
282 and 9, Dimir Uldaros vs Orzhov Lifegain 346 and 12; files grew to 67–87 KB a game.

The player's own upkeep (`upkeep`) and draw step (`draw`), when an instant-speed card in hand is
castable, came next; again 90 of 90 identical, no errors, nothing unresolved. Upkeep / draw lines:
Azorius Control vs Boros Dwarves 135 / 113 (cast in 22 / 9), Jund Sacrifice vs Mono-Green Landfall
21 / 16 (4 / 1), Dimir Uldaros vs Orzhov Lifegain 49 / 20 (29 / 8). The draw line is taken when the
drawn card reaches the hand: in all 147 turns with both lines and nothing cast in upkeep, the draw
line's hand is one card larger. Files are 69–100 KB a game.

Same Forge patch set as the calibration run; no tracker errors in the worker logs; no decision
left unresolved. The snapshots agree with the game records: one `main` line per turn a player
took (739 of 739), each seat's `mulligan` lines match its recorded mulligans, the kept hand has
seven cards and as many cards put on the bottom as mulligans taken. Azorius Control's counter
windows: 61 countered, 85 let resolve, in line with its `counter` fields. About 60 KB of
snapshots a game before `main2` and `endstep`. The integration test checks the same properties on four games.

## Misplay tracking

The driver's tracker gained the misplay fields (`mtgsim/bridge/AGENTS.md`) on 13 November 2026.
It runs inside the game thread, so the check that matters is that it does not change games:
three matchups were played with seed 1, 20 games each, first with the original driver and then
with the new one, and every game compared field by field (status, winner, turns, who went
first, seats, seed, and for each player the opening hand, draws, cards played, mulligans,
turns, life and loss reason).

| Driver | Azorius Control vs Jund Sacrifice | Dimir Uldaros vs Izzet Spellementals | Dimir Midrange vs Boros Dwarves |
|---|---|---|---|
| First version | 20 of 20 identical | 20 of 20 identical | 20 of 20 identical |
| Shipped version (refinements below) | 20 of 20 identical | 20 of 20 identical | 20 of 20 identical |

No tracker errors appeared in the worker logs. The first version's data showed false positives
that the shipped version removes: a second copy of a legendary card counted as castable while
the first was in play, X spells were checked at X = 0, "up to one target" removal counted as
castable with no target, and bouncing your own creatures to save them (Get Out) counted as
removal hitting your own permanent. Charms with a counter mode now get counter windows too.

What the signals showed in those 60 games (first version):

- Azorius Control's Countersculpt was seen in 18 games and never cast, while 48 opponent spells
  it could have countered resolved; No More Lies let 45 through and was cast 11 times. Jace's
  Machinations was never cast in the 15 games it was seen.
- Dimir Uldaros never cast Requiting Hex, Seasoned Cryomancer or Uldaros Theorix in the games
  they were seen (17, 17 and 11), although they were castable on some of those turns.
- No removal cast was flagged for a poor target: Forge chooses targets with the same creature
  evaluation the check uses, so that column only catches cards whose own AI logic aims
  elsewhere.

These are pointers for reading card scripts and AI code, not measured misplays; the next
section shows what fixing the top ones did.

**The whole round robin, replayed.** The 1,650-game meta round robin (seed 1, 30 games per
pairing) was re-run with the merged driver (misplay tracking plus the per-run AI profile folder)
on the same unpatched Forge: all 1,650 games identical to the baseline, field by field.

## Fixing the cards the AI never cast

`python3 -m mtgsim misplays` on that round robin put one or two cards at the top of three decks
that the AI held in almost every game it drew them and almost never cast (seen = games the card
was in the opening hand or drawn):

| Deck | Card | Hits per 100 games | Seen | Cast |
|---|---|---|---|---|
| Azorius Momo | Springleaf Drum | 71 | 230 | 0 |
| Azorius Control | Countersculpt | 56 | 259 | 0 |
| Azorius Control | Jace's Machinations | 56 | 228 | 0 |
| Azorius Momo | Nurturing Pixie | 46 | 165 | 5 |
| Dimir Uldaros | Seasoned Cryomancer | 39 | 209 | 7 |
| Azorius Momo | Practiced Offense | 30 | 184 | 0 |
| Dimir Uldaros | Uldaros Theorix | 18 | 188 | 3 |

Each traced to a gap in Forge's AI code at the pinned commit (an API with no AI class, a missing
`AILogic`, an `AI:RemoveDeck` filter, enter-the-battlefield checks that refuse a creature over an
optional trigger). The eight patches in `mtgsim/forge_patches/` fix them; its README lists cause
and fix per card, and each patch header carries its measurement. Each deck was measured against
the other ten meta decks, 100 games per opponent, seed 1, on a private copy of the Forge checkout,
without and with its patches; the games share seeds, so the paired interval is also given:

| Deck (patches) | Without | With | Difference, 95% CI | Mirror, patched (200 games) |
|---|---|---|---|---|
| Azorius Control (0001 Empower AI) | 22.4% (20–25%) | 39.9% (37–43%) | +17.5 (+13.5 to +21.4; paired +14.7 to +20.3) | |
| Azorius Control (0001 + 0002) | 22.4% (20–25%) | 47.8% (45–51%) | +25.4 (+21.3 to +29.4; paired +22.3 to +28.5) | 54.0% (47–61%) |
| Azorius Momo (0003–0005, 0008) | 44.9% (42–48%) | 54.2% (51–57%) | +9.3 (+4.9 to +13.6) | 50.0% (43–57%) |
| Dimir Uldaros (0006, 0007) | 30.1% (27–33%) | 33.9% (31–37%) | +3.8 (−0.3 to +7.9), not reliable | 51.0% (44–58%) |

After the fixes the cards are cast in most games they are seen in: Countersculpt 690 of 874,
Jace's Machinations 600 of 799, Springleaf Drum 655 of 728, Practiced Offense 579 of 629,
Nurturing Pixie 417 of 483, Seasoned Cryomancer 478 of 679, Uldaros Theorix 326 of 632. Fixing
Practiced Offense exposed an engine crash (5 of 1,000 Momo games: `PumpEffect` read a target that
had left in response), which patch 0008 fixes. Dimir Uldaros's patches are kept although its
gain is not significant: without them two of its cards could not be cast at all.

**What the fixes do to the calibration.** The round robin on the patched engine
(`setup --build` with all eight patches, same command and seed):

| | Baseline | Patched | Patched minus baseline, 95% interval |
|---|---|---|---|
| Rank correlation with real win rates | 0.24 (noise 0.12–0.35) | 0.11 (−0.05–0.25) | −0.13 (−0.32 to +0.08) |
| Pearson correlation | 0.23 | 0.08 | −0.15 (−0.31 to +0.02) |
| Mean absolute gap | 13.0 pts (11.8–14.5) | 10.8 pts (9.4–12.5) | −2.2 (−4.1 to −0.3) |

The decks the fixes touch moved towards their real win rates (Azorius Control −26.9 → −3.9
points, Azorius Momo −3.8 → +1.9), and the average gap shrank by more than the noise. The ranking
did not improve: Boros Dwarves (+19.8) and Boros Dragons (+18.7) are still the most overrated,
Jund Sacrifice, the best real deck, is still 20 points low, and Azorius Artifacts fell to −8.1,
partly because the repaired control deck now beats it. Fixing cards the AI could not cast at all
is a correctness fix; what remains is how Forge's AI plays the cards it can cast.

## More card fixes, and why the creature decks win (14 November 2026)

**Cards the misplay report still flagged.** On the patched round robin (re-run with `--save-logs`;
all 1,650 games identical to the first patched run) the cards "castable but never cast" most
often were read against Forge's AI code:

| Card (deck) | Castable, never cast | Cause | Outcome |
|---|---|---|---|
| Nova Hellkite (Boros Dragons) | 50 of 71 games | `AiController.checkETBEffects` refuses a creature whose enter trigger `DamageDealAi` would not use; 1 damage rarely kills | patch 0009 |
| Chainsaw (Boros Dwarves) | 25 of 38 | the same refusal, for its 3 damage | patch 0010 |
| Pinnacle Starcage (Azorius Artifacts, Azorius Control) | 56 of 67, 46 of 100 | `ChangeZoneAllAi` casts it only when the opponent loses more value than the AI; Artifacts' own cheap artifacts are exiled too | left alone: the rule is sensible |
| Day of Judgment (Azorius Control) | 52 of 122 | `DestroyAllAi` sweeps when the opponent's creatures are worth 200 evaluation points more than its own, or when it would otherwise die next turn | left alone |
| Torch the Tower (Jund Sacrifice) | 31 of 61 | no target the damage kills. The AI does bargain (it pays every optional cost it can), so it shoots toughness-3 creatures when it has something to sacrifice | left alone |
| Seam Rip (Azorius Control, Azorius Momo) | 26 of 143, 13 of 32 | needs an opposing permanent of mana value 2 or less to be worth casting | left alone |

Each patch was measured as before (deck against the other ten, 100 games each, seed 1, without and
with; paired interval over the shared seeds in brackets):

| Deck (patch) | Without | With | Difference, 95% CI | Card cast in games seen | Mirror (200 games) |
|---|---|---|---|---|---|
| Boros Dragons (0009) | 64.5% (61–67%) | 66.0% (63–69%) | +1.5 (−2.7 to +5.7; paired −0.8 to +3.8), not reliable | 346 → 660 of 671 | 53.0% (46–60%) |
| Boros Dwarves (0010) | 74.5% (72–77%) | 74.4% (72–77%) | −0.1 (−3.9 to +3.7; paired −1.6 to +1.4), no effect | 284 → 408 of 444 | 48.0% (41–55%) |
| Mono-Green Landfall (0011) | 47.4% (44–50%) | 67.7% (65–71%) | +20.3 (+16.0 to +24.5; paired +17.7 to +22.9) | see below | 54.8% (48–62%) |

0009 and 0010 make the AI play the cards and are kept for that; they do not change a win rate.

**Why Boros Dwarves and Boros Dragons win.** The 1,650 game logs of that round robin were
parsed (`tools/log_analysis/`; the board state it reconstructs is approximate) to test the
obvious suspects, and they are not the cause:

- *Blocking.* Dwarves' attackers are blocked more than any other deck's (22% of attackers, 42%
  when the defender had an untapped creature), but 44% of those blocks are chump blocks and the
  attacker dies in only 21%. On the 208 turns Dwarves dealt lethal damage the defender had a
  blocker in 109 and blocked in 99. Dragons' fliers are blocked 6.5% of the time.
- *Removal.* Against Dwarves opponents see 1.61 removal cards a game and cast 79% of them (1.86
  and 78% against other decks), at a target quality of 0.99. Nothing is held or wasted.
  Lavaspur Boots' ward countered 21 of 119 spells or abilities because the AI targets without
  keeping the mana to pay; that is a real mistake, but 21 events in 300 games.
- *Card scripts.* Every main-deck card of the two decks matches its Oracle text, and equipment,
  double strike with trample and the pre-game Leyline Axe resolved correctly in the logs read.
- *Only beating badly piloted decks.* Against the seven decks not rated weak Dwarves still win
  66% and Dragons 59%.

What the logs do show is how much removal decides these games. Dwarves win 72% of the 225 games
in which the opponent cast at most one removal spell at their permanents and 45% of the 22 games
with three or more; 80% when at most one of their creatures left the battlefield, 44% when four
or more did. In 125 of 300 games the opponent cast no removal at all. The simulation is game one
of a match: no sideboards, and the opposing sideboards hold exactly what an equipment deck fears
(sweepers, artifact removal, three Clarion Conqueror in Azorius Momo). A best-of-three match is
won with probability p2·(2·p1 + p2 − 2·p1·p2) for a game-one rate p1 and a post-board rate p2:
70% in game one and 40% after sideboarding is a 49.6% match win rate, Dwarves' real figure. That
split is a hypothesis, not a measurement. Testing it needs hand-built post-board lists and an AI
that casts sweepers well (see Day of Judgment above), so it was not run.

**The Ba Sing Se bug.** The same reading found one real pilot error on the other side of those
games. `EarthbendAi.canPlay` approved Ba Sing Se's `{2}{G}, {T}: Earthbend 2` whenever the AI
controlled a land, so Mono-Green Landfall activated it in the first main phase of every turn
(4.35 times a game) and had no mana left for the permanents Forge's AI casts in the second. In
the 190 round-robin games where Landfall played Ba Sing Se it won 44.2% and cast Mossborn Hydra
in 31% of the games it saw one; in the other 110 it won 58.2% and cast it in 76%. Patch 0011
puts the activation off while a permanent in hand can be paid for. Against the other ten decks
Landfall rises from 47.4% to 67.7% (table above; 209 losses became wins and 6 wins became
losses), and games in which the card was cast, of 1,000, go from 340 to 502 for Mossborn Hydra,
295 to 534 for Icetill Explorer and 298 to 451 for Earthbender Ascension. The misplay report
could not see this: the mana was tapped by the cleanup step, so nothing counted as castable.

Leads from the logs that were not followed up: the AI attacks without counting equipment the
opponent has on the battlefield but not attached (`ComputerUtil.predictNextCombat` uses current
power; 20 to 45 of Dwarves' 208 kills followed such an attack), it casts instant-speed removal
in its own upkeep rather than in response to an equip, and the 20- to 22-land decks mulligan
in 51–63% of their games (Izzet Spellementals kept no two-land seven-card hand in 112). The
mulligan switch (`FLAT_MC_MULLIGAN`) was in the profile search and did not win there.

**The round robin with all eleven patches and a twelfth deck.** Four-Color Control (4.6% of the
field, real win rate 48.8%) was added from the Magic.gg article once the page could be read, and
the round robin replayed (`matrix decks/standard/meta -n 30 --seed 1`, 1,980 games, no time-outs
or errors):

| Deck | Real | Simulated | Gap |
|---|---|---|---|
| Boros Dragons | 45.0% | 63.9% | +18.9 |
| Boros Dwarves | 50.2% | 68.8% | +18.6 |
| Mono-Green Landfall | 53.4% | 67.0% | +13.6 |
| Orzhov Lifegain | 53.6% | 66.1% | +12.5 |
| Azorius Momo | 48.8% | 50.3% | +1.5 |
| Dimir Midrange | 54.5% | 54.2% | −0.3 |
| Azorius Control | 46.6% | 43.0% | −3.6 |
| Azorius Artifacts | 54.8% | 47.3% | −7.5 |
| Four-Color Control | 48.8% | 38.5% | −10.3 |
| Izzet Spellementals | 44.3% | 30.9% | −13.4 |
| Dimir Uldaros | 49.2% | 31.8% | −17.4 |
| Jund Sacrifice | 57.6% | 38.2% | −19.4 |

Rank correlation 0.23 (noise 0.08–0.36), Pearson 0.20 (0.09–0.30), mean absolute gap 11.4 points
(10.4–13.0). Over the eleven decks both runs share, and only the pairings among them
(`tools/calibration_diff.py`), against the eight-patch round robin:

| | Eight patches | Eleven patches | Difference, 95% interval |
|---|---|---|---|
| Rank correlation | 0.11 | 0.16 | +0.05 (−0.16 to +0.25) |
| Pearson correlation | 0.08 | 0.17 | +0.09 (−0.09 to +0.26) |
| Mean absolute gap | 10.8 pts | 11.5 pts | +0.7 (−1.3 to +2.8) |

Nothing here clears the noise. Fixing Ba Sing Se moved Mono-Green Landfall from 4 points under
its real win rate to 14 over (it now loses to Boros Dwarves 12–18 instead of 6–24) and took a few
points from most other decks, Boros Dwarves (70.0% → 67.3% on the shared pairings) and Dimir
Midrange (58.0% → 53.3%) among them. A deck the AI now pilots properly is one more creature deck
the simulation overrates, which fits the reading above: the remaining gap is less about cards
the AI cannot play than about game one without sideboards and about decks that need planning.

## Monte Carlo with a fixed budget (`--mc fixed`)

`--mc fixed` (and `ai_mc: fixed` per deck) is Forge's Flat Monte Carlo at its maximum-strength
settings with the clock taken out (Forge patch 0020 plus the driver): the search is counted in
rollouts, the AI timeout is out of reach, and nothing shrinks or pauses the search when the
machine is slow. Measured on 14–15 November 2026 in a private `MTGSIM_HOME` built from the pinned
Forge commit with patches 0001–0008 and 0020; all commands are `python3 -m mtgsim match` on
`decks/standard/meta/azorius-control.txt` and `boros-dwarves.txt` unless stated.

**The budget.** Per decision at most 3 plays the heuristics approve, 1 other target, 2 plays
they rejected and "hold", each sampled in 4 rounds, plus 2 rounds for the lines still in the race
after pruning; at most 100 rollouts per player per game turn. That is 28–42 rollouts for a full
decision; in practice pruning and short candidate lists bring the average to 6.8. It was chosen
to sit where `--mc max` lands on this machine, not tuned for strength: the same 40 games with
`--mc max` on 4 workers used 6.1 rollouts per decision and 385 per game (fixed: 6.8 and 444), with
47 decisions skipped for lack of turn budget and 13 cut short as too slow, the two things that
make its games depend on the machine. The turn budget is not optional: without it 3 of 40 games ran
into the 1,800 s time limit, because the search chose a play that could not be put on the stack
(an equip aimed by the search) again and again, up to 30,000 rollouts in one game; the clocked
modes are saved from this by their turn budget in seconds.

**Replay.** `-n 40 --seed 7 --mc fixed`, both seats searching: once with
2 workers, once with 1 and again with 2 (the last after a container restart, under a different machine load). All 40
games of each run were identical to the first, field by field (`tools/compare_games.py`), and so
were the rollout counts per game. No game timed out or had a failed rollout; Azorius Control won
16 of 40 (26–55%). An earlier pair of runs without the turn budget also agreed on all 28 games
both had finished.

**Games without Monte Carlo are unchanged.** `-n 200 --seed 1` on a build without patch 0020
with the previous driver, and on the build with 0020 and the new driver: 200 of 200 games
identical (`tools/compare_games.py`; Azorius Control 52–148 both times).

**Mirror.** Boros Dwarves against itself, `-n 100 --seed 5 --mc fixed`: 50–50 (50.0%, 40–60%),
52% on the play.

**Cost** (engine time per game is per worker; the machine was shared for part of these runs, so
times are within about ±25%, counts are exact):

| Games | Rollouts per game (mean / median / most) | Search time per rollout | Engine time per game (mean / median / longest) |
|---|---|---|---|
| Azorius Control vs Boros Dwarves, no Monte Carlo (200) | 0 | – | 2.3 s / 1.8 s / 12 s |
| Azorius Control `fixed`, Boros Dwarves default (200) | 178 / 158 / 832 | 0.10 s | 21.3 s / 13.4 s / 195 s |
| both `fixed` (40, three runs) | 444 / 370 / 1,834 | 0.08–0.11 s | 40–51 s / 25–32 s / 265–326 s |
| Boros Dwarves mirror, both `fixed` (100) | 292 / 255 / 1,065 | 0.14 s | 42.9 s / 29.3 s / 311 s |
| both `--mc max` (40, for comparison) | 385 / 350 / 780 | 0.10 s | 42.4 s / 37.8 s / 123 s |

A searching seat costs about 9 times the engine time of the default AI in this matchup, both
seats about 18–22 times; 86–93% of a game's time is search. The longest games are far below the
1,800 s limit that games with a `fixed` seat get. Every game with Monte Carlo now logs
`FlatMonteCarloStats.summary()` to its worker log and carries the counters in `games.jsonl`;
`tools/mc_cost.py RUN_DIR` prints the table rows.

**Pilot A/B: no reliable gain.** Azorius Control vs Boros Dwarves, `-n 200 --seed 1`, the same
deals in both arms; the opponent always plays the default AI. The `fixed` arm sets
`"ai_mc": "fixed"` for Azorius Control in a copy of the meta `gauntlet.json`.

| Azorius Control piloted by | W–L | Win rate (95% CI) |
|---|---|---|
| default AI | 52–148 | 26.0% (20–32%) |
| `fixed` Monte Carlo | 64–136 | 32.0% (26–39%) |

Difference +6.0 points, 95% interval −2.9 to +14.8 (p = 0.19); paired over the 200 shared deals
−1.0 to +13.0 (`tools/compare_arms.py`). Both intervals include zero, so this is not a measured
gain. It points the same way as the earlier 40-game `--mc max` comparison (17.5% → 32.5%), made
before the Empower patches lifted the default pilot in this matchup from 17.5% to 26%, and it is
now a result that can be re-run and extended game for game: telling a 6-point gain from zero
needs about 1,000 games per arm, roughly 3 hours on 4 idle cores for the `fixed` arm. Where the
search changed the heuristics' play in the `fixed` arm: 132 of 665 responses, 41 of 482 end-step
decisions, 16 of 93 after blocks, 8 of 447 attacks.

**Limits.** One matchup. The search still relies on Forge's evaluator and heuristic playouts
(`docs/stronger-ai.md`). Forge's `StormSolver` keeps a 4 s clock budget; it only runs for decks
Forge classifies as tutor-storm combo, none of which were played here. Whether rollout failures
replay was not observed (there were none in the 420 `fixed` games above). `fixed` needs a Java heap
above 768 MB (the default is 2 GB) and is refused otherwise.

These measurements were made on Forge with patches 0001–0008 and 0020. On the build that also
carries 0009–0011 the two properties were checked again: `match azorius-control boros-dwarves
-n 30 --seed 1` without Monte Carlo is identical, game for game, to the same pairing in the
twelve-deck round robin played before 0020 was applied, and 8 of 8 `--mc fixed` games (seed 7)
are identical with one and with four workers.

## Best-of-three with sideboards (16 November 2026)

The leading hypothesis for the creature decks' excess was that games are best-of-one without
sideboards: in the logs their results turn on how much removal the opponent draws, and sideboards
are where the rest of it is. `matrix decks/standard/meta -n 30 --seed 1 --bo3 --out runs/rr18-bo3`
played the 18 meta decks in a round robin of best-of-three matches, 30 per pairing (4,590 matches,
11,174 games, 2.3 hours on 4 cores, 0 errors or time-outs). Before games 2 and 3 each deck
sideboards against the other's main deck with Forge's `SideboardAdvisor`, and the loser of the
previous game starts. Its game 1s are the best-of-one round robin with the same seeds (a); the
match results are (b). On the original twelve decks the game 1s equal `runs/rr-final-12` game for
game (identical metrics: Spearman 0.23, gap 11.41, SD 13.34).

Metrics from `tools/calibration.py` (noise ranges in brackets; "weighted" weights opponents by
meta share). Real SD: 4.0 points for the 12 decks, 6.0 for the 18 (the six new decks' real rates
rest on 20–25 players each).

| | Spearman | Mean gap | SD | Weighted gap | Weighted SD |
|---|---|---|---|---|---|
| 12 decks, game 1s (a) | 0.23 (0.08–0.36) | 11.4 (10.4–13.0) | 13.3 (12.2–14.9) | 12.1 | 14.2 |
| 12 decks, matches (b) | 0.08 (0.01–0.23) | 16.7 (15.6–17.8) | 19.0 (18.1–20.3) | 17.6 | 20.1 |
| 18 decks, game 1s (a) | 0.18 (0.08–0.23) | 12.1 (11.4–13.1) | 14.5 (13.9–15.6) | 12.2 | 14.9 |
| 18 decks, matches (b) | 0.14 (0.04–0.16) | 16.0 (15.4–16.8) | 19.1 (18.5–19.8) | 16.6 | 19.8 |

Matches stretch win rates away from 50%, as the format must (a 60% game rate is about a 65%
match rate), so (b) alone cannot say whether the sideboards helped. The sideboarded games
themselves can: per deck, the game-level win rate in games 2 and 3 has SD 14.2 and gap 11.5
across the 18 decks, against 14.5 and 12.1 in the game 1s. The creature decks barely move (Boros
Dwarves 72.2% → 71.7%, Boros Dragons 62.9 → 63.0, Mono-Green Landfall 68.4 → 66.4, Orzhov
Lifegain 66.3 → 62.9) and of the underrated decks only Four-Color Control rises a little (39.0 →
41.8); Jund Sacrifice falls (39.4 → 33.3). Games 2 and 3 are not a random sample (game 3s come
mostly from close matches) and give the previous loser the play, which by itself pulls rates
towards 50%, so if anything this overstates what the sideboards do.

The same round robin without sideboarding (`--no-sideboard --out runs/rr18-bo3-nosb`, the same
seeds, game 1s copied from `rr18-bo3`, 1.4 hours for the later games) separates the format from
the sideboards:

| 18 decks | Spearman | Mean gap | SD | Weighted gap | Weighted SD |
|---|---|---|---|---|---|
| matches without sideboards | 0.16 (0.10–0.21) | 16.7 (16.1–17.5) | 19.6 (19.0–20.3) | 17.0 | 19.9 |
| matches with sideboards | 0.14 (0.04–0.16) | 16.0 (15.4–16.8) | 19.1 (18.5–19.8) | 16.6 | 19.8 |
| difference (`calibration_diff.py`) | −0.03 (−0.14 to +0.02) | −0.8 (−1.9 to +0.3) | −0.5 (−1.5 to +0.4) | −0.4 (−1.6 to +1.1) | −0.2 (−1.4 to +1.1) |

On the original 12 decks: without sideboards gap 16.5 and SD 18.9, with them 16.7 and 19.0 (gap
difference +0.2, −1.6 to +1.7). Per game, the unsideboarded games 2 and 3 have SD 14.6 and gap
12.3, the sideboarded ones 14.2 and 11.5, game 1s 14.5 and 12.1. So the format accounts for all
of the widening (14.5 → 19.6) and Forge's sideboards pull the decks back by about half a point,
an amount no interval separates from zero. **Best-of-one without sideboards is not why the
creature decks are overrated, as far as Forge's sideboarding can show.** It does not rule out
sideboards built the way people build them; the advisor's weak spots are in
`docs/ai-pilot-status.md`.

Determinism: of the 4,590 game 1s, 570 were replayed in the second run (a copy filter skipped
them), and `tools/compare_games.py --game1` finds 4,588 of 4,590 identical. Both differences are
Four-Color Control vs Grixis Reanimator (games 18 and 28): game 18 ended with seat 0 winning in 35
turns in one run and 42 in the other, and two fresh replays of that pairing with `--save-logs`
gave seat 1 in 27 turns, identical to each other. So that pairing's games depend on something
besides the seed, most likely state a worker keeps from its earlier games; every other pairing
replayed exactly. Not yet traced.

## The whole field: the meta decks against the "Other" decks (16 November 2026)

Real win rates are against the whole field, of which the 18 meta decks are 81.3%. The other 18.6%
("Other", archetypes below 1% each, 45.7% match win rate together) is stood in for by the thirteen
lists the Magic.gg article links (`decks/standard/fracture-2026-field/`, share split evenly). Each
meta deck played each of them, best-of-one, 30 games, seed 1 (`runs/field/<deck>`, 7,020 games, 1.8
hours, 0 errors or time-outs); the meta-vs-meta games are the game 1s of `runs/rr18-bo3`.
`tools/field_calibration.py "runs/rr18-bo3#game1" runs/field` weights every opponent by meta share:

| | Spearman | Mean gap | SD |
|---|---|---|---|
| 18 decks, against the meta decks only | 0.13 (0.08–0.24) | 12.2 (11.4–13.5) | 14.9 (14.1–16.2) |
| 18 decks, against the meta decks + field | 0.13 (0.10–0.23) | 12.0 (11.3–13.0) | 14.5 (13.8–15.5) |
| 12 decks, meta only | 0.14 (0.04–0.30) | 11.9 (10.9–13.4) | 14.1 (13.0–15.7) |
| 12 decks, meta + field | 0.14 (0.08–0.31) | 11.6 (10.7–12.7) | 13.6 (12.8–14.9) |

(Real SD 6.0 for the 18, 4.0 for the 12.) The field moves the spread by less than half a point, as
`tools/field_bound.py` predicted: it only changes a fifth of each deck's games. The meta decks win
56.6% of their games against it on average, and the field decks 43.4%, close to the real "Other"
45.7%. Inside the field the AI's usual bias shows again: Mono-Red Aggro wins 68.9% against the meta
decks, Selesnya Offense 63.1%, while Temur Omniscience (24.4%), Izzet Fling (23.5%) and Jeskai Control
(26.9%) lose most games. Against the field Jund Sacrifice does best of the underrated decks (53.1%)
and Azorius Momo gains 2 points; no deck's verdict changes.

**The closed field is not the explanation either.** With best-of-three (above) also ruled out, the
spread comes from the pilot: Forge's AI plays creature decks far better, relative to people, than
decks that win through planning.

## A random sample of the real field, best-of-three (17 November 2026)

A stricter version of the field test: instead of one list per small archetype, 100 lists drawn at
random from the 1,811 decklists of the three events the real win rates come from
(`decks/standard/fracture-2026-sample/`; draw, sources and the card-overlap archetypes in its README).
The sample has the field's real composition: 81 of the 100 are meta archetypes (real 81.3%), with
list-to-list variation inside them. Each meta deck played 6 best-of-three matches against each
list, Forge's sideboarding, seed 1 (`tools/sample_runs.sh`, `runs/sample/<deck>`, 10,800 matches,
0 errors; the pairing counts are in `decks/standard/fracture-2026-sample/baseline-bo3-n6-s1.json`).
Every list counts once. `tools/sample_calibration.py runs/rr18-bo3 runs/sample` compares the decks'
match win rates against the sample with their share-weighted match win rates against the other
meta decks (`runs/rr18-bo3`, the same format):

| 18 decks, best-of-three matches | Spearman | Mean gap | SD |
|---|---|---|---|
| against the meta decks only, share-weighted | 0.08 (0.04–0.17) | 16.6 (15.9–17.7) | 19.8 (19.0–20.7) |
| against the 100-list sample | 0.11 (0.05–0.17) | 15.8 (15.1–16.5) | 18.6 (18.0–19.3) |
| against the sample, mirrors left out | 0.11 (0.06–0.18) | 16.3 (15.6–17.0) | 19.1 (18.5–19.8) |
| sample minus meta-only | +0.03 (−0.07 to +0.10) | −0.9 (−2.2 to +0.1) | −1.2 (−2.4 to −0.2) |
| no-mirror sample minus meta-only | +0.04 (−0.07 to +0.11) | −0.3 (−1.8 to +0.6) | −0.7 (−1.9 to +0.3) |

(Real SD 6.0. Matches spread wider than games, as in "Best-of-three with sideboards": the same
comparison on game 1s of `runs/rr18-bo3` gives SD 14.9.) The realistic field narrows the spread by
about one point out of the thirteen it would need to lose, and with mirrors left out, as the real
win rates are, not beyond noise. The ranking does not change: Boros Dwarves 82%, Mono-Black Aggro
73%, Boros Dragons 72% and Mono-Green Landfall 78% against the sample; Jund Sacrifice 34% (real
57.6%), Dimir Uldaros 29%, Izzet Spellementals 32%. The largest single moves are Four-Color Control
(+9.5 points, 34.7 → 44.2), Jund Sacrifice (+9.1), Rakdos Lizards (+6.1) and Azorius Momo (+5.3):
against variant lists and the small archetypes they do better than against the 18 fixed lists,
without changing the overall verdict. **A bigger, realistic field does not explain the gap**; this
confirms `tools/field_bound.py` with real lists.

## The pilot: AI fixes and Monte Carlo search (16–17 November 2026)

Step 4 of the plan in `docs/ai-pilot-status.md`, after the format and the field were ruled out.
All gauntlets: the deck against the other 17 meta decks, best-of-one, seed 1; "paired" intervals
compare the same seeds with and without the change (`tools/compare_arms.py`).

### (i) Mana sinks and wrong-phase activations in the underrated decks

`tools/log_analysis/activations.py` on a `--save-logs` gauntlet of each of Jund Sacrifice, Dimir
Uldaros, Izzet Spellementals, Four-Color Control and Dimir Excruciator (30 games per pairing,
seed 1, 2,700 games). Three leads, one per deck; the two Dimir decks had none (Restless Reef is
animated in combat, Seasoned Cryomancer's draw in the second main phase).

| Patch | Card (deck) | AI error | Without | With | Paired difference |
|---|---|---|---|---|---|
| 0012, dropped | Umbral Collar Zealot (Jund Sacrifice) | "about to die" pays a sacrifice cost with creatures outside combat, for surveil 1 | 40.5% | 40.0% | −0.5 (−0.9 to −0.0) |
| 0013 | Stoke Genius (Izzet Spellementals) | "discard your hand, draw two" cast with any hand (219 of 249 casts discarded 3+) | 32.9% | 36.2% | +3.3 (+1.6 to +5.0) |
| 0014 | Great Hall of the Biblioplex (Four-Color Control) | permanent {5} animate paid in its own upkeep (398 times), tapping out for two turns | 42.1% | 54.2% | +12.1 (+9.9 to +14.4) |

0014 also covers Soulstone Sanctuary: Mono-Black Aggro −0.8 (−1.9 to +0.4) and Dimir Midrange
+0.6 (−1.0 to +2.2), both within noise, in the shipped version (third revision; the first cost
Mono-Black Aggro −2.8). Details in `mtgsim/forge_patches/README.md` and `pending/README.md`.

### (ii) `--mc fixed` A/B

Azorius Control with `ai_mc: fixed` on its own seat (a copy of the list with its own
`gauntlet.json`, `runs/mcfix/hero/`) against the default-piloted field, 60 games per opponent,
1,020 games per arm, seed 1, Forge with patches 0001–0011, 0013, 0014 (17 Nov 2026):

| Arm | Win rate |
|---|---|
| Default AI | 42.1% (39–45%) |
| `--mc fixed` for Azorius Control | 51.1% (48–54%) |
| Difference | **+9.0 points**, 95% CI +4.7 to +13.3; paired +5.7 to +12.4 (203 losses became wins, 111 wins losses) |

All 1,020 searching games finished (no time-outs); engine time 21.2 s a game (median 14.0 s,
longest 922 s), 238 rollouts a game, search 86% of the engine time (`tools/mc_cost.py`). The
earlier 200-game result (+6.0, −2.9 to +14.8) is confirmed: the counted search plays Azorius
Control better. It gained most against Dimir Midrange (43 → 62), Golgari Midrange (25 → 43),
Boros Dwarves (23 → 37) and Rakdos Lizards (37 → 50); nothing against Mono-Green Landfall, Dimir
Uldaros or Dimir Excruciator. Real win rate 46.6%.

The same A/B for the two decks the simulation underrates most (17 Nov, same setup):

| Deck (real) | Default AI | `--mc fixed` on its seat | Paired difference |
|---|---|---|---|
| Azorius Control (46.6%) | 42.1% (39–45%) | 51.1% (48–54%) | +9.0 (+5.7 to +12.4) |
| Jund Sacrifice (57.6%) | 40.1% (37–43%) | 50.4% (47–53%) | +10.3 (+7.3 to +13.3) |
| Dimir Uldaros (49.2%) | 30.0% (27–33%) | 43.7% (41–47%) | +13.7 (+10.4 to +17.0) |
| Boros Dwarves (50.2%), control | 73.7% (71–76%) | 76.7% (74–79%) | +2.9 (+0.0 to +5.9) |

The three underrated, planning-heavy decks gain 9–14 points beyond noise and move towards their
real win rates; the overrated creature deck gains about 3 (interval touching zero). Search helps
the decks the simulation underrates three to five times as much as the deck it overrates, which
is what a narrower spread needs. All 4,080 searching games finished without a time-out.

### (iii) Round robin with `--mc fixed` for every seat

The 18 meta decks, best-of-one, 20 games per pairing, seed 1, 3,060 games per arm, Forge with
patches 0001–0011, 0013, 0014 (17 Nov 2026): `matrix decks/standard/meta -n 20 --seed 1` with
and without `--mc fixed` (`runs/rr18-default`, `runs/rr18-mcfixed`; no time-outs or errors).
`tools/calibration.py` and `tools/calibration_diff.py`, 1,000 resamples:

| Share-weighted, 18 decks | Default AI | `--mc fixed` everywhere | B − A (95% interval) |
|---|---|---|---|
| SD (real 6.0) | 13.8 | 13.2 | −0.6 (−2.5 to +1.3) |
| Mean absolute gap | 11.5 | 10.6 | −1.0 (−2.5 to +1.2) |
| Spearman | 0.16 | 0.10 | −0.06 (−0.20 to +0.08) |
| Pearson | 0.34 | 0.28 | −0.07 (−0.19 to +0.07) |

Equal-weighted: SD 13.8 → 12.5 (−1.3, −2.6 to +0.3), gap 11.0 → 10.4 (−0.5, −2.1 to +0.9).
**Nothing changes beyond noise.** Searching on one seat against default opponents lifts the
planning decks by 9–14 points, but when the opponents search too most of that edge is gone:
Jund Sacrifice is still 18 points under its real rate (37.1% → 39.7% weighted), Dimir Uldaros
12 under; Mono-Green Landfall (+24) and Mono-Black Aggro (+25) end further over. The deck order
reshuffles (Orzhov Lifegain +10 → −1, Dimir Midrange −3 → −14, Boros Dwarves +21 → +14) without
coming closer to the real one. The one-seat gains measure "search beats the default AI", not a
pilot that plays these decks the way people do.

### (iv) A larger budget: `--mc deep` (option (b), 17 Nov)

`--mc deep` is the counted search of `fixed` at depth 8 (patch 0020, `Config.counted(depth)`: up
to 8 approved and 5 discovered lines, 2 target variants, 32 rounds plus 16, 800 rollouts a turn,
against 3 + 2, 1, 4 + 2 and 100 for `fixed`). It replays from the seed like `fixed`. The gate
before an all-seat round robin: is it stronger than `fixed` on one seat? Dimir Uldaros (the deck
`fixed` helped most) against the default-piloted meta, 30 games per opponent including the
mirror, 540 games per arm, seed 1, same seeds in every arm (`tools/deep_ab.sh`,
`runs/deepab/`; Forge with patches 0001–0011, 0013, 0014, 0020):

| Dimir Uldaros's seat | Win rate | Rollouts a decision | Engine time a game |
|---|---|---|---|
| Default AI | 32.0% (28–36%) | | |
| `--mc fixed` | 45.2% (41–49%) | 5.4 | 16.3 s (median 11.9) |
| `--mc deep` | 44.4% (40–49%) | 15.3 | 46.9 s (median 29.0, longest 1,189) |
| `fixed` − default | **+13.1** (paired +8.6 to +17.6) | | |
| `deep` − `fixed` | −0.7 (paired −3.6 to +2.1) | | |

`fixed`'s gain replicates the earlier +13.7. Nearly three times the rollouts buy nothing: 478 of
540 games end the same way with both, 29 losses become wins and 33 wins losses. The search is
saturated at `fixed`'s size; what limits it is the rollouts' own play (the heuristic AI plays
out every line) and the evaluation, not the number of samples. Since `fixed` on every seat did
not narrow the spread (iii), and `deep` does not even beat `fixed` on one seat, the all-seat
round robin (about 19 hours at 20 games per pairing) was not run. Budget is not the lever.

What this leaves: the two remaining levers in the plan, the format and the field (steps 1–3) and
a stronger pilot (this step), each move single decks but not the spread. The simulator's ranking of
these meta decks should be reported as it is: decided matchups and A/B differences between lists
of one deck are what mtgsim measures well; the meta win rates of a deck against the field are not.

## Calibration with fourteen patches (17 November 2026)

The standard calibration run after patches 0013 and 0014: `matrix decks/standard/meta -n 30
--seed 1` (`runs/rr18-cal`), 18 decks, best-of-one, 153 pairings, 4,590 games, Forge commit
7db198d72e with the fourteen shipped patches (combined hash e689217ab372); no time-outs or
errors. `tools/calibration.py runs/rr18-cal --reps 1000`:

| 18 decks | Equal-weighted (noise range) | Share-weighted (noise range) |
|---|---|---|
| Spearman | 0.14 (0.04–0.19) | 0.14 (0.03–0.21) |
| Pearson | 0.31 (0.24–0.36) | 0.30 (0.22–0.36) |
| Mean absolute gap | 11.4 (10.9–12.4) | 11.6 (10.7–12.8) |
| SD (real 6.0) | 14.0 (13.4–15.0) | 14.0 (13.3–15.2) |

It agrees with the 20-game default arm of (iii) within noise (share-weighted SD 13.8, gap 11.5,
Spearman 0.16). Over-rated by 18–23 points: Mono-Black Aggro, Boros Dwarves, Rakdos Lizards,
Boros Dragons; by 12–14: Mono-Green Landfall, Orzhov Lifegain. Under-rated by 14–19: Jund
Sacrifice, Dimir Uldaros, Dimir Excruciator; by 10–11: Azorius Artifacts, Izzet Spellementals.
Four-Color Control is now within 2 points of its real rate (38.5% against eleven opponents
before 0014, 50.0% against seventeen after; the fields differ, so the two figures are not a
paired comparison). `tools/update_calibration.py` wrote these figures into
`decks/standard/meta/gauntlet.json`; the table is in `decks/standard/meta/README.md`.

Patch 0020 was revised afterwards for `--mc deep` (combined hash 69b5119ef601). Replaying the first
3 games of every pairing (459 games, `matrix decks/standard/meta -n 3 --seed 1`) on that build
gives 459 of 459 games identical to this run (winner, turns, life totals), so the calibration
stands for the current patch set.

**Replay (21 November 2026).** The same command on a fresh container (`runs/rr18-cal`, 4,590
games, 0 errors) gives the same metrics (Spearman 0.14, mean gap 11.5, SD 14.0); two games came
out differently (Mono-Green Landfall and Four-Color Control one win more, Azorius Control and
Grixis Reanimator one fewer, 0.2 points each). The pairing table is now committed as
`decks/standard/meta/sim-matchups.json`.

## Swiss pairing (21 November 2026)

The real win rates come from Swiss events and are match results; the simulated ones are a round
robin of games. `tools/swiss_check.py runs/rr18-cal` turns each pairing's game rate p into a
best-of-three match rate p²(3 − 2p), plays simulated Swiss events (decks drawn by `meta_share`,
the 18.7% of the field outside the 18 decks as "other" beaten 50% of the time, paired by record
without rematches, 200 seasons) and computes each deck's match win rate with mirrors and byes
left out. Noise ranges: 100 bootstrap replicates of the games.

The real structure (checked 23 Nov; `--events real`): the article's rates are match win rates
"excluding mirror matches, byes, and draws" over 1,810 lists from three events. Arena
Championship 13 had 176 players and nine rounds of modified Swiss, in which a player stops at 7
wins or 3 losses (magic.gg viewer's guide). Magic Spotlight: Fracture had 775 players in Hartford
and 865 in Beijing, nine rounds, 18+ match points (6 wins) to day two, six more rounds (melee.gg
tournaments 440878 and 457663). The top 16 and top 8 playoffs are left out of the simulation.
"Other" (18.6% of the field) won 45.7% of its matches, so the meta decks beat it about 54–55% of
the time; the rate against "other" moves every deck equally and changes no metric here (0.50,
0.543 and 0.553 give the same SD, gap and sign errors).

| Event structure | SD | Mean gap | Spearman | Sign errors | Swiss minus round-robin matches, SD |
|---|---|---|---|---|---|
| round robin, games (the calibration) | 14.0 | 11.6 | 0.14 | 8 | |
| round robin, best-of-three matches | 14.7 | 12.2 | 0.14 | 8 | |
| **the three real events, "other" at 54.3%** | **11.4 (10.4–12.0)** | **9.3** | **0.11** | **8** | **−3.3 (−3.7 to −2.7)** |

Before the real structure was known, event structures were varied; they give the same reading:

| Event structure | SD | Mean gap | Spearman | Sign errors | Swiss minus round-robin matches, SD |
|---|---|---|---|---|---|
| Swiss, 600 players, 12 rounds | 11.2 (10.5–12.2) | 9.1 | 0.14 | 8 | −3.5 (−4.0 to −2.7) |
| Swiss, 300 players, 8 rounds | 12.2 | 10.0 | 0.11 | 8 | −2.5 (−3.0 to −1.3) |
| Swiss, 1,800 players, 15 rounds | 10.6 (9.9–11.4) | 8.6 | 0.11 | 8 | −4.1 (−4.7 to −3.4) |
| Swiss, 600 players, 14 rounds, cut to X-3 after round 8 | 11.6 | 9.6 | 0.14 | 7 | −3.1 (−3.7 to −2.3) |
| Swiss, 600 × 12, players drop at 4 losses | 12.2 | 10.2 | 0.14 | 7 | −2.5 (−3.0 to −1.6) |
| Swiss, 600 × 12, game rates as match rates | 9.4 | 7.8 | 0.14 | 8 | −1.9 (−2.4 to −1.3) |

(Real SD 6.0; every deck at 50% scores a mean gap of 4.7 with no sign errors. Shares and the
"other" assumption matter: with the field restricted to the 18 decks, `--no-other`, the round
robin of matches has SD 18.3 and Swiss 12.8.)

Reading: Swiss pairing is real and in the right direction. Winning decks meet winning decks, and
under the real events it takes 2.6 points of SD off the calibration's 14.0 (to 11.4; 3.3 off the
round robin of matches, the like-for-like comparison), about a third of the 8 points of excess.
It does not change the ranking (Spearman 0.11) or the sign errors (8 of 18): Boros Dragons 63.9%
(real 45.0), Boros Dwarves 69.0% (50.2), Jund Sacrifice 38.9% (57.6), Dimir Uldaros 32.7% (49.2).
Pairing explains part of the spread, not the ranking: the simulated matchups themselves are
wrong. Meta win rates should be reported as a simulated Swiss event of the real structure when
they are compared with real ones, which narrows the gap by about 2–3 points without any change in
play.

### Built into mtgsim: the reference metric (23 November 2026)

The comparison is now part of mtgsim (`mtgsim/calibration.py`): every `matrix` run whose decks have
`real_win_rate` and `meta_share` ends with it, and `python3 -m mtgsim calibrate RUN_DIR|TABLE.json`
recomputes it. The event structure is read from the gauntlet's `real_events` (the three events
above for `decks/standard/meta`), the rest of the field is beaten 50% of the time (the reading above:
that rate changes no metric), and a `--bo3` run's own match results are used instead of the
p²(3 − 2p) conversion. `tools/swiss_check.py` now runs on the same code and prints the same
numbers as before (checked on `sim-matchups.json` with `--events real` and two other option sets).
On the committed calibration table, `calibrate` gives:

| Line | SD (real 6.0) | Mean gap | Spearman | Sign errors |
|---|---|---|---|---|
| games, equal weights | 14.0 (13.2–15.0) | 11.5 (10.7–12.3) | 0.14 (0.04–0.18) | 9 |
| games, share-weighted | 14.0 (12.9–15.3) | 11.6 (10.4–12.9) | 0.14 (0.01–0.19) | 8 |
| best-of-three matches, share-weighted | 14.7 (13.4–15.4) | 12.2 (10.7–13.0) | 0.14 (0.01–0.19) | 8 |
| **Swiss, the three real events** | **11.4 (10.6–12.2)** | **9.4 (8.5–10.1)** | **0.11 (0.01–0.18)** | **8** |

(100 bootstrap replicates of 10 seasons; Swiss minus round-robin matches SD −3.3, −3.7 to −2.5.)
**From now on runs are compared on the Swiss line**; these are its baseline numbers for the
18-deck meta with fourteen patches. A change that does not move the Swiss SD or gap beyond these
noise ranges has not brought the simulation closer to the real results. The older figures in this
file are round-robin game rates and stay as they were measured.

## Decision probe: steps B and C (23 November 2026)

**Step B** is the run the cases are sampled from. The seven planning decks each played the six
creature decks with `--snapshots`, 10 games per pairing at seed 1, one `gauntlet` per planning
deck. All 420 games finished, and the snapshots hold 19,629 decision lines for both players. The
run is committed packed in `probe/run/probe-b.tar.xz`. The planning decks' records against the
creature decks, 60 games each:

| Deck | Win rate |
|---|---|
| Four-Color Control | 31.7% |
| Izzet Spellementals | 31.7% |
| Azorius Control | 26.7% |
| Dimir Midrange | 26.7% |
| Jund Sacrifice | 26.7% |
| Dimir Uldaros | 18.3% |
| Dimir Excruciator | 10.0% |

Each figure has an interval of about ±12 points.

**Step C** is 200 close decisions, written as plain-text cases and answered blind by fresh
Claude subagents. 175 are by the planning decks (25 each) and 25 by the creature decks; all ten
answers in a batch came from one subagent. `probe/README.md` covers how the cases were sampled
and written, how the answerers were kept blind, and what was done by hand (C100, C159).

The answers and Forge's choices agree on 102 of 200 cases, 51% (44–58%). For the planning decks
it is 85 of 175, 49% (41–56%); for the creature decks 17 of 25, 68% (48–83%). Agreement is
lowest on spell decisions: main phase 19 of 60 (32%), second main 3 of 16. Where they differ on
spells, the answer casts more than Forge 33 times and fewer 15 times. Combat and mulligan
decisions agree on 59–71%.

These figures measure difference, not quality: about half of the planning decks' decisions would
go another way under a model. Whether the other way is better is step D, where the user grades
the 98 disagreements blind. The gate is set in `docs/ai-pilot-status.md`. Gaps found in the cases and the
comparison (token text, choices made for cards such as Cavern of Souls' type, castable lists, Forge's targets not recorded) are
listed in `probe/README.md`, "Fix before step D", to be fixed and the cases re-answered first.

**Round 2 (24 Nov 2026).** The tracker gained token text, the choices made for each permanent
(`getChosen*`: Cavern of Souls' type and the rest), the targets of Forge's casts, the spells cast
this turn and the last, and spree / tiered mode costs in its castable check. Replaying step B with
it (`probe/run/probe-b2.tar.xz`) gave 420 of 420 games identical to the first run; the snapshots
differ only by the new fields and by Three Steps Ahead and Lively Dirge no longer counting as
castable without an affordable mode. The case builder rebuilt the same decisions (`--same-as`)
with the fixed text (tokens' abilities, "chose …" after a permanent, the recent spells, notes on
cost reductions, restricted mana and what history is missing, lands "you may play"). C128 and
C177 are gone: both were recorded only because Three Steps Ahead counted as castable with one
mana open. Twenty fresh subagents answered the 198 cases under the same rules; their transcripts
show each read only its own batch file.

| | Round 1 (200 cases) | Round 2 (198 cases) |
|---|---|---|
| all | 103, 52% (45–58%) | 102, 52% (45–58%) |
| planning decks | 85 of 175, 49% | 85 of 173, 49% (42–57%) |
| creature decks | 18 of 25, 72% | 17 of 25, 68% (48–83%) |
| main | 20 of 60 | 21 of 60, 35% (24–48%) |
| main2 | 3 of 16 | 2 of 15, 13% |

(Round 1 is re-scored here with the comparison's fix for spells an answer says it holds, which
moved C197 to agreement; its published 102 of 200 is the same data before that fix.)

The fixes do not move agreement. 183 of the 198 cases get the same verdict in both rounds. Of the
15 that change, one follows plainly from the new text (C175: the Treefolk tokens now show reach
and the answer no longer attacks), and the rest look like the answerer's own variation (mulligans
and blocks that go the other way on a second asking). So about one case in thirteen flips between
two askings of the same model: a single answer per case is a noisy measure, and step D's grades
inherit that. Of the agreeing spell cases where Forge targeted something, all 3 name the same
target; 10 of 15 agreeing `main` cases with casts differ in timing (Forge after combat).

**Round 3 (24 Nov 2026).** The tracker's castable check now applies the cost changes Forge would
apply on casting (Forge's own `CostAdjustment` requirement test and reduction step, read only;
convoke, delve, improvise and reductions whose size the player chooses left out), and the
snapshots split the open mana into free mana and mana with a spending rule (Cavern of Souls,
Great Hall of the Biblioplex, Tablet of Discovery), and record the abilities and triggers of this
turn and the last, this turn's conditions (crimes, life gained and lost, cards drawn, tokens,
creatures that died, sacrifices, discards) and the opponent's cards the player has seen
(`mtgsim/bridge/AGENTS.md`). Replaying step B (`probe/run/probe-b3.tar.xz`) gave 419 of 420 games
identical to the first run. The other, Four-Color Control against Orzhov Lifegain game 6, gave
18, 22 and 16 turns in five runs, including two on the old driver without snapshots: it does not
replay from its seed, like the two Four-Color Control games of the best-of-three check. The
snapshots differ from round 2's only by the new fields and by discounted cards (Eddymurk Crab,
Sapling Nursery, Sunderflock, Momo's Dragons, Hearth Elemental) added to castable lists, which
adds 71 decisions and removes none. All 198 decisions were found again; the only case from the
non-replaying game (C045) is at turn 5, before it diverges at turn 13. Of the 198 cases, 47 now
show restricted mana, 29 cards known in the opponent's hand, and 117 abilities or triggers; one
castable list changed (C162 gains Eddymurk Crab). Twenty fresh subagents answered; each read only
its own batch file. The comparison now stops reading casts at a cost or choice note ("collecting
evidence with Duress, ...", "discarding ...", "naming ..."), which moved C018 to agreement and no
case of rounds 1 or 2.

| | Round 2 (198 cases) | Round 3 (198 cases) |
|---|---|---|
| all | 102, 52% (45–58%) | 105, 53% (46–60%) |
| planning decks | 85 of 173, 49% (42–57%) | 90 of 173, 52% (45–59%) |
| creature decks | 17 of 25, 68% (48–83%) | 15 of 25, 60% (41–77%) |
| main | 21 of 60, 35% (24–48%) | 21 of 60, 35% (24–48%) |
| main2 | 2 of 15, 13% | 4 of 15, 27% (11–52%) |

Agreement is unchanged. 173 of 198 cases get the same verdict as in round 2; 25 flip (14 to
agreement, 11 away). One follows plainly from the new text: in C135 the opponent's hand is known
to hold Starscape Cleric, and the answer now evokes Deceit to take it, as Forge did. The rest
look like the answerer's own variation, as between rounds 1 and 2 (one case in eight here, one in
thirteen there). Every agreeing spell and counter case was read by hand; none is a false match,
though some still hide an unrecorded choice (Theorix Charm's mode in C102, evoke in C135 and
C189). Both agreeing spell cases where Forge targeted something name its target; 9 of 14 agreeing
`main` cases with casts differ in timing.

**Step D (25 Nov 2026): blind grading by Claude subagent judges.** At the user's request, the 93
disagreements of round 3 were graded by 20 fresh subagents instead of by hand
(`probe/round3/grading/`, `probe/README.md`, "Step D"). Each case showed Forge's and the answerer's
choice as an unnamed A and B, without the answer's reason. Each case was graded twice, by
different judges with A and B swapped.

| | answerer better | Forge better | no preference | answerer's share of decided (95% CI) |
|---|---|---|---|---|
| all (93) | 69 | 10 | 14 | 87% (78–93%) |
| planning decks (83) | 63 | 9 | 11 | 88% (78–93%) |
| creature decks (10) | 6 | 1 | 3 | 86% (49–97%) |

The judges show no position bias: A 82, B 85 and equal 19 of 186 grades. The two passes differ in
12 of 93 cases. In 7 cases Forge's choice named a card drawn later in the phase, which the judges
read as illegal. The case builder now marks such cards, and those 7 cases were regraded on the
corrected text; the table includes the regrade.

**What it means.** The judges share the answerer's model family, so this result cannot separate
better play from shared reasoning. It is an upper bound. That Forge wins 9 planning cases, several
of them clear answerer errors, shows the judges do not side with the answerer reflexively.

## The goldfish model

Unit tests check the opening-hand land counts against the exact hypergeometric distribution
and the mulligan rule against exact probabilities, and that a 17-land deck screws more and
floods less than a 27-land deck. 20,000 games of 8 turns take about 3 seconds. The engine
clock (`goldfish --clock`) for Mono-Red Burn: median kill on turn 5, 93% by turn 6 against an
opponent that does nothing.

## Problems found and fixed during validation

- Integration tests and `doctor` used two decks that could stall each other (Grizzly Bears
  could never attack into Hill Giants), so a game could run into the time limit; they now
  use decks that always finish.
- Fetch lands whose basic arrives untapped (Prismatic Vista) were modelled as tapped lands.
- Deck keys could collide for names such as "X", "X-2", "X".
- A harmless but alarming "Exception ignored" message could appear when a run ended.
- The matchup verdict said "a real edge" without saying for which deck.

## Not covered

- Commander and other multiplayer formats (out of scope for this version).
- Best-of-three with sideboarding: Forge's AI sideboarding was not evaluated.
- The meta decklists were transcribed from search results rather than read from the source
  pages; see `decks/standard/meta/README.md`.
