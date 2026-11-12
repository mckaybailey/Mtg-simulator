"""End-to-end tests that play real games on Forge.

They are skipped unless a Forge installation is configured (``mtgsim setup`` or
``MTGSIM_FORGE_DIR``) and Java is available, so the rest of the suite stays fast and
dependency-free. They use two simple creature decks that cannot stall each other, so games always finish.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from mtgsim import analysis, experiment, forge
from mtgsim.decks import deck_from_text
from mtgsim.experiment import Entrant, RunOptions


def _forge_or_skip():
    try:
        install = forge.find_install()
        forge.check_java()
        forge.ensure_bridge(install)
        return install
    except forge.ForgeError as exc:
        raise unittest.SkipTest(f"Forge is not available: {exc}")


class ForgeIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = _forge_or_skip()
        from mtgsim.carddb import load_database

        cls.db = load_database(cls.install)
        cls.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-it-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _entrants(self):
        bears = deck_from_text("20 Forest\n40 Grizzly Bears\n", "bears", self.db)
        giants = deck_from_text("20 Mountain\n40 Raging Goblin\n", "giants", self.db)
        self.assertEqual([], bears.errors + giants.errors)
        return [Entrant("bears", bears), Entrant("giants", giants)]

    def _play(self, name, games=6, seed=3, workers=2):
        entrants = self._entrants()
        records = experiment.execute(
            self.install, self.tmp / name, entrants, [(entrants[0], entrants[1])],
            RunOptions(games=games, seed=seed, workers=workers, timeout=120), quiet=True,
        )
        return sorted(records, key=lambda r: r["game"])

    def test_games_complete_with_structured_results(self):
        records = self._play("basic")
        self.assertEqual(6, len(records))
        for record in records:
            self.assertEqual("ok", record["status"], record.get("error"))
            self.assertIn(record["winner_seat"], (0, 1))
            self.assertIn(record["first_seat"], (0, 1))
            self.assertGreater(record["turns"], 0)
            for seat, player in enumerate(record["players"]):
                self.assertEqual(60, player["mainCount"])
                self.assertEqual(7 - player["mulligans"], sum(player["opening"].values()))
                expected = {"bears": {"Forest", "Grizzly Bears"}, "giants": {"Mountain", "Raging Goblin"}}
                self.assertLessEqual(set(player["opening"]) | set(player["drawn"]) | set(player["played"]),
                                     expected[record["seats"][seat]])
        summary = analysis.summarize_pairing(records, "bears", "giants")
        self.assertEqual(6, summary["decided"])
        self.assertEqual(6, summary["on_play"]["games"] + summary["on_draw"]["games"])

    def test_same_seed_replays_the_same_games(self):
        first = self._play("replay-a", seed=9, workers=2)
        second = self._play("replay-b", seed=9, workers=1)
        self.assertEqual(
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"]) for r in first],
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"]) for r in second],
        )

    def test_different_seeds_give_different_games(self):
        first = self._play("seed-a", seed=1)
        second = self._play("seed-b", seed=2)
        self.assertNotEqual([r["players"] for r in first], [r["players"] for r in second])

    def test_resume_does_not_replay_recorded_games(self):
        self._play("resume", games=4)
        before = (self.tmp / "resume" / "games.jsonl").read_text(encoding="utf-8")
        records = self._play("resume", games=6)
        after = (self.tmp / "resume" / "games.jsonl").read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before))
        self.assertEqual(6, len(records))
        self.assertEqual(6, len(after.strip().splitlines()))


if __name__ == "__main__":
    unittest.main()
