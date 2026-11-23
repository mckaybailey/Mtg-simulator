import io
import json
import random
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mtgsim import calibration, cli, report

EVIL = 'Evil <script>alert(1)</script> "deck"'


def _pairing(a, b, wins, decided):
    return {"a": a, "b": b, "wins": wins, "decided": decided}


# four decks with a clear order: strong > mid > soft > weak
RATES = {("mid", "soft"): 0.6, ("mid", "strong"): 0.3, ("mid", "weak"): 0.7,
         ("soft", "strong"): 0.25, ("soft", "weak"): 0.55, ("strong", "weak"): 0.8}
DECIDED = 40


def _entrants(real=None, weight=25.0):
    real = real or {"strong": 60.0, "mid": 52.0, "soft": 46.0, "weak": 40.0}
    names = {"strong": "Strong", "mid": "Mid", "soft": "Soft", "weak": EVIL}
    return {k: {"key": k, "name": names[k], "real_win_rate": real[k], "weight": weight, "main": {"Shock": 60},
                "main_count": 60} for k in names}


def _pairings(scale=DECIDED):
    return [_pairing(a, b, round(p * scale), scale) for (a, b), p in sorted(RATES.items())]


class PartsTest(unittest.TestCase):
    def test_bo3_conversion(self):
        self.assertAlmostEqual(0.5, calibration.bo3(0.5))
        self.assertAlmostEqual(0.648, calibration.bo3(0.6))
        self.assertAlmostEqual(1 - calibration.bo3(0.6), calibration.bo3(0.4))

    def test_parse_events(self):
        events = calibration.parse_events(calibration.FRACTURE_2026_EVENTS)
        self.assertEqual([176, 775, 865], [e["n"] for e in events])
        self.assertEqual((7, 3), (events[0]["win_cap"], events[0]["loss_cap"]))
        self.assertEqual((9, 3), events[1]["cut"])
        self.assertIsNone(events[1]["loss_cap"])
        for bad in ("600", "x:12", "600:12:q4", "1:3", "600:0"):
            with self.assertRaises(ValueError, msg=bad):
                calibration.parse_events(bad)

    def test_metrics(self):
        m = calibration.metrics([60.0, 50.0, 40.0], [55.0, 45.0, 52.0])
        self.assertAlmostEqual(8.165, m["sd"], places=3)
        self.assertAlmostEqual(22 / 3, m["mean_gap"])
        self.assertEqual(1, m["sign_errors"])  # 40 against a real 52; 50 is neither side
        self.assertAlmostEqual(0.5, m["spearman"])

    def test_pairing_avoids_rematches_and_gives_one_bye(self):
        rng = random.Random(3)
        players = [[i, 0, 0, 0] for i in range(5)]
        pairs, bye = calibration.pair(players, rng, {(0, 1), (1, 0)})
        self.assertEqual(2, len(pairs))
        self.assertIsNotNone(bye)
        ids = sorted([a[0] for a, b in pairs] + [b[0] for a, b in pairs] + [bye[0]])
        self.assertEqual(list(range(5)), ids)

    def test_mirrors_are_left_out_of_swiss_rates(self):
        # one archetype only: every match is a mirror, so it has no rate
        field = calibration.Field(["solo"], {"solo": 100.0}, {}, include_other=False)
        rates = calibration.swiss(field, calibration.parse_events("16:4"), 3, random.Random(1))
        self.assertNotEqual(rates[0], rates[0])  # nan

    def test_even_field_stays_even(self):
        keys = ["a", "b", "c"]
        cells = {("a", "b"): (50, 100), ("a", "c"): (50, 100), ("b", "c"): (50, 100)}
        f = calibration.Field(keys, {k: 30.0 for k in keys}, cells)
        rates = calibration.swiss(f, calibration.parse_events("200:8"), 20, random.Random(2))
        for r in rates:
            self.assertAlmostEqual(0.5, r, delta=0.03)


