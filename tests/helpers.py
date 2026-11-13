"""Small fixtures shared by the tests: a hand-made card database and synthetic game records."""

from mtgsim.carddb import CardDatabase, parse_card_script

SCRIPTS = [
    "Name:Mountain\nManaCost:no cost\nTypes:Basic Land Mountain\nOracle:({T}: Add {R}.)",
    "Name:Forest\nManaCost:no cost\nTypes:Basic Land Forest\nOracle:({T}: Add {G}.)",
    "Name:Lightning Strike\nManaCost:1 R\nTypes:Instant\nOracle:Lightning Strike deals 3 damage to any target.",
    "Name:Shock\nManaCost:R\nTypes:Instant\nOracle:Shock deals 2 damage to any target.",
    "Name:Hill Giant\nManaCost:3 R\nTypes:Creature Giant\nPT:3/3\nOracle:",
    "Name:Grizzly Bears\nManaCost:1 G\nTypes:Creature Bear\nPT:2/2\nOracle:",
    "Name:Rat Colony\nManaCost:1 B\nTypes:Creature Rat\nPT:2/1\nK:A deck can have any number of cards named CARDNAME.\nOracle:",
    "Name:Black Lotus\nManaCost:0\nTypes:Artifact\nOracle:{T}, Sacrifice Black Lotus: Add three mana of any one color.",
    "Name:Fire\nManaCost:1 R\nTypes:Instant\nAlternateMode:Split\nOracle:Fire deals 2 damage.\n\nALTERNATE\n\n"
    "Name:Ice\nManaCost:1 U\nTypes:Instant\nOracle:Tap target permanent.",
    "Name:Delver of Secrets\nManaCost:U\nTypes:Creature Human Wizard\nPT:1/1\nAlternateMode:DoubleFaced\nOracle:\n\n"
    "ALTERNATE\n\nName:Insectile Aberration\nManaCost:no cost\nTypes:Creature Human Insect\nPT:3/2\nOracle:Flying",
]
# set code -> rarity, per card, as the edition files would assign them
PRINTINGS = {
    "Mountain": {"NEW": "L", "OLD": "L"}, "Forest": {"NEW": "L", "OLD": "L"},
    "Lightning Strike": {"NEW": "C"}, "Shock": {"OLD": "C"}, "Hill Giant": {"NEW": "U", "OLD": "C"},
    "Grizzly Bears": {"NEW": "C"}, "Rat Colony": {"NEW": "C"}, "Black Lotus": {"OLD": "R"},
    "Fire // Ice": {"NEW": "U"}, "Delver of Secrets": {"NEW": "C"},
}


def make_db() -> CardDatabase:
    cards = [parse_card_script(s) for s in SCRIPTS]
    for card in cards:
        card.sets = dict(PRINTINGS.get(card.name, {}))
    return CardDatabase(cards)


def signals(opening=None, drawn=None, played=None, end_hand=None, lands_in_hand=0, idle_own=None, idle_opp=None,
            counter=None, removal=None, roles=None):
    """Player fields as a driver with misplay tracking records them; pass as ``a_extra``/``b_extra`` to ``game``."""
    return {"opening": opening or {}, "drawn": drawn or {}, "played": played or {},
            "endHand": end_hand or {}, "endHandLands": lands_in_hand, "idleOwn": idle_own or {},
            "idleOpp": idle_opp or {}, "counter": counter or {}, "removal": removal or {}, "roles": roles or {}}


def game(a, b, index, winner=None, first="a", status="ok", turns=6, a_extra=None, b_extra=None):
    """A stored game record for pairing (a, b). ``winner``/``first`` are "a", "b" or None."""
    seat_a = 0 if index % 2 == 0 else 1
    seats = [a, b] if seat_a == 0 else [b, a]
    seat = {"a": seat_a, "b": 1 - seat_a, None: -1}
    players = [None, None]
    for who, extra in (("a", a_extra), ("b", b_extra)):
        player = {"mainCount": 60, "sideCount": 0, "life": 20, "mulligans": 0, "turns": turns,
                  "lossReason": None, "altWin": None, "opening": {}, "drawn": {}, "played": {}}
        if winner is not None and who != winner:
            player["lossReason"] = "LifeReachedZero"
            player["life"] = 0
        player.update(extra or {})
        players[seat[who]] = player
    return {"a": a, "b": b, "game": index, "seats": seats, "id": f"{a}|{b}|{index}", "seed": index,
            "status": status, "winner_seat": seat[winner] if status == "ok" else -1,
            "first_seat": seat[first], "turns": turns * 2, "end_reason": "AllOpponentsLost", "ms": 1000,
            "players": players}
