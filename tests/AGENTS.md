# Tests

Run everything with `python3 -m unittest discover -s tests` from the repository root. pytest is
not installed and must not be required.

- **Unit tests** (`test_*.py` except `test_integration.py`) must not need Forge, Java or the
  network. Build card databases from inline Forge card-script text with
  `carddb.parse_card_script`, or use `helpers.make_db()`.
- **`helpers.py`**: `make_db()` (a dozen cards with set printings, for legality tests) and
  `game(a, b, index, winner=…, first=…, status=…)`, which builds a stored game record with the
  correct seat alternation. Use it rather than hand-writing records. `later_game(a, b, index,
  number, starter, winner=…)` builds game 2 or 3 of a best-of-three match, with `starter` in seat 0. `signals(...)` builds a
  player's fields as a driver with misplay tracking records them; pass it as `a_extra=`.
- `test_misplay.py` covers every misplay signal on synthetic records, old runs without the
  fields, the report section's escaping and the `misplays` command (with `MTGSIM_HOME` pointed
  at an empty directory, so no Forge is involved).
- Anything that touches `MTGSIM_HOME` must point it at a temporary directory.
- `test_experiment.py` replaces `experiment.run_jobs` with a fake to test planning, storage and
  resume without Java. `BestOfThreeTest` covers `--bo3`: game 1s are the best-of-one jobs, later
  games seat the loser first with `first=0` / `sideboard=1` and store the driver's swaps, no game 3
  after 2-0, re-planning on resume, refusal to resume under another format, the job-line fields.
  Its fake picks the winner per job; note that `"|g"` also matches deck keys such as `green`, so
  find later games by the `|g2` / `|g3` suffix. The `--snapshots` tests check the absolute per-game
  paths (`snapshots/<a>__<b>__<game>.jsonl`, `_g2` for later match games) and that the `snap=` field
  appears only when asked for. `test_analysis.py` `MatchTest` covers
  `summarize_matches` (wins, draws, unfinished matches, game-1 and later-game splits).
- `test_tune.py` covers `ai_profiles.py` (Forge's file-reading rules, overrides, the run's
  profile folder) and `tune.py` with a fake `runner.run_jobs` whose outcomes depend on the seed
  and each seat's profile: cache reuse, resume, successive halving, hold-out isolation,
  cross-validation, import from an earlier run. It patches `ai_profiles.SHIPPED_DIR` and
  `MTGSIM_HOME` so no real profile folder is read.
- `test_report.py` renders every report kind and checks that names containing `<script>` and
  quotes come out escaped.
- `test_calibration.py` covers `calibration.py` (best-of-three conversion, event parsing, Swiss
  pairing without rematches, mirrors left out, an even field staying even, the four views and
  their order on a field with a known ranking, best-of-three runs using their own matches,
  reproducibility from the seed), the `calibrate` command on a pairing table and a run folder
  (temporary files only) and the report section's escaping.
- `test_goldfish.py` checks the solo model against exact hypergeometric probabilities.
- `test_forge_patches.py` builds a tiny git repository laid out like a Forge checkout and runs
  `forge.build_from_source` on it with `forge._maven_build` replaced by a fake that writes a jar
  (no network, Forge or Maven; skipped if `git` is missing). It also checks that every shipped
  patch in `mtgsim/forge_patches/` has `Subject:`, `Why:` and `Measured:` lines.
- **`test_integration.py`** plays real games (about 4 minutes) and skips itself when Forge is
  not set up. Its decks (Raging Goblin vs Grizzly Bears) were chosen because they cannot stall;
  Grizzly Bears vs Hill Giant can, and a stalled game hits the time limit and breaks the
  reproducibility check.
  `test_best_of_three_matches_replay_and_seat_the_loser_first` plays three bo3 matches with
  two workers and with one (same games, sideboard swaps included), checks that the loser starts
  the next game and that the game 1s equal the best-of-one games with the same seed.
  `test_fixed_monte_carlo_replays_the_same_games` plays four `--mc fixed` games with two workers
  and with one and compares them, rollout counts included; it skips itself on a Forge build
  without patch 0020. It is the slowest test (about a minute).
  `test_snapshots_do_not_change_games_and_follow_the_records` plays four games with and without
  `--snapshots`, compares them, and checks the files against the records (header, mulligans and
  the kept hand, one `main` line per turn, no opponent hand, nothing unresolved).
- **`test_integration_profiles.py`** (a few seconds of real games, skipped without Forge) checks
  that a run-generated AI profile reaches the engine: 60 Forests mulligan under Default but never
  with MULLIGAN_THRESHOLD=8, and an unknown profile name is an error, not a silent fallback.
- When a test exposes a real bug, fix the module rather than the expectation.
