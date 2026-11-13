"""Likely AI misplays, card by card: which cards the Forge AI holds, wastes or points badly.

Everything here works on the stored game records (``games.jsonl``) and the entrants' decklists, so
it can be run on any finished run. The Java driver records, per player and card name (see
``mtgsim/bridge/AGENTS.md`` for the exact field definitions):

* ``endHand`` / ``endHandLands``: non-land cards (counts) and the number of lands still in hand
  when the game ended.
* ``idleOwn``: turns on which the card sat in hand at the start of its owner's cleanup step while
  the owner's untapped mana could have paid for it and it had legal targets (timing ignored: the
  mana was there in the second main phase). ``idleOpp``: the same at the start of an opponent's
  cleanup step, counted only for cards castable at instant speed.
* ``counter``: for counterspells, opponents' spells that resolved while this card sat in hand and
  could have countered them (``passed``, ``passedMaxMv``), and what it targeted when cast.
* ``removal``: for spells with a harmful targeted effect on permanents (destroy, exile or bounce
  from the battlefield, damage, -X/-X, -1/-1 counters, fight, steal), the target quality of each
  cast: the chosen targets' value over the value of the best legal opposing targets the effect
  could have killed (Forge's creature evaluation; other permanents by mana value), and whether it
  hit the caster's own permanent.
* ``roles``: tags per card (``land``, ``creature``, ``instant``, ``counter``, ``removal``,
  ``sweeper``, ``edict``) read from the card's scripted abilities.

From those, per card of each deck and over decided games only:

* **Rarely cast** (works on old runs too): games the card was seen (opening hand or drawn) but
  never cast.
* **Idle turns per game seen**: free windows in which the card was castable and not cast. A free
  window is an opponent's cleanup step for instant-speed cards (holding an instant through your
  own turn is normal, but the mana untaps anyway after the opponent's turn) and the owner's
  cleanup step for everything else.
* **Castable, never cast**: games with at least one free window in which the card was never cast,
  as a share of the games with a free window.
* **Stranded**: games the card ended in hand, and the win rate when stranded versus not.
* **Poor targets**: removal casts whose target quality is below ``POOR_TARGET`` (a legal opposing
  target was worth at least 1.5 times as much) or that hit the caster's own permanent.
* **Counter windows passed**: opponents' spells of mana value ``BIG_SPELL`` or more that resolved
  while the counterspell could have countered them.

A game is *flagged* for a card when the card was castable in a free window and never cast,
stranded after having been castable, pointed at a poor target, or let a big spell resolve. The
ranking score is flagged games per 100 games of the deck, an estimate of how many games the
problem touches. Each card also gets the win-rate difference between flagged games and the other
games it was seen in, with a 95% interval; only differences whose interval excludes zero are
marked significant. These are heuristics and correlations, not proof: losing games end with more
cards in hand, flooded or screwed games look like holding cards, and Forge's target evaluation is
itself a heuristic. Use them to choose which cards' AI logic to read, not as verdicts.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set

from . import stats

POOR_TARGET = 2.0 / 3.0  # must match Tracker.POOR_TARGET in ForgeBridge.java
BIG_SPELL = 3  # a counterspell letting a spell of this mana value or more resolve is flagged
BASIC_LANDS = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
                         "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
                         "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes"})
CAVEAT = (
    "Misplay signals are heuristics read from the engine's state, and the win-rate differences are "
    "correlations: losing games end with more cards in hand, mana-screwed or flooded games look like "
    "holding cards, and Forge's own target evaluation is a heuristic. Use the ranking to decide which "
    "cards' AI logic to inspect, not as proof that the AI misplayed them."
)


def has_signals(records: Iterable[dict]) -> bool:
    """True when at least one game was recorded by a driver that reports the misplay fields."""
    for record in records:
        for player in record.get("players") or []:
            if isinstance(player, dict) and player.get("endHand") is not None:
                return True
    return False


def _decided(record: dict) -> bool:
    return record.get("status") == "ok" and record.get("winner_seat") in (0, 1)


def _new_tally() -> dict:
    keys = ("seen", "seen_w", "cast", "never", "never_w", "new", "new_w",
            "stranded", "stranded_w", "stranded_castable", "windows", "own", "opp",
            "castable", "castable_never", "flag", "flag_w",
            "r_casts", "r_own", "r_poor", "r_quality", "r_games",
            "c_passed", "c_games", "c_big", "c_casts", "c_targets", "c_mv")
    return {k: 0 for k in keys}


def deck_misplays(records: Iterable[dict], deck_key: str, decklist: Dict[str, int],
                  lands: Optional[Set[str]] = None) -> dict:
    """Misplay signals for one deck's cards across every decided game it played.

    ``lands`` names the deck's lands when the card database is at hand; the driver's ``roles``
    tags and the basic land names are used as well, so old runs without either only miss
    nonbasic lands.
    """
    games = wins = new_games = new_wins = 0
    lands_left: List[int] = []
    roles: Dict[str, Set[str]] = {}
    tally = {name: _new_tally() for name in decklist}
    for record in records:
        if not _decided(record):
            continue
        players = record.get("players") or []
        for seat, key in enumerate(record.get("seats", [])):
            if key != deck_key or seat >= len(players) or not isinstance(players[seat], dict):
                continue
            player = players[seat]
            won = record["winner_seat"] == seat
            games += 1
            wins += won
            new = player.get("endHand") is not None
            if new:
                new_games += 1
                new_wins += won
                if player.get("endHandLands") is not None:
                    lands_left.append(player["endHandLands"])
                for name, tags in (player.get("roles") or {}).items():
                    roles.setdefault(name, set()).update(tags or ())
            _tally_game(tally, player, won, new, roles)
    is_land = _land_test(roles, lands)
    rows = [_row(name, decklist[name], tally[name], roles.get(name, set()), games, new_games)
            for name in decklist if not is_land(name)]
    basis = "flagged" if new_games else "never_cast"
    rows.sort(key=lambda r: (-(r["score"] or 0), -r["seen"], r["card"]))
    return {
        "deck": deck_key, "games": games, "wins": wins, "win_rate": stats.rate(wins, games),
        "signal_games": new_games, "basis": basis,
        "lands_left_in_hand": stats.mean(lands_left),
        "cards": rows,
    }


def _land_test(roles: Dict[str, Set[str]], lands: Optional[Set[str]]):
    def is_land(name: str) -> bool:
        if name in roles:
            return "land" in roles[name]
        if lands is not None:
            return name in lands
        return name in BASIC_LANDS
    return is_land


def _tally_game(tally: Dict[str, dict], player: dict, won: bool, new: bool, roles: Dict[str, Set[str]]) -> None:
    opening, drawn, played = player.get("opening") or {}, player.get("drawn") or {}, player.get("played") or {}
    end_hand = player.get("endHand") or {}
    idle_own, idle_opp = player.get("idleOwn") or {}, player.get("idleOpp") or {}
    counters, removal = player.get("counter") or {}, player.get("removal") or {}
    for name, t in tally.items():
        seen = (opening.get(name, 0) + drawn.get(name, 0)) > 0
        cast = played.get(name, 0) > 0
        if not seen:
            continue
        t["seen"] += 1
        t["seen_w"] += won
        if cast:
            t["cast"] += 1
        else:
            t["never"] += 1
            t["never_w"] += won
        if not new:
            continue
        t["new"] += 1
        t["new_w"] += won
        instant = "instant" in roles.get(name, ())
        own, opp = idle_own.get(name, 0), idle_opp.get(name, 0)
        windows = opp if instant else own
        t["own"] += own
        t["opp"] += opp
        t["windows"] += windows
        flagged = False
        if windows:
            t["castable"] += 1
            if not cast:
                t["castable_never"] += 1
                flagged = True
        if end_hand.get(name, 0):
            t["stranded"] += 1
            t["stranded_w"] += won
            if windows:
                t["stranded_castable"] += 1
                flagged = True
        r = removal.get(name)
        if r and r.get("casts"):
            t["r_casts"] += r["casts"]
            t["r_own"] += r.get("own", 0)
            t["r_poor"] += r.get("poor", 0)
            t["r_quality"] += r.get("quality", 0.0)
            if r.get("poor", 0):
                t["r_games"] += 1
                flagged = True
        c = counters.get(name)
        if c:
            t["c_passed"] += c.get("passed", 0)
            t["c_casts"] += c.get("cast", 0)
            t["c_targets"] += c.get("targets", 0)
            t["c_mv"] += c.get("targetMv", 0)
            if c.get("passed", 0):
                t["c_games"] += 1
                if c.get("passedMaxMv", 0) >= BIG_SPELL:
                    t["c_big"] += 1
                    flagged = True
        if flagged:
            t["flag"] += 1
            t["flag_w"] += won


def _versus(w1: int, n1: int, w2: int, n2: int) -> dict:
    test = stats.diff_test(w1, n1, w2, n2)
    lo, hi = test["ci"]
    return {
        "games": n1, "win_rate": stats.rate(w1, n1), "other_games": n2, "other_win_rate": stats.rate(w2, n2),
        "diff": test["diff"], "ci": test["ci"], "p": test["p"],
        "significant": lo is not None and (lo > 0 or hi < 0),
    }


def _row(name: str, copies: int, t: dict, tags: Set[str], deck_games: int, deck_new_games: int) -> dict:
    new = t["new"]
    row = {
        "card": name, "copies": copies, "roles": sorted(tags),
        "seen": t["seen"], "cast_rate": stats.rate(t["cast"], t["seen"]),
        "never_cast": t["never"], "never_cast_rate": stats.rate(t["never"], t["seen"]),
        "signal_games": new,
    }
    if not deck_new_games:
        # Old run: only the cast record is known. Score = seen-but-never-cast games per 100 games.
        row["score"] = 100.0 * t["never"] / deck_games if deck_games else None
        row["compare"] = _versus(t["never_w"], t["never"], t["seen_w"] - t["never_w"], t["seen"] - t["never"])
        row["reasons"] = _reasons_old(row)
        return row
    row["idle"] = {
        "windows": t["windows"], "per_game": stats.rate(t["windows"], new),
        "own_turns": t["own"], "opponent_turns": t["opp"],
        "instant_speed": "instant" in tags,
        "castable_games": t["castable"], "never_cast_games": t["castable_never"],
        "never_cast_share": stats.rate(t["castable_never"], t["castable"]),
    }
    row["stranded"] = dict(_versus(t["stranded_w"], t["stranded"], t["new_w"] - t["stranded_w"], new - t["stranded"]),
                           rate=stats.rate(t["stranded"], new), castable_games=t["stranded_castable"])
    if t["r_casts"] or "removal" in tags:
        row["removal"] = {
            "casts": t["r_casts"], "mean_quality": stats.rate(t["r_quality"], t["r_casts"]),
            "poor": t["r_poor"], "poor_share": stats.rate(t["r_poor"], t["r_casts"]),
            "own": t["r_own"], "own_share": stats.rate(t["r_own"], t["r_casts"]), "poor_games": t["r_games"],
        }
    if t["c_casts"] or t["c_passed"] or "counter" in tags:
        row["counter"] = {
            "passed": t["c_passed"], "passed_per_game": stats.rate(t["c_passed"], new),
            "passed_games": t["c_games"], "big_passed_games": t["c_big"],
            "casts": t["c_casts"], "targets": t["c_targets"],
            "mean_countered_mv": stats.rate(t["c_mv"], t["c_targets"]),
        }
    row["flagged_games"] = t["flag"]
    row["score"] = 100.0 * t["flag"] / deck_new_games
    row["compare"] = _versus(t["flag_w"], t["flag"], t["new_w"] - t["flag_w"], new - t["flag"])
    row["reasons"] = _reasons(row)
    return row


def _pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x * 100:.0f}%"


def _games(n: int) -> str:
    return f"{n} game" + ("" if n == 1 else "s")


def _reasons(row: dict) -> List[str]:
    out = []
    idle = row["idle"]
    if idle["never_cast_games"]:
        when = "on opponents' turns" if idle["instant_speed"] else "on its own turns"
        out.append(f"castable {when} but never cast in {idle['never_cast_games']} of "
                   f"{_games(idle['castable_games'])} where it could have been")
    if row["stranded"]["castable_games"]:
        out.append(f"left in hand at the end after being castable in {_games(row['stranded']['castable_games'])}")
    removal = row.get("removal")
    if removal and removal["poor"]:
        own = f", {removal['own']} at its caster's own permanent" if removal["own"] else ""
        out.append(f"{removal['poor']} of {removal['casts']} casts at a poor target{own}")
    counter = row.get("counter")
    if counter and counter["big_passed_games"]:
        out.append(f"let a spell of mana value {BIG_SPELL}+ resolve while able to counter it in "
                   f"{_games(counter['big_passed_games'])}")
    if not out and row["seen"] and row["never_cast"]:
        out.append(f"never cast in {row['never_cast']} of {_games(row['seen'])} seen")
    return out


def _reasons_old(row: dict) -> List[str]:
    if not row["seen"]:
        return []
    return [f"never cast in {row['never_cast']} of {_games(row['seen'])} seen ({_pct(row['never_cast_rate'])})"]


def analyze(records: Sequence[dict], entrants: Dict[str, dict], keys: Optional[Iterable[str]] = None,
            lands: Optional[Set[str]] = None) -> dict:
    """Misplay tables for the given decks (default: every entrant), keyed like ``summary.json``.

    ``entrants`` maps deck keys to ``Entrant.describe()`` dicts (``summary["entrants"]``); a list of
    them, as stored in ``run.json``, is accepted too.
    """
    if isinstance(entrants, list):
        entrants = {e["key"]: e for e in entrants}
    wanted = list(keys) if keys is not None else list(entrants)
    decks = {}
    for key in wanted:
        info = entrants.get(key)
        if not info:
            continue
        result = deck_misplays(records, key, dict(info.get("main") or {}), lands)
        if result["games"]:
            decks[key] = result
    return {
        "signals": has_signals(records), "poor_target": POOR_TARGET, "big_spell": BIG_SPELL,
        "caveat": CAVEAT, "decks": decks,
    }


def top_cards(deck: dict, limit: int = 10, min_seen: int = 1) -> List[dict]:
    """The highest-scoring cards worth showing: seen at least ``min_seen`` times and scoring above zero."""
    rows = [r for r in deck.get("cards", []) if r["seen"] >= min_seen and (r.get("score") or 0) > 0]
    return rows[:limit]
