# AI pilot project: where it stands

Handoff note for the next agent. Rewritten 2026-11-15 on branch `claude/ai-decision-engine`. The
goal of the project: make mtgsim's Forge AI play more like real players, so simulated meta win
rates track real ones. Numbers and methods are in `VALIDATION.md`; this note says what is done,
what was learned and what to do next.

## CHECKPOINT 23 Nov 2026, night (latest): probe steps B and C done; fix the case gaps, then step D. START HERE

**State of the repository.** Steps B and C and the fix list below are in pull request #11, from
branch `claude/relaxed-franklin-4vtvog` (open, not merged, as of this note). Everything before
them is on `main`. The step A work (#10) and everything before it
is merged.

**What the user asked (23 Nov).** Run step B, answer all 200 step C cases with subagents, write
the handoff, open a pull request with the documentation, and commit step B's run in it.
`runs/` is ignored, so the run is committed packed at `probe/run/probe-b.tar.xz` (1 MB, 38 MB
unpacked), with the script that played it.

**Step B: done.** 420 games: the seven planning decks against the six creature decks, 10 games
each, seed 1, `--snapshots`. It holds 19,629 decision lines. Details are in the previous
checkpoint and `VALIDATION.md`, "Decision probe".

**Step C: done.** Everything is in `probe/`; `probe/README.md` is the full account.

- `tools/probe/make_cases.py` sampled 200 close decisions. 175 are the planning decks' (25 a
  deck, stratified by kind) and 25 the creature decks' as a comparison group.
- Each case is plain text: the deciding player's visible state, both decklists, the options and
  an answer format. A card reference with Oracle text for every card named heads each batch of
  ten.
- Forge's choices are in a separate `probe/key.jsonl`.
- Twenty fresh Claude subagents answered one batch each. They read only their own file (checked
  in their transcripts), with no repository access, no hypothesis and no mention of Forge.
- `probe/answers.jsonl` holds the answers. Two cases were handled by hand: C159 was skipped and
  re-asked, and C100 was self-corrected.
- `tools/probe/collect.py` compares the answers with Forge's choices mechanically and writes
  `probe/merged.jsonl`.

**What it found: difference, not yet quality.**

| | Agreement with Forge |
|---|---|
| All 200 cases | 51% (44–58%) |
| Planning decks (175) | 49% (41–56%) |
| Creature decks (25) | 68% (48–83%) |
| Main phase | 32% |
| Second main phase | 19% |
| Combat | about 60% |
| Mulligans | 71% |

Where they differ on spells, the answer casts more than Forge 33 times and fewer 15 times.
When both cast the same spells, Forge often casts after combat and the answer before (7 of 11).
A disagreement is not a Forge mistake until it is graded. (An earlier version of this note said
C051 and C053 misread card abilities. They do not: Icetill Explorer allows lands from the
graveyard, and the case text was what misled.)

**Fix before step D (the user asked, 23 Nov).** `probe/README.md`, "Fix before step D", has the
detail and a suggested fix for each:

1. Eleven token names shown without abilities (Illusion, Pest, Monk, Robot, Treefolk and others).
2. The type named for Cavern of Souls not recorded (53 cases).
3. "Castable now" lists that ignore spree mode costs (C177) and cost reductions.
4. Main-phase option text that says lands come only from the hand.
5. No game history in a case.
6. Restricted mana counted as free.
7. The three name misreads in the comparison: fixed, but the 102 agreements are not yet read by
   hand.
8. Forge's targets not recorded, so 22 agreeing spell cases cannot be checked.
9. Timing compared loosely.

Items 1, 2, 3 and 8 need the tracker (`mtgsim/bridge/`), checked game for game as in step A.
Then re-run B, rebuild and re-answer C, and re-collect. Then step D.

**Next, after the fixes above: step D, the grading sheet** (plan below):

- Build a page from `probe/merged.jsonl` that shows each of the 98 disagreeing cases with the
  two choices as A and B in random order, unnamed. The answer's one-line reason must not show:
  it would name the model's side.
- The user marks A better, B better or equal. The 102 agreeing cases count as equal without
  grading.
- Use an Artifact with saved state, so the marks survive and can be read back.
- Report preference with intervals, by kind and for planning versus creature decks.
- The gate is unchanged: only a clear preference for the model on the planning decks'
  decisions (interval excluding 50%) makes the in-game step worth discussing.

Notes for D:
- Show the grader the case text as written (`text`), plus Forge's choice in the same answer
  format (`forge_text`).
- Forge's `main` choice lists casts with their phase, and some are instant-speed casts on its
  own turn. The answers mark timing in words. Both sides should be shown as written.
- The step D tally needs the grades only, not `agree`, which was computed from parsed text.

## CHECKPOINT 23 Nov 2026, evening: probe steps A and B done (superseded by the checkpoint above)

**State of the repository.** Everything is on `main`: step A (below) was merged by pull request
#10, the Swiss comparison by #9, the earlier work by #2–#8. No other branch holds unmerged work.
`runs/` is not committed; the check runs named below (`runs/snap2-*`, `runs/snapcheck-*`) may be
gone in a new container and are not needed.

