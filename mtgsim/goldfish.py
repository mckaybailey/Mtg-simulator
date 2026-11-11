"""A "goldfish" analysis: thousands of solitaire games of one deck, with no opponent and no engine.

Forge answers "does this deck win?", which takes minutes. This module answers the questions
that come first and need no opponent: how often does the deck stumble on mana, does it use
its mana every turn, and can the mana base cast each spell on time? Those depend only on the
order of the cards and on mana costs, so a simple Monte Carlo model gives stable numbers in a
few seconds.

**This is a mana and curve model, not a rules engine.** Nothing a card says is carried out
except producing mana. The simplifications, all deliberate:

* No card draw, tutoring, removal, cost reduction, alternative costs, or opponent. The only
  cards the player ever sees are the opening hand and one draw per turn (none on turn 1 when
  on the play). There is no maximum hand size.
* Every land taps for one mana of any one colour the card database lists for it
  (``Card.produces``). Lands with no listed mana count as lands that pay generic costs only,
  and are named under ``warnings``. A land enters tapped only if it *always* does
  (``Card.enters_tapped``); such a land gives no mana on the turn it is played. Fetch lands
  such as Evolving Wilds are listed as tapped lands of every colour, and limits on what a
  land's mana may be spent on (Cavern of Souls) are unknown here, so both look better than
  they are.
* Nonland mana sources (``Card.mana_source``: mana creatures and mana rocks) add one mana of
  their colours from the turn after they are cast. They never die.
* Spell/land modal cards are spells. One is played as a land only on a turn when the hand
  holds no real land; its land face's colours and tapped-ness are read from that face's rules
  text. A modal card with a land on both faces is a land of both faces' colours.
* A spell costs its generic mana plus its coloured symbols; X is zero. Hybrid symbols take
  any of their colours; Phyrexian symbols and the cheaper half of a split card are costed the
  way ``ManaCost`` and ``Card.cost`` already do. Coloured symbols are assigned to sources
  exactly (a source pays one symbol), so "two blue sources for UU" is checked properly.
* Play pattern, every turn: draw; play one land if possible; cast spells. The land chosen is
  the one that lets the most mana be spent this turn; ties go to a land that enters tapped
  (it costs nothing now), then to the land that leaves the fewest coloured symbols in hand
  without a source. Spells with no mana cost are always cast; of the rest, the set that
  spends the most mana is cast, preferring mana sources and then the more expensive spells.

Result of :func:`analyze`
-------------------------

A dict of plain JSON types. Rates and probabilities are fractions from 0 to 1 and averages
are floats, all rounded to 4 decimals. ``null`` marks a value that could not be measured.

``deck`` (str), ``games`` (int), ``turns`` (int), ``seed`` (int)
    What was run. Games alternate between being on the play (first game) and on the draw.
``games_on_play``, ``games_on_draw`` (int)
    How many games were played from each seat.
``composition`` (dict) - a static description of the main deck:
    ``cards`` (int)                  cards in the main deck
    ``lands`` (int)                  real lands (front face is a land)
    ``modal_lands`` (int)            spell/land modal cards; they are *also* counted as spells below
    ``tapped_lands`` (int)           real lands that always enter tapped
    ``spells`` (int)                 nonland cards (``creatures + other_spells``)
    ``creatures`` (int)              nonland cards with the Creature type
    ``other_spells`` (int)           every other nonland card
    ``nonland_mana_sources`` (int)   nonland cards that tap for mana (mana creatures, mana rocks)
    ``avg_mana_value`` (float)       average mana value of the nonland cards
    ``curve`` (list of 8 ints)       nonland cards by mana value: index 0-6, index 7 is "7 or more"
    ``pips`` (dict colour -> number) coloured symbols in the costs of nonland cards, per copy;
                                     a hybrid symbol is split evenly between its colours
    ``sources`` (dict colour -> int) cards able to make that colour: lands, modal land faces
                                     and nonland mana sources
    ``land_sources`` (dict colour -> int)  the same, real lands only
    The three colour dicts always have exactly the keys "W", "U", "B", "R", "G", "C".
``opening_hand`` (dict):
    ``lands_in_seven`` (list of 8 floats)     probability that the first seven cards, before any
                                              mulligan, hold exactly ``index`` real lands
    ``mulligan_rate`` (float)                 share of games with at least one mulligan
    ``kept_hand_sizes`` (dict "7"/"6"/"5"/"4" -> float)  share of games keeping that many cards
    ``avg_kept_hand_size`` (float)
    ``lands_in_kept_hand`` (list of 8 floats) the same distribution for the hand actually kept
    ``avg_lands_in_kept_hand`` (float)
``by_turn`` (dict) with keys ``overall``, ``play`` and ``draw``. Each is a list with one row
    per turn 1..turns (``overall`` pools all games, so it is the 50/50 average); every row has:
    ``turn`` (int)
    ``lands`` (float)                average lands on the battlefield after the land drop
    ``hit_all_land_drops`` (float)   probability of having played a land on every turn so far
    ``mana_available`` (float)       average mana usable this turn (see ``definitions``)
    ``mana_spent`` (float)           average mana spent on spells this turn
    ``spells_cast`` (float)          average number of spells cast this turn
    ``cards_in_hand`` (float)        average hand size at end of turn
    Values in ``play``/``draw`` rows are null if no game was played from that seat.
``mana_screw``, ``mana_flood`` (dict ``overall``/``play``/``draw`` -> float or null)
    Rates under the definitions below; null when ``turns`` is too short to measure them.
``cards`` (list of dict) - one row per distinct nonland card, by mana value then name:
    ``name`` (str), ``copies`` (int), ``mana_value`` (int)
    ``cost`` (str)           the cost as the model sees it, e.g. "{1}{U}{U}" or "{X}{B/G}"
    ``curve_turn`` (int)     the turn the card is "on curve": its mana value, at least 1
    ``samples`` (int)        games in which a copy had been drawn by ``curve_turn``
    ``castable`` (list of 3) probability, in those games, that the card is castable on
                             ``curve_turn``, by one turn later, by two turns later
    ``enough_mana`` (list of 3)  the same, ignoring colours; ``enough_mana[i] - castable[i]``
                             is therefore the share lost to colours alone
    List entries are null where the turn lies beyond ``turns`` or ``samples`` is 0.
``definitions`` (dict str -> str)
    One sentence per metric, for reports to show: ``keep_rule``, ``mana_screw``,
    ``mana_flood``, ``hit_all_land_drops``, ``mana_available``, ``mana_spent``, ``castable``,
    ``enough_mana``, ``model``.
``warnings`` (list of str)
    Cards the model could not describe well (currently: lands with no known mana).

Metric definitions
------------------

*Keep rule (London mulligan).* Seven cards are looked at each time. Seven are kept with 2-5
lands; after one mulligan the hand is kept if those seven hold 2-6 lands; after two, 1-7;
after three it is always kept (four cards). Modal spell/lands count towards the minimum
only. Each mulligan then puts one card on the bottom: a land while the hand holds more than
three lands (two when keeping four), otherwise the most expensive spell, modal spell/lands
last.

*Mana screw.* Fewer than 3 lands on the battlefield after the player's own turn 4.

*Mana flood.* At least 60% of the cards seen by the end of turn 6 (kept hand plus draws) are
real lands. On the play with a seven-card hand that is 8 or more lands among 12 cards.

*Castable.* The card could have been cast that turn had it been the turn's only spell: with
the battlefield as the model built it on earlier turns, some land drop the hand allowed
leaves enough usable mana of the right colours for the whole cost. Every real land in hand
is tried, not only the one the model played, so its choice between equally good plays never
makes a mana base look worse. It is measured in the games where a copy had been drawn by the
card's curve turn (a copy already cast still counts; one played as a land does not), and
because mana sources never leave, a card castable on one turn stays castable.

*Enough mana.* The same test counting mana only. ``mana_available`` in the turn rows is a
different thing: the mana the model really had after the land it chose to play.
"""

