"""Tests for AI profile handling (ai_profiles.py) and the profile-tuning search (tune.py).

The engine is replaced by a fake ``runner.run_jobs`` whose outcomes depend on the seed and on the
profiles each seat plays, so caching, reuse, selection and hold-out logic can be checked without Java.
"""

import contextlib
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import ai_profiles, experiment, forge, runner, tune
from mtgsim.decks import deck_from_text
from mtgsim.experiment import Entrant, RunError, RunOptions
from mtgsim.forge import ForgeError, ForgeInstall
from tests.helpers import make_db

DEFAULT_AI = """# The amount of cards at which to stop considering mulligan
MULLIGAN_THRESHOLD=4
# aggro
PLAY_AGGRO=false
CHANCE_TO_ATTACK_INTO_TRADE=0
"""
CAUTIOUS_AI = "MULLIGAN_THRESHOLD=4\nPLAY_AGGRO=false\nCHANCE_TO_ATTACK_INTO_TRADE=0\nAI_IN_DANGER_THRESHOLD=6\n"


def fake_install(root: Path) -> ForgeInstall:
    (root / "res" / "ai").mkdir(parents=True, exist_ok=True)
    (root / "res" / "ai" / "Default.ai").write_text(DEFAULT_AI)
    (root / "res" / "ai" / "Cautious.ai").write_text(CAUTIOUS_AI)
    return ForgeInstall(root=root, jar=root / "forge-gui-desktop-9.9-jar-with-dependencies.jar",
                        res=root / "res", workdir=root)


class TempHome(unittest.TestCase):
    """A temporary MTGSIM_HOME and Forge folder, with no shipped profiles unless a test adds them."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-tune-"))
        self.install = fake_install(self.tmp / "forge")
        self.shipped = self.tmp / "shipped"
        self.shipped.mkdir()
        patches = [mock.patch.dict(os.environ, {"MTGSIM_HOME": str(self.tmp / "home")}),
                   mock.patch.object(ai_profiles, "SHIPPED_DIR", self.shipped)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ============================================================== profile files


class ProfileFormatTest(unittest.TestCase):
    def test_parse_follows_forges_reading_rules(self):
        text = "# comment\n\nA=1\nB=\nC==3\nD=4=\n #not a comment=x\nA=2\r\nE"
        self.assertEqual({"A": "2", "B": "", "D": "4", " #not a comment": "x"}, ai_profiles.parse(text))

    def test_format_value(self):
        self.assertEqual(["true", "false", "5", "5", "auto"],
                         [ai_profiles.format_value(v) for v in (True, False, 5, 5.0, "auto")])
        for bad in ("a=b", " 5", "x\ny", 2.5, None, [1]):
            with self.assertRaises(ai_profiles.ProfileError, msg=repr(bad)):
                ai_profiles.format_value(bad)

    def test_check_key_and_name(self):
        self.assertEqual("PLAY_AGGRO", ai_profiles.check_key("PLAY_AGGRO", {"PLAY_AGGRO"}))
        for bad in ("play_aggro", "X Y", ""):
            with self.assertRaises(ai_profiles.ProfileError):
                ai_profiles.check_key(bad)
        with self.assertRaises(ai_profiles.ProfileError):
            ai_profiles.check_key("NOT_A_KEY", {"PLAY_AGGRO"})
        ai_profiles.check_name("tune-reactive-0a1b2c3d4e")
        for bad in ("a/b", "-x", "a b", "x" * 65):
            with self.assertRaises(ai_profiles.ProfileError):
                ai_profiles.check_name(bad)

    def test_overrides_replace_in_place_and_add_missing_keys(self):
        base = "# head\nA=1\nB=2\n# note\nA=9\n"
        text = ai_profiles.apply_overrides(base, {"A": "5", "Z": "true"}, header=["made by a test"])
        self.assertTrue(text.startswith("# made by a test\n# head\nA=5\nB=2\n# note\n"))
        self.assertEqual({"A": "5", "B": "2", "Z": "true"}, ai_profiles.parse(text))
        self.assertEqual(1, text.count("A="), "a later duplicate of an overridden key would win in Forge")
        self.assertEqual(ai_profiles.parse(base), ai_profiles.parse(ai_profiles.apply_overrides(base, {})))

    def test_settings_hash_ignores_comments_order_and_spelled_out_defaults(self):
        a = "# x\nA=1\nB=2\n"
        b = "B=2\n# other comment\nA=1\n"
        self.assertEqual(ai_profiles.settings_hash(a), ai_profiles.settings_hash(b))
        self.assertNotEqual(ai_profiles.settings_hash(a), ai_profiles.settings_hash("A=1\nB=3\n"))
        defaults = {"A": "0", "B": "0", "C": "7"}
        self.assertEqual(ai_profiles.settings_hash(a, defaults), ai_profiles.settings_hash(a + "C=7\n", defaults))
        self.assertEqual(ai_profiles.settings_hash(a, defaults), ai_profiles.settings_hash(a + "C=\n", defaults),
                         "Forge treats an empty value as unset")
        self.assertNotEqual(ai_profiles.settings_hash(a, defaults), ai_profiles.settings_hash(a + "C=8\n", defaults))

    def test_parse_aiprops_reads_constants_and_defaults(self):
        source = """package forge.ai;