**What the user asked (23 Nov).** Start the decision probe with step A, the driver snapshots; then
add four more decision kinds (the second main phase, the opponent's end step, the player's own
upkeep and draw step) before step B,
because B's run is what step C samples from. Not every step of the turn: untap holds no decision,
the other steps are recorded only when something is castable (empty lines would dilute the cases),
and `--save-logs` already has the play-by-play.

**Step A, driver snapshots: done.** `--snapshots` (any simulating command) writes
`RUN_DIR/snapshots/<a>__<b>__<game>.jsonl` (`_g2` / `_g3` for later best-of-three games): a header
line (`type` `game`: decklists and the result), then one line per decision with the deciding
player's visible state and Forge's choice under `forge`. Nine kinds; the full format is in
`mtgsim/bridge/AGENTS.md`, "Decision snapshots":

| Kind | When | Forge's choice |
|---|---|---|
| `mulligan` | each hand decided on | mulligan, or keep and the cards put on the bottom |
| `upkeep` | own upkeep, if an instant-speed card in hand is castable | what was cast in that step |
| `draw` | own draw step, once the card is drawn, if an instant-speed card is castable | what was cast in that step |
| `main` | first main phase, every turn | everything cast from then to cleanup (with the phase), lands, mana left at cleanup |
| `main2` | second main phase, if a card in hand is castable | what was cast and played in that phase |
| `attack` | declare attackers, if a creature could attack | the attackers and what they attacked |
| `block` | declare blockers, if attacked and a creature could block | the blocks |
| `counter` | an opposing spell cast while a castable counter that could target it was in hand | countered with which card, or passed (resolved / fizzled / left the stack) |
| `endstep` | the opponent's end step, if an instant-speed card in hand is castable | what was cast in that step (empty: held) |

Checked (`VALIDATION.md`, "Decision snapshots"): 90 of 90 seed-1 games of three pairings (Azorius
Control vs Boros Dwarves, Jund Sacrifice vs Mono-Green Landfall, Dimir Uldaros vs Orzhov Lifegain)
identical to the old driver's games in `runs/rr18-cal`, after each addition of kinds; 40 of 40 with and without snapshots, record for record; the lines agree with
the records (one `main` per turn taken, mulligans, kept hands of seven with as many bottomed as
mulligans; the draw line's hand is one card larger than the upkeep line's, 147 of 147); no tracker
errors, nothing unresolved. 69–100 KB a game. Tests: 3 unit tests in
`tests/test_experiment.py` (paths, the `snap=` field only when asked), an integration test on real
games; the suite is 318 tests.

How the format differs from the plan below, and why:
- A mulligan event fires only after the new hand is drawn, so each hand's state is captured as its
  cards are drawn and frozen when they go back to the library.
- Attack and block lines are taken when the declare step begins, before the declaration, and only
  when the player had a creature that could act; a step with no declaration gets an empty choice.
