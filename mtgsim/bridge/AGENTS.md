# ForgeBridge.java

A small headless driver compiled against the Forge jar (`forge.ensure_bridge`) and cached in
`~/.mtgsim/bridge/<hash of jar fingerprint + this source>`, so editing this file triggers a
recompile on the next run. Forge is GPL-3.0 and this driver links against it.

## Protocol

- stdout carries only protocol lines; everything Forge prints is redirected to stderr (the
  runner saves it as `logs/worker-N.log` in the run directory).
- Startup: `{"type":"ready","forgeVersion":…,"java":…}` once the card database is loaded
  (several seconds), or `{"type":"fatal",…}`.
- stdin: one job per line, tab-separated `key=value`: `id`, `seed`, `timeout`, `format`,
  `mc` (`off|on|max`, whole game), `log` (path or empty), repeated `deck=` (seat order),
  repeated `profile=`, repeated `seatmc=` (per seat; empty follows `mc`). `quit` ends the process.
  Values may not contain tabs or newlines (`runner.Job.line` enforces it).
- One result line per job: `status` (`ok|timeout|error`), `winner` and `first` (seat index or
  -1), `turns`, `endReason`, `ms`, `restart`, and per player `mainCount`, `mulligans`, `turns`,
  `lossReason`, `altWin`, `life`, and `opening` / `drawn` / `played` card-name counts.

## Behaviour that matters

- `MyRandom` is seeded before anything that consumes randomness, so a seed replays a game
  exactly, unless Monte Carlo is on (it thinks against a clock).
- Each job builds a new `Match`, so every game has its own coin flip.
- A game runs on its own thread with a 64 MB stack. Past the timeout it is ended as a draw; if the
  thread will not stop, the result carries `restart: true` and the process exits with code 3,
  and the runner starts a fresh JVM.
- Card tracking: `opening` = hand when the first turn begins (after mulligans); `drawn` = library
  to hand after that; `played` = spells cast (not abilities or triggers) plus land drops. The
  tracker swallows its own exceptions so it can never break a game.
- Optional or newer Forge APIs (per-player profiles, per-player Monte Carlo) are reached by
  reflection and fail loudly if missing rather than being silently ignored.
- It relies on Forge internals, so it is tied to `FORGE_PINNED_REF` in `mtgsim/forge.py`.