public enum AiProps {
    // a comment with FAKE ("x")
    MULLIGAN_THRESHOLD ("5"),
    /** doc */
    PLAY_AGGRO("false"),
    ALWAYS_COUNTER_SPELLS_FROM_NAMED_CARDS (""),
    LAST_ONE("true");
    private final String strDefaultVal;
    AiProps(final String s0) { this.strDefaultVal = s0; }
}"""
        self.assertEqual({"MULLIGAN_THRESHOLD": "5", "PLAY_AGGRO": "false",
                          "ALWAYS_COUNTER_SPELLS_FROM_NAMED_CARDS": "", "LAST_ONE": "true"},
                         ai_profiles.parse_aiprops(source))


class ProfileLibraryTest(TempHome):
    def test_library_lists_forge_shipped_and_user_profiles(self):
        (self.shipped / "Patient.json").write_text(json.dumps({"base": "Default", "overrides": {"PLAY_AGGRO": True}}))
        user = self.tmp / "home" / "profiles"
        user.mkdir(parents=True)
        (user / "Mine.ai").write_text("MULLIGAN_THRESHOLD=6\n")
        lib = ai_profiles.library(self.install)
        self.assertEqual(["Cautious", "Default", "Mine", "Patient"], sorted(lib))
        self.assertEqual(("forge", "mtgsim", "user"), (lib["Default"].kind, lib["Patient"].kind, lib["Mine"].kind))
        patient = ai_profiles.parse(ai_profiles.text_of(self.install, "Patient"))
        self.assertEqual({"MULLIGAN_THRESHOLD": "4", "PLAY_AGGRO": "true", "CHANCE_TO_ATTACK_INTO_TRADE": "0"}, patient,
                         "a JSON profile is a full copy of its base with the overrides applied")

    def test_a_profile_may_not_redefine_a_forge_profile(self):
        (self.shipped / "Default.json").write_text(json.dumps({"base": "Cautious", "overrides": {}}))
        with self.assertRaises(ai_profiles.ProfileError):
            ai_profiles.library(self.install)

    def test_unknown_base_and_bad_json_are_reported(self):
        (self.shipped / "Broken.json").write_text("{not json")
        with self.assertRaises(ai_profiles.ProfileError):
            ai_profiles.text_of(self.install, "Broken")
        (self.shipped / "Broken.json").write_text(json.dumps({"base": "Nope", "overrides": {}}))
        with self.assertRaises(ai_profiles.ProfileError):
            ai_profiles.text_of(self.install, "Broken")

    def test_prepare_dir_writes_everything_and_removes_stale_profiles(self):
        dest = self.tmp / "run" / "ai"
        dest.mkdir(parents=True)
        (dest / "Leftover.ai").write_text("A=1\n")
        extra = {"tune-x": ai_profiles.build(self.install, "Default", {"MULLIGAN_THRESHOLD": 8})}
        hashes = ai_profiles.prepare_dir(self.install, dest, extra)
        self.assertEqual(["Cautious.ai", "Default.ai", "tune-x.ai"], sorted(p.name for p in dest.iterdir()))
        self.assertEqual(DEFAULT_AI, (dest / "Default.ai").read_text(), "Forge's profiles are copied unchanged")
        self.assertEqual("8", ai_profiles.parse((dest / "tune-x.ai").read_text())["MULLIGAN_THRESHOLD"])
        self.assertEqual(hashes["tune-x"], ai_profiles.settings_hash(extra["tune-x"]))
        with self.assertRaises(ai_profiles.ProfileError):
            ai_profiles.prepare_dir(self.install, dest, {"Default": "PLAY_AGGRO=true\n"})
        self.assertEqual(DEFAULT_AI, (self.install.res / "ai" / "Default.ai").read_text(), "Forge's folder is untouched")

    def test_known_settings_prefers_the_aiprops_source(self):
        keys, exact = ai_profiles.known_settings(self.install)
        self.assertFalse(exact)
        self.assertIn("AI_IN_DANGER_THRESHOLD", keys)
        src = self.install.root / ai_profiles.AIPROPS_SOURCE
        src.parent.mkdir(parents=True)
        src.write_text('public enum AiProps {\n    MULLIGAN_THRESHOLD ("5"),\n    FLAT_MC_MULLIGAN("true");\n}')
        self.assertEqual(({"MULLIGAN_THRESHOLD": "5", "FLAT_MC_MULLIGAN": "true"}, True),
                         ai_profiles.known_settings(self.install))
        with self.assertRaises(ai_profiles.ProfileError):
            ai_profiles.build(self.install, "Default", {"NOT_A_SETTING": 1})


class ProfileFolderReachesTheEngineTest(TempHome):
    """The run's profile folder is prepared by execute and handed to the JVM."""

    def _entrants(self):
        db = make_db()
        return [Entrant("red", deck_from_text("40 Mountain\n20 Shock\n", "Red", db)),
                Entrant("green", deck_from_text("40 Forest\n20 Grizzly Bears\n", "Green", db))]

    def test_execute_prepares_the_folder_and_passes_it_on(self):
        seen = {}

        def run_jobs(install, jobs, on_result, **kwargs):
            seen.update(kwargs)
            seen["profiles"] = [j.profiles for j in jobs]
            return {}

        a, b = self._entrants()
        a.ai_profile = "tune-x"
        extra = {"tune-x": ai_profiles.build(self.install, "Default", {"PLAY_AGGRO": True})}
        with mock.patch.object(experiment, "run_jobs", run_jobs):
            experiment.execute(self.install, self.tmp / "run", [a, b], [(a, b)], RunOptions(games=2),
                               quiet=True, profiles=extra)
        self.assertEqual(self.tmp / "run" / "ai", seen["profile_dir"])
        self.assertTrue((self.tmp / "run" / "ai" / "tune-x.ai").is_file())
        self.assertEqual([["tune-x", ""], ["", "tune-x"]], seen["profiles"])
        info = json.loads((self.tmp / "run" / "run.json").read_text())
        self.assertEqual({"Default", "tune-x"}, set(info["ai_profiles"]))

    def test_execute_refuses_an_unknown_profile(self):
        a, b = self._entrants()
        a.ai_profile = "Nonexistent"
        with mock.patch.object(experiment, "run_jobs", lambda *x, **k: {}):
            with self.assertRaises(RunError):
                experiment.execute(self.install, self.tmp / "run", [a, b], [(a, b)], RunOptions(games=1), quiet=True)

    def test_java_command_carries_the_profile_folder(self):
        with mock.patch.object(forge, "java_path", lambda: "java"):
            cmd = forge.java_command(self.install, Path("/classes"), profile_dir=self.tmp / "run" / "ai")
            plain = forge.java_command(self.install, Path("/classes"))
        prop = f"-Dmtgsim.aiProfileDir={(self.tmp / 'run' / 'ai').resolve()}"
        self.assertIn(prop, cmd)
        self.assertLess(cmd.index(prop), cmd.index("-cp"), "a system property must come before the class path")
        self.assertFalse(any("aiProfileDir" in part for part in plain))

    def test_a_driver_that_ignores_the_folder_is_refused(self):
        # A stand-in for an outdated driver: it announces itself ready but names no profile folder.
        script = "import sys; print('{\"type\":\"ready\"}', flush=True); sys.stdin.readline()"
        worker = runner._Worker([sys.executable, "-c", script], self.tmp, dict(os.environ), self.tmp / "w.log",
                                expect_profiles=True)
        with self.assertRaises(ForgeError):
            worker.start()
        ok = runner._Worker([sys.executable, "-c", script.replace('"ready"', '"ready","aiProfileDir":"/x"')],
                            self.tmp, dict(os.environ), self.tmp / "w2.log", expect_profiles=True)
        ok.start()
        self.assertEqual("/x", ok.info["aiProfileDir"])
        ok.stop(kill=True)


