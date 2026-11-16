# The "Other" field, 5 November 2026

Thirteen Standard decks from the "Other" row of the same Magic.gg Metagame Mentor table as
`../meta/` (5 November 2026; Arena Championship 13 and the two Magic Spotlight: Fracture events,
about 1,810 decklists). "Other" is every archetype below 1% of the field: 18.6% of it together,
with a 45.7% match win rate. With the 18 meta decks (81.3%) they make up the whole field.

This folder is not a gauntlet to test decks against: it exists so the meta decks' simulated win
rates can be measured against a realistic field, the way the real ones were
(`tools/field_calibration.py`). The meta gauntlet stays the default.

| Deck | Type | List (melee.gg) |
|---|---|---|
| Sultai Reanimator | combo | NAKASHIMA, SHUNICHI, Magic Spotlight: Fracture (Beijing) |
| Izzet Fling | combo | AlexMacIsaac, Beijing |
| Jeskai Planeswalkers | control | Andrade, Nick, Hartford |
| Jeskai Artifacts | control | Talonflame23185, Hartford |
| Boros Mobilize | aggro | liguanglei, Beijing |
| Selesnya Offense | aggro | White, Sam, Hartford |
| Dimir Control | control | iwi, Beijing |
| Mardu Discard | midrange | Kuznetsov, Iaroslav, Beijing |
| Temur Omniscience | combo | Davis, Aylin, Hartford |
| Azorius Prison | aggro | boring_syndrome, Beijing |
| Mono-Red Aggro | aggro | Sutter, Noah, Hartford |
| Dimir Oculus | midrange | O'Donnell, Devon, Hartford |
| Jeskai Control | control | Deng, Dezhong, Hartford |

- **Source:** the article names these archetypes in its "Other" paragraph and links one melee.gg
  decklist for each; that list, main deck and sideboard, was copied from the page's Arena text
  (fetched 16 November 2026). The article's "and more" is not covered: these thirteen stand for
  the whole 18.6%. Links, pilots and event dates are in `gauntlet.json`.
- **Names** are the article's; melee.gg labels some differently (Sultai Reanimator is "U-B-R-G
  Combo", Temur Omniscience "Four-Color Omniscience", Azorius Prison "Azorius Aggro", Boros
  Mobilize "Boros Aggro", Jeskai Planeswalkers "Jeskai Control"; the two Jeskai control lists are
  different decks). The types are a judgement call from the lists.
- **`meta_share`** splits the 18.6% evenly (1.43% each): the article gives no share per archetype.
- **No real win rates:** the article gives only the category's 45.7%.
- All thirteen pass `python3 -m mtgsim check`.
