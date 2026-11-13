# mtgsim package

## Modules, in the order data flows through them

| Module | Job |
|---|---|
| `forge.py` | find or build Forge, compile the Java driver, build the `java` command line; `MTGSIM_HOME` (default `~/.mtgsim`) holds config, the Forge build, compiled driver, card cache and a private Forge profile |
| `carddb.py` | card database parsed from Forge's own card scripts and edition files, so a name that resolves here is one the engine can play; cached as `~/.mtgsim/cache/carddb-v<CACHE_VERSION>-<fingerprint>.json.gz` |
| `decks.py` | parse Arena / MTGO / Forge `.dck` lists, resolve names, write `.dck` for Forge |
| `legality.py` | deck size, copy limits and format legality from Forge's `res/formats` files |
| `runner.py` | pool of long-lived Forge JVMs (one game at a time each), fed jobs over stdin |
| `experiment.py` | plan pairings, per-game seeds, write `games.jsonl`, resume |
| `analysis.py`, `stats.py` | win rates, Wilson intervals, A/B tests, matrix, card stats, clock |
| `misplay.py` | likely AI misplays per card (cards left in hand, castable but never cast, poor removal targets, unused counterspell windows, rarely cast) from the driver's misplay fields; its docstring defines every signal and the ranking score; old runs fall back to "seen but never cast" |
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
- **Per-deck AI settings** (`ai_profile`, `ai_mc` on an `Entrant`, from `gauntlet.json`) follow
  the deck to whichever seat it sits in. `--ai-profile` / `--mc` on the command line set
  `force_profile` / `force_monte_carlo` and override them for every seat.
- If `Card` fields or their parsing change, bump `CACHE_VERSION` in `carddb.py` so stale caches
  are rebuilt.
- **The driver's tracker only reads game state** (see `bridge/AGENTS.md`); a tracker that calls
  something with side effects silently changes every game. `misplay.POOR_TARGET` must match
  `Tracker.POOR_TARGET` in the driver.

## Reports

`report.py` reads only `summary.json`, so `python3 -m mtgsim report RUN_DIR` can re-render old
runs. `match`, `gauntlet` and `matrix` summaries carry a `misplays` key (`misplay.analyze` over
every entrant), rendered as the "Likely AI misplays" section; `python3 -m mtgsim misplays RUN_DIR`
recomputes it from `run.json` and `games.jsonl`. The page loads nothing external. Escape every name with `esc()`; the tooltip script builds
its DOM with `textContent` from a `data-tip` JSON attribute, never `innerHTML`. Colours are CSS
variables with light and dark values, checked with the dataviz palette validator; every chart is
followed by a table with the same numbers. After changing layout, screenshot a report with
Playwright at 1100 px and 390 px wide and check there is no horizontal page scroll.
