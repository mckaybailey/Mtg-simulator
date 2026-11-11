"""Rendering ``summary.json`` as a single self-contained HTML report.

The page has no external dependencies (no scripts, fonts or images are loaded), so it can be
opened from disk, e-mailed or attached anywhere. Charts are plain HTML/CSS positioned on a
shared percentage scale; every chart is followed by a table with the same numbers.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import analysis

# ----------------------------------------------------------------- formatting


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def pct(value: Optional[float], digits: int = 1) -> str:
    return "–" if value is None else f"{value * 100:.{digits}f}%"


def pts(value: Optional[float], digits: int = 1) -> str:
    return "–" if value is None else f"{value * 100:+.{digits}f}"


def num(value: Optional[float], digits: int = 1) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def ci_text(ci: Sequence[Optional[float]], digits: int = 0) -> str:
    if not ci or ci[0] is None:
        return "–"
    return f"{ci[0] * 100:.{digits}f}–{ci[1] * 100:.{digits}f}%"


def tip(title: str, rows: Sequence[Sequence[str]]) -> str:
    """A ``data-tip`` attribute: the tooltip script builds its content from this with textContent."""
    return f' tabindex="0" data-tip="{esc(json.dumps([title] + [list(r) for r in rows]))}"'


def _pos(value: float) -> str:
    return f"{max(0.0, min(1.0, value)) * 100:.2f}%"


# ---------------------------------------------------------------------- style

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s1soft:#b7d3f6;
--pos:#2a78d6;--neg:#e34948;--mid:#f0efec;--warn-bg:#fdf3d8;--wash:rgba(11,11,11,.04)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;
--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s1soft:#184f95;--pos:#3987e5;--neg:#e66767;
--mid:#383835;--warn-bg:#3a3117;--wash:rgba(255,255,255,.05)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;
--s1soft:#184f95;--pos:#3987e5;--neg:#e66767;--mid:#383835;--warn-bg:#3a3117;--wash:rgba(255,255,255,.05)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;line-height:1.2;margin:0 0 4px}
h2{font-size:18px;margin:0 0 4px}
h3{font-size:15px;margin:20px 0 6px}
p{margin:6px 0}
.sub{color:var(--ink2);margin:0 0 16px}
.note{color:var(--ink2);font-size:13px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin:16px 0}
.caveat{background:var(--warn-bg);border-radius:8px;padding:10px 14px;font-size:13.5px;margin:12px 0}
.headline{display:flex;flex-wrap:wrap;gap:24px 40px;align-items:flex-end}
.hero .v{font-size:52px;font-weight:650;line-height:1.05}
.hero .l{color:var(--ink2)}
.tiles{display:flex;flex-wrap:wrap;gap:16px 32px}
.tile .v{font-size:22px;font-weight:600}
.tile .l{color:var(--ink2);font-size:13px}
.tile .s{color:var(--muted);font-size:12px}
.takeaway{margin:14px 0 0;padding-left:18px}
.takeaway li{margin:3px 0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:6px 10px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--grid)}
th{color:var(--ink2);font-weight:600;font-size:12.5px}
th:first-child,td:first-child{text-align:left}
td.name{white-space:normal;min-width:150px}
td.n,th.n{font-variant-numeric:tabular-nums}
tr.low td{color:var(--muted)}
tbody tr:hover td{background:var(--wash)}
.legend{display:flex;gap:18px;font-size:13px;color:var(--ink2);margin:8px 0}
.key{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:baseline}
.rows{display:grid;grid-template-columns:minmax(120px,220px) 1fr auto;column-gap:14px;align-items:center;margin-top:8px}
.rows .lab{font-size:13.5px;padding:7px 0;overflow-wrap:anywhere}
.rows .fig{font-size:13.5px;font-variant-numeric:tabular-nums;text-align:right;color:var(--ink2)}
.rows .fig b{color:var(--ink);font-weight:600}
.strip{position:relative;height:30px;border-radius:4px;outline:none}
.strip:hover,.strip:focus-visible{background:var(--wash)}
.strip:focus-visible{box-shadow:0 0 0 2px var(--s1)}
.tick{position:absolute;top:0;bottom:0;width:1px;background:var(--grid)}
.tick.even{background:var(--axis)}
.whisk{position:absolute;top:14px;height:2px;background:var(--s1soft);border-radius:1px}
.link{position:absolute;top:14px;height:2px;background:var(--axis)}
.dot{position:absolute;top:9px;width:12px;height:12px;margin-left:-6px;border-radius:50%;background:var(--s1);
box-shadow:0 0 0 2px var(--surface)}
.dot.b{background:var(--s2)}
.axis{position:relative;height:18px;font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.axis span{position:absolute;transform:translateX(-50%)}
.axis span:first-child{transform:none}.axis span:last-child{transform:translateX(-100%)}
.heat td,.heat th{text-align:center;padding:0;border:2px solid var(--surface)}
.heat th{padding:4px 6px;font-size:12px}
.heat th.row{text-align:left;white-space:normal;min-width:150px;font-weight:500;color:var(--ink)}
.heat td{height:34px;min-width:46px;font-variant-numeric:tabular-nums;border-radius:4px;outline:none;
background:color-mix(in oklab,var(--pole) calc(var(--t)*60%),var(--mid))}
.heat td.self{background:none;color:var(--muted)}
.heat td:hover,.heat td:focus-visible{box-shadow:inset 0 0 0 2px var(--ink)}
.heat tbody tr:hover td{background:color-mix(in oklab,var(--pole) calc(var(--t)*60%),var(--mid))}
.heat tbody tr:hover td.self{background:none}
.bar0{position:relative;display:inline-block;width:120px;height:14px;vertical-align:middle}
.bar0:before{content:"";position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--axis)}
.bar0 i{position:absolute;top:3px;height:8px;background:var(--pos);border-radius:0 4px 4px 0}
.bar0 i.neg{background:var(--neg);border-radius:4px 0 0 4px}
.cols{display:flex;align-items:flex-end;gap:2px;height:150px;border-bottom:1px solid var(--axis);margin-top:22px}
.cols .c{flex:1 1 0;max-width:44px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;
height:100%;outline:none}
.cols .c i{display:block;width:100%;max-width:24px;background:var(--s1);border-radius:4px 4px 0 0;min-height:1px}
.cols .c:hover i,.cols .c:focus-visible i{filter:brightness(1.15)}
.cols .c span{font-size:11.5px;color:var(--ink2);margin-bottom:3px;font-variant-numeric:tabular-nums}
.colx{display:flex;gap:2px;font-size:11.5px;color:var(--muted);margin-top:4px}
.colx span{flex:1 1 0;max-width:44px;text-align:center}
.meter{position:relative;display:inline-block;width:110px;height:8px;border-radius:4px;background:var(--s1soft);
vertical-align:middle;margin-right:8px}
.meter i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--s1)}
details{margin:8px 0}
summary{cursor:pointer;color:var(--ink2);font-size:13.5px}
.decklist{columns:2 220px;font-size:13px;margin:8px 0}
.decklist div{break-inside:avoid}
#tip{position:fixed;z-index:10;pointer-events:none;background:var(--ink);color:var(--surface);border-radius:6px;
padding:8px 10px;font-size:12.5px;max-width:300px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
#tip .t{font-weight:600;margin-bottom:4px}
#tip .r{display:flex;justify-content:space-between;gap:14px}
#tip .r span{opacity:.8}
@media (max-width:640px){.rows{grid-template-columns:1fr auto;column-gap:10px}
.rows .lab{grid-column:1/-1;padding:10px 0 0;font-weight:500}.rows .pad{display:none}
.hero .v{font-size:42px}.card{padding:14px}}
"""

