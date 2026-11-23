# ForgeBridge.java

A small headless driver compiled against the Forge jar (`forge.ensure_bridge`) and cached in
`~/.mtgsim/bridge/<hash of jar fingerprint + this source>`, so editing this file triggers a
recompile on the next run. Forge is GPL-3.0 and this driver links against it.

## Protocol

- stdout carries only protocol lines; everything Forge prints is redirected to stderr (the
  runner saves it as `logs/worker-N.log` in the run directory).
- Startup: `{"type":"ready","forgeVersion":…,"java":…}` once the card database is loaded
  (several seconds), or `{"type":"fatal",…}`. With `-Dmtgsim.aiProfileDir=DIR` (always set by
  the runner: the run's `ai/` folder) the driver calls `AiProfileUtil.loadAllProfiles(DIR)` after
  `FModel.initialize`, replacing Forge's `res/ai` set, and the ready line adds `aiProfileDir` and
  `aiProfiles` (count). A profile setting this Forge does not know is a fatal startup error.
- stdin: one job per line, tab-separated `key=value`: `id`, `seed`, `timeout`, `format`,
  `mc` (`off|on|max|fixed|deep`, whole game), `log` (path or empty), repeated `deck=` (seat order),
  repeated `profile=`, repeated `seatmc=` (per seat; empty follows `mc`). `quit` ends the process.
  Any other Monte Carlo value makes the game an `error`. Three optional fields serve games 2 and 3
  of a best-of-three match (`experiment.plan_match_game`); without them the job is what it always
  was: `first=0` (seat 0 starts; any other value is an `error`), `sideboard=1` (both seats
  sideboard before the game, see below; needs exactly two decks), `planonly=1` (with
  `sideboard=1`: report the swaps and play nothing, status `plan`; used by
  `tools/sideboard_plans.py`).
  `snap=PATH` (optional, only sent with `--snapshots`) writes the game's decision snapshots to
  PATH, see below; without it no snapshot code runs.
  Values may not contain tabs or newlines (`runner.Job.line` enforces it).
- One result line per job: `status` (`ok|timeout|error`), `winner` and `first` (seat index or
  -1), `turns`, `endReason`, `ms`, `restart`, and per player `mainCount`, `mulligans`, `turns`,
  `lossReason`, `altWin`, `life`, `opening` / `drawn` / `played` card-name counts, and the
  misplay fields below (all `null` when the game thread could not be stopped). Games in which a
  seat used Monte Carlo also carry `mc`: `decisions`, `rollouts` and `failures` (rollouts or
  decisions that ended in an exception) summed over both seats; games without it have no such
  key, so their records are byte-for-byte what they were before the field existed. Games with
  `sideboard=1` carry `sideboard`: per seat, the swaps made as `"out>in"` strings (one per copy;
  an empty list when the advisor changed nothing). The runner stores it in the record.

### Misplay fields (per player; read by `mtgsim/misplay.py`)

Card names are paper names, as in `played`. "Castable" below means: the player is the spell's
activating player as the engine last set it (spells it never set are skipped), the casting
restrictions other than timing pass (`checkActivatorRestrictions`, `checkZoneRestrictions`,
`checkOtherRestrictions`, can't-be-cast statics), every non-mana cost part can be paid, required
targets exist (a harmful effect, see `removal`, needs an opposing target even when its targets
are optional), it is not a second copy of a legendary card already on the player's battlefield,
and the player's untapped free mana sources can pay the printed mana cost with X = 1. Free
sources are permanents whose mana ability costs only a tap (no summoning sickness), sacrificing
itself, or life; each makes the colours its `Produced$` names (`Any`, `Chosen`, `Combo` → any
colour; `Amount$` when it is a number); coloured symbols are matched to distinct sources;
Phyrexian symbols are paid with life above 2; cost reductions and mana-pool mana are ignored.

| Field | Definition |
|---|---|
| `endHand` | non-land cards in hand when the game ended (name → copies) |
| `endHandLands` | number of lands in hand when the game ended |
| `idleOwn` | name → turns of this player on which, at the start of the cleanup step, a card of that name was in hand and castable (timing ignored: the mana was untapped through the second main phase) |
| `idleOpp` | name → opponents' turns on which, at the start of the cleanup step, a card of that name was in hand and castable at instant speed (instant, flash, or a cast-with-flash static) |
| `counter` | for counterspells (a `Counter` spell, or a charm with a `Counter` mode): `passed` = opponents' spells that resolved (not fizzled) while a castable copy sat in hand that could target and counter them (checked when the spell was cast, counted when it resolved with the copy still in hand; one per spell); `passedMaxMv` = highest mana value among them; `cast` = times cast; `targets` / `targetMv` = spells it targeted and their summed mana value |
| `removal` | for spells with a harmful targeted effect on permanents (`Destroy`, `DealDamage`, `Fight`, `GainControl`, `ChangeZone` from the battlefield to anywhere else, `Pump` with negative toughness, `PutCounter` of `M1M1`; not when the targets are limited to your own permanents, not exile-and-return): `casts` = casts that targeted a permanent; `own` = casts that hit the caster's own permanent (a fight's own creature excepted); `poor` = casts with `own` or a target quality below 2/3; `quality` = summed target quality |
| `roles` | name → sorted tags from the card's scripted spells: `land`, `creature`, `instant`, `counter`, `removal`, `sweeper` (`DestroyAll`, `DamageAll`, `SacrificeAll`, battlefield `ChangeZoneAll`, negative `PumpAll`, `M1M1` `PutCounterAll`), `edict` (`Sacrifice` aimed at a player or opponents) |

Target quality of one harmful effect: the summed value of the opposing permanents it targeted
over the summed value of the same number of best legal opposing targets of the same kind
(creature or not) that the effect would have killed (damage and -X/-X against toughness minus
damage, destroy against indestructible, numbers only; other effects count every legal target),
capped at 1. Creatures are valued with `ComputerUtilCard.evaluateCreature`, other permanents by
mana value + 1. A cast's quality is the mean over its harmful effects; an effect that hit only
the caster's own permanents counts as 0. `POOR_TARGET` (2/3) must match `misplay.POOR_TARGET`.

### Decision snapshots (`snap=PATH`; read by the decision probe, `docs/ai-pilot-status.md`)

One JSON-lines file per game, written by the driver thread after the game (not for a game whose
thread would not stop). Line 1 is `{"type":"game"}` with `game` (job id), `seed`, `status`,
`winner`, `first`, `turns` and `seats` (`deck` name and `main` decklist per seat): the result is
there for analysis and must not reach whoever answers a case. Every other line is one decision:
`type` `decision`, `game`, `n` (order), `kind`, `seat`, `deck`, `opponentDeck`, `state`, `context`
and Forge's choice under `forge`.

| `kind` | Taken when | `context` | `forge` |
|---|---|---|---|
| `counter` | an opponent casts a spell while the player holds a counter that is castable (as in `counter.passed`) and could target it | `spell` (`id`, `name`, `manaValue`), `castableCounters` | `{"action":"counter","with":NAME}` if the player cast a counter at that spell, else `{"action":"pass","result":"resolved"\|"fizzled"\|"left the stack"}` |
| `main` | the active player's first main phase begins (once a turn) | `{}` | `cast` (spells the player cast from then to cleanup, `name` and `phase`), `lands` played, `manaOpenAtCleanup` (free mana units, as below) |
| `attack` | the declare-attackers step begins and the active player has an untapped creature without summoning sickness or defender | `canAttack` (ids) | `attackers` (`id`, `name`, `attacking`: `opponent` or a planeswalker's name), sorted by id; `[]` when no one attacked |
| `main2` | the active player's second main phase begins and a non-land card in hand is castable (the tracker's check, sorcery timing) | `castable` (names) | `cast` (spells cast in that phase), `lands` played in it |
| `upkeep` | the active player's upkeep begins and they hold a non-land card castable at instant speed | `castable` (names) | `cast` (spells cast in that step), `lands` |
| `draw` | the active player's draw step: taken when the step's draw reaches their hand (the step's event comes before the draw), if they then hold an instant-speed castable card | `castable` (names) | `cast` (spells cast in that step), `lands` |
| `endstep` | the opponent's end step begins and the player holds a non-land card castable at instant speed | `castable` (names) | `cast` (spells cast in that step), `lands`; `[]` when the card was held |
| `block` | the declare-blockers step begins and the player is attacked (or their planeswalker is) and has an untapped creature | `attackers` (`id`, `name`, `attacking`: `you` or the planeswalker) | `blocks` (`blocker`, `name`, `attacker`); `[]` for no blocks |
| `mulligan` | each hand decided on before the first turn | `mulligansSoFar`, `onThePlay` | `{"action":"mulligan"}`, or `{"action":"keep","bottom":[names]}` (London: the cards put on the bottom) |

`state` holds only what the deciding player may know: `turn`, `phase`, `activePlayer` (`you` /
`opponent`), `you` and `opponent` (`life`, `poison` when above 0, `hand` for `you` only (sorted
names), `handCount`, `library` count, `landsPlayedThisTurn`, `manaOpen` = the tracker's free mana
units (`manaUnits`, see "Castable"), `battlefield`, `graveyard`, face-up `exile`), and `stack`
(`name`, `controller`, `kind` spell / ability / trigger, `targets`). A permanent: `id`, `name`,
`types`, `tapped`, for creatures `power`, `toughness`, `damage` and `sick` (when present),
`counters`, `attachedTo` (an id), `token`. Opposing face-down cards are shown as face-down, never
named; the opponent's hand and library order never appear. A mulligan's state is the one taken
when the last card of that hand was drawn (the mulligan event fires only after the new hand is
drawn). A decision still open when the game ends gets `{"unresolved":"game ended"}`.

Snapshots are taken from the tracker's handlers and obey its rules below (read only). Checked
23 Nov 2026: 90 seed-1 games of three pairings with snapshots are identical to the same games
played by the driver before snapshots existed, and 40 games with and without them agree record for
record (`VALIDATION.md`, "Decision snapshots"); the same 90 again after `main2` and `endstep`
were added, and again after `upkeep` and `draw`.

## Behaviour that matters

- `MyRandom` is seeded before anything that consumes randomness, so a seed replays a game
  exactly, unless Monte Carlo is `on` or `max` (they think against a clock).
- **Monte Carlo `fixed` replays from the seed.** A seat playing it gets Forge's maximum-strength
  Flat Monte Carlo (`setFlatMonteCarloMaxOverride`) switched to a counted search with
  `AiController.setFlatMonteCarloCountOnly(true)` (Forge patch 0020; a build without it makes the
  game an `error` that names the patch), and the game's `AI_TIMEOUT` is raised to 1,000,000 s so
  no AI decision of either seat, searched or heuristic, is ever cut short by the clock. The
  budget is in the patch (`FlatMonteCarloPicker.Config.counted`): per decision at most 3 approved
  plays + 1 other target + 2 discovered plays + holding, 4 rounds for every line and 2 more for
  the lines still in the race, and at most 100 rollouts per player per game turn before the
  rest of that turn goes to the heuristics (this counted turn budget is what ends a turn in which
  the search keeps choosing a play that cannot be put on the stack). `fixed` is refused on a heap of 768 MB or less, where Forge
  shrinks its search to phone size. What still reads the clock in such a game: the job's own
  `timeout` (a game stopped by it is a `timeout`, not a replay; the runner gives fixed games
  1,800 s), and Forge's `StormSolver` (only for decks whose plan Forge classifies as a tutor-storm combo, a 4 s budget; not exercised by the
  measurements in `VALIDATION.md`).
- **Monte Carlo `deep` is `fixed` at a larger budget.** The driver also calls
  `AiController.setFlatMonteCarloCountedDepth(DEEP_DEPTH)` (8; `Config.counted(depth)` in patch
  0020): at most 8 approved + 2 other targets + 5 discovered plays + holding, 32 rounds and 16 more,
  800 rollouts a turn. Pruning keeps the real growth smaller: 23.6 rollouts a decision against 6.6
  for `fixed`, about 3.5 times its engine time; it plays no better than `fixed` (`VALIDATION.md`, "The pilot" (iv)). Everything said above about `fixed` (no clock,
  replays from the seed, heap, timeout) holds for `deep`. `fixed` never calls the depth setter,
  so its games are the same on builds with and without it.
- After every game with Monte Carlo the driver prints `FlatMonteCarloStats.summary()` to stderr
  (the worker log) under a `[mtgsim] Monte Carlo in game <id>` line; the counters are reset at
  the start of each such game (one game at a time per JVM). `tools/mc_cost.py` adds them up.
- Each job builds a new `Match`, so every game has its own coin flip, unless `first=0`: then the
  driver sets the match's `lastOutcome` (reflection) to an empty `GameOutcome(Draw, [])`, Forge
  asks the first non-winner in seat order, seat 0, and its AI always chooses to play.
- `sideboard=1`: each seat's deck is changed against the other seat's **main** deck by Forge's own
  `forge.ai.SideboardAdvisor` (card roles read from Oracle text, at most 7 swaps, creature for
  creature, cost within 1), on copies of the cached decks, using a throwaway `Match` to create
  the card objects. Then `MyRandom` is re-seeded with the job's seed, so a sideboarded game replays
  from its seed like any other. Boarding is always from the main decks, not from the previous
  game's lists, and the advisor knows nothing of the previous game's result. Its plans are by text
  pattern and sometimes odd (Boros Dwarves boards Rest in Peace in against Azorius Control;
  Azorius Control changes nothing against Dwarves): results are "with Forge's sideboarding".
- A game runs on its own thread with a 64 MB stack. Past the timeout it is ended as a draw; if the
  thread will not stop, the result carries `restart: true` and the process exits with code 3,
  and the runner starts a fresh JVM.
- Card tracking: `opening` = hand when the first turn begins (after mulligans); `drawn` = library
  to hand after that; `played` = spells cast (not abilities or triggers) plus land drops. The
  tracker swallows its own exceptions so it can never break a game.
- **The tracker must not change how games play.** Its handlers run synchronously on the game
  thread, so it may only read state: no `MyRandom`, no AI memory, no `setActivatingPlayer`, no
  copies of spells or cards. That is why it does its own mana check: `ComputerUtilMana`'s payment
  test can roll `MyRandom` (mana reservation) and writes `AiCardMemory`. `canTarget`,
  `canTargetSpellAbility`, the restriction checks, `CostPart.canPay` and `evaluateCreature` were
  read to confirm they only read. After changing the tracker, replay a seeded match with the old
  and new driver and compare every game (`VALIDATION.md`, "Misplay tracking").
- Games end with a stderr line in the worker log when the tracker ignored errors or skipped
  castability checks for spells without an activating player, naming the cards.
- Optional or newer Forge APIs (per-player profiles, per-player Monte Carlo) are reached by
  reflection and fail loudly if missing rather than being silently ignored.
- A `profile=` the JVM did not load makes that game an `error` (Forge would otherwise use the
  `AiProps` enum defaults, which differ from Default.ai). An empty `profile=` plays Forge's
  preferred profile, pinned to Default at startup.
- It relies on Forge internals, so it is tied to `FORGE_PINNED_REF` in `mtgsim/forge.py`.
