"""The Forge patch mechanism, on a tiny git repository laid out like a Forge checkout.

No network, no Forge, no Maven: `forge._maven_build` is replaced by a fake that writes a jar."""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import experiment, forge
from mtgsim.experiment import Entrant, RunOptions
from mtgsim.forge import ForgeError, ForgeInstall
from tests.helpers import make_db

CARD = "forge-gui/res/cardsfolder/l/llanowar_elves.txt"
BEARS = "forge-gui/res/cardsfolder/g/grizzly_bears.txt"
PROFILE = "forge-gui/res/ai/Default.ai"
JAVA = "forge-ai/src/main/java/forge/ai/AiController.java"

FILES = {
    CARD: "Name:Llanowar Elves\nManaCost:G\nTypes:Creature Elf Druid\nPT:1/1\n"
          "A:AB$ Mana | Cost$ T | Produced$ G | SpellDescription$ Add {G}.\nOracle:{T}: Add {G}.\n",
    BEARS: "Name:Grizzly Bears\nManaCost:1 G\nTypes:Creature Bear\nPT:2/2\nOracle:\n",
    PROFILE: "MulliganThreshold=2\nPlayAggro=false\nMoveEquipmentToBetterCreatures=true\n",
    JAVA: "package forge.ai;\n\npublic class AiController {\n    int aggression() {\n        return 1;\n    }\n}\n",
    "pom.xml": "<project/>\n",
}

HEADER = "Subject: {name}\nWhy: a test.\nMeasured: not measured, it is a test.\n\n"


