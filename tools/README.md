# Analysis scripts

Small standard-library scripts used to produce the numbers in `VALIDATION.md` and
`decks/standard/meta/README.md`. Run them from the repository root on run directories made by
`python3 -m mtgsim` (they read `summary.json`, `games.jsonl` and `decks/standard/meta/gauntlet.json`).
They are not part of the package and have no tests of their own; `mtgsim/tune.py` has the tested
implementation of the same metrics.

| Script | What it prints |
|---|---|
| `calibration.py RUN_DIR [--reps N]` | each deck's simulated vs real win rate for a `matrix` run, Spearman and Pearson correlation and mean absolute gap, each with a game-noise range (parametric bootstrap: every pairing's wins redrawn from its observed rate); writes `RUN_DIR/calibration.json` |
| `calibration_diff.py RUN_A RUN_B [--reps N]` | the same three metrics for two `matrix` runs and B minus A with a 95% bootstrap interval (both runs resampled independently) |
| `compare_arms.py HERO RUN_DIR... [--cards "A,B"]` | one deck's gauntlet runs on different engines (same seeds): win rate and interval per run, per-opponent rates, how often the named cards were seen and cast, and each later run minus the first, unpaired and paired over shared game ids |
| `matchup_check.py RUN_DIR MATCHUPS_JSON` | a `matrix` run's pairing win rates against `decks/standard/meta/real-matchups-unverified.json` (unambiguous rows only, pooled per pairing) |
| `compare_games.py RUN_A RUN_B [RUN_C RUN_D ...]` | game-by-game comparison of runs that should be identical (same seeds): status, winner, turns, first seat, seats, seed, and each player's opening hand, draws, plays, mulligans, turns, life and loss reason |
| `update_calibration.py RUN_DIR [GAUNTLET_JSON]` | writes `sim_win_rate` and `ai_pilot` into a `gauntlet.json` from a `matrix` run and prints the README table (edit the `calibration` string by hand) |

`VALIDATION.md` quotes noise ranges and intervals from 1,000 resamples (`--reps 1000`); fewer
resamples move the interval ends by a few hundredths.

## `log_analysis/`

Exploratory scripts that parse the per-game text logs of a run made with `--save-logs`; they
produced the blocking, removal and ward numbers in `VALIDATION.md` ("More card fixes, and why the
creature decks win"). Run from the repository root, with the run in `MTGSIM_RUN` (default
`runs/rr-patched`) and the folder on the path:
`MTGSIM_RUN=runs/x PYTHONPATH=tools/log_analysis python3 tools/log_analysis/combat.py`.
`parse.py` reads a log into turns and events and `board.py` keeps a rough board state on top of it
(it misses tokens until they act and ignores vigilance); the rest print one analysis each:
`basic` (records, play/draw, game length), `combat` and `blockavail` (attacks and blocks),
`lethal` (the turn before a kill), `removal DECK`, `remuse`, `remwr DECK` (removal aimed at a deck
and win rate by amount), `equip` (equipment, and when removal was cast), `ward` (spells lost to
Lavaspur Boots' ward). Deck names and several card lists are written for Boros Dwarves and Boros
Dragons; treat the output as a pointer to logs worth reading, not as exact counts.
