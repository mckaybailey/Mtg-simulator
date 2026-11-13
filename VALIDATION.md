# Validation

What was checked before mtgsim was handed over, how, and what came out. Engine runs used
Forge commit `7db198d72e` on a 4-core cloud machine; raw game files are not kept in the
repository, but every run can be reproduced with the commands and seeds below.

## Summary

| Check | Result |
|---|---|
| Unit tests (no Forge needed) | 187 pass |
| Integration tests (real games) | 4 pass |
| Same seed, different worker count | 40 of 40 games identical |
| Interrupted run, then `--resume` | 80 of 80 games identical to an uninterrupted run; no orphan processes |
| Mirror match (identical decks, 400 games) | 48.9%, 95% CI 44–54% (expected 50%) |
| Lopsided match (meta deck vs 40 lands + 20 Llanowar Elves) | 93.3%, CI 84–97% |
| A/B with a deliberately worse variant | detected: +12.5 points, CI +6.8 to +18.2, p < 0.001 |
| Simulated vs real meta win rates | weak agreement (rank correlation 0.24); see below |
| Engine failures | 0 crashes in about 4,100 recorded games; 1 time-out (a board stall in the mirror match), plus 1 in an early integration-test run |
| Fresh install (`setup --build` in an empty home, then `doctor`) | passes in about 2 minutes |

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
