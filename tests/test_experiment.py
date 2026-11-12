import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import experiment
from mtgsim.decks import deck_from_text
from mtgsim.experiment import Entrant, RunError, RunOptions
from mtgsim.forge import ForgeInstall
from mtgsim.runner import Job
from tests.helpers import make_db


def _entrants():
    db = make_db()
    red = deck_from_text("40 Mountain\n20 Shock\n", "Red", db)
    green = deck_from_text("40 Forest\n20 Grizzly Bears\n", "Green", db)
    return [Entrant("red", red), Entrant("green", green)]


def _fake_run_jobs(played, main_count=60):
    """Stands in for the Forge worker pool: seat 0 always wins on turn 5."""
    def run_jobs(install, jobs, on_result, **kwargs):
        for job in jobs:
            played.append(job.id)
            player = {"mainCount": main_count, "sideCount": 0, "life": 20, "mulligans": 0, "turns": 5,
                      "lossReason": None, "altWin": None, "opening": {}, "drawn": {}, "played": {}}
            on_result(job, {"type": "result", "id": job.id, "status": "ok", "winner": 0, "first": 0,
                            "turns": 10, "endReason": "AllOpponentsLost", "ms": 5, "players": [player, dict(player)]})
        return {"forgeVersion": "test", "java": "21"}
    return run_jobs


class SeedAndPlanTest(unittest.TestCase):
    def test_seed_is_stable_symmetric_and_sensitive(self):
        red, green = (e.deck for e in _entrants())
        seed = experiment.game_seed(1, red, green, 0)
        self.assertEqual(seed, experiment.game_seed(1, red, green, 0))
        self.assertEqual(seed, experiment.game_seed(1, green, red, 0), "deck order must not matter")
        self.assertNotEqual(seed, experiment.game_seed(1, red, green, 1))
        self.assertNotEqual(seed, experiment.game_seed(2, red, green, 0))
        changed = deck_from_text("41 Mountain\n19 Shock\n", "Red", make_db())
        self.assertNotEqual(seed, experiment.game_seed(1, changed, green, 0))
        self.assertTrue(0 <= seed < 2 ** 63, "must fit in a Java long")

    def test_renaming_a_deck_keeps_its_seeds(self):
        red, green = (e.deck for e in _entrants())
        renamed = deck_from_text("40 Mountain\n20 Shock\n", "Another name", make_db())
        self.assertEqual(experiment.game_seed(1, red, green, 3), experiment.game_seed(1, renamed, green, 3))

    def test_pairing_alternates_seats(self):
        a, b = _entrants()
        a.dck_path, b.dck_path = "/tmp/a.dck", "/tmp/b.dck"
        jobs = experiment.plan_pairing(a, b, RunOptions(games=4, timeout=99), Path("/tmp/run"))
        self.assertEqual(["red|green|0", "red|green|1", "red|green|2", "red|green|3"], [j.id for j in jobs])
        self.assertEqual([["/tmp/a.dck", "/tmp/b.dck"], ["/tmp/b.dck", "/tmp/a.dck"]] * 2, [j.decks for j in jobs])
        self.assertEqual([["red", "green"], ["green", "red"]] * 2, [j.meta["seats"] for j in jobs])
        self.assertEqual(4, len({j.seed for j in jobs}))
        self.assertTrue(all(j.timeout == 99 and j.log_path == "" for j in jobs))

    def test_unique_keys(self):
        self.assertEqual(["mono-red", "mono-red-2", "deck", "a-b-s-c"],
                         experiment.unique_keys(["Mono Red", "mono-red", "???", "A // B's C"]))
        keys = experiment.unique_keys(["X", "X-2", "X", "x 2"])
        self.assertEqual(4, len(set(keys)), keys)

    def test_job_line_format_and_rejection_of_control_characters(self):
        job = Job(id="a|b|0", seed=7, decks=["/x/a.dck", "/x/b.dck"], timeout=30, profiles=["Default", "Default"])
        fields = job.line().split("\t")
        self.assertEqual(["id=a|b|0", "seed=7", "timeout=30", "format=Constructed", "mc=off", "log="], fields[:6])
        self.assertEqual(["deck=/x/a.dck", "deck=/x/b.dck", "profile=Default", "profile=Default"], fields[6:])
        with self.assertRaises(ValueError):
            Job(id="bad\tid", seed=1, decks=["a", "b"]).line()
        with self.assertRaises(ValueError):
            Job(id="x", seed=1, decks=["a\nb", "c"]).line()


class ExecuteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-exp-"))
        self.install = ForgeInstall(root=self.tmp, jar=self.tmp / "forge-gui-desktop-9.9-jar-with-dependencies.jar",
                                    res=self.tmp / "res", workdir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _execute(self, games, played, main_count=60):
        entrants = _entrants()
        with mock.patch.object(experiment, "run_jobs", _fake_run_jobs(played, main_count)):
            return experiment.execute(self.install, self.tmp / "run", entrants, [(entrants[0], entrants[1])],
                                      RunOptions(games=games), meta={"kind": "match"}, quiet=True)

    def test_records_are_stored_with_seats_and_decks_written(self):
        played = []
        records = self._execute(4, played)
        self.assertEqual(4, len(records))
        first = sorted(records, key=lambda r: r["game"])[1]
        self.assertEqual((["green", "red"], 0, "ok"), (first["seats"], first["winner_seat"], first["status"]))
        self.assertTrue((self.tmp / "run" / "decks" / "red.dck").read_text().startswith("[metadata]\nName=Red"))
        info = json.loads((self.tmp / "run" / "run.json").read_text())
        self.assertEqual("match", info["kind"])
        self.assertEqual("test", info["forge"]["forgeVersion"])
        self.assertEqual(["red", "green"], [e["key"] for e in info["entrants"]])

    def test_resume_plays_only_the_missing_games(self):
        played = []
        self._execute(3, played)
        self.assertEqual(3, len(played))
        records = self._execute(5, played)
        self.assertEqual(5, len(records))
        self.assertEqual(5, len(played), "the three recorded games must not be replayed")
        self.assertEqual(5, len((self.tmp / "run" / "games.jsonl").read_text().strip().splitlines()))

    def test_failed_games_are_retried_on_resume(self):
        self._execute(2, [])
        path = self.tmp / "run" / "games.jsonl"
        lines = path.read_text().strip().splitlines()
        crashed = json.loads(lines[1])
        crashed["status"] = "crash"
        path.write_text(lines[0] + "\n" + json.dumps(crashed) + "\n")
        played = []
        records = self._execute(2, played)
        self.assertEqual([crashed["id"]], played)
        self.assertEqual(["ok", "ok"], [r["status"] for r in records])

    def test_a_deck_the_engine_did_not_fully_load_stops_the_run(self):
        with self.assertRaises(RunError) as ctx:
            self._execute(2, [], main_count=56)
        self.assertIn("56", str(ctx.exception))

    def test_read_games_tolerates_a_truncated_line_and_keeps_the_last_record(self):
        run = self.tmp / "run2"
        run.mkdir()
        (run / "games.jsonl").write_text(
            '{"id":"a","status":"crash"}\n{"id":"b","status":"ok"}\n{"id":"a","status":"ok"}\n{"id":"c","sta')
        games = {g["id"]: g["status"] for g in experiment.read_games(run)}
        self.assertEqual({"a": "ok", "b": "ok"}, games)
        self.assertEqual([], experiment.read_games(self.tmp / "missing"))


if __name__ == "__main__":
    unittest.main()
