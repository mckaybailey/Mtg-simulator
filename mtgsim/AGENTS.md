# mtgsim package

## Modules, in the order data flows through them

| Module | Job |
|---|---|
| `forge.py` | find or build Forge, apply mtgsim's Forge patches, compile the Java driver, build the `java` command line; `MTGSIM_HOME` (default `~/.mtgsim`) holds config, the Forge build, compiled driver, card cache and a private Forge profile |
| `forge_patches/` | mtgsim's own changes to Forge as `NNNN-name.patch` diffs against `FORGE_PINNED_REF`; its `README.md` gives the format, how to make one and how to measure it |
| `carddb.py` | card database parsed from Forge's own card scripts and edition files, so a name that resolves here is one the engine can play; cached as `~/.mtgsim/cache/carddb-v<CACHE_VERSION>-<fingerprint>.json.gz` |
| `decks.py` | parse Arena / MTGO / Forge `.dck` lists, resolve names, write `.dck` for Forge |
| `legality.py` | deck size, copy limits and format legality from Forge's `res/formats` files |
| `ai_profiles.py` | AI profiles: Forge's `res/ai`, shipped `profiles/*.ai|*.json`, the user's `MTGSIM_HOME/profiles`; builds a run's own profile folder |
| `runner.py` | pool of long-lived Forge JVMs (one game at a time each), fed jobs over stdin |
| `experiment.py` | plan pairings (and games 2/3 of best-of-three matches), per-game seeds, write `games.jsonl`, resume |
| `tune.py` | `tune`: search AI profile settings against real win rates; game cache, successive halving, hold-out, CV, noise |
| `analysis.py`, `stats.py` | win rates, Wilson intervals, A/B tests, matrix, card stats, clock |
| `calibration.py` | a `matrix` run's meta win rates against the gauntlet's `real_win_rate`: round robin of games (equal and share-weighted), of best-of-three matches, and simulated Swiss events of the gauntlet's `real_events` structure; SD, mean gap, Spearman, sign errors, bootstrap noise ranges. `cli._add_calibration` adds it to matrix summaries; `tools/swiss_check.py` uses the same code |
| `misplay.py` | likely AI misplays per card (cards left in hand, castable but never cast, poor removal targets, unused counterspell windows, rarely cast) from the driver's misplay fields; its docstring defines every signal and the ranking score; old runs fall back to "seen but never cast" |
| `goldfish.py` | engine-free mana/curve Monte Carlo; its docstring defines the result schema exactly |
| `report.py`, `goldfish_report.py` | render `summary.json` as one self-contained HTML page |
| `cli.py` | commands; assembles `summary.json` (`_base_summary` plus per-command keys) |

## Invariants – break one and results are silently wrong

- **Seats alternate by game index.** Even games put the pairing's first deck in seat 0, odd
  games in seat 1 (`analysis.seat_of_a`). Who plays first is the engine's coin flip, recorded
  as `first_seat`. In best-of-one every game is a fresh match; never let the previous loser go first.
- **Best-of-three (`--bo3`) adds games 2 and 3 to those game 1s; it changes nothing in them.**
  Game 1 of match *i* has the id `a|b|i`, the best-of-one seed and seats, so it *is* best-of-one
  game *i* (an old run's `games.jsonl` can be copied into a new bo3 run directory to reuse them;
  `analysis.first_games` and `matrix_game1` / `pairings_game1` read them as the best-of-one
  result). Games 2 and 3 (`a|b|i|g2`, `a|b|i|g3`, `match_game` 2/3, their own seeds from
  `experiment.match_game_seed`) do **not** follow the parity rule: the previous game's loser gets
  seat 0 and starts (`first=0`; after a game without a winner, whoever started it starts again),
  so read their seats from `seats` (`analysis.seat_of_a` does). They are planned from the results
  recorded so far (`next_match_games`), in a round after all game 1s and another after all game
  2s; a resumed run re-plans them, and `execute` refuses to resume a run under another format.
  A match is won with two game wins; three games without one is a draw. Card and misplay
  statistics use the first games only, since later games are sideboarded.
- **Seeds come from deck contents** (`experiment.game_seed`: base seed + sorted main-deck
  fingerprints + game index), not names or argument order. Same decks and seed = same games.
- **Win rates use decided games only**; draws, timeouts and engine errors are counted and shown
  separately.
- **The engine must load every card.** `execute` stops the run with `RunError` if Forge reports a
  different main-deck count than the list.
- **`games.jsonl` is append-only.** On resume, games recorded as `ok` or `timeout` are skipped
  and everything else is replayed; when an id repeats, the last record wins.
- **Per-deck AI settings** (`ai_profile`, `ai_mc` on an `Entrant`, from `gauntlet.json`; the
  profile may be Forge's, shipped or the user's) follow the deck to whichever seat it sits in.
  `--ai-profile` / `--mc` on the command line set `force_profile` / `force_monte_carlo` and
  override them for every seat.
- **AI profiles come from the run's own folder.** `experiment.execute` (and `tune`) write
  `RUN_DIR/ai/` with Forge's profiles copied unchanged (from the patched checkout, so a Forge
  patch to a profile is picked up), the shipped and user profiles, and any generated ones, and
  start the JVMs with `-Dmtgsim.aiProfileDir`. Never write into Forge's `res/ai`: changing one
  of Forge's own profiles is a Forge patch; a new profile mtgsim selects by name belongs in
  `mtgsim/profiles/` and, like a patch, is only shipped with a measurement in VALIDATION.md. A generated profile is a *complete* copy of its base with overrides applied: a key
  missing from a Forge profile falls back to the `AiProps` enum default, not to Default.ai.
  Shipped or user profiles may not reuse a Forge profile's name. The driver refuses a profile
  name it did not load (Forge itself would silently use enum defaults), and the runner refuses a
  driver whose ready line does not name the folder. `run.json` records each used profile's
  settings hash and the Forge build fingerprint.