- `main` is taken once a turn; its choice covers the whole turn (including spells cast in response
  on the player's own turn). `main2` repeats the post-combat part as a decision of its own.
- A `counter` line counts as countered only when the player aimed a counter at that very spell; a
  spell that left the stack another way is `"left the stack"`.
- The draw step's event comes before the draw, so its line waits for the drawn card to reach the
  hand.
- `upkeep`, `draw`, `main2` and `endstep` use the tracker's castability check (`castableNow`): free mana sources,
  restrictions, targets; cost reductions are ignored, so a reduced spell can be missed, never
  wrongly listed.

**Step B, the logged run: done (23 Nov).** `probe/run/probe-b.sh` (the run itself is committed packed, `probe/run/probe-b.tar.xz`):
one `gauntlet` per planning deck against the six creature decks, `-n 10 --seed 1 --snapshots`,
into `runs/probe-b/<planning-deck>/`. 420 games, all finished; 420 snapshot files, 19,629
decision lines (main 6,629, main2 3,888, attack 2,931, upkeep 1,609, draw 1,276, mulligan 1,074,
block 895, endstep 527, counter 380; both players' decisions). Planning decks' records, 60 games
each: Azorius Control 26.7%, Four-Color Control 31.7%, Izzet Spellementals 31.7%, Dimir Midrange
26.7%, Jund Sacrifice 26.7%, Dimir Uldaros 18.3%, Dimir Excruciator 10.0%. If the run is gone in a
new container, unpack the archive (`tar -C runs -xJf probe/run/probe-b.tar.xz`) or rerun the script (seeded, about 20 minutes on 4 cores). **Next: step C**, sampling
cases from it (below). The run as planned: the seven planning decks against the six
creature decks, about 10 games per pairing, seed 1, with `--snapshots --out runs/probe-b` (420
games, about 5 minutes). Probably a `match` per pairing or a `gauntlet` per planning deck; a
`matrix` of all 13 would add the pairings within each group. Notes for step C:
- The header line carries the winner and the turn count; the case text must not.
- Ids in `state` are Forge card ids, stable within one game; use them to name attackers and
  blockers in a case, and give the options in words.
- `main` and `main2` choices are lists of what was cast, not single picks; a case should offer the
  realistic alternatives (cast X, cast Y, hold) and map Forge's list onto one of them.
- Close spots: `counter`, `upkeep`, `draw` and `endstep` lines are choices by construction (though
  in most of them casting now is plainly worse than waiting: sample them sparingly); for `main`, `attack` and
  `block` prefer lines with more than one castable card or more than one possible attacker.

## CHECKPOINT 23 Nov 2026, later: Swiss comparison built in; next is probe step A

**State of the repository.** Everything, including the work below, is on `main` (#2–#9; #9 merged
the Swiss comparison). No other branch holds unmerged work.

**What the user asked (23 Nov).** Make the Swiss comparison part of mtgsim and use it as *the*
metric to compare future iterations against. Done:

- `mtgsim/calibration.py` plays a `matrix` run's pairing results out as simulated Swiss events of
  the real structure and compares four lines with the real win rates (round-robin games equal and
  share-weighted, round-robin best-of-three matches, Swiss): SD, mean gap, Spearman, sign errors,
  bootstrap noise ranges. Every `matrix` run whose decks have `real_win_rate` and `meta_share` prints
  it and puts it in the report ("Against real win rates"); `python3 -m mtgsim calibrate RUN_DIR|TABLE`
  recomputes it or adds it to old runs. The real events' structure is `real_events` in
  `decks/standard/meta/gauntlet.json`. `tools/swiss_check.py` now uses the same code (same output).
- **The reference numbers to beat** (Swiss line, `calibrate decks/standard/meta/sim-matchups.json`,
  18 decks, fourteen patches): **SD 11.4 (10.6–12.2) against a real 6.0, mean gap 9.4 (8.5–10.1),
  Spearman 0.11 (0.01–0.18), 8 sign errors of 18.** A change counts only if it moves the Swiss SD
  or gap outside those ranges (better: `tools/calibration_diff.py`-style paired comparison on the
  same seeds; there is no Swiss version of that script yet, see below).
- Docs updated: root `AGENTS.md` (the goal now names the Swiss line), `README.md` (new section and
  command), `VALIDATION.md` ("Built into mtgsim: the reference metric"), `mtgsim/AGENTS.md`,
  `tests/AGENTS.md`, `decks/AGENTS.md`, `tools/README.md`, `decks/standard/meta/README.md`.

**Next.** Unchanged: the decision probe, starting with step A (driver snapshots) as laid out in
the checkpoint below. Two small optional follow-ups, not asked for: a paired Swiss difference
between two runs (`calibrate` on each gives independent noise ranges, which overstate the noise of
a difference on shared seeds); and `tools/update_calibration.py` writing the Swiss rate per deck
into `gauntlet.json` next to `sim_win_rate` (the `ai_pilot` ratings still use the round-robin rate).

## CHECKPOINT 23 Nov 2026: Swiss check done; next is the decision probe

**State of the repository.** Everything is on `main`: the Swiss tool, its results, the real event
structure and this checkpoint were merged by pull request #7 (`14c2fd9`); the AI-pilot work of
15–17 Nov by #2–#3. No other branch holds unmerged work. `runs/rr18-cal` (the replayed calibration) is not committed. Nothing
below needs it except re-deriving the audit numbers, and its pairing table is committed.

**What the user decided (21 Nov).** Option 2 of the 17 Nov checkpoint: the Swiss check, then the
LLM probe, with one change: **no API key.** The probe's decisions are answered by Claude subagents
spawned in the session, and graded by the user (or a separate grading agent if they prefer).
Running a model inside live games (option 2's probe step 3) is out of reach without a key and is
not part of the plan. It comes back only if the probe shows the model clearly beats Forge.

### Done

- **Swiss check** (`tools/swiss_check.py`, `VALIDATION.md` "Swiss pairing"). The calibration was
  replayed (`runs/rr18-cal`, the same metrics, two games of 4,590 differ) and its pairing table
  committed (`decks/standard/meta/sim-matchups.json`). The real win rates are match win rates
  without mirrors, byes and draws (the Magic.gg article; `magic.gg` is reachable, `www.magic.gg`
  is not). The three real events (176-player Arena Championship 13, play to 7 wins or 3 losses;
  Spotlight Hartford 775 and Beijing 865, 9 rounds, 6 wins to day two, 15 rounds; `--events
  real`) take the SD from 14.0 to 11.4 (real 6.0), Spearman 0.14 to 0.11, and leave the 8 sign
  errors. Pairing is a third of the excess spread, none of the ranking: the matchups are wrong.
  Rerun without games: `python3 tools/swiss_check.py decks/standard/meta/sim-matchups.json --events real`.
  Open (not asked for): mtgsim could report meta rates as a simulated Swiss event when it
  compares them with real ones.
- **Probe step 1, first pass** from the driver's misplay fields in `runs/rr18-cal/games.jsonl`
  (510 games per deck). Opposing spells let resolve with a castable counter in hand, against
  counters cast: Azorius Control 1,418 / 1,267, Four-Color Control 546 / 367, Izzet Spellementals
  296 / 455, Dimir Midrange 273 / 250. Instant-speed cards held unused through an opponent's turn,
  per game: Izzet Spellementals 1.84, Dimir Midrange 1.52, Four-Color Control 1.20, Azorius Control
  1.11, Jund Sacrifice 0.46, Dimir Excruciator 0.46, Dimir Uldaros 0.35. **The two worst sign
  errors, Jund Sacrifice and Dimir Uldaros, hold almost nothing**, so held answers do not explain
  them; their cases must be other decisions (attacks and blocks, sacrifice and engine sequencing,
  mulligans, what to cast).

### Next: the decision probe, in four steps

**A. Driver snapshots** (`mtgsim/bridge/ForgeBridge.java`; read `mtgsim/bridge/AGENTS.md` first).
The `--save-logs` logs record events, not hands, so there is no way to know what a player held
at a decision. Add an optional job field (for example `snap=PATH`, plumbed through `runner.Job`
and a CLI flag such as `--snapshots`) that appends one JSON line per decision point:
- *Decision points.* (1) An opposing spell is cast while the player holds a castable counter: the
  misplay code already detects this for `counter.passed`; record whether the spell was then
  countered. (2) The start of the player's first main phase: what was cast that turn and what
  mana was left open. (3) Declare attackers and declare blockers: the assignments made. (4) The
  mulligan decision: hand and keep or mulligan. Kinds (1) and (2) serve the control decks; (2),
  (3) and (4) serve Jund Sacrifice and Dimir Uldaros.
- *State, only what the deciding player may know.* Their hand; both battlefields (tapped,
  counters, power and toughness, attachments, summoning sickness); both graveyards; face-up exile;
  the stack; life totals; library and hand counts; turn, phase and whose turn; untapped mana
  sources. Also their own decklist and the opponent's deck name (players know their 75, and day
  two at the real events had open decklists). Never the opponent's hand or library order.
- *Forge's choice goes in the same line under a separate key*, so the case and the answer can be
  split later.
- *Snapshots must not change games.* Write them from the existing card tracker (it already sees
  these moments) and keep to its rule in `mtgsim/bridge/AGENTS.md`, "The tracker must not change
  how games play": read state only, no `MyRandom`, no AI memory, no `setActivatingPlayer`, no
  `ComputerUtilMana` payment checks (they can roll `MyRandom`); for "untapped mana" reuse the
  tracker's own free-source count. Check with
  `tools/compare_games.py` that a run with snapshots is game-for-game identical to one without
  (same seed), and add unit tests for the new job field beside the existing job-line tests in
  `tests/test_experiment.py` (`tests/AGENTS.md` first). Editing
  the Java source makes the next run recompile the bridge (cached by hash).

**B. A logged run.** Planning decks (Azorius Control, Four-Color Control, Izzet Spellementals,
Dimir Midrange, Jund Sacrifice, Dimir Uldaros, Dimir Excruciator) against the creature decks
(Boros Dwarves, Boros Dragons, Mono-Green Landfall, Mono-Black Aggro, Orzhov Lifegain, Rakdos
Lizards), about 10 games per pairing, seed 1, with snapshots. That is 420 games, about 5 minutes.

**C. About 200 cases, answered blind.** Sample them stratified by decision kind and deck, and
favour close spots (more than one sensible option; skip forced plays). Write each case as plain
text with the legal options listed. Keep Forge's choice in a separate key file. Give batches of
about 10 cases to fresh subagents with only the case text and an instruction to answer with a
choice and a one-line reason; they must not read the repository or know the hypothesis, or which
player is Forge. Save the answers to a file. It costs plan usage, not API money.

**D. Grading sheet.** For each case, the state and the two choices labelled A and B in random
order (Forge's and the model's, unnamed), and the user marks A better, B better or equal. A
page the user fills in is the natural form (an artifact with saved state). Report how often the
two agree, which is preferred by kind and by deck, with intervals. **Gate:** only if the model is
preferred clearly (interval excluding 50%) on the planning decks' decisions is the in-game step
worth discussing with the user (it needs an API key; costs in `docs/stronger-ai.md`, section 4).
If not, the remaining choice is option 1 of the 17 Nov checkpoint, repositioning mtgsim, whose
wording the user wants to review before it is committed.

## CHECKPOINT 17 Nov 2026: options discussed with the user; decision pending

**Read this first.** No code or runs changed in this session; it was a discussion with the user
about where to take the AI pilot after `--mc deep` failed (next section). The facts it rests on are
in the sections below and in `VALIDATION.md`; this records the conclusions, two corrections and
the options now on the table. **Ask the user which option to take before doing more work.**

**State of the numbers** (the calibration on `main`, commit `6be0cdd`, from `runs/rr18-cal`, 18 decks, 14 patches, 4,590 games): rank
correlation 0.14 (noise 0.04–0.19), mean gap 11.4 points, SD 14.0 against a real 6.0.
**Correction:** a pilot that put every deck at exactly 50% would score a mean gap of 4.7 points
(4.1 share-weighted), better than any simulation. SD and mean gap reward compression toward 50%
however it is achieved, so judge pilot changes on the ranking and on the sign errors (Jund
Sacrifice and Dimir Uldaros below 50%, Boros Dragons and Boros Dwarves above), and report the 4.7
baseline beside the gap. (An earlier remark in the discussion gave 3.5 from the old 12-deck table.)

**Conclusions of the discussion:**

- **Forge's AI is not a trained model**: about 80,000 lines of rules (156 `ability/*Ai` classes,
  attack/block controllers, card-script hints), a hand-weighted evaluator (card in hand 5, life
  point 2, a 2/2 about 150) and profiles of ~140 settings, many of them dice rolls. "Swap or upgrade
  the model" therefore means rewriting rules, the evaluator or the decision-maker. Settings were
  tuned (no effect), rules patched (one deck at a time), search tried at two budgets (`fixed`,
  `deep`): search is saturated because its playouts and evaluator, not its sample count, limit it.
- **Realistic win rates are a necessary check, not proof of human-like play.** Many pilots fit 18
  numbers (a coin flip fits the gap best), and real rates come from a population: mixed skill,
  skill correlated with deck choice, best-of-three with human sideboarding, metagame adaptation,
  noisy small decks (20–25 players each). Better checks: matchup-level results, game shape (length,
  kill turn, mulligans, counters held up), agreement on single decisions.
- **A skill spectrum** (seats of mixed strength) only shrinks rates toward 50% and keeps the
  ranking; with the calibration numbers a uniform shrink of 57% matches the SD but leaves Dragons
  above and Jund below 50%. It helps only if the upper levels play planning decks better than
  Forge, and search cannot supply that level. Any mix must be set from outside data (how much
  strong players outperform average ones), never fitted to the 18 rates.
- **An LLM (or SLM) for every decision is not viable as the engine.** `PlayerController` has 113
  abstract decision methods; about 30–80 decisions per player per game matter, ~100 calls a game
  with both seats (est.). At the per-decision costs in `docs/stronger-ai.md`: about $0.05 (Haiku
  5.5), $0.90 (Sonnet 5.5), $1.80 (Opus 5.5) per game, minutes per game instead of 2.8 s, a round
  robin in one to two days; answers do not replay from the seed (no temperature; needs a decision
  log). A small local model is not viable in this container (4 cores, 15 GB, no GPU) and has no
  training data (no human Constructed logs; Forge self-play is circular). LLM decisions are useful
  only for the 5–15 high-leverage decisions per game, or for a one-off study of a few hundred games.
- **Why planning decks lose** (Jund Sacrifice, Dimir Uldaros, Izzet Spellementals, Four-Color
  Control, Dimir Excruciator, Azorius Control): the evaluator scores held answers and open mana at
  almost nothing, the AI never plans across turns, and search scores with the same evaluator and
  plays out lines with the same heuristics. With search ruled out, a planning-aware evaluator is
  less promising than it looked (it would act mainly through search); the main untried lever is an
  LLM for the planning decisions.
- **Matchup and pairing structure.** Meta-share weighting and wider fields were tested and ruled
  out (sections below; `tools/field_bound.py`). Untested: Swiss pairing, mirrors in the real
  figures, deck choice and adaptation. Probably secondary, because the simulated matchups
  themselves correlate only 0.15 with the unverified real matchup figures.
- **An app** (user submits a list and a play guide): realistic as a tool for consistency
  (mulligans, colour screw, curve, goldfish kill turn: little dependent on the AI) and A/B
  comparisons of two lists; the guide could become mulligan rules and card priorities, later the
  prompt for LLM decisions (about $6 Haiku or ~$100 Sonnet per 1,200-game gauntlet on one seat,
  est.). Not realistic as a predictor of tournament win rates. Forge is GPL-3 (hosting is allowed;
  distributing a modified Forge requires source); card names and images fall under Wizards' fan
  content policy, which restricts charging.

**The options now (the user's decision):**

1. **Reposition mtgsim** (option (a) below, still the recommendation, stronger now that search is
   ruled out): a tool for comparing versions of one deck and for consistency, with the limits
   stated. The user wants to review the wording before it is committed.
2. **Swiss check, then the LLM probe**, before any more pilot work (pilot work: anything that
   changes how the decks are played, i.e. patches, settings, search, an LLM; as opposed to the
   format, the field or how results are reported). The Swiss check is the cheaper one and could
   weaken the case for spending days on the AI.
3. **More single-error hunting** (option (c) below): every fix so far moved one deck.

**The Swiss check** (not built; a small stdlib Python tool in `tools/`, an hour or two):
1. Needs the calibration's per-pairing table (153 pairings). The calibration itself is on `main`
   (commit `6be0cdd`), but only as per-deck averages (`gauntlet.json`, the meta README table,
   `VALIDATION.md` "Calibration with fourteen patches"); the pairing results live only in
   `runs/rr18-cal`, which is git-ignored and absent from a fresh container. Replay it first with
   `matrix decks/standard/meta -n 30 --seed 1 --out $PWD/runs/rr18-cal` (about an hour on 4
   cores; detached, see "Long runs" below; same seed, so the same games), and consider committing
   the exported pairing table (for example `decks/standard/meta/sim-matchups.json`) so later
   checks need no replay.
2. Convert each pairing's game win rate to a best-of-three match win rate (the real figures are
   match results; this widens the spread before Swiss narrows it).
3. Simulate about 1,000 events of the real size (~1,810 players) with decks drawn by real meta
   share: Swiss rounds paired by record, no repeat pairings, matches decided by the converted
   rates; optionally drops after several losses and a day-2 cut.
4. Compute each deck's win rate as the coverage does (check in the Magic.gg article whether
   mirrors and day 2 are included) and compare SD, mean gap, rank correlation and sign errors with
   the plain round robin and with the real rates.
