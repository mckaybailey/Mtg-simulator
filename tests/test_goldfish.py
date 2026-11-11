"""Tests for the goldfish analyzer, on hand-made cards so that no Forge installation is needed.

Many of them use a seven-card deck: the opening hand is then the whole deck and nothing is
ever drawn, so every game is identical and the play pattern can be checked exactly.
"""

import json
import math
import random
import unittest
from collections import Counter
from typing import Dict, List, Sequence

from mtgsim.carddb import Card, CardDatabase, Face, parse_card_script
from mtgsim.decks import Deck
from mtgsim.goldfish import analyze, format_text, unpaid_pips


def land(name: str, produces: str, tapped: bool = False) -> Card:
    return Card(name, faces=[Face(name, "no cost", ("Land",))], produces=produces, enters_tapped=tapped)


def spell(name: str, cost: str, types: Sequence[str] = ("Sorcery",), produces: str = "") -> Card:
    return Card(name, faces=[Face(name, cost, tuple(types))], produces=produces, mana_source=bool(produces))


LLANOWAR_ELVES = parse_card_script(
    "Name:Llanowar Elves\nManaCost:G\nTypes:Creature Elf Druid\nPT:1/1\n"
    "A:AB$ Mana | Cost$ T | Produced$ G | SpellDescription$ Add {G}.\nOracle:{T}: Add {G}."
)
BALA_GED_RECOVERY = parse_card_script(
    "Name:Bala Ged Recovery\nManaCost:2 G\nTypes:Sorcery\nAlternateMode:Modal\n"
    "Oracle:Return target card from your graveyard to your hand.\n\nALTERNATE\n\n"
    "Name:Bala Ged Sanctuary\nManaCost:no cost\nTypes:Land\n"
    "A:AB$ Mana | Cost$ T | Produced$ G | SpellDescription$ Add {G}.\n"
    "Oracle:Bala Ged Sanctuary enters tapped.\\n{T}: Add {G}."
)

CARDS = [
    land("Forest", "G"),
    land("Island", "U"),
    land("Mountain", "R"),
    land("Swamp", "B"),
    land("Steam Vents", "UR"),
    land("Thicket", "G", tapped=True),
    land("Maze", ""),
    LLANOWAR_ELVES,
    BALA_GED_RECOVERY,
    spell("Mox", "0", ("Artifact",), produces="G"),
    spell("Trinket", "0", ("Artifact",)),
    spell("Shock", "R", ("Instant",)),
    spell("Rat", "B", ("Creature", "Rat")),
    spell("Fireball", "X R"),
    spell("Bear", "1 G", ("Creature", "Bear")),
    spell("Ogre", "2 G", ("Creature", "Ogre")),
    spell("Giant", "5 G", ("Creature", "Giant")),
    spell("Wurm", "6 G", ("Creature", "Wurm")),
    spell("Counterspell", "U U", ("Instant",)),
    spell("Rot Bear", "BG BG", ("Creature", "Bear")),
]
DB = CardDatabase(CARDS)


def deck(**copies: int) -> Deck:
    """A deck from keyword arguments; underscores stand for the spaces in card names."""
    return Deck("test deck", Counter({name.replace("_", " "): n for name, n in copies.items()}))


def card_row(result: dict, name: str) -> dict:
    return next(row for row in result["cards"] if row["name"] == name)


def turn_row(result: dict, turn: int, seat: str = "overall") -> dict:
    return result["by_turn"][seat][turn - 1]


