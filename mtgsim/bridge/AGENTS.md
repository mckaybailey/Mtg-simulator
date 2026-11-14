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
  `mc` (`off|on|max|fixed`, whole game), `log` (path or empty), repeated `deck=` (seat order),
  repeated `profile=`, repeated `seatmc=` (per seat; empty follows `mc`). `quit` ends the process.
  Any other Monte Carlo value makes the game an `error`.
  Values may not contain tabs or newlines (`runner.Job.line` enforces it).
- One result line per job: `status` (`ok|timeout|error`), `winner` and `first` (seat index or
  -1), `turns`, `endReason`, `ms`, `restart`, and per player `mainCount`, `mulligans`, `turns`,
  `lossReason`, `altWin`, `life`, `opening` / `drawn` / `played` card-name counts, and the
  misplay fields below (all `null` when the game thread could not be stopped). Games in which a
  seat used Monte Carlo also carry `mc`: `decisions`, `rollouts` and `failures` (rollouts or
  decisions that ended in an exception) summed over both seats; games without it have no such
  key, so their records are byte-for-byte what they were before the field existed.

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
  the lines still in the race. `fixed` is refused on a heap of 768 MB or less, where Forge
  shrinks its search to phone size. What still reads the clock in such a game: the job's own
  `timeout` (a game stopped by it is a `timeout`, not a replay; the runner gives fixed games
  1,800 s), and Forge's `StormSolver` (storm combo decks only, a 2 s budget; not exercised by the
  measurements in `VALIDATION.md`).
- After every game with Monte Carlo the driver prints `FlatMonteCarloStats.summary()` to stderr
  (the worker log) under a `[mtgsim] Monte Carlo in game <id>` line; the counters are reset at
  the start of each such game (one game at a time per JVM). `tools/mc_cost.py` adds them up.
- Each job builds a new `Match`, so every game has its own coin flip.
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
