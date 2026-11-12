import unittest

from mtgsim import analysis, cli, report
from mtgsim.decks import deck_from_text
from mtgsim.experiment import Entrant
from tests.helpers import game, make_db

EVIL = 'Evil <script>alert(1)</script> "deck"'


def _entrant(key, name, role="opponent", weight=None, pilot=""):
    deck = deck_from_text("40 Mountain\n20 Shock\n", name, make_db())
    return Entrant(key, deck, role=role, weight=weight, category="aggro", pilot=pilot)


def _summary(kind, entrants, **extra):
    base = {
        "kind": kind, "title": f"{kind} of {EVIL}", "created": "2026-11-11 10:00:00", "format": "Standard",
        "forge": {"forgeVersion": "2.0.17"}, "options": {"games_per_pairing": 20, "seed": 1, "timeout": 180,
                                                          "monte_carlo": "off", "ai_profile": "Default"},
        "elapsed_seconds": 120.0, "entrants": {e.key: e.describe() for e in entrants},
        "deck_notes": {entrants[0].key: ['warning: <b>odd</b> note']},
        "problems": {"timeouts": 1, "errors": 0}, "caveat": cli.AI_CAVEAT, "mtgsim_version": "test",
    }
    base.update(extra)
    return base


def _records(a, b, wins, n=20):
    return [game(a, b, i, winner="a" if i < wins else "b", first="a" if i % 2 else "b",
                 a_extra={"opening": {"Shock": 1}} if i % 3 == 0 else None) for i in range(n)]


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.hero = _entrant("hero", EVIL, role="hero")
        self.variant = _entrant("variant", "Variant", role="variant")
        self.foes = [_entrant("x", "Opp <X>", weight=12.5, pilot="weak"), _entrant("y", "Opp Y", weight=5.0, pilot="fair")]

    def _check(self, html):
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<b>odd</b>", html)
        self.assertNotIn("Opp <X>", html)
        self.assertIn("Read this first", html)
        return html

    def test_gauntlet(self):
        records = _records("hero", "x", 18) + _records("hero", "y", 9)
        pairings = [analysis.summarize_pairing(records, "hero", k) for k in ("x", "y")]
        field = analysis.summarize_field("hero", pairings, {"x": 12.5, "y": 5.0})
        entrants = [self.hero] + self.foes
        html = self._check(report.render(_summary(
            "gauntlet", entrants, hero="hero", pairings=pairings, field={"hero": field},
            cards={"hero": analysis.card_stats(records, "hero", dict(self.hero.deck.main))}, goldfish={})))
        self.assertIn("67.5%", html, "equal-weight win rate of 90% and 45%")
        self.assertIn("Clearly favoured against: Opp &lt;X&gt;", html)
        self.assertIn("Discount the results against Opp &lt;X&gt;", html)
        self.assertIn("Card performance", html)
        self.assertIn("Weighted by meta share", html)

    def test_match(self):
        records = _records("hero", "x", 12)
        pairing = analysis.summarize_pairing(records, "hero", "x")
        html = self._check(report.render(_summary("match", [self.hero, self.foes[0]], pairings=[pairing], cards={}, goldfish={})))
        self.assertIn("60.0%", html)
        self.assertIn("When games end", html)

    def test_ab(self):
        records = (_records("hero", "x", 16) + _records("hero", "y", 12) + _records("variant", "x", 8)
                   + _records("variant", "y", 10) + _records("hero", "variant", 11))
        pairs = [("hero", "x"), ("hero", "y"), ("variant", "x"), ("variant", "y"), ("hero", "variant")]
        pairings = [analysis.summarize_pairing(records, a, b) for a, b in pairs]
        ab = analysis.summarize_ab("hero", "variant", pairings, {"x": 12.5, "y": 5.0})
        fields = {k: analysis.summarize_field(k, [p for p in pairings if p["b"] in ("x", "y")]) for k in ("hero", "variant")}
        html = self._check(report.render(_summary(
            "ab", [self.hero, self.variant] + self.foes, hero="hero", variant="variant", pairings=pairings,
            field=fields, ab=ab, deck_changes=["-4 Shock", "+4 Mountain"], cards={}, goldfish={})))
        self.assertIn("+25.0 pts", html, "70% versus 45% against the field")
        self.assertIn("Changes from A to B: -4 Shock, +4 Mountain", html)
        self.assertIn("Head to head", html)

    def test_matrix(self):
        records = _records("hero", "x", 15) + _records("hero", "y", 10) + _records("x", "y", 4)
        pairings = [analysis.summarize_pairing(records, a, b) for a, b in (("hero", "x"), ("hero", "y"), ("x", "y"))]
        matrix = analysis.summarize_matrix(["hero", "x", "y"], pairings)
        html = self._check(report.render(_summary("matrix", [self.hero] + self.foes, pairings=pairings, matrix=matrix, cards={})))
        self.assertIn("Matchup grid", html)
        self.assertIn(">75<", html)
        self.assertIn(">25<", html)

    def test_clock(self):
        passive = _entrant("passive", "Passive opponent")
        records = [game("hero", "passive", i, winner="a", turns=4 + i % 3) for i in range(12)]
        clock = analysis.summarize_clock(records, "hero", "passive")
        html = self._check(report.render(_summary("clock", [self.hero, passive], hero="hero", clock=clock, goldfish={})))
        self.assertIn("Winning turn", html)
        self.assertIn("5.0", html)

    def test_report_handles_a_pairing_with_no_decided_games(self):
        records = [game("hero", "x", 0, winner=None, status="timeout")]
        pairings = [analysis.summarize_pairing(records, "hero", "x")]
        field = analysis.summarize_field("hero", pairings)
        self._check(report.render(_summary("gauntlet", [self.hero, self.foes[0]], hero="hero", pairings=pairings,
                                           field={"hero": field}, cards={}, goldfish={})))


