# A stronger pilot for mtgsim: three options

*Design note, November 2026; nothing here is implemented. "est." marks estimates and
extrapolations; other figures come from `VALIDATION.md` or from default-AI meta games run in this
environment. Forge paths are relative to `~/.mtgsim/forge/forge-ai/src/main/java/forge/ai/` at the
pinned commit (`FORGE_PINNED_REF`, 7db198d72e).*

## 1. The problem, and how to tell when it is solved

In the 1,650-game meta round robin, simulated win rates barely track real ones (Spearman 0.24).
Three numbers from the same table describe the failure better: the mean absolute gap is 13.0
points; the simulator spreads the decks 3.9 times too wide (standard deviation 16.2 points
against 4.2); the three `weak` decks come out 17–27 points low, the three `strong` ones 13–25
high. Spearman over 11 decks cannot steer anything: at 0.24 its 95% interval is about −0.44 to
0.74. Acceptance tests should be, in order: (1) a **pilot A/B**: the same list with the new pilot
vs the default one, against the default-piloted field (the existing stratified `ab` comparison;
seeds come from deck contents, so both arms get the same deals); (2) mean gap and spread ratio
over a round robin; (3) Spearman, reported, not a gate. There are floors: a deck's round-robin
rate is known to ±5.7 points, and the real figures are best-of-three human matches with
sideboards. With only 11 real numbers, nothing may be tuned against them without a hold-out (the
next meta snapshot).

The one search measurement so far: Azorius Control vs Boros Dwarves went from 7/40 (Wilson
9–32%) to 13/40 (20–48%) with `--mc max`, p ≈ 0.12. Suggestive, not established.

The code shows why creature decks win. `simulation/GameStateEvaluator.java` scores a card in hand
at 5 points (an opposing one at −4), a life point at 2, a 2/2 at about 150 and other permanents at
50 + 30 × mana value, so scoring a position at the end of a turn favours deploying bodies over
holding answers (`simulation/StrategicEvaluator.java` corrects part of this, inside Monte Carlo
only). `ability/CounterAi.java` counters by mana-value thresholds and dice rolls
(`CHANCE_TO_COUNTER_CMC_1..3`). Blocks (`AiBlockController`) and mulligans
(`simulation/OpeningHand.java`, a deck-plan score) are never searched.

## 2. Option 1: a search-based player inside Forge