class UnpaidPipsTest(unittest.TestCase):
    def test_each_source_pays_one_symbol(self):
        self.assertEqual(unpaid_pips(["U", "U"], ["UR", "U"]), 0)
        self.assertEqual(unpaid_pips(["U", "U"], ["R", "UR"]), 1)
        self.assertEqual(unpaid_pips(["U", "R"], ["UR", "UR"]), 0)
        self.assertEqual(unpaid_pips(["U", "R"], ["UR"]), 1)
        self.assertEqual(unpaid_pips(["W", "U", "B"], ["WU", "UB", "WB"]), 0)
        self.assertEqual(unpaid_pips(["W", "W", "U"], ["WU", "WU", "B"]), 1)

    def test_hybrid_and_colourless_symbols(self):
        self.assertEqual(unpaid_pips(["BG", "BG"], ["B", "G"]), 0)
        self.assertEqual(unpaid_pips(["BG", "B"], ["B", "R"]), 1)
        self.assertEqual(unpaid_pips(["C"], ["W"]), 1)
        self.assertEqual(unpaid_pips(["C"], ["C"]), 0)

    def test_nothing_owed_or_nothing_to_pay_with(self):
        self.assertEqual(unpaid_pips([], ["W"]), 0)
        self.assertEqual(unpaid_pips(["W", "U"], []), 2)
        self.assertEqual(unpaid_pips(["W"], [""]), 1)

    def test_agrees_with_exhaustive_assignment(self):
        def most_paid(pips: List[str], sources: List[str]) -> int:
            if not pips:
                return 0
            best = most_paid(pips[1:], sources)  # leave the first symbol unpaid
            for index, source in enumerate(sources):
                if set(source) & set(pips[0]):
                    best = max(best, 1 + most_paid(pips[1:], sources[:index] + sources[index + 1:]))
            return best

        rng = random.Random(7)
        colour_sets = ["W", "U", "B", "R", "G", "C", "WU", "UB", "BR", "RG", "GW", "WUB", "WUBRG"]
        for _ in range(400):
            pips = [rng.choice(colour_sets[:11]) for _ in range(rng.randint(0, 5))]
            sources = [rng.choice(colour_sets) for _ in range(rng.randint(0, 6))]
            self.assertEqual(unpaid_pips(pips, sources), len(pips) - most_paid(pips, sources), (pips, sources))


class CompositionTest(unittest.TestCase):
    def test_counts_curve_pips_and_sources(self):
        list_ = deck(
            Forest=10, Swamp=4, Steam_Vents=2, Thicket=3, Maze=1,
            Llanowar_Elves=4, Bala_Ged_Recovery=2, Mox=1, Fireball=3, Bear=8, Rot_Bear=4, Giant=6, Wurm=2,
            Counterspell=10,
        )
        result = analyze(list_, DB, games=10, turns=2)
        comp = result["composition"]
        self.assertEqual(comp["cards"], 60)
        self.assertEqual(comp["lands"], 20)
        self.assertEqual(comp["modal_lands"], 2)
        self.assertEqual(comp["tapped_lands"], 3)
        self.assertEqual(comp["spells"], 40)
        self.assertEqual(comp["creatures"], 4 + 8 + 4 + 6 + 2)
        self.assertEqual(comp["other_spells"], 2 + 1 + 3 + 10)
        self.assertEqual(comp["nonland_mana_sources"], 5)
        # mana value:       0  1          2            3  4  5  6  7+
        self.assertEqual(comp["curve"], [1, 4 + 3, 8 + 4 + 10, 2, 0, 0, 6, 2])
        self.assertAlmostEqual(comp["avg_mana_value"], (7 * 1 + 22 * 2 + 2 * 3 + 6 * 6 + 2 * 7) / 40, places=4)
        # Each hybrid symbol of Rot Bear is half black, half green.
        self.assertEqual(comp["pips"], {"W": 0, "U": 20, "B": 4, "R": 3, "G": 4 + 2 + 8 + 4 + 6 + 2, "C": 0})
        self.assertEqual(comp["land_sources"], {"W": 0, "U": 2, "B": 4, "R": 2, "G": 13, "C": 0})
        self.assertEqual(comp["sources"], {"W": 0, "U": 2, "B": 4, "R": 2, "G": 13 + 4 + 2 + 1, "C": 0})
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("Maze", result["warnings"][0])

    def test_x_counts_as_zero(self):
        row = card_row(analyze(deck(Mountain=3, Fireball=4), DB, games=4), "Fireball")
        self.assertEqual((row["mana_value"], row["curve_turn"], row["cost"]), (1, 1, "{X}{R}"))
        self.assertEqual(row["castable"][0], 1.0)

    def test_cost_text(self):
        result = analyze(deck(Swamp=3, Rot_Bear=2, Trinket=1, Giant=1), DB, games=2)
        self.assertEqual(card_row(result, "Rot Bear")["cost"], "{B/G}{B/G}")
        self.assertEqual(card_row(result, "Trinket")["cost"], "{0}")
        self.assertEqual(card_row(result, "Giant")["cost"], "{5}{G}")


