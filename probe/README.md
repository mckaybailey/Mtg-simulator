# The decision probe (steps B and C, 23 November 2026)

The decision probe asks whether a language model plays the planning decks' decisions better than
Forge's AI does. The plan and the reasoning behind it are in `docs/ai-pilot-status.md`, at the
latest checkpoint. This folder holds the data. The scripts that made it are in `tools/probe/`.

| Path | What it is |
|---|---|
| `run/probe-b.tar.xz` | **Step B**, the logged run: `runs/probe-b/` as it was played, about 1 MB packed and 38 MB unpacked. The seven planning decks each play the six creature decks, 10 games per pairing, seed 1, with `--snapshots`: 420 games and 19,629 decision lines. Each deck folder has the usual run files (`run.json`, `games.jsonl`, `summary.json`, `report.html`) and `snapshots/`. Unpack with `tar -C runs -xJf probe/run/probe-b.tar.xz` |
| `run/probe-b.sh`, `run/probe-b.log` | the script that played it (one `gauntlet` per planning deck; it resumes after a restart) and its output |
| `batches/batch-NN.txt` | **Step C**, the 200 cases (C001–C200) in 20 batches, exactly as the answerers saw them. Each file starts with a card reference (the Oracle text of every card named in the batch, from Forge's card database and token scripts), followed by about ten cases |
| `cases.jsonl` | the same cases, one line each (`case`, `kind`, `deck`, `text`), for the grading sheet |
| `key.jsonl` | **not shown to the answerers**: where each case came from (`file`, `game`, `n`), its `kind`, `deck`, `group` (`planning` or `creature`), the hand, and Forge's choice, both raw (`forge`) and in the case's answer format (`forge_text`) |
| `answers.jsonl` | the blind answers: `case`, `choice`, `reason`, `batch`, and `note` where something was done by hand (two cases, see below) |
| `run/probe-b2.tar.xz`, `run/probe-b2.sh`, `run/probe-b2.log` | **Round 2's step B**: the same 420 games replayed by the fixed tracker (24 Nov), identical game for game; unpack with `tar -C runs -xJf probe/run/probe-b2.tar.xz` |
| `round2/` | **Round 2** (24 Nov): the same decisions rebuilt with the gaps below fixed, and answered again. `batches/`, `cases.jsonl`, `key.jsonl`, `answers.jsonl` and `merged.jsonl` as here (198 cases; C128 and C177 dropped). Use this round for step D |
| `merged.jsonl` | key, case text and answer side by side, with `agree` (the mechanical comparison) and `timing` (whether a `main` case that agrees on its spells also agrees on casting them before or after combat) |

## How the cases were made

`python3 tools/probe/make_cases.py runs/probe-b --out probe --n 200 --seed 1` rebuilds every file here
except `answers.jsonl` and `merged.jsonl`. It needs Forge for the card text and the step B run in
`runs/probe-b`. A rebuild was checked to be byte-identical.

- **Who decides.** 175 cases are decisions by the planning decks (25 per deck). The other 25 are
  decisions by the creature decks, as a comparison group spread over the six decks.
- **Kinds.** Each planning deck's 25 are split as main 7, block 4, attack 3, mulligan 3, main2 2,
  counter 2, endstep 2, upkeep 1 and draw 1. A kind short of candidates hands its places to main,
  block, attack, main2 and mulligan, in that order: Jund Sacrifice, for example, holds no
  counterspells. The result is 60 main, 33 block, 27 attack, 24 mulligan, 16 main2, 15 endstep,
  10 counter, 8 upkeep and 7 draw.
- **Close spots only.** These filters skip forced or empty decisions:
  - `main`: turn 2 or later, with at least two different nonland cards in hand whose mana value
    fits the open mana plus a land drop.
  - `attack`: two or more possible attackers, or an untapped creature on the other side.
  - `block`: two or more possible blockers, or two or more attackers.
  - `mulligan`: two or five lands, after a mulligan, or a hand Forge sent back.
  - `main2`, `upkeep`, `draw`, `endstep` and `counter`: always choices, because they are only
    recorded when something is castable.
  - At most two cases come from one player's side of one game.
- **What a case shows.** It shows only what the deciding player could know: their hand, both
  battlefields with ids, tapped and summoning-sick state, counters and attachments, both
  graveyards, face-up exile, the stack, life, library and hand counts, open mana, the turn and
  who went first. It also shows both decklists, as at a day two with open decklists. The plan
  named only the opponent's deck name; the list was added because many of these cards are newer
  than any model's training. A case never shows the game's result, the opponent's hand, that the
  game was simulated, or which program made the original choice.
- **What is missing.** The tracker does not record a few things, so the cases cannot show them:
  the creature type named for Cavern of Souls (one answerer said it assumed one), which modes of
  a spree card are affordable, and earlier events of the game beyond what is on the board and in
  the graveyards.

## How the answers were made

There were 20 fresh general-purpose Claude subagents, one batch each, all started at once. Each
was told only that it is an expert Magic player and to read its one batch file, which was copied
outside the repository. It was not to open anything else, search or run commands, and was to
answer each case with a choice in the case's format and a one-line reason, as a JSON array.

The answerers' transcripts were checked: every one read only its own batch file. The answers
were extracted from the transcripts by script, not retyped. Two cases were handled by hand:

- **C159.** The answerer for batch 16 returned nine answers and skipped C159. A fresh answerer
  was given the same file and asked for C159 alone.
- **C100.** The answerer wrote "Blocks: #45 -> #48? no: #45 -> #80" and added a note correcting
  it to "#45 -> #80". The corrected choice is the one recorded.

## Agreement with Forge (`python3 tools/probe/collect.py --out probe`)

Agreement is mechanical:

- **mulligan:** keep or mulligan, and the same cards on the bottom.
- **counter:** whether to counter, and with which card.
- **attack:** the same set of attackers.
- **block:** the same blocker-to-attacker pairs.
- **Spell decisions:** the same set of spells cast and the same land. Notes in brackets (targets,
  discards, cards held) are ignored, and timing is reported apart.

The comparison was read case by case for false disagreements, and three were fixed in the script:
card names that contain commas, names inside notes, and bottom lists joined with "and".

| | cases | agree | agreement (95% CI) |
|---|---|---|---|
| all | 200 | 102 | 51% (44–58%) |
| planning decks | 175 | 85 | 49% (41–56%) |
| creature decks | 25 | 17 | 68% (48–83%) |
| main | 60 | 19 | 32% (21–44%) |
| main2 | 16 | 3 | 19% (7–43%) |
| block | 33 | 20 | 61% (44–75%) |
| attack | 27 | 16 | 59% (41–75%) |
| mulligan | 24 | 17 | 71% (51–85%) |
| endstep | 15 | 9 | 60% (36–80%) |
| counter | 10 | 6 | 60% (31–83%) |
| upkeep | 8 | 6 | 75% (41–93%) |
| draw | 7 | 6 | 86% (49–97%) |

63 of the 98 disagreements are spell decisions (main, main2, upkeep, draw and end step):

| How the answer differs from Forge's | cases |
|---|---|
| it casts more | 33 |
| it casts fewer, usually holding counters or instants for the opponent's turn | 15 |
| the same number of spells, but different ones | 12 |
| the same spells, but a different land | 3 |

In 11 `main` cases both cast the same spells. In 7 of them Forge casts after combat and the
answerer before.

**Agreement says nothing about which choice is better.** That is step D's job. A disagreement is
a case to grade, not a mistake by either side. A correction: the first write-up called C051 and
C053 answers that misread card abilities. They do not. Icetill Explorer lets its controller play
lands from the graveyard, and Superior Spider-Man copying it gets that too, so both lines are
legal. What misled was the case's own option text (gap 4 below). No answer has been checked and
found wrong.

## Fix before step D

**Status, 24 Nov 2026 (round 3, see the end):**
- **Done:** items 1, 2, 4 and 8 (round 2), and 3, 5 and 6 (round 3: cost changes in the castable
  lists, abilities, turn conditions and known cards in the history, the restricted part of the
  open mana). What is still left out of each is named in the case text and in "Round 3" below.
- **Item 7:** done for the spell and counter agreements, which were read by hand; a misread was
  fixed.
- **Item 9:** left to step D.

These were found after the answers came in. Fixing items 1–5 changes the case text, so the cases
must be rebuilt and answered again (about 20 subagent runs). They are cheap next to a grading
pass that would otherwise judge some answers on wrong or missing information.

**Gaps in what the cases show**

1. **Tokens without text.** Eleven token names are shown with power and toughness but no
   abilities, because Forge has several token scripts under each name:
   | Token | Cases |
   |---|---|
   | Illusion | 11 |
   | Pest | 11 |
   | Monk | 8 |
   | Robot | 6 |
   | Treefolk | 6 |
   | Dwarf | 5 |
   | Bat | 4 |
   | Spirit | 4 |
   | Dragon | 3 |
   | Skeleton Pirate | 3 |
   | Cadet | 1 |

   C191, for one, turns on the Spirit token's evasion. *Fix:* have the tracker record each
   token's Oracle text (it is on the card object) in the snapshot's permanent, or failing that
   pick the token script by name, power/toughness and colour.

2. **Choices made for a card are not recorded.** Cavern of Souls is the case found: the type
   named for it is missing, though Cavern is on a battlefield in 53 cases, and C040's answerer
   had to assume Dragon. The same gap holds for every card that has you choose something as it
   enters or resolves: a colour, a player, a number, a card or card name, a mode or a direction.
   *Fix:* do not handle Cavern by itself. Forge keeps every such choice on the card object:
   - `getChosenType`, `getChosenColors`, `getChosenPlayer` and `getChosenNumber`;
   - `getChosenCards` and `getNamedCards`;
   - `getChosenMode`, `getChosenDirection`, `getChosenEvenOdd` and `getChosenSector`
     (`forge-game/.../card/Card.java`).

   The tracker should write whichever of these are set into each permanent's snapshot as a
   `chosen` object, for example `"chosen": {"type": "Dragon"}`. The case should then show it
   after the permanent ("chose Dragon"). The getters only read, so the tracker's rule holds.
   - **Visibility:** most such choices are announced, but a few are secret until revealed ("secretly
     choose"). Show those only on the deciding player's own permanents.
   - **A choice involving a player:** write "you" or "opponent" for a player, as elsewhere in
     the snapshot.
   - **A choice that is a card:** write the card's name if it is a public card, and an id if it
     is a permanent.

3. **The castable lists are wrong in both directions.** The `castable` lists behind upkeep,
   draw, second-main and end-step cases come from the tracker's check (`castableNow`).
   - It ignores spree mode costs: C177 offers Three Steps Ahead with 1 mana open, though no mode
     can be paid.
   - It ignores cost reductions, such as Momo's discount on Dragons or the graveyard reduction
     on Eddymurk Crab and Hearth Elemental. A reduced spell can be missing from the list.

   *Fix:*
   - For spree cards, require the base cost plus the cheapest mode.
   - Add a case line: "Spells may cost less than shown because of cost reductions; the list may
     omit them."
   - Or drop the "Castable now" list and let the answerer judge from the hand and the open mana,
     as `main` already does.

4. **The main-phase option text says "any land from your hand".** In C051 and C053 lands can be
   played from the graveyard (Icetill Explorer), and the answerers worked that out despite the
   text. *Fix:* say "any land you may play (one per turn unless an effect allows more)".

5. **No history.** A case shows the board, the graveyards and face-up exile. It does not show
   what happened earlier: spells the opponent has revealed or cast this turn, cards they hold
   from a known source, or whether a "crime" or other turn condition has happened. Several
   answers reason about "the crime trigger" without knowing. *Fix (optional):* add the last few
   game-log lines, or this turn's spells by both players, from the tracker. If not fixed, note
   it in the case's header.

6. **Restricted mana.** Opposing "untapped mana available" counts restricted mana (Cavern of
   Souls, Treasures under Clarion Conqueror) as free. *Fix:* note in the case text that the
   count includes mana usable only for some spells, or list the untapped sources (they are
   already listed, so the note is enough).

**The comparison with Forge (`collect.py`)**

7. **Three name misreads, fixed.** The first comparison misread answers in three ways, and the
   fixed comparison is the one in this README. The misreads were:
   - card names with commas ("Kaito, Bane of Nightmares") split when the hand was read from the
     case text (the hand now comes from the key);
   - names inside notes ("Bitter Triumph (… discarding Restless Reef)") counted as casts (notes
     in brackets are now ignored);
   - bottom cards joined with "and" not counted.

   Agreement went from 48% to 51%. *Still to do:* the 102 agreements were not read by hand, only
   the 98 disagreements. Read them before step D, or have step D show all 200.

8. **Targets are not compared, and cannot be.** Forge's choices in the snapshots list what was
   cast but not at what (`cast` has `name` and `phase`). 22 agreeing spell cases that cast
   something may hide a different target. *Fix:* record targets in the snapshot's `cast` entries
   (the tracker sees the spell ability at cast time). Until then, step D should grade those 22
   instead of counting them as equal.

9. **Timing is compared loosely.** Forge's `main` choice gives each cast's phase. The answers
   give it in words, which are parsed for "before" and "after". 7 of 11 same-spell `main` cases
   differ only in timing. Step D should show both as written and let the grader decide whether
   timing matters.

The fixes to items 1, 2, 3 and 8 are changes to the driver's tracker
(`mtgsim/bridge/`). They follow its read-only rule and need the same check as step A: a seeded
replay that is game-for-game identical to a run without them (`tools/compare_games.py`). After
that, re-run step B, rebuild the cases, re-answer and re-collect. The step B run here stays as
the record of this round.

## Round 2 (24 November 2026)

**What changed.** The driver's tracker (`mtgsim/bridge/ForgeBridge.java`, documented in
`mtgsim/bridge/AGENTS.md`) now records:
- each token's rules text (`text`; empty for a vanilla token, which most of the Illusion, Robot,
  Dwarf, Skeleton Pirate and Spirit tokens here are);
