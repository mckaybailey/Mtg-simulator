"""Turning stored game records into win rates, comparisons and card-level statistics.

All functions take the plain dict records written to ``games.jsonl`` and return plain dicts, so
the results can be saved as ``summary.json`` and rendered by ``report.py`` without this module.

Conventions used throughout:

* A *decided* game has a winner. Draws and games stopped by the time limit are counted and
  reported separately and are left out of win-rate denominators.
* "Turns" for a deck are that deck's own turns (a turn-4 kill means the deck's fourth turn).
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import stats


def seat_of_a(record: dict) -> int:
    """Which seat the pairing's first deck had (seats alternate by game; see experiment.plan_pairing)."""
    return 0 if record["game"] % 2 == 0 else 1


def _rate_block(wins: int, games: int) -> dict:
    lo, hi = stats.wilson(wins, games)
    return {"games": games, "wins": wins, "win_rate": stats.rate(wins, games), "ci": [lo, hi]}


def summarize_pairing(records: Iterable[dict], a_key: str, b_key: str) -> dict:
    """Results of one pairing from the first deck's point of view."""
    wins = losses = draws = timeouts = errors = 0
    play_games = play_wins = draw_games = draw_wins = 0
    turns_all: List[int] = []
    kill_a: Counter = Counter()
    kill_b: Counter = Counter()
    how_a: Counter = Counter()
    how_b: Counter = Counter()
    mull_a = mull_b = mull_games = 0
    ms: List[int] = []
    total = 0

    for record in records:
        if record.get("a") != a_key or record.get("b") != b_key:
            continue
        total += 1
        status = record.get("status")
        if status == "timeout":
            timeouts += 1
            continue
        if status != "ok":
            errors += 1
            continue
        seat_a = seat_of_a(record)
        seat_b = 1 - seat_a
        players = record.get("players") or [{}, {}]
        if record.get("ms") is not None:
            ms.append(record["ms"])
        mull_games += 1
        mull_a += 1 if (players[seat_a].get("mulligans") or 0) > 0 else 0
        mull_b += 1 if (players[seat_b].get("mulligans") or 0) > 0 else 0

        winner = record.get("winner_seat", -1)
        if winner not in (0, 1):
            draws += 1
            continue
        a_won = winner == seat_a
        on_play = record.get("first_seat") == seat_a
        if on_play:
            play_games += 1
            play_wins += 1 if a_won else 0
        elif record.get("first_seat") == seat_b:
            draw_games += 1
            draw_wins += 1 if a_won else 0
        winner_turns = players[winner].get("turns")
        loser = players[1 - winner]
        reason = loser.get("lossReason") or record.get("end_reason") or "unknown"
        if players[winner].get("altWin"):
            reason = "AltWin: " + players[winner]["altWin"]
        if a_won:
            wins += 1
            how_a[reason] += 1
            if winner_turns:
                kill_a[winner_turns] += 1
        else:
            losses += 1
            how_b[reason] += 1
            if winner_turns:
                kill_b[winner_turns] += 1
        if winner_turns:
            turns_all.append(winner_turns)

    decided = wins + losses
    block = _rate_block(wins, decided)
    play = _rate_block(play_wins, play_games)
    draw = _rate_block(draw_wins, draw_games)
    balanced = None
    if play["win_rate"] is not None and draw["win_rate"] is not None:
        balanced = (play["win_rate"] + draw["win_rate"]) / 2.0
    return {
        "a": a_key, "b": b_key,
        "games": total, "decided": decided, "wins": wins, "losses": losses,
        "draws": draws, "timeouts": timeouts, "errors": errors,
        "win_rate": block["win_rate"], "ci": block["ci"],
        "p_even": stats.binomial_p_even(wins, decided),
        "on_play": play, "on_draw": draw, "balanced_win_rate": balanced,
        "avg_win_turn": stats.mean(turns_all),
        "avg_turn_a_wins": _mean_of_counter(kill_a), "avg_turn_b_wins": _mean_of_counter(kill_b),
        "kill_turns_a": _sorted_counter(kill_a), "kill_turns_b": _sorted_counter(kill_b),
        "how_a_wins": dict(how_a.most_common()), "how_b_wins": dict(how_b.most_common()),
        "mulligan_rate_a": stats.rate(mull_a, mull_games), "mulligan_rate_b": stats.rate(mull_b, mull_games),
        "avg_ms": stats.mean(ms),
    }


