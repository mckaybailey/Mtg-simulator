import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mtgsim import cli, misplay, report
from mtgsim.decks import deck_from_text
from mtgsim.experiment import Entrant
from tests.helpers import game, make_db, signals

DECK = {"Mountain": 20, "Mystic Gate": 4, "Hill Giant": 4, "Shock": 4, "Cancel": 4, "Murder": 4}
ROLES = {"Mountain": ["land"], "Mystic Gate": ["land"], "Hill Giant": ["creature"], "Shock": ["instant", "removal"],
         "Cancel": ["counter", "instant"], "Murder": ["instant", "removal"]}


def _cards(result, key="hero"):
    return {r["card"]: r for r in result["decks"][key]["cards"]}


class OldRunTest(unittest.TestCase):
    """Records without the misplay fields still give the 'rarely cast' ranking."""

    def setUp(self):
        self.records = []
        for i in range(10):
            hero = {"opening": {"Hill Giant": 1, "Shock": 1, "Mystic Gate": 1}, "drawn": {"Murder": 1} if i < 4 else {},
                    "played": {"Shock": 1} if i % 2 else {}}
            self.records.append(game("hero", "foe", i, winner="a" if i < 5 else "b", a_extra=hero))

    def test_never_cast_ranking(self):
        self.assertFalse(misplay.has_signals(self.records))
        result = misplay.analyze(self.records, {"hero": {"key": "hero", "main": DECK}}, lands={"Mountain", "Mystic Gate"})
        deck = result["decks"]["hero"]
        self.assertEqual(deck["basis"], "never_cast")
        self.assertEqual(deck["signal_games"], 0)
        cards = _cards(result)
        self.assertNotIn("Mystic Gate", cards, "lands named by the card database are left out")
        self.assertNotIn("Mountain", cards)
        self.assertEqual(cards["Hill Giant"]["never_cast"], 10)
        self.assertEqual(cards["Hill Giant"]["score"], 100.0)
        self.assertEqual(cards["Shock"]["never_cast"], 5)
        self.assertEqual(cards["Shock"]["score"], 50.0)
        self.assertEqual(cards["Murder"]["score"], 40.0, "never cast in 4 of 10 games of the deck")
        self.assertEqual(cards["Cancel"]["score"], 0.0, "never seen")
        self.assertEqual([r["card"] for r in deck["cards"]][:3], ["Hill Giant", "Shock", "Murder"])
        self.assertNotIn("idle", cards["Hill Giant"], "no idle data in old runs")
        self.assertEqual(misplay.top_cards(deck, limit=10)[-1]["card"], "Murder", "zero scores are not shown")

    def test_without_card_database_only_basics_are_known_lands(self):
        cards = _cards(misplay.analyze(self.records, {"hero": {"key": "hero", "main": DECK}}))
        self.assertNotIn("Mountain", cards)
        self.assertIn("Mystic Gate", cards)

    def test_entrant_list_and_empty_decks(self):
        result = misplay.analyze(self.records, [{"key": "hero", "main": DECK}, {"key": "foe", "main": {"Forest": 60}},
                                                {"key": "absent", "main": DECK}])
        self.assertEqual(sorted(result["decks"]), ["foe", "hero"], "decks without games are left out")