def git(cwd, *args):
    proc = subprocess.run(
        ["git", "-c", "user.name=mtgsim test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
         *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout


def write(root, path, text):
    target = Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class PatchTestCase(unittest.TestCase):
    """A fake Forge 'upstream' repository, a checkout of it, and a folder of patches."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-patches-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        saved = os.environ.get("MTGSIM_HOME")
        os.environ["MTGSIM_HOME"] = str(self.tmp / "home")
        self.addCleanup(lambda: os.environ.pop("MTGSIM_HOME", None) if saved is None
                        else os.environ.__setitem__("MTGSIM_HOME", saved))

        self.upstream = self.tmp / "upstream"
        self.upstream.mkdir()
        git(self.upstream, "init", "-q")
        for path, text in FILES.items():
            write(self.upstream, path, text)
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", "pinned")
        self.ref = git(self.upstream, "rev-parse", "HEAD").strip()

        self.root = self.tmp / "forge"
        git(self.tmp, "clone", "-q", str(self.upstream), str(self.root))
        git(self.root, "checkout", "-q", "--detach", self.ref)
        self.work = self.tmp / "work"  # where patches are made, so the checkout stays untouched
        git(self.tmp, "clone", "-q", str(self.upstream), str(self.work))
        self.patch_dir = self.tmp / "patches"
        self.patch_dir.mkdir()
        self.builds = 0
        self.messages = []

    # ------------------------------------------------------------ helpers

    def make_patch(self, name, edits, base=()):
        """Write NAME.patch changing ``edits`` ({path: new text, or None to delete}), made on top of
        the patches in ``base`` (so a later patch may touch a file an earlier one changed)."""
        for earlier in base:
            git(self.work, "apply", str(self.patch_dir / earlier))
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "base", "--allow-empty")
        for path, text in edits.items():
            if text is None:
                (self.work / path).unlink()
            else:
                existed = (self.work / path).exists()
                write(self.work, path, text)
                if not existed:
                    git(self.work, "add", "-N", path)
        diff = git(self.work, "diff")
        path = self.patch_dir / name
        path.write_text(HEADER.format(name=name) + diff, encoding="utf-8")
        git(self.work, "reset", "-q", "--hard", self.ref)
        git(self.work, "clean", "-q", "-fd")
        return path

    def fake_build(self, dest):
        self.builds += 1
        jar = Path(dest) / "forge-gui-desktop" / "target" / "forge-gui-desktop-9.9-jar-with-dependencies.jar"
        jar.parent.mkdir(parents=True, exist_ok=True)
        jar.write_text(f"build {self.builds}\n")

    def build(self, names=None, apply_patches=True):
        """Run setup --build's logic on the checkout with the patches ``names`` (default: all)."""
        patches = [p for p in forge.load_patches(self.patch_dir) if names is None or p.name in names]
        with mock.patch.object(forge, "_maven_build", side_effect=self.fake_build):
            return forge.build_from_source(self.root, ref=self.ref, say=self.messages.append,
                                           patches=patches, apply_patches=apply_patches)

    def read(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def marker(self):
        return json.loads((self.root / forge.PATCH_MARKER).read_text(encoding="utf-8"))

    def status(self, names=None, verify=False):
        patches = [p for p in forge.load_patches(self.patch_dir) if names is None or p.name in names]
        return forge.patch_status(self.root, patches=patches, verify=verify)

    def card_patch(self, name="0001-elves-main-one.patch"):
        return self.make_patch(name, {CARD: FILES[CARD].replace("Oracle:", "SVar:PlayMain1:TRUE\nOracle:")})

    def profile_patch(self, name="0002-aggro-profile.patch"):
        return self.make_patch(name, {PROFILE: FILES[PROFILE].replace("PlayAggro=false", "PlayAggro=true")})

    def java_patch(self, name="0003-ai-aggression.patch"):
        return self.make_patch(name, {JAVA: FILES[JAVA].replace("return 1;", "return 2;")})


class ApplyTest(PatchTestCase):
    def test_fresh_build_applies_the_patches_and_records_them(self):
        card, profile = self.card_patch(), self.profile_patch()
        install = self.build()

        self.assertEqual(1, self.builds, "a checkout without a jar is built once")
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD))
        self.assertIn("PlayAggro=true", self.read(PROFILE))
        self.assertEqual(FILES[BEARS], self.read(BEARS))
        self.assertEqual(self.root.resolve(), install.root)

        marker = self.marker()
        self.assertEqual("applied", marker["state"])
        self.assertEqual(self.ref, marker["forge_ref"])
        entries = [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (card, profile)]
        self.assertEqual(entries, [{"name": p["name"], "sha256": p["sha256"]} for p in marker["patches"]])
        self.assertEqual([[CARD], [PROFILE]], [p["paths"] for p in marker["patches"]])
        self.assertEqual([False, False], [p["code"] for p in marker["patches"]])
        self.assertEqual(forge.combined_sha256(entries), marker["combined_sha256"])
        self.assertEqual(64, len(marker["combined_sha256"]))
        self.assertEqual({CARD, PROFILE}, set(marker["files"]))
        self.assertEqual({"ref": self.ref, "code_patches": []}, marker["jar"])

        status = self.status(verify=True)
        self.assertEqual("up-to-date", status.state)
        self.assertIn("2 applied, up to date", status.summary())
        self.assertIsNone(status.warning())
        self.assertEqual(entries, status.record()["applied"])

    def test_git_apply_skips_the_description(self):
        patch = self.card_patch()
        self.assertTrue(patch.read_text().startswith("Subject: 0001-elves-main-one.patch\nWhy:"))
        self.assertEqual("Subject: 0001-elves-main-one.patch\nWhy: a test.\nMeasured: not measured, it is a test.",
                         forge.load_patches(self.patch_dir)[0].description)
        self.build()
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD))

    def test_rerun_with_the_same_patches_changes_nothing(self):
        self.card_patch()
        self.build()
        before_marker = (self.root / forge.PATCH_MARKER).read_bytes()
        before_mtime = (self.root / CARD).stat().st_mtime_ns
        self.messages.clear()
        self.build()
        self.assertEqual(1, self.builds)
        self.assertEqual(before_marker, (self.root / forge.PATCH_MARKER).read_bytes())
        self.assertEqual(before_mtime, (self.root / CARD).stat().st_mtime_ns, "an unchanged set is not re-applied")
        self.assertTrue(any("unchanged" in m for m in self.messages), self.messages)

    def test_changed_set_restores_old_files_and_applies_the_new_set(self):
        self.card_patch()
        self.make_patch("0002-new-card.patch", {"forge-gui/res/cardsfolder/z/zz_test_card.txt": "Name:ZZ Test\n"})
        self.profile_patch("0003-aggro-profile.patch")
        self.build(["0001-elves-main-one.patch", "0002-new-card.patch"])
        self.assertTrue((self.root / "forge-gui/res/cardsfolder/z/zz_test_card.txt").is_file())

        self.build(["0003-aggro-profile.patch"])
        self.assertEqual(FILES[CARD], self.read(CARD), "a patch that was dropped is taken off")
        self.assertFalse((self.root / "forge-gui/res/cardsfolder/z").exists(), "files a patch created are deleted")
        self.assertIn("PlayAggro=true", self.read(PROFILE))
        self.assertEqual(["0003-aggro-profile.patch"], [p["name"] for p in self.marker()["patches"]])
        self.assertEqual(1, self.builds, "card scripts and AI profiles need no rebuild")
        self.assertTrue(any("No Maven rebuild needed" in m for m in self.messages), self.messages)
        self.assertEqual("", git(self.root, "status", "--porcelain", "--", "forge-gui/res/cardsfolder"))

    def test_edited_patch_content_is_reapplied(self):
        self.card_patch()
        self.build()
        self.make_patch("0001-elves-main-one.patch", {CARD: FILES[CARD].replace("PT:1/1", "PT:1/2")})
        self.assertEqual("out-of-date", self.status().state)
        self.assertIn("changed since applied: 0001-elves-main-one.patch", self.status().problems)
        self.build()
        self.assertNotIn("SVar:PlayMain1:TRUE", self.read(CARD))
        self.assertIn("PT:1/2", self.read(CARD))

    def test_patches_on_the_same_file_apply_in_order(self):
        self.card_patch()
        self.make_patch("0002-elves-again.patch", {CARD: FILES[CARD].replace(
            "Oracle:", "SVar:PlayMain1:TRUE\nSVar:BuffedBy:Elf\nOracle:")}, base=["0001-elves-main-one.patch"])
        self.build()
        self.assertIn("SVar:PlayMain1:TRUE\nSVar:BuffedBy:Elf\n", self.read(CARD))
        self.assertEqual([[CARD], [CARD]], [p["paths"] for p in self.marker()["patches"]])
        self.build(["0001-elves-main-one.patch"])
        self.assertNotIn("BuffedBy", self.read(CARD))

    def test_deleting_and_creating_files(self):
        self.make_patch("0001-drop-bears.patch", {BEARS: None, "forge-ai/src/main/java/forge/ai/NewLogic.java": "class X {}\n"})
        self.build()
        self.assertFalse((self.root / BEARS).exists())
        self.assertTrue((self.root / "forge-ai/src/main/java/forge/ai/NewLogic.java").is_file())
        self.assertEqual([True], [p["code"] for p in self.marker()["patches"]])
        self.build([])
        self.assertEqual(FILES[BEARS], self.read(BEARS))
        self.assertFalse((self.root / "forge-ai/src/main/java/forge/ai/NewLogic.java").exists())
        self.assertTrue((self.root / JAVA).is_file(), "directories that still hold files stay")
        self.assertEqual("", git(self.root, "status", "--porcelain", "--untracked-files=all", "--", "forge-ai", "forge-gui"))