class OpeningHandTest(unittest.TestCase):
    def test_first_seven_matches_the_hypergeometric_distribution(self):
        result = analyze(deck(Forest=24, Bear=36), DB, games=20000, turns=1)
        simulated = result["opening_hand"]["lands_in_seven"]
        self.assertAlmostEqual(sum(simulated), 1.0, places=3)
        for lands in range(8):
            exact = math.comb(24, lands) * math.comb(36, 7 - lands) / math.comb(60, 7)
            self.assertAlmostEqual(simulated[lands], exact, delta=0.012, msg=f"{lands} lands")

    def test_keep_rule_against_exact_probabilities(self):
        # Seven are kept with 2-5 lands, so the mulligan rate is the chance of 0, 1, 6 or 7.
        result = analyze(deck(Forest=24, Bear=36), DB, games=20000, turns=1)
        exact = sum(math.comb(24, n) * math.comb(36, 7 - n) for n in (0, 1, 6, 7)) / math.comb(60, 7)
        opening = result["opening_hand"]
        self.assertAlmostEqual(opening["mulligan_rate"], exact, delta=0.012)
        self.assertAlmostEqual(opening["kept_hand_sizes"]["7"], 1 - exact, delta=0.012)
        self.assertAlmostEqual(sum(opening["kept_hand_sizes"].values()), 1.0, places=3)
        self.assertAlmostEqual(
            opening["avg_kept_hand_size"],
            sum(int(size) * share for size, share in opening["kept_hand_sizes"].items()),
            places=2,
        )

    def test_all_lands_is_kept_at_five(self):
        opening = analyze(deck(Forest=40), DB, games=50, turns=2)["opening_hand"]
        self.assertEqual(opening["mulligan_rate"], 1.0)
        self.assertEqual(opening["kept_hand_sizes"], {"7": 0.0, "6": 0.0, "5": 1.0, "4": 0.0})
        self.assertEqual(opening["avg_kept_hand_size"], 5.0)
        self.assertEqual(opening["lands_in_seven"][7], 1.0)
        self.assertEqual(opening["lands_in_kept_hand"][5], 1.0)

    def test_no_lands_goes_down_to_four(self):
        opening = analyze(deck(Bear=40), DB, games=50, turns=2)["opening_hand"]
        self.assertEqual(opening["kept_hand_sizes"]["4"], 1.0)
        self.assertEqual(opening["avg_kept_hand_size"], 4.0)
        self.assertEqual(opening["avg_lands_in_kept_hand"], 0.0)

    def test_an_excess_land_goes_to_the_bottom(self):
        # Six lands and a spell: mulligan once, keep six, and the card bottomed must be a land.
        opening = analyze(deck(Forest=6, Bear=1), DB, games=20, turns=2)["opening_hand"]
        self.assertEqual(opening["kept_hand_sizes"]["6"], 1.0)
        self.assertEqual(opening["lands_in_kept_hand"][5], 1.0)

    def test_the_most_expensive_spells_go_to_the_bottom(self):
        # With no lands the hand goes to four, bottoming its three dearest cards. Free Trinkets
        # are cast at once, so the spells cast on turn 1 on the play count the Trinkets kept.
        result = analyze(deck(Trinket=30, Wurm=30), DB, games=6000, turns=1)
        kept = sum(
            min(4, cheap) * math.comb(30, cheap) * math.comb(30, 7 - cheap) for cheap in range(8)
        ) / math.comb(60, 7)
        self.assertAlmostEqual(turn_row(result, 1, "play")["spells_cast"], kept, delta=0.04)

    def test_a_modal_land_can_make_a_hand_keepable(self):
        opening = analyze(deck(Forest=1, Bala_Ged_Recovery=1, Bear=5), DB, games=20, turns=2)["opening_hand"]
        self.assertEqual(opening["mulligan_rate"], 0.0)
        self.assertEqual(opening["lands_in_seven"][1], 1.0)


