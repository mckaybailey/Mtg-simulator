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
| 0014-land-animate-at-opponents-end-step | Four-Color Control (Great Hall of the Biblioplex) | 0001–0011, 0013 (and the dropped 0012) |

## Dropped

**0012-no-library-sac-when-dying** (Jund Sacrifice, Umbral Collar Zealot). In the declare
blockers step, when `ComputerUtilCombat.lifeInSeriousDanger` holds, `ComputerUtil.getCardPreference`
pays any sacrifice cost with anything; for the Zealot's surveil 1 that sacrificed creatures
outside combat (33 of 510 games in the log run). The patch let a Scry/Surveil/Mill outlet pay only
with a creature the combat destroys anyway. Measured (`gauntlet jund-sacrifice --vs <the other 17
meta decks> -n 100 --seed 1`, on 0001–0011, 16 Nov 2026): 40.5% (38–43) without, 40.0% (38–42)
with, −0.5 points, paired 95% CI −0.9 to −0.0 (12 wins became losses, 4 losses wins, 1,684 of
1,700 games unchanged). Most of the lost wins end on the same turn: in this deck a sacrifice is
not only a surveil, it also triggers Biotech Specialist (2 damage per artifact) and The
Sackville-Bagginses (1 life per token), so the last-ditch sacrifices sometimes win the race. Not
shipped. 0013 and 0014 were measured on builds that included it in both arms; it changes 16 of
1,700 of Jund's games and no other deck casts the Zealot.

0013 was measured and moved up to the shipped series (Izzet Spellementals +3.3 points, paired 95% CI +1.6 to +5.0).
