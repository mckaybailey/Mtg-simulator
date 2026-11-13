# mtgsim

Test Magic: The Gathering decks by playing them against each other, hundreds of games at a
time, and get win rates you can actually compare.

mtgsim is a harness around [Forge](https://github.com/Card-Forge/forge), the open-source
MTG rules engine (about 34,000 cards implemented, with a built-in AI). Forge plays the
games; mtgsim imports decklists, checks them, runs seeded AI-vs-AI games in parallel and
turns the results into statistics and an HTML report.

What you can do with it:

- **`gauntlet`** – run a brew against a field of opponents (a Standard meta gauntlet and a
  casual gauntlet are included) and see win rates with 95% intervals, play/draw splits and
  how fast games end.
- **`ab`** – compare two versions of a deck against the same field and find out whether the
  difference is real or just luck.
- **`match`** / **`matrix`** – one matchup in depth, or every deck against every other.
- **`goldfish`** – instant solo analysis with no engine: mana screw and flood rates,
  land-drop odds, whether your colours cast your spells on curve. Add `--clock` to measure
  the deck's unopposed kill turn on the real engine.
- **`check`** – validate a list: card names, deck size, copy limits, format legality.
- **Card-level stats** in every report: how the deck does when each card is seen, in the
  opening hand, and how often it actually gets played.
- **`misplays`** – which cards Forge's AI seems to mishandle: cards it could have cast but kept
  in hand, counterspells it never used, removal aimed at the wrong target. Also a section of
  every `match`, `gauntlet` and `matrix` report.

## Read this before trusting a number

- **The pilot is Forge's AI.** Forge's own documentation rates it best with aggro and
  midrange decks, "poor to OK" with control and "pretty bad" with most combo decks. Decks
  that need careful sequencing are understated, on both sides of the table. Use the results
  to compare similar decks and to spot weak cards and bad mana, not to predict tournament
  win rates.
- **Against the meta gauntlet this was measured, and it is a large effect.** In a 1,650-game
  round robin of the eleven included meta decks, simulated win rates barely tracked the
  decks' real tournament win rates (rank correlation about 0.24): creature decks came out
  on top and the real field's best deck, Jund Sacrifice, near the bottom. Each gauntlet deck
  therefore carries an "AI pilot" rating, and reports tell you which opponents to discount.
  Details are in `decks/standard/meta/README.md` and `VALIDATION.md`.
- **Games are best-of-one with no sideboarding.** Sideboards are read and checked but never
  played.
- **Sample size matters.** At 100 games a win rate is only known to about ±10 points, at 400
  games about ±5. Every number in the report comes with an interval; a matchup is only
  clearly good or bad when the whole interval is on one side of 50%.

## Setup

You need Python 3.9+ and a JDK 17 or newer (a full JDK, not just a runtime). mtgsim itself
has no Python dependencies.

Build the supported Forge version from source (also needs `git` and Maven; about 1 GB of
disk and a few minutes):

```
python -m mtgsim setup --build
python -m mtgsim doctor
```

Or point mtgsim at a Forge you already have (an unpacked release or a built source
checkout):

```
python -m mtgsim setup --forge-dir /path/to/forge
```

mtgsim compiles a small Java driver against whichever Forge it is given. It is developed and
tested against one specific Forge commit (the one `--build` fetches); other versions work
as long as the driver still compiles against them, and `setup` tells you if it does not.

`--build` also applies mtgsim's own fixes to Forge (`mtgsim/forge_patches/`, for example AI
hints in card scripts) on top of that commit, and records them in `mtgsim-patches.json` in the
checkout. A Forge you point to with `--forge-dir` is never modified, so it plays without them.
`doctor` shows which patches are applied; after updating mtgsim, run `setup --build` again when
it says they are out of date. That re-applies the patches in seconds and rebuilds Forge only
when a patch changes its Java code. `setup --build --no-patches` builds the plain Forge commit,
for comparing results with and without the patches. Every run's `run.json` records the patch
set it was played with.

Everything mtgsim stores lives in `~/.mtgsim` (override with `MTGSIM_HOME`), including a
private profile directory for Forge, so simulations never read or change the settings of a
Forge you use for playing.

## Quick start

```
# Is my list legal and spelled right?
python -m mtgsim check mydeck.txt

# How consistent is the mana? (instant, no engine)
python -m mtgsim goldfish mydeck.txt

# How does it do against the Standard field? (100 games per opponent)
python -m mtgsim gauntlet mydeck.txt

# ...or against casual decks, with more games
python -m mtgsim gauntlet mydeck.txt --vs decks/standard/casual -n 200

# Did swapping those four cards help?
python -m mtgsim ab mydeck.txt mydeck-v2.txt -n 200

# One matchup in depth
python -m mtgsim match mydeck.txt decks/standard/meta/dimir-midrange.txt -n 300

# Which cards did the AI mishandle in that run?
python -m mtgsim misplays runs/<the run folder>
```

Each run prints a summary and writes a folder under `runs/` containing `report.html` (open
it in a browser), `summary.json` (the analysed numbers) and `games.jsonl` (one line per
game). An interrupted run can be continued with `--resume RUN_DIR`.

### Decklists

Paste lists straight from Arena, MTGO, MTGGoldfish or Moxfield exports, or use Forge `.dck`
files:

```
Deck
4 Llanowar Elves
20 Forest
...

Sideboard
2 Negate
```

Set codes and collector numbers are ignored. Unknown names are reported with suggestions.
Legality is checked against `--format standard` by default (`pioneer`, `modern`, `legacy`,
`vintage`, `pauper` and `casual` for no restrictions are also available); format problems
are warnings unless you pass `--strict`.