Reading: if the SD falls far toward 6.0, part of the gap is how the real numbers are produced, and
mtgsim should report meta rates as a simulated Swiss event. If it falls little (expected), pairing
is ruled out and the matchups themselves are wrong. It cannot fix the ranking much.

**The LLM probe** (not built; needs an API key, which this environment does not have):
1. A decision audit of the planning decks from `--save-logs` games: turns tapped out on the AI's own
   turn while holding an instant it could have held up, counters and instant removal used versus
   held until the end, sweepers against creature counts, engines assembled versus parts drawn.
2. About 200 logged decisions (counter, hold up mana, sweep, mulligan), state limited to what the
   deciding player may know, answered by a model and read by a human; a few dollars.
3. Only if the model beats Forge on them: one call per turn to choose a plan (develop, hold up
   interaction, sweep, go for the engine) that Forge's rules carry out, ~10 calls per seat per
   game; driver design and costs in `docs/stronger-ai.md`, section 4. Gate: planning decks gain
   relative to creature decks with the change on every seat, then the 18-deck ranking and sign
   errors improve.

## CHECKPOINT 17 Nov 2026: step 4 (the pilot) done; no lever in the plan closes the gap

**Where things stand:** all four steps of the plan are done, and none brings the spread near the
real one. Format (best-of-three, step 2), field (13 "Other" decks, step 3; 100 real lists,
`VALIDATION.md` "A random sample") and pilot (step 4) each move single decks, not the spread.
Step 4, in `VALIDATION.md`, "The pilot":
- (i) `tools/log_analysis/activations.py` on the five underrated decks found three AI errors.
  Shipped: 0013 Stoke Genius (Izzet Spellementals +3.3) and 0014 Great Hall of the Biblioplex /
  Soulstone Sanctuary (Four-Color Control +12.1; Mono-Black Aggro and Dimir Midrange within noise,
  after two revisions). Dropped: 0012 Umbral Collar Zealot (−0.5). The Dimir decks had none.
