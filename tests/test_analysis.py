import unittest

from mtgsim import analysis
from tests.helpers import game


def _records():
    """Ten games of hero vs foe: 6 wins, 2 losses, one draw, one timeout."""
    out = []
    for i in range(6):
        out.append(game("hero", "foe", i, winner="a", first="a" if i < 4 else "b", turns=5))
    out.append(game("hero", "foe", 6, winner="b", first="a", turns=8))
    out.append(game("hero", "foe", 7, winner="b", first="b", turns=8))
    out.append(game("hero", "foe", 8, winner=None, first="a"))
    out.append(game("hero", "foe", 9, winner=None, first="a", status="timeout"))
    return out


class PairingTest(unittest.TestCase):
    def test_win_rate_uses_decided_games_only(self):
        p = analysis.summarize_pairing(_records(), "hero", "foe")
        self.assertEqual((10, 8, 6, 2, 1, 1, 0), (p["games"], p["decided"], p["wins"], p["losses"], p["draws"], p["timeouts"], p["errors"]))
        self.assertAlmostEqual(0.75, p["win_rate"])
        self.assertLess(p["ci"][0], 0.75)
        self.assertGreater(p["ci"][1], 0.75)

    def test_play_draw_split_follows_who_went_first(self):
        p = analysis.summarize_pairing(_records(), "hero", "foe")
        self.assertEqual((5, 4), (p["on_play"]["games"], p["on_play"]["wins"]))
        self.assertEqual((3, 2), (p["on_draw"]["games"], p["on_draw"]["wins"]))
        self.assertAlmostEqual((0.8 + 2 / 3) / 2, p["balanced_win_rate"])

    def test_seats_alternate_so_results_follow_the_deck_not_the_seat(self):
        records = [game("hero", "foe", i, winner="a") for i in range(4)]
        self.assertEqual([0, 1, 0, 1], [r["winner_seat"] for r in records])
        self.assertEqual(4, analysis.summarize_pairing(records, "hero", "foe")["wins"])

    def test_winning_turns_and_reasons(self):
        p = analysis.summarize_pairing(_records(), "hero", "foe")
        self.assertEqual({"5": 6}, p["kill_turns_a"])
        self.assertEqual({"8": 2}, p["kill_turns_b"])
        self.assertAlmostEqual(5.0, p["avg_turn_a_wins"])
        self.assertEqual({"LifeReachedZero": 6}, p["how_a_wins"])

    def test_other_pairings_are_ignored(self):
        records = _records() + [game("hero", "other", 0, winner="b")]
        self.assertEqual(10, analysis.summarize_pairing(records, "hero", "foe")["games"])

    def test_flip_is_an_exact_mirror(self):
        p = analysis.summarize_pairing(_records(), "hero", "foe")
        f = analysis.flip(p)
        self.assertEqual(("foe", "hero", 2, 6), (f["a"], f["b"], f["wins"], f["losses"]))
        self.assertAlmostEqual(0.25, f["win_rate"])
        self.assertEqual((3, 1), (f["on_play"]["games"], f["on_play"]["wins"]))
        self.assertEqual((5, 1), (f["on_draw"]["games"], f["on_draw"]["wins"]))
        self.assertEqual(p["kill_turns_b"], f["kill_turns_a"])
        back = analysis.flip(f)
        for key in ("a", "b", "wins", "losses", "win_rate", "ci", "on_play", "on_draw", "kill_turns_a", "how_a_wins"):
            self.assertEqual(p[key], back[key], key)

    def test_mirror_match_with_one_key_on_both_seats(self):
        records = [game("same", "same", i, winner="a" if i % 3 else "b") for i in range(9)]
        p = analysis.summarize_pairing(records, "same", "same")
        self.assertEqual((6, 3), (p["wins"], p["losses"]))