### Useful options

| Option | Meaning |
|---|---|
| `-n 200` | games per pairing (default 100) |
| `-j 4` | parallel Forge processes (default: one per CPU core, up to 8; each uses about 1 GB of memory) |
| `--vs PATH...` | opponent decklists or folders (default `decks/standard/meta`) |
| `--seed 7` | base random seed; the same seed and decks replay exactly the same games |
| `--timeout 180` | seconds before a stalled game is stopped and counted as unfinished |
| `--ai-profile Reckless` | Forge AI personality for every player (`Default`, `Cautious`, `Reckless`, `Experimental`, `Hard`, `Hardest`); overrides per-deck settings |
| `--mc on` | Forge's Monte Carlo look-ahead on top of the usual AI (`max` for its strongest setting) for every player: slower, and because it thinks against a clock the same seed no longer replays the same game; overrides per-deck settings |
| `--save-logs` | keep Forge's full play-by-play log of every game |

### How long it takes

Most games take 2–4 seconds of engine time; slow control and artifact decks take longer.
On a 4-core machine the meta decks ran at about 85 games per minute, so 100 games against
each of the eleven meta decks takes roughly a quarter of an hour.

## How results are produced

- Every game is its own fresh match with its own seed and its own coin flip for who goes
  first. (Forge's built-in simulator lets the previous loser go first, which drags measured
  win rates towards 50%.)
- Seeds depend on the decks' contents, not their file names, so re-running a matchup
  replays the same games and editing a deck gives it new ones.
- Win rates use decided games only; draws, timeouts and engine failures are counted and
  shown separately.
- Intervals are 95% Wilson intervals. A/B comparisons use a stratified comparison across
  the shared opponents. When a `gauntlet.json` supplies metagame shares, a meta-weighted
  win rate is reported alongside the equal-weight one.
- Card statistics ("win rate when seen" versus "when not seen") are correlations. Long
  games see more cards, which flatters late-game cards; compare cards that fill the same
  role rather than reading the numbers as each card's worth. They are also noisy: in a
  400-game test of two identical decks, the same card came out 20 points apart. Reports
  mark the differences whose 95% interval excludes zero; ignore the rest.

## Finding AI misplays

Forge's AI loses games a person would not, and some cards suffer more than others. The
engine driver watches every game for signs of that, without changing how it is played, and
`misplays` ranks each deck's cards by how many games they touched:

```
python -m mtgsim misplays RUN_DIR                    # every deck in the run
python -m mtgsim misplays RUN_DIR --deck "Azorius Control" --top 15 --json misplays.json
```

The same tables are in the report of every `match`, `gauntlet` and `matrix` run, under
"Likely AI misplays". Per card, over decided games:

| Column | Meaning |
|---|---|
| Hit/100 | games, per 100 games of the deck, in which at least one of the problems below happened with this card; the ranking |
| Seen, Cast | games the card was in the opening hand or drawn; share of those in which it was cast |
| Idle/game | turns per game seen on which the card sat in hand while the untapped lands could pay for it and it had a legal target. Sorcery-speed cards are checked at the end of their owner's turns, instants and flash cards at the end of the opponent's turns (holding an instant through your own turn is normal) |
| Castable, never cast | of the games with at least one such turn, the share in which the card was never cast |
| In hand at end | share of games the card was still in hand when the game ended |
| Poor targets | removal casts that hit the caster's own permanent, or whose target was worth less than two thirds of the best opposing target the spell could have killed (by Forge's own creature evaluation) |
| Counter passed | opponents' spells a counterspell in hand could have countered but that resolved; "big" counts the games where one cost 3 or more |
| Hit-not pts | win rate in the flagged games minus the other games the card was seen in, with a `*` (bold in reports) when its 95% interval excludes zero |

How to read it:

- **These are pointers, not verdicts.** A card high on the list is one whose Forge AI logic is
  worth reading; whether holding it was wrong depends on the game. "Hit-not" is a correlation
  that moves for reasons unrelated to the card: losing games end with more cards in hand,
  long games give a card more turns to be flagged, and mana-flooded or screwed games look like
  holding cards.
- The mana check is deliberately simple: lands and other free mana sources that are untapped,
  printed costs (cost reductions are ignored, so a cheaper-than-printed spell may be missed),
  X = 1. Two copies of a legendary card are not counted as castable while one is in play.
- Removal is rarely flagged for poor targets, because Forge chooses targets with the same
  evaluation the check uses; the column is there to catch cards whose own AI logic aims
  elsewhere.
- Runs made before this version have no signals; `misplays` then ranks cards by games in which
  they were seen but never cast, and says so.

## Included decks

- `decks/standard/meta/` – eleven of the most-played Standard archetypes as of early
  November 2026, with metagame shares. See the README in that folder for sources and limits.
- `decks/standard/casual/` – five simple one-colour decks built from Foundations commons and
  uncommons, as kitchen-table opponents.

## Running in a Claude cloud session

Ask Claude to test a deck in a session attached to this repository; `CLAUDE.md` tells it
how to set Forge up and run the commands above, and it can hand back the HTML report.

## Tests

```
python -m unittest discover -s tests
```

The unit tests need neither Forge nor Java. `tests/test_integration.py` plays real games
and is skipped automatically when Forge has not been set up.

`VALIDATION.md` records what was checked before release (reproducibility, mirror matches,
A/B sensitivity, simulated versus real win rates, speed) and the results.

## Licensing note

Forge is licensed under GPL-3.0. mtgsim does not include Forge; it fetches or uses a copy
you provide. The Java driver in `mtgsim/bridge/` links against Forge's classes, so GPL-3.0
terms apply to that driver if you distribute it.