class PlayPatternTest(unittest.TestCase):
    def test_tapped_land_is_played_when_it_costs_nothing(self):
        # Turn 1 has nothing to cast, so the tapped land goes first and the Bear is on time.
        result = analyze(deck(Forest=1, Thicket=1, Bear=5), DB, games=20, turns=4)
        self.assertEqual(turn_row(result, 1)["mana_available"], 0.0)
        self.assertEqual(turn_row(result, 2)["mana_available"], 2.0)
        self.assertEqual(turn_row(result, 2)["mana_spent"], 2.0)
        self.assertEqual(card_row(result, "Bear")["castable"], [1.0, 1.0, 1.0])

    def test_tapped_land_gives_no_mana_the_turn_it_arrives(self):
        # Turn 3 has two Thickets untapped plus the Elves cast on turn 2.
        result = analyze(deck(Thicket=3, Llanowar_Elves=4), DB, games=20, turns=4)
        self.assertEqual([turn_row(result, turn)["mana_available"] for turn in (1, 2, 3)], [0.0, 1.0, 3.0])
        row = card_row(result, "Llanowar Elves")
        self.assertEqual(row["castable"], [0.0, 1.0, 1.0])
        self.assertEqual(row["enough_mana"], [0.0, 1.0, 1.0])

    def test_land_choice_looks_after_the_colours_in_hand(self):
        # Mountain and Steam Vents both cast Shock on turn 1; only Vents then Island casts
        # Counterspell on turn 2.
        result = analyze(deck(Island=1, Mountain=1, Steam_Vents=1, Shock=1, Counterspell=3), DB, games=20, turns=3)
        self.assertEqual(turn_row(result, 1)["mana_spent"], 1.0)
        self.assertEqual(turn_row(result, 2)["mana_spent"], 2.0)
        self.assertEqual(card_row(result, "Counterspell")["castable"][0], 1.0)

    def test_spends_as_much_mana_as_possible(self):
        # Turn 1: Forest and both free Moxen. Turn 2: four mana, and two Bears (4) beat one Ogre (3).
        result = analyze(deck(Forest=2, Mox=2, Ogre=1, Bear=2), DB, games=20, turns=3)
        self.assertEqual(turn_row(result, 1)["spells_cast"], 2.0)
        self.assertEqual(turn_row(result, 1)["mana_spent"], 0.0)
        self.assertEqual(turn_row(result, 2)["mana_available"], 4.0)
        self.assertEqual(turn_row(result, 2)["mana_spent"], 4.0)
        self.assertEqual(turn_row(result, 2)["spells_cast"], 2.0)
        self.assertEqual(turn_row(result, 3)["mana_spent"], 3.0)
        self.assertEqual(turn_row(result, 3)["cards_in_hand"], 0.0)

    def test_mana_creature_works_from_the_next_turn(self):
        result = analyze(deck(Forest=2, Llanowar_Elves=1, Ogre=4), DB, games=20, turns=3)
        self.assertEqual(turn_row(result, 1)["mana_available"], 1.0)
        self.assertEqual(turn_row(result, 1)["mana_spent"], 1.0)
        self.assertEqual(turn_row(result, 2)["mana_available"], 3.0)
        self.assertEqual(turn_row(result, 2)["mana_spent"], 3.0)
        self.assertEqual(turn_row(result, 2)["lands"], 2.0)

    def test_modal_card_is_a_land_only_without_a_real_one(self):
        # Two Forests: on turn 3 the hand has no land, so the modal card is played as one (tapped).
        short = analyze(deck(Forest=2, Bala_Ged_Recovery=1, Giant=4), DB, games=20, turns=4)
        self.assertEqual([turn_row(short, turn)["lands"] for turn in (2, 3, 4)], [2.0, 3.0, 3.0])
        self.assertEqual([turn_row(short, turn)["mana_available"] for turn in (3, 4)], [2.0, 3.0])
        self.assertEqual(turn_row(short, 3)["hit_all_land_drops"], 1.0)
        self.assertEqual(turn_row(short, 4)["hit_all_land_drops"], 0.0)
        self.assertEqual(card_row(short, "Bala Ged Recovery")["samples"], 0)
        # Three Forests: every drop is a real land, and the modal card is cast as a spell on turn 3.
        enough = analyze(deck(Forest=3, Bala_Ged_Recovery=1, Giant=3), DB, games=20, turns=4)
        self.assertEqual(turn_row(enough, 3)["mana_spent"], 3.0)
        self.assertEqual(turn_row(enough, 4)["lands"], 3.0)
        self.assertEqual(card_row(enough, "Bala Ged Recovery")["castable"][0], 1.0)

    def test_two_coloured_symbols_need_two_sources(self):
        result = analyze(deck(Island=1, Mountain=2, Counterspell=4), DB, games=20, turns=5)
        row = card_row(result, "Counterspell")
        self.assertEqual(row["samples"], 20)
        self.assertEqual(row["castable"], [0.0, 0.0, 0.0])
        self.assertEqual(row["enough_mana"], [1.0, 1.0, 1.0])
        self.assertEqual(turn_row(result, 3)["mana_spent"], 0.0)

    def test_castability_does_not_depend_on_which_land_was_chosen(self):
        # Turn 1 casts a Rat off the Swamp, but the Mountain in hand could have cast Shock instead.
        result = analyze(deck(Swamp=1, Mountain=1, Rat=3, Shock=2), DB, games=20, turns=2)
        self.assertEqual(turn_row(result, 1)["mana_spent"], 1.0)
        self.assertEqual(card_row(result, "Rat")["castable"][0], 1.0)
        self.assertEqual(card_row(result, "Shock")["castable"][0], 1.0)
        # A land that enters tapped is no such alternative. The model plays the Thicket on turn 1
        # (nothing is castable either way), yet the Mountain would have given one mana of the
        # wrong colour, so the Elves had enough mana but were not castable until turn 2.
        slow = analyze(deck(Thicket=1, Mountain=1, Llanowar_Elves=5), DB, games=20, turns=3)
        self.assertEqual(turn_row(slow, 1)["mana_available"], 0.0)
        self.assertEqual(card_row(slow, "Llanowar Elves")["castable"][:2], [0.0, 1.0])
        self.assertEqual(card_row(slow, "Llanowar Elves")["enough_mana"][:2], [1.0, 1.0])

    def test_hybrid_cost_takes_either_colour(self):
        result = analyze(deck(Swamp=1, Forest=1, Rot_Bear=5), DB, games=20, turns=3)
        self.assertEqual(card_row(result, "Rot Bear")["castable"][0], 1.0)

    def test_land_without_known_mana_pays_generic_only(self):
        result = analyze(deck(Maze=2, Forest=1, Bear=4), DB, games=20, turns=3)
        self.assertEqual(turn_row(result, 2)["mana_spent"], 2.0)  # Forest for {G}, Maze for {1}
        stuck = analyze(deck(Maze=3, Bear=4), DB, games=20, turns=3)
        self.assertEqual(card_row(stuck, "Bear")["castable"], [0.0, 0.0, None])  # turn 4 was not played
        self.assertEqual(card_row(stuck, "Bear")["enough_mana"], [1.0, 1.0, None])


class WholeDeckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.list = deck(Forest=16, Thicket=4, Steam_Vents=4, Llanowar_Elves=4, Bear=12, Ogre=8, Shock=4, Giant=8)
        cls.result = analyze(cls.list, DB, games=6000, turns=8, seed=3)

    def test_result_is_plain_json(self):
        self.assertEqual(json.loads(json.dumps(self.result)), self.result)
        self.assertEqual(
            set(self.result),
            {
                "deck", "games", "turns", "seed", "games_on_play", "games_on_draw", "composition",
                "opening_hand", "by_turn", "mana_screw", "mana_flood", "cards", "definitions", "warnings",
            },
        )
        self.assertEqual((self.result["games_on_play"], self.result["games_on_draw"]), (3000, 3000))
        self.assertEqual(set(self.result["by_turn"]), {"overall", "play", "draw"})
        for rows in self.result["by_turn"].values():
            self.assertEqual([row["turn"] for row in rows], list(range(1, 9)))
        for key in ("mana_screw", "mana_flood", "keep_rule", "castable", "model"):
            self.assertIn(key, self.result["definitions"])

    def test_same_seed_same_result(self):
        again = analyze(self.list, DB, games=6000, turns=8, seed=3)
        self.assertEqual(again, self.result)
        other = analyze(self.list, DB, games=6000, turns=8, seed=4)
        self.assertNotEqual(other["by_turn"], self.result["by_turn"])

    def test_order_of_the_decklist_does_not_matter(self):
        shuffled = Deck("test deck", Counter(dict(reversed(list(self.list.main.items())))))
        self.assertEqual(analyze(shuffled, DB, games=300, seed=3), analyze(self.list, DB, games=300, seed=3))

    def test_global_random_state_is_left_alone(self):
        random.seed(99)
        expected = random.random()
        random.seed(99)
        analyze(self.list, DB, games=50)
        self.assertEqual(random.random(), expected)

    def test_turn_rows_are_consistent(self):
        for seat in ("overall", "play", "draw"):
            previous_drops = 1.0
            for row in self.result["by_turn"][seat]:
                self.assertLessEqual(row["lands"], row["turn"])
                self.assertLessEqual(row["mana_spent"], row["mana_available"])
                self.assertLessEqual(row["hit_all_land_drops"], previous_drops)
                previous_drops = row["hit_all_land_drops"]
        for turn in range(1, 9):
            play, draw, overall = (turn_row(self.result, turn, seat) for seat in ("play", "draw", "overall"))
            self.assertAlmostEqual(overall["lands"], (play["lands"] + draw["lands"]) / 2, places=3)
            self.assertGreaterEqual(draw["lands"], play["lands"])
        # The extra card on the draw is still in hand, or already on the table, after turn 1.
        self.assertGreater(
            turn_row(self.result, 1, "draw")["cards_in_hand"], turn_row(self.result, 1, "play")["cards_in_hand"]
        )

    def test_castability_grows_with_time_and_never_beats_the_mana(self):
        for row in self.result["cards"]:
            self.assertGreater(row["samples"], 0)
            self.assertEqual(row["curve_turn"], max(1, row["mana_value"]))
            measured = [value for value in row["castable"] if value is not None]
            self.assertEqual(measured, sorted(measured))
            for castable, enough in zip(row["castable"], row["enough_mana"]):
                if castable is not None:
                    self.assertLessEqual(castable, enough)
        # Green is everywhere in this mana base; red comes from four Steam Vents only.
        self.assertGreater(card_row(self.result, "Bear")["castable"][0], card_row(self.result, "Shock")["castable"][0])
        shock = card_row(self.result, "Shock")
        self.assertGreater(shock["enough_mana"][0] - shock["castable"][0], 0.3)
        self.assertEqual([row["mana_value"] for row in self.result["cards"]], [1, 1, 2, 3, 6])

    def test_more_lands_mean_less_screw_and_more_flood(self):
        light = analyze(deck(Forest=17, Bear=20, Ogre=15, Giant=8), DB, games=8000)
        heavy = analyze(deck(Forest=27, Bear=15, Ogre=12, Giant=6), DB, games=8000)
        for seat in ("overall", "play", "draw"):
            self.assertGreater(light["mana_screw"][seat], heavy["mana_screw"][seat] + 0.08)
            self.assertLess(light["mana_flood"][seat], heavy["mana_flood"][seat] - 0.04)
        self.assertGreater(light["mana_screw"]["play"], light["mana_screw"]["draw"])
        self.assertGreater(light["opening_hand"]["mulligan_rate"], heavy["opening_hand"]["mulligan_rate"])

    def test_format_text(self):
        text = format_text(self.result)
        for expected in ("test deck", "6,000 games", "COMPOSITION", "OPENING HAND", "TURN BY TURN",
                         "MANA SCREW AND FLOOD", "CASTABLE ON TIME", "Llanowar Elves", "{5}{G}",
                         self.result["definitions"]["mana_screw"], self.result["definitions"]["mana_flood"]):
            self.assertIn(expected, text)
        self.assertNotIn("WARNINGS", text)
        self.assertEqual(format_text(json.loads(json.dumps(self.result))), text)


