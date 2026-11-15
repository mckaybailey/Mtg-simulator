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
`docs/ai-pilot-status.md` is the handoff note for the unfinished work on the AI pilot: what is done, what was
learned and what to do next. Read it before working on the AI, patches or calibration.
`tools/` holds the analysis scripts behind the numbers in `VALIDATION.md` (see its README):
calibration and arm comparisons, `mc_cost.py` for Monte Carlo runs, and `log_analysis/`, which
parses the game logs of a `--save-logs` run. `mtgsim/forge_patches/README.md` lists every Forge
patch with its cause and measurement.

## The AI pilot: what is settled, so it is not repeated

`docs/ai-pilot-status.md` has the detail and the ordered next steps; `VALIDATION.md` has every
number. In short, as of 15 November 2026:

- **The simulator's ranking of the meta decks does not match the real one, and fixing the AI's
  mistakes has not changed that.** Twelve Forge patches ship. Three moved a deck a lot (Azorius
  Control +25 points, Mono-Green Landfall +20, Azorius Momo +9); none moved the rank correlation
  or the mean gap beyond noise. A deck the AI learns to pilot becomes one more overrated
  creature deck.
- **Tried and found to change nothing beyond noise:** AI profile settings (`tune`, 16
  candidates, 12,010 games; do not rerun on the default space), per-deck `Cautious` / `Hardest`
  profiles, casting Nova Hellkite and Chainsaw (patches 0009, 0010).
- **Read and found sensible, no patch:** the AI's rules for Pinnacle Starcage, Day of Judgment,
  Torch the Tower and Seam Rip; how opponents block and aim removal against Boros Dwarves and
  Boros Dragons; those two decks' card scripts.
- **Not established either way:** whether `--mc fixed` plays better (+6.0 points, interval −2.9
  to +14.8, one pairing); whether best-of-one without sideboards explains the creature decks'
  excess (the leading hypothesis, untested).
- **Still unverified:** `decks/standard/meta/real-matchups-unverified.json` (mtgdecks.net refuses
  automated requests) and the three melee.gg tournament lists. Real win rates, shares and the
  nine aggregate lists were checked against the Magic.gg article.

How the findings were made, for the next card or deck:

- A card the AI holds: `python3 -m mtgsim misplays RUN_DIR`, then read the `ability/*Ai.java`
  class for its effect and `AiController.checkETBEffects` (it refuses a permanent whose enter
  trigger the AI would not use; `OptionalDecider$ You` on the trigger is the usual fix).
- A mana sink or wrong-phase activation is invisible to `misplays`, because nothing is castable
  at cleanup. Compare a deck's spell play rates in games with and without one of its own
  permanents on the battlefield, then read `logs/games/` (Ba Sing Se was found this way).
- Measure every patch as `mtgsim/forge_patches/README.md` says: the deck against the other meta
  decks, 100 games each, seed 1, without and with (`tools/compare_arms.py` gives the paired
  interval and how often the card was cast), plus a 200-game mirror. Card-script patches can be
  measured on the shared Forge one at a time; Java patches in a private `MTGSIM_HOME`.
- After patches change, replay `matrix decks/standard/meta -n 30 --seed 1` and update the
  calibration (`tools/calibration.py`, `tools/calibration_diff.py`, `tools/update_calibration.py`,
  the meta README table, the numbers in this file and `README.md`).

## Running simulations for the user

1. `python3 -m mtgsim doctor` checks Java, Forge and mtgsim's Forge patches and plays two games.
   If Forge is missing, run `python3 -m mtgsim setup --build` (fetches the pinned Forge commit,
   applies `mtgsim/forge_patches/`, builds it with Maven; about 2 minutes, ~1 GB in
   `~/.mtgsim/forge`). The cloud environment "Mtg-simulator" runs that in its setup script
   before the session starts. If `doctor` says the patches are out of date (the repository
   gained or changed a patch since the build), run `setup --build` again: it re-applies them and
   rebuilds only when a patch touches Java code. Do not run it while games are running on that
   Forge.
2. Save the user's list to a file (`decks/brews/` if they want it kept) and run
   `python3 -m mtgsim check FILE` first. Resolve unknown card names with the user; never guess.
