# A random sample of the field, 5 November 2026

One hundred Standard decklists drawn at random from the 1,811 lists of the three events behind the
Magic.gg Metagame Mentor table of 5 November 2026 (Arena Championship 13, 176 lists; Magic Spotlight:
Fracture Beijing, 869; Magic Spotlight: Fracture Hartford, 781), the same table `../meta/` takes its
real win rates from. The lists already in `../meta/` and `../fracture-2026-field/` were left out of
the draw.

This folder is not a gauntlet to test decks against. It exists so the meta decks' simulated win
rates can be measured against the field the real ones were measured against: a random sample of it,
every list counted once (`meta_share` 1.0 each), so each archetype appears about as often as it was
played (`tools/sample_runs.sh`, `tools/sample_calibration.py`).

- **Source:** the final Swiss round standings of each event on melee.gg (`/Standing/GetRoundStandings`)
  list every player's decklist id, melee.gg label and match record. The 1,789 eligible ids were
  sorted, then `random.seed(1); random.sample(ids, 100)` (Python 3) drew the sample. Each list, main
  deck and sideboard, is the Arena text of its melee.gg page, fetched 16 November 2026. The pilot,
  event, melee.gg label and the pilot's real record are in `gauntlet.json`.
- **`archetype`** is assigned from the cards, not the player-chosen melee.gg label: the meta or
  "Other" list (`../meta/`, `../fracture-2026-field/`) whose main deck shares the most non-basic
  cards (shared copies over the smaller deck's non-basic count, `archetype_similarity`), or `other`
  below 0.6. It is used to leave out mirrors, as the real win rates do. 81 of the 100 lists are meta
  archetypes (real field: 81.3%); Jund Sacrifice 14, Dimir Midrange 13, Orzhov Lifegain 10,
  Mono-Green Landfall 9, 14 other. Dimir Uldaros and Dimir Excruciator lists are close (similarity
  0.8–0.9 to both), so that split is rough.
- **Names** are the melee.gg label plus the draw number (`Dimir Midrange #012`).
- Two lists have 61 main-deck cards and two have short sideboards (10 and 4), as submitted; all 100
  pass `python3 -m mtgsim check`.