class SignalTest(unittest.TestCase):
    def _game(self, i, winner="a", **fields):
        fields.setdefault("roles", ROLES)
        return game("hero", "foe", i, winner=winner, a_extra=signals(**fields))

    def test_idle_uses_the_free_window(self):
        records = [
            # Hill Giant castable on 3 own turns and never cast; Shock idle on own turns only (normal holding)
            self._game(0, opening={"Hill Giant": 1, "Shock": 1}, idle_own={"Hill Giant": 3, "Shock": 2}),
            # Shock idle on an opponent's turn, cast later: idle but not flagged
            self._game(1, opening={"Shock": 1, "Hill Giant": 1}, played={"Shock": 1, "Hill Giant": 1},
                       idle_opp={"Shock": 1, "Hill Giant": 4}),
            self._game(2, opening={"Hill Giant": 1}, played={"Hill Giant": 1}),
        ]
        cards = _cards(misplay.analyze(records, {"hero": {"main": DECK}}))
        giant, shock = cards["Hill Giant"], cards["Shock"]
        self.assertEqual(giant["idle"]["windows"], 3, "a sorcery-speed card only counts its owner's turns")
        self.assertEqual(giant["idle"]["opponent_turns"], 4)
        self.assertEqual(giant["idle"]["castable_games"], 1)
        self.assertEqual(giant["idle"]["never_cast_games"], 1)
        self.assertEqual(giant["idle"]["never_cast_share"], 1.0)
        self.assertAlmostEqual(giant["idle"]["per_game"], 1.0, msg="3 windows over 3 games seen")
        self.assertEqual(giant["flagged_games"], 1)
        self.assertAlmostEqual(giant["score"], 100 / 3)
        self.assertEqual(shock["idle"]["windows"], 1, "an instant only counts opponents' turns")
        self.assertTrue(shock["idle"]["instant_speed"])
        self.assertEqual(shock["idle"]["never_cast_games"], 0)
        self.assertEqual(shock["flagged_games"], 0)
        self.assertEqual(shock["score"], 0.0)
        self.assertIn("castable on its own turns but never cast", giant["reasons"][0])

    def test_stranded(self):
        records = [self._game(i, winner="b" if i < 4 else "a", opening={"Murder": 1},
                              end_hand={"Murder": 1} if i < 4 else {}, lands_in_hand=2 if i < 5 else 0,
                              idle_opp={"Murder": 1} if i == 0 else {}) for i in range(10)]
        deck = misplay.analyze(records, {"hero": {"main": DECK}})["decks"]["hero"]
        murder = _cards({"decks": {"hero": deck}})["Murder"]
        stranded = murder["stranded"]
        self.assertEqual(stranded["games"], 4)
        self.assertEqual(stranded["rate"], 0.4)
        self.assertEqual(stranded["win_rate"], 0.0)
        self.assertEqual(stranded["other_win_rate"], 1.0)
        self.assertEqual(stranded["castable_games"], 1)
        self.assertEqual(murder["flagged_games"], 1, "stranded without ever being castable is not flagged")
        self.assertEqual(deck["lands_left_in_hand"], 1.0)

    def test_removal_targets(self):
        records = [
            self._game(0, opening={"Murder": 2}, played={"Murder": 2},
                       removal={"Murder": {"casts": 2, "own": 0, "poor": 1, "quality": 1.4}}),
            self._game(1, opening={"Murder": 1}, played={"Murder": 1},
                       removal={"Murder": {"casts": 1, "own": 1, "poor": 1, "quality": 0.0}}),
            self._game(2, opening={"Murder": 1}, played={"Murder": 1},
                       removal={"Murder": {"casts": 1, "own": 0, "poor": 0, "quality": 1.0}}),
        ]
        murder = _cards(misplay.analyze(records, {"hero": {"main": DECK}}))["Murder"]
        self.assertEqual(murder["removal"]["casts"], 4)
        self.assertEqual(murder["removal"]["poor"], 2)
        self.assertEqual(murder["removal"]["poor_share"], 0.5)
        self.assertEqual(murder["removal"]["own"], 1)
        self.assertAlmostEqual(murder["removal"]["mean_quality"], 0.6)
        self.assertEqual(murder["removal"]["poor_games"], 2)
        self.assertEqual(murder["flagged_games"], 2)
        self.assertIn("2 of 4 casts at a poor target, 1 at its caster's own permanent", murder["reasons"])

    def test_counter_windows(self):
        records = [
            self._game(0, opening={"Cancel": 1}, counter={"Cancel": {"passed": 2, "passedMaxMv": 5, "cast": 0,
                                                                     "targets": 0, "targetMv": 0}}),
            self._game(1, opening={"Cancel": 1}, counter={"Cancel": {"passed": 1, "passedMaxMv": 1, "cast": 0,
                                                                     "targets": 0, "targetMv": 0}}),
            self._game(2, opening={"Cancel": 1}, played={"Cancel": 1},
                       counter={"Cancel": {"passed": 0, "passedMaxMv": 0, "cast": 1, "targets": 1, "targetMv": 4}}),
            self._game(3, opening={"Cancel": 1}),
        ]
        cancel = _cards(misplay.analyze(records, {"hero": {"main": DECK}}))["Cancel"]
        counter = cancel["counter"]
        self.assertEqual(counter["passed"], 3)
        self.assertEqual(counter["passed_games"], 2)
        self.assertEqual(counter["big_passed_games"], 1, f"only spells of mana value {misplay.BIG_SPELL}+ count")
        self.assertEqual(counter["casts"], 1)
        self.assertEqual(counter["mean_countered_mv"], 4.0)
        self.assertEqual(cancel["flagged_games"], 1)
        self.assertIn("counter", cancel["roles"])

    def test_flagged_win_rate_difference(self):
        strong = [self._game(i, winner="b" if i < 30 else "a", opening={"Hill Giant": 1},
                             idle_own={"Hill Giant": 2} if i < 30 else {},
                             played={} if i < 30 else {"Hill Giant": 1}) for i in range(60)]
        giant = _cards(misplay.analyze(strong, {"hero": {"main": DECK}}))["Hill Giant"]
        self.assertEqual(giant["compare"]["games"], 30)
        self.assertEqual(giant["compare"]["diff"], -1.0)
        self.assertTrue(giant["compare"]["significant"])
        weak = strong[:1] + strong[30:31]
        giant = _cards(misplay.analyze(weak, {"hero": {"main": DECK}}))["Hill Giant"]
        self.assertEqual(giant["compare"]["diff"], -1.0)
        self.assertFalse(giant["compare"]["significant"], "two games cannot show a difference")

    def test_only_decided_games_and_mixed_runs(self):
        records = [
            self._game(0, opening={"Hill Giant": 1}, idle_own={"Hill Giant": 1}),
            self._game(1, winner=None, opening={"Hill Giant": 1}, idle_own={"Hill Giant": 1}),  # a draw
            game("hero", "foe", 2, status="timeout", a_extra=signals(opening={"Hill Giant": 1})),
            game("hero", "foe", 3, winner="a", a_extra={"opening": {"Hill Giant": 1}}),  # recorded by an old driver
        ]
        result = misplay.analyze(records, {"hero": {"main": DECK}})
        self.assertTrue(result["signals"])
        deck = result["decks"]["hero"]
        self.assertEqual(deck["games"], 2)
        self.assertEqual(deck["signal_games"], 1)
        giant = _cards(result)["Hill Giant"]
        self.assertEqual(giant["seen"], 2)
        self.assertEqual(giant["signal_games"], 1)
        self.assertEqual(giant["idle"]["windows"], 1)
        self.assertEqual(giant["score"], 100.0, "flagged in the one game with signals")

    def test_roles_name_lands(self):
        records = [self._game(0, opening={"Mystic Gate": 1, "Hill Giant": 1})]
        cards = _cards(misplay.analyze(records, {"hero": {"main": DECK}}))
        self.assertNotIn("Mystic Gate", cards, "the driver's land role is enough")