- **The tune cache key** (`tune.pairing_key` + game index) must hold everything that decides a
  game: the engine (`tune.engine_identity`: Forge build fingerprint plus the applied Forge patch
  set's `combined_sha256`; a card-script patch changes no jar or folder timestamp), seed, game
  format, Monte Carlo, time limit, and per deck its main-deck
  fingerprint, its *name* (Forge pilots a deck whose name contains "Control", or whose average
  mana value is above 3, as non-aggro) and its profile's *effective* settings hash
  (`ai_profiles.settings_hash` with the enum defaults filled in). Pairings are oriented by deck
  order and game g has the pairing's first deck in seat g % 2, exactly as `plan_pairing`, which is
  what makes `--import` of a `matrix` run valid; an import also needs the same patch set (a run
  recorded before patches were tracked counts as unpatched). If the driver ever changes how a game is played,
  bump `CACHE_VERSION` in `tune.py`. With Monte Carlo `on` or `max`, cached games are valid samples
  but not replays; with `fixed` they are replays.
- **Monte Carlo `fixed` (and `deep`, the same search at depth 8) must never read the clock.** Its games replay from the seed because the
  search is counted in rollouts (Forge patch 0020) and the driver puts `Game.AI_TIMEOUT` out of
  reach (`bridge/AGENTS.md`). `runner.MONTE_CARLO_MODES` is the one list of settings (`Job.line`
  refuses anything else); a job with a `fixed` or `deep` seat (`runner.COUNTED_MODES`) gets `RunOptions.fixed_timeout`
  (`runner.FIXED_TIMEOUT`, 1,800 s) because a game stopped at the time limit is not a replay.
  Changing the counted budget in the patch changes every `fixed` game: re-measure and say so in
  VALIDATION.md. Games without Monte Carlo must stay bit-identical through any change to this
  path (`tools/compare_games.py` on a seeded match, old against new).
- **Selection never sees held-out real win rates**, and the confirmation round uses game indices
  after the last selection round, so its numbers are not inflated by the choice.
- If `Card` fields or their parsing change, bump `CACHE_VERSION` in `carddb.py` so stale caches
  are rebuilt.
- **The driver's tracker only reads game state** (see `bridge/AGENTS.md`); a tracker that calls
  something with side effects silently changes every game. `misplay.POOR_TARGET` must match
  `Tracker.POOR_TARGET` in the driver.
- **Forge patches are applied only by `setup --build`, only to the checkout it manages**, never
  to a Forge given with `--forge-dir`. `forge.sync_patches` tries the series on a scratch git
  index first (a patch that does not apply raises `ForgeError` naming it and changes nothing),
  then restores every path the old or new series touches to the pinned commit and `git apply`s
  the whole series. `mtgsim-patches.json` in the checkout root records names, sha256, touched
  paths, the expected blob of each path and what the jar was built from; Maven runs only when
  that jar record differs from the commit plus the patches touching anything outside
  `forge-gui/res/`. Write the marker through `_write_marker` (atomic, state `applying` while
  files change) so an interrupted setup is repaired on the next run.
- **The applied patch set is part of `ForgeInstall.fingerprint()`** (only when non-empty, so an
  unpatched Forge keeps its cache names). A patched card script changes neither the jar nor the
  folder timestamps the fingerprint also uses, so without this the card cache and compiled
  driver would go stale. `experiment.execute` records `forge.patch_status(...).record()` in
  `run.json` under `forge.patches` and warns on stderr (unless `quiet`) when the install is not
  carrying the shipped set or a resumed run changes set. `patch_status` reads only the marker
  (cheap, no git); `verify=True` (doctor, setup) also hashes the patched files with git.

## Comparing with real win rates

The Swiss line of `calibration.compare` is the reference metric for how closely simulations
match real results (root `AGENTS.md`). Keep it reproducible: it draws only from its own
`random.Random(seed)` (default 1), in a fixed order (decks sorted by key, pairings in summary
order, the point estimate before the bootstrap), so the same run gives the same numbers, and
`tools/swiss_check.py` must keep printing what it printed before any change here. Only decks with
both `real_win_rate` and `meta_share` (the entrant's `weight`) take part; `real_win_rate` is
carried on `Entrant` and in `run.json` / `summary.json`. For a `--bo3` run, game rates come from
`pairings_game1` and match rates from `pairings`; never convert match results again.

## Reports

`report.py` reads only `summary.json`, so `python3 -m mtgsim report RUN_DIR` can re-render old
runs. A `matrix` summary with a `calibration` key gets the "Against real win rates" section.
`match`, `gauntlet` and `matrix` summaries carry a `misplays` key (`misplay.analyze` over
every entrant), rendered as the "Likely AI misplays" section; `python3 -m mtgsim misplays RUN_DIR`
recomputes it from `run.json` and `games.jsonl`. The page loads nothing external. Escape every name with `esc()`; the tooltip script builds
its DOM with `textContent` from a `data-tip` JSON attribute, never `innerHTML`. Colours are CSS
variables with light and dark values, checked with the dataviz palette validator; every chart is
followed by a table with the same numbers. After changing layout, screenshot a report with
Playwright at 1100 px and 390 px wide and check there is no horizontal page scroll.