from __future__ import annotations

import random
import re
import textwrap
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .carddb import Card, CardDatabase, ManaCost
from .decks import Deck

MANA_SYMBOLS = "WUBRGC"
HAND_SIZE = 7
# Kept hand size -> (fewest, most) lands among the seven cards looked at.
KEEP_LANDS = {7: (2, 5), 6: (2, 6), 5: (1, 7)}
SMALLEST_HAND = 4  # kept whatever it holds
# Kept hand size -> lands worth keeping; while the hand holds more, a land goes to the bottom.
LANDS_WORTH_KEEPING = {6: 3, 5: 3, 4: 2}
SCREW_TURN, SCREW_LANDS = 4, 3
FLOOD_TURN, FLOOD_LAND_PERCENT = 6, 60
LATE_TURNS = 2  # castability is followed for this many turns past the curve turn

_BITS = 16  # width of one counter in the packed integers that describe a battlefield or a cost
_ADD_MANA = re.compile(r"\{T\}: Add ([^.\n]*)")

_Plan = Tuple[int, List[int]]  # mana spent this turn, and the cards cast for it


# ------------------------------------------------------------- colour payment


def unpaid_pips(pips: Sequence[str], sources: Sequence[str]) -> int:
    """How many coloured symbols stay unpaid when each source pays at most one of them.

    ``pips`` holds one string per symbol (the colours that may pay it, e.g. "U" or "BG") and
    ``sources`` one string per mana source (the colours it can make). 0 means the coloured
    part of the cost is payable.
    """
    return _shortfall(_grouped(pips), _grouped(sources))


def _grouped(colour_sets: Sequence[str]) -> List[Tuple[int, int]]:
    counts: Dict[int, int] = {}
    for colours in colour_sets:
        counts[_mask(colours)] = counts.get(_mask(colours), 0) + 1
    return list(counts.items())


def _mask(colours: str) -> int:
    return sum(1 << MANA_SYMBOLS.index(c) for c in set(colours))


def _shortfall(pips: Sequence[Tuple[int, int]], sources: Sequence[Tuple[int, int]]) -> int:
    """Unpaid symbols, given (colour mask, how many) groups of symbols and of sources.

    By the deficiency form of Hall's marriage theorem the answer is the largest amount by
    which some set of symbols outnumbers the sources able to pay any of them. Symbols with
    the same colours are interchangeable, so only whole groups need trying: a handful of
    subsets instead of a search over individual lands.
    """
    worst = 0
    for subset in range(1, 1 << len(pips)):
        colours = short = 0
        for index, (mask, count) in enumerate(pips):
            if subset >> index & 1:
                colours |= mask
                short += count
        for mask, count in sources:
            if mask & colours:
                short -= count
        worst = max(worst, short)
    return worst


