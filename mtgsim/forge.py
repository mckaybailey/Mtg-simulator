"""Locating, building and describing a Forge installation.

Two on-disk layouts are understood:

* a source checkout built with Maven (``forge-gui/res`` plus
  ``forge-gui-desktop/target/*-jar-with-dependencies.jar``), and
* an unpacked release (``res/`` next to ``forge-gui-desktop-*-jar-with-dependencies.jar``).

Everything mtgsim writes lives under ``MTGSIM_HOME`` (default ``~/.mtgsim``): the config file,
a source build of Forge if one was requested, the compiled Java driver, a private home
directory for Forge's own preferences, and the card database cache.

A source build made by ``setup --build`` also carries mtgsim's own changes to Forge: the
unified diffs in ``mtgsim/forge_patches/`` are applied on top of the pinned commit, and the
applied set is recorded in ``mtgsim-patches.json`` in the checkout (see "Forge patches" below).
A Forge the user supplies is never modified.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

FORGE_REPO_URL = "https://github.com/Card-Forge/forge"
# The Forge commit this version of mtgsim was developed and validated against.
FORGE_PINNED_REF = "7db198d72e04b396d09b8727a76ffcfaba145280"
MIN_JAVA = 17

BRIDGE_SOURCE = Path(__file__).resolve().parent / "bridge" / "ForgeBridge.java"
BRIDGE_MAIN_CLASS = "ForgeBridge"

PATCH_DIR = Path(__file__).resolve().parent / "forge_patches"
PATCH_MARKER = "mtgsim-patches.json"  # in the root of a Forge checkout built by mtgsim
PATCH_MARKER_FORMAT = 1
# Forge reads everything under forge-gui/res/ (card scripts, AI profiles, formats) from disk at
# startup; a patch that touches anything else changes compiled code and needs a Maven rebuild.
RUNTIME_PREFIX = "forge-gui/res/"


class ForgeError(RuntimeError):
    """A problem with the Forge installation or the Java toolchain, phrased for the user."""


def home_dir() -> Path:
    override = os.environ.get("MTGSIM_HOME")
    return Path(override).expanduser() if override else Path.home() / ".mtgsim"


def config_path() -> Path:
    return home_dir() / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class ForgeInstall:
    root: Path
    jar: Path
    res: Path
    workdir: Path  # the directory the JVM must run in: the one that contains res/

    @property
    def version(self) -> str:
        m = re.match(r"forge-gui-desktop-(.+)-jar-with-dependencies\.jar$", self.jar.name)
        return m.group(1) if m else self.jar.name

    @property
    def cardsfolder(self) -> Path:
        return self.res / "cardsfolder"

    def fingerprint(self) -> str:
        """Changes whenever the engine or its card data may have changed."""
        parts = [str(self.jar), str(self.jar.stat().st_mtime_ns), str(self.jar.stat().st_size)]
        for extra in (self.cardsfolder, self.res / "editions", self.res / "formats"):
            try:
                parts.append(str(extra.stat().st_mtime_ns))
            except OSError:
                parts.append("missing")
        zipped = self.cardsfolder / "cardsfolder.zip"
        if zipped.is_file():
            parts.append(str(zipped.stat().st_mtime_ns))
        # Patching a card script changes neither the jar nor the folder timestamps above, so the
        # applied patch set is part of the fingerprint (left out when none is applied, which keeps
        # the caches of an unpatched Forge valid).
        patches = applied_patch_key(self.root)
        if patches:
            parts.append("patches:" + patches)
        return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def detect_install(root: Path) -> ForgeInstall:
    """Recognise a Forge directory, or explain what is missing from it."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ForgeError(f"Forge directory does not exist: {root}")

    if (root / "forge-gui" / "res").is_dir():  # source checkout
        workdir = root / "forge-gui"
        jars = sorted((root / "forge-gui-desktop" / "target").glob("*-jar-with-dependencies.jar"))
        if not jars:
            raise ForgeError(
                f"{root} is a Forge source checkout that has not been built yet "
                "(no forge-gui-desktop/target/*-jar-with-dependencies.jar). "
                "Run `python -m mtgsim setup --build` or build it with Maven."
            )
    elif (root / "res").is_dir():  # unpacked release
        workdir = root
        jars = sorted(root.glob("*-jar-with-dependencies.jar"))
        if not jars:
            raise ForgeError(f"{root} has a res/ folder but no Forge *-jar-with-dependencies.jar next to it.")
    else:
        raise ForgeError(
            f"{root} does not look like Forge: expected either res/ (a release) "
            "or forge-gui/res (a source checkout)."
        )
    return ForgeInstall(root=root, jar=jars[-1], res=workdir / "res", workdir=workdir)


