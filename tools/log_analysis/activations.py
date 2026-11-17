"""Mana sinks and wrong-phase activations of one deck (the Ba Sing Se method).

usage: MTGSIM_RUN=runs/x PYTHONPATH=tools/log_analysis python3 tools/log_analysis/activations.py DECK_SLUG [--min 20]

Reads a --save-logs run in which DECK_SLUG played (a gauntlet of it is simplest). Prints:

1. every ability the deck activated: per game, and how the activations split by phase
   (own main 1 / own combat / own main 2 / own end / opponent's turn);
2. for each permanent the deck had on the battlefield in at least --min games and the rest: the
   deck's win rate and how many spells it cast per game, with and without that permanent, and the
   same for the spells cast per own turn while the permanent was on the battlefield against turns
   it was not. A permanent with activations whose presence lowers the spells cast is a lead worth
   reading in the logs (`logs/games/`), not proof of a misplay: a land that animates arrives late,
   a card drawn in long games comes with more spells.
"""
import collections
import re
import sys

from parse import R, games

RE_TURN = re.compile(r'^Turn: Turn (\d+) \((Seat\d)\)')
RE_PHASE = re.compile(r"^Phase: (Seat\d)'s (.*)$")
RE_STACK = re.compile(r'^Add To Stack: (Seat\d) (cast|activated|triggered) (.*?)(?: targeting .*)?$')
RE_LAND = re.compile(r'^Land: (Seat\d) played (.*) \((\d+)\)$')
RE_RES = re.compile(r'^Resolve Stack: (.*?) - ')
PHASES = {'Main phase, precombat': 'main1', 'Main phase, postcombat': 'main2', 'End step': 'end',
          'Cleanup step': 'end', 'Upkeep step': 'upkeep', 'Draw step': 'upkeep', 'Untap step': 'upkeep'}


def phase_key(ph, own):
    if not own:
        return 'opp'
    if ph in PHASES:
        return PHASES[ph]
    return 'combat'


def scan(path, seat):
    """Per own turn: spells cast; activations with phase; names of own permanents that arrived."""
    turns = []
    cur = None
    active = None
    ph = ''
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        m = RE_TURN.match(line)
        if m:
            active = m.group(2)
            cur = {'own': active == seat, 'casts': [], 'acts': [], 'arrived': []}
            turns.append(cur)
            continue
        if cur is None:
            continue
        m = RE_PHASE.match(line)
        if m:
            ph = m.group(2)
            continue
        m = RE_LAND.match(line)
        if m:
            if m.group(1) == seat:
                cur['arrived'].append(m.group(2))
            continue
        m = RE_STACK.match(line)
        if m and m.group(1) == seat:
            name = m.group(3)
            if m.group(2) == 'cast':
                cur['casts'].append(name)
                cur['arrived'].append(name)  # permanents among them are filtered by the caller
            elif m.group(2) == 'activated':
                cur['acts'].append((name, phase_key(ph, active == seat)))
    return turns


def main(argv):
    deck = argv[0]
    mn = int(argv[argv.index('--min') + 1]) if '--min' in argv else 20
    acts = collections.Counter()
    act_phase = collections.defaultdict(collections.Counter)
    act_games = collections.Counter()
    per_game = []  # (won, spells cast, set of arrived names, [(own turn spells, set present)])
    for g, path in games():
        if g.get('status') != 'ok' or deck not in g['seats']:
            continue
        if g['seats'][0] == g['seats'][1]:
            continue  # mirror: which seat is which deck is ambiguous for this purpose
        idx = g['seats'].index(deck)
        seat = 'Seat%d' % (idx + 1)
        try:
            turns = scan(path, seat)
        except FileNotFoundError:
            continue
        seen = set()
        present = set()
        tspells = []
        for t in turns:
            for name, pk in t['acts']:
                acts[name] += 1
                act_phase[name][pk] += 1
                seen.add(name)
            if t['own']:
                tspells.append((len(t['casts']), frozenset(present)))
            present |= set(t['arrived'])
        for name in seen:
            act_games[name] += 1
        won = g.get('winner_seat') == idx
        per_game.append((won, sum(len(t['casts']) for t in turns if True), present, tspells))
    n = len(per_game)
    print('%s: %d games (mirrors left out), win rate %.1f%%' % (deck, n, 100.0 * sum(w for w, *_ in per_game) / max(n, 1)))
    print('\nActivations                                   per game  in games  main1 combat main2  end upkeep  opp')
    for name, c in acts.most_common():
        ph = act_phase[name]
        tot = sum(ph.values())
        print('  %-44s %6.2f   %5d   %s' % (name[:44], c / n, act_games[name],
              ' '.join('%5.0f%%' % (100.0 * ph[k] / tot) for k in ('main1', 'combat', 'main2', 'end', 'upkeep', 'opp'))))
    names = collections.Counter()
    for _, _, present, _ in per_game:
        names.update(present)
    print('\nWith / without each permanent (cards cast or played; spells = everything the deck cast)')
    print('  %-34s %5s %6s %6s  %6s %6s  %13s' % ('card', 'games', 'win w', 'win wo', 'sp/g w', 'wo',
                                                'sp/turn w  wo'))
    for name, k in names.most_common():
        if k < mn or n - k < mn:
            continue
        w = [x for x in per_game if name in x[2]]
        wo = [x for x in per_game if name not in x[2]]
        tw = [s for x in per_game for s, pr in x[3] if name in pr]
        two = [s for x in per_game for s, pr in x[3] if name not in pr]
        print('  %-34s %5d %5.1f%% %5.1f%%  %6.2f %6.2f  %6.2f %6.2f%s' % (
            name[:34], k, 100.0 * sum(x[0] for x in w) / len(w), 100.0 * sum(x[0] for x in wo) / len(wo),
            sum(x[1] for x in w) / len(w), sum(x[1] for x in wo) / len(wo),
            sum(tw) / max(len(tw), 1), sum(two) / max(len(two), 1), '  *act' if name in acts else ''))


if __name__ == '__main__':
    main(sys.argv[1:])