- (ii) `--mc fixed` on one seat: Azorius Control +9.0, Jund Sacrifice +10.3, Dimir Uldaros +13.7,
  Boros Dwarves +2.9 points (1,020 games per arm, paired intervals exclude zero except Dwarves).
- (iii) 18-deck round robin, 20 games per pairing, with and without `--mc fixed` on every seat:
  share-weighted SD 13.8 → 13.2 (−0.6, −2.5 to +1.3), gap 11.5 → 10.6 (−1.0, −2.5 to +1.2),
  Spearman 0.16 → 0.10. Within noise: the one-seat gains vanish when the opponents search too.

**Update, later on 17 Nov: option (b) was tried and fails at the gate.** The user chose (b), a much
larger search budget. `--mc deep` (patch 0020 revised: the counted search at depth 8, still
replayable) uses 2.9 times the rollouts of `fixed` on one seat and wins no more: Dimir Uldaros
against the default meta, 540 games per arm, `fixed` 45.2%, `deep` 44.4%, −0.7 (paired −3.6 to
+2.1); `fixed` − default +13.1, replicating step 4 (ii). 478 of 540 games end the same way. The
search is saturated at `fixed`'s size: the rollouts' heuristic playouts and the evaluation limit
it, not the sample count. The all-seat round robin (~19 h) was therefore not run.
`VALIDATION.md`, "The pilot" (iv). What remains of the options below: (a), (c), or a different
kind of pilot change (better rollout policy or evaluation, which is real Forge AI work).
Decision with the user (17 Nov): the result is kept, not deleted, so the experiment is not
repeated. `--mc deep` stays as an experiment setting (it gives no better results than `fixed`;
`fixed` games are unchanged by it) and the branch `claude/intelligent-bohr-0rx7cq` goes to `main`
by pull request. Dropping the code later is safe: the experiment rebuilds from commit `8aa373d`.