def _sorted_counter(counter: Counter) -> Dict[str, int]:
    return {str(k): counter[k] for k in sorted(counter)}


def _mean_of_counter(counter: Counter) -> Optional[float]:
    n = sum(counter.values())
    return sum(k * v for k, v in counter.items()) / n if n else None


def flip(pairing: dict) -> dict:
    """The same pairing seen from the second deck's side."""
    wins, losses = pairing["losses"], pairing["wins"]
    decided = pairing["decided"]
    block = _rate_block(wins, decided)
    play = _rate_block(pairing["on_draw"]["games"] - pairing["on_draw"]["wins"], pairing["on_draw"]["games"])
    draw = _rate_block(pairing["on_play"]["games"] - pairing["on_play"]["wins"], pairing["on_play"]["games"])
    balanced = None if pairing["balanced_win_rate"] is None else 1.0 - pairing["balanced_win_rate"]
    out = dict(pairing)
    out.update({
        "a": pairing["b"], "b": pairing["a"], "wins": wins, "losses": losses,
        "win_rate": block["win_rate"], "ci": block["ci"],
        "on_play": play, "on_draw": draw, "balanced_win_rate": balanced,
        "avg_turn_a_wins": pairing["avg_turn_b_wins"], "avg_turn_b_wins": pairing["avg_turn_a_wins"],
        "kill_turns_a": pairing["kill_turns_b"], "kill_turns_b": pairing["kill_turns_a"],
        "how_a_wins": pairing["how_b_wins"], "how_b_wins": pairing["how_a_wins"],
        "mulligan_rate_a": pairing["mulligan_rate_b"], "mulligan_rate_b": pairing["mulligan_rate_a"],
    })
    return out


def summarize_field(hero: str, pairings: Sequence[dict], weights: Optional[Dict[str, Optional[float]]] = None) -> dict:
    """A deck's overall record against a set of opponents.

    Three overall numbers are given because they answer different questions: ``pooled`` is the
    raw record, ``mean`` treats every opponent as equally important, and ``weighted`` (when
    metagame shares are known) estimates the win rate against a field shaped like the real one.
    """
    rows = [p for p in pairings if p["a"] == hero]
    samples = [(p["wins"], p["decided"]) for p in rows]
    wins = sum(p["wins"] for p in rows)
    decided = sum(p["decided"] for p in rows)
    play_w = sum(p["on_play"]["wins"] for p in rows)
    play_g = sum(p["on_play"]["games"] for p in rows)
    draw_w = sum(p["on_draw"]["wins"] for p in rows)
    draw_g = sum(p["on_draw"]["games"] for p in rows)
    out = {
        "hero": hero,
        "opponents": [p["b"] for p in rows],
        "games": sum(p["games"] for p in rows),
        "decided": decided, "wins": wins, "losses": decided - wins,
        "draws": sum(p["draws"] for p in rows),
        "timeouts": sum(p["timeouts"] for p in rows),
        "errors": sum(p["errors"] for p in rows),
        "pooled": _rate_block(wins, decided),
        "mean": stats.weighted_rate(samples),
        "weighted": None,
        "on_play": _rate_block(play_w, play_g), "on_draw": _rate_block(draw_w, draw_g),
        "mulligan_rate": stats.mean([p["mulligan_rate_a"] for p in rows if p["mulligan_rate_a"] is not None]),
        "avg_win_turn": stats.mean([p["avg_turn_a_wins"] for p in rows if p["avg_turn_a_wins"] is not None]),
    }
    if weights:
        w = [weights.get(p["b"]) or 0.0 for p in rows]
        if any(x > 0 for x in w):
            out["weighted"] = stats.weighted_rate(samples, w)
            out["weighted"]["coverage"] = sum(w)
    return out


