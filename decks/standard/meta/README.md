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

## How far to trust these lists

- The lists were transcribed from web search results of the source pages; the pages
  themselves could not be opened from the environment this was built in. Each list was
  checked to total exactly 60 main / 15 sideboard, every card name resolves in Forge, and
  every card is Standard-legal and unbanned according to Forge's format file. A count
  swapped between two cards in a list would not have been caught by those checks.
- Four-Color Control (4.6% of the field) is missing because no consistent list could be
  retrieved, and there is no dedicated combo deck: none of the top twelve archetypes is one.
- Forge's AI pilots these decks, and it is much better with the aggro and midrange decks
  than with the control decks (Azorius Control, Azorius Artifacts, Dimir Uldaros) or the
  spell-heavy Izzet deck. Results against those four say more about the AI than the matchup.

## Using your own field

Any folder of decklists works: `python -m mtgsim gauntlet mydeck.txt --vs path/to/folder`.
A `gauntlet.json` in the folder is optional; it supplies display names, an archetype label
and `meta_share` (percent of the field), which enables the meta-weighted win rate.
