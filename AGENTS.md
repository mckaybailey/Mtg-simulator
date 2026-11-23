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

**The goal of the current work is simulations whose win rates look like the real ones.** Judge every
change by the spread (SD) and the mean gap of the 18 meta decks against their real win rates,
**on the Swiss line** of `python3 -m mtgsim calibrate` (since 23 Nov; every `matrix` run of the
meta prints it): the real rates come from Swiss events, so the round robin's pairing results are
played out as simulated events of the real structure (`mtgsim/calibration.py`). Baseline (17 Nov
calibration, fourteen patches): Swiss SD 11.4 (10.6–12.2) against a real 6.0, mean gap 9.4
(8.5–10.1), Spearman 0.11, 8 sign errors of 18. Round-robin figures quoted below (SD 14.0, gap
11.4) are the older measure of the same run; compare old and new results like with like. The
plan, revised 16 Nov 2026, in order: check best-of-three with sideboards (`--bo3`; done 16 Nov);
run the 18-deck round robin in best-of-three (done 16 Nov: the format widens the spread and Forge's
sideboards do not pull it back beyond noise, so best-of-one is not the explanation); a field of
the 13 "Other" decks (done 16 Nov: SD 14.9 → 14.5, within noise); a random sample of 100 real lists in best-of-three
(done 17 Nov: match SD 19.8 → 18.6, one point of the thirteen needed); the pilot (done 17 Nov:
three measured AI fixes and `--mc fixed` for every seat leave the 18-deck SD at 13.2–13.8 against
6.0, see `VALIDATION.md`, "The pilot"). None of the levers in the plan closes the gap. The earlier plan of
about 100 decks was dropped: `tools/field_bound.py` shows that no outside field can bring the spread
near the real one, because it comes from lopsided matchups, not from a zero-sum field. Start from the
"CHECKPOINT" section at the top of `docs/ai-pilot-status.md`. Option (b) there, a larger search
budget, was tried on 17 Nov (`--mc deep`) and plays no better than `--mc fixed`. A later
discussion with the user (the "latest" checkpoint there) laid out what remains: repositioning
mtgsim, a Swiss-pairing check and an LLM probe, or more single-error hunting. The user chose the
Swiss check and the probe (21 Nov), the probe answered by Claude subagents instead of an API key.
The Swiss check is done (`tools/swiss_check.py`, `VALIDATION.md` "Swiss pairing"): simulated
Swiss events of the real events' structure take the SD from 14.0 to 11.4 and leave the ranking unchanged. On 23 Nov the
Swiss comparison became part of mtgsim (`calibrate`, and every meta `matrix` run) and the metric
for future iterations (above). Probe step A, the driver's decision snapshots (`--snapshots`:
the deciding player's visible state and Forge's choice at nine kinds of decision), is done and
merged (23 Nov); the next step is B, a logged run of the planning decks against the creature decks:
start from the latest checkpoint ("START HERE") in `docs/ai-pilot-status.md`.

## The AI pilot: what is settled, so it is not repeated

`docs/ai-pilot-status.md` has the detail and the ordered next steps; `VALIDATION.md` has every
number. In short, as of 17 November 2026:

- **The simulator's ranking of the meta decks does not match the real one, and fixing the AI's
  mistakes has not changed that.** Fourteen Forge patches ship. Three moved a deck a lot (Azorius
  Control +25 points, Mono-Green Landfall +20, Azorius Momo +9); none moved the rank correlation
  or the mean gap beyond noise. A deck the AI learns to pilot becomes one more overrated
  creature deck.
- **Tried and found to change nothing beyond noise:** AI profile settings (`tune`, 16
  candidates, 12,010 games; do not rerun on the default space), per-deck `Cautious` / `Hardest`
  profiles, casting Nova Hellkite and Chainsaw (patches 0009, 0010).
- **Read and found sensible, no patch:** the AI's rules for Pinnacle Starcage, Day of Judgment,
  Torch the Tower and Seam Rip; how opponents block and aim removal against Boros Dwarves and
  Boros Dragons; those two decks' card scripts.
- **Settled (17 Nov):** `--mc fixed` plays better on one seat against default opponents (Azorius
  Control +9.0, Jund Sacrifice +10.3, Dimir Uldaros +13.7, Boros Dwarves +2.9 points), but a round
  robin with it on every seat does not narrow the spread (SD 13.8 → 13.2, −0.6, −2.5 to +1.3; gap
  11.5 → 10.6, within noise).