class FieldAndAbTest(unittest.TestCase):
    def _pairings(self):
        records = []
        for i in range(20):
            records.append(game("A", "x", i, winner="a" if i < 16 else "b"))   # A beats x 80%
            records.append(game("A", "y", i, winner="a" if i < 6 else "b"))    # A beats y 30%
            records.append(game("B", "x", i, winner="a" if i < 10 else "b"))   # B beats x 50%
            records.append(game("B", "y", i, winner="a" if i < 6 else "b"))    # B beats y 30%
            records.append(game("A", "B", i, winner="a" if i < 12 else "b"))   # head to head 60%
        return [analysis.summarize_pairing(records, a, b)
                for a, b in (("A", "x"), ("A", "y"), ("B", "x"), ("B", "y"), ("A", "B"))]

    def test_field_summary_gives_pooled_mean_and_weighted_rates(self):
        pairings = [p for p in self._pairings() if p["a"] == "A" and p["b"] in ("x", "y")]
        field = analysis.summarize_field("A", pairings, {"x": 10.0, "y": 30.0})
        self.assertEqual((22, 40), (field["wins"], field["decided"]))
        self.assertAlmostEqual(0.55, field["pooled"]["win_rate"])
        self.assertAlmostEqual(0.55, field["mean"]["rate"])
        self.assertAlmostEqual((0.8 * 10 + 0.3 * 30) / 40, field["weighted"]["rate"])
        self.assertAlmostEqual(40.0, field["weighted"]["coverage"])
        self.assertIsNone(analysis.summarize_field("A", pairings, {"x": None, "y": None})["weighted"])

    def test_ab_compares_shared_opponents_and_finds_the_head_to_head(self):
        ab = analysis.summarize_ab("A", "B", self._pairings())
        self.assertEqual(["x", "y"], [r["opponent"] for r in ab["rows"]])
        self.assertAlmostEqual(0.30, ab["rows"][0]["diff"])
        self.assertAlmostEqual(0.0, ab["rows"][1]["diff"])
        self.assertAlmostEqual(0.15, ab["overall_mean"]["diff"])
        self.assertEqual(40, ab["games_each"])
        self.assertAlmostEqual(0.6, ab["head_to_head"]["win_rate"])
        self.assertFalse(ab["significant"], "a 15-point gap over 40 games each is not conclusive")
        text = analysis.ab_verdict(ab, "Alpha", "Beta")
        self.assertIn("No reliable difference", text)

    def test_ab_calls_a_large_gap_and_names_the_better_deck(self):
        records = []
        for i in range(200):
            records.append(game("A", "x", i, winner="a" if i < 150 else "b"))
            records.append(game("B", "x", i, winner="a" if i < 90 else "b"))
        pairings = [analysis.summarize_pairing(records, k, "x") for k in ("A", "B")]
        ab = analysis.summarize_ab("A", "B", pairings)
        self.assertTrue(ab["significant"])
        self.assertEqual("A", ab["better"])
        self.assertTrue(analysis.ab_verdict(ab, "Alpha", "Beta").startswith("Alpha did better"))
        reverse = analysis.summarize_ab("B", "A", pairings)
        self.assertEqual("A", reverse["better"])
        self.assertTrue(analysis.ab_verdict(reverse, "Beta", "Alpha").startswith("Alpha did better"))

    def test_ab_without_shared_opponents(self):
        ab = analysis.summarize_ab("A", "B", [])
        self.assertIsNone(ab["overall_mean"]["diff"])
        self.assertIn("cannot be compared", analysis.ab_verdict(ab, "A", "B"))


class MatrixCardsClockTest(unittest.TestCase):
    def test_matrix_is_antisymmetric_and_ranked(self):
        records = []
        for i in range(10):
            records.append(game("a", "b", i, winner="a" if i < 8 else "b"))
            records.append(game("a", "c", i, winner="a" if i < 6 else "b"))
            records.append(game("b", "c", i, winner="a" if i < 5 else "b"))
        pairings = [analysis.summarize_pairing(records, x, y) for x, y in (("a", "b"), ("a", "c"), ("b", "c"))]
        matrix = analysis.summarize_matrix(["a", "b", "c"], pairings)
        self.assertEqual("a", matrix["order"][0])
        self.assertIsNone(matrix["grid"]["a"]["a"])
        self.assertAlmostEqual(0.8, matrix["grid"]["a"]["b"]["win_rate"])
        self.assertAlmostEqual(0.2, matrix["grid"]["b"]["a"]["win_rate"])
        self.assertAlmostEqual(0.7, matrix["ranking"][0]["mean_win_rate"])

    def test_card_stats_split_games_by_whether_the_card_was_seen(self):
        records = []
        for i in range(10):  # the card is seen in games 0-5; hero wins games 0-3 and 6
            seen = i < 6
            extra = {"opening": {"Bolt": 1} if i < 2 else {}, "drawn": {"Bolt": 1} if 2 <= i < 6 else {},
                     "played": {"Bolt": 1} if i < 3 else {}}
            records.append(game("hero", "foe", i, winner="a" if i < 4 or i == 6 else "b", a_extra=extra if seen else None))
        records.append(game("hero", "foe", 10, winner=None))
        stats = analysis.card_stats(records, "hero", {"Bolt": 4, "Unseen": 2})
        self.assertEqual((10, 5), (stats["games"], stats["wins"]))
        bolt = next(c for c in stats["cards"] if c["card"] == "Bolt")
        self.assertEqual((6, 4), (bolt["seen"]["games"], bolt["seen"]["wins"]))
        self.assertEqual((4, 1), (bolt["not_seen"]["games"], bolt["not_seen"]["wins"]))
        self.assertEqual((2, 2), (bolt["opening"]["games"], bolt["opening"]["wins"]))
        self.assertAlmostEqual(4 / 6 - 1 / 4, bolt["iwd"])
        self.assertAlmostEqual(0.5, bolt["play_rate"])
        unseen = next(c for c in stats["cards"] if c["card"] == "Unseen")
        self.assertIsNone(unseen["iwd"])

    def test_card_stats_count_both_seats_of_a_mirror(self):
        records = [game("same", "same", 0, winner="a", a_extra={"opening": {"Bolt": 1}})]
        stats = analysis.card_stats(records, "same", {"Bolt": 4})
        self.assertEqual((2, 1), (stats["games"], stats["wins"]))

    def test_clock_distribution(self):
        records = [game("hero", "passive", i, winner="a", turns=4 if i < 3 else 6) for i in range(8)]
        records.append(game("hero", "passive", 8, winner=None, status="timeout"))
        clock = analysis.summarize_clock(records, "hero", "passive")
        self.assertEqual((9, 8, 1), (clock["games"], clock["won"], clock["not_won"]))
        self.assertEqual((4, 6), (clock["fastest_turn"], clock["median_turn"]))
        by_turn = {t["turn"]: t["by_turn"] for t in clock["turns"]}
        self.assertAlmostEqual(3 / 9, by_turn[4])
        self.assertAlmostEqual(8 / 9, by_turn[6])


if __name__ == "__main__":
    unittest.main()