# ------------------------------------------------------------ reading the deck


@dataclass(frozen=True)
class _Kind:
    """One distinct card of the deck, reduced to what a mana model can see."""

    name: str
    copies: int
    is_land: bool
    is_modal_land: bool  # a spell that can be played as a land instead
    is_creature: bool
    mana_value: int
    cost: ManaCost
    land_colours: Optional[str]  # mana made when played as a land; None if it cannot be
    enters_tapped: bool
    ramp_colours: Optional[str]  # mana made as a nonland permanent; None if it makes none


def _ordered(colours: str) -> str:
    return "".join(c for c in MANA_SYMBOLS if c in colours)


def _land_face_mana(card: Card) -> Tuple[str, bool]:
    """Colours and tapped-ness of the land faces behind a modal card's front face.

    The database's ``produces`` and ``enters_tapped`` describe the front face only, so for the
    other side the rules text is the only source. "Always tapped" follows the database's
    convention: a land that may enter untapped (for life, or under a condition) is untapped.
    """
    colours, tapped = "", False
    for face in card.faces[1:]:
        if not face.is_land:
            continue
        for clause in _ADD_MANA.findall(face.oracle):
            colours += "".join(re.findall(r"\{([WUBRGC])\}", clause))
            if "any color" in clause:
                colours += "WUBRG"
        for sentence in re.split(r"[.\n]", face.oracle.lower()):
            if re.search(r"enters (the battlefield )?tapped", sentence) and not re.search(
                r"\b(unless|may|if)\b", sentence
            ):
                tapped = True
    return colours, tapped


def _describe(card: Card, copies: int) -> _Kind:
    land_colours: Optional[str] = None
    tapped = False
    if card.is_land:
        land_colours, tapped = card.produces, card.enters_tapped
        if card.layout == "modal":  # a land on both faces: the player picks one, much like a dual land
            land_colours += _land_face_mana(card)[0]
    elif card.has_land_face:
        land_colours, tapped = _land_face_mana(card)
    return _Kind(
        name=card.name,
        copies=copies,
        is_land=card.is_land,
        is_modal_land=card.has_land_face,
        is_creature=card.is_creature and not card.is_land,
        mana_value=card.cmc,
        cost=card.cost,
        land_colours=None if land_colours is None else _ordered(land_colours),
        enters_tapped=tapped,
        ramp_colours=_ordered(card.produces) if card.mana_source and not card.is_land else None,
    )


def _deck_kinds(deck: Deck, db: CardDatabase) -> List[_Kind]:
    """The main deck as kinds, in name order so that a seed gives the same games however the list was sorted."""
    kinds: List[_Kind] = []
    unknown: List[str] = []
    for name in sorted(deck.main):
        card = db.get(name)
        if card is None:
            unknown.append(name)
        elif deck.main[name] > 0:
            kinds.append(_describe(card, deck.main[name]))
    if unknown:
        raise ValueError("cards missing from the card database: " + ", ".join(unknown))
    if sum(kind.copies for kind in kinds) < HAND_SIZE:
        raise ValueError(f"a deck needs at least {HAND_SIZE} cards to draw an opening hand")
    return kinds


# ------------------------------------------------------------------- tallies


class _Tally:
    """Running totals over the games played from one seat (on the play, or on the draw)."""

    def __init__(self, turns: int, kinds: int) -> None:
        self.games = 0
        # opening hand; the lists are indexed by a number of lands or of cards
        self.seven_lands = [0] * (HAND_SIZE + 1)
        self.kept_lands = [0] * (HAND_SIZE + 1)
        self.kept_size = [0] * (HAND_SIZE + 1)
        # per turn
        self.lands = [0] * turns
        self.on_time = [0] * turns
        self.mana = [0] * turns
        self.spent = [0] * turns
        self.cast = [0] * turns
        self.hand = [0] * turns
        self.screw = 0
        self.flood = 0
        # per kind; castable/enough are indexed by turns past the curve turn, then by kind
        self.samples = [0] * kinds
        self.castable = [[0] * kinds for _ in range(LATE_TURNS + 1)]
        self.enough = [[0] * kinds for _ in range(LATE_TURNS + 1)]

    def plus(self, other: "_Tally") -> "_Tally":
        total = _Tally(len(self.lands), len(self.samples))
        for name, mine in vars(self).items():
            setattr(total, name, _added(mine, getattr(other, name)))
        return total


def _added(a, b):
    if isinstance(a, list):
        return [_added(x, y) for x, y in zip(a, b)]
    return a + b


# ----------------------------------------------------------------- simulation


