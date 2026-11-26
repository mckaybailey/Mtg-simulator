# Plan: Claude subagents make the hard decisions in real games (26 November 2026)

The decision probe (`probe/README.md`) showed Claude subagents choosing differently from Forge's AI
in about half of 198 logged decisions. Same-model judges preferred the subagents' choice in 88%
(78–93%) of the planning decks' decided cases. That figure is an upper bound, because the judges
share the answerer's model. The in-game step answers the question without a judge. The planning
decks play real games in which Claude makes their close decisions, and the result is a win rate.
This note is the plan for it. Nothing here is built yet.

## The question and the gate

**Question.** Does a planning deck that the simulator underrates win more when Claude makes its
close decisions? Forge's AI plays the rest of that deck's game and the opponent's whole game.

**Gate.** An A/B difference against the same deck played by Forge alone, with an interval that
excludes zero. The size matters as much as the sign. Jund Sacrifice wins 38.0% on the Swiss line
against a real 57.6%, so a gain of 5 points would not change the calibration's picture. A gain of
15 or more would.

## Which decisions go to Claude

These are measured on the 420 logged games of step B (`runs/probe-b3`, the planning decks against
the creature decks). A planning seat meets 24.3 decisions a game, and 19.9 of them pass the probe's
"close spot" filter (`tools/probe/make_cases.py`, `close_spot`). The median is 17.5 and the 90th
percentile 35.

| Kind | Close spots per seat-game | Step D grade (answerer's share of decided) | Version 1 |
|---|---|---|---|
| main (the turn plan from main phase 1 to cleanup) | 4.72 | 88% (73–95%) | yes |
| attack | 2.05 | 100% (65–100%) | yes |
| block | 0.92 | 100% (74–100%) | yes |
| endstep (instant on the opponent's end step, or hold) | 0.89 | 86% (49–97%) | yes |
| counter | 0.85 | 75% (30–95%) | yes |
| mulligan | 0.83 | 86% (49–97%) | yes |
| main2 | 4.51 | 62% (31–86%) | no: the turn plan already covers it |
| upkeep, draw | 5.18 | 2 cases | no: Forge decides, as today |

Version 1 hands over about **10.3 decisions per seat-game**. Forge still makes every other choice:
targets the plan does not name, the order of casting, triggers, mana payment, and modes. Only the
planning deck's seat gets Claude. The opponent is always Forge's default AI.

## How the game waits for an answer: replay to the next open decision

A Java game cannot keep running while a subagent thinks for minutes, and a JVM left blocked is
lost when the container restarts. The design uses the fact that a seed replays a game exactly
(4,588 of 4,590 games in the calibration replay):

1. The driver plays the game from its seed. At each Claude decision it looks up the answer in the
   run's decision log, keyed by game id and decision number.
2. At the first decision with no answer, the driver stops the game. It writes the case, which is the
   snapshot already taken at that moment, plus a state hash. The game's status is `pending`.
3. The orchestrator (the main session) gathers every pending case of the round. It turns them into
   case text with the probe's renderer (`make_cases.case_text`, so the answerers see what the
   probe's answerers saw) and hands them out in batches of about 10 to fresh subagents. Each
   batch's cases come from different games.
4. The answers are parsed into the driver's answer format and appended to `decisions.jsonl`. Then
   every pending game is replayed from its seed. It runs identically up to the answered decision,
   applies the answer, and goes on to its next open decision.
5. The round ends when no game is pending.

This gives reproducibility for free. `decisions.jsonl` plus the seed replays every game, and
`--resume` works. A restart loses at most the round in flight. The state hash catches a game that
does not replay. Such a game is dropped and counted, never patched. A game needs as many rounds as
it has Claude decisions, about 10 at the median and 18 at the 90th percentile. Replays cost engine
time, about 1.5 hours a stage on 4 cores. That runs while the next round's subagents think.

## How the driver applies an answer

The answer kinds and formats are the probe's, so the parser in `tools/probe/collect.py` carries
over.

- **mulligan:** keep or mulligan, and the cards to put on the bottom.
- **attack:** the attackers and what each attacks. The set is checked against Forge's combat
  legality.
- **block:** blocker-to-attacker pairs, checked the same way.
- **counter:** counter with a named card, or pass. On "pass" the AI may not cast a counterspell at
  that spell.
- **main and endstep:** a whitelist. Forge's AI may cast only the cards the plan names (and play the
  named land) until the plan's window ends. It casts them in its own order and timing. A target the
  plan names by id is used when it is legal. Otherwise Forge picks.

An answer that cannot be carried out falls back to Forge's choice for that item. Examples are a
card that is not castable, as in the probe's C005 (Uldaros with 6 of 7 mana), or a target that is
gone. Every fallback is logged with its reason, and the fallback rate is reported next to the win
rate. Fallbacks replay too, because they are deterministic.

The driver work extends the snapshot code (`mtgsim/bridge/AGENTS.md`, "Decision snapshots"). It
adds a controller for the Claude seat that overrides `PlayerControllerAi`'s mulligan, attack and
block declarations and its choice of spell to play. Two new job fields go with it: `decide=` (the
seat and the kinds) and `answers=` (the log path). There is one new result status, `pending`.

## Stages

**Stage 0: build and prove it without Claude.** This has no subagent cost.
- The driver hook, the decision log, the orchestrator loop (`tools/llm_pilot/`), and unit tests of
  the parser and the log.
- **Replay test.** A decider that always returns Forge's own choice, played round by round through
  the full replay loop, must reproduce the baseline games bit for bit. It runs on the 180 games of
  three planning decks used for the snapshot checks.
- **Enforcement test.** A decider that picks a different legal option, such as the second-best
  attacker set or a random legal block, must be carried out as given. A fallback is allowed only
  where the option really is illegal.

**Stage 1: a pilot of 30 games.** Jund Sacrifice, the most underrated deck at −19.6 on the Swiss
line, plays the six creature decks, 5 games each, seed 1. It has no counterspells, so the first
real run covers five of the six kinds.
- **Measures:** decisions per game, subagent minutes per batch, the parse failure rate, the
  fallback rate, replay divergences and total wall time.
- **Size:** about 300 decisions, or 30 subagent batches.
- **Purpose:** it checks the mechanics, not the effect. 30 games cannot show a difference.

**Stage 2: the A/B.** Jund Sacrifice against all 17 other meta decks, 15 games per pairing, seed 1:
255 games.
- **Baseline arm:** the same games played by Forge alone. Those are games 1–15 of each Jund pairing
  in the calibration run `runs/rr18-cal`, so they need no new games if the job ids and seeds match.
  Stage 0 checks that they do.
- **Size:** about 2,600 decisions, or about 260 subagent batches.
- **Precision:** each arm is ±6 points. The difference is about ±9 points, because the games share
  seeds but diverge after the first changed decision.
- **What it shows:** a gain of 15 or more is clear. One of 9 or more counts as a reliable gain. Half
  as many games would leave about ±12 on the difference.

**Stage 3: only if stage 2 shows a reliable gain.**
- Dimir Uldaros (−17.7, holds counterspells), the same way.
- Put the two decks' new pairing results into the Swiss calibration (`calibrate`, as a new pairing
  table) and see whether the spread (11.4) and the rank correlation (0.11) move beyond noise. That
  is the project's metric.
