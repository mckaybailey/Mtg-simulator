# Step 4 (the pilot): results so far

Work of 16–17 November 2026 on branch `claude/gifted-mendel-ia018w` (based on
`claude/ai-decision-engine` at dfe6303). These numbers belong in `VALIDATION.md` and
`docs/ai-pilot-status.md`; they are kept here until the sample-run session's edits to those files
are merged, so the two sessions do not conflict.

All gauntlets: the deck against the other 17 meta decks, best-of-one, seed 1; "paired" intervals
compare the same seeds with and without the change (`tools/compare_arms.py`).

## (i) Mana sinks and wrong-phase activations in the underrated decks

`tools/log_analysis/activations.py` on a `--save-logs` gauntlet of each of Jund Sacrifice, Dimir
Uldaros, Izzet Spellementals, Four-Color Control and Dimir Excruciator (30 games per pairing,
seed 1, 2,700 games). Three leads, one per deck; the two Dimir decks had none (Restless Reef is
animated in combat, Seasoned Cryomancer's draw in the second main phase).

| Patch | Card (deck) | AI error | Without | With | Paired difference |
|---|---|---|---|---|---|
| 0012, dropped | Umbral Collar Zealot (Jund Sacrifice) | "about to die" pays a sacrifice cost with creatures outside combat, for surveil 1 | 40.5% | 40.0% | −0.5 (−0.9 to −0.0) |
| 0013 | Stoke Genius (Izzet Spellementals) | "discard your hand, draw two" cast with any hand (219 of 249 casts discarded 3+) | 32.9% | 36.2% | +3.3 (+1.6 to +5.0) |
| 0014 | Great Hall of the Biblioplex (Four-Color Control) | permanent {5} animate paid in its own upkeep (398 times), tapping out for two turns | 42.1% | 54.2% | +12.1 (+9.9 to +14.4) |

0014 also covers Soulstone Sanctuary: Mono-Black Aggro −0.8 (−1.9 to +0.4) and Dimir Midrange
+0.6 (−1.0 to +2.2), both within noise, in the shipped version (third revision; the first cost
Mono-Black Aggro −2.8). Details in `mtgsim/forge_patches/README.md` and `pending/README.md`.

## (ii) `--mc fixed` A/B

Azorius Control with `ai_mc: fixed` on its own seat (a copy of the list with its own
`gauntlet.json`, `runs/mcfix/hero/`) against the default-piloted field, 60 games per opponent,
1,020 games per arm, seed 1, Forge with patches 0001–0011, 0013, 0014 (17 Nov 2026):

| Arm | Win rate |
|---|---|
| Default AI | 42.1% (39–45%) |
| `--mc fixed` for Azorius Control | 51.1% (48–54%) |
| Difference | **+9.0 points**, 95% CI +4.7 to +13.3; paired +5.7 to +12.4 (203 losses became wins, 111 wins losses) |

All 1,020 searching games finished (no time-outs); engine time 21.2 s a game (median 14.0 s,
longest 922 s), 238 rollouts a game, search 86% of the engine time (`tools/mc_cost.py`). The
earlier 200-game result (+6.0, −2.9 to +14.8) is confirmed: the counted search plays Azorius
Control better. It gained most against Dimir Midrange (43 → 62), Golgari Midrange (25 → 43),
Boros Dwarves (23 → 37) and Rakdos Lizards (37 → 50); nothing against Mono-Green Landfall, Dimir
Uldaros or Dimir Excruciator. Real win rate 46.6%.

The same A/B for the two decks the simulation underrates most (17 Nov, same setup):

| Deck (real) | Default AI | `--mc fixed` on its seat | Paired difference |
|---|---|---|---|
| Azorius Control (46.6%) | 42.1% (39–45%) | 51.1% (48–54%) | +9.0 (+5.7 to +12.4) |
| Jund Sacrifice (57.6%) | 40.1% (37–43%) | 50.4% (47–53%) | +10.3 (+7.3 to +13.3) |
| Dimir Uldaros (49.2%) | 30.0% (27–33%) | 43.7% (41–47%) | +13.7 (+10.4 to +17.0) |
| Boros Dwarves (50.2%), control | 73.7% (71–76%) | 76.7% (74–79%) | +2.9 (+0.0 to +5.9) |

The three underrated, planning-heavy decks gain 9–14 points beyond noise and move towards their
real win rates; the overrated creature deck gains about 3 (interval touching zero). Search helps
the decks the simulation underrates three to five times as much as the deck it overrates, which
is what a narrower spread needs. All 4,080 searching games finished without a time-out.

## (iii) Round robin with `--mc fixed` for every seat

The 18 meta decks, best-of-one, 20 games per pairing, seed 1, 3,060 games per arm, Forge with
patches 0001–0011, 0013, 0014 (17 Nov 2026): `matrix decks/standard/meta -n 20 --seed 1` with
and without `--mc fixed` (`runs/rr18-default`, `runs/rr18-mcfixed`; no time-outs or errors).
`tools/calibration.py` and `tools/calibration_diff.py`, 1,000 resamples:

| Share-weighted, 18 decks | Default AI | `--mc fixed` everywhere | B − A (95% interval) |
|---|---|---|---|
| SD (real 6.0) | 13.8 | 13.2 | −0.6 (−2.5 to +1.3) |
| Mean absolute gap | 11.5 | 10.6 | −1.0 (−2.5 to +1.2) |
| Spearman | 0.16 | 0.10 | −0.06 (−0.20 to +0.08) |
| Pearson | 0.34 | 0.28 | −0.07 (−0.19 to +0.07) |

Equal-weighted: SD 13.8 → 12.5 (−1.3, −2.6 to +0.3), gap 11.0 → 10.4 (−0.5, −2.1 to +0.9).
**Nothing changes beyond noise.** Searching on one seat against default opponents lifts the
planning decks by 9–14 points, but when the opponents search too most of that edge is gone:
Jund Sacrifice is still 18 points under its real rate (37.1% → 39.7% weighted), Dimir Uldaros
12 under; Mono-Green Landfall (+24) and Mono-Black Aggro (+25) end further over. The deck order
reshuffles (Orzhov Lifegain +10 → −1, Dimir Midrange −3 → −14, Boros Dwarves +21 → +14) without
coming closer to the real one. The one-seat gains measure "search beats the default AI", not a
pilot that plays these decks the way people do.

What this leaves: the two remaining levers in the plan, the format and the field (steps 1–3) and
a stronger pilot (this step), each move single decks but not the spread. The simulator's ranking of
these meta decks should be reported as it is: decided matchups and A/B differences between lists
of one deck are what mtgsim measures well; the meta win rates of a deck against the field are not.