- **Settled (17 Nov): a larger search budget is not the lever.** `--mc deep` (the counted search
  at depth 8, 2.9 times `fixed`'s rollouts) on Dimir Uldaros's seat: −0.7 points against `fixed`
  (paired −3.6 to +2.1, 540 games per arm); the search is saturated at `fixed`'s size.
- **Patches 0013 (Stoke Genius) and 0014 (Great Hall of the Biblioplex) (17 Nov):** found with
  `tools/log_analysis/activations.py`; Izzet Spellementals +3.3, Four-Color Control +12.1 points.
  0012 (Umbral Collar Zealot) was measured and dropped. The two Dimir decks showed no mana-sink error.
- **Tested and rejected (16 Nov):** that best-of-one without sideboards explains the creature
  decks' excess. In the 18-deck best-of-three round robin, Forge-sideboarded games 2 and 3 have
  the same spread as game 1s (SD 14.2 vs 14.5) and match results with and without sideboards
  differ by −0.5 points of SD (−1.5 to +0.4). Only a sideboarder much better than Forge's
  `SideboardAdvisor` could revive it.
- **Tested and rejected (16 Nov):** that the closed 18-deck field explains it. Adding the 13
  "Other" decks (`decks/standard/fracture-2026-field/`, 18.6% of the field) moves the share-weighted
  SD from 14.9 to 14.5 and the gap from 12.2 to 12.0; the field decks show the same bias.
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
  calibration: the run's own "Against real win rates" block (the Swiss line is the headline;
  `calibrate RUN_DIR` recomputes it), `tools/calibration.py`, `tools/calibration_diff.py`,
  `tools/update_calibration.py`, the meta README table, `decks/standard/meta/sim-matchups.json`,
  the numbers in this file and `README.md`.

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

- The pilot is Forge's AI. Simulated meta win rates barely track real ones (calibration run of
  17 Nov, 18 decks, 14 Forge patches, best-of-one, 4,590 games: rank correlation 0.14, noise
  0.04–0.19; mean gap 11.4 points; SD 14.0 against a real 6.0; as simulated Swiss events like the
  real ones, which is how to compare with real figures: SD 11.4, gap 9.4, Spearman 0.11, 8 of 18
  decks on the wrong side of 50%): creature decks (Boros Dwarves,
  Boros Dragons, Mono-Black Aggro, Mono-Green Landfall, Rakdos Lizards, Orzhov Lifegain) are
  overrated, Jund Sacrifice, Dimir Uldaros, Dimir Excruciator, Azorius Artifacts and Izzet
  Spellementals underrated.
  Wins against opponents marked `ai_pilot: weak` say little.
- Games are best-of-one without sideboards unless `--bo3` is passed. In the logs the creature
  decks' results turn on how much removal the opponent draws, but best-of-three with Forge's
  sideboarding did not bring them down (`VALIDATION.md`), and matches spread win rates wider than games.
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
  with a counted budget: its games do replay and it costs about 6–9 times the engine time per
  searching player. On one seat against the default AI it wins 3–14 points more (`VALIDATION.md`,
  "The pilot"); with it on every seat the meta ranking is no closer to the real one.

## Working on the code

- Python 3.9+, standard library only; no third-party imports, no pytest.
- Tests: `python3 -m unittest discover -s tests` (318 tests, ~5 minutes because the integration
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
- Work reaches `main` through pull requests from each session's own branch (cloud sessions can
  push only the branch they are given); open or merge one only when the user asks. As of 23 Nov
  2026 everything is merged and `main` is the only long-lived branch. Commit messages explain why,
  not just what.
- The cloud container restarts without warning, and stops within about 10 minutes of the
  session going idle; background jobs and `/tmp` go with it (`runs/` usually survives a restart,
  not a new container). Commit after each milestone, start long runs detached from a script that
  resumes, and keep the turn open with repeated foreground waits under the 10-minute tool limit;
  scheduled check-ins do not keep it awake. Continue with `--resume RUN_DIR` (repeat the original
  arguments). Pass `--out` to keep run names predictable.
- Never commit `runs/`, Forge itself, or anything from `~/.mtgsim`.