3. Run what they asked for: `gauntlet`, `ab`, `match`, `matrix`, `goldfish` (`--clock` for the
   engine-measured kill turn). About 85 games a minute on 4 cores; 100 games against each of the
   12 meta decks is roughly 15 minutes. Start long runs in the background (detach with
   `setsid nohup` if they may exceed 2 hours) and say how long they will take.
   `--resume RUN_DIR` continues an interrupted run. `tune` (searching AI profile settings against
   real win rates) is a research command that needs hours of engine time: run it with `--dry-run`
   first, which prints the candidates and the games needed. The one full search on the meta so far
   found no profile that beats Forge's default beyond noise (`VALIDATION.md`).
4. Report the printed summary in chat and hand over `runs/<run>/report.html` as a file. `runs/`
   is git-ignored.

Always pass on the limits with the numbers:

- The pilot is Forge's AI. Simulated meta win rates barely track real ones (rank correlation
  0.23 over twelve decks with mtgsim's Forge patches, noise 0.08–0.36; mean gap 11.4 points):
  creature decks (Boros Dwarves, Boros Dragons, Mono-Green Landfall, Orzhov Lifegain) are
  overrated, Jund Sacrifice, Dimir Uldaros, Izzet Spellementals and Four-Color Control underrated.
  Wins against opponents marked `ai_pilot: weak` say little.
- Games are best-of-one without sideboards. That alone favours creature decks: in the logs their
  results turn on how much removal the opponent draws, and sideboards are where the rest of it is.
- A matchup is only decided when its 95% interval excludes 50%; an A/B difference only when the
  verdict says it is reliable. 100 games pin a win rate to about ±10 points; detecting a 5-point
  A/B gap needs ~1,500 games per version. Never present a 54% from 100 games as an edge.
- Card statistics are noisy correlations; only differences whose interval excludes zero
  (bold in reports, `*` in the terminal) deserve attention.
- The misplay ranking (`python3 -m mtgsim misplays RUN_DIR`, and the "Likely AI misplays"
  report section) is a heuristic pointer to cards whose Forge AI logic is worth reading, not
  proof that the AI misplayed them.
- `--mc on|max` (Monte Carlo search) plays better but ~6x slower, and its games are not
  reproducible from the seed. `--mc fixed` (or `ai_mc: fixed` for one deck) is the same search
  with a counted budget: its games do replay, it costs about 9 times the engine time per
  searching player, and the one A/B so far (Azorius Control vs Boros Dwarves, 200 games per arm)
  gave +6.0 points with an interval of −2.9 to +14.8, so do not present it as stronger.

## Working on the code

- Python 3.9+, standard library only; no third-party imports, no pytest.
- Tests: `python3 -m unittest discover -s tests` (284 tests, ~4 minutes because the integration
  test plays real games; the unit tests alone take ~3 seconds).
- Forge is pinned by `FORGE_PINNED_REF` in `mtgsim/forge.py`. The Java driver uses Forge
  internals, so bump the pin deliberately and re-run the integration test plus a mirror match
  (two copies of one deck should come out near 50%). Bumping it also means checking that every
  Forge patch still applies (`setup --build` names any that does not) and still does its job.
- Changes to Forge itself (card-script AI hints such as `AILogic$`, `SVar:PlayMain1`,
  `AI:RemoveDeck`, AI profiles, AI Java code) go in `mtgsim/forge_patches/NNNN-name.patch`, a
  `git diff` against the pinned commit with a `Subject:` / `Why:` / `Measured:` header;
  `mtgsim/forge_patches/README.md` says how to make one without disturbing runs on the shared
  checkout. Never edit `~/.mtgsim/forge` by hand to change results: only the patch set is
  recorded in each run's `run.json`. **Every patch must be measured before it is committed**:
  the same command and seed with and without it, enough games to see the difference, and the
  numbers (with intervals) in its `Measured:` line. A patch without a measurable effect still
  records that it had none. New AI profiles that mtgsim selects by name (for example one found
  by `tune`) are not Forge changes: they go in `mtgsim/profiles/`, under the same rule.
- Commit to `main` and keep `claude/mtg-deck-simulator-h1pbfa` pointing at the same commit; push
  both. Commit messages explain why, not just what. Exception: the AI pilot work is on
  `claude/ai-decision-engine`, not yet merged into `main` (the sessions that wrote it could push
  only that branch); merge it or open a pull request only when the user asks.
- The cloud container restarts without warning and takes `runs/`, `/tmp` and background jobs
  with it. Commit after each milestone, start long runs detached, and continue them with
  `--resume RUN_DIR` (repeat the original arguments). Pass `--out` to keep run names predictable.
- Never commit `runs/`, Forge itself, or anything from `~/.mtgsim`.