class CliHelpersTest(unittest.TestCase):
    def test_parser_accepts_each_command(self):
        parser = cli.build_parser()
        cases = [
            ["setup", "--build"], ["doctor"], ["check", "a.txt", "b.txt", "--format", "modern"],
            ["match", "a.txt", "b.txt", "-n", "50", "-j", "2", "--seed", "9"],
            ["gauntlet", "a.txt", "--vs", "d1", "d2", "--strict"], ["ab", "a.txt", "b.txt", "--head-to-head"],
            ["matrix", "folder", "--mc", "max"], ["goldfish", "a.txt", "--clock"], ["report", "runs/x"],
        ]
        for argv in cases:
            args = parser.parse_args(argv)
            self.assertTrue(callable(args.func), argv)
        self.assertEqual(200, parser.parse_args(["goldfish", "a.txt", "--clock"]).clock)
        self.assertEqual(0, parser.parse_args(["goldfish", "a.txt"]).clock)
        self.assertEqual("standard", parser.parse_args(["match", "a", "b"]).format)

    def test_table_alignment(self):
        text = cli._table(["Name", "N"], [["a", "1"], ["longer", "22"]], right=(1,))
        lines = text.splitlines()
        self.assertEqual(4, len(lines))
        self.assertTrue(lines[2].endswith(" 1") and lines[3].endswith("22"))

    def test_deck_diff(self):
        db = make_db()
        a = deck_from_text("4 Shock\n20 Mountain\n", "a", db)
        b = deck_from_text("2 Shock\n2 Hill Giant\n20 Mountain\n", "b", db)
        self.assertEqual(["+2 Hill Giant", "-2 Shock"], cli._deck_diff(a, b))

    def test_no_command_prints_help(self):
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(2, cli.main([]))
        self.assertIn("gauntlet", out.getvalue())


if __name__ == "__main__":
    unittest.main()
