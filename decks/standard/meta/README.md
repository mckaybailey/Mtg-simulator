# Standard meta gauntlet

Eighteen of the most-played Standard archetypes, used as the default opponents for
`python -m mtgsim gauntlet` and `python -m mtgsim ab`.

**Snapshot: 5 November 2026.** Metagame shares come from the Magic.gg "Metagame Mentor"
table published that day, which combines Arena Championship 13 and the Magic Spotlight:
Fracture events (about 1,810 decklists from late October 2026). The eighteen decks cover
81.3% of that field (the first twelve 73.7%). The snapshot predates the Star Trek set and World Championship 32,
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
| Four-Color Control | control | 4.6% | aggregate |
| Boros Dragons | ramp | 3.6% | aggregate |
| Azorius Artifacts | control | 3.5% | aggregate |
| Boros Dwarves | aggro | 2.3% | aggregate |
| Azorius Momo | tempo | 2.1% | aggregate |
| Dimir Excruciator | control | 1.4% | LiShuhao, Magic Spotlight: Fracture (Beijing) |
| Rakdos Lizards | aggro | 1.4% | EddieWong, Magic Spotlight: Fracture (Beijing) |
| Izzet Prowess | tempo | 1.4% | 梁 Liang, 辰 Chen (as melee.gg gives it), Magic Spotlight: Fracture (Beijing) |
| Mono-Black Aggro | aggro | 1.3% | Jeremy Fraser, Magic Spotlight: Fracture (Hartford) |
| Golgari Midrange | midrange | 1.1% | wgzzg, Magic Spotlight: Fracture (Beijing) |
| Grixis Reanimator | combo | 1.0% | Amin Ebady, Magic Spotlight: Fracture (Hartford) |

