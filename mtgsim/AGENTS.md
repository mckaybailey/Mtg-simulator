# mtgsim package

## Modules, in the order data flows through them

| Module | Job |
|---|---|
| `forge.py` | find or build Forge, compile the Java driver, build the `java` command line; `MTGSIM_HOME` (default `~/.mtgsim`) holds config, the Forge build, compiled driver, card cache and a private Forge profile |
| `carddb.py` | card database parsed from Forge's own card scripts and edition files, so a name that resolves here is one the engine can play; cached as `~/.mtgsim/cache/carddb-v<CACHE_VERSION>-<fingerprint>.json.gz` |
| `decks.py` | parse Arena / MTGO / Forge `.dck` lists, resolve names, write `.dck` for Forge |
| `legality.py` | deck size, copy limits and format legality from Forge's `res/formats` files |
| `ai_profiles.py` | AI profiles: Forge's `res/ai`, shipped `profiles/*.ai|*.json`, the user's `MTGSIM_HOME/profiles`; builds a run's own profile folder |
| `runner.py` | pool of long-lived Forge JVMs (one game at a time each), fed jobs over stdin |
| `experiment.py` | plan pairings, per-game seeds, write `games.jsonl`, resume |
| `tune.py` | `tune`: search AI profile settings against real win rates; game cache, successive halving, hold-out, CV, noise |
| `analysis.py`, `stats.py` | win rates, Wilson intervals, A/B tests, matrix, card stats, clock |
| `goldfish.py` | engine-free mana/curve Monte Carlo; its docstring defines the result schema exactly |
| `report.py`, `goldfish_report.py` | render `summary.json` as one self-contained HTML page |
| `cli.py` | commands; assembles `summary.json` (`_base_summary` plus per-command keys) |

## Invariants – break one and results are silently wrong

- **Seats alternate by game index.** Even games put the pairing's first deck in seat 0, odd
  games in seat 1 (`analysis.seat_of_a`). Who plays first is the engine's coin flip, recorded
  as `first_seat`. Every game is a fresh match; never let the previous loser go first.
- **Seeds come from deck contents** (`experiment.game_seed`: base seed + sorted main-deck
  fingerprints + game index), not names or argument order. Same decks and seed = same games.
- **Win rates use decided games only**; draws, timeouts and engine errors are counted and shown
  separately.
- **The engine must load every card.** `execute` stops the run with `RunError` if Forge reports a
  different main-deck count than the list.
- **`games.jsonl` is append-only.** On resume, games recorded as `ok` or `timeout` are skipped
  and everything else is replayed; when an id repeats, the last record wins.
- **Per-deck AI settings** (`ai_profile`, `ai_mc` on an `Entrant`, from `gauntlet.json`; the
  profile may be Forge's, shipped or the user's) follow the deck to whichever seat it sits in. `--ai-profile` / `--mc` on the command line set
  `force_profile` / `force_monte_carlo` and override them for every seat.
- **AI profiles come from the run's own folder.** `experiment.execute` (and `tune`) write
  `RUN_DIR/ai/` with Forge's profiles copied unchanged, the shipped and user profiles, and any
  generated ones, and start the JVMs with `-Dmtgsim.aiProfileDir`. Never write into Forge's
  `res/ai`. A generated profile is a *complete* copy of its base with overrides applied: a key
  missing from a Forge profile falls back to the `AiProps` enum default, not to Default.ai.
  Shipped or user profiles may not reuse a Forge profile's name. The driver refuses a profile
  name it did not load (Forge itself would silently use enum defaults), and the runner refuses a
  driver whose ready line does not name the folder. `run.json` records each used profile's
  settings hash and the Forge build fingerprint.
- **The tune cache key** (`tune.pairing_key` + game index) must hold everything that decides a
  game: engine fingerprint, seed, game format, Monte Carlo, time limit, and per deck its main-deck
  fingerprint, its *name* (Forge pilots a deck whose name contains "Control", or whose average
  mana value is above 3, as non-aggro) and its profile's *effective* settings hash
  (`ai_profiles.settings_hash` with the enum defaults filled in). Pairings are oriented by deck
  order and game g has the pairing's first deck in seat g % 2, exactly as `plan_pairing`, which is
  what makes `--import` of a `matrix` run valid. If the driver ever changes how a game is played,
  bump `CACHE_VERSION` in `tune.py`. With Monte Carlo on, cached games are valid samples but not
  replays.
- **Selection never sees held-out real win rates**, and the confirmation round uses game indices
  after the last selection round, so its numbers are not inflated by the choice.
- If `Card` fields or their parsing change, bump `CACHE_VERSION` in `carddb.py` so stale caches
  are rebuilt.

## Reports

`report.py` reads only `summary.json`, so `python3 -m mtgsim report RUN_DIR` can re-render old
runs. The page loads nothing external. Escape every name with `esc()`; the tooltip script builds
its DOM with `textContent` from a `data-tip` JSON attribute, never `innerHTML`. Colours are CSS
variables with light and dark values, checked with the dataviz palette validator; every chart is
followed by a table with the same numbers. After changing layout, screenshot a report with
Playwright at 1100 px and 390 px wide and check there is no horizontal page scroll.