**Done 17 Nov (later session): recalibration and user-doc facts.** `matrix decks/standard/meta
-n 30 --seed 1` (`runs/rr18-cal`, 4,590 games, 14 patches, no time-outs or errors): Spearman
0.14 (0.04–0.19), mean gap 11.4, SD 14.0 against a real 6.0, equal- and share-weighted alike.
`gauntlet.json` (all 18 decks now have `sim_win_rate` / `ai_pilot`; Four-Color Control weak →
fair, Izzet Spellementals weak → fair on the 10-point line, Azorius Artifacts fair → weak), the
meta README table, the facts in `README.md`, `AGENTS.md` and `VALIDATION.md` ("Calibration with
fourteen patches") are updated. The wider rewrite of `README.md` still waits for decision (a).

**A decision is pending with the user (17 Nov). Ask which one before doing more work:**

- **(a) Recommended: accept what mtgsim measures well and say so.** No more searching for realistic
  meta win rates. Rewrite the opening of `README.md` (and the caveat in reports, `mtgsim/report.py`)
  so mtgsim is described as a tool for A/B comparisons of one deck's lists (same opponents, same
  seeds: the pilot's bias largely cancels in the paired difference; plausible, not validated
  against real A/B data), decided matchups for the simulated pilots, and finding cards the AI
  misplays; not for predicting a deck's win rate against a real field. Quote the numbers: 18 decks,
  rank correlation 0.14, SD 14.0 against a real 6.0, mean gap 11.4 (calibration run); which decks are over- and
  underrated (AGENTS.md "Always pass on the limits"). The user wanted to review the wording
  before anything is committed: draft it, show it, then commit.