class _Goldfish:
    """Plays solitaire games of one deck and adds what happened to a tally.

    Mana sources are grouped by the colours they make and coloured symbols by the colours that
    pay them. "How many of each group" is packed into one integer (``_BITS`` bits per group),
    so a battlefield is one number, the symbols of several spells cast together are the sum of
    their numbers, and "can this battlefield pay those symbols" is a dictionary lookup that is
    solved once and reused across games. That cache is what keeps 20,000 games to seconds.
    """

    def __init__(self, kinds: Sequence[_Kind], turns: int) -> None:
        self.turns = turns
        self.pool = [index for index, kind in enumerate(kinds) for _ in range(kind.copies)]
        # Only this many cards can be seen in a game, so only this many are shuffled.
        self.depth = min(len(self.pool), HAND_SIZE + turns)

        source_groups = sorted(
            {kind.land_colours for kind in kinds if kind.land_colours is not None}
            | {kind.ramp_colours for kind in kinds if kind.ramp_colours is not None}
        )
        pip_groups = sorted({pip for kind in kinds if not kind.is_land for pip in kind.cost.pips})
        self.source_masks = [_mask(colours) for colours in source_groups]
        self.pip_masks = [_mask(colours) for colours in pip_groups]
        self.unit = [1 << (_BITS * group) for group in range(len(source_groups))]

        self.is_land = [kind.is_land for kind in kinds]
        self.tapped = [kind.enters_tapped for kind in kinds]
        self.land_group = [
            source_groups.index(kind.land_colours) if kind.land_colours is not None else -1 for kind in kinds
        ]
        self.ramp_group = [
            source_groups.index(kind.ramp_colours) if kind.ramp_colours is not None else -1 for kind in kinds
        ]
        self.land_colour_count = [len(kind.land_colours or "") for kind in kinds]
        self.need = [0 if kind.is_land else kind.cost.generic + len(kind.cost.pips) for kind in kinds]
        self.pips = [
            0 if kind.is_land else sum(1 << (_BITS * pip_groups.index(pip)) for pip in kind.cost.pips)
            for kind in kinds
        ]

        everything = range(len(kinds))
        self.land_kinds = [k for k in everything if kinds[k].is_land]
        self.modal_kinds = [k for k in everything if kinds[k].is_modal_land]
        spells = [k for k in everything if not kinds[k].is_land]
        # Casting preference among equally mana-hungry plays: ramp first, then the dearer spell.
        self.cast_order = sorted(spells, key=lambda k: (self.ramp_group[k] < 0, -self.need[k], kinds[k].name))
        # What to bottom first in a mulligan: the dearest pure spell; a card that could be a land goes last.
        self.bottom_order = sorted(
            spells, key=lambda k: (kinds[k].is_modal_land, -kinds[k].mana_value, kinds[k].name)
        )
        # Lands that would change the battlefield identically are weighed once. A modal card also
        # takes its own spell out of the hand, so each modal kind stands alone.
        self.land_twin = [
            (self.land_group[k], self.tapped[k], k if kinds[k].is_modal_land else -1) for k in everything
        ]
        # checks[turn]: the (turns past curve, kind) castability samples to take on that turn.
        self.checks: List[List[Tuple[int, int]]] = [[] for _ in range(turns + 1)]
        for k in spells:
            for late in range(LATE_TURNS + 1):
                turn = max(1, kinds[k].mana_value) + late
                if turn <= turns:
                    self.checks[turn].append((late, k))

        self._unpaid: Dict[int, Dict[int, int]] = {}  # battlefield -> symbols owed -> symbols left unpaid

    # -- colour payment, cached

    def _payments(self, battlefield: int) -> Dict[int, int]:
        known = self._unpaid.get(battlefield)
        if known is None:
            known = self._unpaid[battlefield] = {}
        return known

    def _solve(self, known: Dict[int, int], battlefield: int, owed: int) -> int:
        """Work out, and remember in ``known``, how many of the owed symbols this battlefield cannot pay."""
        result = known[owed] = _shortfall(_unpack(owed, self.pip_masks), _unpack(battlefield, self.source_masks))
        return result

    # -- opening hand

    def _deal(self, rng: random.Random, tally: _Tally) -> Tuple[List[int], List[int]]:
        """London mulligans under the keep rule; returns the hand (copies per kind) and the library."""
        is_land = self.is_land
        size = HAND_SIZE
        while True:
            order = rng.sample(self.pool, self.depth)
            seven = order[:HAND_SIZE]
            lands = sum(1 for card in seven if is_land[card])
            if size == HAND_SIZE:
                tally.seven_lands[lands] += 1
            if size == SMALLEST_HAND:
                break
            window = KEEP_LANDS[size]
            flexible = sum(1 for card in seven if self.land_group[card] >= 0) - lands
            if lands <= window[1] and lands + flexible >= window[0]:
                break
            size -= 1

        hand = [0] * len(is_land)
        for card in seven:
            hand[card] += 1
        library = order[HAND_SIZE:]
        for _ in range(HAND_SIZE - size):
            card = self._to_bottom(hand, size)
            hand[card] -= 1
            library.append(card)
        tally.kept_size[size] += 1
        tally.kept_lands[sum(hand[k] for k in self.land_kinds)] += 1
        return hand, library

    def _to_bottom(self, hand: List[int], size: int) -> int:
        """The card a mulligan sends to the bottom: an excess land, otherwise the most expensive spell."""
        lands = [k for k in self.land_kinds if hand[k]]
        spells = [k for k in self.bottom_order if hand[k]]
        if spells and (not lands or sum(hand[k] for k in lands) <= LANDS_WORTH_KEEPING[size]):
            return spells[0]
        # Give up the land the hand has most duplicates of, and a one-colour land before a dual.
        held: Dict[int, int] = {}
        for k in lands:
            held[self.land_group[k]] = held.get(self.land_group[k], 0) + hand[k]
        return max(lands, key=lambda k: (held[self.land_group[k]], -self.land_colour_count[k]))

    # -- one turn's decisions

    def _spend(self, hand: List[int], battlefield: int, mana: int) -> _Plan:
        """What to cast with this mana: every free spell, plus the set that spends the most."""
        need, pips = self.need, self.pips
        known = self._payments(battlefield)
        free: List[int] = []
        options: List[int] = []  # one entry per castable copy, in casting preference order
        for k in self.cast_order:
            copies = hand[k]
            if not copies:
                continue
            if need[k] == 0:
                free += [k] * copies
            elif need[k] <= mana:
                unpaid = known.get(pips[k])
                if unpaid is None:
                    unpaid = self._solve(known, battlefield, pips[k])
                if unpaid == 0:
                    options += [k] * copies
        if not options:
            return 0, free
        if len(options) == 1:
            return need[options[0]], free + options

        # Largest total that fits, by depth-first search. Hands are small and the bound prunes hard.
        rest = [0] * (len(options) + 1)  # rest[i]: mana the options from i onwards could still use
        for i in range(len(options) - 1, -1, -1):
            rest[i] = rest[i + 1] + need[options[i]]
        best_spent = 0
        best: List[int] = []
        chosen: List[int] = []

        def search(i: int, spent: int, owed: int) -> None:
            nonlocal best_spent, best
            if spent > best_spent:
                best_spent, best = spent, chosen[:]
            if min(mana, spent + rest[i]) <= best_spent:
                return
            k = options[i]
            if spent + need[k] <= mana:
                together = owed + pips[k]
                unpaid = known.get(together)
                if unpaid is None:
                    unpaid = self._solve(known, battlefield, together)
                if unpaid == 0:
                    chosen.append(k)
                    search(i + 1, spent + need[k], together)
                    chosen.pop()
            i += 1
            while i < len(options) and options[i] == k:  # passing on one copy means passing on its twins
                i += 1
            search(i, spent, owed)

        search(0, 0, 0)
        return best_spent, free + best

    def _choose_land(self, choices: List[int], hand: List[int], battlefield: int, sources: int) -> Tuple[int, _Plan]:
        """The land drop that helps the hand most, with the casting plan it leads to.

        Most mana spent this turn wins. Ties go to a land that enters tapped, since playing it
        now costs nothing, and then to the land after which the fewest coloured symbols in
        hand lack a source.
        """
        pips = self.pips
        best_land, best_plan, best_score = choices[0], (0, []), None
        weighed = set()
        for land in choices:
            if self.land_twin[land] in weighed:
                continue
            weighed.add(self.land_twin[land])
            hand[land] -= 1  # a modal card played as a land is no longer a spell in hand
            after = battlefield + self.unit[self.land_group[land]]
            if self.tapped[land]:
                plan = self._spend(hand, battlefield, sources)
            else:
                plan = self._spend(hand, after, sources + 1)
            known = self._payments(after)
            orphans = 0
            for k in self.cast_order:
                if hand[k]:
                    unpaid = known.get(pips[k])
                    if unpaid is None:
                        unpaid = self._solve(known, after, pips[k])
                    orphans += hand[k] * unpaid
            hand[land] += 1
            score = (plan[0], self.tapped[land], -orphans)
            if best_score is None or score > best_score:
                best_land, best_plan, best_score = land, plan, score
        return best_land, best_plan

    # -- one game

    def play(self, rng: random.Random, on_draw: bool, tally: _Tally) -> None:
        need, pips, unit, is_land = self.need, self.pips, self.unit, self.is_land
        land_kinds, modal_kinds = self.land_kinds, self.modal_kinds
        hand, library = self._deal(rng, tally)
        tally.games += 1

        drawn = hand[:]  # copies of each kind seen so far
        became_land = [0] * len(hand)  # modal copies spent as land drops
        followed = [False] * len(hand)  # kinds whose castability is being sampled this game
        in_hand = cards_seen = sum(hand)
        lands_seen = sum(hand[k] for k in land_kinds)
        battlefield = 0  # every mana source in play, packed by source group
        sources = 0
        lands = 0
        next_draw = 0

        for turn in range(1, self.turns + 1):
            if (on_draw or turn > 1) and next_draw < len(library):
                card = library[next_draw]
                next_draw += 1
                hand[card] += 1
                drawn[card] += 1
                in_hand += 1
                cards_seen += 1
                if is_land[card]:
                    lands_seen += 1

            # Land drop. `usable`/`mana` are what can be tapped this turn; a tapped land joins them next turn.
            usable, mana = battlefield, sources
            plan: Optional[_Plan] = None
            choices = [k for k in land_kinds if hand[k]] or [k for k in modal_kinds if hand[k]]
            # Castability is judged against every real land the hand could have played untapped, not
            # only the one chosen below: picking between equally good plays must not make the mana
            # base look worse. `views` are those battlefields and `reach` the mana each of them has.
            views = {battlefield + unit[self.land_group[k]] for k in choices if is_land[k] and not self.tapped[k]}
            reach = sources + 1
            if choices:
                land = choices[0]
                if len(choices) > 1:
                    land, plan = self._choose_land(choices, hand, battlefield, sources)
                hand[land] -= 1
                in_hand -= 1
                lands += 1
                if not is_land[land]:
                    became_land[land] += 1
                battlefield += unit[self.land_group[land]]
                sources += 1
                if not self.tapped[land]:
                    usable, mana = battlefield, sources
            if plan is None:
                plan = self._spend(hand, usable, mana)
            spent, casts = plan
            for card in casts:
                hand[card] -= 1
            in_hand -= len(casts)

            if not views:
                views, reach = {usable}, mana
            payments = [(view, self._payments(view)) for view in views]
            for late, k in self.checks[turn]:
                if late == 0:
                    if drawn[k] == became_land[k]:
                        continue
                    followed[k] = True
                    tally.samples[k] += 1
                elif not followed[k]:
                    continue
                if need[k] <= reach:
                    tally.enough[late][k] += 1
                    for view, known in payments:
                        unpaid = known.get(pips[k])
                        if unpaid is None:
                            unpaid = self._solve(known, view, pips[k])
                        if unpaid == 0:
                            tally.castable[late][k] += 1
                            break

            for card in casts:  # mana creatures and rocks start working next turn
                if self.ramp_group[card] >= 0:
                    battlefield += unit[self.ramp_group[card]]
                    sources += 1

            index = turn - 1
            tally.lands[index] += lands
            if lands == turn:
                tally.on_time[index] += 1
            tally.mana[index] += mana
            tally.spent[index] += spent
            tally.cast[index] += len(casts)
            tally.hand[index] += in_hand
            if turn == SCREW_TURN and lands < SCREW_LANDS:
                tally.screw += 1
            if turn == FLOOD_TURN and 100 * lands_seen >= FLOOD_LAND_PERCENT * cards_seen:
                tally.flood += 1