**Flat Monte Carlo** (`simulation/FlatMonteCarloPicker.java`, `--mc on|max`).
`AiController.chooseSpellAbilityToPlay` keeps the first few plays the heuristics approve, adds
legal plays they rejected, a HOLD option (pass with mana up) and alternative single targets, and
lets `FlatMonteCarloPicker.choose` compare them. Modes: MAIN (own main phase, land drop
included), RESPOND (spell on the stack or opposing combat), END_STEP, BLOCKED (tricks after
blocks) and, at `max`, ATTACK (up to six attack sets: heuristic, none, all, one more or fewer).
Each sample copies the game (`GameSimulator.forRollout` → `GameCopier.makeCopy`: new `Match` and
`Game`, every card of all seven zones cloned), re-deals the cards the AI cannot see
(`HiddenInfoShuffler`: each player's hidden hand and library cards are pooled and shuffled, a
uniform determinization that ignores what the opponent's play has revealed), plays the candidate,
lets the heuristic AI finish the turn and the combat, and scores the second main phase with
`GameStateEvaluator` + `StrategicEvaluator`; at `max` half the value comes from the position after
the opponent's next turn, played by its heuristics. Candidates share seeds, weak lines are
pruned, and an override needs a margin (80 points) and a majority of paired samples. It is one
ply: no tree, and the opponent never chooses, it follows its heuristics.

**Full simulation** (`simulation/SpellAbilityPicker.java`, `SimulationController`,
`SpellAbilityChoicesIterator`, `PossibleTargetSelector`): a depth-3 search over chains of the AI's
own plays in one priority window, enumerating targets, modes, X and card choices, plus "act now or
after blockers". It takes over spell choice for a player created with
`AIOption.USE_FULL_SIMULATION`, which `GamePlayerUtil.createAiPlayer(name, 0, 0, options, profile)`
accepts, so the driver could offer it in a few lines. Its copies are not determinized (draws see
the real library), and it does not search combat, mulligans or responses (`GameSimulator.COPY_STACK`
is false).

**Why `--mc` games do not replay.** Seeds are deterministic (`baseSeed = MyRandom.nextLong()`,
round `r` uses `baseSeed + r × SEED_STEP`), but how much gets evaluated depends on the clock: the
decision and turn budgets (1.5 s and 6 s at `max`), `affordableLines` (cuts candidates after timing
the first rollout), deadlines between rollouts, `AITimeoutTracker` (`Game.AI_TIMEOUT` = 5 s; 2 s in
copies) and a slowness circuit breaker (`AiController.noteFlatMcOutcome` pauses Monte Carlo for 3,
6 or 9 turns). A budget counted in rollouts would replay from the seed.

**Cost.** Not measured per rollout. In the validation run 40 games took 1.3 min on 4 workers by
default and 7.5 min with `--mc max`: about 8 s and 45 s of worker time per game, or ~1.9 s of
search per AI turn (est.; players take ~10 turns per game here). The default AI spends ~0.14 s per
game turn and a rollout replays the rest of a turn (at `max` the opponent's too) from a fresh copy,
so a rollout costs roughly 0.05–0.3 s (est.), and at `max` the 1.5 s budget, not the configured 8
lines × 14 rounds, is the limit. `FlatMonteCarloStats.summary()` reports rollouts and decision-time
percentiles; logging it is the first measurement to take.

**Designs.**
- **1a. Deterministic Monte Carlo**: the same picker with a rollout budget (say 4 lines × 6
  rounds), no deadlines, no device scaling, no circuit breaker. The driver gets close alone
  (`Game.AI_TIMEOUT` is a public field; counts and budgets are `FLAT_MC_*` profile properties,
  budgets capped at 10 s and 60 s); removing the last clock checks needs a small Forge patch
  applied by `setup --build`, or an upstream option.
- **1b. Targeted search**: only where heuristics fail: per deck (`ai_mc` exists), per decision kind
  (`FLAT_MC_REACTIVE`, `FLAT_MC_ATTACK`), and blocks (new). Mulligans fit search badly (a sample is
  a whole game) and belong to Options 2 or 3.
- **1c. Determinized ISMCTS**: single-observer search to the end of the opponent's next turn. Each
  iteration copies the root once, re-deals with a seeded `HiddenInfoShuffler`, descends a tree of
  abstracted actions (top heuristic plays plus HOLD for the AI; top responses, attack and block
  sets for the opponent), finishes with a heuristic playout and scores with the evaluator. Nodes
  hold action paths, not game copies (a copy is a whole game; a JVM has ~1 GB). An iteration budget
  and a seed from `MyRandom` keep it reproducible. The Flat Monte Carlo hooks are private
  `AiController` methods, so it needs a Forge patch or a driver-installed `PlayerControllerAi`
  subclass (section 4) overriding `chooseSpellAbilityToPlay`, `declareAttackers`, `declareBlockers`.

**Assessment.**
- *Effort:* 1a 2–4 person-days; 1b 1–2; 1c 15–30, plus upkeep at every Forge pin bump.
- *Gain:* 1a plays like `--mc max` (the unconfirmed +15 above) but becomes usable for A/B tests,
  `--resume` and replays; meta-wide unknown (a guess: mean gap 9–11 instead of 13). 1c can weigh
  the opponent's choices, which is what holding up a counter is about, but inherits two caps: 5
  points per card in hand, and playouts by the heuristics that misplay control. Without a better
  evaluator, deeper search may sharpen aggro decks as much as control decks.
- *Compute (est.):* 1a at ~6× is ~17 s per game, ~8 core-hours or ~2 h on this 4-core machine per
  1,650-game round robin; 1c at 20–50× is 26–64 core-hours, 6.5–16 h. The cost is wall clock, not
  money.
- *Needs:* Java (driver, probably a Forge patch); no data, no keys.
- *Risks:* copy fidelity (copies are only verified with assertions on; unsimulatable cards are
  counted in `FlatMonteCarloStats`); `SpellAbility.hashCode` includes `SpellAbility.class.hashCode()`,
  which differs per JVM, so search code that iterates hash sets of abilities, or reads the clock,
  breaks replay; `MyRandom` is global, so no parallel rollouts within a game; coupling to Forge
  internals.

## 3. Option 2: a learned player

**Data.** No human Constructed data exists here. `--save-logs` keeps Forge's text play-by-play;
`games.jsonl` has outcomes, mulligans and per-card seen/played counts; neither holds states. As far
as I know (not checked from here), 17lands publishes Arena *Limited* data only (picks, game
records, turn summaries), and tournament sites publish decklists and match results, already used
for validation. So: self-play, with a feature dump at each turn start added to the driver's
`Tracker`. 100,000 default-AI games ≈ 78 core-hours ≈ 2 million positions.

**What to learn**, most useful first: (1) **evaluator weights**, a logistic model over 30–60
card-agnostic features (life, hand by card type, castable answers, untapped mana, creature
power/toughness/evasion, permanents' mana value, library size, turn, play/draw) replacing the
hand-set constants of `GameStateEvaluator`/`StrategicEvaluator`, aimed at the diagnosed weakness;
card-agnostic because mtgsim tests brews, and weights for the meta's ~250 cards would not transfer;
(2) a **keep/mulligan model** on opening-hand features; (3) **policy priors** ranking candidates
for search, which need search-labelled data.

**The catch is circularity.** Default-AI self-play teaches who wins when Forge pilots both sides;
a value function trained on it learns that control positions lose, the bias to remove. Useful
labels need search-vs-search games and iteration (expert iteration), multiplying the data cost by
the search slowdown.

**Integration.** Inference inside the JVM (a dot product or tiny MLP, microseconds); rollouts
evaluate thousands of positions per game, too many for a protocol round trip each. Needs a Forge
patch (simulation code does `new GameStateEvaluator()`). Training is CPU-only; logistic regression
in pure Python fits the stdlib-only rule, anything larger belongs in a separate tool.

- *Effort:* 20–40 person-days with one or two iterations; a mulligan model alone 5–8.
- *Gain:* small until labels come from stronger play (a guess: 0–3 points of mean gap), then
  unknown.
- *Compute:* one-off 80–500 core-hours of games (default to search labels); training minutes to
  hours; per game, whatever the search it feeds costs.
- *Needs:* feature dumper, trainer, Forge patch; no keys.
- *Risks:* circular labels; overfitting the 11 real rates; card-specific overfitting; ML
  dependencies creeping into a stdlib-only package.

## 4. Option 3: a language model for a few decisions per game

**Which decisions.** Mulligans; whether (and with what) to counter; in the own main phase, tap out
or hold up mana, sweep now or wait; possibly attack or hold back. That is where `CounterAi`'s dice
and the board-heavy evaluator hurt most. Azorius Control, the largest gap, runs 9 counterspells,
2 Day of Judgment and 4 Get Lost. Jund Sacrifice's deficit looks like sequencing (many small
decisions) and would gain little.

**Driver.** A `LobbyPlayerAi` subclass whose `createIngamePlayer` installs a `PlayerControllerAi`
subclass overriding `mulliganKeepHand`, `chooseSpellAbilityToPlay` (only when an opposing spell is
on top and a counter is castable, or in the own main phase with an answer castable) and optionally
`declareAttackers`. It computes the heuristic choice first (`super`), then asks, outside any
`AITimeoutTracker` session so the wait cannot change later heuristic decisions, and defers to
`super` when `game.isSimulationCopy()` (`GameCopier` keeps `LobbyPlayerAi` subclasses, so Monte
Carlo copies would call out too).

**Protocol.** Mid-game the driver writes
`{"type":"decide","id":…,"seq":3,"kind":"counter","state":{…},"options":[…],"default":0}` and
waits for `answer<TAB>id=…<TAB>seq=3<TAB>choice=1` on stdin (the game thread reads it; the main
thread is blocked in `join`). `runner._Worker.run` serves `decide` messages until the `result`
line: decision log, then model, then `default` on any failure. Game timeout and `RESULT_GRACE`
count engine time only. The state holds what the deciding player may know (own hand, public
zones, opponent's hand size, revealed cards), never the opponent's hand or a library order.

**Reproducibility.** Current Claude models reject `temperature`/`top_p`/`top_k` (HTTP 400 on Opus
5.5, non-default values on Sonnet 5.5 and Haiku 5.5, every model from API version 2026-10-21), so
"temperature 0" is unavailable and answers vary. Reproducibility comes from a **decision log**:
`decisions.jsonl` in the run directory, append-only, keyed by a hash of model id, prompt version,
decision kind, canonical state and options. The engine is deterministic given seed and answers
(the callback draws nothing from `MyRandom`), so replays and `--resume` with the log reproduce
every game; the same seed with an empty log does not. Errors and refusals fall back to the
heuristic choice and are logged, so they replay too. Answers come back as JSON through structured
outputs (`output_config.format`).

**Cost** (est.; list prices of 3 Nov 2026, Haiku's cache-read price assumed at a tenth of input).
Per decision: 8,000 cached tokens (instructions, both lists with card text), 1,500 fresh tokens of
state, 500 output tokens with thinking (Opus 5.5 cannot switch thinking off; low effort). About 10
decisions per LLM seat per game: 1.3 mulligan decisions (0.29 mulligans per player measured here),
~4 counter windows, ~4 hold/sweep decisions; attacks and blocks would add 10–20.

| Model (in / out / cache read, $ per M tokens) | Per decision | Per seat-game | 1,000-game A/B arm | 1,650-game round robin, both seats |
|---|---|---|---|---|
| Opus 5.5 (4 / 20 / 0.20) | $0.018 | $0.18 | $180 | $580 |
| Sonnet 5.5 (2 / 10 / 0.10) | $0.009 | $0.09 | $90 | $290 |
| Haiku 5.5 (0.10 / 0.50 / ~0.01) | $0.0005 | $0.005 | $5 | $16 |

Calls are synchronous inside a game, so the Batch discount does not apply. At 1–5 s per call
(est.) a seat waits 10–50 s per game; waiting JVMs use no CPU, so run more JVMs than cores (15 GB
of RAM allows ~10–12): a both-seats round robin then takes ~2.5 h (est.). The package is
stdlib-only, so the client is either the official `anthropic` SDK as an optional dependency
imported only under `--llm`, or `urllib`; that and the model are the maintainers' choices.

**Evaluation.** (1) Without a key: a decider that always returns the heuristic choice must replay
baseline games bit for bit (tests protocol, log, timeouts). (2) Offline probe: ~200 logged
decisions, model answers against deterministic Monte Carlo (1a) and a human read; a few dollars.
(3) Pilot A/B: Azorius Control with LLM decisions vs default against the field, 1,000–1,500 games
per arm (enough for 5–7 points). (4) The round-robin metrics of section 1.

- *Effort:* 8–13 person-days (driver 3–5, runner/log/client 2–3, prompts and evaluation 3–5).
- *Gain:* concentrated in counter and sweeper decks; a guess is +5 to +15 points for Azorius
  Control, little elsewhere, 1–3 points of mean gap. A few good answers cannot fix the hundred-plus
  heuristic decisions around them (blocks, sequencing), and models misread boards.
- *Needs:* an API key (none here, so this stays a design), network access, money per experiment.
- *Risks:* cost creep as decision kinds grow; prompt sensitivity; model updates (pin and log the
  id); hidden information leaking into prompts; latency.

## 5. Side by side

| | 1a deterministic MC | 1c ISMCTS | 2 learned evaluator | 3 LLM decisions |
|---|---|---|---|---|
| Effort (person-days) | 2–4 | 15–30 | 20–40 | 8–13 |
| Effect on the gap | hinted on one deck | larger, capped by evaluator | small until labels improve | control decks only |
| Time per game (est.) | ~17 s | 55–140 s | as its search | 2.8 s + 10–50 s wait per LLM seat |
| 1,650-game round robin (est.) | ~2 h | 6.5–16 h | + 80–500 core-h once | ~2.5 h, $16–$580 |
| Needs | driver, maybe Forge patch | Forge patch | dumper, trainer, patch | API key, callback |
| Replays from | seed | seed | seed | seed + decision log |

## 6. Recommendation

Make search reproducible, measure it across the meta, and keep the language model for decisions
search still gets wrong. Forge already holds most of a reasonable search, the only measured gain
came from it, it needs no data or key, and reproducibility removes the reason `--mc` cannot be used
in A/B tests today. The learned player is least attractive now: no human data, circular labels,
most effort.

0. **Measure** (1–2 days): log `FlatMonteCarloStats.summary()` per worker; count decision points by
   kind and deck; add mean gap and spread ratio to the matrix summary.
1. **Deterministic Monte Carlo** (2–4 days, the first prototype). Then round robins with it for
   every seat and for the weak decks only. Gate: weak-deck pilot A/B gains whose intervals exclude
   zero, and a lower mean gap.
2. **LLM decisions** (8–13 days), only if counter and hold decisions still explain the control
   decks' losses and a key is available; offline probe before any full run.
3. **ISMCTS** with blocks, and/or evaluator weights learned from search-vs-search games, only if
   stage 1 shows search helps and the evaluator is the limit; judged on the next meta snapshot.

**First prototype: `--mc fixed`** (and `ai_mc: fixed`), Flat Monte Carlo with a rollout budget:
- `mtgsim/bridge/ForgeBridge.java`: raise `game.AI_TIMEOUT`; load an extra profile with fixed
  `FLAT_MC_*` counts and maximal budgets (`AiProfileUtil.loadAllProfiles` on a directory of Forge's
  profiles plus mtgsim's); log `FlatMonteCarloStats.summary()` after each game; report rollouts.
- If games still diverge, a small Forge patch (count-only switch in `FlatMonteCarloPicker.chooseImpl`
  skipping `affordableLines` and deadlines; breaker off in `AiController.noteFlatMcOutcome`),
  applied by `mtgsim/forge.py` at `setup --build` and tied to the pin.
- `mtgsim/runner.py` (job field), `mtgsim/experiment.py`, `mtgsim/cli.py` (accept `fixed`; longer
  default timeout), `mtgsim/bridge/AGENTS.md`, `README.md`, `VALIDATION.md`; a job-line unit test
  and an integration test that a fixed-mode game replays with one and two workers.
- Done when 40 of 40 games are identical across worker counts, a mirror match lands near 50%, the
  cost per rollout is measured, and Azorius Control vs Boros Dwarves is rerun at 200 games per arm
  (about an hour on 4 cores, est.).
