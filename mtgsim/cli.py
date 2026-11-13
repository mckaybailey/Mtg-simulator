"""Command-line interface: ``python -m mtgsim <command>``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__, analysis, experiment, forge, legality
from .carddb import CardDatabase, load_database
from .decks import Deck, DeckIssue, find_deck_files, load_deck
from .experiment import Entrant, RunError, RunOptions
from .forge import ForgeError

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAUNTLET = REPO_ROOT / "decks" / "standard" / "meta"
MANIFEST_NAMES = ("gauntlet.json", "manifest.json")

AI_CAVEAT = (
    "Games are played by Forge's built-in AI on both sides. It plays aggro and midrange decks "
    "competently, control decks poorly and most combo decks badly, so results understate decks "
    "that need careful sequencing. Treat win rates as relative signals between similar decks, "
    "not as predictions of tournament results."
)


class UserError(RuntimeError):
    """Something the user needs to fix; printed without a traceback."""


# ------------------------------------------------------------------ helpers


def _pct(value: Optional[float], digits: int = 1) -> str:
    return "  -  " if value is None else f"{value * 100:.{digits}f}%"


def _ci(ci: Sequence[Optional[float]]) -> str:
    if not ci or ci[0] is None:
        return "-"
    return f"{ci[0] * 100:.0f}-{ci[1] * 100:.0f}%"


def _num(value: Optional[float], digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _table(headers: List[str], rows: List[List[str]], right: Sequence[int] = ()) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    def fmt(row: List[str]) -> str:
        cells = [c.rjust(widths[i]) if i in right else c.ljust(widths[i]) for i, c in enumerate(row)]
        return "  ".join(cells).rstrip()
    lines = [fmt(headers), "  ".join("-" * w for w in widths)]
    lines += [fmt(r) for r in rows]
    return "\n".join(lines)


class Context:
    """Lazily resolved Forge installation, card database and format for one command."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self._install: Optional[forge.ForgeInstall] = None
        self._db: Optional[CardDatabase] = None

    @property
    def install(self) -> forge.ForgeInstall:
        if self._install is None:
            self._install = forge.find_install(getattr(self.args, "forge_dir", None))
        return self._install

    @property
    def db(self) -> CardDatabase:
        if self._db is None:
            self._db = load_database(self.install)
        return self._db

    @property
    def format(self) -> Optional[legality.Format]:
        try:
            return legality.get_format(self.install.res, getattr(self.args, "format", None))
        except ValueError as exc:
            raise UserError(str(exc))


def _read_manifest(folder: Path) -> Dict[str, dict]:
    """Optional per-folder metadata (display name, archetype, metagame share) keyed by file name."""
    for name in MANIFEST_NAMES:
        path = folder / name
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise UserError(f"{path} is not valid JSON: {exc}")
            entries = data.get("decks", []) if isinstance(data, dict) else data
            return {str(e["file"]): e for e in entries if isinstance(e, dict) and "file" in e}
    return {}


def _load_decks(ctx: Context, paths: Sequence[str], role: str) -> List[Tuple[Deck, dict, List[DeckIssue]]]:
    """Load decks from files and folders, attach manifest metadata, and collect their problems."""
    loaded = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            raise UserError(f"deck path not found: {path}")
        files = find_deck_files(path)
        if not files:
            raise UserError(f"no decklists (.txt/.dck) found in {path}")
        manifest = _read_manifest(path if path.is_dir() else path.parent)
        for file in files:
            info = manifest.get(file.name, {})
            deck = load_deck(file, ctx.db)
            if info.get("name"):
                deck.name = str(info["name"])
            issues = list(deck.issues)
            if not deck.errors:
                issues += legality.check_deck(deck, ctx.db, ctx.format)
            loaded.append((deck, info, issues))
    return loaded


