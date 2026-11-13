# Tests

Run everything with `python3 -m unittest discover -s tests` from the repository root. pytest is
not installed and must not be required.

- **Unit tests** (`test_*.py` except `test_integration.py`) must not need Forge, Java or the
  network. Build card databases from inline Forge card-script text with
  `carddb.parse_card_script`, or use `helpers.make_db()`.
- **`helpers.py`**: `make_db()` (a dozen cards with set printings, for legality tests) and
  `game(a, b, index, winner=…, first=…, status=…)`, which builds a stored game record with the
  correct seat alternation. Use it rather than hand-writing records.
- Anything that touches `MTGSIM_HOME` must point it at a temporary directory.
- `test_experiment.py` replaces `experiment.run_jobs` with a fake to test planning, storage and
  resume without Java.
- `test_report.py` renders every report kind and checks that names containing `<script>` and
  quotes come out escaped.
- `test_goldfish.py` checks the solo model against exact hypergeometric probabilities.
- **`test_integration.py`** plays real games (about 2 minutes) and skips itself when Forge is
  not set up. Its decks (Raging Goblin vs Grizzly Bears) were chosen because they cannot stall;
  Grizzly Bears vs Hill Giant can, and a stalled game hits the time limit and breaks the
  reproducibility check.
- When a test exposes a real bug, fix the module rather than the expectation.