def _unpack(packed: int, masks: Sequence[int]) -> List[Tuple[int, int]]:
    """A packed integer back as (colour mask, count) groups, leaving out the empty ones."""
    groups = []
    for index, mask in enumerate(masks):
        count = packed >> (_BITS * index) & ((1 << _BITS) - 1)
        if count:
            groups.append((mask, count))
    return groups


# -------------------------------------------------------------------- results


def _rate(count: float, total: int) -> Optional[float]:
    return round(count / total, 4) if total else None


def _cost_text(cost: ManaCost) -> str:
    symbols = ["X"] if cost.has_x else []
    if cost.generic or not (cost.pips or cost.has_x):
        symbols.append(str(cost.generic))
    symbols += ["/".join(pip) for pip in cost.pips]
    return "".join("{" + symbol + "}" for symbol in symbols)


def _composition(kinds: Sequence[_Kind]) -> dict:
    spells = [kind for kind in kinds if not kind.is_land]
    spell_count = sum(kind.copies for kind in spells)
    curve = [0] * 8
    pips = {colour: 0.0 for colour in MANA_SYMBOLS}
    sources = {colour: 0 for colour in MANA_SYMBOLS}
    land_sources = {colour: 0 for colour in MANA_SYMBOLS}
    for kind in spells:
        curve[min(kind.mana_value, 7)] += kind.copies
        for pip in kind.cost.pips:
            for colour in pip:
                pips[colour] += kind.copies / len(pip)
    for kind in kinds:
        for colour in set((kind.land_colours or "") + (kind.ramp_colours or "")):
            sources[colour] += kind.copies
        if kind.is_land:
            for colour in kind.land_colours or "":
                land_sources[colour] += kind.copies
    creatures = sum(kind.copies for kind in spells if kind.is_creature)
    return {
        "cards": sum(kind.copies for kind in kinds),
        "lands": sum(kind.copies for kind in kinds if kind.is_land),
        "modal_lands": sum(kind.copies for kind in kinds if kind.is_modal_land),
        "tapped_lands": sum(kind.copies for kind in kinds if kind.is_land and kind.enters_tapped),
        "spells": spell_count,
        "creatures": creatures,
        "other_spells": spell_count - creatures,
        "nonland_mana_sources": sum(kind.copies for kind in spells if kind.ramp_colours is not None),
        "avg_mana_value": round(sum(kind.mana_value * kind.copies for kind in spells) / spell_count, 4)
        if spell_count
        else 0.0,
        "curve": curve,
        "pips": {colour: round(count, 2) for colour, count in pips.items()},
        "sources": sources,
        "land_sources": land_sources,
    }