def summarize_ab(
    first: str,
    second: str,
    pairings: Sequence[dict],
    weights: Optional[Dict[str, Optional[float]]] = None,
) -> dict:
    """Compare two decks that played the same opponents."""
    by_first = {p["b"]: p for p in pairings if p["a"] == first and p["b"] != second}
    by_second = {p["b"]: p for p in pairings if p["a"] == second and p["b"] != first}
    shared = [k for k in by_first if k in by_second]
    rows = []
    for opponent in shared:
        x, y = by_first[opponent], by_second[opponent]
        test = stats.diff_test(x["wins"], x["decided"], y["wins"], y["decided"])
        rows.append({
            "opponent": opponent,
            "first": {"wins": x["wins"], "decided": x["decided"], "win_rate": x["win_rate"], "ci": x["ci"]},
            "second": {"wins": y["wins"], "decided": y["decided"], "win_rate": y["win_rate"], "ci": y["ci"]},
            "diff": test["diff"], "ci": test["ci"], "p": test["p"],
        })
    s1 = [(by_first[k]["wins"], by_first[k]["decided"]) for k in shared]
    s2 = [(by_second[k]["wins"], by_second[k]["decided"]) for k in shared]
    overall_mean = stats.weighted_diff(s1, s2)
    overall_weighted = None
    if weights and any((weights.get(k) or 0) > 0 for k in shared):
        overall_weighted = stats.weighted_diff(s1, s2, [weights.get(k) or 0.0 for k in shared])

    head = next((p for p in pairings if p["a"] == first and p["b"] == second), None)
    if head is None:
        other = next((p for p in pairings if p["a"] == second and p["b"] == first), None)
        head = flip(other) if other else None

    games_each = min((sum(d for _, d in s1), sum(d for _, d in s2))) if shared else 0
    diff, p_value = overall_mean["diff"], overall_mean["p"]
    significant = diff is not None and p_value is not None and p_value < 0.05
    detectable = None
    for delta in (0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20):
        need = stats.games_to_detect(delta)
        if need is not None and need <= games_each:
            detectable = delta
            break
    return {
        "first": first, "second": second, "rows": rows,
        "overall_mean": overall_mean, "overall_weighted": overall_weighted,
        "head_to_head": head, "games_each": games_each,
        "significant": significant,
        "better": None if not significant else (first if diff > 0 else second),
        "detectable_gap": detectable,
        "games_for_3_points": stats.games_to_detect(0.03), "games_for_5_points": stats.games_to_detect(0.05),
    }


def ab_verdict(ab: dict, name_first: str, name_second: str) -> str:
    """One or two plain sentences saying what an A/B comparison does and does not show."""
    diff, p_value = ab["overall_mean"]["diff"], ab["overall_mean"]["p"]
    if diff is None:
        return "No shared opponents were played, so the two decks cannot be compared."
    if ab["significant"]:
        better = name_first if ab["better"] == ab["first"] else name_second
        return (f"{better} did better against this field by {abs(diff) * 100:.1f} points "
                f"(p = {p_value:.3f}); a gap this large is unlikely to be luck.")
    text = (f"No reliable difference: the gap of {diff * 100:+.1f} points is within what luck alone "
            f"produces at this sample size (p = {p_value:.2f}).")
    if ab["detectable_gap"]:
        text += (f" With {ab['games_each']} decided games each, only gaps of about "
                 f"{ab['detectable_gap'] * 100:.0f} points or more would reliably show up; detecting a "
                 f"3-point gap takes about {ab['games_for_3_points']} games each.")
    else:
        text += " The sample is too small to detect even a 20-point gap reliably."
    return text


def summarize_matrix(keys: Sequence[str], pairings: Sequence[dict]) -> dict:
    """Round-robin results: a win-rate grid plus each deck's average result against the others."""
    lookup: Dict[Tuple[str, str], dict] = {}
    for p in pairings:
        lookup[(p["a"], p["b"])] = p
        if p["a"] != p["b"]:
            lookup.setdefault((p["b"], p["a"]), flip(p))
    grid: Dict[str, Dict[str, Optional[dict]]] = {}
    ranking = []
    for row in keys:
        grid[row] = {}
        samples = []
        for col in keys:
            cell = lookup.get((row, col))
            if cell is None or row == col:
                grid[row][col] = None
                continue
            grid[row][col] = {"wins": cell["wins"], "decided": cell["decided"],
                              "win_rate": cell["win_rate"], "ci": cell["ci"]}
            samples.append((cell["wins"], cell["decided"]))
        overall = stats.weighted_rate(samples)
        ranking.append({
            "key": row, "mean_win_rate": overall["rate"], "ci": overall["ci"],
            "wins": sum(w for w, _ in samples), "decided": sum(d for _, d in samples),
        })
    ranking.sort(key=lambda r: -(r["mean_win_rate"] if r["mean_win_rate"] is not None else -1))
    return {"order": [r["key"] for r in ranking], "grid": grid, "ranking": ranking}


