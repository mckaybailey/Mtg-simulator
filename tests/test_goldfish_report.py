"""The consistency section of the HTML report renders whatever goldfish.analyze returns."""

import unittest
from collections import Counter

from mtgsim import goldfish, goldfish_report, report
from mtgsim.carddb import CardDatabase, parse_card_script
from mtgsim.decks import Deck

SCRIPTS = [
    "Name:Mountain\nManaCost:no cost\nTypes:Basic Land Mountain\nOracle:({T}: Add {R}.)",
    "Name:Hill Giant\nManaCost:3 R\nTypes:Creature Giant\nPT:3/3\nOracle:",
    "Name:Shock <b>\nManaCost:R\nTypes:Instant\nOracle:Shock deals 2 damage to any target.",
]


def _result():
    db = CardDatabase(parse_card_script(s) for s in SCRIPTS)
    deck = Deck(name="Red <script>alert(1)</script>", main=Counter({"Mountain": 24, "Hill Giant": 20, "Shock <b>": 16}))
    return goldfish.analyze(deck, db, games=300, turns=6, seed=1)


class GoldfishReportTest(unittest.TestCase):
    def test_section_shows_the_headline_numbers(self):
        result = _result()
        html = goldfish_report.render({"red": result}, {"red": "Red deck"})
        self.assertIn("Mana and consistency", html)
        self.assertIn("Hill Giant", html)
        self.assertIn(report.pct(result["mana_screw"]["overall"]), html)
        self.assertIn(report.pct(result["opening_hand"]["mulligan_rate"], 0), html)

    def test_card_and_deck_names_are_escaped(self):
        html = goldfish_report.render({"red": _result(), "other": _result()},
                                      {"red": "Red <script>alert(1)</script>", "other": "Other"})
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("Shock <b>", html)
        self.assertIn("Shock &lt;b&gt;", html)

    def test_no_results_renders_nothing(self):
        self.assertEqual("", goldfish_report.render({}, {}))


if __name__ == "__main__":
    unittest.main()
