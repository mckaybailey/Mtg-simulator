import tempfile
import unittest
from pathlib import Path

from mtgsim import legality
from mtgsim.decks import deck_from_text
from tests.helpers import make_db


def _res():
    tmp = Path(tempfile.mkdtemp(prefix="mtgsim-fmt-"))
    folder = tmp / "formats" / "Sanctioned"
    folder.mkdir(parents=True)
    (folder / "Standard.txt").write_text(
        "[format]\nName:Standard\nSets:NEW\nBanned:Grizzly Bears; Something Else\n", encoding="utf-8")
    (folder / "Vintage.txt").write_text(
        "[format]\nName:Vintage\nSets:NEW, OLD\nRestricted:Black Lotus\n", encoding="utf-8")
    (folder / "Pauper.txt").write_text("[format]\nName:Pauper\nRarities:L, C\n", encoding="utf-8")
    return tmp


class LegalityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = make_db()
        cls.res = _res()

    def _issues(self, text, fmt):
        deck = deck_from_text(text, "d", self.db)
        return [str(i) for i in legality.check_deck(deck, self.db, legality.get_format(self.res, fmt))]

    def test_formats_are_read_from_forge_files(self):
        formats = legality.load_formats(self.res)
        self.assertEqual({"standard", "vintage", "pauper"}, set(formats))
        self.assertEqual({"NEW"}, formats["standard"].sets)
        self.assertIn("Grizzly Bears", formats["standard"].banned)

    def test_unknown_format_is_rejected_and_casual_means_none(self):
        with self.assertRaises(ValueError):
            legality.get_format(self.res, "nonsense")
        self.assertIsNone(legality.get_format(self.res, "casual"))

    def test_legal_deck_has_no_issues(self):
        self.assertEqual([], self._issues("4 Lightning Strike\n4 Hill Giant\n52 Mountain\n", "standard"))

    def test_too_few_cards_and_too_many_sideboard_cards(self):
        issues = self._issues("Deck\n40 Mountain\n\nSideboard\n16 Mountain\n", "standard")
        self.assertTrue(any("main deck has 40" in i for i in issues))
        self.assertTrue(any("sideboard has 16" in i for i in issues))

    def test_copy_limit_counts_main_and_sideboard_but_not_basics_or_any_number_cards(self):
        issues = self._issues("Deck\n3 Lightning Strike\n30 Rat Colony\n27 Mountain\n\nSideboard\n2 Lightning Strike\n", "vintage")
        self.assertEqual(1, len(issues), issues)
        self.assertIn("5 copies of Lightning Strike", issues[0])

    def test_banned_and_out_of_format_cards(self):
        issues = self._issues("4 Grizzly Bears\n4 Shock\n52 Mountain\n", "standard")
        self.assertTrue(any("Grizzly Bears is banned" in i for i in issues))
        self.assertTrue(any("Shock is not legal in Standard" in i for i in issues))
        self.assertTrue(all(i.startswith("error") for i in issues))

    def test_restricted_card(self):
        self.assertTrue(any("restricted" in i for i in self._issues("2 Black Lotus\n58 Mountain\n", "vintage")))
        self.assertEqual([], self._issues("1 Black Lotus\n59 Mountain\n", "vintage"))

    def test_rarity_format(self):
        issues = self._issues("4 Fire // Ice\n4 Hill Giant\n52 Mountain\n", "pauper")
        self.assertEqual(1, len(issues), issues)
        self.assertIn("Fire // Ice", issues[0])

    def test_casual_reports_construction_problems_as_warnings_only(self):
        issues = self._issues("10 Shock\n30 Mountain\n", "casual")
        self.assertEqual(2, len(issues))
        self.assertTrue(all(i.startswith("warning") for i in issues))


if __name__ == "__main__":
    unittest.main()
