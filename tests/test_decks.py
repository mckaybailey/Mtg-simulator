import unittest

from mtgsim.decks import deck_from_text, parse_deck_text
from tests.helpers import make_db


class ParseDeckTextTest(unittest.TestCase):
    def test_arena_export_with_set_codes_and_headers(self):
        text = "About\nName Burn Baby\n\nDeck\n4 Lightning Strike (DFT) 137\n20 Mountain (FDN) 279\n\nSideboard\n2 Shock (M21) 159\n"
        name, entries = parse_deck_text(text, "file")
        self.assertEqual("Burn Baby", name)
        self.assertEqual([("main", 4, "Lightning Strike"), ("main", 20, "Mountain"), ("side", 2, "Shock")], entries)

    def test_headerless_list_treats_a_small_final_block_as_the_sideboard(self):
        main = "".join(f"4 Card{i}\n" for i in range(15))
        _, entries = parse_deck_text(main + "\n3 Shock\n2 Fire // Ice\n")
        self.assertEqual(60, sum(n for sec, n, _ in entries if sec == "main"))
        self.assertEqual([("side", 3, "Shock"), ("side", 2, "Fire // Ice")], [e for e in entries if e[0] == "side"])

    def test_blank_lines_between_groups_do_not_create_a_sideboard(self):
        _, entries = parse_deck_text("4 Shock\n\n4 Hill Giant\n\n20 Mountain\n")
        self.assertTrue(all(section == "main" for section, _, _ in entries))

    def test_forge_dck_format(self):
        text = "[metadata]\nName=My Deck\n[Main]\n4 Shock|M21|1\n3 Mountain|FDN\n[Sideboard]\n1 Hill Giant|FDN\n"
        name, entries = parse_deck_text(text, "file")
        self.assertEqual("My Deck", name)
        self.assertEqual([("main", 4, "Shock"), ("main", 3, "Mountain"), ("side", 1, "Hill Giant")], entries)

    def test_quantity_styles_comments_and_sb_prefix(self):
        text = "# name: Commented\n// a comment\n4x Shock\nHill Giant\nSB: 2 Lightning Strike\n"
        name, entries = parse_deck_text(text)
        self.assertEqual("Commented", name)
        self.assertEqual([("main", 4, "Shock"), ("main", 1, "Hill Giant"), ("side", 2, "Lightning Strike")], entries)

    def test_split_card_names_survive(self):
        _, entries = parse_deck_text("Deck\n4 Fire // Ice (APC) 128\n")
        self.assertEqual([("main", 4, "Fire // Ice")], entries)


class DeckFromTextTest(unittest.TestCase):
    def setUp(self):
        self.db = make_db()

    def test_names_resolve_to_the_engines_spelling(self):
        deck = deck_from_text("4 lightning strike\n2 Fire/Ice\n1 Delver of Secrets // Insectile Aberration\n20 MOUNTAIN\n", "d", self.db)
        self.assertEqual({"Lightning Strike": 4, "Fire // Ice": 2, "Delver of Secrets": 1, "Mountain": 20}, dict(deck.main))
        self.assertEqual([], deck.errors)

    def test_duplicate_lines_are_added_together(self):
        deck = deck_from_text("2 Shock\n2 Shock\n", "d", self.db)
        self.assertEqual(4, deck.main["Shock"])

    def test_unknown_card_is_an_error_with_a_suggestion(self):
        deck = deck_from_text("4 Lightnin Strike\n20 Mountain\n", "d", self.db)
        self.assertEqual(1, len(deck.errors))
        self.assertIn("Lightnin Strike", deck.errors[0].message)
        self.assertIn("Lightning Strike", deck.errors[0].message)
        self.assertEqual(20, deck.main_count, "the unknown card is left out rather than guessed")

    def test_empty_list_is_an_error(self):
        self.assertTrue(deck_from_text("\n\n", "d", self.db).errors)

    def test_dck_output_round_trips(self):
        deck = deck_from_text("Deck\n4 Shock\n20 Mountain\n\nSideboard\n2 Hill Giant\n", "Round Trip", self.db)
        again = deck_from_text(deck.to_dck(), "x", self.db)
        self.assertEqual((deck.main, deck.side, "Round Trip"), (again.main, again.side, again.name))

    def test_fingerprint_follows_main_deck_contents_only(self):
        one = deck_from_text("4 Shock\n20 Mountain\n", "a", self.db)
        same = deck_from_text("20 Mountain\n4 Shock\n\nSideboard\n1 Hill Giant\n", "b", self.db)
        other = deck_from_text("3 Shock\n21 Mountain\n", "a", self.db)
        self.assertEqual(one.fingerprint(), same.fingerprint())
        self.assertNotEqual(one.fingerprint(), other.fingerprint())


if __name__ == "__main__":
    unittest.main()