JS = """
(function(){var tip=document.getElementById('tip');
function fill(el){var d;try{d=JSON.parse(el.getAttribute('data-tip'))}catch(e){return false}
tip.textContent='';var t=document.createElement('div');t.className='t';t.textContent=d[0];tip.appendChild(t);
for(var i=1;i<d.length;i++){var r=document.createElement('div');r.className='r';var l=document.createElement('span');
l.textContent=d[i][0];var v=document.createElement('strong');v.textContent=d[i][1];r.appendChild(l);r.appendChild(v);
tip.appendChild(r)}return true}
function place(x,y){tip.hidden=false;var w=tip.offsetWidth,h=tip.offsetHeight;var px=x+14,py=y+16;
if(px+w>window.innerWidth-8)px=Math.max(8,x-w-14);if(py+h>window.innerHeight-8)py=Math.max(8,y-h-12);
tip.style.left=px+'px';tip.style.top=py+'px'}
document.addEventListener('pointermove',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');
if(el&&fill(el))place(e.clientX,e.clientY);else tip.hidden=true});
document.addEventListener('focusin',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');
if(el&&fill(el)){var b=el.getBoundingClientRect();place(b.left+b.width/2,b.bottom-10)}});
document.addEventListener('focusout',function(){tip.hidden=true});
document.addEventListener('pointerleave',function(){tip.hidden=true})})();
"""