class RebuildTest(PatchTestCase):
    def test_only_code_patches_trigger_a_maven_rebuild(self):
        self.card_patch()
        self.java_patch("0002-ai-aggression.patch")
        self.profile_patch("0003-aggro-profile.patch")

        self.build(["0001-elves-main-one.patch"])
        self.assertEqual(1, self.builds)  # first build
        self.build(["0001-elves-main-one.patch", "0002-ai-aggression.patch"])
        self.assertEqual(2, self.builds, "a patch to Java code needs a rebuild")
        self.assertIn("return 2;", self.read(JAVA))
        self.assertEqual([False, True], [p["code"] for p in self.marker()["patches"]])
        self.assertTrue(any("Rebuilding Forge" in m for m in self.messages), self.messages)

        self.build(["0001-elves-main-one.patch", "0002-ai-aggression.patch", "0003-aggro-profile.patch"])
        self.assertEqual(2, self.builds, "the jar already has this code; the new patch is res-only")
        self.build(["0001-elves-main-one.patch", "0003-aggro-profile.patch"])
        self.assertEqual(3, self.builds, "taking a code patch off needs a rebuild too")
        self.assertEqual(FILES[JAVA], self.read(JAVA))
        self.assertEqual({"ref": self.ref, "code_patches": []}, self.marker()["jar"])

    def test_a_failed_build_is_retried_and_reported(self):
        self.card_patch()
        self.build()
        self.java_patch("0002-ai-aggression.patch")
        with mock.patch.object(forge, "_maven_build", side_effect=ForgeError("The Forge build failed")):
            with self.assertRaises(ForgeError):
                forge.build_from_source(self.root, ref=self.ref, say=self.messages.append,
                                        patches=forge.load_patches(self.patch_dir))
        status = self.status()
        self.assertEqual("out-of-date", status.state)
        self.assertTrue(any("not rebuilt" in p for p in status.problems), status.problems)
        self.build()
        self.assertEqual(2, self.builds, "the next setup builds again although the patches are already applied")
        self.assertEqual("up-to-date", self.status().state)

    def test_an_existing_unpatched_build_is_not_rebuilt_for_res_patches(self):
        # A checkout built before patches were tracked: jar present, no marker.
        self.fake_build(self.root)
        self.card_patch()
        self.build()
        self.assertEqual(1, self.builds, "only the fake build above; the card patch needs no Maven run")
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD))

    def test_moving_to_another_commit_takes_patches_off_reapplies_and_rebuilds(self):
        self.make_patch("0001-new-card.patch", {"forge-gui/res/cardsfolder/z/zz_test_card.txt": "Name:ZZ Test\n"})
        self.card_patch("0002-elves-main-one.patch")
        self.build()
        write(self.upstream, BEARS, FILES[BEARS].replace("PT:2/2", "PT:2/3"))
        git(self.upstream, "commit", "-q", "-am", "upstream moves on")
        new_ref = git(self.upstream, "rev-parse", "HEAD").strip()
        with mock.patch.object(forge, "_maven_build", side_effect=self.fake_build):
            forge.build_from_source(self.root, ref=new_ref, say=self.messages.append,
                                    patches=forge.load_patches(self.patch_dir))
        self.assertEqual(new_ref, git(self.root, "rev-parse", "HEAD").strip())
        self.assertIn("PT:2/3", self.read(BEARS))
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD))
        self.assertTrue((self.root / "forge-gui/res/cardsfolder/z/zz_test_card.txt").is_file())
        self.assertEqual(new_ref, self.marker()["forge_ref"])
        self.assertEqual(2, self.builds, "a different commit needs a rebuild")