- **(b) A much larger search budget** than `--mc fixed`'s (about 100 rollouts a turn,
  `FLAT_MC_*` in patch 0020 and `ForgeBridge.java`). Costs grow with the budget (now 6–9 times the
  default AI per searching seat; an 18-deck round robin with 20 games per pairing took about 5.5
  hours with every seat searching). `--mc max` searches more but does not replay from the seed.
  Measure it the same way as step 4 (iii): `matrix decks/standard/meta -n 20 --seed 1` with and
  without, `tools/calibration_diff.py`.
- **(c) Keep hunting single AI errors** with `tools/log_analysis/activations.py` and `misplays`.
  Every fix so far moved one deck and not the spread.

**Long runs in the cloud container:** it stops within about 10 minutes of the session going idle
(scheduled check-ins every 10–15 minutes did not prevent it; `uptime` showed 0 minutes at each
wake-up). What works: start the run detached (`setsid nohup SCRIPT >> LOG 2>&1 < /dev/null &`)
from a script that resumes on its own, then stay in the turn with repeated foreground waits just
under the 10-minute tool limit (`timeout 580 bash -c 'until grep -q DONE LOG; do sleep 20; done'`).
`runs/` survives restarts; `/tmp` and the scratchpad may not.

**Runs behind the step 4 numbers** (git-ignored; replayable from the commands in `VALIDATION.md`,
"The pilot"): `runs/sinks/<deck>` (logs), `runs/p12-*`, `runs/p13-*`, `runs/p14*-*` (patch arms;
the without-arms were built on private Forge builds that included the dropped 0012),
`runs/mcfix-*` (one-seat search A/Bs), `runs/rr18-default`, `runs/rr18-mcfixed`.

## CHECKPOINT 16 Nov 2026: format and field ruled out; next is the pilot (step 4)

**Where things stand:** steps 1–3 below are done. Best-of-three with Forge's sideboards (step 2)
and a wider field of 13 "Other" decks (step 3) both leave the spread where it was (18 decks,
share-weighted SD about 14.5–14.9 against a real 6.0; mean gap about 12). The gap is the pilot.
**Start at step 4**, in this order (agreed with the user as the recommendation, not yet started):
(i) one cheap pass for mana sinks and wrong-phase activations in the underrated decks (Jund
Sacrifice, Dimir Uldaros, Izzet Spellementals, Four-Color Control, Dimir Excruciator), the Ba Sing
Se method; (ii) the `--mc fixed` A/B, Azorius Control with `ai_mc: fixed` against the default
field, about 1,000 games per arm, then Jund Sacrifice and Dimir Uldaros. Details under "Next
steps, in order of expected value" (items 2 and 3).

Runs behind the numbers (git-ignored, lost on a container restart, all replayable from seed 1):
`runs/rr18-bo3` and `runs/rr18-bo3-nosb` (commands in step 2 below) and `runs/field/<deck>`
(`tools/field_runs.sh`). Open issue: 2 of 4,590 game 1s did not replay, both Four-Color Control vs
Grixis Reanimator (step 2 below).

The history of this checkpoint follows.

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

**Steps 2 and 3 are done (below); start the next session at step 4, the pilot.**

### Step 2 done (16 Nov 2026, later session): best-of-three does not explain the gap

- `tools/calibration.py` takes `--game1` (reads `pairings_game1`) and `--only SLUGS`; it and
  `calibration_diff.py` (which reads `RUN#game1`) print SD and meta-share-weighted figures.
  `tools/compare_games.py` handles best-of-three ids and takes `--game1`.