class EdgeCaseTest(unittest.TestCase):
    def test_short_runs_leave_unmeasurable_values_empty(self):
        result = analyze(deck(Forest=24, Maze=1, Bear=20, Giant=15), DB, games=1, turns=3)
        self.assertEqual((result["games_on_play"], result["games_on_draw"]), (1, 0))
        self.assertEqual(result["mana_screw"], {"overall": None, "play": None, "draw": None})
        self.assertEqual(result["mana_flood"], {"overall": None, "play": None, "draw": None})
        self.assertIsNone(turn_row(result, 1, "draw")["lands"])
        giant = card_row(result, "Giant")
        self.assertEqual((giant["samples"], giant["castable"], giant["enough_mana"]), (0, [None] * 3, [None] * 3))
        self.assertIsNone(card_row(result, "Bear")["castable"][2])
        text = format_text(result)
        self.assertIn("WARNINGS", text)
        self.assertIn("Maze", text)

    def test_screw_and_flood_need_enough_turns(self):
        result = analyze(deck(Forest=24, Bear=36), DB, games=200, turns=5)
        self.assertIsNotNone(result["mana_screw"]["overall"])
        self.assertIsNone(result["mana_flood"]["overall"])

    def test_library_can_run_out(self):
        result = analyze(deck(Forest=5, Bear=4), DB, games=10, turns=12)
        self.assertEqual(turn_row(result, 12)["lands"], 5.0)
        self.assertEqual(turn_row(result, 12)["cards_in_hand"], 0.0)

    def test_bad_input(self):
        with self.assertRaisesRegex(ValueError, "Black Lotus"):
            analyze(deck(Forest=20, Black_Lotus=4), DB, games=10)
        with self.assertRaises(ValueError):
            analyze(deck(Forest=6), DB, games=10)
        with self.assertRaises(ValueError):
            analyze(deck(Forest=24, Bear=36), DB, games=0)
        with self.assertRaises(ValueError):
            analyze(deck(Forest=24, Bear=36), DB, games=10, turns=0)


if __name__ == "__main__":
    unittest.main()
