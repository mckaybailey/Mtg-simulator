# mtgsim – notes for Claude

mtgsim tests Magic: The Gathering decks by running seeded AI-vs-AI games on the Forge
engine. `README.md` is the user documentation; read it for the commands and options.

## Running simulations for the user in a cloud session

1. Make sure Forge is ready: `python3 -m mtgsim doctor`. If it reports that Forge is not set
   up, run `python3 -m mtgsim setup --build` (fetches the pinned Forge commit and builds it
   with Maven; several minutes and about 1 GB in `~/.mtgsim/forge`). The environment's setup
   script normally does this before the session starts.
2. Put the user's decklist in a file (anywhere; `decks/brews/` is a good place if they want
   it kept) and run `python3 -m mtgsim check FILE` first. Fix unknown card names with the
   user rather than guessing.
3. Run what they asked for (`gauntlet`, `ab`, `match`, `matrix`, `goldfish`). Runs take
   minutes to an hour: start long ones in the background and tell the user the expected
   time. `--resume RUN_DIR` continues an interrupted run.
4. Give them the results: the printed summary in chat, and `runs/<run>/report.html` as a
   file. `runs/` is git-ignored; copy a report elsewhere if it should be committed.

Always pass on the limits with the numbers: the pilot is Forge's AI (fine with aggro and
midrange, poor with control, bad with combo), games are best-of-one without sideboards, and
a result is only meaningful when its 95% interval excludes 50% (or, for `ab`, when the
verdict says the difference is reliable). Do not present a 54% from 100 games as an edge.
Wins against opponents the output marks as poorly piloted (`ai_pilot: weak` in the
gauntlet) say little; `VALIDATION.md` has the measurements behind that, and they are worth
quoting when the user asks how far to trust a result.

## Working on the code

- Python 3.9+, standard library only. No third-party imports.
- Tests: `python3 -m unittest discover -s tests`. Unit tests must not need Forge or Java;
  `tests/test_integration.py` plays real games and skips itself when Forge is absent.
- `mtgsim/bridge/ForgeBridge.java` is compiled against the Forge jar on first use and
  cached in `~/.mtgsim/bridge`. It uses Forge internals, so it is tied to the commit in
  `mtgsim/forge.py` (`FORGE_PINNED_REF`); bump that deliberately and re-run the integration
  test and a mirror-match check when you do.
- Layout: `forge.py` (locating/building Forge), `carddb.py` (cards parsed from Forge's own
  scripts), `decks.py`, `legality.py`, `runner.py` (JVM worker pool), `experiment.py` (run
  planning, seeds, storage, resume), `analysis.py` and `stats.py` (results), `goldfish.py`
  (engine-free consistency model), `report.py` (HTML), `cli.py`.
- The meta gauntlet in `decks/standard/meta/` is a dated snapshot; its README says where it
  came from and what was and was not verified. When the lists are replaced, re-run
  `python3 -m mtgsim matrix decks/standard/meta -n 30` and update `sim_win_rate` and
  `ai_pilot` in `gauntlet.json` from the result.
