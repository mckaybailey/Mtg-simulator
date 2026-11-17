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

Next, as planned: the same A/B for Jund Sacrifice and Dimir Uldaros, the two decks the
simulation underrates most; only if they gain too is a round robin with `fixed` for the weak
decks worth its cost.
