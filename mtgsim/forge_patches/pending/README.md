# Patches waiting for their measurement

`setup --build` applies only `../*.patch`, so nothing here changes any build. These are
candidates from step 4 of `docs/ai-pilot-status.md` (mana sinks and wrong-phase activations in
the underrated decks), each with its cause in the `Why:` line and `Measured: PENDING`. Each
moves up to `..` once it has been measured as `../README.md` says (the deck against the other
17 meta decks, 100 games each, seed 1, without and with, plus a 200-game mirror), with the numbers in
its `Measured:` line, or is dropped.

To build with them: copy them into `..` in a private `MTGSIM_HOME` checkout of this repository,
or point a private build at a copy of the folder; never on the shared `~/.mtgsim/forge` while
games run on it.

| Patch | Deck | Measured on top of |
|---|---|---|
| 0012-no-library-sac-when-dying | Jund Sacrifice (Umbral Collar Zealot) | 0001–0011 |
| 0013-discard-hand-only-when-small | Izzet Spellementals (Stoke Genius) | 0001–0012 |
| 0014-land-animate-at-opponents-end-step | Four-Color Control (Great Hall of the Biblioplex) | 0001–0013 |
