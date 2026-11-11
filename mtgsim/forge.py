"""Locating, building and describing a Forge installation.

Two on-disk layouts are understood:

* a source checkout built with Maven (``forge-gui/res`` plus
  ``forge-gui-desktop/target/*-jar-with-dependencies.jar``), and
* an unpacked release (``res/`` next to ``forge-gui-desktop-*-jar-with-dependencies.jar``).

Everything mtgsim writes lives under ``MTGSIM_HOME`` (default ``~/.mtgsim``): the config file,
a source build of Forge if one was requested, the compiled Java driver, a private home
directory for Forge's own preferences, and the card database cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

FORGE_REPO_URL = "https://github.com/Card-Forge/forge"
# The Forge commit this version of mtgsim was developed and validated against.
FORGE_PINNED_REF = "7db198d72e04b396d09b8727a76ffcfaba145280"
MIN_JAVA = 17

BRIDGE_SOURCE = Path(__file__).resolve().parent / "bridge" / "ForgeBridge.java"
BRIDGE_MAIN_CLASS = "ForgeBridge"


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


# ---------------------------------------------------------------------- build


def build_from_source(
    dest: Optional[Path] = None,
    ref: str = FORGE_PINNED_REF,
    say: Callable[[str], None] = print,
) -> ForgeInstall:
    """Fetch one Forge commit and build the desktop jar with Maven."""
    dest = Path(dest).expanduser().resolve() if dest else home_dir() / "forge"
    for tool in ("git", "mvn"):
        if not shutil.which(tool):
            raise ForgeError(f"`{tool}` was not found; building Forge from source needs git, Maven and a JDK {MIN_JAVA}+.")
    check_java()

    if not (dest / ".git").is_dir():
        if dest.exists() and any(dest.iterdir()):
            raise ForgeError(f"{dest} already exists and is not a git checkout; choose another --dest.")
        dest.mkdir(parents=True, exist_ok=True)
        _run(["git", "init", "-q"], dest)
        _run(["git", "remote", "add", "origin", FORGE_REPO_URL], dest)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True).stdout.strip()
    if head != ref:
        say(f"Fetching Forge {ref[:10]} (about 800 MB, this takes a few minutes)...")
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
        _run(["git", "fetch", "-q", "--depth", "1", "origin", ref], dest, env=env)
        _run(["git", "checkout", "-q", "--force", "FETCH_HEAD"], dest, env=env)

    try:
        return detect_install(dest)  # already built
    except ForgeError:
        pass

    say("Building Forge with Maven (a few minutes; downloads its dependencies on the first run)...")
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
    return detect_install(dest)


def _run(cmd: list, cwd: Path, env: Optional[dict] = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise ForgeError(f"`{' '.join(cmd)}` failed:\n{(proc.stderr or proc.stdout).strip()[-2000:]}")