def _turn_rows(tally: _Tally) -> List[dict]:
    games = tally.games
    return [
        {
            "turn": index + 1,
            "lands": _rate(tally.lands[index], games),
            "hit_all_land_drops": _rate(tally.on_time[index], games),
            "mana_available": _rate(tally.mana[index], games),
            "mana_spent": _rate(tally.spent[index], games),
            "spells_cast": _rate(tally.cast[index], games),
            "cards_in_hand": _rate(tally.hand[index], games),
        }
        for index in range(len(tally.lands))
    ]


def _card_rows(kinds: Sequence[_Kind], tally: _Tally, turns: int) -> List[dict]:
    rows = []
    for index, kind in enumerate(kinds):
        if kind.is_land:
            continue
        curve_turn = max(1, kind.mana_value)
        samples = tally.samples[index]
        measured = [curve_turn + late <= turns for late in range(LATE_TURNS + 1)]
        rows.append(
            {
                "name": kind.name,
                "copies": kind.copies,
                "mana_value": kind.mana_value,
                "cost": _cost_text(kind.cost),
                "curve_turn": curve_turn,
                "samples": samples,
                "castable": [
                    _rate(tally.castable[late][index], samples) if measured[late] else None
                    for late in range(LATE_TURNS + 1)
                ],
                "enough_mana": [
                    _rate(tally.enough[late][index], samples) if measured[late] else None
                    for late in range(LATE_TURNS + 1)
                ],
            }
        )
    rows.sort(key=lambda row: (row["mana_value"], row["name"]))
    return rows