"Aggregate" lists are the composite lists printed in the Magic.gg article (built by its
author's algorithm from tournament lists), not one player's 75. Source links and dates for
every list are in `gauntlet.json`. The last six were added on 16 November 2026: for each, the
melee.gg decklist the Magic.gg article links for the archetype. Their real win rates rest on
only about 20–25 players each (1.0–1.4% of the field), so they are noisy (roughly ±7 points). The archetype types are a judgement call in a few cases
(Dimir Uldaros, Azorius Artifacts, Boros Dragons).

## How well the AI plays each deck

Results against this gauntlet depend heavily on how well Forge's AI pilots each opponent.
To measure that, all eighteen decks were played against each other in the simulator (4,590
games, best-of-one, 30 per pairing, seed 1, 17 November 2026) and each deck's simulated win rate
was set beside its real-world match win rate from the same Magic.gg table. "Simulated" is the
average over the other seventeen decks, on Forge with mtgsim's fourteen Forge patches
(`mtgsim/forge_patches/`):

| Deck | Real win rate | Simulated | Gap | AI pilot |
|---|---|---|---|---|
| Mono-Black Aggro | 42.6% | 65.9% | +23.3 | strong |
| Boros Dwarves | 50.2% | 71.4% | +21.2 | strong |
| Rakdos Lizards | 42.9% | 62.7% | +19.8 | strong |
| Boros Dragons | 45.0% | 63.3% | +18.3 | strong |
| Mono-Green Landfall | 53.4% | 67.1% | +13.7 | strong |
| Orzhov Lifegain | 53.6% | 65.3% | +11.7 | strong |
| Golgari Midrange | 47.5% | 54.1% | +6.6 | fair |
| Azorius Momo | 48.8% | 51.0% | +2.2 | fair |
| Four-Color Control | 48.8% | 50.0% | +1.2 | fair |
| Dimir Midrange | 54.5% | 54.7% | +0.2 | fair |
| Azorius Control | 46.6% | 43.9% | −2.7 | fair |
| Grixis Reanimator | 52.7% | 48.8% | −3.9 | fair |
| Izzet Prowess | 30.6% | 22.4% | −8.2 | fair |
| Izzet Spellementals | 44.3% | 34.3% | −10.0 | fair |
| Azorius Artifacts | 54.8% | 44.1% | −10.7 | weak |
| Dimir Excruciator | 46.0% | 31.8% | −14.2 | weak |
| Dimir Uldaros | 49.2% | 30.8% | −18.4 | weak |
| Jund Sacrifice | 57.6% | 38.4% | −19.2 | weak |

The six newer decks' real win rates rest on only 20–25 players each (about ±7 points). Izzet
Spellementals sits on the 10-point line between "fair" and "weak"; treat it as weak.

The patches fix cards the AI could not cast or used wrongly, and each moved its deck a lot
(Azorius Control could not cast seven of its sixty cards and won one game in five; Mono-Green
Landfall spent its mana on Ba Sing Se every turn and gained 20 points once that was fixed;
Four-Color Control gained 12 points from patch 0014), but the two columns still barely agree on
the order: rank correlation 0.14 (game noise alone moves it between 0.04 and 0.19), mean gap 11.4
points, and a spread (SD) of 14.0 points against the real 6.0. Played out as simulated Swiss
events of the real events' structure (`real_events` in `gauntlet.json`; `python3 -m mtgsim
calibrate`), which is how the real figures were produced and the comparison to use from now on,
the spread is 11.4, the mean gap 9.4, the rank correlation 0.11, and 8 of 18 decks are still on
the wrong side of 50%. The AI wins with decks that turn
creatures sideways and loses with decks that need planning: Jund Sacrifice, the best deck in the
real field, comes out fifth from the bottom. Best-of-three with Forge's sideboarding, a wider
field and a Monte Carlo search pilot were all tried and leave this where it is; `VALIDATION.md`
has the numbers and what the game logs show. Gaps of 18 to 23 points are far outside the
comparison's error.

What this means in practice:

- A good result against a deck marked **weak** tells you little: you beat a badly piloted
  deck. Reports flag these opponents and `gauntlet.json` records the rating as `ai_pilot`.
- Decks marked **strong** are honest, even harsh, tests for a creature deck.
- The meta-weighted win rate is a win rate against these decks as the AI plays them, not a
  forecast of a tournament result.

## Real matchup data (unverified)

`real-matchups-unverified.json` holds deck-vs-deck win rates for these archetypes gathered on
13 November 2026 from web-search summaries only. 37 of its 58 rows are unambiguous numbers,
covering 26 of the 55 pairings among the first eleven decks, mostly from mtgdecks.net archetype
pages (time window, platform and best-of-one/three unknown); several pairings appear from both
sides and are not independent. Each row keeps its URL and the summary text it came from. It is
still unverified: on 14 November mtgdecks.net was allowed through the environment's network
policy, but the site answers automated requests with a Cloudflare challenge (HTTP 403), so its
pages could not be read. Checking it needs a person with a browser. Use it only as a rough
secondary check (`tools/matchup_check.py`): against it the eleven-deck round robin scored
Pearson 0.15 over 24 pairings with the first eight Forge patches (0.20 before). It is not in the
format `mtgsim tune --matchups` expects, deliberately: verify and de-duplicate it first.

## How far to trust these lists

- The win rates, metagame shares and the nine aggregate lists were checked on 14 November 2026
  against the Magic.gg article itself (it could be opened once `magic.gg` was allowed in the
  environment's network policy). The twelve decks' shares and win rates match its table, and the eight aggregate lists transcribed earlier from search results (Dimir Midrange,
  Dimir Uldaros, Izzet Spellementals, Azorius Control, Boros Dragons, Azorius Artifacts, Boros
  Dwarves, Azorius Momo) are identical to the article's, main deck and sideboard. Four-Color
  Control was copied from the article directly.
- Mono-Green Landfall, Jund Sacrifice and Orzhov Lifegain are single tournament lists from
  melee.gg, first transcribed from search results. On 16 November 2026 (melee.gg allowed in the
  network policy) all three were checked against their melee.gg pages: identical, main deck and
  sideboard. The article prints aggregate lists for these too, which differ by a few cards, as
  one player's list would. The six decks added that day were taken from their melee.gg pages
  directly.
- Every list totals exactly 60 main / 15 sideboard, every card name resolves in Forge, and
  every card is Standard-legal and unbanned according to Forge's format file.
- The only combo-like deck is Grixis Reanimator (1.0%). The six smaller archetypes' real win
  rates are Dimir Excruciator 46.0%, Rakdos Lizards 42.9%, Izzet Prowess 30.6%, Mono-Black Aggro
  42.6%, Golgari Midrange 47.5% and Grixis Reanimator 52.7%. Their `sim_win_rate` and
  `ai_pilot` come from the 18-deck round robin of 17 November 2026 (table above).
- Forge's AI pilots these decks, and it is much better with the creature decks than with Jund
  Sacrifice, Dimir Uldaros, Dimir Excruciator, Azorius Artifacts and the spell-heavy Izzet deck.
  Results against those say more about the AI than the matchup.

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