class CompareTest(unittest.TestCase):
    def test_compare_shape_order_and_reproducibility(self):
        cal = calibration.compare(_entrants(), _pairings(), events="64:6", seasons=30, reps=5, boot_seasons=3)
        again = calibration.compare(_entrants(), _pairings(), events="64:6", seasons=30, reps=5, boot_seasons=3)
        self.assertEqual(cal, again, "seeded: the same inputs give the same numbers")
        self.assertEqual(["mid", "soft", "strong", "weak"], [d["key"] for d in cal["decks"]])
        by = {d["key"]: d for d in cal["decks"]}
        for view in calibration.VIEWS:
            self.assertGreater(by["strong"][view], by["mid"][view], view)
            self.assertGreater(by["soft"][view], by["weak"][view], view)
            self.assertEqual(1.0, round(cal["metrics"][view]["spearman"], 6), view)
            self.assertEqual(2, len(cal["noise"][view]["sd"]))
        # equal-weighted games are the plain average of the pairing rates
        self.assertAlmostEqual(100 * (0.8 + 0.7 + 0.75) / 3, by["strong"]["games"])
        # best-of-three widens the spread; with no "other" share, matches are bo3 of games
        self.assertGreater(cal["metrics"]["matches"]["sd"], cal["metrics"]["weighted"]["sd"])
        self.assertEqual(0.0, cal["other_share"])
        self.assertIn("sd", cal["pairing_effect"])
        self.assertAlmostEqual(cal["metrics"]["swiss"]["sd"] - cal["metrics"]["matches"]["sd"],
                               cal["pairing_effect"]["sd"])

    def test_decks_without_real_rate_or_share_are_left_out(self):
        ents = _entrants()
        ents["weak"]["real_win_rate"] = None
        cal = calibration.compare(ents, _pairings(), events="32:5", seasons=5, reps=0)
        self.assertEqual(["mid", "soft", "strong"], [d["key"] for d in cal["decks"]])
        self.assertEqual({}, cal["noise"])
        ents["soft"]["weight"] = None
        self.assertIsNone(calibration.compare(ents, _pairings(), events="32:5", seasons=5, reps=0))

    def test_rest_of_field_is_other(self):
        cal = calibration.compare(_entrants(weight=20.0), _pairings(), events="32:5", seasons=5, reps=0)
        self.assertAlmostEqual(20.0, cal["other_share"])

    def test_best_of_three_run_uses_its_matches(self):
        game1 = _pairings()
        matches = [_pairing(p["a"], p["b"], p["decided"] // 2, p["decided"]) for p in game1]  # every match even
        cal = calibration.compare(_entrants(), matches, game1, events="32:5", seasons=5, reps=2, boot_seasons=2)
        self.assertEqual("bo3 matches played", cal["match_rates"])
        for d in cal["decks"]:
            self.assertAlmostEqual(50.0, d["matches"])
        by = {d["key"]: d for d in cal["decks"]}
        self.assertGreater(by["strong"]["games"], 70)

    def test_format_text(self):
        cal = calibration.compare(_entrants(), _pairings(), events="32:5", seasons=5, reps=3, boot_seasons=2)
        text = calibration.format_text(cal)
        self.assertIn("swiss", text)
        self.assertIn("Swiss minus round-robin matches", text)
        self.assertIn("Strong", text)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        names = {"strong": "Strong", "mid": "Mid", "soft": "Soft", "weak": "Weak"}
        self.table = self.root / "table.json"
        self.table.write_text(json.dumps({"entrants": {k: {"name": n} for k, n in names.items()},
                                          "pairings": _pairings()}), encoding="utf-8")
        self.gauntlet = self.root / "gauntlet.json"
        real = {"Strong": 60.0, "Mid": 52.0, "Soft": 46.0, "Weak": 40.0}
        self.gauntlet.write_text(json.dumps({
            "real_events": {"structure": "48:5", "description": "test"},
            "decks": [{"file": f"{n.lower()}.txt", "name": n, "real_win_rate": r, "meta_share": 20.0}
                      for n, r in real.items()]}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["calibrate", *argv])
        return code, out.getvalue()

    def test_table_with_gauntlet(self):
        out_json = self.root / "cal.json"
        code, out = self._run(str(self.table), "--gauntlet", str(self.gauntlet), "--reps", "2", "--seasons", "5",
                              "--json", str(out_json))
        self.assertEqual(0, code)
        self.assertIn("48:5", out, "the gauntlet's real_events is the default structure")
        cal = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual(4, len(cal["decks"]))
        self.assertAlmostEqual(20.0, cal["other_share"])

    def test_run_directory_is_updated(self):
        run = self.root / "run"
        run.mkdir()
        summary = json.loads(self.table.read_text(encoding="utf-8"))
        summary.update({"kind": "matrix", "title": "t", "matrix": {"order": [], "ranking": [], "grid": {}}})
        for e in summary["entrants"].values():
            e.update({"main": {"Shock": 60}, "main_count": 60})
        (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        code, out = self._run(str(run), "--gauntlet", str(self.gauntlet), "--reps", "0", "--seasons", "3",
                              "--events", "24:4")
        self.assertEqual(0, code)
        saved = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual("24:4", saved["calibration"]["events"])
        self.assertIn("Against real win rates", (run / "report.html").read_text(encoding="utf-8"))

    def test_too_few_decks(self):
        data = json.loads(self.gauntlet.read_text(encoding="utf-8"))
        for d in data["decks"][1:]:
            d.pop("real_win_rate")
        self.gauntlet.write_text(json.dumps(data), encoding="utf-8")
        code, _ = self._run(str(self.table), "--gauntlet", str(self.gauntlet), "--reps", "0")
        self.assertNotEqual(0, code)


class ReportTest(unittest.TestCase):
    def test_section_is_rendered_and_escaped(self):
        ents = _entrants()
        cal = calibration.compare(ents, _pairings(), events="32:5", seasons=5, reps=2, boot_seasons=2)
        summary = {"kind": "matrix", "title": "t", "entrants": ents, "caveat": "",
                   "matrix": {"order": [], "ranking": [], "grid": {}}, "calibration": cal}
        html = report.render(summary)
        self.assertIn("Against real win rates", html)
        self.assertIn("Simulated Swiss events", html)
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("Against real win rates", report.render(dict(summary, calibration=None)))


if __name__ == "__main__":
    unittest.main()
