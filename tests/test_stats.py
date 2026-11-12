import unittest

from mtgsim import stats


class StatsTest(unittest.TestCase):
    def test_wilson_matches_known_values(self):
        lo, hi = stats.wilson(50, 100)
        self.assertAlmostEqual(0.404, lo, places=3)
        self.assertAlmostEqual(0.596, hi, places=3)
        lo, hi = stats.wilson(0, 20)
        self.assertEqual(0.0, lo)
        self.assertAlmostEqual(0.161, hi, places=3)
        self.assertEqual((None, None), stats.wilson(0, 0))

    def test_wilson_narrows_with_more_games(self):
        widths = [hi - lo for lo, hi in (stats.wilson(n // 2, n) for n in (20, 100, 400, 1600))]
        self.assertEqual(sorted(widths, reverse=True), widths)

    def test_exact_binomial_p_value(self):
        self.assertAlmostEqual(0.0569, stats.binomial_p_even(60, 100), places=3)
        self.assertAlmostEqual(1.0, stats.binomial_p_even(50, 100), places=6)
        self.assertEqual(stats.binomial_p_even(40, 100), stats.binomial_p_even(60, 100))
        self.assertIsNone(stats.binomial_p_even(0, 0))
        self.assertLess(stats.binomial_p_even(1300, 2400), 0.001)  # normal-approximation branch

    def test_diff_test(self):
        same = stats.diff_test(50, 100, 50, 100)
        self.assertAlmostEqual(0.0, same["diff"])
        self.assertAlmostEqual(1.0, same["p"])
        clear = stats.diff_test(70, 100, 40, 100)
        self.assertAlmostEqual(0.30, clear["diff"])
        self.assertLess(clear["p"], 0.001)
        self.assertGreater(clear["ci"][0], 0.15)
        self.assertLess(clear["ci"][1], 0.45)
        self.assertIsNone(stats.diff_test(1, 2, 0, 0)["diff"])

    def test_weighted_rate(self):
        equal = stats.weighted_rate([(80, 100), (20, 100)])
        self.assertAlmostEqual(0.5, equal["rate"])
        weighted = stats.weighted_rate([(80, 100), (20, 100)], [3, 1])
        self.assertAlmostEqual(0.65, weighted["rate"])
        self.assertLess(weighted["ci"][0], 0.65)
        self.assertGreater(weighted["ci"][1], 0.65)
        skipped = stats.weighted_rate([(80, 100), (0, 0)])
        self.assertAlmostEqual(0.8, skipped["rate"], msg="matchups without games are left out")
        self.assertIsNone(stats.weighted_rate([])["rate"])
        perfect = stats.weighted_rate([(10, 10)])
        self.assertLess(perfect["ci"][0], 1.0, "a perfect record still carries uncertainty")

    def test_weighted_diff(self):
        result = stats.weighted_diff([(70, 100), (60, 100)], [(50, 100), (40, 100)])
        self.assertAlmostEqual(0.20, result["diff"])
        self.assertLess(result["p"], 0.01)
        none = stats.weighted_diff([(5, 10)], [(0, 0)])
        self.assertIsNone(none["diff"])

    def test_games_to_detect(self):
        self.assertTrue(1500 < stats.games_to_detect(0.05) < 1650)
        self.assertGreater(stats.games_to_detect(0.03), stats.games_to_detect(0.05))
        self.assertIsNone(stats.games_to_detect(0))


if __name__ == "__main__":
    unittest.main()