def find_install(explicit: Optional[str] = None) -> ForgeInstall:
    """Resolve the Forge installation: explicit path, then $MTGSIM_FORGE_DIR, then the saved config."""
    candidate = explicit or os.environ.get("MTGSIM_FORGE_DIR") or load_config().get("forge_dir")
    if not candidate:
        default = home_dir() / "forge"
        if default.is_dir():
            candidate = str(default)
    if not candidate:
        raise ForgeError(
            "Forge is not set up yet. Run `python -m mtgsim setup --build` to build it from source, "
            "or `python -m mtgsim setup --forge-dir PATH` to use an existing Forge installation."
        )
    return detect_install(Path(candidate))


# ------------------------------------------------------------------ toolchain


def _tool(name: str) -> Optional[str]:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        for suffix in ("", ".exe"):
            candidate = Path(java_home) / "bin" / (name + suffix)
            if candidate.is_file():
                return str(candidate)
    return shutil.which(name)


def java_path() -> str:
    path = _tool("java")
    if not path:
        raise ForgeError(f"Java was not found. Install a JDK {MIN_JAVA} or newer and make sure `java` is on PATH.")
    return path


def java_major_version(java: Optional[str] = None) -> int:
    out = subprocess.run([java or java_path(), "-version"], capture_output=True, text=True)
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out.stderr + out.stdout)
    if not m:
        raise ForgeError("Could not read the Java version from `java -version`.")
    major = int(m.group(1))
    if major == 1 and m.group(2):  # "1.8.0" style
        major = int(m.group(2))
    return major


def check_java() -> int:
    major = java_major_version()
    if major < MIN_JAVA:
        raise ForgeError(f"Forge needs Java {MIN_JAVA} or newer, but `java` is version {major}.")
    return major


# --------------------------------------------------------------------- bridge


def bridge_dir(install: ForgeInstall) -> Path:
    key = hashlib.sha1()
    key.update(install.fingerprint().encode())
    key.update(BRIDGE_SOURCE.read_bytes())
    return home_dir() / "bridge" / key.hexdigest()[:12]