# ===================================================================== space


SPACE = {"base": "Default", "change_probability": 0.5, "params": [
    {"key": "MULLIGAN_THRESHOLD", "values": [4, 5, 6]},
    {"keys": ["PLAY_AGGRO", "CHANCE_TO_ATTACK_INTO_TRADE"], "values": [[True, 100], [False, 50]]},
    {"key": "AI_IN_DANGER_THRESHOLD", "values": [6, 8], "groups": ["reactive"]},
]}
BASE = {"MULLIGAN_THRESHOLD": "4", "PLAY_AGGRO": "false", "CHANCE_TO_ATTACK_INTO_TRADE": "0",
        "AI_IN_DANGER_THRESHOLD": "4"}


class SpaceTest(unittest.TestCase):
    def test_parse_and_round_trip(self):
        space = tune.parse_space(SPACE)
        self.assertEqual("Default", space.base)
        self.assertEqual(("PLAY_AGGRO", "CHANCE_TO_ATTACK_INTO_TRADE"), space.params[1].keys)
        self.assertEqual([("true", "100"), ("false", "50")], space.params[1].values)
        self.assertEqual(("reactive",), space.params[2].groups)
        self.assertEqual(space.to_json(), tune.parse_space(space.to_json()).to_json())

    def test_the_shipped_default_space_is_valid(self):
        space = tune.load_space(tune.DEFAULT_SPACE)
        self.assertGreaterEqual(len(space.params), 10)
        self.assertTrue(all(p.why for p in space.params), "every parameter explains why it is there")
        self.assertFalse(any(k.startswith("FLAT_MC_") and k not in ("FLAT_MC_MULLIGAN", "FLAT_MC_DECK_PLAN")
                             for p in space.params for k in p.keys),
                         "Monte Carlo-only settings do nothing with Monte Carlo off")

    def test_invalid_spaces_are_rejected(self):
        bad = [
            {"params": []},
            {"params": [{"key": "A", "keys": ["A"], "values": [1]}]},
            {"params": [{"keys": ["A", "B"], "values": [[1]]}]},
            {"params": [{"key": "lower", "values": [1]}]},
            {"params": [{"key": "A", "values": ["x=y"]}]},
            {"change_probability": 0, "params": [{"key": "A", "values": [1]}]},
            {"params": [{"key": "A", "values": [1]}, {"keys": ["A", "B"], "values": [[2, 3]]}]},
        ]
        for data in bad:
            with self.assertRaises(RunError, msg=json.dumps(data)):
                tune.parse_space(data)
        with self.assertRaises(RunError):
            tune.parse_space({"params": [{"key": "A", "values": [1]}]}, known={"B"})
        tune.parse_space({"params": [{"key": "A", "values": [1], "groups": ["x"]},
                                     {"key": "A", "values": [2], "groups": ["y"]}]})

    def test_sampling_changes_only_applicable_settings_and_never_repeats(self):
        space = tune.parse_space(SPACE)
        rng = random.Random(3)
        taken = []
        for _ in range(6):
            o = tune.sample_overrides(space, "proactive", BASE, rng, taken)
            self.assertTrue(o)
            self.assertNotIn("AI_IN_DANGER_THRESHOLD", o, "that parameter is for the reactive group only")
            self.assertTrue(all(BASE[k] != v for k, v in o.items()), "overrides only hold real changes")
            self.assertNotIn(tune.overrides_id(o), taken)
            taken.append(tune.overrides_id(o))
        self.assertEqual(tune.sample_overrides(space, "reactive", BASE, random.Random(9)),
                         tune.sample_overrides(space, "reactive", BASE, random.Random(9)))
        tiny = tune.parse_space({"params": [{"key": "MULLIGAN_THRESHOLD", "values": [8]}]})
        first = tune.sample_overrides(tiny, "g", BASE, random.Random(1))
        with self.assertRaises(RunError):
            tune.sample_overrides(tiny, "g", BASE, random.Random(1), [tune.overrides_id(first)])

    def test_candidates_are_every_combination_of_group_profiles(self):
        space = tune.parse_space(SPACE)
        profiles, cands = tune.make_candidates(space, ["reactive", "proactive"], ["reactive", "proactive"], 2,
                                               BASE, random.Random(1))
        self.assertEqual(9, len(cands))
        self.assertEqual({"reactive": "Default", "proactive": "Default"}, cands[0]["profiles"])
        self.assertTrue(cands[0]["baseline"] and not any(c["baseline"] for c in cands[1:]))
        self.assertEqual(9, len({tuple(sorted(c["profiles"].items())) for c in cands}))
        self.assertEqual(5, len(profiles))
        only_one, cands1 = tune.make_candidates(space, ["reactive"], ["reactive", "proactive"], 3, BASE, random.Random(1))
        self.assertEqual(4, len(cands1))
        self.assertTrue(all(c["profiles"]["proactive"] == "Default" for c in cands1), "untuned groups keep the base")
        self.assertTrue(all(name.startswith("tune-reactive-") for name in only_one if name != "Default"))


