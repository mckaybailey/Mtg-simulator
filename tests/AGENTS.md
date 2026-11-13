# Tests

Run everything with `python3 -m unittest discover -s tests` from the repository root. pytest is
not installed and must not be required.

- **Unit tests** (`test_*.py` except `test_integration.py`) must not need Forge, Java or the
  network. Build card databases from inline Forge card-script text with
  `carddb.parse_card_script`, or use `helpers.make_db()`.
- **`helpers.py`**: `make_db()` (a dozen cards with set printings, for legality tests) and
  `game(a, b, index, winner=…, first=…, status=…)`, which builds a stored game record with the
  correct seat alternation. Use it rather than hand-writing records. `signals(...)` builds a
  player's fields as a driver with misplay tracking records them; pass it as `a_extra=`.
- `test_misplay.py` covers every misplay signal on synthetic records, old runs without the
  fields, the report section's escaping and the `misplays` command (with `MTGSIM_HOME` pointed
  at an empty directory, so no Forge is involved).
- Anything that touches `MTGSIM_HOME` must point it at a temporary directory.
- `test_experiment.py` replaces `experiment.run_jobs` with a fake to test planning, storage and
  resume without Java.
- `test_report.py` renders every report kind and checks that names containing `<script>` and
  quotes come out escaped.
- `test_goldfish.py` checks the solo model against exact hypergeometric probabilities.
- `test_forge_patches.py` builds a tiny git repository laid out like a Forge checkout and runs
  `forge.build_from_source` on it with `forge._maven_build` replaced by a fake that writes a jar
  (no network, Forge or Maven; skipped if `git` is missing). It also checks that every shipped
  patch in `mtgsim/forge_patches/` has `Subject:`, `Why:` and `Measured:` lines.
- **`test_integration.py`** plays real games (about 2 minutes) and skips itself when Forge is
  not set up. Its decks (Raging Goblin vs Grizzly Bears) were chosen because they cannot stall;
  Grizzly Bears vs Hill Giant can, and a stalled game hits the time limit and breaks the
  reproducibility check.
- When a test exposes a real bug, fix the module rather than the expectation.
