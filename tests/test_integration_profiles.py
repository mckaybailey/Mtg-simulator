"""Real-engine check that a run's own AI profiles reach Forge (skipped when Forge is not set up).

A deck of 60 Forests can never cast anything, so the AI mulligans it under the Default profile.
With MULLIGAN_THRESHOLD=8 a seven-card hand is already below the threshold and is always kept:
if that generated profile reaches the engine, its seat records zero mulligans. A few short games.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from mtgsim import ai_profiles, experiment
from mtgsim.decks import deck_from_text
from mtgsim.experiment import Entrant, RunOptions
from tests.test_integration import _forge_or_skip


class ProfileFolderIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = _forge_or_skip()
        from mtgsim.carddb import load_database

        cls.db = load_database(cls.install)
        cls.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-it-profiles-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _play(self, name, profile, extra=None):
        lands = Entrant("lands", deck_from_text("60 Forest\n", "lands", self.db), ai_profile=profile)
        goblins = Entrant("goblins", deck_from_text("20 Mountain\n40 Raging Goblin\n", "goblins", self.db))
        records = experiment.execute(self.install, self.tmp / name, [lands, goblins], [(lands, goblins)],
                                     RunOptions(games=2, seed=5, workers=1, timeout=120), quiet=True, profiles=extra)
        return sorted(records, key=lambda r: r["game"])

    @staticmethod
    def _mulligans(record):
        return record["players"][record["seats"].index("lands")]["mulligans"]

    def test_a_generated_profile_changes_how_the_engine_plays(self):
        default = self._play("default", "")
        self.assertTrue(all(r["status"] == "ok" for r in default), [r.get("error") for r in default])
        self.assertGreater(sum(self._mulligans(r) for r in default), 0, "60 lands should be mulliganed under Default")
        probe = ai_profiles.build(self.install, "Default", {"MULLIGAN_THRESHOLD": 8})
        never = self._play("probe", "mtgsim-test-probe", {"mtgsim-test-probe": probe})
        self.assertTrue(all(r["status"] == "ok" for r in never), [r.get("error") for r in never])
        self.assertEqual([0, 0], [self._mulligans(r) for r in never])
        self.assertEqual([r["seed"] for r in default], [r["seed"] for r in never], "same seeds, different play")

    def test_an_unknown_profile_is_an_error_not_a_silent_fallback(self):
        lands = Entrant("lands", deck_from_text("60 Forest\n", "lands", self.db))
        goblins = Entrant("goblins", deck_from_text("20 Mountain\n40 Raging Goblin\n", "goblins", self.db))
        experiment.write_decks([lands, goblins], self.tmp / "unknown")
        experiment.prepare_profiles(self.install, self.tmp / "unknown", [])
        job = experiment.plan_pairing(lands, goblins, RunOptions(games=1), self.tmp / "unknown")[0]
        job.profiles = ["NoSuchProfile", ""]
        results = []
        from mtgsim import runner

        runner.run_jobs(self.install, [job], lambda j, r: results.append(r), workers=1,
                        log_dir=self.tmp / "unknown" / "logs", profile_dir=self.tmp / "unknown" / "ai")
        self.assertEqual("error", results[0]["status"])
        self.assertIn("unknown AI profile", results[0].get("error", ""))


if __name__ == "__main__":
    unittest.main()