class ErrorTest(PatchTestCase):
    def test_a_patch_that_does_not_apply_is_named_and_nothing_changes(self):
        self.card_patch()
        self.build()
        before = (self.root / forge.PATCH_MARKER).read_bytes()
        bad = self.make_patch("0002-stale.patch", {BEARS: FILES[BEARS].replace("PT:2/2", "PT:3/3")})
        bad.write_text(bad.read_text().replace("-PT:2/2", "-PT:9/9").replace(" Types:Creature Bear", " Types:Creature Wolf"))
        with self.assertRaises(ForgeError) as caught:
            self.build()
        message = str(caught.exception)
        self.assertIn("0002-stale.patch does not apply", message)
        self.assertIn("on top of 0001-elves-main-one.patch", message)
        self.assertIn("nothing in", message)
        self.assertEqual(before, (self.root / forge.PATCH_MARKER).read_bytes())
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD), "the patches already applied stay")
        self.assertEqual(FILES[BEARS], self.read(BEARS))
        self.assertEqual(1, self.builds)

    def test_a_patch_that_conflicts_with_an_earlier_one(self):
        self.card_patch()
        self.make_patch("0002-elves-too.patch", {CARD: FILES[CARD].replace("PT:1/1", "PT:1/2").replace(
            "Oracle:", "SVar:Other:1\nOracle:")})
        with self.assertRaises(ForgeError) as caught:
            self.build()
        self.assertIn("0002-elves-too.patch does not apply", str(caught.exception))
        self.assertFalse((self.root / forge.PATCH_MARKER).exists() and self.marker()["patches"])
        self.assertEqual(FILES[CARD], self.read(CARD))

    def test_a_patch_without_a_diff_is_refused(self):
        (self.patch_dir / "0001-empty.patch").write_text(HEADER.format(name="empty"))
        with self.assertRaises(ForgeError) as caught:
            self.build()
        self.assertIn("0001-empty.patch does not apply", str(caught.exception))

    def test_an_interrupted_apply_is_repaired(self):
        self.card_patch()
        self.profile_patch()
        self.build(["0001-elves-main-one.patch"])
        marker = self.marker()
        marker["state"] = "applying"
        (self.root / forge.PATCH_MARKER).write_text(json.dumps(marker))
        status = self.status(["0001-elves-main-one.patch"])
        self.assertEqual("out-of-date", status.state)
        self.assertIn("stopped", status.problems[0])
        self.build(["0002-aggro-profile.patch"])
        self.assertEqual(FILES[CARD], self.read(CARD))
        self.assertIn("PlayAggro=true", self.read(PROFILE))
        self.assertEqual("up-to-date", self.status(["0002-aggro-profile.patch"]).state)

    def test_a_damaged_marker_is_repaired(self):
        self.card_patch()
        self.build()
        (self.root / forge.PATCH_MARKER).write_text("{not json")
        self.assertEqual("out-of-date", self.status().state)
        self.assertIn("unreadable", self.status().problems[0])
        self.build()
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD))
        self.assertEqual("up-to-date", self.status(verify=True).state)