# ===================================================================== metrics


class MetricsTest(unittest.TestCase):
    def test_ranks_share_ties(self):
        self.assertEqual([1.0, 2.5, 2.5, 4.0], tune.ranks([1, 5, 5, 9]))
        self.assertEqual([3.0, 1.0, 2.0], tune.ranks([0.9, 0.1, 0.5]))

    def test_correlations(self):
        self.assertAlmostEqual(1.0, tune.spearman([1, 2, 3, 4], [10, 20, 30, 400]))
        self.assertAlmostEqual(-1.0, tune.spearman([1, 2, 3, 4], [4, 3, 2, 1]))
        self.assertAlmostEqual(0.8, tune.spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]))
        self.assertLess(tune.pearson([1, 2, 3, 4], [10, 20, 30, 400]), 1.0)
        self.assertIsNone(tune.spearman([1, 2], [1, 2]))
        self.assertIsNone(tune.pearson([1, 1, 1], [1, 2, 3]))

    def test_compare_uses_decks_with_both_numbers(self):
        out = tune.compare({"a": 0.6, "b": 0.5, "c": 0.4, "d": None}, {"a": 0.5, "b": 0.5, "c": 0.3, "d": 0.9},
                           ["a", "b", "c", "d"])
        self.assertEqual(3, out["n"])
        self.assertAlmostEqual((0.1 + 0 + 0.1) / 3, out["mae"])

    def test_spearman_interval_and_data_needed(self):
        lo, hi = tune.spearman_interval(0.24, 11)
        self.assertAlmostEqual(-0.44, lo, places=2)
        self.assertAlmostEqual(0.74, hi, places=2)
        self.assertIsNone(tune.spearman_interval(0.5, 3))
        n02, n01 = tune.points_needed(0.5, 0.2), tune.points_needed(0.5, 0.1)
        self.assertLess(n02, n01)
        lo, hi = tune.spearman_interval(0.5, n01)
        self.assertLessEqual((hi - lo) / 2, 0.1)
        lo, hi = tune.spearman_interval(0.5, n01 - 1)
        self.assertGreater((hi - lo) / 2, 0.1)
        self.assertEqual(97, tune.matches_for_margin(0.10))
        self.assertEqual(385, tune.matches_for_margin(0.05))
        statement = tune.data_needed(9, 0.6, 11, 0)
        self.assertEqual(9, statement["train_decks"])
        self.assertTrue(any("95% interval" in line for line in statement["text"]))
        self.assertTrue(any("55 data points" in line for line in statement["text"]))

    def test_binomial_draws(self):
        rng = random.Random(1)
        draws = tune.binomial_draws(30, 0.7, 4000, rng)
        self.assertTrue(all(0 <= d <= 30 for d in draws))
        self.assertAlmostEqual(21.0, sum(draws) / len(draws), delta=0.3)
        var = sum((d - 21.0) ** 2 for d in draws) / len(draws)
        self.assertAlmostEqual(30 * 0.7 * 0.3, var, delta=0.6)
        self.assertEqual([0, 0], tune.binomial_draws(0, 0.5, 2, rng))

    def test_successive_halving_keeps_the_best_and_the_baseline(self):
        self.assertEqual(["c3", "c1", "c0"], tune.successive_halving_keep(["c3", "c1", "c2", "c4", "c0"], 3, "c0"))
        self.assertEqual(["c0", "c3"], tune.successive_halving_keep(["c0", "c3", "c1", "c2"], 2, "c0"))
        self.assertEqual(["c2"], tune.successive_halving_keep(["c2"], 3, "c2"))

    def test_option_parsing(self):
        self.assertEqual([10, 30], tune.parse_rounds("10,30"))
        for bad in ("30,10", "0", "x", ""):
            with self.assertRaises(RunError):
                tune.parse_rounds(bad)
        self.assertEqual((0, -1, 5), (tune.parse_cv("off"), tune.parse_cv("loo"), tune.parse_cv("5")))
        with self.assertRaises(RunError):
            tune.parse_cv("1")
        self.assertEqual({"a": ("x", "y"), "b": ("z",)}, tune.parse_groups(["a=x, y", "B=z"]))
        self.assertEqual(tune.DEFAULT_GROUPS, tune.parse_groups(None))
        for bad in (["a"], ["a=x", "b=x"], ["a="], ["9=x"]):
            with self.assertRaises(RunError):
                tune.parse_groups(bad)