EVIL = 'Evil <script>alert(1)</script> "card"'


class RenderTest(unittest.TestCase):
    def _has(self, text, html):
        self.assertTrue(text in html, f"{text!r} missing from the report")

    def _lacks(self, text, html):
        self.assertFalse(text in html, f"{text!r} should not be in the report")

    def _summary(self, records, entrants):
        return {
            "kind": "match", "title": "t", "created": "now", "format": "Standard", "forge": {}, "options": {},
            "entrants": {e.key: e.describe() for e in entrants}, "deck_notes": {}, "problems": {}, "caveat": "c",
            "pairings": [cli.analysis.summarize_pairing(records, "hero", "foe")], "cards": {},
            "misplays": misplay.analyze(records, {e.key: e.describe() for e in entrants}),
        }

    def _entrants(self):
        db = make_db()
        hero = Entrant("hero", deck_from_text("40 Mountain\n20 Shock\n", 'Hero <b>"deck"</b>', db), role="hero")
        foe = Entrant("foe", deck_from_text("40 Mountain\n20 Hill Giant\n", "Foe", db))
        hero.deck.main[EVIL] = 1  # a name that must be escaped wherever it appears
        return hero, foe

    def test_section_escapes_names(self):
        hero, foe = self._entrants()
        records = [game("hero", "foe", i, winner="a" if i % 2 else "b", a_extra=signals(
            opening={EVIL: 1, "Shock": 1}, idle_own={EVIL: 2}, end_hand={EVIL: 1},
            removal={"Shock": {"casts": 1, "own": 1, "poor": 1, "quality": 0.0}},
            roles={EVIL: ["creature"], "Shock": ["instant", "removal"], "Mountain": ["land"]})) for i in range(6)]
        html = report.render(self._summary(records, [hero, foe]))
        self._has("Likely AI misplays", html)
        self._lacks("<script>alert(1)", html)
        self._lacks('<b>"deck"</b>', html)
        self._has("Evil &lt;script&gt;alert(1)&lt;/script&gt; &quot;card&quot;", html)
        self._has("castable on its own turns but never cast", html)
        self._has("heuristics", html)

    def test_old_run_section(self):
        hero, foe = self._entrants()
        records = [game("hero", "foe", i, winner="a", a_extra={"opening": {"Shock": 1}}) for i in range(4)]
        html = report.render(self._summary(records, [hero, foe]))
        self._has("Likely AI misplays", html)
        self._has("recorded before", html)

    def test_no_section_without_data(self):
        hero, foe = self._entrants()
        summary = self._summary([game("hero", "foe", 0, winner="a")], [hero, foe])
        del summary["misplays"]
        self._lacks("Likely AI misplays", report.render(summary))