def card_stats(records: Iterable[dict], deck_key: str, decklist: Dict[str, int]) -> dict:
    """Per-card results for one deck across every decided game it played.

    For each card: how the deck did in games where the card was in the opening hand, was seen at
    all (opening hand or drawn), was never seen, and was actually played. ``iwd`` ("improvement
    when drawn") is the seen win rate minus the never-seen win rate. These are correlations, not
    causes: long games see more cards, so cards that are only good late are flattered and
    cheap early plays are understated. They are most useful for comparing cards with similar
    roles, and for spotting cards that are often seen but rarely played.
    """
    names = list(decklist)
    tally = {n: {"oh_g": 0, "oh_w": 0, "seen_g": 0, "seen_w": 0, "played_g": 0, "played_w": 0,
                 "copies_seen": 0} for n in names}
    games = wins = 0
    for record in records:
        if record.get("status") != "ok" or record.get("winner_seat") not in (0, 1):
            continue
        for seat, key in enumerate(record.get("seats", [])):
            if key != deck_key:
                continue
            player = (record.get("players") or [{}, {}])[seat]
            opening, drawn, played = player.get("opening", {}), player.get("drawn", {}), player.get("played", {})
            won = record["winner_seat"] == seat
            games += 1
            wins += 1 if won else 0
            for name in names:
                in_opening = opening.get(name, 0)
                seen = in_opening + drawn.get(name, 0)
                t = tally[name]
                if in_opening:
                    t["oh_g"] += 1
                    t["oh_w"] += 1 if won else 0
                if seen:
                    t["seen_g"] += 1
                    t["seen_w"] += 1 if won else 0
                    t["copies_seen"] += seen
                    if played.get(name, 0):
                        t["played_g"] += 1
                        t["played_w"] += 1 if won else 0
    rows = []
    for name in names:
        t = tally[name]
        unseen_g, unseen_w = games - t["seen_g"], wins - t["seen_w"]
        test = stats.diff_test(t["seen_w"], t["seen_g"], unseen_w, unseen_g)
        rows.append({
            "card": name, "copies": decklist[name],
            "opening": _rate_block(t["oh_w"], t["oh_g"]),
            "seen": _rate_block(t["seen_w"], t["seen_g"]),
            "not_seen": _rate_block(unseen_w, unseen_g),
            "played": _rate_block(t["played_w"], t["played_g"]),
            "iwd": test["diff"], "iwd_ci": test["ci"], "iwd_p": test["p"],
            "seen_rate": stats.rate(t["seen_g"], games),
            "play_rate": stats.rate(t["played_g"], t["seen_g"]),
        })
    rows.sort(key=lambda r: -(r["iwd"] if r["iwd"] is not None else -9))
    return {"deck": deck_key, "games": games, "wins": wins, "win_rate": stats.rate(wins, games), "cards": rows}


def summarize_clock(records: Iterable[dict], hero: str, passive: str) -> dict:
    """How fast a deck wins when the opponent does nothing: the distribution of its winning turn."""
    pairing = summarize_pairing(records, hero, passive)
    kills = {int(k): v for k, v in pairing["kill_turns_a"].items()}
    games = pairing["games"]
    won = sum(kills.values())
    cumulative = []
    running = 0
    for turn in range(1, (max(kills) if kills else 0) + 1):
        running += kills.get(turn, 0)
        cumulative.append({"turn": turn, "wins": kills.get(turn, 0), "by_turn": stats.rate(running, games)})
    ordered = sorted(t for t, n in kills.items() for _ in range(n))
    median = ordered[len(ordered) // 2] if ordered else None
    return {
        "hero": hero, "games": games, "won": won, "not_won": games - won,
        "timeouts": pairing["timeouts"], "errors": pairing["errors"],
        "mean_turn": _mean_of_counter(Counter(kills)), "median_turn": median,
        "fastest_turn": min(kills) if kills else None,
        "turns": cumulative,
    }
