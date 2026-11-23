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

    def _play(self, name, games=6, seed=3, workers=2, **options):
        entrants = self._entrants()
        records = experiment.execute(
            self.install, self.tmp / name, entrants, [(entrants[0], entrants[1])],
            RunOptions(games=games, seed=seed, workers=workers, timeout=120, **options), quiet=True,
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
                # Misplay fields: these decks have no instants, counterspells or removal.
                spells = expected[record["seats"][seat]] - {"Forest", "Mountain"}
                self.assertIsInstance(player["endHandLands"], int)
                self.assertLessEqual(set(player["endHand"]) | set(player["idleOwn"]), spells)
                self.assertEqual({}, player["idleOpp"])
                self.assertEqual({}, player["counter"])
                self.assertEqual({}, player["removal"])
                self.assertLessEqual(set(player["opening"]) | set(player["drawn"]), set(player["roles"]))
                for name, tags in player["roles"].items():
                    self.assertEqual(["creature"] if name in spells else ["land"], tags, name)
        summary = analysis.summarize_pairing(records, "bears", "giants")
        self.assertEqual(6, summary["decided"])
        self.assertEqual(6, summary["on_play"]["games"] + summary["on_draw"]["games"])
        from mtgsim import misplay

        misplays = misplay.analyze(records, {e.key: e.describe() for e in self._entrants()})
        self.assertTrue(misplays["signals"])
        self.assertEqual({"bears", "giants"}, set(misplays["decks"]))
        self.assertEqual("flagged", misplays["decks"]["bears"]["basis"])

    def test_same_seed_replays_the_same_games(self):
        first = self._play("replay-a", seed=9, workers=2)
        second = self._play("replay-b", seed=9, workers=1)
        self.assertEqual(
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"]) for r in first],
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"]) for r in second],
        )

    def test_snapshots_do_not_change_games_and_follow_the_records(self):
        plain = self._play("snap-off", games=4, seed=9, workers=2)
        snapped = self._play("snap-on", games=4, seed=9, workers=2, snapshots=True)
        self.assertEqual(
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"]) for r in plain],
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"]) for r in snapped],
        )
        import json

        folder = self.tmp / "snap-on" / "snapshots"
        self.assertEqual(4, len(list(folder.glob("*.jsonl"))))
        self.assertFalse((self.tmp / "snap-off" / "snapshots").exists())
        for record in snapped:
            lines = [json.loads(l) for l in (folder / f"bears__giants__{record['game']:04d}.jsonl").read_text().splitlines()]
            head, decisions = lines[0], lines[1:]
            self.assertEqual(("game", record["id"], record["winner_seat"]), (head["type"], head["game"], head["winner"]))
            self.assertEqual(2, len(head["seats"]))
            for seat, player in enumerate(record["players"]):
                mine = [d for d in decisions if d["seat"] == seat]
                hands = [d for d in mine if d["kind"] == "mulligan"]
                self.assertEqual(player["mulligans"], sum(d["forge"]["action"] == "mulligan" for d in hands))
                keep = [d for d in hands if d["forge"]["action"] == "keep"]
                self.assertEqual(1, len(keep))
                self.assertEqual(7, len(keep[0]["state"]["you"]["hand"]))
                self.assertEqual(player["mulligans"], len(keep[0]["forge"]["bottom"]))
                self.assertEqual(player["turns"], sum(d["kind"] == "main" for d in mine))
            for d in decisions:
                self.assertNotIn("hand", d["state"]["opponent"] or {})  # never the opponent's hand
                self.assertNotIn("unresolved", d["forge"])
                self.assertNotIn(d["kind"], ("counter", "endstep", "upkeep", "draw"))  # no counterspells or instants
                if d["kind"] == "main2":
                    self.assertTrue(d["context"]["castable"])
                    self.assertLessEqual(set(d["forge"]["cast"]), {"Grizzly Bears", "Raging Goblin"})
            self.assertTrue(any(d["kind"] == "attack" and d["forge"]["attackers"] for d in decisions))

    def test_fixed_monte_carlo_replays_the_same_games(self):
        # Monte Carlo "fixed" counts rollouts instead of reading the clock, so unlike "on" and "max"
        # it must replay from the seed whatever the number of workers.
        fixed = dict(monte_carlo="fixed", force_monte_carlo=True, fixed_timeout=600)
        first = self._play("fixed-a", games=4, seed=9, workers=2, **fixed)
        if any("Forge patch 0020" in (r.get("error") or "") for r in first):
            self.skipTest("this Forge build lacks mtgsim's patch 0020; run `python3 -m mtgsim setup --build`")
        second = self._play("fixed-b", games=4, seed=9, workers=1, **fixed)
        for record in first + second:
            self.assertEqual("ok", record["status"], record.get("error"))
            self.assertEqual(0, record["mc"]["failures"])
        self.assertGreater(sum(r["mc"]["rollouts"] for r in first), 0, "the search must really have run")
        self.assertEqual(
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"], r["mc"]) for r in first],
            [(r["id"], r["winner_seat"], r["first_seat"], r["turns"], r["players"], r["mc"]) for r in second],
        )

    def test_best_of_three_matches_replay_and_seat_the_loser_first(self):
        # A sideboard, so the driver's sideboarding (Forge's SideboardAdvisor) has something to consider.
        def entrants():
            bears = deck_from_text("20 Forest\n40 Grizzly Bears\n\nSideboard\n15 Llanowar Elves\n", "bears", self.db)
            giants = deck_from_text("20 Mountain\n40 Raging Goblin\n", "giants", self.db)
            self.assertEqual([], bears.errors + giants.errors)
            return [Entrant("bears", bears), Entrant("giants", giants)]

        def play(name, workers, match_format="bo3"):
            es = entrants()
            records = experiment.execute(
                self.install, self.tmp / name, es, [(es[0], es[1])],
                RunOptions(games=3, seed=9, workers=workers, timeout=120, match_format=match_format), quiet=True)
            return sorted(records, key=lambda r: r["id"])

        first, second = play("bo3-a", 2), play("bo3-b", 1)
        keys = ("id", "seats", "winner_seat", "first_seat", "turns", "players", "sideboard")
        self.assertEqual([[r.get(k) for k in keys] for r in first], [[r.get(k) for k in keys] for r in second])
        by_id = {r["id"]: r for r in first}
        later = [r for r in first if r.get("match_game")]
        self.assertTrue(later, "every match has a game 2")
        for r in first:
            self.assertEqual("ok", r["status"], r.get("error"))
        for r in later:
            prev_id = r["id"].rsplit("|", 1)[0] if r["match_game"] == 2 else r["id"][:-1] + "2"
            prev = by_id[prev_id]
            self.assertEqual(0, r["first_seat"])
            self.assertEqual(prev["seats"][1 - prev["winner_seat"]], r["seats"][0], "the loser starts")
            self.assertEqual(2, len(r["sideboard"]))
            self.assertEqual([60, 60], [p["mainCount"] for p in r["players"]])
        game1 = {r["id"]: r for r in play("bo3-bo1", 2, "bo1")}
        for i in range(3):
            g = by_id[f"bears|giants|{i}"]
            self.assertEqual((g["seed"], g["seats"], g["winner_seat"], g["turns"], g["players"]),
                             tuple(game1[g["id"]][k] for k in ("seed", "seats", "winner_seat", "turns", "players")),
                             "game 1 of a match is the best-of-one game")

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