def ensure_bridge(install: ForgeInstall, force: bool = False) -> Path:
    """Compile the Java driver against this Forge jar (once) and return the class directory."""
    out = bridge_dir(install)
    marker = out / (BRIDGE_MAIN_CLASS + ".class")
    if marker.is_file() and not force:
        return out
    javac = _tool("javac")
    if not javac:
        raise ForgeError(
            "`javac` was not found. mtgsim compiles a small driver against Forge, which needs a full JDK "
            f"({MIN_JAVA}+), not just a Java runtime."
        )
    check_java()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    proc = subprocess.run(
        [javac, "-nowarn", "-encoding", "UTF-8", "-cp", str(install.jar), "-d", str(out), str(BRIDGE_SOURCE)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not marker.is_file():
        shutil.rmtree(out, ignore_errors=True)
        raise ForgeError(
            "The mtgsim driver did not compile against this Forge version "
            f"({install.version}). mtgsim is validated against Forge commit {FORGE_PINNED_REF[:10]}; "
            "`python -m mtgsim setup --build` builds exactly that version.\n" + proc.stderr.strip()[-2000:]
        )
    return out


def forge_user_home() -> Path:
    """A private home directory for Forge, so simulations never read or write a real Forge profile."""
    path = home_dir() / "forge-home"
    path.mkdir(parents=True, exist_ok=True)
    return path


def java_command(install: ForgeInstall, classes: Path, heap: str = "2g") -> list:
    sep = os.pathsep
    return [
        java_path(),
        f"-Xmx{heap}",
        "-Djava.awt.headless=true",
        f"-Duser.home={forge_user_home()}",
        "-Dfile.encoding=UTF-8",
        "-cp",
        f"{classes}{sep}{install.jar}",
        BRIDGE_MAIN_CLASS,
    ]


def java_env() -> dict:
    env = dict(os.environ)
    # On Windows Forge takes its profile location from these rather than from user.home.
    env["APPDATA"] = str(forge_user_home())
    env["LOCALAPPDATA"] = str(forge_user_home())
    return env


# ------------------------------------------------------------- Forge patches
#
# mtgsim's changes to Forge are unified diffs against FORGE_PINNED_REF in mtgsim/forge_patches/,
# applied in file-name order by `setup --build`. The checkout records what it carries in
# PATCH_MARKER, a JSON file:
#
#   format       PATCH_MARKER_FORMAT
#   state        "applied", or "applying" while files are being changed (an interrupted setup
#                leaves it there, and the next one starts over)
#   forge_ref    the commit the patches were applied to
#   disabled     true when built with --no-patches
#   patches      [{name, sha256, paths, code}] in order; `code` is true when the patch touches
#                anything outside forge-gui/res/
#   combined_sha256  hash of the names and hashes in order ("" for no patches)
#   files        every path that may differ from forge_ref -> the git blob it should have once
#                patched (null: the file must not exist). Restoring these paths from forge_ref
#                takes all patches off again, including files a patch created.
#   jar          {ref, code_patches} the Forge jar was last built from, or null before the first
#                build; a Maven rebuild is due exactly when this differs from the current
#                ref and code patches.


@dataclass(frozen=True)
class ForgePatch:
    """One patch file shipped with mtgsim."""

    name: str
    path: Path
    sha256: str

    @property
    def description(self) -> str:
        """The free text above the first ``diff --git`` line (``git apply`` skips it)."""
        lines = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("diff --git "):
                break
            lines.append(line)
        return "\n".join(lines).strip()

    def entry(self) -> dict:
        return {"name": self.name, "sha256": self.sha256}


def load_patches(folder: Optional[Path] = None) -> List[ForgePatch]:
    """The patches shipped in ``folder`` (default: mtgsim/forge_patches), in the order they apply."""
    folder = PATCH_DIR if folder is None else Path(folder)
    if not folder.is_dir():
        return []
    return [
        ForgePatch(path.name, path, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(folder.glob("*.patch"), key=lambda p: p.name)
    ]


def combined_sha256(entries: Iterable[dict]) -> str:
    """One hash for an ordered patch set: names and contents. Empty for no patches."""
    entries = list(entries)
    if not entries:
        return ""
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(f"{entry['name']}\0{entry['sha256']}\n".encode("utf-8"))
    return digest.hexdigest()


def read_patch_marker(root: Path) -> Optional[dict]:
    """The patch record of a Forge checkout, or None if mtgsim never patched it."""
    path = Path(root) / PATCH_MARKER
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("patches"), list) or not isinstance(data.get("files"), dict):
        # Damaged (edited by hand?): unknown state, so treat it as an interrupted apply.
        return {"format": PATCH_MARKER_FORMAT, "state": "damaged", "forge_ref": "", "disabled": False,
                "patches": [], "combined_sha256": "", "files": {}, "jar": None}
    return data


def _write_marker(root: Path, marker: dict) -> None:
    marker = dict(marker, format=PATCH_MARKER_FORMAT)
    marker["combined_sha256"] = combined_sha256(_entries(marker))
    path = Path(root) / PATCH_MARKER
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(marker, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _entries(marker: dict) -> List[dict]:
    return [{"name": p["name"], "sha256": p["sha256"]} for p in marker.get("patches", [])]


def _jar_key(marker: dict) -> dict:
    """What the jar must have been built from for this checkout: its commit and its code patches."""
    return {
        "ref": marker.get("forge_ref", ""),
        "code_patches": [{"name": p["name"], "sha256": p["sha256"]} for p in marker.get("patches", []) if p.get("code")],
    }


def applied_patch_key(root: Path) -> str:
    """A short key for the patches applied to a checkout ("" when none), for cache names."""
    marker = read_patch_marker(root)
    if marker is None:
        return ""
    key = marker.get("combined_sha256") or ""
    if marker.get("state") != "applied":
        key = "incomplete:" + key
    return key[:24]


def _checkout_head(root: Path) -> str:
    """The commit a detached checkout is at, read without git ("" if it cannot be told)."""
    try:
        text = (Path(root) / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if re.fullmatch(r"[0-9a-f]{40}", text) else ""


def _default_build_without_marker(root: Path) -> bool:
    """A checkout `setup --build` made before patches were tracked: mtgsim's to patch."""
    try:
        default = (home_dir() / "forge").resolve()
    except OSError:
        return False
    return Path(root).resolve() == default and (default / ".git").is_dir()


@dataclass
class PatchStatus:
    """How the Forge patches on an installation compare with the ones this mtgsim ships."""

    state: str  # "up-to-date" | "out-of-date" | "disabled" | "not-managed"
    applied: List[dict] = field(default_factory=list)  # [{name, sha256}] in order
    shipped: List[dict] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)  # why it is out of date

    @property
    def combined(self) -> str:
        return combined_sha256(self.applied)

    def record(self) -> dict:
        """What run.json stores, so every result can be traced to the Forge it was played on."""
        return {"state": self.state, "applied": list(self.applied), "combined_sha256": self.combined}

    def summary(self) -> str:
        """One line for `setup` and `doctor`."""
        n = len(self.applied)
        names = f" ({', '.join(e['name'] for e in self.applied)}; combined {self.combined[:12]})" if n else ""
        if self.state == "up-to-date":
            if not n:
                return "Forge patches: none (mtgsim ships no Forge patches)"
            return f"Forge patches: {n} applied, up to date{names}"
        if self.state == "out-of-date":
            return (f"Forge patches: OUT OF DATE, {n} applied, mtgsim ships {len(self.shipped)}: "
                    + "; ".join(self.problems) + ". Run `python -m mtgsim setup --build` to update.")
        if self.state == "disabled":
            return f"Forge patches: none applied (built with --no-patches; mtgsim ships {len(self.shipped)})"
        if not self.shipped:
            return "Forge patches: none (mtgsim ships no Forge patches)"
        return (f"Forge patches: not applied; mtgsim only patches a Forge it builds with `setup --build` "
                f"(it ships {len(self.shipped)})")

    def warning(self) -> Optional[str]:
        """A note for stderr before games are played on a Forge that lacks the shipped patches."""
        if self.state == "out-of-date":
            return ("warning: Forge's patches are out of date (" + "; ".join(self.problems) + "), so results "
                    "will differ from a current install. Run `python -m mtgsim setup --build` to update.")
        if self.state in ("disabled", "not-managed") and self.shipped:
            why = "was built with --no-patches" if self.state == "disabled" else "was not built by `mtgsim setup --build`"
            return (f"note: this Forge {why}, so mtgsim's {len(self.shipped)} Forge patch(es) "
                    "(fixes to Forge's AI and card scripts) are not applied.")
        return None


def patch_status(install, patches: Optional[Sequence[ForgePatch]] = None, verify: bool = False) -> PatchStatus:
    """Compare a Forge installation's applied patches with the shipped ones.

    ``install`` is a ForgeInstall or a checkout root. Only the marker file is read, so this is
    cheap enough to run before every command; ``verify`` also checks with git that the patched
    files still hold what the patches put there (for `doctor`)."""
    root = install.root if isinstance(install, ForgeInstall) else Path(install)
    shipped = [p.entry() for p in (load_patches() if patches is None else patches)]
    marker = read_patch_marker(root)
    if marker is None:
        if not _default_build_without_marker(root):
            return PatchStatus("not-managed", [], shipped)
        marker = {"state": "applied", "forge_ref": _checkout_head(root), "patches": [], "files": {},
                  "jar": {"ref": _checkout_head(root), "code_patches": []}}
    applied = _entries(marker)
    problems: List[str] = []
    if marker.get("state") == "damaged":
        problems.append(f"its patch record {PATCH_MARKER} is unreadable")
    elif marker.get("state") != "applied":
        problems.append("an earlier `setup --build` stopped while changing patched files")
    elif not marker.get("disabled") and applied != shipped:
        have = {e["name"]: e["sha256"] for e in applied}
        want = {e["name"]: e["sha256"] for e in shipped}
        missing = [n for n in want if n not in have]
        extra = [n for n in have if n not in want]
        changed = [n for n in want if n in have and have[n] != want[n]]
        if missing:
            problems.append("not applied: " + ", ".join(missing))
        if extra:
            problems.append("applied but no longer shipped: " + ", ".join(extra))
        if changed:
            problems.append("changed since applied: " + ", ".join(changed))
        if not (missing or extra or changed):
            problems.append("applied in a different order")
    head = _checkout_head(root)
    if head and marker.get("forge_ref") and head != marker.get("forge_ref"):
        problems.append(f"the checkout moved from {marker['forge_ref'][:10]} to {head[:10]} after patching")
    if marker.get("state") == "applied" and marker.get("jar") != _jar_key(marker):
        problems.append("Forge was not rebuilt after its Java code was patched (did the Maven build fail?)")
    if verify and marker.get("state") == "applied" and shutil.which("git"):
        modified = _modified_files(root, marker.get("files", {}))
        if modified:
            shown = ", ".join(modified[:3]) + (" ..." if len(modified) > 3 else "")
            problems.append(f"{len(modified)} patched file(s) were changed by hand: {shown}")
    if problems:
        return PatchStatus("out-of-date", applied, shipped, problems)
    return PatchStatus("disabled" if marker.get("disabled") else "up-to-date", applied, shipped)


def patches_for_run(install, run_json: Path, quiet: bool = False) -> dict:
    """The patch record for a run's run.json; warns on stderr when it is not what mtgsim ships,
    or when a resumed run continues on a different patch set than it started with."""
    status = patch_status(install)
    record = status.record()
    if quiet:
        return record
    message = status.warning()
    if message:
        print(message, file=sys.stderr)
    try:
        before = json.loads(Path(run_json).read_text(encoding="utf-8")).get("forge", {}).get("patches")
    except (OSError, ValueError, AttributeError):
        before = None
    if isinstance(before, dict) and before.get("combined_sha256") != record["combined_sha256"]:
        old = before.get("combined_sha256") or "none"
        new = record["combined_sha256"] or "none"
        print(f"warning: this run was started on Forge patch set {old[:12]} and continues on {new[:12]}; "
              "its games come from two different engines.", file=sys.stderr)
    return record


# Git plumbing for the patches. Paths are passed literally (GIT_LITERAL_PATHSPECS), never as globs.


def _git(root: Path, *args: str, env: Optional[dict] = None, input: Optional[str] = None,
         check: bool = True) -> subprocess.CompletedProcess:
    full_env = dict(os.environ, GIT_LITERAL_PATHSPECS="1", **(env or {}))
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, env=full_env, input=input,
                          encoding="utf-8", errors="surrogateescape")
    if check and proc.returncode != 0:
        raise ForgeError(f"`git {' '.join(args[:3])}` failed in {root}:\n{(proc.stderr or proc.stdout).strip()[-2000:]}")
    return proc


def _git_head(root: Path) -> str:
    return _git(root, "rev-parse", "--verify", "-q", "HEAD", check=False).stdout.strip()


def _index_snapshot(root: Path, env: dict) -> Dict[str, str]:
    """path -> "mode blob" for every entry of the index named in ``env``."""
    out = _git(root, "ls-files", "-s", "-z", env=env).stdout
    snapshot = {}
    for item in out.split("\0"):
        if item:
            meta, path = item.split("\t", 1)
            mode, blob, _stage = meta.split(" ")
            snapshot[path] = f"{mode} {blob}"
    return snapshot


def _plan_patches(root: Path, patches: Sequence[ForgePatch]) -> tuple:
    """Apply the series to a scratch index built from HEAD, touching nothing in the checkout.

    Returns ([{name, sha256, paths, code}], {path: expected blob or None}). A patch that does
    not apply on top of the ones before it raises ForgeError naming it."""
    entries: List[dict] = []
    files: Dict[str, Optional[str]] = {}
    if not patches:
        return entries, files
    with tempfile.TemporaryDirectory(prefix="mtgsim-patch-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(root, "read-tree", "HEAD", env=env)
        before = _index_snapshot(root, env)
        for i, patch in enumerate(patches):
            proc = _git(root, "apply", "--cached", "--whitespace=nowarn", str(patch.path), env=env, check=False)
            if proc.returncode != 0:
                raise ForgeError(_not_applying(root, patch, patches[:i], proc.stderr or proc.stdout))
            after = _index_snapshot(root, env)
            paths = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
            if not paths:
                raise ForgeError(_not_applying(root, patch, patches[:i], "it changes nothing"))
            entries.append(dict(patch.entry(), paths=paths, code=any(not p.startswith(RUNTIME_PREFIX) for p in paths)))
            before = after
        for entry in entries:
            for path in entry["paths"]:
                files[path] = before[path].split(" ")[1] if path in before else None
    return entries, files


def _not_applying(root: Path, patch: ForgePatch, earlier: Sequence[ForgePatch], detail: str) -> str:
    head = _git_head(root)
    after = f" on top of {', '.join(p.name for p in earlier)}" if earlier else ""
    return (f"The Forge patch {patch.name} does not apply to Forge {head[:10] or '(unknown commit)'}{after}, "
            f"so nothing in {root} was changed. Remake it against this commit or remove it "
            f"(see {PATCH_DIR / 'README.md'}).\ngit said: {detail.strip()[-1500:]}")


def _modified_files(root: Path, files: Dict[str, Optional[str]]) -> List[str]:
    """Paths whose content differs from what the applied patches put there."""
    present = [p for p, blob in files.items() if blob is not None and (Path(root) / p).is_file()]
    hashes: Dict[str, str] = {}
    if present:
        out = _git(root, "hash-object", "--stdin-paths", input="\n".join(present) + "\n").stdout.split()
        hashes = dict(zip(present, out))
    modified = []
    for path, blob in sorted(files.items()):
        if blob is None:
            if os.path.lexists(Path(root) / path):
                modified.append(path)
        elif hashes.get(path) != blob:
            modified.append(path)
    return modified


def _restore(root: Path, paths: Iterable[str]) -> None:
    """Put these paths back as they are at HEAD; delete the ones HEAD does not have."""
    paths = sorted(set(paths))
    if not paths:
        return
    out = _git(root, "cat-file", "--batch-check", input="".join(f"HEAD:{p}\n" for p in paths)).stdout.splitlines()
    tracked = [p for p, line in zip(paths, out) if not line.endswith(" missing")]
    added = [p for p in paths if p not in set(tracked)]
    for i in range(0, len(tracked), 200):
        _git(root, "checkout", "-q", "HEAD", "--", *tracked[i:i + 200])
    for i in range(0, len(added), 200):  # also drops `git add -N` entries left from making a patch
        _git(root, "rm", "-q", "--cached", "--ignore-unmatch", "--", *added[i:i + 200])
    top = Path(root).resolve()
    for path in added:
        target = top / path
        if target.is_file() or target.is_symlink():
            target.unlink()
        parent = target.parent
        while parent != top and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def sync_patches(root: Path, patches: Sequence[ForgePatch], say: Callable[[str], None] = print,
                 disabled: bool = False) -> bool:
    """Make the checkout carry exactly ``patches`` on top of its HEAD. Returns True if files changed.

    The new series is tried on a scratch index first, so a patch that does not apply leaves the
    checkout as it was. Otherwise every path touched by the old or the new series is restored to
    HEAD and the whole series is applied again with `git apply`."""
    root = Path(root)
    head = _git_head(root)
    marker = read_patch_marker(root) or {"state": "applied", "forge_ref": head, "patches": [], "files": {}, "jar": None}
    wanted = [p.entry() for p in patches]
    if (marker.get("state") == "applied" and marker.get("forge_ref") == head and _entries(marker) == wanted
            and bool(marker.get("disabled")) == disabled):
        modified = _modified_files(root, marker.get("files", {}))
        if not modified:
            if wanted:
                say(f"Forge patches unchanged: {len(wanted)} applied.")
            return False
        say(f"{len(modified)} patched Forge file(s) were changed since the patches were applied; restoring them.")

    entries, files = _plan_patches(root, patches)
    old_paths = set(marker.get("files", {}))
    if marker.get("state") == "damaged":
        # No record of what was changed: restore every tracked file that differs from HEAD.
        diff = _git(root, "diff", "--name-only", "-z", "--no-renames", "HEAD").stdout
        old_paths.update(p for p in diff.split("\0") if p)
    marker = dict(marker, state="applying", forge_ref=head, disabled=disabled, patches=entries,
                  files={p: None for p in sorted(old_paths | set(files))})
    _write_marker(root, marker)
    _restore(root, old_paths | set(files))
    if patches:
        say(f"Applying {len(patches)} Forge patch(es): {', '.join(p.name for p in patches)}")
        proc = _git(root, "apply", "--whitespace=nowarn", *[str(p.path) for p in patches], check=False)
        if proc.returncode != 0:
            _restore(root, files)
            _write_marker(root, dict(marker, state="applied", patches=[], files={}))
            raise ForgeError(f"Applying the Forge patches failed, so none are applied:\n{proc.stderr.strip()[-2000:]}")
    elif old_paths:
        say("Removed mtgsim's Forge patches" + (" (--no-patches)." if disabled else "."))
    _write_marker(root, dict(marker, state="applied", files=files))
    return True


# ---------------------------------------------------------------------- build


def _find_jar(root: Path) -> Optional[Path]:
    jars = sorted((Path(root) / "forge-gui-desktop" / "target").glob("*-jar-with-dependencies.jar"))
    return jars[-1] if jars else None


def build_from_source(
    dest: Optional[Path] = None,
    ref: str = FORGE_PINNED_REF,
    say: Callable[[str], None] = print,
    patches: Optional[Sequence[ForgePatch]] = None,
    apply_patches: bool = True,
) -> ForgeInstall:
    """Fetch one Forge commit, apply mtgsim's patches to it and build the desktop jar with Maven.

    Re-running it is cheap: the patches are re-applied only when the shipped set changed, and
    Maven runs only when the jar was not yet built from this commit and these code patches
    (patches confined to forge-gui/res/ take effect without a rebuild)."""
    dest = Path(dest).expanduser().resolve() if dest else home_dir() / "forge"
    if not shutil.which("git"):
        raise ForgeError(f"`git` was not found; building Forge from source needs git, Maven and a JDK {MIN_JAVA}+.")

    if not (dest / ".git").is_dir():
        if dest.exists() and any(dest.iterdir()):
            raise ForgeError(f"{dest} already exists and is not a git checkout; choose another --dest.")
        dest.mkdir(parents=True, exist_ok=True)
        _run(["git", "init", "-q"], dest)
        _run(["git", "remote", "add", "origin", FORGE_REPO_URL], dest)

    head = _git_head(dest)
    marker = read_patch_marker(dest)
    if marker is None:
        # Never patched (or built before patches were tracked): its jar, if any, is plain `head`.
        marker = {"state": "applied", "forge_ref": head, "disabled": False, "patches": [], "files": {},
                  "jar": {"ref": head, "code_patches": []} if head and _find_jar(dest) else None}
        _write_marker(dest, marker)

    if head != ref:
        say(f"Fetching Forge {ref[:10]} (about 800 MB, this takes a few minutes)...")
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
        _run(["git", "fetch", "-q", "--depth", "1", "origin", ref], dest, env=env)
        if head:
            _restore(dest, marker.get("files", {}))  # take the old patches off before switching
        _run(["git", "checkout", "-q", "--force", "FETCH_HEAD"], dest, env=env)
        marker = dict(marker, state="applied", forge_ref=_git_head(dest), patches=[], files={})
        _write_marker(dest, marker)

    wanted = (load_patches() if patches is None else list(patches)) if apply_patches else []
    changed = sync_patches(dest, wanted, say=say, disabled=not apply_patches)
    marker = read_patch_marker(dest)
    key = _jar_key(marker)
    built = marker.get("jar")
    if _find_jar(dest) and built == key:
        if changed:
            say(f"No Maven rebuild needed: the jar was already built from this commit with these code "
                f"patches, and files under {RUNTIME_PREFIX} are read when Forge starts.")
        return detect_install(dest)

    if _find_jar(dest) is None or built is None:
        say("Building Forge with Maven (a few minutes; downloads its dependencies on the first run)...")
    else:
        say("Rebuilding Forge with Maven, because the Forge commit or the patches to its Java code "
            "changed (a few minutes)...")
    _maven_build(dest)
    _write_marker(dest, dict(read_patch_marker(dest), jar=key))
    return detect_install(dest)


def _maven_build(dest: Path) -> None:
    if not shutil.which("mvn"):
        raise ForgeError(f"`mvn` was not found; building Forge from source needs git, Maven and a JDK {MIN_JAVA}+.")
    check_java()
    # Start from empty build directories so no class or resource from an earlier patch set can
    # survive in the jar. (Deleting them here rather than with `mvn clean` avoids needing
    # maven-clean-plugin, which a plain `package` build never downloads.) A JVM that still has
    # the old jar open keeps reading its deleted copy.
    for module in [dest, *(pom.parent for pom in dest.glob("*/pom.xml"))]:
        shutil.rmtree(module / "target", ignore_errors=True)
    log = dest / "mtgsim-build.log"
    with open(log, "w", encoding="utf-8") as fh:
        proc = subprocess.run(
            ["mvn", "-B", "-pl", "forge-gui-desktop", "-am", "package", "-DskipTests", "-Dcheckstyle.skip=true"],
            cwd=dest,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:])
        raise ForgeError(f"The Forge build failed (full log: {log}):\n{tail}")


def _run(cmd: list, cwd: Path, env: Optional[dict] = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise ForgeError(f"`{' '.join(cmd)}` failed:\n{(proc.stderr or proc.stdout).strip()[-2000:]}")
