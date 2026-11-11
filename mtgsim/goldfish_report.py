"""HTML for the engine-free consistency analysis (the result of ``goldfish.analyze``)."""

from __future__ import annotations

from typing import Dict, List, Optional

from .report import _tile, esc, num, pct, tip

COLOUR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green", "C": "Colourless"}


def _curve(curve: List[int]) -> str:
    peak = max(curve) or 1
    cols, labels = [], []
    for value, count in enumerate(curve):
        label = "7+" if value == 7 else str(value)
        cols.append(
            f'<div class="c"{tip(f"Mana value {label}", [["Cards", str(count)]])}>'
            f'<span>{count if count else ""}</span><i style="height:{count / peak * 100:.1f}%"></i></div>')
        labels.append(f"<span>{label}</span>")
    return f'<div class="cols">{"".join(cols)}</div><div class="colx">{"".join(labels)}</div>'


def _colours(comp: dict) -> str:
    pips, sources, lands = comp.get("pips", {}), comp.get("sources", {}), comp.get("land_sources", {})
    rows = []
    for colour in "WUBRGC":
        if not pips.get(colour) and not (sources.get(colour) and colour != "C"):
            continue
        rows.append(f'<tr><td>{COLOUR_NAMES[colour]}</td><td class="n">{num(pips.get(colour, 0), 0)}</td>'
                    f'<td class="n">{sources.get(colour, 0)}</td><td class="n">{lands.get(colour, 0)}</td></tr>')
    if not rows:
        return ""
    return ('<div class="scroll"><table><thead><tr><th>Colour</th><th>Coloured symbols in costs</th>'
            '<th>Cards that make it</th><th>of which lands</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _by_turn(by_turn: dict) -> str:
    overall, play, draw = by_turn.get("overall", []), by_turn.get("play", []), by_turn.get("draw", [])
    rows = []
    for i, row in enumerate(overall):
        on_play = play[i]["hit_all_land_drops"] if i < len(play) else None
        on_draw = draw[i]["hit_all_land_drops"] if i < len(draw) else None
        rows.append(
            f'<tr><td class="n">{row["turn"]}</td><td class="n">{num(row["lands"], 2)}</td>'
            f'<td class="n">{pct(on_play, 0)}</td><td class="n">{pct(on_draw, 0)}</td>'
            f'<td class="n">{num(row["mana_available"], 2)}</td><td class="n">{num(row["mana_spent"], 2)}</td>'
            f'<td class="n">{num(row["cards_in_hand"], 1)}</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>Turn</th><th>Lands in play</th>'
            '<th>Every land drop made (on the play)</th><th>(on the draw)</th><th>Mana available</th>'
            '<th>Mana spent</th><th>Cards left in hand</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _cards(cards: List[dict]) -> str:
    rows = []
    for card in cards:
        castable = (card.get("castable") or [None, None, None]) + [None, None, None]
        enough = (card.get("enough_mana") or [None]) + [None]
        on_curve = castable[0]
        lost: Optional[float] = None
        if on_curve is not None and enough[0] is not None:
            lost = max(0.0, enough[0] - on_curve)
        meter = ""
        if on_curve is not None:
            meter = f'<span class="meter"><i style="width:{on_curve * 100:.1f}%"></i></span>'
        rows.append(
            f'<tr><td class="name">{card["copies"]} {esc(card["name"])}</td><td class="n">{esc(card.get("cost", ""))}</td>'
            f'<td class="n">{card.get("curve_turn", "")}</td><td class="n">{meter}<b>{pct(on_curve, 0)}</b></td>'
            f'<td class="n">{pct(castable[1], 0)}</td><td class="n">{pct(castable[2], 0)}</td>'
            f'<td class="n">{pct(lost, 0)}</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>Card</th><th>Cost</th><th>Curve turn</th>'
            '<th>Castable on curve</th><th>One turn later</th><th>Two turns later</th>'
            '<th>Lost to colours on curve</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def render(results: Dict[str, dict], names: Dict[str, str]) -> str:
    out = []
    for key, result in results.items():
        comp, opening = result.get("composition", {}), result.get("opening_hand", {})
        definitions = result.get("definitions", {})
        screw, flood = result.get("mana_screw", {}), result.get("mana_flood", {})
        lands = str(comp.get("lands", "–")) + (f" + {comp['modal_lands']} spell/lands" if comp.get("modal_lands") else "")
        tiles = [
            _tile("Lands", lands, f"{comp.get('tapped_lands', 0)} always enter tapped"),
            _tile("Average mana value", num(comp.get("avg_mana_value"), 2), "nonland cards"),
            _tile("Mulligan rate", pct(opening.get("mulligan_rate"), 0),
                  f"average kept hand {num(opening.get('avg_kept_hand_size'), 2)} cards"),
            _tile("Mana screw", pct(screw.get("overall")), "fewer than 3 lands after turn 4"),
            _tile("Mana flood", pct(flood.get("overall")), "60%+ lands among cards seen by turn 6"),
        ]
        title = "Mana and consistency" + (f": {esc(names.get(key, key))}" if len(results) > 1 else "")
        out.append(
            f'<section class="card"><h2>{title}</h2>'
            f'<p class="note">From {result.get("games", 0):,} simulated solo games with no opponent and no rules engine: '
            "a model of lands, mana and costs only. Card draw, cost reduction and everything else the cards do are "
            "ignored, so decks that rely on them look clunkier here than they play.</p>"
            f'<div class="tiles">{"".join(tiles)}</div>'
            "<h3>Mana curve (nonland cards by mana value)</h3>" + _curve(comp.get("curve", [0] * 8))
            + "<h3>Colours</h3>" + _colours(comp)
            + "<h3>Turn by turn</h3>" + _by_turn(result.get("by_turn", {}))
            + "<h3>Can the mana cast each card on time?</h3>"
            + f'<p class="note">{esc(definitions.get("castable", ""))}</p>' + _cards(result.get("cards", []))
            + "".join(f'<p class="note">Note: {esc(w)}</p>' for w in result.get("warnings", []))
            + f'<details><summary>Definitions</summary><p class="note">Keep rule: {esc(definitions.get("keep_rule", ""))}</p>'
            + f'<p class="note">Mana screw: {esc(definitions.get("mana_screw", ""))}</p>'
            + f'<p class="note">Mana flood: {esc(definitions.get("mana_flood", ""))}</p>'
            + f'<p class="note">Mana available: {esc(definitions.get("mana_available", ""))}</p></details></section>')
    return "".join(out)
