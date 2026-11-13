# Validation

What was checked before mtgsim was handed over, how, and what came out. Engine runs used
Forge commit `7db198d72e` on a 4-core cloud machine; raw game files are not kept in the
repository, but every run can be reproduced with the commands and seeds below.

## Summary

| Check | Result |
|---|---|
| Unit tests (no Forge needed) | 229 pass |
| Integration tests (real games) | 4 pass |
| Same seed, different worker count | 40 of 40 games identical |
| Interrupted run, then `--resume` | 80 of 80 games identical to an uninterrupted run; no orphan processes |
| Mirror match (identical decks, 400 games) | 48.9%, 95% CI 44–54% (expected 50%) |
| Lopsided match (meta deck vs 40 lands + 20 Llanowar Elves) | 93.3%, CI 84–97% |
| A/B with a deliberately worse variant | detected: +12.5 points, CI +6.8 to +18.2, p < 0.001 |
| Simulated vs real meta win rates | weak agreement (rank correlation 0.24); see below |
| Engine failures | 0 crashes in about 4,100 recorded games; 1 time-out (a board stall in the mirror match), plus 1 in an early integration-test run |
| Fresh install (`setup --build` in an empty home, then `doctor`) | passes in about 2 minutes |
| Forge patches (fresh build with patches, then changed patch sets) | applied, recorded and rebuilt exactly as designed; see below |
| Misplay tracking does not change games (same seed, original vs new driver) | 60 of 60 games identical; see below |

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

**A stronger AI helps, at a price.** Azorius Control vs Boros Dwarves, 40 games each way:

| AI | Control's win rate | Time |
|---|---|---|
| Default | 17.5% (7–33) | 1.3 min |
| `--mc max` (Monte Carlo look-ahead) | 32.5% (13–27) | 7.5 min |

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

## Speed

Average engine time per game was 2.8 s across the meta round robin (slowest deck, Azorius
Artifacts, 4.1 s). With four workers that is about 85 games a minute: the 550-game sample
gauntlet (a casual deck against all eleven meta decks, 50 games each) took 6 minutes. Each worker
uses about 0.9–1.2 GB of memory.

## Forge patches

`setup --build` applies the patches in `mtgsim/forge_patches/` (none ship yet). The mechanism
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

These are pointers for reading card scripts and AI code, not measured misplays. No experiment
has yet shown that fixing one of them changes a win rate.

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