- every choice made for a permanent (`chosen`: type, colours, player, number, cards, card names,
  mode, direction, odd or even, sector), for example Cavern of Souls' type or the card named for
  Petrified Hamlet; the opponent's only as publicly known;
- the targets of the spells Forge cast;
- the spells each player cast this turn and the last;
- spree and tiered mode costs in the castable check.

The case text (`tools/probe/make_cases.py`) shows these, says lands are "any land you may play",
notes that castable lists can miss reduced-cost spells and that open mana includes restricted
mana, and says which history is not shown (abilities, reveals, crimes).

**Checks.** Step B replayed with the new tracker is identical to the first run in all 420 games
(`tools/compare_games.py`). The snapshots differ only by the new fields and by the spree fix.
`make_cases.py --same-as probe/key.jsonl --old-run runs/probe-b` found 198 of the 200 decisions
again. C128 and C177 were recorded only because Three Steps Ahead counted as castable with one
mana open, so they no longer exist. Twenty fresh general-purpose subagents answered under the
prompt in `tools/probe/answer_prompt.txt`. `tools/probe/extract_answers.py` took the answers from
their transcripts and confirmed that each read only its own batch file. Nothing was done by hand
this round.

**Comparison fixes.** `collect.py` no longer counts a spell the answer says it holds ("Erode
(hold, cast if needed)", "hold No More Lies (opponent's turn)") as cast; that fix moved C040 in
round 2 and C197 in round 1. It also reports, for agreeing spell cases, whether the answer names
Forge's targets. Every spell and counter agreement was read by hand and none is false. Some still
hide a choice the snapshot does not record: a charm's mode (C102), evoke or not (C189), what
Superior Spider-Man copies (C026, C034). Attack, block and mulligan agreements compare ids and
keep or mulligan exactly.

**Result** (`python3 tools/probe/collect.py --out probe/round2`):

| | cases | agree | agreement (95% CI) |
|---|---|---|---|
| all | 198 | 102 | 52% (45–58%) |
| planning decks | 173 | 85 | 49% (42–57%) |
| creature decks | 25 | 17 | 68% (48–83%) |
| main | 60 | 21 | 35% (24–48%) |
| main2 | 15 | 2 | 13% (4–38%) |
| block | 33 | 18 | 55% (38–70%) |
| attack | 27 | 18 | 67% (48–81%) |
| mulligan | 24 | 16 | 67% (47–82%) |
| endstep | 14 | 9 | 64% (39–84%) |
| counter | 10 | 5 | 50% (24–76%) |
| upkeep | 8 | 7 | 88% (53–98%) |
| draw | 7 | 6 | 86% (49–97%) |

Agreement is where it was. 183 of the 198 cases get the same verdict in both rounds. Of the 15
that flip, one follows plainly from the new text: in C175 the Treefolk tokens now show reach,
and the answer no longer attacks into them.

The other flips are the model answering the same question differently a second time, mostly
mulligans and blocks. About one case in thirteen flips, so one answer per case is a noisy
measure.

**For step D.** Superseded by round 3, below.

## Round 3 (24 November 2026)

**What changed.** The tracker (`mtgsim/bridge/AGENTS.md`) now:
- applies cost changes in the castable check, as Forge would apply them on casting: the spell's own
  `RaiseCost$` / `ReduceCost$` and the `RaiseCost` / `ReduceCost` statics on the battlefield, the
  stack, the command zone and the card itself (Eddymurk Crab, Hearth Elemental, Sunderflock,
  Momo's discount, affinity), tested and sized by Forge's own `CostAdjustment` code. Left out:
  reductions whose size the player chooses, convoke, delve, improvise and the like, set costs,
  statics that need the spell's targets;
- splits the open mana: `manaOpenFree`, and `manaRestricted` with each spending rule;
- records `abilitiesThisTurn` / `abilitiesLastTurn` (activated abilities and triggers as they went
  on the stack, Forge's stack text), `thisTurn` per player (crimes, life gained and lost, cards
  drawn, tokens created, creatures that died, sacrifices, discards) and the opponent's
  `knownInHand` (returned to hand from a public zone, or seen when the player's Duress-style or
  reveal-hand effect resolved).

The case text shows all of these: "Untapped mana available: 10 (2 of them from Tablet of
Discovery: Spend this mana only to cast instant and sorcery spells)", the abilities of both turns,
a line of this turn's conditions per player, and "Cards you know are in your opponent's hand".
Still not shown, and said so: cards revealed from a library, and older history than last turn
beyond the public zones.

**Commands** (as round 2):
```
bash probe/run/probe-b3.sh                       # step B again -> runs/probe-b3 (about 30 min)
python3 tools/compare_games.py runs/probe-b/DECK runs/probe-b3/DECK    # for each of the 7 decks
python3 tools/probe/make_cases.py runs/probe-b3 --out probe/round3 \
    --same-as probe/round2/key.jsonl --old-run runs/probe-b2
# 20 fresh subagents, one batch each, tools/probe/answer_prompt.txt; then
python3 tools/probe/extract_answers.py --out probe/round3 TRANSCRIPTS...
python3 tools/probe/collect.py --out probe/round3
```

**Checks.** Step B replayed: 419 of 420 games identical. The other (Four-Color Control against
Orzhov Lifegain, game 6) does not replay from its seed even on the old driver without snapshots
(18, 22 and 16 turns in five runs); its one case, C045, is at turn 5, before the game diverges.
The snapshots differ from round 2's only by the new fields and by discounted cards added to
castable lists (71 more decisions, none fewer). All 198 decisions were found again. One castable
list in the cases changed (C162 gains Eddymurk Crab); 47 cases show restricted mana, 29 known
cards, 117 abilities or triggers. Twenty fresh subagents answered; `extract_answers.py` reported
no problems.

**Comparison fix.** `collect.py` stops reading casts at a part that opens with a cost or choice
note ("collecting evidence with Duress, Duress and Superior Spider-Man and naming Kíli" had
counted Duress and Spider-Man as casts). It moved C018 to agreement and changes no case of rounds
1 or 2. Every spell and counter agreement was read by hand; none is false. Unrecorded choices
remain in C102 (Theorix Charm's mode), C135 and C189 (evoke).

**Result** (`python3 tools/probe/collect.py --out probe/round3`):

| | cases | agree | agreement (95% CI) |
|---|---|---|---|
| all | 198 | 105 | 53% (46–60%) |
| planning decks | 173 | 90 | 52% (45–59%) |
| creature decks | 25 | 15 | 60% (41–77%) |
| main | 60 | 21 | 35% (24–48%) |
| main2 | 15 | 4 | 27% (11–52%) |
| block | 33 | 19 | 58% (41–73%) |
| attack | 27 | 18 | 67% (48–81%) |
| mulligan | 24 | 17 | 71% (51–85%) |
| endstep | 14 | 7 | 50% (27–73%) |
| counter | 10 | 6 | 60% (31–83%) |
| upkeep | 8 | 6 | 75% (41–93%) |
| draw | 7 | 7 | 100% (65–100%) |

Agreement is where it was. 173 of 198 cases get the same verdict as in round 2; 25 flip, 14 to
agreement and 11 away. One follows plainly from the new text: in C135 the opponent's hand is known
to hold Starscape Cleric, and the answer now evokes Deceit to take it, as Forge did. The rest look
like the answerer's own variation, one case in eight this time.

**For step D.** Grade round 3's 93 disagreements (`round3/merged.jsonl`, `agree` false). For the
agreeing cases, show the 9 `main` cases that differ only in timing and the three whose modes or
evoke choices are unrecorded, or count them as equal and say so.