def _report_issues(loaded, strict: bool) -> Dict[str, List[str]]:
    """Print deck problems; stop if any deck cannot be simulated (or is illegal under --strict)."""
    fatal = False
    notes: Dict[str, List[str]] = {}
    for deck, _info, issues in loaded:
        if not issues:
            continue
        notes[deck.name] = [str(i) for i in issues]
        print(f"{deck.name}:", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        if deck.errors or (strict and any(i.severity == "error" for i in issues)):
            fatal = True
    if fatal:
        raise UserError(
            "Fix the problems above before simulating"
            + ("" if not strict else " (or drop --strict to simulate decks that break format rules)") + "."
        )
    return notes


def _entrants(ctx: Context, groups: Sequence[Tuple[Sequence[str], str]]) -> Tuple[List[Entrant], Dict[str, List[str]]]:
    """Load several groups of decks (paths, role) into entrants with unique keys."""
    loaded = []
    roles = []
    for paths, role in groups:
        batch = _load_decks(ctx, paths, role)
        loaded += batch
        roles += [role] * len(batch)
    notes_by_name = _report_issues(loaded, getattr(ctx.args, "strict", False))
    keys = experiment.unique_keys(deck.name for deck, _, _ in loaded)
    entrants = []
    notes: Dict[str, List[str]] = {}
    for key, role, (deck, info, _issues) in zip(keys, roles, loaded):
        share = info.get("meta_share")
        entrants.append(Entrant(
            key=key, deck=deck, role=role,
            weight=float(share) if isinstance(share, (int, float)) and share > 0 else None,
            category=str(info.get("category") or ""),
            pilot=str(info.get("ai_pilot") or ""),
            ai_profile=str(info.get("ai_profile") or ""),
            ai_mc=_mc_setting(info.get("ai_mc"), deck.name),
        ))
        if deck.name in notes_by_name:
            notes[key] = notes_by_name[deck.name]
    for entrant in entrants:
        _check_profile_name(ctx, entrant.ai_profile, f" (set for {entrant.deck.name})")
    return entrants, notes


def _mc_setting(value, deck_name: str) -> str:
    if value in (None, ""):
        return ""
    if value not in ("off", "on", "max"):
        raise UserError(f"ai_mc for {deck_name} must be off, on or max, not {value!r}")
    return str(value)


def _options(args: argparse.Namespace) -> RunOptions:
    if args.games < 1:
        raise UserError("--games must be at least 1")
    return RunOptions(
        games=args.games, seed=args.seed, timeout=args.timeout, workers=args.workers,
        heap=args.heap, monte_carlo=args.mc or "off", ai_profile=args.ai_profile or "", save_logs=args.save_logs,
        force_profile=bool(args.ai_profile), force_monte_carlo=args.mc is not None,
    )


def _run_dir(args: argparse.Namespace, kind: str, label: str) -> Path:
    if getattr(args, "resume", None):
        path = Path(args.resume).expanduser()
        if not (path / "run.json").is_file():
            raise UserError(f"{path} is not a run directory (no run.json)")
        return path
    if args.out:
        return Path(args.out).expanduser()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path("runs") / f"{stamp}-{kind}-{experiment.slug(label)[:40]}"


def _check_ai_profile(ctx: Context) -> None:
    _check_profile_name(ctx, getattr(ctx.args, "ai_profile", None))


def _check_profile_name(ctx: Context, profile: Optional[str], where: str = "") -> None:
    if not profile:
        return
    from . import ai_profiles

    available = ai_profiles.available(ctx.install)  # Forge's, mtgsim's and the user's (MTGSIM_HOME/profiles)
    if profile not in available:
        raise UserError(f"unknown AI profile \"{profile}\"{where}. Available: {', '.join(available)}")


def _finish(ctx: Context, run_dir: Path, summary: dict) -> None:
    """Save the analysed results and the HTML report, and tell the user where they are."""
    from . import report

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    html = report.write_report(run_dir, summary)
    problems = summary.get("problems") or {}
    if problems.get("timeouts") or problems.get("errors"):
        print(f"\nNote: {problems.get('timeouts', 0)} game(s) hit the time limit and "
              f"{problems.get('errors', 0)} failed in the engine; they are excluded from win rates.")
    print(f"\nReport:  {html}")
    print(f"Data:    {run_dir / 'summary.json'}  (raw games: {run_dir / 'games.jsonl'})")


def _base_summary(kind: str, title: str, ctx: Context, run_dir: Path, entrants: List[Entrant],
                  records: List[dict], notes: Dict[str, List[str]]) -> dict:
    run_info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    fmt = ctx.format
    return {
        "kind": kind,
        "title": title,
        "created": run_info.get("created"),
        "format": fmt.name if fmt else "Casual (no format rules)",
        "forge": run_info.get("forge", {}),
        "options": run_info.get("options", {}),
        "elapsed_seconds": run_info.get("elapsed_seconds"),
        "entrants": {e.key: e.describe() for e in entrants},
        "deck_notes": notes,
        "problems": {
            "timeouts": sum(1 for r in records if r["status"] == "timeout"),
            "errors": sum(1 for r in records if r["status"] not in ("ok", "timeout")),
        },
        "caveat": AI_CAVEAT,
        "mtgsim_version": __version__,
    }


def _card_tables(entrants: List[Entrant], records: List[dict], roles: Sequence[str]) -> dict:
    return {
        e.key: analysis.card_stats(records, e.key, dict(e.deck.main))
        for e in entrants if e.role in roles
    }


def _goldfish_for(ctx: Context, entrants: List[Entrant], roles: Sequence[str]) -> dict:
    """Engine-free consistency numbers for the decks under test (fast enough to always include)."""
    try:
        from . import goldfish
    except ImportError:
        return {}
    out = {}
    for e in entrants:
        if e.role in roles:
            out[e.key] = goldfish.analyze(e.deck, ctx.db, games=5000, turns=8, seed=ctx.args.seed)
    return out


def _print_pairing_rows(rows: List[dict], names: Dict[str, str], label: str = "Opponent") -> None:
    table = []
    for p in rows:
        table.append([
            names.get(p["b"], p["b"]), str(p["games"]), f"{p['wins']}-{p['losses']}",
            _pct(p["win_rate"]), _ci(p["ci"]),
            _pct(p["on_play"]["win_rate"], 0), _pct(p["on_draw"]["win_rate"], 0),
            _num(p["avg_turn_a_wins"]), _num(p["avg_turn_b_wins"]),
        ])
    print(_table(
        [label, "Games", "W-L", "Win rate", "95% CI", "On play", "On draw", "Wins on turn", "Loses on turn"],
        table, right=(1, 2, 3, 4, 5, 6, 7, 8),
    ))


def _print_pilot_note(opponents: List[Entrant]) -> None:
    weak = [o.deck.name for o in opponents if o.pilot == "weak"]
    if weak:
        print("\nDiscount results against " + ", ".join(weak) + ": Forge's AI plays "
              + ("that deck" if len(weak) == 1 else "those decks") + " far below real strength.")


def _print_field(field: dict) -> None:
    print(f"\nOverall: {field['wins']}-{field['losses']} in {field['decided']} decided games")
    print(f"  Raw record            {_pct(field['pooled']['win_rate'])}  (95% CI {_ci(field['pooled']['ci'])})")
    print(f"  Each opponent equal   {_pct(field['mean']['rate'])}  (95% CI {_ci(field['mean']['ci'])})")
    if field.get("weighted"):
        w = field["weighted"]
        print(f"  Weighted by meta share {_pct(w['rate'])}  (95% CI {_ci(w['ci'])})")
    print(f"  On the play {_pct(field['on_play']['win_rate'])}, on the draw {_pct(field['on_draw']['win_rate'])}; "
          f"mulligan rate {_pct(field['mulligan_rate'])}")


def _print_cards(stats_for_deck: dict, name: str, limit: int = 6) -> None:
    cards = [c for c in stats_for_deck["cards"] if c["seen"]["games"] >= 20 and c["not_seen"]["games"] >= 20]
    if len(cards) < 2:
        return
    print(f"\nCards in {name}: win rate when seen minus when not seen, in points (* = clearly not zero; "
          "the rest may be noise):")
    rows = []
    picks = cards[:limit] + ([None] if len(cards) > 2 * limit else []) + cards[-limit:] if len(cards) > limit else cards
    seen = set()
    for c in picks:
        if c is None:
            rows.append(["...", "", "", "", "", ""])
            continue
        if c["card"] in seen:
            continue
        seen.add(c["card"])
        lo, hi = (c.get("iwd_ci") or [None, None])[:2]
        clear = lo is not None and (lo > 0 or hi < 0)
        rows.append([
            f"{c['copies']} {c['card']}", f"{c['iwd'] * 100:+.1f}{'*' if clear else ' '}", _pct(c["seen"]["win_rate"], 0),
            _pct(c["not_seen"]["win_rate"], 0), _pct(c["opening"]["win_rate"], 0), _pct(c["play_rate"], 0),
        ])
    print(_table(["Card", "IWD pts", "Seen", "Not seen", "In opener", "Played when seen"], rows, right=(1, 2, 3, 4, 5)))


# ----------------------------------------------------------------- commands


def cmd_setup(args: argparse.Namespace) -> int:
    major = forge.check_java()
    print(f"Java {major} found.")
    if args.build:
        install = forge.build_from_source(Path(args.dest) if args.dest else None, ref=args.ref,
                                          apply_patches=not args.no_patches)
    elif args.forge_dir:
        if args.no_patches:
            raise UserError("--no-patches only applies to --build; mtgsim never patches a Forge you supply")
        install = forge.detect_install(Path(args.forge_dir))
    else:
        raise UserError("choose --build (fetch and build Forge) or --forge-dir PATH (use an existing Forge)")
    config = forge.load_config()
    config["forge_dir"] = str(install.root)
    forge.save_config(config)
    print(f"Forge {install.version} at {install.root}")
    print(forge.patch_status(install, verify=args.build).summary())
    print("Compiling the game driver...")
    forge.ensure_bridge(install, force=True)
    print("Reading the card database...")
    db = load_database(install, refresh=True)
    print(f"{len(db)} cards, {len(db.editions)} sets.")
    print("Setup complete. Try: python -m mtgsim doctor")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check the whole toolchain by playing two real games."""
    ctx = Context(args)
    print(f"mtgsim {__version__}")
    print(f"Java {forge.check_java()}")
    install = ctx.install
    print(f"Forge {install.version} at {install.root}")
    patches = forge.patch_status(install, verify=True)
    print(patches.summary())
    print(f"Card database: {len(ctx.db)} cards")
    formats = legality.load_formats(install.res)
    if "standard" in formats:
        print(f"Standard: {len(formats['standard'].sets)} legal sets, {len(formats['standard'].banned)} banned cards")
    import tempfile
    from .decks import deck_from_text

    red = deck_from_text("20 Mountain\n40 Raging Goblin\n", "doctor-red", ctx.db)
    green = deck_from_text("20 Forest\n40 Grizzly Bears\n", "doctor-green", ctx.db)
    entrants = [Entrant("doctor-red", red), Entrant("doctor-green", green)]
    with tempfile.TemporaryDirectory() as tmp:
        records = experiment.execute(install, Path(tmp), entrants, [(entrants[0], entrants[1])],
                                     RunOptions(games=2, workers=1, timeout=120), quiet=True)
    ok = [r for r in records if r["status"] == "ok"]
    if len(ok) != 2:
        raise UserError("the test games did not complete: " + "; ".join(r.get("error", r["status"]) for r in records))
    played = f"Played 2 test games in {sum(r['ms'] for r in ok) / 1000:.1f}s of engine time."
    if patches.state == "out-of-date":
        raise UserError(f"{played} The engine works, but its Forge patches are out of date; "
                        "run `python -m mtgsim setup --build` to update them.")
    print(f"{played} Everything works.")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    ctx = Context(args)
    loaded = _load_decks(ctx, args.decks, "hero")
    fmt = ctx.format
    failed = False
    for deck, _info, issues in loaded:
        types: Counter = Counter()
        for name, n in deck.main.items():
            card = ctx.db.get(name)
            if card is None:
                continue
            kind = "Land" if card.is_land else "Creature" if card.is_creature else "Other spell"
            types[kind] += n
        print(f"{deck.name}: {deck.main_count} main / {deck.side_count} sideboard  "
              f"({types['Land']} lands, {types['Creature']} creatures, {types['Other spell']} other spells)")
        errors = [i for i in issues if i.severity == "error"]
        for issue in issues:
            print(f"  {issue}")
        if not issues:
            print(f"  OK - legal in {fmt.name}" if fmt else "  OK - every card is known to the engine")
        failed = failed or bool(errors)
    return 1 if failed else 0


def cmd_match(args: argparse.Namespace) -> int:
    ctx = Context(args)
    _check_ai_profile(ctx)
    entrants, notes = _entrants(ctx, [([args.deck_a], "hero"), ([args.deck_b], "hero")])
    a, b = entrants
    options = _options(args)
    run_dir = _run_dir(args, "match", f"{a.deck.name}-vs-{b.deck.name}")
    print(f"{a.deck.name} vs {b.deck.name}: {options.games} games (Forge {ctx.install.version})")
    records = experiment.execute(ctx.install, run_dir, entrants, [(a, b)], options, meta={"kind": "match"})
    pairing = analysis.summarize_pairing(records, a.key, b.key)
    names = {e.key: e.deck.name for e in entrants}
    print()
    _print_pairing_rows([pairing], names, label=f"{a.deck.name} vs")
    if pairing["p_even"] is not None:
        even = pairing["p_even"]
        ahead = a.deck.name if (pairing["win_rate"] or 0) > 0.5 else b.deck.name
        print("\n" + (f"A real edge for {ahead}: an even matchup would rarely produce this result "
                      if even < 0.05 else "This is consistent with an even matchup ") + f"(p = {even:.3f}).")
    cards = _card_tables(entrants, records, ("hero",))
    if a.key != b.key:
        for e in entrants:
            _print_cards(cards[e.key], e.deck.name)
    summary = _base_summary("match", f"{a.deck.name} vs {b.deck.name}", ctx, run_dir, entrants, records, notes)
    summary.update({"pairings": [pairing], "cards": cards, "goldfish": _goldfish_for(ctx, entrants, ("hero",))})
    _finish(ctx, run_dir, summary)
    return 0


def _opponent_paths(args: argparse.Namespace) -> List[str]:
    if args.vs:
        return args.vs
    if DEFAULT_GAUNTLET.is_dir() and find_deck_files(DEFAULT_GAUNTLET):
        return [str(DEFAULT_GAUNTLET)]
    raise UserError("no opponents given: pass --vs FOLDER_OR_DECKLIST (one or more)")


def cmd_gauntlet(args: argparse.Namespace) -> int:
    ctx = Context(args)
    _check_ai_profile(ctx)
    entrants, notes = _entrants(ctx, [([args.deck], "hero"), (_opponent_paths(args), "opponent")])
    hero, opponents = entrants[0], entrants[1:]
    options = _options(args)
    run_dir = _run_dir(args, "gauntlet", hero.deck.name)
    print(f"{hero.deck.name} vs {len(opponents)} opponents: {options.games} games each, "
          f"{options.games * len(opponents)} in total (Forge {ctx.install.version})")
    pairs = [(hero, o) for o in opponents]
    records = experiment.execute(ctx.install, run_dir, entrants, pairs, options, meta={"kind": "gauntlet"})
    pairings = [analysis.summarize_pairing(records, hero.key, o.key) for o in opponents]
    weights = {o.key: o.weight for o in opponents}
    field = analysis.summarize_field(hero.key, pairings, weights)
    names = {e.key: e.deck.name for e in entrants}
    print()
    _print_pairing_rows(sorted(pairings, key=lambda p: -(p["win_rate"] or 0)), names)
    _print_pilot_note(opponents)
    _print_field(field)
    cards = _card_tables(entrants, records, ("hero",))
    _print_cards(cards[hero.key], hero.deck.name)
    summary = _base_summary("gauntlet", f"{hero.deck.name} vs the field", ctx, run_dir, entrants, records, notes)
    summary.update({"hero": hero.key, "pairings": pairings, "field": {hero.key: field}, "cards": cards,
                    "goldfish": _goldfish_for(ctx, entrants, ("hero",))})
    _finish(ctx, run_dir, summary)
    return 0


def cmd_ab(args: argparse.Namespace) -> int:
    ctx = Context(args)
    _check_ai_profile(ctx)
    entrants, notes = _entrants(ctx, [([args.deck_a], "hero"), ([args.deck_b], "variant"),
                                      (_opponent_paths(args), "opponent")])
    first, second, opponents = entrants[0], entrants[1], entrants[2:]
    if first.deck.fingerprint() == second.deck.fingerprint():
        raise UserError("the two decks have identical main decks; there is nothing to compare")
    options = _options(args)
    run_dir = _run_dir(args, "ab", f"{first.deck.name}-vs-{second.deck.name}")
    pairs = [(first, o) for o in opponents] + [(second, o) for o in opponents]
    if args.head_to_head:
        pairs.append((first, second))
    print(f"A/B test: {first.deck.name} and {second.deck.name}, each vs {len(opponents)} opponents, "
          f"{options.games} games per pairing, {options.games * len(pairs)} in total (Forge {ctx.install.version})")
    changes = _deck_diff(first.deck, second.deck)
    if changes:
        print("Changes from A to B: " + ", ".join(changes))
    records = experiment.execute(ctx.install, run_dir, entrants, pairs, options, meta={"kind": "ab"})
    pairings = [analysis.summarize_pairing(records, a.key, b.key) for a, b in pairs]
    weights = {o.key: o.weight for o in opponents}
    result = analysis.summarize_ab(first.key, second.key, pairings, weights)
    fields = {e.key: analysis.summarize_field(e.key, [p for p in pairings if p["b"] not in (first.key, second.key)], weights)
              for e in (first, second)}
    names = {e.key: e.deck.name for e in entrants}

    rows = []
    for row in result["rows"]:
        rows.append([
            names.get(row["opponent"], row["opponent"]),
            f"{_pct(row['first']['win_rate'])} ({row['first']['wins']}/{row['first']['decided']})",
            f"{_pct(row['second']['win_rate'])} ({row['second']['wins']}/{row['second']['decided']})",
            f"{row['diff'] * 100:+.1f}" if row["diff"] is not None else "-",
            f"{row['p']:.2f}" if row["p"] is not None else "-",
        ])
    print()
    print(_table(["Opponent", f"A: {first.deck.name}", f"B: {second.deck.name}", "A-B pts", "p"], rows, right=(1, 2, 3, 4)))
    overall = result["overall_mean"]
    if overall["diff"] is not None:
        print(f"\nA {_pct(fields[first.key]['mean']['rate'])} vs B {_pct(fields[second.key]['mean']['rate'])} "
              f"(each opponent equal): A-B = {overall['diff'] * 100:+.1f} points, "
              f"95% CI {overall['ci'][0] * 100:+.1f} to {overall['ci'][1] * 100:+.1f}")
    if result.get("overall_weighted") and result["overall_weighted"]["diff"] is not None:
        w = result["overall_weighted"]
        print(f"Weighted by meta share: A-B = {w['diff'] * 100:+.1f} points, "
              f"95% CI {w['ci'][0] * 100:+.1f} to {w['ci'][1] * 100:+.1f}")
    _print_pilot_note(opponents)
    if result["head_to_head"]:
        h = result["head_to_head"]
        print(f"Head to head: A won {h['wins']} of {h['decided']} ({_pct(h['win_rate'])}, 95% CI {_ci(h['ci'])})")
    print("\n" + analysis.ab_verdict(result, f"A ({first.deck.name})", f"B ({second.deck.name})"))

    summary = _base_summary("ab", f"A/B: {first.deck.name} vs {second.deck.name}", ctx, run_dir, entrants, records, notes)
    summary.update({"hero": first.key, "variant": second.key, "pairings": pairings, "field": fields, "ab": result,
                    "deck_changes": changes, "cards": _card_tables(entrants, records, ("hero", "variant")),
                    "goldfish": _goldfish_for(ctx, entrants, ("hero", "variant"))})
    _finish(ctx, run_dir, summary)
    return 0


def _deck_diff(a: Deck, b: Deck) -> List[str]:
    changes = []
    for name in sorted(set(a.main) | set(b.main)):
        delta = b.main.get(name, 0) - a.main.get(name, 0)
        if delta:
            changes.append(f"{delta:+d} {name}")
    return changes


def cmd_matrix(args: argparse.Namespace) -> int:
    ctx = Context(args)
    _check_ai_profile(ctx)
    entrants, notes = _entrants(ctx, [(args.decks, "hero")])
    if len(entrants) < 2:
        raise UserError("a round robin needs at least two decks")
    options = _options(args)
    pairs = [(entrants[i], entrants[j]) for i in range(len(entrants)) for j in range(i + 1, len(entrants))]
    run_dir = _run_dir(args, "matrix", f"{len(entrants)}-decks")
    print(f"Round robin: {len(entrants)} decks, {len(pairs)} pairings, {options.games} games each, "
          f"{options.games * len(pairs)} in total (Forge {ctx.install.version})")
    records = experiment.execute(ctx.install, run_dir, entrants, pairs, options, meta={"kind": "matrix"})
    pairings = [analysis.summarize_pairing(records, a.key, b.key) for a, b in pairs]
    matrix = analysis.summarize_matrix([e.key for e in entrants], pairings)
    names = {e.key: e.deck.name for e in entrants}
    rows = [[str(i + 1), names[r["key"]], _pct(r["mean_win_rate"]), _ci(r["ci"]), f"{r['wins']}-{r['decided'] - r['wins']}"]
            for i, r in enumerate(matrix["ranking"])]
    print()
    print(_table(["#", "Deck", "Avg win rate", "95% CI", "W-L"], rows, right=(0, 2, 3, 4)))
    summary = _base_summary("matrix", f"Round robin of {len(entrants)} decks", ctx, run_dir, entrants, records, notes)
    summary.update({"pairings": pairings, "matrix": matrix, "cards": _card_tables(entrants, records, ("hero",))})
    _finish(ctx, run_dir, summary)
    return 0


def cmd_goldfish(args: argparse.Namespace) -> int:
    ctx = Context(args)
    from . import goldfish

    loaded = _load_decks(ctx, [args.deck], "hero")
    _report_issues(loaded, False)
    deck = loaded[0][0]
    result = goldfish.analyze(deck, ctx.db, games=args.hands, turns=args.turns, seed=args.seed)
    print(goldfish.format_text(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"\nSaved to {args.json}")
    if not args.clock:
        return 0

    # The clock is measured on the real engine: the deck plays against 60 basic lands, an
    # opponent that never does anything, so the winning turn is the deck's unopposed speed.
    from .decks import deck_from_text

    _check_ai_profile(ctx)
    passive = deck_from_text("60 Wastes\n", "Passive opponent", ctx.db)
    hero, dummy = Entrant("hero", deck, role="hero"), Entrant("passive", passive)
    options = _options(args)
    options.games = args.clock
    run_dir = _run_dir(args, "clock", deck.name)
    print(f"\nClock: {args.clock} games against an opponent that does nothing (Forge {ctx.install.version})")
    records = experiment.execute(ctx.install, run_dir, [hero, dummy], [(hero, dummy)], options, meta={"kind": "clock"})
    clock = analysis.summarize_clock(records, hero.key, dummy.key)
    print()
    rows = [[str(t["turn"]), str(t["wins"]), _pct(t["by_turn"])] for t in clock["turns"] if t["wins"] or t["turn"] <= 12]
    print(_table(["Turn", "Wins on this turn", "Won by this turn"], rows, right=(0, 1, 2)))
    print(f"\nAverage winning turn {_num(clock['mean_turn'])}, median {clock['median_turn']}, "
          f"fastest {clock['fastest_turn']}; {clock['not_won']} of {clock['games']} games not won.")
    summary = _base_summary("clock", f"Goldfish clock: {deck.name}", ctx, run_dir, [hero, dummy], records, {})
    summary.update({"hero": hero.key, "clock": clock, "goldfish": {hero.key: result}})
    _finish(ctx, run_dir, summary)
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    """Search AI profile settings that make simulated win rates track real ones (see tune.py)."""
    from . import tune

    ctx = Context(args)
    stored = tune.stored_run(args.resume) if args.resume else None
    paths = [d["file"] for d in stored["decks"]] if stored else (args.decks or [str(DEFAULT_GAUNTLET)])
    entrants, _notes = _entrants(ctx, [(paths, "hero")])
    real = {}
    for e in entrants:
        info = _read_manifest(e.deck.path.parent).get(e.deck.path.name, {}) if e.deck.path else {}
        real[e.key] = info.get("real_win_rate")
    if args.resume:
        run_dir = Path(args.resume).expanduser()
    else:
        run_dir = Path(args.out).expanduser() if args.out else \
            Path("runs") / f"{time.strftime('%Y%m%d-%H%M%S')}-tune-{len(entrants)}-decks"
    return tune.command(ctx.install, run_dir, entrants, real, args, stored)


def cmd_report(args: argparse.Namespace) -> int:
    from . import report

    run_dir = Path(args.run_dir).expanduser()
    path = run_dir / "summary.json"
    if not path.is_file():
        raise UserError(f"{run_dir} has no summary.json; was the run interrupted? Re-run its command with --resume {run_dir}")
    html = report.write_report(run_dir, json.loads(path.read_text(encoding="utf-8")))
    print(f"Report: {html}")
    return 0


# ------------------------------------------------------------------- parser


def _add_common(p: argparse.ArgumentParser, sim: bool = True) -> None:
    p.add_argument("--forge-dir", help="Forge installation to use (default: the one saved by `setup`)")
    p.add_argument("--format", default="standard",
                   help="format for legality checks: standard (default), pioneer, modern, ..., or casual for none")
    p.add_argument("--seed", type=int, default=1, help="base random seed; the same seed replays the same games")
    if not sim:
        return
    p.add_argument("-n", "--games", type=int, default=100, help="games per pairing (default 100)")
    p.add_argument("-j", "--workers", type=int, default=None, help="parallel Forge processes (default: CPU count, max 8)")
    p.add_argument("--out", help="directory for results (default: runs/<timestamp>-...)")
    p.add_argument("--resume", metavar="RUN_DIR", help="continue an interrupted run in this directory")
    p.add_argument("--strict", action="store_true", help="refuse to simulate decks that break format rules")
    p.add_argument("--timeout", type=int, default=180, help="seconds before a game is stopped and counted as unfinished")
    p.add_argument("--ai-profile", help="Forge AI profile for both players (Default, Reckless, Cautious, ...)")
    p.add_argument("--mc", choices=("off", "on", "max"), default=None,
                   help="Forge's Monte Carlo AI look-ahead: slower, and results are no longer exactly reproducible")
    p.add_argument("--heap", default="2g", help="Java heap per worker (default 2g)")
    p.add_argument("--save-logs", action="store_true", help="keep Forge's full text log of every game")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mtgsim",
        description="Test Magic: The Gathering decks by playing them against each other on the Forge engine.",
    )
    parser.add_argument("--version", action="version", version=f"mtgsim {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("setup", help="install or locate Forge and prepare mtgsim")
    p.add_argument("--build", action="store_true", help="fetch the supported Forge version and build it (needs git, Maven, JDK 17+)")
    p.add_argument("--forge-dir", help="use an existing Forge installation or built source checkout")
    p.add_argument("--dest", help="where --build puts Forge (default: ~/.mtgsim/forge)")
    p.add_argument("--ref", default=forge.FORGE_PINNED_REF, help="Forge commit to build (default: the validated one)")
    p.add_argument("--no-patches", action="store_true",
                   help="build Forge without mtgsim's Forge patches (mtgsim/forge_patches), e.g. to measure what they change")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor", help="verify the installation by playing two test games")
    p.add_argument("--forge-dir")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("check", help="validate decklists: card names, deck size, format legality")
    p.add_argument("decks", nargs="+", help="decklist files or folders")
    _add_common(p, sim=False)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("match", help="play one deck against another")
    p.add_argument("deck_a")
    p.add_argument("deck_b")
    _add_common(p)
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("gauntlet", help="play one deck against a field of opponents")
    p.add_argument("deck")
    p.add_argument("--vs", nargs="+", metavar="PATH", help="opponent decklists or folders (default: decks/standard/meta)")
    _add_common(p)
    p.set_defaults(func=cmd_gauntlet)

    p = sub.add_parser("ab", help="compare two versions of a deck against the same field")
    p.add_argument("deck_a")
    p.add_argument("deck_b")
    p.add_argument("--vs", nargs="+", metavar="PATH", help="opponent decklists or folders (default: decks/standard/meta)")
    p.add_argument("--head-to-head", action="store_true", help="also play the two versions against each other")
    _add_common(p)
    p.set_defaults(func=cmd_ab)

    p = sub.add_parser("matrix", help="round robin: every deck against every other deck")
    p.add_argument("decks", nargs="+", help="decklist files or folders")
    _add_common(p)
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("goldfish", help="solo consistency analysis (mana, curve, colours) without the engine")
    p.add_argument("deck")
    p.add_argument("--hands", type=int, default=20000, help="simulated solo games (default 20000)")
    p.add_argument("--turns", type=int, default=8, help="turns to simulate (default 8)")
    p.add_argument("--json", metavar="FILE", help="also save the full result as JSON")
    p.add_argument("--clock", type=int, nargs="?", const=200, default=0, metavar="GAMES",
                   help="also measure the kill turn on Forge against an opponent that does nothing (default 200 games)")
    _add_common(p)
    p.set_defaults(func=cmd_goldfish)

    p = sub.add_parser("tune", help="search AI profile settings that make simulated win rates track real ones")
    p.add_argument("decks", nargs="*", help="decklists or folders whose gauntlet.json has real_win_rate "
                   "(default: decks/standard/meta)")
    _add_common(p, sim=False)
    p.add_argument("--space", help="parameter space JSON (default: mtgsim/profiles/spaces/default.json)")
    p.add_argument("--group", action="append", metavar="NAME=CAT,CAT",
                   help="decks sharing a profile, by category (default: reactive=control,midrange,tempo "
                        "and proactive=aggro,ramp,combo); repeat for each group")
    p.add_argument("--tune", nargs="+", metavar="GROUP", help="groups that get candidate profiles (default: all)")
    p.add_argument("--profiles", type=int, default=3, metavar="K",
                   help="random profiles per tuned group; candidates are every combination (default 3)")
    p.add_argument("--rounds", default="10,30", metavar="N,N",
                   help="games per pairing in each round of successive halving (default 10,30)")
    p.add_argument("--eta", type=int, default=3, help="keep the best 1/ETA candidates after each round (default 3)")
    p.add_argument("--confirm", type=int, default=30, metavar="GAMES",
                   help="fresh games per pairing to re-measure the winner and the baseline (default 30; 0 skips)")
    p.add_argument("--holdout", nargs="+", metavar="DECK", help="decks whose real win rates are never used for selection")
    p.add_argument("--cv", default="loo", help="cross-validate the selection over training decks: loo, K folds, or off")
    p.add_argument("--matchups", metavar="FILE", help="real deck-vs-deck win rates (see README)")
    p.add_argument("--objective", choices=("deck", "matchup", "both"), default="deck",
                   help="rank correlation over deck win rates, matchup win rates, or their mean (default deck)")
    p.add_argument("--bootstrap", type=int, default=1000, help="resamples for the game-noise ranges (default 1000)")
    p.add_argument("--search-seed", type=int, default=None, help="seed for drawing profiles (default: --seed)")
    p.add_argument("--import", dest="import_runs", nargs="+", metavar="RUN_DIR",
                   help="reuse games of earlier runs (e.g. a matrix with the same seed) where they are identical")
    p.add_argument("--dry-run", action="store_true", help="print the candidates and the games needed, play nothing")
    p.add_argument("-j", "--workers", type=int, default=None, help="parallel Forge processes (default: CPU count, max 8)")
    p.add_argument("--out", help="directory for results (default: runs/<timestamp>-tune-...)")
    p.add_argument("--resume", metavar="RUN_DIR", help="continue a tuning run (its settings are read from tune.json)")
    p.add_argument("--strict", action="store_true", help="refuse decks that break format rules")
    p.add_argument("--timeout", type=int, default=180, help="seconds before a game is stopped and counted as unfinished")
    p.add_argument("--mc", choices=("off", "on", "max"), default=None,
                   help="Monte Carlo search for every seat (default off; on makes the cache inexact)")
    p.add_argument("--heap", default="2g", help="Java heap per worker (default 2g)")
    p.set_defaults(func=cmd_tune)

    p = sub.add_parser("report", help="rebuild report.html for an existing run directory")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except (UserError, ForgeError, RunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Finished games are saved; re-run the same command with --resume RUN_DIR to continue.",
              file=sys.stderr)
        return 130