class StatusTest(PatchTestCase):
    def test_out_of_date_when_the_shipped_set_differs(self):
        self.card_patch()
        self.profile_patch()
        self.build(["0001-elves-main-one.patch"])
        status = self.status()
        self.assertEqual("out-of-date", status.state)
        self.assertEqual(["not applied: 0002-aggro-profile.patch"], status.problems)
        self.assertIn("OUT OF DATE, 1 applied, mtgsim ships 2", status.summary())
        self.assertIn("setup --build", status.warning())
        self.assertIn("applied but no longer shipped: 0001-elves-main-one.patch",
                      self.status(["0002-aggro-profile.patch"]).problems)

    def test_hand_edits_are_found_only_when_verifying(self):
        self.card_patch()
        self.build()
        write(self.root, CARD, FILES[CARD])
        self.assertEqual("up-to-date", self.status().state, "the cheap check reads only the marker")
        status = self.status(verify=True)
        self.assertEqual("out-of-date", status.state)
        self.assertIn("changed by hand", status.problems[0])
        self.build()  # setup --build puts it back
        self.assertIn("SVar:PlayMain1:TRUE", self.read(CARD))
        self.assertEqual("up-to-date", self.status(verify=True).state)

    def test_a_forge_mtgsim_did_not_build_is_not_managed(self):
        self.card_patch()
        status = self.status()
        self.assertEqual("not-managed", status.state)
        self.assertIn("not applied", status.summary())
        self.assertIn("not built by `mtgsim setup --build`", status.warning())
        self.assertEqual({"state": "not-managed", "applied": [], "combined_sha256": ""}, status.record())
        empty = forge.patch_status(self.root, patches=[])
        self.assertIsNone(empty.warning(), "nothing to warn about when mtgsim ships no patches")
        self.assertIn("none", empty.summary())
        self.assertFalse((self.root / forge.PATCH_MARKER).exists(), "status never writes anything")

    def test_old_default_build_without_marker(self):
        default = self.tmp / "home" / "forge"
        default.parent.mkdir(parents=True)
        self.root.rename(default)
        self.assertEqual("up-to-date", forge.patch_status(default, patches=[]).state)
        self.card_patch()
        status = forge.patch_status(default, patches=forge.load_patches(self.patch_dir))
        self.assertEqual("out-of-date", status.state)
        self.assertEqual(["not applied: 0001-elves-main-one.patch"], status.problems)

    def test_no_patches_build_is_disabled(self):
        self.card_patch()
        self.build()
        self.build(apply_patches=False)
        self.assertEqual(FILES[CARD], self.read(CARD))
        status = self.status(verify=True)
        self.assertEqual("disabled", status.state)
        self.assertIn("--no-patches", status.summary())
        self.assertIn("--no-patches", status.warning())
        self.assertEqual([], status.record()["applied"])

    def test_fingerprint_and_driver_cache_follow_the_patch_set(self):
        self.build([])
        install = forge.detect_install(self.root)
        plain = install.fingerprint()
        self.assertEqual("", forge.applied_patch_key(self.root))
        (self.root / forge.PATCH_MARKER).unlink()
        self.assertEqual(plain, install.fingerprint(), "an unpatched Forge keeps its old cache names")
        self.build([])

        self.card_patch()
        self.profile_patch()
        self.build(["0001-elves-main-one.patch"])
        one = install.fingerprint()
        bridge_one = forge.bridge_dir(install)
        self.build()
        two = install.fingerprint()
        self.assertEqual(3, len({plain, one, two}), "every patch set has its own card cache and driver")
        self.assertNotEqual(bridge_one, forge.bridge_dir(install))
        self.build([])
        self.assertEqual(plain, install.fingerprint())


