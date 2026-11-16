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
from mtgsim.runner import DEFAULT_TIMEOUT, FIXED_TIMEOUT, Job
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

    def test_saved_game_logs_get_absolute_paths(self):
        # the JVMs run in Forge's folder, so a relative --out must not leak into the log path
        a, b = _entrants()
        a.dck_path, b.dck_path = "/tmp/a.dck", "/tmp/b.dck"
        jobs = experiment.plan_pairing(a, b, RunOptions(games=2, save_logs=True), Path("runs/x"))
        self.assertTrue(all(Path(j.log_path).is_absolute() for j in jobs))
        self.assertTrue(jobs[1].log_path.endswith("runs/x/logs/games/red__green__0001.log".replace("/", os.sep)))

    def test_per_deck_ai_settings_follow_the_deck_to_its_seat(self):
        a, b = _entrants()
        a.dck_path, b.dck_path = "/tmp/a.dck", "/tmp/b.dck"
        a.ai_profile, a.ai_mc = "Cautious", "max"
        jobs = experiment.plan_pairing(a, b, RunOptions(games=2), Path("/tmp/run"))
        self.assertEqual([["Cautious", ""], ["", "Cautious"]], [j.profiles for j in jobs])
        self.assertEqual([["max", ""], ["", "max"]], [j.seat_monte_carlo for j in jobs])
        self.assertIn("seatmc=max\tseatmc=", jobs[0].line())

    def test_command_line_ai_settings_override_per_deck_ones(self):
        a, b = _entrants()
        a.ai_profile, a.ai_mc = "Cautious", "max"
        forced = RunOptions(games=1, ai_profile="Reckless", force_profile=True, monte_carlo="off", force_monte_carlo=True)
        job = experiment.plan_pairing(a, b, forced, Path("/tmp/run"))[0]
        self.assertEqual(["Reckless", "Reckless"], job.profiles)
        self.assertEqual([], job.seat_monte_carlo)
        self.assertNotIn("seatmc", job.line())

    def test_no_per_deck_settings_adds_nothing_to_the_job(self):
        a, b = _entrants()
        job = experiment.plan_pairing(a, b, RunOptions(games=1), Path("/tmp/run"))[0]
        self.assertEqual([], job.profiles)
        self.assertNotIn("seatmc", job.line())

    def test_fixed_monte_carlo_reaches_the_job_line_and_gets_the_long_time_limit(self):
        a, b = _entrants()
        a.dck_path, b.dck_path = "/tmp/a.dck", "/tmp/b.dck"
        whole = experiment.plan_pairing(a, b, RunOptions(games=1, monte_carlo="fixed", force_monte_carlo=True),
                                        Path("/tmp/run"))[0]
        fields = whole.line().split("\t")
        self.assertIn("mc=fixed", fields)
        self.assertIn(f"timeout={FIXED_TIMEOUT}", fields)
        self.assertNotIn("seatmc", whole.line())
        self.assertTrue(whole.uses_fixed_search())

        a.ai_mc = "fixed"  # one deck only, as ``ai_mc`` in gauntlet.json
        jobs = experiment.plan_pairing(a, b, RunOptions(games=2, fixed_timeout=700), Path("/tmp/run"))
        self.assertEqual([["fixed", ""], ["", "fixed"]], [j.seat_monte_carlo for j in jobs])
        self.assertIn("mc=off", jobs[0].line().split("\t"))
        self.assertIn("seatmc=fixed\tseatmc=", jobs[0].line())
        self.assertEqual([700, 700], [j.timeout for j in jobs])

        b.ai_mc = "max"
        forced_off = RunOptions(games=1, monte_carlo="off", force_monte_carlo=True)
        job = experiment.plan_pairing(a, b, forced_off, Path("/tmp/run"))[0]
        self.assertFalse(job.uses_fixed_search(), "--mc off overrides a deck's ai_mc")
        self.assertEqual(DEFAULT_TIMEOUT, job.timeout)
        a.ai_mc = ""
        clocked = experiment.plan_pairing(a, b, RunOptions(games=1), Path("/tmp/run"))[0]
        self.assertEqual(DEFAULT_TIMEOUT, clocked.timeout, "only the counted search gets the long limit")

    def test_job_line_refuses_an_unknown_monte_carlo_setting(self):
        with self.assertRaises(ValueError):
            Job(id="a|b|0", seed=1, decks=["a", "b"], monte_carlo="fast").line()
        with self.assertRaises(ValueError):
            Job(id="a|b|0", seed=1, decks=["a", "b"], seat_monte_carlo=["", "fxied"]).line()
        self.assertIn("seatmc=\tseatmc=fixed", Job(id="a|b|0", seed=1, decks=["a", "b"],
                                                   seat_monte_carlo=["", "fixed"]).line())

    def test_options_record_the_fixed_time_limit_only_for_fixed_runs(self):
        self.assertNotIn("timeout_fixed", RunOptions().describe())
        self.assertEqual(FIXED_TIMEOUT, RunOptions(monte_carlo="fixed").describe()["timeout_fixed"])

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


