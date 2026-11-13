"""Forge AI profiles: Forge's own, the ones mtgsim ships, the user's, and ones a run generates.

Forge steers its AI with personality profiles ("Default", "Cautious", ...): ``res/ai/<name>.ai``,
one ``KEY=value`` line per setting, where KEY is a member of Forge's ``AiProps`` enum. Forge loads
every profile in that folder once, when the JVM starts.

mtgsim never writes into Forge's folder. Every run gets a profile folder of its own,
``RUN_DIR/ai``, holding

1. Forge's built-in profiles, copied unchanged;
2. profiles shipped with mtgsim (``mtgsim/profiles/*.ai|*.json``);
3. the user's profiles (``MTGSIM_HOME/profiles/*.ai|*.json``);
4. profiles the run generated (``tune`` writes its candidates here),

and the Java driver is started with ``-Dmtgsim.aiProfileDir=RUN_DIR/ai`` (see ``forge.java_command``)
so Forge loads that folder instead of its own.

A profile in 2. or 3. is either a complete Forge ``.ai`` file, copied as it is, or a ``.json`` file
``{"base": "Default", "overrides": {"KEY": value, ...}, "note": "..."}``, written out as a full copy
of the base profile with those settings replaced. A setting missing from a Forge profile falls back
to the enum's built-in default, not to Default.ai's value (Default.ai sets
CHANCE_TO_ATTACK_INTO_TRADE=0, the enum default is 40), which is why a generated profile is always a
complete copy of its base rather than a list of changes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

from . import forge
from .forge import ForgeError, ForgeInstall

SHIPPED_DIR = Path(__file__).resolve().parent / "profiles"
EXT = ".ai"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
AIPROPS_SOURCE = Path("forge-ai") / "src" / "main" / "java" / "forge" / "ai" / "AiProps.java"


class ProfileError(ForgeError):
    """A profile that cannot be used as written; the message is meant for the user."""


def user_dir() -> Path:
    return forge.home_dir() / "profiles"


def builtin_dir(install: ForgeInstall) -> Path:
    return install.res / "ai"


# ------------------------------------------------------------------ file format


def parse(text: str) -> Dict[str, str]:
    """The settings Forge reads from a profile file, following ``AiProfileUtil.loadProfile`` exactly.

    Forge splits each line on "=" (Java's ``String.split``, which drops trailing empty parts) and
    keeps it only when that gives exactly two parts, or one part and the line ends with "=". Lines
    starting with "#" and empty lines are skipped; nothing is trimmed. A later line for the same key
    wins.
    """
    settings: Dict[str, str] = {}
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        parts = line.split("=")
        while len(parts) > 1 and parts[-1] == "":
            parts.pop()
        if len(parts) == 2:
            settings[parts[0]] = parts[1]
        elif len(parts) == 1 and line.endswith("="):
            settings[parts[0]] = ""
    return settings


def format_value(value) -> str:
    """A setting's value as Forge expects it: booleans as true/false, whole numbers without a decimal point."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != int(value):
            raise ProfileError(f"AI settings are whole numbers, not {value!r}")
        return str(int(value))
    if not isinstance(value, str):
        raise ProfileError(f"an AI setting must be a string, number or true/false, not {value!r}")
    if value != value.strip() or any(c in value for c in "=\t\r\n"):
        # Forge would split on "=" and silently drop the line, or fail to parse a padded number.
        raise ProfileError(f"AI setting value {value!r} may not contain '=', tabs, newlines or surrounding spaces")
    return value


def check_key(key: str, known: Optional[Set[str]] = None) -> str:
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise ProfileError(f"{key!r} is not an AI setting name (expected UPPER_CASE like PLAY_AGGRO)")
    if known is not None and key not in known:
        raise ProfileError(f"unknown AI setting {key}: this Forge version's AiProps has no such key")
    return key


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ProfileError(f"{name!r} is not a usable profile name (letters, digits and _.+- only, at most 64)")
    return name


def apply_overrides(base_text: str, overrides: Mapping[str, str], header: Iterable[str] = ()) -> str:
    """The base profile's text with some settings replaced (or added at the end when the base lacks them)."""
    out: List[str] = [f"# {h}" for h in header]
    done: set = set()
    for line in base_text.split("\n"):
        line = line.rstrip("\r")
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            if key in overrides:
                if key not in done:  # later duplicates of an overridden key would win in Forge: drop them
                    out.append(f"{key}={overrides[key]}")
                    done.add(key)
                continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    added = sorted(k for k in overrides if k not in done)
    if added:
        out += ["", "# Added by mtgsim (not in the base profile)"] + [f"{k}={overrides[k]}" for k in added]
    return "\n".join(out) + "\n"


def effective(text: str, defaults: Optional[Mapping[str, Optional[str]]] = None) -> Dict[str, str]:
    """What the AI will actually use: the file's settings, with Forge's enum defaults where a key is
    missing or empty (``AiProfileUtil.getProperty`` treats an empty value as unset)."""
    settings = {k: v for k, v in parse(text).items() if v != ""}
    for key, value in (defaults or {}).items():
        if key not in settings and value is not None:
            settings[key] = value
    return settings


def settings_hash(text: str, defaults: Optional[Mapping[str, Optional[str]]] = None) -> str:
    """Identifies what a profile does: profiles with the same effective settings hash alike, whatever
    their comments, order, or whether they spell out a value that equals Forge's default."""
    items = sorted(effective(text, defaults).items())
    return hashlib.sha256(json.dumps(items, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def known_settings(install: ForgeInstall) -> Tuple[Dict[str, Optional[str]], bool]:
    """AI setting names this Forge understands with their enum defaults, and whether the list is exact.

    A source checkout has ``AiProps.java``, which gives the exact list and every default. A release
    only has the profiles, so the union of their keys is used (defaults unknown); a key outside it
    may still be valid, and the driver reports a truly unknown key when it starts.
    """
    source = Path(install.root) / AIPROPS_SOURCE
    if source.is_file():
        found = parse_aiprops(source.read_text(encoding="utf-8", errors="replace"))
        if found:
            return found, True
    keys: Dict[str, Optional[str]] = {}
    for path in sorted(builtin_dir(install).glob("*" + EXT)):
        for key in parse(path.read_text(encoding="utf-8", errors="replace")):
            keys[key] = None
    return keys, False


def known_keys(install: ForgeInstall) -> Tuple[Set[str], bool]:
    found, exact = known_settings(install)
    return set(found), exact


def parse_aiprops(java_source: str) -> Dict[str, Optional[str]]:
    """Enum constants of ``AiProps.java`` and their default values (``NAME ("default")``)."""
    body = java_source.split("enum AiProps", 1)[-1]
    body = re.sub(r"//[^\n]*|/\*.*?\*/", "", body, flags=re.S)
    body = body.split(";", 1)[0]  # the constants end at the first semicolon
    return {m.group(1): m.group(2) for m in re.finditer(r"\b([A-Z][A-Z0-9_]*)\s*\(\s*\"([^\"]*)\"\s*\)", body)}


# ---------------------------------------------------------------- the library


@dataclass(frozen=True)
class Source:
    name: str
    kind: str  # "forge", "mtgsim" or "user"
    path: Path


def library(install: ForgeInstall, extra_dirs: Optional[List[Tuple[str, Path]]] = None) -> Dict[str, Source]:
    """Every named profile available to a run: Forge's, then mtgsim's, then the user's.

    A name may only be defined once; a shipped or user profile with the name of a Forge profile would
    silently change what that name means for every run, so it is an error.
    """
    found: Dict[str, Source] = {}
    for path in sorted(builtin_dir(install).glob("*" + EXT)):
        found[path.stem] = Source(path.stem, "forge", path)
    dirs = extra_dirs if extra_dirs is not None else [("mtgsim", SHIPPED_DIR), ("user", user_dir())]
    for kind, folder in dirs:
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix not in (EXT, ".json") or not path.is_file():
                continue
            name = check_name(path.stem)
            if name in found:
                raise ProfileError(f"AI profile \"{name}\" is defined twice: {found[name].path} and {path}")
            found[name] = Source(name, kind, path)
    return found


def available(install: ForgeInstall) -> List[str]:
    return sorted(library(install))


def text_of(install: ForgeInstall, name: str, lib: Optional[Dict[str, Source]] = None, _depth: int = 0) -> str:
    """The complete Forge profile text for a named profile."""
    lib = library(install) if lib is None else lib
    source = lib.get(name)
    if source is None:
        raise ProfileError(f"unknown AI profile \"{name}\". Available: {', '.join(sorted(lib))}")
    if source.path.suffix == EXT:
        return source.path.read_text(encoding="utf-8", errors="replace")
    if _depth > 4:
        raise ProfileError(f"AI profile \"{name}\": too many levels of \"base\"")
    try:
        data = json.loads(source.path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ProfileError(f"{source.path} is not valid JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("overrides", {}), dict):
        raise ProfileError(f"{source.path} must be an object with \"base\" and \"overrides\"")
    base = str(data.get("base") or "Default")
    if base == name:
        raise ProfileError(f"AI profile \"{name}\" names itself as its base")
    known, exact = known_keys(install)
    overrides = {check_key(k, known if exact else None): format_value(v)
                 for k, v in data.get("overrides", {}).items()}
    base_text = text_of(install, base, lib, _depth + 1)
    header = [f"mtgsim profile {name}: {base} with {len(overrides)} setting(s) changed ({source.path.name})"]
    if data.get("note"):
        header.append(str(data["note"]).replace("\n", " "))
    return apply_overrides(base_text, overrides, header)


def build(install: ForgeInstall, base: str, overrides: Mapping[str, object], header: Iterable[str] = ()) -> str:
    """A complete profile: a named base with some settings replaced."""
    known, exact = known_keys(install)
    clean = {check_key(k, known if exact else None): format_value(v) for k, v in overrides.items()}
    return apply_overrides(text_of(install, base), clean, header)


def prepare_dir(install: ForgeInstall, dest: Path, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Fill a run's profile folder and return the settings hash of every profile in it.

    ``extra`` maps the names of run-generated profiles to their full text. The folder ends up holding
    exactly the library plus ``extra``; files from an earlier, different preparation are removed.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    lib = library(install)
    texts = {name: text_of(install, name, lib) for name in lib}
    for name, text in (extra or {}).items():
        check_name(name)
        if name in texts and texts[name] != text:
            raise ProfileError(f"generated AI profile \"{name}\" clashes with an existing profile of that name")
        texts[name] = text
    for stale in dest.glob("*" + EXT):
        if stale.stem not in texts:
            stale.unlink()
    for name, text in texts.items():
        path = dest / (name + EXT)
        if not path.is_file() or path.read_text(encoding="utf-8", errors="replace") != text:
            path.write_text(text, encoding="utf-8")
    defaults, _exact = known_settings(install)
    return {name: settings_hash(text, defaults) for name, text in texts.items()}
