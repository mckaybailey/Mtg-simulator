# Validation

What was checked before mtgsim was handed over, how, and what came out. Engine runs used
Forge commit `7db198d72e` on a 4-core cloud machine; raw game files are not kept in the
repository, but every run can be reproduced with the commands and seeds below.

## Summary

| Check | Result |
|---|---|
| Unit tests (no Forge needed) | 273 pass |
| Integration tests (real games) | 6 pass |
| Same seed, different worker count | 40 of 40 games identical |
| Interrupted run, then `--resume` | 80 of 80 games identical to an uninterrupted run; no orphan processes |
| Mirror match (identical decks, 400 games) | 48.9%, 95% CI 44–54% (expected 50%) |
| Lopsided match (meta deck vs 40 lands + 20 Llanowar Elves) | 93.3%, CI 84–97% |
| A/B with a deliberately worse variant | detected: +12.5 points, CI +6.8 to +18.2, p < 0.001 |
| Simulated vs real meta win rates | weak agreement: rank correlation 0.11 with the Forge patches (0.24 before, within noise of each other), mean gap 10.8 points (13.0 before); see below |
| Engine failures | 0 crashes in about 4,100 recorded games; 1 time-out (a board stall in the mirror match), plus 1 in an early integration-test run |
| Fresh install (`setup --build` in an empty home, then `doctor`) | passes in about 2 minutes |
| Forge patches (fresh build with patches, then changed patch sets) | applied, recorded and rebuilt exactly as designed; see below |
| Misplay tracking does not change games (same seed, original vs new driver) | 60 of 60 games identical, then 1,650 of 1,650 over the whole round robin; see below |
| Forge patches for cards the AI never cast | Azorius Control +25.4 points (CI +21.3 to +29.4), Azorius Momo +9.3 (+4.9 to +13.6), Dimir Uldaros +3.8 (not reliable); mirrors 50–54% |
| Profile tuning on the meta (16 candidates, 12,010 games, 2 decks held out) | no profile beats Forge's default beyond noise (training rank correlation +0.18, noise −0.20 to +0.43; held-out gap −0.8 points, noise −5.8 to +4.7); none shipped |

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

`setup --build` applies the patches in `mtgsim/forge_patches/` (eight ship; see "Fixing the cards the
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
