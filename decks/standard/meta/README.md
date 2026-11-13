# Standard meta gauntlet

Eleven of the most-played Standard archetypes, used as the default opponents for
`python -m mtgsim gauntlet` and `python -m mtgsim ab`.

**Snapshot: 5 November 2026.** Metagame shares come from the Magic.gg "Metagame Mentor"
table published that day, which combines Arena Championship 13 and the Magic Spotlight:
Fracture events (about 1,810 decklists from late October 2026). The eleven decks cover
69.1% of that field. The snapshot predates the Star Trek set and World Championship 32,
so expect it to drift; replace the lists whenever you want a fresher field.

| Deck | Type | Share | List |
|---|---|---|---|
| Mono-Green Landfall | aggro | 12.7% | Jeff Lin, 2nd, Arena Championship 13 |
| Dimir Midrange | midrange | 8.9% | aggregate |
| Dimir Uldaros | midrange | 8.3% | aggregate |
| Izzet Spellementals | tempo | 7.5% | aggregate |
| Jund Sacrifice | midrange | 7.4% | Alexander von Stange, 1st, Magic Spotlight: Fracture |
| Orzhov Lifegain | midrange | 6.9% | Gage Fevold, 1st, Arena Championship 13 |
| Azorius Control | control | 5.9% | aggregate |
| Boros Dragons | ramp | 3.6% | aggregate |
| Azorius Artifacts | control | 3.5% | aggregate |
| Boros Dwarves | aggro | 2.3% | aggregate |
| Azorius Momo | tempo | 2.1% | aggregate |

"Aggregate" lists are the composite lists printed in the Magic.gg article (built by its
author's algorithm from tournament lists), not one player's 75. Source links and dates for
every list are in `gauntlet.json`. The archetype types are a judgement call in a few cases
(Dimir Uldaros, Azorius Artifacts, Boros Dragons).

## How well the AI plays each deck

Results against this gauntlet depend heavily on how well Forge's AI pilots each opponent.
To measure that, all eleven decks were played against each other in the simulator (1,650
games, 30 per pairing, seed 1) and each deck's simulated win rate was set beside its real-world
match win rate from the same Magic.gg table. "Simulated" is on Forge with mtgsim's eight Forge
patches (`mtgsim/forge_patches/`), which fix cards the AI held but could never cast; "before
fixes" is the same round robin on unpatched Forge:

| Deck | Real win rate | Simulated | Gap | AI pilot | Before fixes |
|---|---|---|---|---|---|
| Boros Dwarves | 50.2% | 70.0% | +19.8 | strong | 74.7% |
| Boros Dragons | 45.0% | 63.7% | +18.7 | strong | 68.3% |
| Orzhov Lifegain | 53.6% | 65.0% | +11.4 | strong | 66.3% |
| Dimir Midrange | 54.5% | 58.0% | +3.5 | fair | 61.3% |
| Azorius Momo | 48.8% | 50.7% | +1.9 | fair | 45.0% |
| Azorius Control | 46.6% | 42.7% | −3.9 | fair | 19.7% |
| Mono-Green Landfall | 53.4% | 49.3% | −4.1 | fair | 52.0% |
| Azorius Artifacts | 54.8% | 46.7% | −8.1 | fair | 52.7% |
| Izzet Spellementals | 44.3% | 33.7% | −10.6 | weak | 37.7% |
| Dimir Uldaros | 49.2% | 32.7% | −16.5 | weak | 31.3% |
| Jund Sacrifice | 57.6% | 37.7% | −19.9 | weak | 41.0% |

The fixes brought the decks they touch close to their real win rates (Azorius Control could
not cast seven of its sixty cards and won one game in five) and cut the average gap from 13.0
to 10.8 points, but the two columns still barely agree on the order (rank correlation 0.11,
before 0.24; the difference is within the noise). The AI wins with decks that turn creatures
sideways and loses with decks that need planning: Jund Sacrifice, the best deck in the real
field, comes out third from the bottom. The comparison is rough (the real figures are
best-of-three matches with sideboards against the whole field, played by people of varying
skill), but gaps of 16 to 20 points are far outside its error.

What this means in practice:

- A good result against a deck marked **weak** tells you little: you beat a badly piloted
  deck. Reports flag these opponents and `gauntlet.json` records the rating as `ai_pilot`.
- Decks marked **strong** are honest, even harsh, tests for a creature deck.
- The meta-weighted win rate is a win rate against these decks as the AI plays them, not a
  forecast of a tournament result.

## Real matchup data (unverified)

`real-matchups-unverified.json` holds deck-vs-deck win rates for these archetypes gathered on
13 November 2026 from web-search summaries only: the environment's network blocked every MTG
site, so no source page could be opened and checked. 37 of its 58 rows are unambiguous
numbers, covering 26 of the 55 pairings, mostly from mtgdecks.net archetype pages (time window,
platform and best-of-one/three unknown); several pairings appear from both sides and are not
independent. Each row keeps its URL and the summary text it came from. Use it only as a rough
secondary check (`tools/matchup_check.py`): against it the round robin scores Pearson 0.15 over
24 pairings with the Forge patches (0.20 before). It is not in the format `mtgsim tune
--matchups` expects, deliberately: verify and de-duplicate it first.

## How far to trust these lists

- The lists were transcribed from web search results of the source pages; the pages
  themselves could not be opened from the environment this was built in. Each list was
  checked to total exactly 60 main / 15 sideboard, every card name resolves in Forge, and
  every card is Standard-legal and unbanned according to Forge's format file. A count
  swapped between two cards in a list would not have been caught by those checks.
- Four-Color Control (4.6% of the field) is missing because no consistent list could be
  retrieved, and there is no dedicated combo deck: none of the top twelve archetypes is one.
- Forge's AI pilots these decks, and it is much better with the aggro decks and creature-based
  midrange than with Jund Sacrifice, Dimir Uldaros and the spell-heavy Izzet deck. Results
  against those three say more about the AI than the matchup.

## Using your own field

Any folder of decklists works: `python -m mtgsim gauntlet mydeck.txt --vs path/to/folder`.
A `gauntlet.json` in the folder is optional; it supplies display names, an archetype label
and `meta_share` (percent of the field), which enables the meta-weighted win rate. Two more
optional fields set how the AI pilots one deck: `ai_profile` (a Forge AI profile such as
`Cautious` or `Hardest`) and `ai_mc` (`on` or `max` turns Forge's Monte Carlo search on for
that deck only; games involving it get slower). `--ai-profile` and `--mc` on the command line
override them for every deck.

The shipped `gauntlet.json` sets neither. On unpatched Forge, adding `"ai_mc": "max"` to the
three decks then rated `weak` (Jund Sacrifice, Dimir Uldaros, Azorius Control) brought their
simulated win rates close to the real ones, but made runs about three times slower and no
longer exactly reproducible from the seed, and it did not improve the overall ranking (see
`VALIDATION.md`). That was measured before the Forge patches; part of Monte Carlo's gain for
Azorius Control was plausibly its trying plays (such as Countersculpt) that the patched AI now
makes on its own, but that has not been measured.
