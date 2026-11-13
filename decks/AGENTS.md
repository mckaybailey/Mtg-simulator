# Decks

- `standard/meta/`: eleven Standard archetypes, a snapshot of the Magic.gg metagame table of
  5 November 2026 (69.1% of the field). Its `README.md` gives sources, what was and was not
  verified, and the AI-pilot calibration table. Lists were transcribed from search results, not
  read from the source pages; Four-Color Control is missing. `real-matchups-unverified.json` is
  second-hand matchup data (see that README); never use it as tuning data without verifying it.
- `standard/casual/`: five one-colour decks built from Foundations commons and uncommons, as
  kitchen-table opponents. Written for mtgsim, not tournament lists.
- `brews/` (create when needed): user decks worth keeping.

Any folder of `.txt` / `.dck` lists works as a gauntlet. Check every list with
`python3 -m mtgsim check PATH` before committing it.

## gauntlet.json (optional, one per folder)

`{"format", "snapshot", "description", "calibration", "decks": [...]}`; each deck entry:

| Field | Meaning |
|---|---|
| `file` | decklist file in the same folder (required) |
| `name`, `category` | display name; archetype label (aggro, midrange, control, tempo, ramp, combo) |
| `meta_share` | percent of the metagame; enables the meta-weighted win rate |
| `list_type`, `pilot`, `source_url`, `source_date` | provenance |
| `real_win_rate`, `sim_win_rate` | real tournament match win rate vs. average win rate in the mtgsim round robin |
| `ai_pilot` | `weak` / `fair` / `strong`: simulated minus real win rate below −10, within ±10, above +10 points; reports warn about `weak` opponents |
| `ai_profile`, `ai_mc` | optional per-deck AI settings: a profile name (Forge's, `mtgsim/profiles/` or `~/.mtgsim/profiles/`); Monte Carlo search `on` / `max` for this deck's seat only. `tune` ignores both and assigns profiles by group |

## Refreshing the meta gauntlet

1. Replace the lists and update `meta_share`, provenance fields and the README table.
2. `python3 -m mtgsim check decks/standard/meta` must pass with no errors.
3. Re-calibrate: `python3 -m mtgsim matrix decks/standard/meta -n 30` (about 20 minutes), then
   update `sim_win_rate` and `ai_pilot` for every deck and the README's calibration table.