def _definitions() -> Dict[str, str]:
    keep = KEEP_LANDS
    return {
        "keep_rule": (
            "London mulligan, looking at seven cards each time: keep seven with "
            f"{keep[7][0]}-{keep[7][1]} lands; after one mulligan keep if the seven hold "
            f"{keep[6][0]}-{keep[6][1]} lands; after two, {keep[5][0]}-{keep[5][1]}; always keep four cards. "
            "Each mulligan bottoms one card: a land while the hand holds more than "
            f"{LANDS_WORTH_KEEPING[6]} lands ({LANDS_WORTH_KEEPING[4]} when keeping four), "
            "otherwise the most expensive spell."
        ),
        "mana_screw": f"Fewer than {SCREW_LANDS} lands on the battlefield after the player's own turn {SCREW_TURN}.",
        "mana_flood": (
            f"At least {FLOOD_LAND_PERCENT}% of the cards seen by the end of turn {FLOOD_TURN} "
            "(kept hand plus draws) are lands."
        ),
        "hit_all_land_drops": "A land was played on every turn up to and including this one.",
        "mana_available": (
            "Mana that can be tapped this turn: lands on the battlefield, except one that entered tapped "
            "this turn, plus mana creatures and mana rocks cast on earlier turns."
        ),
        "mana_spent": (
            "Mana paid for spells this turn; the player casts the set of spells in hand that uses "
            "the most of the mana available."
        ),
        "castable": (
            "In games where a copy had been drawn by the card's curve turn (its mana value, at least 1): "
            "some land drop the hand allowed would have left enough mana of the right colours to cast it "
            "on that turn, by one turn later, and by two turns later."
        ),
        "enough_mana": (
            "The same as castable but counting mana only and ignoring colours, "
            "so the gap between the two is what the colours of the mana base cost."
        ),
        "model": (
            "A mana and curve model, not a rules engine: one land per turn, then as much mana as possible "
            "spent on spells. Card draw, removal, cost reduction, the opponent and everything else "
            "the cards do are ignored; X counts as zero."
        ),
    }


def analyze(deck: Deck, db: CardDatabase, games: int = 20000, turns: int = 8, seed: int = 0) -> dict:
    """Goldfish ``deck`` for ``games`` games of ``turns`` turns; see the module docstring for the result.

    The same deck, card data and arguments always give the same result: the games draw on their
    own ``random.Random(seed)`` and never on the global generator. Raises ``ValueError`` for a
    card the database does not know, a deck of fewer than seven cards, or non-positive
    ``games``/``turns``.
    """
    if games < 1 or turns < 1:
        raise ValueError("games and turns must both be at least 1")
    kinds = _deck_kinds(deck, db)
    goldfish = _Goldfish(kinds, turns)
    rng = random.Random(seed)
    play, draw = _Tally(turns, len(kinds)), _Tally(turns, len(kinds))
    for game in range(games):
        if game % 2 == 0:
            goldfish.play(rng, False, play)
        else:
            goldfish.play(rng, True, draw)
    overall = play.plus(draw)
    seats = {"overall": overall, "play": play, "draw": draw}

    kept = range(SMALLEST_HAND, HAND_SIZE + 1)
    return {
        "deck": deck.name,
        "games": games,
        "turns": turns,
        "seed": seed,
        "games_on_play": play.games,
        "games_on_draw": draw.games,
        "composition": _composition(kinds),
        "opening_hand": {
            "lands_in_seven": [_rate(count, games) for count in overall.seven_lands],
            "mulligan_rate": _rate(games - overall.kept_size[HAND_SIZE], games),
            "kept_hand_sizes": {str(size): _rate(overall.kept_size[size], games) for size in reversed(kept)},
            "avg_kept_hand_size": _rate(sum(size * overall.kept_size[size] for size in kept), games),
            "lands_in_kept_hand": [_rate(count, games) for count in overall.kept_lands],
            "avg_lands_in_kept_hand": _rate(sum(n * count for n, count in enumerate(overall.kept_lands)), games),
        },
        "by_turn": {seat: _turn_rows(tally) for seat, tally in seats.items()},
        "mana_screw": {
            seat: _rate(tally.screw, tally.games) if turns >= SCREW_TURN else None for seat, tally in seats.items()
        },
        "mana_flood": {
            seat: _rate(tally.flood, tally.games) if turns >= FLOOD_TURN else None for seat, tally in seats.items()
        },
        "cards": _card_rows(kinds, overall, turns),
        "definitions": _definitions(),
        "warnings": [
            f"{kind.name}: the card database lists no mana for this land, so it only pays generic costs here."
            for kind in kinds
            if kind.land_colours == ""
        ],
    }