# ============================================================ decks and keys


def _decks():
    db = make_db()
    specs = [("Red Burn", "40 Mountain\n20 Shock\n", "aggro", 40.0),
             ("Green Bears", "40 Forest\n20 Grizzly Bears\n", "aggro", 45.0),
             ("Giant Control", "40 Mountain\n20 Hill Giant\n", "control", 55.0),
             ("Strike Control", "36 Mountain\n24 Lightning Strike\n", "midrange", 60.0),
             ("Rat Tempo", "30 Mountain\n30 Rat Colony\n", "tempo", 50.0)]
    keys = experiment.unique_keys(s[0] for s in specs)
    entrants, real = [], {}
    for key, (name, text, cat, rate) in zip(keys, specs):
        deck = deck_from_text(text, name, db)
        deck.path = Path(f"/decks/{key}.txt")
        entrants.append(Entrant(key, deck, role="hero", category=cat))
        real[key] = rate
    return entrants, real


class DeckSetupTest(unittest.TestCase):
    def test_groups_real_rates_and_holdout(self):
        entrants, real = _decks()
        decks = tune.make_decks(entrants, real, tune.DEFAULT_GROUPS, ["giant control", "rat-tempo.txt"])
        self.assertEqual(["proactive", "proactive", "reactive", "reactive", "reactive"], [d.group for d in decks])
        self.assertEqual([False, False, True, False, True], [d.holdout for d in decks])
        self.assertAlmostEqual(0.4, decks[0].real)
        with self.assertRaises(RunError):
            tune.make_decks(entrants, real, {"only": ("aggro",)})
        with self.assertRaises(RunError):
            tune.make_decks(entrants, real, tune.DEFAULT_GROUPS, ["No Such Deck"])
        with self.assertRaises(RunError):
            tune.make_decks(entrants, dict(real, **{"red-burn": 140}), tune.DEFAULT_GROUPS)

    def test_pairing_key_covers_everything_that_decides_a_game(self):
        entrants, _ = _decks()
        a, b = entrants[0], entrants[1]
        base = tune.pairing_key("eng", 1, a, b, "h1", "h2", "off", 180)
        self.assertEqual(base, tune.pairing_key("eng", 1, a, b, "h1", "h2", "off", 180))
        variants = [tune.pairing_key("eng2", 1, a, b, "h1", "h2", "off", 180),
                    tune.pairing_key("eng", 2, a, b, "h1", "h2", "off", 180),
                    tune.pairing_key("eng", 1, a, b, "h9", "h2", "off", 180),
                    tune.pairing_key("eng", 1, a, b, "h1", "h9", "off", 180),
                    tune.pairing_key("eng", 1, a, b, "h1", "h2", "on", 180),
                    tune.pairing_key("eng", 1, a, b, "h1", "h2", "off", 60),
                    tune.pairing_key("eng", 1, b, a, "h2", "h1", "off", 180)]
        self.assertEqual(len(variants), len(set(variants) - {base}))
        renamed = Entrant("other", deck_from_text("40 Mountain\n20 Shock\n", "Red Control", make_db()))
        self.assertNotEqual(base, tune.pairing_key("eng", 1, renamed, b, "h1", "h2", "off", 180),
                            "Forge pilots decks named ...Control differently, so the name is part of the key")

    def test_game_cache_persists_and_survives_a_cut_line(self):
        tmp = Path(tempfile.mkdtemp(prefix="mtgsim-cache-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        cache = tune.GameCache(tmp / "cache.jsonl")
        cache.add({"pk": "k", "g": 0, "status": "ok", "winner": "a"})
        cache.add({"pk": "k", "g": 1, "status": "ok", "winner": "b"})
        with open(tmp / "cache.jsonl", "a") as fh:
            fh.write('{"pk": "k", "g": 2, "sta')
        again = tune.GameCache(tmp / "cache.jsonl")
        self.assertEqual(2, len(again))
        self.assertEqual("b", again.get("k", 1)["winner"])
        self.assertIsNone(again.get("k", 2))
        result = tune.collect(again, "k", "x", "y", range(0, 3))
        self.assertEqual((1, 2, 2, 3), (result.wins, result.decided, result.found, result.wanted))

    def test_matchup_file(self):
        entrants, real = _decks()
        decks = tune.make_decks(entrants, real, tune.DEFAULT_GROUPS)
        tmp = Path(tempfile.mkdtemp(prefix="mtgsim-mu-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        path = tmp / "m.json"
        path.write_text(json.dumps({"matchups": [
            {"a": "Green Bears", "b": "Red Burn", "real_win_rate": 60, "games": 100, "source": "s1"},
            {"a": "red-burn", "b": "green-bears", "real_win_rate": 50, "games": 300, "source": "s2"},
            {"a": "Red Burn", "b": "Unknown Deck", "real_win_rate": 50, "games": 10},
        ]}))
        matchups, notes = tune.load_matchups(path, decks)
        self.assertEqual(1, len(matchups))
        m = matchups[0]
        self.assertEqual(("red-burn", "green-bears", 400), (m.a, m.b, m.games))
        self.assertAlmostEqual((0.4 * 100 + 0.5 * 300) / 400, m.real, msg="flipped to the run's orientation, pooled")
        self.assertEqual(1, len(notes))
        path.write_text(json.dumps([{"a": "Red Burn", "b": "Green Bears", "real_win_rate": 0.5, "games": 0}]))
        with self.assertRaises(RunError):
            tune.load_matchups(path, decks)


# ================================================================ the search


STRENGTH = {"red-burn": 1.5, "green-bears": 1.2, "giant-control": 0.0, "strike-control": 0.2, "rat-tempo": 0.4}


def fake_engine(played, results=None):
    """Seat strength from the deck, plus a large boost for a reactive deck playing a tuned profile.

    With the base profile the creature decks win (simulated ranks oppose the real ones); with any
    tuned reactive profile the reactive decks win more, which is what the search should find.
    """
    def run_jobs(install, jobs, on_result, **kwargs):
        assert kwargs.get("profile_dir") is not None
        for job in jobs:
            played.append((job.meta["pk"], job.meta["g"]))
            score = [STRENGTH[k] + (2.0 if p.startswith("tune-reactive") else 0.0)
                     for k, p in zip(job.meta["seats"], job.profiles)]
            p0 = 1.0 / (1.0 + math.exp(score[1] - score[0]))
            rng = random.Random(f"{job.seed}|{job.profiles}")
            winner = 0 if rng.random() < p0 else 1
            player = {"mainCount": 60, "mulligans": 0}
            on_result(job, {"status": "ok", "winner": winner, "first": rng.randrange(2), "turns": 9, "ms": 1,
                            "players": [dict(player), dict(player)]})
        return {}
    return run_jobs


SEARCH_SPACE = {"base": "Default", "change_probability": 1.0, "params": [
    {"key": "MULLIGAN_THRESHOLD", "values": [5, 6, 7]},
]}


class SearchTest(TempHome):
    def _tuner(self, run_dir, holdout=(), real=None, **overrides):
        entrants, real0 = _decks()
        real = real or real0
        settings = {"seed": 1, "search_seed": 1, "rounds": [4, 8], "eta": 2, "profiles_per_group": 2,
                    "groups": {k: list(v) for k, v in tune.DEFAULT_GROUPS.items()}, "tune_groups": ["reactive"],
                    "holdout": list(holdout), "confirm_games": 4, "cv": -1, "objective": "deck", "bootstrap": 60,
                    "timeout": 180, "mc": "off"}
        settings.update(overrides)
        space = tune.parse_space(SEARCH_SPACE)
        decks = tune.make_decks(entrants, real, tune.DEFAULT_GROUPS, holdout)
        base = ai_profiles.effective(DEFAULT_AI)
        groups = sorted({d.group for d in decks}, key=list(tune.DEFAULT_GROUPS).index)
        profiles, cands = tune.make_candidates(space, settings["tune_groups"], groups, settings["profiles_per_group"],
                                               base, random.Random("tune-search-1"))
        return tune.Tuner(self.install, run_dir, decks, space, settings, profiles, cands, engine_id="test-engine",
                          say=lambda *_: None)

    def _run(self, tuner, played, imports=()):
        with mock.patch.object(runner, "run_jobs", fake_engine(played)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return tuner.run(imports)

    def test_search_finds_the_better_profile_and_writes_its_history(self):
        played = []
        run = self.tmp / "run"
        state = self._run(self._tuner(run), played)
        self.assertEqual("done", state["status"])
        self.assertNotEqual("c00", state["best"])
        diff = state["confirm"]["difference"]["train"]["spearman"]
        self.assertGreater(diff["diff"], 0)
        saved = json.loads((run / "tune.json").read_text())
        self.assertEqual([1, 2], [r["round"] for r in saved["rounds"]])
        self.assertEqual(3, len(saved["rounds"][0]["candidates"]))
        self.assertIn("c00", saved["rounds"][1]["candidates"], "the baseline always survives")
        self.assertTrue((run / "ai" / "Default.ai").is_file())
        best = json.loads((run / "best" / "tuned-reactive.json").read_text())
        self.assertEqual("Default", best["base"])
        self.assertTrue(best["overrides"])
        self.assertTrue(saved["data_needed"]["text"])
        self.assertIsNotNone(saved["cv"]["out_of_fold"]["spearman"])
        self.assertEqual({d["key"] for d in saved["decks"] if not d["holdout"]}, set(state["cv"]["chosen"]),
                         "leave-one-out gives every training deck a prediction made without it")

    def test_unchanged_pairings_are_never_replayed(self):
        played = []
        tuner = self._tuner(self.tmp / "run")
        state = self._run(tuner, played)
        self.assertEqual(len(played), len(set(played)), "no game is played twice")
        proactive = [(a, b) for a, b in tuner.pairs if tuner.by_key[a].group == tuner.by_key[b].group == "proactive"]
        self.assertEqual(1, len(proactive))
        keys = {pk for pk, _ in played if any(pk == tuner.pk(tuner.cand(c["id"]), *proactive[0]) for c in tuner.candidates)}
        self.assertEqual(1, len(keys), "the aggro-vs-aggro pairing plays the same games for every candidate")
        round1 = state["rounds"][0]
        self.assertEqual(round1["results_used"] - round1["new_games"],
                         2 * 4 * 1, "two non-baseline candidates reuse the baseline's 4 games of that pairing")
        confirm_games = [g for _, g in played if g >= 8]
        self.assertTrue(confirm_games and all(8 <= g < 12 for g in confirm_games),
                        "confirmation plays fresh game indices")

    def test_resume_plays_nothing_new_and_gives_the_same_answer(self):
        played = []
        run = self.tmp / "run"
        first = self._run(self._tuner(run), played)
        again = []
        second = self._run(self._tuner(run), again)
        self.assertEqual([], again)
        self.assertEqual(first["best"], second["best"])
        self.assertEqual(first["confirm"]["difference"]["train"]["spearman"]["diff"],
                         second["confirm"]["difference"]["train"]["spearman"]["diff"])

    def test_plan_matches_what_the_first_round_plays(self):
        played = []
        tuner = self._tuner(self.tmp / "run")
        tuner.prepare()
        plan = tuner.plan()
        state = self._run(tuner, played)
        self.assertEqual(plan["steps"][0]["new_games"], state["rounds"][0]["new_games"])
        self.assertGreaterEqual(plan["games"], len(played), "later rounds are an upper estimate")

    def test_held_out_real_rates_never_influence_selection(self):
        entrants, real = _decks()
        changed = dict(real, **{"strike-control": 1.0})
        a = self._run(self._tuner(self.tmp / "a", holdout=["strike-control"]), [])
        b = self._run(self._tuner(self.tmp / "b", holdout=["strike-control"], real=changed), [])
        self.assertEqual(a["best"], b["best"])
        self.assertEqual([r["ranking"] for r in a["rounds"]], [r["ranking"] for r in b["rounds"]])
        ra, rb = a["rounds"][0]["results"]["c00"]["metrics"], b["rounds"][0]["results"]["c00"]["metrics"]
        self.assertEqual(ra["train"], rb["train"])
        self.assertNotEqual(ra["holdout"]["mae"], rb["holdout"]["mae"])
        self.assertEqual(1, ra["holdout"]["n"])
        self.assertNotIn("strike-control", a["cv"]["chosen"])

    def test_identical_candidates_have_exactly_zero_paired_difference(self):
        tuner = self._tuner(self.tmp / "run")
        tuner.prepare()
        with mock.patch.object(runner, "run_jobs", fake_engine([])), contextlib.redirect_stderr(io.StringIO()):
            tuner.play(tuner.needed(["c00"], range(0, 6))[0])
        ev = tuner.evaluate("c00", range(0, 6))
        diff = tuner.paired_difference(ev, tuner.evaluate("c00", range(0, 6)))
        self.assertEqual(0.0, diff["train"]["spearman"]["diff"])
        self.assertEqual([0.0, 0.0], diff["train"]["spearman"]["noise"])
        self.assertFalse(diff["train"]["spearman"]["clears_noise"])
        lo, hi = ev["noise"]["train"]["spearman"]
        self.assertLessEqual(lo, hi)

    def test_matchup_objective(self):
        tuner = self._tuner(self.tmp / "run", objective="matchup")
        tuner.matchups = [tune.Matchup("red-burn", "giant-control", 0.3, 200),
                          tune.Matchup("green-bears", "strike-control", 0.35, None),
                          tune.Matchup("red-burn", "rat-tempo", 0.45, 50),
                          tune.Matchup("giant-control", "strike-control", 0.5, 80)]
        state = self._run(tuner, [])
        metrics = state["rounds"][0]["results"]["c00"]["metrics"]
        self.assertEqual(4, metrics["matchup_train"]["n"])
        self.assertEqual(metrics["matchup_train"]["spearman"], state["rounds"][0]["results"]["c00"]["objective"])

    def test_import_takes_identical_games_from_an_earlier_run(self):
        entrants, _ = _decks()
        prior = self.tmp / "prior"
        options = RunOptions(games=4, seed=1)
        with mock.patch.object(experiment, "run_jobs", self._fake_execute_engine()):
            experiment.execute(self.install, prior, entrants, [(entrants[0], entrants[1]), (entrants[2], entrants[0])],
                               options, quiet=True)
        info = json.loads((prior / "run.json").read_text())
        info["forge"]["fingerprint"] = "test-engine"
        (prior / "run.json").write_text(json.dumps(info))
        tuner = self._tuner(self.tmp / "run")
        tuner.prepare()
        counts = tuner.import_run(prior)
        self.assertEqual(4, counts["imported"])
        self.assertEqual(4, counts["skipped: pairing played the other way round"])
        pk = tuner.pk(tuner.cand("c00"), "red-burn", "green-bears")
        record = tuner.cache.get(pk, 1)
        self.assertEqual("b", record["winner"], "game 1 has the pairing's first deck in seat 1, and seat 0 won")
        self.assertEqual(4, tuner.import_run(prior)["already cached"], "importing twice adds nothing")
        self.assertEqual("", info["forge"]["patches"]["combined_sha256"], "execute records the patch set")
        for change in ({"seed": 2}, {"patched": "abc123"}):
            broken = json.loads(json.dumps(info))
            if "seed" in change:
                broken["options"]["seed"] = change["seed"]
            else:
                broken["forge"]["patches"]["combined_sha256"] = change["patched"]
            (prior / "run.json").write_text(json.dumps(broken))
            with self.assertRaises(RunError, msg=str(change)):
                tuner.import_run(prior)
        # A run from before patches were recorded was unpatched: fine for an unpatched Forge, not for a patched one.
        old = json.loads(json.dumps(info))
        del old["forge"]["patches"]
        (prior / "run.json").write_text(json.dumps(old))
        self.assertEqual(4, tuner.import_run(prior)["already cached"])
        patched = self._tuner(self.tmp / "run2")
        patched.patches = {"state": "up-to-date", "applied": [{"name": "0001-x", "sha256": "f"}], "combined_sha256": "abc"}
        patched.prepare()
        with self.assertRaises(RunError) as ctx:
            patched.import_run(prior)
        self.assertIn("unpatched", str(ctx.exception))

    def test_the_forge_patch_set_is_part_of_the_engine_identity(self):
        with mock.patch.object(ForgeInstall, "fingerprint", lambda self: "build1"):
            plain = tune.engine_identity(self.install, {"combined_sha256": ""})
            patched = tune.engine_identity(self.install, {"combined_sha256": "abc"})
            other = tune.engine_identity(self.install, {"combined_sha256": "abd"})
            tuner = tune.Tuner(self.install, self.tmp / "run", [], tune.parse_space(SEARCH_SPACE), {"seed": 1}, {}, [],
                               patches={"state": "up-to-date", "applied": [], "combined_sha256": "abc"})
        self.assertEqual(3, len({plain, patched, other}))
        self.assertEqual(patched, tuner.engine_id)
        self.assertEqual("build1", tuner.build_fingerprint)
        entrants, _ = _decks()
        keys = {tune.pairing_key(e, 1, entrants[0], entrants[1], "h", "h", "off", 180) for e in (plain, patched)}
        self.assertEqual(2, len(keys), "a game on a patched Forge is a different game")

    @staticmethod
    def _fake_execute_engine():
        def run_jobs(install, jobs, on_result, **kwargs):
            for job in jobs:
                player = {"mainCount": 60, "mulligans": 1}
                on_result(job, {"status": "ok", "winner": 0, "first": 0, "turns": 7, "ms": 1,
                                "players": [dict(player), dict(player)]})
            return {}
        return run_jobs


if __name__ == "__main__":
    unittest.main()
