# mtgsim – notes for agents

mtgsim tests Magic: The Gathering decks by running seeded AI-vs-AI games on the
[Forge](https://github.com/Card-Forge/forge) engine and reporting win rates with intervals.
`README.md` is the user documentation (commands, options); `VALIDATION.md` records what was
measured and how far results can be trusted. Each folder with code or data has its own
`AGENTS.md`:

| Folder | What is there |
|---|---|
| `mtgsim/` | the Python package; module map and the invariants that keep results correct |
| `mtgsim/bridge/` | the Java driver that plays games inside Forge, and its stdin/stdout protocol |
| `tests/` | unit tests (no Forge needed) and the integration test |
| `decks/` | the included gauntlets and the `gauntlet.json` format |

`docs/stronger-ai.md` is a design note comparing ways to give mtgsim a stronger pilot than Forge's AI.

## Running simulations for the user

1. `python3 -m mtgsim doctor` checks Java, Forge and plays two games. If Forge is missing, run
   `python3 -m mtgsim setup --build` (fetches the pinned Forge commit, builds it with Maven;
   about 2 minutes, ~1 GB in `~/.mtgsim/forge`). The cloud environment "Mtg-simulator" runs
   that in its setup script before the session starts.
2. Save the user's list to a file (`decks/brews/` if they want it kept) and run
   `python3 -m mtgsim check FILE` first. Resolve unknown card names with the user; never guess.
3. Run what they asked for: `gauntlet`, `ab`, `match`, `matrix`, `goldfish` (`--clock` for the
   engine-measured kill turn). About 85 games a minute on 4 cores; 100 games against each of the
   11 meta decks is roughly 15 minutes. Start long runs in the background (detach with
   `setsid nohup` if they may exceed 2 hours) and say how long they will take.
   `--resume RUN_DIR` continues an interrupted run.
4. Report the printed summary in chat and hand over `runs/<run>/report.html` as a file. `runs/`
   is git-ignored.

Always pass on the limits with the numbers:

- The pilot is Forge's AI. Simulated meta win rates barely track real ones (rank correlation
  0.24): creature decks are overrated, control and value decks underrated. Wins against opponents
  marked `ai_pilot: weak` say little.
- Games are best-of-one without sideboards.
- A matchup is only decided when its 95% interval excludes 50%; an A/B difference only when the
  verdict says it is reliable. 100 games pin a win rate to about ±10 points; detecting a 5-point
  A/B gap needs ~1,500 games per version. Never present a 54% from 100 games as an edge.
- Card statistics are noisy correlations; only differences whose interval excludes zero
  (bold in reports, `*` in the terminal) deserve attention.
- `--mc on|max` (Monte Carlo search) plays better but ~6x slower, and its games are not
  reproducible from the seed.

## Working on the code

- Python 3.9+, standard library only; no third-party imports, no pytest.
- Tests: `python3 -m unittest discover -s tests` (191 tests, ~2 minutes because the integration
  test plays real games; the unit tests alone take ~3 seconds).
- Forge is pinned by `FORGE_PINNED_REF` in `mtgsim/forge.py`. The Java driver uses Forge
  internals, so bump the pin deliberately and re-run the integration test plus a mirror match
  (two copies of one deck should come out near 50%).
- Commit to `main` and keep `claude/mtg-deck-simulator-h1pbfa` pointing at the same commit; push
  both. Commit messages explain why, not just what.
- Never commit `runs/`, Forge itself, or anything from `~/.mtgsim`.