class RunRecordTest(PatchTestCase):
    def _execute(self, install, run_dir, quiet):
        db = make_db()
        from mtgsim.decks import deck_from_text
        entrants = [Entrant("red", deck_from_text("40 Mountain\n20 Shock\n", "Red", db)),
                    Entrant("green", deck_from_text("40 Forest\n20 Grizzly Bears\n", "Green", db))]

        def run_jobs(install, jobs, on_result, **kwargs):
            player = {"mainCount": 60, "opening": {}, "drawn": {}, "played": {}}
            for job in jobs:
                on_result(job, {"status": "ok", "winner": 0, "first": 0, "turns": 9, "ms": 1,
                                "players": [player, dict(player)]})
            return {"forgeVersion": "test"}

        err = io.StringIO()
        with mock.patch.object(experiment, "run_jobs", run_jobs), contextlib.redirect_stderr(err):
            experiment.execute(install, run_dir, entrants, [(entrants[0], entrants[1])], RunOptions(games=2),
                               quiet=quiet)
        notes = "".join(line for line in err.getvalue().splitlines(True) if " games/min " not in line)
        return json.loads((run_dir / "run.json").read_text())["forge"], notes

    def test_run_json_records_the_applied_patches(self):
        self.card_patch()
        self.profile_patch()
        install = self.build(["0001-elves-main-one.patch"])
        shipped = forge.load_patches(self.patch_dir)
        with mock.patch.object(forge, "load_patches", return_value=shipped[:1]):
            record, err = self._execute(install, self.tmp / "run", quiet=False)
        self.assertEqual("", err)
        self.assertEqual("up-to-date", record["patches"]["state"])
        self.assertEqual(["0001-elves-main-one.patch"], [p["name"] for p in record["patches"]["applied"]])
        self.assertEqual(self.marker()["combined_sha256"], record["patches"]["combined_sha256"])
        self.assertEqual("test", record["forgeVersion"])

        with mock.patch.object(forge, "load_patches", return_value=shipped):
            _record, err = self._execute(install, self.tmp / "run", quiet=False)
        self.assertIn("warning: Forge's patches are out of date (not applied: 0002-aggro-profile.patch)", err)

        self.build()  # now both: resuming the run mixes two engines
        with mock.patch.object(forge, "load_patches", return_value=shipped):
            record, err = self._execute(install, self.tmp / "run", quiet=False)
        self.assertNotIn("out of date", err)
        self.assertIn("this run was started on Forge patch set", err)
        self.assertEqual(2, len(record["patches"]["applied"]))

    def test_quiet_runs_do_not_warn(self):
        self.card_patch()
        install = ForgeInstall(root=self.tmp, jar=self.tmp / "forge-gui-desktop-9.9-jar-with-dependencies.jar",
                               res=self.tmp / "res", workdir=self.tmp)
        with mock.patch.object(forge, "load_patches", return_value=forge.load_patches(self.patch_dir)):
            record, err = self._execute(install, self.tmp / "run", quiet=True)
            self.assertEqual("", err)
            self.assertEqual("not-managed", record["patches"]["state"])
            _record, err = self._execute(install, self.tmp / "run2", quiet=False)
            self.assertIn("note: this Forge was not built by `mtgsim setup --build`", err)


class ShippedPatchesTest(unittest.TestCase):
    def test_every_shipped_patch_is_named_and_documented(self):
        for patch in forge.load_patches():
            with self.subTest(patch=patch.name):
                self.assertRegex(patch.name, r"^\d{4}-[a-z0-9][a-z0-9.-]*\.patch$")
                description = patch.description
                for field in ("Subject:", "Why:", "Measured:"):
                    self.assertRegex(description, rf"(?m)^{field}\s*\S", f"{patch.name} needs a {field} line")
                for line in description.splitlines():
                    self.assertFalse(re.match(r"(diff |--- |\+\+\+ |@@)", line), f"{patch.name}: {line!r}")

    def test_the_folder_ships_with_the_package(self):
        self.assertTrue((forge.PATCH_DIR / "README.md").is_file())
        self.assertIn("*.patch -text", (forge.PATCH_DIR / ".gitattributes").read_text())
        pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
        self.assertIn('"forge_patches/*.patch"', pyproject)

    def test_combined_hash(self):
        self.assertEqual("", forge.combined_sha256([]))
        a = [{"name": "0001-a.patch", "sha256": "1" * 64}, {"name": "0002-b.patch", "sha256": "2" * 64}]
        self.assertNotEqual(forge.combined_sha256(a), forge.combined_sha256(a[::-1]), "order matters")
        self.assertEqual(forge.combined_sha256(a), forge.combined_sha256(list(a)))


if __name__ == "__main__":
    unittest.main()