# ------------------------------------------------------------------ fragments


def _tile(label: str, value: str, sub: str = "") -> str:
    return (f'<div class="tile"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div>'
            + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>")


def _hero(value: str, label: str, sub: str = "") -> str:
    return (f'<div class="hero"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div>'
            + (f'<div class="note">{esc(sub)}</div>' if sub else "") + "</div>")


def _axis() -> str:
    marks = "".join(f'<span style="left:{p}%">{p}%</span>' for p in (0, 25, 50, 75, 100))
    return f'<div class="pad"></div><div class="axis">{marks}</div><div></div>'


def _ticks() -> str:
    return "".join(f'<div class="tick{" even" if p == 50 else ""}" style="left:{p}%"></div>' for p in (0, 25, 50, 75, 100))


def _pairing_tip(p: dict, name_a: str, name_b: str) -> str:
    return tip(f"{name_a} vs {name_b}", [
        ["Win rate", pct(p["win_rate"])],
        ["95% interval", ci_text(p["ci"])],
        ["Record", f"{p['wins']}–{p['losses']}"],
        ["On the play", f"{pct(p['on_play']['win_rate'], 0)} of {p['on_play']['games']}"],
        ["On the draw", f"{pct(p['on_draw']['win_rate'], 0)} of {p['on_draw']['games']}"],
        ["Wins on turn (avg)", num(p["avg_turn_a_wins"])],
        ["Loses on turn (avg)", num(p["avg_turn_b_wins"])],
    ])


def _matchup_chart(pairings: List[dict], names: Dict[str, str]) -> str:
    """One row per opponent: win rate as a dot with its 95% interval on a shared 0-100% scale."""
    rows = [_axis()]
    for p in pairings:
        name_a, name_b = names.get(p["a"], p["a"]), names.get(p["b"], p["b"])
        marks = _ticks()
        if p["win_rate"] is not None:
            lo, hi = p["ci"]
            marks += f'<div class="whisk" style="left:{_pos(lo)};width:{(hi - lo) * 100:.2f}%"></div>'
            marks += f'<div class="dot" style="left:{_pos(p["win_rate"])}"></div>'
        rows.append(
            f'<div class="lab">{esc(name_b)}</div>'
            f'<div class="strip"{_pairing_tip(p, name_a, name_b)}>{marks}</div>'
            f'<div class="fig"><b>{pct(p["win_rate"])}</b> &nbsp;{p["wins"]}–{p["losses"]}</div>'
        )
    return '<div class="rows">' + "".join(rows) + "</div>"


def _matchup_table(pairings: List[dict], names: Dict[str, str], entrants: dict) -> str:
    unfinished = any(p["draws"] + p["timeouts"] + p["errors"] for p in pairings)
    head = ("<tr><th>Opponent</th><th>Type</th><th>Meta share</th><th>Games</th><th>W–L</th><th>Win rate</th>"
            "<th>95% interval</th><th>On play</th><th>On draw</th><th>Wins on turn</th><th>Loses on turn</th>"
            "<th>Mulligans</th>" + ("<th>Unfinished</th>" if unfinished else "") + "</tr>")
    body = []
    for p in pairings:
        info = entrants.get(p["b"], {})
        share = info.get("weight")
        body.append(
            f'<tr><td class="name">{esc(names.get(p["b"], p["b"]))}</td><td>{esc(info.get("category") or "–")}</td>'
            f'<td class="n">{"–" if not share else f"{share:g}%"}</td><td class="n">{p["games"]}</td>'
            f'<td class="n">{p["wins"]}–{p["losses"]}</td><td class="n"><b>{pct(p["win_rate"])}</b></td>'
            f'<td class="n">{ci_text(p["ci"])}</td><td class="n">{pct(p["on_play"]["win_rate"], 0)}</td>'
            f'<td class="n">{pct(p["on_draw"]["win_rate"], 0)}</td><td class="n">{num(p["avg_turn_a_wins"])}</td>'
            f'<td class="n">{num(p["avg_turn_b_wins"])}</td><td class="n">{pct(p["mulligan_rate_a"], 0)}</td>'
            + (f'<td class="n">{p["draws"] + p["timeouts"] + p["errors"]}</td>' if unfinished else "") + "</tr>"
        )
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _classify(pairings: List[dict], names: Dict[str, str]) -> List[str]:
    """Plain-language reading of which matchups are actually decided at this sample size."""
    good = [names.get(p["b"], p["b"]) for p in pairings if p["ci"][0] is not None and p["ci"][0] > 0.5]
    bad = [names.get(p["b"], p["b"]) for p in pairings if p["ci"][1] is not None and p["ci"][1] < 0.5]
    open_ = len([p for p in pairings if p["ci"][0] is not None]) - len(good) - len(bad)
    lines = []
    if good:
        lines.append("Clearly favoured against: " + ", ".join(good) + ".")
    if bad:
        lines.append("Clearly unfavoured against: " + ", ".join(bad) + ".")
    if open_:
        lines.append(f"{open_} matchup{'s are' if open_ != 1 else ' is'} too close to call at this sample size "
                     "(the 95% interval includes 50%).")
    return lines


def _takeaways(lines: List[str]) -> str:
    return '<ul class="takeaway">' + "".join(f"<li>{esc(l)}</li>" for l in lines) + "</ul>" if lines else ""


# ------------------------------------------------------------------- sections


def _section_gauntlet(summary: dict, names: Dict[str, str]) -> str:
    hero = summary["hero"]
    field = summary["field"][hero]
    pairings = sorted([p for p in summary["pairings"] if p["a"] == hero], key=lambda p: -(p["win_rate"] or 0))
    tiles = [
        _tile("Raw record", f"{field['wins']}–{field['losses']}", f"{pct(field['pooled']['win_rate'])} of decided games"),
    ]
    if field.get("weighted"):
        w = field["weighted"]
        tiles.append(_tile("Weighted by meta share", pct(w["rate"]),
                           f"95% interval {ci_text(w['ci'])}; covers {w.get('coverage', 0):.0f}% of the metagame"))
    tiles += [
        _tile("On the play", pct(field["on_play"]["win_rate"]), f"{field['on_play']['games']} games"),
        _tile("On the draw", pct(field["on_draw"]["win_rate"]), f"{field['on_draw']['games']} games"),
        _tile("Mulligan rate", pct(field["mulligan_rate"], 0)),
        _tile("Average winning turn", num(field["avg_win_turn"])),
    ]
    out = ['<section class="card">', '<div class="headline">',
           _hero(pct(field["mean"]["rate"]), "Win rate against the field, every opponent counted equally",
                 f"95% interval {ci_text(field['mean']['ci'], 1)} over {field['decided']} decided games"),
           '<div class="tiles">' + "".join(tiles) + "</div></div>",
           _takeaways(_classify(pairings, names)), "</section>"]
    out += ['<section class="card"><h2>Matchups</h2>',
            f'<p class="note">Win rate of {esc(names.get(hero, hero))} against each opponent. The line through each '
            "dot is the 95% interval: a matchup is only clearly good or bad when the whole line sits on one side of 50%.</p>",
            _matchup_chart(pairings, names), "<h3>All numbers</h3>",
            _matchup_table(pairings, names, summary["entrants"]), "</section>"]
    return "".join(out)


def _section_match(summary: dict, names: Dict[str, str]) -> str:
    p = summary["pairings"][0]
    name_a, name_b = names.get(p["a"], p["a"]), names.get(p["b"], p["b"])
    even = p.get("p_even")
    if even is None:
        reading = "No decided games."
    elif even < 0.05:
        reading = (f"A real edge for {name_a if (p['win_rate'] or 0) > 0.5 else name_b}: "
                   f"an even matchup would rarely produce this result (p = {even:.3f}).")
    else:
        reading = f"Consistent with an even matchup at this sample size (p = {even:.2f})."
    tiles = [
        _tile("Record", f"{p['wins']}–{p['losses']}", f"{p['draws'] + p['timeouts'] + p['errors']} unfinished"),
        _tile("On the play", pct(p["on_play"]["win_rate"]), f"{p['on_play']['games']} games"),
        _tile("On the draw", pct(p["on_draw"]["win_rate"]), f"{p['on_draw']['games']} games"),
        _tile(f"{name_a} wins on turn", num(p["avg_turn_a_wins"])),
        _tile(f"{name_b} wins on turn", num(p["avg_turn_b_wins"])),
        _tile("Mulligan rates", f"{pct(p['mulligan_rate_a'], 0)} / {pct(p['mulligan_rate_b'], 0)}"),
    ]
    out = ['<section class="card"><div class="headline">',
           _hero(pct(p["win_rate"]), f"{name_a} win rate against {name_b}",
                 f"95% interval {ci_text(p['ci'], 1)} over {p['decided']} decided games"),
           '<div class="tiles">' + "".join(tiles) + "</div></div>", _takeaways([reading]), "</section>"]
    out.append('<section class="card"><h2>When games end</h2>'
               '<p class="note">Share of each deck\'s wins by the turn it won on (its own turn count).</p>'
               + _kill_turns(p["kill_turns_a"], f"{name_a} wins", p["kill_turns_b"])
               + _kill_turns(p["kill_turns_b"], f"{name_b} wins", p["kill_turns_a"])
               + "</section>")
    return "".join(out)


def _kill_turns(counts: Dict[str, int], title: str, other: Optional[Dict[str, int]] = None) -> str:
    """Wins by turn as columns; ``other`` only widens the turn axis so two charts line up."""
    if not counts:
        return ""
    total = sum(counts.values())
    turns = sorted(int(t) for t in list(counts) + list(other or {}))
    span = list(range(min(turns), min(max(turns), min(turns) + 17) + 1))
    peak = max(counts.values())
    cols, labels = [], []
    for t in span:
        n = counts.get(str(t), 0)
        share = n / total
        cols.append(f'<div class="c"{tip(f"Turn {t}", [["Wins", str(n)], ["Share of wins", pct(share)]])}>'
                    f'<span>{pct(share, 0) if n == peak else ""}</span>'
                    f'<i style="height:{n / peak * 100:.1f}%"></i></div>')
        labels.append(f"<span>{t}</span>")
    return (f"<h3>{esc(title)} ({total})</h3>" + f'<div class="cols">{"".join(cols)}</div>'
            + f'<div class="colx">{"".join(labels)}</div>')


def _section_ab(summary: dict, names: Dict[str, str]) -> str:
    ab = summary["ab"]
    first, second = ab["first"], ab["second"]
    name_a, name_b = names.get(first, first), names.get(second, second)
    overall = ab["overall_mean"]
    field_a, field_b = summary["field"][first], summary["field"][second]
    tiles = [
        _tile(f"A: {name_a}", pct(field_a["mean"]["rate"]), f"95% interval {ci_text(field_a['mean']['ci'])}"),
        _tile(f"B: {name_b}", pct(field_b["mean"]["rate"]), f"95% interval {ci_text(field_b['mean']['ci'])}"),
    ]
    if ab.get("overall_weighted") and ab["overall_weighted"]["diff"] is not None:
        w = ab["overall_weighted"]
        tiles.append(_tile("A − B weighted by meta share", f"{pts(w['diff'])} pts",
                           f"95% interval {pts(w['ci'][0])} to {pts(w['ci'][1])}"))
    if ab.get("head_to_head"):
        h = ab["head_to_head"]
        tiles.append(_tile("Head to head, A wins", pct(h["win_rate"]), f"{h['wins']}–{h['losses']}, interval {ci_text(h['ci'])}"))
    tiles.append(_tile("Decided games each", str(ab["games_each"])))
    sub = "–" if overall["diff"] is None else f"95% interval {pts(overall['ci'][0])} to {pts(overall['ci'][1])} points"
    out = ['<section class="card"><div class="headline">',
           _hero("–" if overall["diff"] is None else f"{pts(overall['diff'])} pts",
                 "A minus B, win rate against the field (every opponent counted equally)", sub),
           '<div class="tiles">' + "".join(tiles) + "</div></div>",
           _takeaways([analysis.ab_verdict(ab, f"A ({name_a})", f"B ({name_b})")])]
    if summary.get("deck_changes"):
        out.append('<p class="note">Changes from A to B: ' + esc(", ".join(summary["deck_changes"])) + "</p>")
    out.append("</section>")

    rows = [_axis()]
    table = []
    for row in sorted(ab["rows"], key=lambda r: -(r["diff"] or 0)):
        opp = names.get(row["opponent"], row["opponent"])
        a, b = row["first"]["win_rate"], row["second"]["win_rate"]
        marks = _ticks()
        if a is not None and b is not None:
            lo, hi = min(a, b), max(a, b)
            marks += f'<div class="link" style="left:{_pos(lo)};width:{(hi - lo) * 100:.2f}%"></div>'
            marks += f'<div class="dot" style="left:{_pos(a)}"></div><div class="dot b" style="left:{_pos(b)}"></div>'
        t = tip(f"vs {opp}", [
            ["A", f"{pct(a)} ({row['first']['wins']}/{row['first']['decided']})"],
            ["B", f"{pct(b)} ({row['second']['wins']}/{row['second']['decided']})"],
            ["A − B", f"{pts(row['diff'])} pts"],
            ["95% interval", f"{pts(row['ci'][0])} to {pts(row['ci'][1])}"],
            ["p-value", num(row["p"], 3)],
        ])
        rows.append(f'<div class="lab">{esc(opp)}</div><div class="strip"{t}>{marks}</div>'
                    f'<div class="fig"><b>{pts(row["diff"])}</b> pts</div>')
        table.append(
            f'<tr><td class="name">{esc(opp)}</td><td class="n">{pct(a)} ({row["first"]["wins"]}/{row["first"]["decided"]})</td>'
            f'<td class="n">{pct(b)} ({row["second"]["wins"]}/{row["second"]["decided"]})</td>'
            f'<td class="n"><b>{pts(row["diff"])}</b></td><td class="n">{pts(row["ci"][0])} to {pts(row["ci"][1])}</td>'
            f'<td class="n">{num(row["p"], 3)}</td></tr>')
    out += ['<section class="card"><h2>By opponent</h2>',
            '<p class="note">Win rate of each version against each opponent. Single matchups are noisy: '
            "judge the change by the overall number above unless one matchup moves a lot.</p>",
            f'<div class="legend"><span><i class="key" style="background:var(--s1)"></i>A: {esc(name_a)}</span>'
            f'<span><i class="key" style="background:var(--s2)"></i>B: {esc(name_b)}</span></div>',
            '<div class="rows">' + "".join(rows) + "</div>", "<h3>All numbers</h3>",
            '<div class="scroll"><table><thead><tr><th>Opponent</th><th>A</th><th>B</th><th>A − B (pts)</th>'
            f'<th>95% interval</th><th>p</th></tr></thead><tbody>{"".join(table)}</tbody></table></div></section>']
    return "".join(out)


def _section_matrix(summary: dict, names: Dict[str, str]) -> str:
    matrix = summary["matrix"]
    order = matrix["order"]
    ranking = "".join(
        f'<tr><td class="n">{i + 1}</td><td class="name">{esc(names.get(r["key"], r["key"]))}</td>'
        f'<td class="n"><b>{pct(r["mean_win_rate"])}</b></td><td class="n">{ci_text(r["ci"])}</td>'
        f'<td class="n">{r["wins"]}–{r["decided"] - r["wins"]}</td></tr>'
        for i, r in enumerate(matrix["ranking"]))
    head = "<tr><th></th>" + "".join(f"<th>{i + 1}</th>" for i in range(len(order))) + "</tr>"
    body = []
    for i, row in enumerate(order):
        cells = [f'<th class="row">{i + 1}. {esc(names.get(row, row))}</th>']
        for col in order:
            cell = matrix["grid"][row].get(col)
            if cell is None or cell["win_rate"] is None:
                cells.append('<td class="self">·</td>')
                continue
            wr = cell["win_rate"]
            strength = min(1.0, abs(wr - 0.5) / 0.30)
            pole = "var(--pos)" if wr >= 0.5 else "var(--neg)"
            t = tip(f"{names.get(row, row)} vs {names.get(col, col)}", [
                ["Win rate", pct(wr)], ["95% interval", ci_text(cell["ci"])],
                ["Record", f"{cell['wins']}–{cell['decided'] - cell['wins']}"]])
            cells.append(f'<td style="--t:{strength:.3f};--pole:{pole}"{t}>{wr * 100:.0f}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<section class="card"><h2>Ranking</h2>'
        '<p class="note">Average win rate against the other decks in this round robin, every opponent counted equally.</p>'
        '<div class="scroll"><table><thead><tr><th>#</th><th>Deck</th><th>Avg win rate</th><th>95% interval</th>'
        f'<th>W–L</th></tr></thead><tbody>{ranking}</tbody></table></div></section>'
        '<section class="card"><h2>Matchup grid</h2>'
        '<p class="note">Win rate (%) of the row deck against the column deck. Blue means the row deck is favoured, '
        "red unfavoured, grey close to even; colour is full strength at 30 points from even. "
        "Hover or focus a cell for the record and interval.</p>"
        f'<div class="scroll"><table class="heat"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div></section>'
    )


def _section_cards(summary: dict, names: Dict[str, str]) -> str:
    out = []
    for key, data in (summary.get("cards") or {}).items():
        cards = data.get("cards") or []
        if not cards or not data.get("games"):
            continue
        rows = []
        for c in cards:
            low = c["seen"]["games"] < 20 or c["not_seen"]["games"] < 20
            iwd = c["iwd"]
            bar = ""
            if iwd is not None:
                width = min(abs(iwd) / 0.20, 1.0) * 50
                side = f"left:50%;width:{width:.1f}%" if iwd >= 0 else f"left:{50 - width:.1f}%;width:{width:.1f}%"
                bar = f'<span class="bar0"><i class="{"neg" if iwd < 0 else ""}" style="{side}"></i></span>'
            rows.append(
                f'<tr class="{"low" if low else ""}"><td class="name">{c["copies"]} {esc(c["card"])}</td>'
                f'<td class="n">{pct(c["seen"]["win_rate"])} <span class="note">({c["seen"]["games"]})</span></td>'
                f'<td class="n">{pct(c["not_seen"]["win_rate"])} <span class="note">({c["not_seen"]["games"]})</span></td>'
                f'<td class="n">{bar} <b>{pts(iwd)}</b></td>'
                f'<td class="n">{pct(c["opening"]["win_rate"])} <span class="note">({c["opening"]["games"]})</span></td>'
                f'<td class="n">{pct(c["play_rate"], 0)}</td></tr>')
        title = "Card performance" + (f": {esc(names.get(key, key))}" if len(summary.get("cards") or {}) > 1 else "")
        out.append(
            f'<section class="card"><h2>{title}</h2>'
            f'<p class="note">Across {data["games"]} decided games ({pct(data["win_rate"])} won). '
            "“Seen” means the card was in the opening hand or drawn; the bar is the win rate when seen minus when "
            "not seen, in points (full width = 20). These are correlations: long games see more cards, which flatters "
            "late-game cards and understates cheap ones. “Played when seen” flags cards that often sit in hand. "
            "Greyed rows have fewer than 20 games on one side.</p>"
            '<div class="scroll"><table><thead><tr><th>Card</th><th>Win rate when seen</th><th>When not seen</th>'
            "<th>Difference (pts)</th><th>In opening hand</th><th>Played when seen</th></tr></thead>"
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')
    return "".join(out)


def _section_clock(summary: dict, names: Dict[str, str]) -> str:
    clock = summary["clock"]
    games = clock["games"] or 1
    by = {t["turn"]: t for t in clock["turns"]}
    tiles = [_tile("Median winning turn", str(clock["median_turn"] or "–")),
             _tile("Fastest win", f"turn {clock['fastest_turn']}" if clock["fastest_turn"] else "–")]
    for turn in (4, 5, 6):
        if turn in by:
            tiles.append(_tile(f"Won by turn {turn}", pct(by[turn]["by_turn"], 0)))
    tiles.append(_tile("Games not won", str(clock["not_won"]), f"of {clock['games']}"))
    peak = max((t["wins"] for t in clock["turns"]), default=0) or 1
    turns = [t for t in clock["turns"] if t["turn"] <= 20]
    first = next((i for i, t in enumerate(turns) if t["wins"]), 0)
    turns = turns[first:]
    cols = "".join(
        f'<div class="c"{tip("Turn " + str(t["turn"]), [["Wins on this turn", str(t["wins"])], ["Share of games", pct(t["wins"] / games)], ["Won by this turn", pct(t["by_turn"])]])}>'
        f'<span>{pct(t["wins"] / games, 0) if t["wins"] == peak else ""}</span>'
        f'<i style="height:{t["wins"] / peak * 100:.1f}%"></i></div>' for t in turns)
    labels = "".join(f"<span>{t['turn']}</span>" for t in turns)
    table = "".join(f'<tr><td class="n">{t["turn"]}</td><td class="n">{t["wins"]}</td>'
                    f'<td class="n">{pct(t["by_turn"])}</td></tr>' for t in turns)
    return (
        '<section class="card"><div class="headline">'
        + _hero(num(clock["mean_turn"]), "Average turn the deck wins on when nothing stops it",
                f"{clock['won']} of {clock['games']} games won against an opponent that never acts")
        + '<div class="tiles">' + "".join(tiles) + "</div></div></section>"
        '<section class="card"><h2>Winning turn</h2><p class="note">Games won on each of the deck\'s own turns. '
        "The opponent only plays lands, so this is the deck's best-case speed as piloted by the Forge AI.</p>"
        f'<div class="cols">{cols}</div><div class="colx">{labels}</div><h3>All numbers</h3>'
        '<div class="scroll"><table><thead><tr><th>Turn</th><th>Wins on this turn</th><th>Won by this turn</th></tr>'
        f'</thead><tbody>{table}</tbody></table></div></section>')


def _section_decks(summary: dict, names: Dict[str, str]) -> str:
    out = ['<section class="card"><h2>Decks and run details</h2>']
    notes = summary.get("deck_notes") or {}
    if notes:
        out.append("<h3>Deck check notes</h3>")
        for key, issues in notes.items():
            out.append(f"<p><b>{esc(names.get(key, key))}</b></p><ul>" + "".join(f"<li>{esc(i)}</li>" for i in issues) + "</ul>")
    for key, info in summary["entrants"].items():
        main = "".join(f"<div>{n} {esc(c)}</div>" for c, n in info["main"].items())
        side = "".join(f"<div>{n} {esc(c)}</div>" for c, n in info.get("side", {}).items())
        role = {"hero": "deck under test", "variant": "variant"}.get(info.get("role"), info.get("category") or "opponent")
        out.append(f'<details{" open" if info.get("role") in ("hero", "variant") else ""}>'
                   f'<summary>{esc(info["name"])} — {esc(role)}, {info["main_count"]} cards</summary>'
                   f'<div class="decklist">{main}</div>'
                   + (f'<p class="note">Sideboard (not used in these best-of-one games)</p><div class="decklist">{side}</div>' if side else "")
                   + "</details>")
    opts, forge = summary.get("options", {}), summary.get("forge", {})
    problems = summary.get("problems", {})
    elapsed = summary.get("elapsed_seconds")
    out.append(
        "<h3>How this was run</h3><p class=\"note\">"
        f"Forge {esc(forge.get('forgeVersion') or forge.get('version') or '?')}, AI profile {esc(opts.get('ai_profile', 'Default'))}"
        f"{'' if opts.get('monte_carlo', 'off') == 'off' else ', Monte Carlo ' + esc(opts.get('monte_carlo'))}; "
        f"{opts.get('games_per_pairing', '?')} games per pairing, best-of-one, no sideboarding; "
        f"base seed {opts.get('seed', '?')}; time limit {opts.get('timeout', '?')}s per game. "
        f"{problems.get('timeouts', 0)} games hit the time limit and {problems.get('errors', 0)} failed in the engine; "
        "both are excluded from win rates."
        + (f" Total run time {elapsed / 60:.0f} min." if elapsed else "")
        + f" Legality checked against: {esc(summary.get('format', '?'))}. Generated by mtgsim {esc(summary.get('mtgsim_version', ''))}"
        f" on {esc(summary.get('created', ''))}.</p></section>")
    return "".join(out)


def _section_goldfish(summary: dict, names: Dict[str, str]) -> str:
    from . import goldfish_report

    return goldfish_report.render(summary.get("goldfish") or {}, names)


# ----------------------------------------------------------------------- page


def render(summary: dict) -> str:
    names = {key: info["name"] for key, info in summary["entrants"].items()}
    kind = summary.get("kind")
    sections = {
        "gauntlet": _section_gauntlet, "match": _section_match, "ab": _section_ab,
        "matrix": _section_matrix, "clock": _section_clock,
    }
    body = sections[kind](summary, names) if kind in sections else ""
    if kind != "clock":
        body += _section_cards(summary, names)
    body += _section_goldfish(summary, names)
    body += _section_decks(summary, names)
    opts = summary.get("options", {})
    sub = (f"{esc(summary.get('format', ''))} · {opts.get('games_per_pairing', '?')} games per pairing · "
           f"Forge AI on both sides · {esc(summary.get('created', ''))}")
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{esc(summary.get('title', 'mtgsim report'))}</title><style>{CSS}</style></head><body><main>"
        f"<h1>{esc(summary.get('title', 'mtgsim report'))}</h1><p class=\"sub\">{sub}</p>"
        f"<div class=\"caveat\"><b>Read this first.</b> {esc(summary.get('caveat', ''))}</div>"
        f"{body}</main><div id=\"tip\" hidden></div><script>{JS}</script></body></html>"
    )


def write_report(run_dir: Path, summary: dict) -> Path:
    path = Path(run_dir) / "report.html"
    path.write_text(render(summary), encoding="utf-8")
    return path