def _later(game_id):
    """Whether a game id is game 2 or 3 of a match."""
    return game_id.endswith(("|g2", "|g3"))


def _fake_bo3_run_jobs(played, winner_of=lambda job: 0):
    """Like _fake_run_jobs, but ``winner_of(job)`` picks the winning seat (-1: a draw), the engine reports who
    started as the job asked (seat 0 when first=0, else seat 1) and sideboarded games report their swaps."""
    def run_jobs(install, jobs, on_result, **kwargs):
        for job in jobs:
            played.append(job)
            winner = winner_of(job)
            player = {"mainCount": 60, "sideCount": 0, "life": 20, "mulligans": 0, "turns": 5,
                      "lossReason": None, "altWin": None, "opening": {}, "drawn": {}, "played": {}}
            result = {"type": "result", "id": job.id, "status": "ok", "winner": winner,
                      "first": 0 if job.first_seat == 0 else 1, "turns": 10,
                      "endReason": "AllOpponentsLost" if winner >= 0 else "Draw", "ms": 5,
                      "players": [player, dict(player)]}
            if job.sideboard:
                result["sideboard"] = [["Shock>Shock"], []]
            on_result(job, result)
        return {"forgeVersion": "test", "java": "21"}
    return run_jobs


class BestOfThreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-bo3-"))
        self.install = ForgeInstall(root=self.tmp, jar=self.tmp / "forge-gui-desktop-9.9-jar-with-dependencies.jar",
                                    res=self.tmp / "res", workdir=self.tmp)
        self.entrants = _entrants()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _execute(self, games, played, winner_of=lambda job: 0, run="run", **opts):
        options = RunOptions(games=games, **opts)
        with mock.patch.object(experiment, "run_jobs", _fake_bo3_run_jobs(played, winner_of)):
            return experiment.execute(self.install, self.tmp / run, self.entrants,
                                      [(self.entrants[0], self.entrants[1])], options,
                                      meta={"kind": "match"}, quiet=True)

    def test_game_one_of_each_match_is_the_best_of_one_game(self):
        bo1, bo3 = [], []
        self._execute(4, bo1, run="bo1")
        self._execute(4, bo3, run="bo3", match_format="bo3")
        firsts = {j.id: j for j in bo3 if not _later(j.id)}
        def key(job):
            return job.seed, [Path(d).name for d in job.decks], job.first_seat, job.sideboard
        self.assertEqual({j.id: key(j) for j in bo1}, {i: key(j) for i, j in firsts.items()})
        self.assertEqual([j.line().replace("/bo1/", "/") for j in bo1],
                         [firsts[j.id].line().replace("/bo3/", "/") for j in bo1])

    def test_later_games_seat_the_loser_first_and_sideboard(self):
        played = []
        records = self._execute(4, played, match_format="bo3")  # seat 0 always wins: every match goes to game 3
        by_id = {r["id"]: r for r in records}
        self.assertEqual(12, len(records))
        for i in range(4):
            g1, g2, g3 = (by_id[f"red|green|{i}"], by_id[f"red|green|{i}|g2"], by_id[f"red|green|{i}|g3"])
            self.assertNotIn("sideboard", g1)
            self.assertEqual(g1["seats"][1], g2["seats"][0], "the loser of game 1 starts game 2")
            self.assertEqual(g2["seats"][1], g3["seats"][0], "the loser of game 2 starts game 3")
            for g, n in ((g2, 2), (g3, 3)):
                self.assertEqual((n, i, 0), (g["match_game"], g["game"], g["first_seat"]))
                self.assertEqual([["Shock>Shock"], []], g["sideboard"])
        later = [j for j in played if _later(j.id)]
        self.assertTrue(all(j.first_seat == 0 and j.sideboard for j in later))
        self.assertTrue(all("\tfirst=0" in j.line() and j.line().endswith("\tsideboard=1") for j in later))
        self.assertEqual(len(later), len({j.seed for j in later} | {j.seed for j in played if not _later(j.id)}) - 4)

    def test_a_match_won_two_nil_has_no_third_game(self):
        # The deck called red wins every game, whichever seat it has.
        def red_wins(job):
            return 0 if job.decks[0].endswith("red.dck") else 1
        played = []
        records = self._execute(3, played, red_wins, match_format="bo3")
        self.assertEqual(6, len(records))
        self.assertFalse(any(j.id.endswith("|g3") for j in played))

    def test_no_sideboard_keeps_the_main_decks(self):
        played = []
        self._execute(2, played, match_format="bo3", sideboard=False)
        later = [j for j in played if _later(j.id)]
        self.assertTrue(later)
        self.assertTrue(all(j.first_seat == 0 and not j.sideboard for j in later))

    def test_after_a_draw_the_same_player_starts_again(self):
        a, b = self.entrants
        previous = {"seats": ["green", "red"], "status": "ok", "winner_seat": -1, "first_seat": 1}
        job = experiment.plan_match_game(a, b, 0, 2, previous, RunOptions(games=1, match_format="bo3"), self.tmp)
        self.assertEqual("red", job.meta["seats"][0])
        previous = {"seats": ["green", "red"], "status": "timeout", "winner_seat": 0, "first_seat": 0}
        job = experiment.plan_match_game(a, b, 0, 2, previous, RunOptions(games=1, match_format="bo3"), self.tmp)
        self.assertEqual("green", job.meta["seats"][0], "a time-out has no winner, whatever the field says")

    def test_next_games_wait_for_the_previous_one(self):
        a, b = self.entrants
        options = RunOptions(games=2, match_format="bo3")
        g1 = {"seats": ["red", "green"], "status": "ok", "winner_seat": 0, "first_seat": 0}
        jobs = experiment.next_match_games(a, b, {"red|green|0": g1}, options, self.tmp, 2)
        self.assertEqual(["red|green|0|g2"], [j.id for j in jobs], "match 1 has no game 1 yet")
        self.assertEqual([], experiment.next_match_games(a, b, {"red|green|0": g1}, options, self.tmp, 3))
        g2 = dict(g1, seats=["green", "red"], winner_seat=1)
        self.assertEqual([], experiment.next_match_games(a, b, {"red|green|0": g1, "red|green|0|g2": g2},
                                                         options, self.tmp, 3), "red won 2-0")

    def test_resume_replans_the_later_games_from_the_record(self):
        played = []
        self._execute(3, played, match_format="bo3")
        path = self.tmp / "run" / "games.jsonl"
        lines = path.read_text().strip().splitlines()
        path.write_text("\n".join(l for l in lines if not _later(json.loads(l)["id"])) + "\n")
        again = []
        records = self._execute(3, again, match_format="bo3")
        self.assertEqual(sorted(j.id for j in played if _later(j.id)), sorted(j.id for j in again))
        self.assertEqual(9, len(records))
        third = []
        self._execute(3, third, match_format="bo3")
        self.assertEqual([], third, "a finished run plays nothing more")

    def test_resume_refuses_another_format(self):
        self._execute(2, [], run="bo1")
        with self.assertRaises(RunError):
            self._execute(2, [], run="bo1", match_format="bo3")
        self._execute(2, [], run="bo1", sideboard=False)  # best-of-one games never sideboard: same format
        self._execute(2, [], run="bo3", match_format="bo3")
        with self.assertRaises(RunError):
            self._execute(2, [], run="bo3", match_format="bo3", sideboard=False)
        with self.assertRaises(RunError):
            self._execute(2, [], run="bo3")

    def test_job_line_fields_for_later_games(self):
        job = Job(id="a|b|0|g2", seed=7, decks=["/x/a.dck", "/x/b.dck"], first_seat=0, sideboard=True)
        self.assertEqual(["first=0", "sideboard=1"], job.line().split("\t")[-2:])
        plan = Job(id="p", seed=7, decks=["a", "b"], sideboard=True, plan_only=True)
        self.assertEqual("planonly=1", plan.line().split("\t")[-1])
        self.assertNotIn("first=", Job(id="x", seed=1, decks=["a", "b"]).line())
        with self.assertRaises(ValueError):
            Job(id="x", seed=1, decks=["a", "b"], plan_only=True).line()
        with self.assertRaises(ValueError):
            Job(id="x", seed=1, decks=["a", "b"], first_seat=1).line()


if __name__ == "__main__":
    unittest.main()
