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
0014 was measured and moved up as well (Four-Color Control +11.8 points, paired 95% CI +9.6 to +14.1). Nothing is pending now.

**0014, revised** (`0014-land-animate-revised.patch.txt`, named so that nothing applies it): the
shipped 0014 was measured on Four-Color Control only, but its rule also covers Soulstone Sanctuary
({4}: a 3/3 vigilance creature for good) in Dimir Midrange, Mono-Black Aggro and 13 lists of the
100-list sample. Against the other 17 meta decks (100 games each, seed 1, without and with 0014):
Dimir Midrange 52.2% → 52.5% (+0.2, paired CI −1.3 to +1.8), Mono-Black Aggro 68.5% → 65.7%
(−2.8, paired −4.0 to −1.5): the aggro deck now attacks with the land a turn later. The revision
also allows the animate before the AI's own attack when the land is untapped and no instant or
flash card in hand wants the mana; it is being measured on all three decks and replaces 0014 if
it keeps Four-Color Control's gain without the loss.

First revision measured (16–17 Nov, against the same without-arms): Four-Color Control +11.8
(paired −/+: +9.6 to +14.0), Mono-Black Aggro −1.7 (paired −2.9 to −0.5). Mono-Black Aggro
holds nine instant removal spells, so one in hand stopped the precombat animate even with mana
to spare. A second revision (`0014-land-animate-revised-mana.patch.txt`) allows it when the mana
left afterwards still pays for the cheapest instant or flash card in hand; being measured.

Second revision measured: Mono-Black Aggro −0.1 (paired −1.0 to +0.9), but Four-Color Control
only +4.6 (paired +2.4 to +6.7, 1,534 of 1,700 games): its cheapest instant costs two, so it went
back to tapping five lands in its first main phase. Third revision
(`0014-land-animate-revised-attack.patch.txt`): before the AI's own attack, the animated land
must attack this turn (`ComputerUtilCard.doesSpecifiedCreatureAttackAI`, which Forge already
uses for temporary animates) and the mana left must pay for all instant and flash cards in hand.
Being measured.

Third revision measured and shipped as 0014 (17 Nov): Four-Color Control +12.1 (paired +9.9 to
+14.4), Mono-Black Aggro −0.8 (paired −1.9 to +0.4), Dimir Midrange +0.6 (paired −1.0 to +2.2),
mirror 49.5%. The revision files were removed; their text is in the git history of this folder.