class CommandTest(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("MTGSIM_HOME")
        os.environ["MTGSIM_HOME"] = self._home.name  # no Forge here: lands come from the records
        self.run_dir = Path(self._home.name) / "run"
        self.run_dir.mkdir()
        entrants = [{"key": "hero", "name": "Hero", "role": "hero", "main": DECK},
                    {"key": "foe", "name": "Foe <X>", "role": "opponent", "main": {"Mountain": 40, "Hill Giant": 20}}]
        (self.run_dir / "run.json").write_text(json.dumps({"kind": "match", "entrants": entrants,
                                                           "pairings": [["hero", "foe"]]}), encoding="utf-8")
        with open(self.run_dir / "games.jsonl", "w", encoding="utf-8") as out:
            for i in range(12):
                record = game("hero", "foe", i, winner="b" if i < 8 else "a", a_extra=signals(
                    opening={"Hill Giant": 1, "Murder": 1}, played={"Murder": 1} if i >= 8 else {},
                    idle_own={"Hill Giant": 2}, idle_opp={"Murder": 1} if i < 8 else {}, roles=ROLES),
                    b_extra=signals(opening={"Hill Giant": 1}, played={"Hill Giant": 1},
                                    roles={"Hill Giant": ["creature"]}))
                out.write(json.dumps(record) + "\n")

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("MTGSIM_HOME", None)
        else:
            os.environ["MTGSIM_HOME"] = self._old_home
        self._home.cleanup()

    def _run(self, *args, run_dir=None):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = cli.main(["misplays", str(run_dir or self.run_dir), *args])
        return code, buf.getvalue()

    def test_prints_every_deck(self):
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("Hero", out)
        self.assertIn("Foe <X>", out)
        self.assertIn("Hill Giant", out)
        self.assertIn("Murder", out)
        self.assertIn("heuristics", out)
        self.assertLess(out.index("Hill Giant"), out.index("Murder"), "ranked by games affected")

    def test_one_deck_top_and_json(self):
        path = Path(self._home.name) / "out.json"
        code, out = self._run("--deck", "hero", "--top", "1", "--json", str(path))
        self.assertEqual(code, 0)
        self.assertNotIn("Foe <X>", out)
        self.assertNotIn("Murder", out)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(list(data["decks"]), ["hero"])
        self.assertTrue(data["signals"])

    def test_unknown_deck_and_missing_run(self):
        self.assertEqual(self._run("--deck", "nobody")[0], 1)
        self.assertEqual(self._run(run_dir=self.run_dir / "nope")[0], 1)


if __name__ == "__main__":
    unittest.main()
