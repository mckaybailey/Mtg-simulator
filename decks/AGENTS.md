# Decks

- `standard/meta/`: eighteen Standard archetypes, a snapshot of the Magic.gg metagame table of
  5 November 2026 (81.3% of the field). Its `README.md` gives sources, what was and was not
  verified, and the AI-pilot calibration table (still the first twelve decks; the six added on
  16 November have no `sim_win_rate` / `ai_pilot` yet). Win rates and the nine aggregate lists were
  checked against the article, the nine melee.gg tournament lists against their melee.gg pages. `real-matchups-unverified.json` is
  second-hand matchup data (see that README); never use it as tuning data without verifying it.
- `standard/fracture-2026-field/`: the thirteen "Other" archetypes (each below 1%, 18.6% together)
  the same Magic.gg article links, one melee.gg list each, `meta_share` split evenly, no real win
  rates. Used by `tools/field_calibration.py` to rate the meta decks against the whole field; not a
  default gauntlet.
- `standard/fracture-2026-sample/`: 100 lists drawn at random from the 1,811 lists of the same three
  events (melee.gg), `meta_share` 1.0 each, `archetype` from card overlap (81 meta archetypes). Used
  by `tools/sample_runs.sh` / `tools/sample_calibration.py`; `baseline-bo3-n6-s1.json` holds the
  meta decks' results against it. Not a default gauntlet.
- `standard/casual/`: five one-colour decks built from Foundations commons and uncommons, as
  kitchen-table opponents. Written for mtgsim, not tournament lists.
- `brews/` (create when needed): user decks worth keeping.

Any folder of `.txt` / `.dck` lists works as a gauntlet. Check every list with
`python3 -m mtgsim check PATH` before committing it.

## gauntlet.json (optional, one per folder)

`{"format", "snapshot", "description", "calibration", "real_events", "decks": [...]}`.
`real_events` is `{"structure", "description"}`: the structure of the events behind the real win
rates as `N:R[:cR/L][:wW][:lL]` per event, comma-separated (N players, R Swiss rounds, a cut to L
losses after round R, a stop at W wins or L losses), used by `calibrate` and every `matrix` run to
play the round robin's results out as Swiss events; without it, `600:12`. Each deck entry:

| Field | Meaning |
|---|---|
| `file` | decklist file in the same folder (required) |
| `name`, `category` | display name; archetype label (aggro, midrange, control, tempo, ramp, combo) |
| `meta_share` | percent of the metagame; enables the meta-weighted win rate |
| `list_type`, `pilot`, `source_url`, `source_date` | provenance |
| `real_win_rate`, `sim_win_rate` | real tournament match win rate vs. average win rate in the mtgsim round robin |
| `ai_pilot` | `weak` / `fair` / `strong`: simulated minus real win rate below −10, within ±10, above +10 points; reports warn about `weak` opponents |
| `ai_profile`, `ai_mc` | optional per-deck AI settings: a profile name (Forge's, `mtgsim/profiles/` or `~/.mtgsim/profiles/`); Monte Carlo search `on` / `max` / `fixed` / `deep` for this deck's seat only (`fixed` and `deep`, its larger-budget version, are the only ones whose games replay from the seed; a game with such a seat gets the 1,800 s time limit). `tune` ignores both and assigns profiles by group |

## Refreshing the meta gauntlet

1. Replace the lists and update `meta_share`, provenance fields and the README table.
2. `python3 -m mtgsim check decks/standard/meta` must pass with no errors.
3. Re-calibrate: `python3 -m mtgsim matrix decks/standard/meta -n 30` (about 30 minutes), then
   update `sim_win_rate` and `ai_pilot` for every deck and the README's calibration table. Update
   `real_events` to the events the new real win rates come from.