# ------------------------------------------------------------------ rendering


def _pct(value: Optional[float], width: int = 6) -> str:
    return f"{'-' if value is None else format(value, '.1%'):>{width}}"


def _num(value: Optional[float], width: int = 5) -> str:
    return f"{'-' if value is None else format(value, '.2f'):>{width}}"


def _wrapped(text: str, indent: str = "  ") -> List[str]:
    return textwrap.wrap(text, width=100, initial_indent=indent, subsequent_indent=indent)


def format_text(result: dict) -> str:
    """A terminal summary of an :func:`analyze` result."""
    comp = result["composition"]
    opening = result["opening_hand"]
    definitions = result["definitions"]
    out: List[str] = []

    out.append(
        f"Goldfish analysis of {result['deck']}: {result['games']:,} games of {result['turns']} turns "
        f"(seed {result['seed']})"
    )
    out += _wrapped(definitions["model"], indent="")

    out += ["", "COMPOSITION"]
    out.append(
        f"  {comp['cards']} cards: {comp['lands']} lands ({comp['tapped_lands']} always enter tapped), "
        f"{comp['spells']} spells ({comp['creatures']} creatures, {comp['other_spells']} others)"
    )
    out.append(
        f"  Spell/land modal cards: {comp['modal_lands']}   Nonland mana sources: {comp['nonland_mana_sources']}   "
        f"Average mana value of spells: {comp['avg_mana_value']:.2f}"
    )
    out.append("  Mana value " + "".join(f"{label:>5}" for label in ["0", "1", "2", "3", "4", "5", "6", "7+"]))
    out.append("  Spells     " + "".join(f"{count:>5}" for count in comp["curve"]))
    out.append("  Colour   Pips   Sources  (lands)")
    for colour in MANA_SYMBOLS:
        if comp["pips"][colour]:
            out.append(
                f"  {colour:<6} {comp['pips'][colour]:>6g} {comp['sources'][colour]:>9} "
                f"{comp['land_sources'][colour]:>8}"
            )

    out += ["", "OPENING HAND"]
    out.append("  Lands in first seven " + "".join(f"{lands:>7}" for lands in range(HAND_SIZE + 1)))
    out.append("                       " + "".join(_pct(share, 7) for share in opening["lands_in_seven"]))
    sizes = ", ".join(f"{size} cards {_pct(share, 0)}" for size, share in opening["kept_hand_sizes"].items())
    out.append(
        f"  Mulligan rate {_pct(opening['mulligan_rate'], 0)}; average kept hand "
        f"{opening['avg_kept_hand_size']:.2f} cards with {opening['avg_lands_in_kept_hand']:.2f} lands"
    )
    out.append(f"  Kept: {sizes}")
    out += _wrapped(f"Keep rule: {definitions['keep_rule']}")

    out += ["", "TURN BY TURN (all games: half on the play, half on the draw)"]
    out.append("  Turn  Lands  All drops   Mana  Spent  Spells   Hand  |  Lands play/draw   All drops play/draw")
    seats = result["by_turn"]
    for row, play, draw in zip(seats["overall"], seats["play"], seats["draw"]):
        out.append(
            f"  {row['turn']:>4}  {_num(row['lands'])}  {_pct(row['hit_all_land_drops'], 9)}  "
            f"{_num(row['mana_available'])}  {_num(row['mana_spent'])}  {_num(row['spells_cast'], 6)}  "
            f"{_num(row['cards_in_hand'])}  |    {_num(play['lands'])} / {_num(draw['lands'])}"
            f"      {_pct(play['hit_all_land_drops'])} / {_pct(draw['hit_all_land_drops'])}"
        )
    available = sum(row["mana_available"] for row in seats["overall"])
    if available:
        used = sum(row["mana_spent"] for row in seats["overall"]) / available
        out.append(f"  Mana used over {result['turns']} turns: {used:.0%} of the mana available")

    out += ["", "MANA SCREW AND FLOOD"]
    for label, key in (("Screw", "mana_screw"), ("Flood", "mana_flood")):
        rates = result[key]
        out.append(
            f"  {label} {_pct(rates['overall'])}  (play {_pct(rates['play'], 0)}, draw {_pct(rates['draw'], 0)})"
        )
        out += _wrapped(definitions[key], indent="      ")

    out += ["", "CASTABLE ON TIME (in games where the card was drawn by its curve turn)"]
    width = max([len(row["name"]) for row in result["cards"]] + [4])
    out.append(
        f"  {'Card':<{width}}  Copies  {'Cost':<14} Turn  On curve  +1 turn  +2 turns  Enough mana on curve"
    )
    for row in result["cards"]:
        castable = row["castable"]
        out.append(
            f"  {row['name']:<{width}}  {row['copies']:>6}  {row['cost']:<14} {row['curve_turn']:>4}  "
            f"{_pct(castable[0], 8)}  {_pct(castable[1], 7)}  {_pct(castable[2], 8)}  {_pct(row['enough_mana'][0], 8)}"
        )

    if result["warnings"]:
        out += ["", "WARNINGS"]
        for warning in result["warnings"]:
            out += _wrapped(warning)
    return "\n".join(out) + "\n"