- After that, decide whether the other planning decks are worth the same treatment.

## Cost, time and limits

- **Subagent volume:** stage 1 is about 30 batches, stage 2 about 260, stage 3 about 260 per deck.
  The minutes per batch are unknown until stage 1 measures them. At an assumed 3–6 minutes and 10
  at once, stage 2 takes 1.5–3 hours of subagent time, plus replays that overlap it. All of it runs
  against the session's plan, not an API key. The model is the session's (no override), and each
  answer logs which model gave it.
- **The session must stay open while a stage runs.** The orchestrator is the main session, and the
  container stops about 10 minutes after the session goes idle. Every round's state is on disk.
  `decisions.jsonl` is committed after every few rounds, so a new container can resume the stage
  from the log.
- **Hidden information.** A case shows only what the deciding seat could know. This is the probe's
  rule and the probe's renderer, already audited.
- **What a gain would and would not mean.** Claude pilots only about 10 decisions a game, and
  Forge's heuristics make the hundred-plus others around them. A gain shows that these decisions
  were costing the deck. No gain means either that they were not, or that the rest of Forge's play
  still loses the game. A gain also does not make the simulator a cheap tool. Each Claude-piloted
  game costs minutes of subagent time, so this is a measurement, not a new default pilot.

## What needs deciding before stage 0

1. **The deck.** The proposal is Jund Sacrifice (largest gap, no counterspells), then Dimir
   Uldaros. Azorius Control has the most counter and hold decisions but is already within 3 points
   of its real rate.
2. **The game budget for stage 2.** The proposal is 255 games, ±9 points on the difference. 500
   games per arm would give about ±6.
3. **Whether to skip probe option 1,** your own grading of about 20 cases. The in-game result does
   not depend on the judges, so this plan does not need it. It would still show early whether the
   88% is believable before the subagent time is spent.