- `runs/rr18-bo3` (with Forge's sideboarding) and `runs/rr18-bo3-nosb` (`--no-sideboard`, same
  seeds, game 1s shared) both finished, 0 errors. Numbers in `VALIDATION.md`, "Best-of-three with
  sideboards". **The format accounts for all of the widening (18 decks: SD 14.5 in game 1s, 19.6
  in matches without sideboards) and the sideboards pull back about half a point (19.1; difference
  −0.5, interval −1.5 to +0.4; gap −0.8, −1.9 to +0.3).** Per game, sideboarded games 2/3 have SD
  14.2, unsideboarded 14.6. Dwarves, Dragons and Landfall do not fall; Jund Sacrifice falls.
- So the leading hypothesis (best-of-one without sideboards favours the creature decks) is not
  supported, with Forge's `SideboardAdvisor`. Only a much better sideboarder could revive it.
- Game 1s on the 12 original decks equal `runs/rr-final-12` exactly.
- **Determinism crack:** 4,588 of 4,590 replayed game 1s identical; both differences are Four-Color
  Control vs Grixis Reanimator (games 18 and 28), and two fresh replays of game 18 agree with each
  other but not with either round-robin run. Likely state a Forge worker keeps between games, touched
  by some card in that pairing. Not traced; worth a look before relying on single-game replays there
  (play that pairing alone with 1 worker, then after other games, and diff `--save-logs` logs).
- **Next: step 3 is optional now.** `field_bound.py` says a field lowers the spread a few points at
  most, and best-of-three did not help, so the gap is the pilot (step 4). Ask the user whether to run
  step 3 anyway (cheap, about 4.5 h) or go straight to step 4.

### Step 3 done (16 Nov 2026): the whole field does not narrow the spread

- `decks/standard/fracture-2026-field/`: the 13 "Other" lists the Magic.gg article links (melee.gg,
  all pass `check`), 18.6% split evenly. The article links no more, so the field is 13, not 25.
- `runs/field/<deck>`: each meta deck against the 13, 30 games, seed 1, 7,020 games, 0 errors
  (`tools/field_runs.sh` replays or resumes it into `runs/field/`). `tools/field_calibration.py "runs/rr18-bo3#game1" runs/field`.
- 18 decks, share-weighted: SD 14.9 → 14.5, gap 12.2 → 12.0, Spearman 0.13 → 0.13 (all within
  noise; real SD 6.0). Numbers in `VALIDATION.md`, "The whole field".
- The field decks repeat the bias: Mono-Red Aggro 68.9% and Selesnya Offense 63.1% against the meta
  decks, Temur Omniscience 24.4%, Izzet Fling 23.5%, Jeskai Control 26.9%. Field decks average 43.4%
  (real "Other" 45.7%).
- **With format and field both ruled out, the gap is the pilot: go to step 4.**

### Step 3b done (17 Nov 2026, at the user's request): a 100-list random sample of the field, bo3

- `decks/standard/fracture-2026-sample/`: 100 lists drawn at random (seed 1) from the 1,811 lists
  of the three source events (melee.gg standings), archetypes assigned by card overlap; 81 are
  meta archetypes, as in the real field.
- `tools/sample_runs.sh` (N=6 bo3 matches per pairing, Forge sideboarding, seed 1) into
  `runs/sample/<deck>`; 10,800 matches. **Baseline for step 4 patches:**
  `decks/standard/fracture-2026-sample/baseline-bo3-n6-s1.json` (pairing counts and the
  `tools/sample_calibration.py` output), so a patch replays only the decks it changes.
- Against `runs/rr18-bo3` matches: SD 19.8 → 18.6 (difference −1.2, −2.4 to −0.2), gap 16.6 → 15.8
  (within noise), Spearman 0.08 → 0.11 (within noise); mirrors left out, SD −0.7 (−1.9 to +0.3).
  Real SD 6.0. Numbers in `VALIDATION.md`, "A random sample of the real field".
- The container sleeps about 10–15 minutes after the session goes idle and kills detached jobs
  (runs/ survives). A long run advances only while a turn is active: stay in the turn with
  foreground waits of at most 10 minutes, with a `send_later` fallback check-in.

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

2. **(Done, see above.) Experiments (a) and (b) in one run: the 18-deck round robin, best-of-three with sideboards.**
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

3. **(Done with 13 decks, see above.) A small field of about 25 decks (experiment (c)), only after step 2.** It makes the field
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

- All AI-pilot work, step 4 and the 100-list sample included, is on `main` (pull requests #2–#7;
  checked 23 Nov 2026). `claude/ai-decision-engine` no longer exists on the remote.
- `runs/` is git-ignored and does not survive a new container; every run can be replayed from its
  command and seed.
- The cloud environment "Mtg-simulator" allows `magic.gg`, `mtgdecks.net` and melee.gg. magic.gg
  and melee.gg work with plain `curl`; mtgdecks.net answers automated requests with a Cloudflare 403.

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

*(Superseded 17 Nov 2026: items 2 and 3 were done in step 4, see the CHECKPOINT at the top; the
next step is the user's decision listed there. Items 4 and 5 are still open leads.)*

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
