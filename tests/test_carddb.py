"""Tests for mtgsim.carddb: card-script parsing, mana costs, name lookup, edition files, the cache.

The card scripts below are short excerpts copied from Forge's ``res/cardsfolder`` so the syntax is
the real one; nothing here reads the Forge checkout at run time.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mtgsim import carddb
from mtgsim.carddb import Card, CardDatabase, Face, ManaCost, norm_name, parse_card_script
from mtgsim.forge import ForgeInstall

LIGHTNING_BOLT = """\
Name:Lightning Bolt
ManaCost:R
Types:Instant
A:SP$ DealDamage | ValidTgts$ Any | NumDmg$ 3 | SpellDescription$ CARDNAME deals 3 damage to any target.
Oracle:Lightning Bolt deals 3 damage to any target.
"""

FIRE_ICE = """\
Name:Fire
ManaCost:1 R
Types:Instant
A:SP$ DealDamage | ValidTgts$ Any | NumDmg$ 2 | TargetMin$ 1 | TargetMax$ 2 | DividedAsYouChoose$ 2 | SpellDescription$ CARDNAME deals 2 damage divided as you choose among one or two targets.
AlternateMode:Split
Oracle:Fire deals 2 damage divided as you choose among one or two targets.

ALTERNATE

Name:Ice
ManaCost:1 U
Types:Instant
A:SP$ Tap | ValidTgts$ Permanent | SubAbility$ DBDraw | SpellDescription$ Tap target permanent. Draw a card.
SVar:DBDraw:DB$ Draw
Oracle:Tap target permanent.\\nDraw a card.
"""

BONECRUSHER_GIANT = """\
Name:Bonecrusher Giant
ManaCost:2 R
Types:Creature Giant
PT:4/3
T:Mode$ BecomesTarget | ValidTarget$ Card.Self | ValidSource$ Spell | TriggerZones$ Battlefield | Execute$ TrigDmg | TriggerDescription$ When CARDNAME becomes the target of a spell, CARDNAME deals 2 damage to that spell's controller.
SVar:TrigDmg:DB$ DealDamage | Defined$ TriggeredSourceController | NumDmg$ 2
AlternateMode:Adventure
Oracle:Whenever Bonecrusher Giant becomes the target of a spell, Bonecrusher Giant deals 2 damage to that spell's controller.

ALTERNATE

Name:Stomp
ManaCost:1 R
Types:Instant Adventure
A:SP$ Effect | StaticAbilities$ STCantPrevent | AILogic$ Burn | SubAbility$ DBDamage | SpellDescription$ Damage can't be prevented this turn. CARDNAME deals 2 damage to any target.
SVar:DBDamage:DB$ DealDamage | ValidTgts$ Any | NumDmg$ 2 | NoPrevention$ True
Oracle:Damage can't be prevented this turn. Stomp deals 2 damage to any target.
"""

DELVER = """\
Name:Delver of Secrets
ManaCost:U
Types:Creature Human Wizard
PT:1/1
T:Mode$ Phase | Phase$ Upkeep | ValidPlayer$ You | TriggerZones$ Battlefield | Execute$ TrigPeek | TriggerDescription$ At the beginning of your upkeep, look at the top card of your library.
DeckHints:Type$Instant|Sorcery
AlternateMode:DoubleFaced
Oracle:At the beginning of your upkeep, look at the top card of your library. You may reveal that card. If an instant or sorcery card is revealed this way, transform Delver of Secrets.

ALTERNATE

Name:Insectile Aberration
ManaCost:no cost
Colors:blue
Types:Creature Human Insect
PT:3/2
K:Flying
Oracle:Flying
"""

SHATTERSKULL_SMASHING = """\
Name:Shatterskull Smashing
ManaCost:X R R
Types:Sorcery
A:SP$ DealDamage | NumDmg$ Y | ValidTgts$ Creature,Planeswalker | TargetMin$ 0 | TargetMax$ 2 | SpellDescription$ CARDNAME deals X damage divided as you choose among up to two target creatures and/or planeswalkers.
SVar:X:Count$xPaid
AlternateMode:Modal
Oracle:Shatterskull Smashing deals X damage divided as you choose among up to two target creatures and/or planeswalkers.

ALTERNATE

Name:Shatterskull, the Hammer Pass
ManaCost:no cost
Types:Land
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplaceWith$ DBTap | ReplacementResult$ Updated | Description$ As CARDNAME enters, you may pay 3 life. If you don't, it enters tapped.
SVar:DBTap:DB$ Tap | ETB$ True | Defined$ Self | UnlessCost$ PayLife<3> | UnlessPayer$ You | StackDescription$ enters tapped.
A:AB$ Mana | Cost$ T | Produced$ R | SpellDescription$ Add {R}.
Oracle:As Shatterskull, the Hammer Pass enters, you may pay 3 life. If you don't, it enters tapped.\\n{T}: Add {R}.
"""

BRANCHLOFT_PATHWAY = """\
Name:Branchloft Pathway
ManaCost:no cost
Types:Land
A:AB$ Mana | Cost$ T | Produced$ G | SpellDescription$ Add {G}.
AlternateMode:Modal
Oracle:{T}: Add {G}.

ALTERNATE

Name:Boulderloft Pathway
ManaCost:no cost
Types:Land
A:AB$ Mana | Cost$ T | Produced$ W | SpellDescription$ Add {W}.
Oracle:{T}: Add {W}.
"""

PLAINS = """\
Name:Plains
ManaCost:no cost
Types:Basic Land Plains
Oracle:({T}: Add {W}.)
"""

SNOW_ISLAND = """\
Name:Snow-Covered Island
ManaCost:no cost
Types:Basic Snow Land Island
Oracle:({T}: Add {U}.)
"""

WASTES = """\
Name:Wastes
ManaCost:no cost
Types:Basic Land
A:AB$ Mana | Cost$ T | Produced$ C | SpellDescription$ Add {C}.
Oracle:{T}: Add {C}.
"""

STEAM_VENTS = """\
Name:Steam Vents
ManaCost:no cost
Types:Land Island Mountain
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplaceWith$ DBTap | ReplacementResult$ Updated | Description$ As CARDNAME enters, you may pay 2 life. If you don't, it enters tapped.
SVar:DBTap:DB$ Tap | ETB$ True | Defined$ Self | UnlessCost$ PayLife<2> | UnlessPayer$ You | StackDescription$ enters tapped.
Oracle:({T}: Add {U} or {R}.)\\nAs Steam Vents enters, you may pay 2 life. If you don't, it enters tapped.
"""

TEMPLE_OF_TRIUMPH = """\
Name:Temple of Triumph
ManaCost:no cost
Types:Land
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplacementResult$ Updated | ReplaceWith$ ETBTapped | Description$ CARDNAME enters tapped.
SVar:ETBTapped:DB$ Tap | Defined$ Self | ETB$ True
T:Mode$ ChangesZone | Origin$ Any | Destination$ Battlefield | ValidCard$ Card.Self | Execute$ TrigScry | TriggerDescription$ When CARDNAME enters, scry 1.
SVar:TrigScry:DB$ Scry | ScryNum$ 1
A:AB$ Mana | Cost$ T | Produced$ Combo R W | SpellDescription$ Add {R} or {W}.
Oracle:Temple of Triumph enters tapped.\\nWhen Temple of Triumph enters, scry 1.\\n{T}: Add {R} or {W}.
"""

# The pre-2024 templating of the same kind of land.
OLD_GUILDGATE = """\
Name:Izzet Guildgate
ManaCost:no cost
Types:Land Gate
A:AB$ Mana | Cost$ T | Produced$ Combo U R | SpellDescription$ Add {U} or {R}.
Oracle:Izzet Guildgate enters the battlefield tapped.\\n{T}: Add {U} or {R}.
"""

CONCEALED_COURTYARD = """\
Name:Concealed Courtyard
ManaCost:no cost
Types:Land
R:Event$ Moved | ValidCard$ Card.Self | Destination$ Battlefield | ReplaceWith$ LandTapped | ReplacementResult$ Updated | Description$ CARDNAME enters tapped unless you control two or fewer other lands.
SVar:LandTapped:DB$ Tap | Defined$ Self | ETB$ True | ConditionPresent$ Land.YouCtrl | ConditionCompare$ GT2
A:AB$ Mana | Cost$ T | Produced$ Combo W B | SpellDescription$ Add {W} or {B}.
Oracle:Concealed Courtyard enters tapped unless you control two or fewer other lands.\\n{T}: Add {W} or {B}.
"""

EVOLVING_WILDS = """\
Name:Evolving Wilds
ManaCost:no cost
Types:Land
A:AB$ ChangeZone | Cost$ T Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | Tapped$ True | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | SpellDescription$ Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.
Oracle:{T}, Sacrifice Evolving Wilds: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.
"""

FABLED_PASSAGE = """\
Name:Fabled Passage
ManaCost:no cost
Types:Land
A:AB$ ChangeZone | Cost$ T Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | Tapped$ True | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | RememberChanged$ True | SubAbility$ DBUntap | StackDescription$ SpellDescription | SpellDescription$ Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control four or more lands, untap that land.
SVar:DBUntap:DB$ Untap | Defined$ Remembered | ConditionPresent$ Land.YouCtrl | ConditionCompare$ GE4 | SubAbility$ DBCleanup | StackDescription$ None
SVar:DBCleanup:DB$ Cleanup | ClearRemembered$ True
Oracle:{T}, Sacrifice Fabled Passage: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control four or more lands, untap that land.
"""

PRISMATIC_VISTA = """\
Name:Prismatic Vista
ManaCost:no cost
Types:Land
A:AB$ ChangeZone | Cost$ T PayLife<1> Sac<1/CARDNAME> | Origin$ Library | Destination$ Battlefield | ChangeType$ Land.Basic | ChangeTypeDesc$ basic land | SpellDescription$ Search your library for a basic land card, put it onto the battlefield, then shuffle.
Oracle:{T}, Pay 1 life, Sacrifice Prismatic Vista: Search your library for a basic land card, put it onto the battlefield, then shuffle.
"""

MANA_CONFLUENCE = """\
Name:Mana Confluence
ManaCost:no cost
Types:Land
A:AB$ Mana | Cost$ T PayLife<1> | Produced$ Any | Amount$ 1 | SpellDescription$ Add one mana of any color.
Oracle:{T}, Pay 1 life: Add one mana of any color.
"""

LLANOWAR_ELVES = """\
Name:Llanowar Elves
ManaCost:G
Types:Creature Elf Druid
PT:1/1
A:AB$ Mana | Cost$ T | Produced$ G | SpellDescription$ Add {G}.
Oracle:{T}: Add {G}.
"""

BIRDS_OF_PARADISE = """\
Name:Birds of Paradise
ManaCost:G
Types:Creature Bird
PT:0/1
A:AB$ Mana | Cost$ T | Produced$ Any | SpellDescription$ Add one mana of any color.
K:Flying
Oracle:Flying\\n{T}: Add one mana of any color.
"""

SOL_RING = """\
Name:Sol Ring
ManaCost:1
Types:Artifact
A:AB$ Mana | Cost$ T | Produced$ C | Amount$ 2 | SpellDescription$ Add {C}{C}.
Oracle:{T}: Add {C}{C}.
"""

RAT_COLONY = """\
Name:Rat Colony
ManaCost:1 B
Types:Creature Rat
PT:2/1
K:A deck can have any number of cards named CARDNAME.
S:Mode$ Continuous | AffectedDefined$ Self | AddPower$ X | Description$ CARDNAME gets +1/+0 for each other Rat you control.
SVar:X:Count$Valid Rat.YouCtrl+Other
DeckNeeds:Type$Rat
Oracle:Rat Colony gets +1/+0 for each other Rat you control.\\nA deck can have any number of cards named Rat Colony.
"""

SEVEN_DWARVES = """\
Name:Seven Dwarves
ManaCost:1 R
Types:Creature Dwarf
PT:2/2
K:DeckLimit:7:A deck can have up to seven cards named CARDNAME.
S:Mode$ Continuous | AffectedDefined$ Self | AddPower$ X | AddToughness$ X | Description$ CARDNAME gets +1/+1 for each other creature named Seven Dwarves you control.
Oracle:Seven Dwarves gets +1/+1 for each other creature named Seven Dwarves you control.\\nA deck can have up to seven cards named Seven Dwarves.
"""

NAZGUL = """\
Name:Nazgûl
ManaCost:2 B
Types:Creature Wraith Knight
PT:1/2
K:Deathtouch
K:DeckLimit:9:A deck can have up to nine cards named CARDNAME.
Oracle:Deathtouch\\nWhen Nazgûl enters, the Ring tempts you.
"""

URZAS_SAGA_LIKE = """\
Name:Urza's Bauble
ManaCost:0
Types:Artifact
Oracle:{T}, Sacrifice Urza's Bauble: Look at a card at random in target player's hand.
"""

LEGENDARY = """\
Name:Thalia, Guardian of Thraben
ManaCost:1 W
Types:Legendary Creature Human Soldier
PT:2/1
K:First Strike
Oracle:First strike\\nNoncreature spells cost {1} more to cast.
"""


def card(script):
    parsed = parse_card_script(script)
    assert parsed is not None, "script did not parse"
    return parsed


class ManaCostTest(unittest.TestCase):
    def test_no_cost_and_empty_cost_nothing(self):
        for text in ("no cost", "No Cost", "  no cost  ", "", None):
            with self.subTest(text=text):
                cost = ManaCost.parse(text)
                self.assertEqual(cost.cmc, 0)
                self.assertEqual(cost.generic, 0)
                self.assertEqual(cost.pips, ())
                self.assertFalse(cost.has_x)

    def test_generic_only(self):
        self.assertEqual(ManaCost.parse("3").cmc, 3)
        self.assertEqual(ManaCost.parse("3").generic, 3)
        self.assertEqual(ManaCost.parse("0").cmc, 0)

    def test_two_digit_generic_is_not_mistaken_for_a_hybrid_symbol(self):
        # "2R" means "two generic or one red"; "10", "12" and "20" are plain generic amounts.
        for text, expected in (("10", 10), ("12", 12), ("20", 20), ("16", 16)):
            with self.subTest(text=text):
                cost = ManaCost.parse(text)
                self.assertEqual(cost.cmc, expected)
                self.assertEqual(cost.generic, expected)

    def test_generic_plus_coloured(self):
        cost = ManaCost.parse("1 R")
        self.assertEqual((cost.generic, cost.cmc), (1, 2))
        self.assertEqual(cost.pips, ("R",))
        self.assertEqual(cost.colours(), "R")

    def test_repeated_and_multiple_colours(self):
        cost = ManaCost.parse("2 W W U")
        self.assertEqual(cost.cmc, 5)
        self.assertEqual(sorted(cost.pips), ["U", "W", "W"])
        self.assertEqual(cost.colours(), "WU")  # always in WUBRG order

    def test_colours_are_reported_in_wubrg_order_whatever_the_cost_order(self):
        self.assertEqual(ManaCost.parse("G R B U W").colours(), "WUBRG")

    def test_hybrid_symbol_is_one_pip_payable_by_either_colour(self):
        cost = ManaCost.parse("1 GW GW")  # Kitchen Finks
        self.assertEqual(cost.cmc, 3)
        self.assertEqual(cost.generic, 1)
        self.assertEqual(len(cost.pips), 2)
        for pip in cost.pips:
            self.assertEqual(set(pip), {"G", "W"})
        self.assertEqual(cost.colours(), "WG")

    def test_x_costs_nothing_but_is_flagged(self):
        cost = ManaCost.parse("X R")  # Fireball
        self.assertTrue(cost.has_x)
        self.assertEqual(cost.cmc, 1)
        self.assertEqual(cost.pips, ("R",))
        double = ManaCost.parse("X X G")
        self.assertTrue(double.has_x)
        self.assertEqual(double.cmc, 1)

    def test_phyrexian_mana_counts_for_mana_value_but_requires_no_colour(self):
        probe = ManaCost.parse("UP")  # Gitaxian Probe
        self.assertEqual(probe.cmc, 1)
        self.assertEqual(probe.pips, ())
        dismember = ManaCost.parse("1 BP BP")
        self.assertEqual(dismember.cmc, 3)
        self.assertEqual(dismember.generic, 1)
        self.assertEqual(dismember.colours(), "")
        self.assertEqual(ManaCost.parse("2 GUP").cmc, 3)  # hybrid Phyrexian (Tamiyo, Compleated Sage)

    def test_monocoloured_hybrid_counts_two_each(self):
        self.assertEqual(ManaCost.parse("2W 2W 2W").cmc, 6)  # Spectral Procession
        self.assertEqual(ManaCost.parse("2/R 2/R").cmc, 4)

    def test_colourless_and_snow_symbols(self):
        colourless = ManaCost.parse("3 C")
        self.assertEqual(colourless.cmc, 4)
        self.assertEqual(colourless.pips, ("C",))
        self.assertEqual(colourless.colours(), "", "colourless is not a colour")
        self.assertEqual(ManaCost.parse("S S").cmc, 2)

    def test_extra_whitespace_is_ignored(self):
        self.assertEqual(ManaCost.parse("  1   R "), ManaCost.parse("1 R"))


class NormNameTest(unittest.TestCase):
    def test_case_and_surrounding_whitespace(self):
        self.assertEqual(norm_name("  Lightning   BOLT "), norm_name("lightning bolt"))

    def test_accents_are_ignored(self):
        self.assertEqual(norm_name("Lim-Dûl's Vault"), norm_name("Lim-Dul's Vault"))
        self.assertEqual(norm_name("Jötun Grunt"), norm_name("Jotun Grunt"))
        self.assertEqual(norm_name("Nazgûl"), norm_name("nazgul"))

    def test_apostrophe_styles_are_equivalent(self):
        for variant in ("Urza’s Saga", "Urza‘s Saga", "Urza`s Saga"):
            with self.subTest(variant=variant):
                self.assertEqual(norm_name(variant), norm_name("Urza's Saga"))

    def test_split_card_separators_are_equivalent(self):
        expected = norm_name("Fire // Ice")
        for variant in ("Fire/Ice", "Fire / Ice", "Fire//Ice", "Fire /// Ice", "fire  //  ice"):
            with self.subTest(variant=variant):
                self.assertEqual(norm_name(variant), expected)

    def test_different_names_stay_different(self):
        self.assertNotEqual(norm_name("Fire // Ice"), norm_name("Fire"))
        self.assertNotEqual(norm_name("Shock"), norm_name("Shocker"))
        self.assertNotEqual(norm_name("Snow-Covered Island"), norm_name("Snow Covered Island"))


class ParseNormalCardTest(unittest.TestCase):
    def test_simple_spell(self):
        bolt = card(LIGHTNING_BOLT)
        self.assertEqual(bolt.name, "Lightning Bolt")
        self.assertEqual(bolt.layout, "normal")
        self.assertEqual(len(bolt.faces), 1)
        self.assertEqual(bolt.cmc, 1)
        self.assertEqual(bolt.colours, "R")
        self.assertEqual(bolt.deck_limit, 4)
        self.assertFalse(bolt.is_land)
        self.assertFalse(bolt.is_creature)
        self.assertFalse(bolt.mana_source)
        self.assertEqual(bolt.produces, "")
        self.assertFalse(bolt.enters_tapped)
        self.assertEqual(bolt.sets, {})

    def test_creature_fields(self):
        thalia = card(LEGENDARY)
        self.assertTrue(thalia.is_creature)
        self.assertEqual(thalia.front.pt, "2/1")
        self.assertEqual(thalia.front.card_types, ("Creature",))
        self.assertIn("Legendary", thalia.front.types)
        self.assertIn("First Strike", thalia.front.keywords)
        self.assertEqual(thalia.front.type_line, "Legendary Creature — Human Soldier")

    def test_oracle_line_breaks_are_real_newlines(self):
        thalia = card(LEGENDARY)
        self.assertEqual(thalia.oracle.split("\n"), ["First strike", "Noncreature spells cost {1} more to cast."])

    def test_text_without_a_name_is_not_a_card(self):
        self.assertIsNone(parse_card_script(""))
        self.assertIsNone(parse_card_script("\n\n"))
        self.assertIsNone(parse_card_script("ManaCost:1 R\nTypes:Instant\n"))

    def test_windows_line_endings(self):
        bolt = parse_card_script(LIGHTNING_BOLT.replace("\n", "\r\n"))
        self.assertEqual(bolt.name, "Lightning Bolt")
        self.assertEqual(bolt.cmc, 1)

    def test_specialize_variants_are_not_extra_faces(self):
        script = LEGENDARY + "AlternateMode:Specialize\n\nSPECIALIZE:WHITE\n\nName:Thalia, Radiant Guardian\nManaCost:1 W\nTypes:Legendary Creature Human\nPT:3/2\nOracle:First strike\n"
        parsed = card(script)
        self.assertEqual(parsed.name, "Thalia, Guardian of Thraben")
        self.assertEqual([f.name for f in parsed.faces], ["Thalia, Guardian of Thraben"])


class ParseMultiFaceTest(unittest.TestCase):
    def test_split_card(self):
        fire_ice = card(FIRE_ICE)
        self.assertEqual(fire_ice.name, "Fire // Ice")
        self.assertEqual(fire_ice.layout, "split")
        self.assertEqual([f.name for f in fire_ice.faces], ["Fire", "Ice"])
        self.assertEqual(fire_ice.colours, "UR", "a split card has the colours of both halves")
        self.assertEqual(fire_ice.cmc, 2)
        self.assertIn("Draw a card.", fire_ice.oracle)
        self.assertIn("Fire deals 2 damage", fire_ice.oracle)

    def test_split_card_curve_cost_is_the_cheaper_half(self):
        script = FIRE_ICE.replace("ManaCost:1 U", "ManaCost:4 U")
        self.assertEqual(card(script).cmc, 2)
        script = FIRE_ICE.replace("ManaCost:1 R", "ManaCost:5 R R")
        self.assertEqual(card(script).cmc, 2)

    def test_adventure_card_is_named_and_costed_by_its_creature(self):
        giant = card(BONECRUSHER_GIANT)
        self.assertEqual(giant.name, "Bonecrusher Giant")
        self.assertEqual(giant.layout, "adventure")
        self.assertEqual([f.name for f in giant.faces], ["Bonecrusher Giant", "Stomp"])
        self.assertEqual(giant.cmc, 3)
        self.assertTrue(giant.is_creature)
        self.assertEqual(giant.faces[1].cost.cmc, 2)

    def test_double_faced_card_uses_its_front_face(self):
        delver = card(DELVER)
        self.assertEqual(delver.name, "Delver of Secrets")
        self.assertEqual(delver.layout, "transform")
        self.assertEqual(delver.cmc, 1)
        self.assertEqual(delver.colours, "U")
        self.assertEqual(delver.front.pt, "1/1")
        self.assertEqual(delver.faces[1].name, "Insectile Aberration")
        self.assertEqual(delver.faces[1].pt, "3/2")
        self.assertIn("Flying", delver.faces[1].keywords)
        self.assertNotIn("Flying", delver.front.keywords, "a back-face keyword must not leak to the front")

    def test_modal_spell_with_land_back(self):
        smashing = card(SHATTERSKULL_SMASHING)
        self.assertEqual(smashing.name, "Shatterskull Smashing")
        self.assertEqual(smashing.layout, "modal")
        self.assertFalse(smashing.is_land, "the front face is a sorcery")
        self.assertTrue(smashing.has_land_face)
        self.assertTrue(smashing.cost.has_x)
        self.assertEqual(smashing.cmc, 2)
        self.assertEqual(smashing.colours, "R")
        self.assertFalse(smashing.mana_source, "it is not a mana rock or mana creature")
        self.assertTrue(smashing.faces[1].is_land)

    def test_modal_land_with_land_back_is_simply_a_land(self):
        pathway = card(BRANCHLOFT_PATHWAY)
        self.assertEqual(pathway.name, "Branchloft Pathway")
        self.assertEqual(pathway.layout, "modal")
        self.assertTrue(pathway.is_land)
        self.assertFalse(pathway.has_land_face, "has_land_face is for spells that can be played as a land")
        self.assertIn("G", pathway.produces)
        self.assertFalse(pathway.enters_tapped)

    def test_ordinary_cards_have_no_land_face(self):
        for script in (LIGHTNING_BOLT, FIRE_ICE, DELVER, BONECRUSHER_GIANT, PLAINS):
            self.assertFalse(card(script).has_land_face)


class ParseLandTest(unittest.TestCase):
    def test_basic_land(self):
        plains = card(PLAINS)
        self.assertTrue(plains.is_land)
        self.assertTrue(plains.is_basic_land)
        self.assertEqual(plains.produces, "W")
        self.assertFalse(plains.enters_tapped)
        self.assertFalse(plains.mana_source, "mana_source is for nonland permanents")
        self.assertEqual(plains.cmc, 0)
        self.assertEqual(plains.colours, "")

    def test_snow_basic_is_basic(self):
        island = card(SNOW_ISLAND)
        self.assertTrue(island.is_basic_land)
        self.assertEqual(island.produces, "U")

    def test_wastes_is_a_basic_that_makes_colourless(self):
        wastes = card(WASTES)
        self.assertTrue(wastes.is_basic_land)
        self.assertEqual(wastes.produces, "C")

    def test_dual_land_with_basic_types_and_optional_life_payment(self):
        vents = card(STEAM_VENTS)
        self.assertTrue(vents.is_land)
        self.assertFalse(vents.is_basic_land)
        self.assertEqual(vents.produces, "UR")
        self.assertFalse(vents.enters_tapped, "a shock land can always be untapped (for 2 life)")

    def test_always_tapped_land(self):
        temple = card(TEMPLE_OF_TRIUMPH)
        self.assertEqual(temple.produces, "WR")
        self.assertTrue(temple.enters_tapped)

    def test_always_tapped_land_with_the_older_wording(self):
        gate = card(OLD_GUILDGATE)
        self.assertEqual(gate.produces, "UR")
        self.assertTrue(gate.enters_tapped)

    def test_conditionally_tapped_land_counts_as_untapped(self):
        courtyard = card(CONCEALED_COURTYARD)
        self.assertEqual(courtyard.produces, "WB")
        self.assertFalse(courtyard.enters_tapped)

    def test_land_that_fetches_a_tapped_basic(self):
        for script in (EVOLVING_WILDS, FABLED_PASSAGE):
            wilds = card(script)
            with self.subTest(card=wilds.name):
                self.assertTrue(wilds.is_land)
                self.assertFalse(wilds.is_basic_land)
                self.assertEqual(wilds.produces, "WUBRG", "it can find whichever basic the deck plays")
        self.assertTrue(card(EVOLVING_WILDS).enters_tapped, "the fetched land arrives tapped: no mana that turn")

    def test_land_that_fetches_an_untapped_basic_is_not_a_tapped_land(self):
        vista = card(PRISMATIC_VISTA)
        self.assertEqual(vista.produces, "WUBRG")
        self.assertFalse(vista.enters_tapped)

    def test_land_whose_mana_costs_life_still_produces_every_colour(self):
        confluence = card(MANA_CONFLUENCE)
        self.assertEqual(confluence.produces, "WUBRG")
        self.assertFalse(confluence.enters_tapped)
        self.assertFalse(confluence.mana_source)


class ParseManaSourceTest(unittest.TestCase):
    def test_mana_creature(self):
        elves = card(LLANOWAR_ELVES)
        self.assertTrue(elves.mana_source)
        self.assertEqual(elves.produces, "G")
        self.assertTrue(elves.is_creature)
        self.assertFalse(elves.is_land)

    def test_any_colour_mana_creature(self):
        birds = card(BIRDS_OF_PARADISE)
        self.assertTrue(birds.mana_source)
        self.assertEqual(birds.produces, "WUBRG")

    def test_mana_rock(self):
        ring = card(SOL_RING)
        self.assertTrue(ring.mana_source)
        self.assertEqual(ring.produces, "C")

    def test_mana_ability_with_an_extra_cost_is_not_a_free_source(self):
        script = LLANOWAR_ELVES.replace("Cost$ T |", "Cost$ 1 T |")
        filtered = card(script)
        self.assertFalse(filtered.mana_source)
        self.assertEqual(filtered.produces, "G")

    def test_non_mana_cards_are_not_sources(self):
        for script in (LIGHTNING_BOLT, BONECRUSHER_GIANT, URZAS_SAGA_LIKE):
            parsed = card(script)
            self.assertFalse(parsed.mana_source, parsed.name)
            self.assertEqual(parsed.produces, "", parsed.name)


class DeckLimitTest(unittest.TestCase):
    def test_default_limit_is_four(self):
        self.assertEqual(card(LIGHTNING_BOLT).deck_limit, 4)
        self.assertEqual(card(PLAINS).deck_limit, 4, "basic lands are exempted by legality, not by deck_limit")

    def test_any_number_keyword(self):
        self.assertIsNone(card(RAT_COLONY).deck_limit)

    def test_explicit_limit_keyword(self):
        self.assertEqual(card(SEVEN_DWARVES).deck_limit, 7)
        self.assertEqual(card(NAZGUL).deck_limit, 9)

    def test_malformed_limit_keyword_keeps_the_default(self):
        script = SEVEN_DWARVES.replace("DeckLimit:7:", "DeckLimit:seven:")
        self.assertEqual(card(script).deck_limit, 4)


class JsonRoundTripTest(unittest.TestCase):
    def test_every_field_survives_the_cache_format(self):
        for script in (LIGHTNING_BOLT, FIRE_ICE, DELVER, SHATTERSKULL_SMASHING, STEAM_VENTS, RAT_COLONY,
                       SEVEN_DWARVES, LLANOWAR_ELVES, TEMPLE_OF_TRIUMPH, NAZGUL):
            original = card(script)
            original.sets = {"M21": "C", "2XM": "U"}
            with self.subTest(card=original.name):
                restored = Card.from_json(json.loads(json.dumps(original.to_json())))
                self.assertEqual(restored, original)
                self.assertEqual(restored.cmc, original.cmc)
                self.assertEqual(restored.front.types, original.front.types)


def small_db(extra=()):
    scripts = (LIGHTNING_BOLT, FIRE_ICE, BONECRUSHER_GIANT, DELVER, SHATTERSKULL_SMASHING, PLAINS, STEAM_VENTS,
               NAZGUL, URZAS_SAGA_LIKE, LLANOWAR_ELVES, RAT_COLONY) + tuple(extra)
    return CardDatabase(card(s) for s in scripts)


class CardDatabaseLookupTest(unittest.TestCase):
    def setUp(self):
        self.db = small_db()

    def test_len_and_iteration(self):
        self.assertEqual(len(self.db), 11)
        self.assertEqual(len(list(self.db)), 11)
        self.assertIn("Fire // Ice", {c.name for c in self.db})

    def test_exact_name(self):
        self.assertEqual(self.db.get("Lightning Bolt").name, "Lightning Bolt")

    def test_case_whitespace_accents_and_apostrophes(self):
        self.assertEqual(self.db.get("lightning bolt").name, "Lightning Bolt")
        self.assertEqual(self.db.get("  LIGHTNING   BOLT ").name, "Lightning Bolt")
        self.assertEqual(self.db.get("Nazgul").name, "Nazgûl")
        self.assertEqual(self.db.get("Urza’s Bauble").name, "Urza's Bauble")

    def test_unknown_name(self):
        self.assertIsNone(self.db.get("Lightning Blot"))
        self.assertIsNone(self.db.get(""))
        self.assertIsNone(self.db.get("//"))

    def test_split_card_spellings(self):
        for spelling in ("Fire // Ice", "Fire/Ice", "fire /// ice", "Fire", "Ice"):
            with self.subTest(spelling=spelling):
                found = self.db.get(spelling)
                self.assertIsNotNone(found)
                self.assertEqual(found.name, "Fire // Ice")

    def test_adventure_card_spellings(self):
        for spelling in ("Bonecrusher Giant", "Stomp", "Bonecrusher Giant // Stomp", "bonecrusher giant/stomp"):
            with self.subTest(spelling=spelling):
                found = self.db.get(spelling)
                self.assertIsNotNone(found)
                self.assertEqual(found.name, "Bonecrusher Giant")

    def test_double_faced_card_spellings(self):
        # Arena exports the full "front // back" name; the engine's name is the front face.
        for spelling in ("Delver of Secrets", "Delver of Secrets // Insectile Aberration", "Insectile Aberration"):
            with self.subTest(spelling=spelling):
                found = self.db.get(spelling)
                self.assertIsNotNone(found)
                self.assertEqual(found.name, "Delver of Secrets")

    def test_modal_card_spellings(self):
        for spelling in ("Shatterskull Smashing", "Shatterskull Smashing // Shatterskull, the Hammer Pass",
                         "Shatterskull, the Hammer Pass"):
            with self.subTest(spelling=spelling):
                self.assertEqual(self.db.get(spelling).name, "Shatterskull Smashing")

    def test_a_real_card_wins_over_another_cards_face_name(self):
        real_stomp = "Name:Stomp\nManaCost:R G\nTypes:Sorcery\nOracle:Trample matters.\n"
        for scripts in ((real_stomp, BONECRUSHER_GIANT), (BONECRUSHER_GIANT, real_stomp)):
            db = CardDatabase(card(s) for s in scripts)
            found = db.get("Stomp")
            self.assertEqual(found.name, "Stomp")
            self.assertEqual(found.layout, "normal")
            self.assertEqual(db.get("Bonecrusher Giant // Stomp").name, "Bonecrusher Giant")

    def test_lookup_returns_the_stored_object(self):
        self.assertIs(self.db.get("plains"), self.db.cards["Plains"])


class SuggestTest(unittest.TestCase):
    def setUp(self):
        self.db = small_db()

    def test_typo_suggests_the_intended_card(self):
        self.assertIn("Lightning Bolt", self.db.suggest("Lightnig Bolt"))
        self.assertIn("Llanowar Elves", self.db.suggest("Llanowar Elfs"))
        self.assertIn("Steam Vents", self.db.suggest("Steam Vent"))

    def test_suggestions_are_canonical_names_even_when_a_face_matched(self):
        self.assertEqual(self.db.suggest("Insectile Aberation"), ["Delver of Secrets"])

    def test_no_duplicates_when_several_spellings_of_one_card_match(self):
        suggestions = self.db.suggest("Fire // Icee")
        self.assertEqual(suggestions.count("Fire // Ice"), 1)
        self.assertEqual(len(suggestions), len(set(suggestions)))

    def test_nothing_close_gives_no_suggestions(self):
        self.assertEqual(self.db.suggest("Zzzzzzzz Qqqqqq"), [])

    def test_limit(self):
        many = CardDatabase(
            card(f"Name:Goblin Raider {suffix}\nManaCost:R\nTypes:Creature Goblin\nPT:1/1\nOracle:\n")
            for suffix in "ABCDEFG"
        )
        self.assertEqual(len(many.suggest("Goblin Raider X", n=3)), 3)
        self.assertEqual(len(many.suggest("Goblin Raider X", n=5)), 5)


EDITION = """\
[metadata]
Code=M21
Date=2020-07-03
Name=Core Set 2021
Type=Core
Booster=10 Common:fromSheet("M21 cards"), 3 Uncommon:fromSheet("M21 cards")
#, 1 Pack Leader+|M21|3
ScryfallCode=M21

[cards]
1 M Ugin, the Spirit Dragon @Raymond Swanland
2 C Alpine Watchdog @Forrest Imel
3 U Angelic Ascension @Volkan Baǵa
162 U Lightning Bolt
199 R Fire // Ice @Franz Vohwinkel
41 M The Great Henge @Viacom ${"flavorName": "The Banyan Tree"}
260 L Plains @Jonas De Ro

[borderless]
279 M Ugin, the Spirit Dragon @Ryan Pancoast

[promo]
392 R Pack Leader @Ilse Gort

[Lands]
6 Bloodfell Caves|M21
3 Forest|M21|2

[tokens]
1 w_4_4_angel_flying @Magali Villeneuve
15 c_a_treasure_sac @Alayna Danner

[other]
16 emblem_basri_ket @Kieran Yanner
"""


class ParseEditionTest(unittest.TestCase):
    def setUp(self):
        self.edition, self.cards = carddb._parse_edition(EDITION)
        self.by_name = {}
        for name, rarity in self.cards:
            self.by_name.setdefault(name, []).append(rarity)

    def test_metadata(self):
        self.assertEqual(self.edition.code, "M21")
        self.assertEqual(self.edition.name, "Core Set 2021")
        self.assertEqual(self.edition.date, "2020-07-03")
        self.assertEqual(self.edition.type, "Core")

    def test_cards_with_rarity_and_without_artist_credit(self):
        self.assertEqual(self.by_name["Alpine Watchdog"], ["C"])
        self.assertEqual(self.by_name["Angelic Ascension"], ["U"])
        self.assertEqual(self.by_name["Lightning Bolt"], ["U"], "a line without an @artist is still a card")
        self.assertEqual(self.by_name["Plains"], ["L"])

    def test_names_keep_commas_and_split_separators(self):
        self.assertIn("Ugin, the Spirit Dragon", self.by_name)
        self.assertEqual(self.by_name["Fire // Ice"], ["R"])

    def test_flavour_name_annotation_is_not_part_of_the_name(self):
        self.assertEqual(self.by_name["The Great Henge"], ["M"])

    def test_variant_sections_also_count_as_printings(self):
        self.assertEqual(self.by_name["Ugin, the Spirit Dragon"], ["M", "M"])
        self.assertEqual(self.by_name["Pack Leader"], ["R"], "the commented-out metadata line must not count")

    def test_tokens_emblems_and_booster_sheets_are_not_cards(self):
        names = set(self.by_name)
        for bogus in ("w_4_4_angel_flying", "c_a_treasure_sac", "emblem_basri_ket"):
            self.assertNotIn(bogus, names)
        self.assertFalse(any("Bloodfell" in n or "Forest" in n for n in names))
        self.assertEqual(len(self.cards), 9)

    def test_file_without_a_code_is_not_an_edition(self):
        edition, cards = carddb._parse_edition("[metadata]\nName=Mystery\n\n[cards]\n1 C Shock\n")
        self.assertIsNone(edition)
        self.assertEqual(cards, [])

    def test_name_defaults_to_the_code(self):
        edition, cards = carddb._parse_edition("[metadata]\nCode=XYZ\n\n[cards]\n1 C Shock @Somebody\n")
        self.assertEqual((edition.code, edition.name, edition.date, edition.type), ("XYZ", "XYZ", "", ""))
        self.assertEqual(cards, [("Shock", "C")])


class _ForgeTreeCase(unittest.TestCase):
    """A miniature Forge ``res`` tree in a temp directory, and MTGSIM_HOME pointed at another."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mtgsim-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._saved_home = os.environ.get("MTGSIM_HOME")
        os.environ["MTGSIM_HOME"] = str(self.tmp / "home")

        res = self.tmp / "forge" / "res"
        scripts = {
            "l/lightning_bolt.txt": LIGHTNING_BOLT, "f/fire_ice.txt": FIRE_ICE, "p/plains.txt": PLAINS,
            "d/delver_of_secrets_insectile_aberration.txt": DELVER, "r/rat_colony.txt": RAT_COLONY,
            "n/nazgul.txt": NAZGUL,
        }
        for relative, text in scripts.items():
            path = res / "cardsfolder" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (res / "cardsfolder" / "notes.md").write_text("not a card script", encoding="utf-8")
        editions = res / "editions"
        editions.mkdir(parents=True)
        (editions / "Alpha.txt").write_text(
            "[metadata]\nCode=LEA\nDate=1993-08-05\nName=Limited Edition Alpha\nType=Core\n\n[cards]\n"
            "161 C Lightning Bolt @Christopher Rush\n250 L Plains @Jesper Myrfors\n", encoding="utf-8")
        (editions / "Masters.txt").write_text(
            "[metadata]\nCode=XMA\nDate=2020-01-01\nName=Example Masters\nType=Reprint\n\n[cards]\n"
            "1 R Lightning Bolt @A\n2 U Lightning Bolt @B\n3 M Lightning Bolt @C\n4 U Fire // Ice @D\n"
            "5 U Delver of Secrets @E\n6 C Rat Colony @F\n7 U Nazgul @G\n8 R Card Forge Does Not Script @H\n",
            encoding="utf-8")
        (editions / "broken.txt").write_text("[cards]\n1 C Lightning Bolt\n", encoding="utf-8")
        jar = self.tmp / "forge" / "forge-gui-desktop-9.9.9-jar-with-dependencies.jar"
        jar.write_bytes(b"not really a jar")
        self.install = ForgeInstall(root=self.tmp / "forge", jar=jar, res=res, workdir=self.tmp / "forge")

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("MTGSIM_HOME", None)
        else:
            os.environ["MTGSIM_HOME"] = self._saved_home


class BuildDatabaseTest(_ForgeTreeCase):
    def test_cards_and_editions_are_read(self):
        db = carddb.build_database(self.install)
        self.assertEqual({c.name for c in db},
                         {"Lightning Bolt", "Fire // Ice", "Plains", "Delver of Secrets", "Rat Colony", "Nazgûl"})
        self.assertEqual(set(db.editions), {"LEA", "XMA"})
        self.assertEqual(db.editions["LEA"].name, "Limited Edition Alpha")

    def test_printings_are_attached_to_cards(self):
        db = carddb.build_database(self.install)
        self.assertEqual(db.get("Plains").sets, {"LEA": "L"})
        self.assertEqual(db.get("Fire // Ice").sets, {"XMA": "U"})
        self.assertEqual(db.get("Delver of Secrets").sets, {"XMA": "U"})
        self.assertEqual(db.get("Rat Colony").sets, {"XMA": "C"})

    def test_lowest_rarity_within_a_set_is_kept(self):
        bolt = carddb.build_database(self.install).get("Lightning Bolt")
        self.assertEqual(bolt.sets, {"LEA": "C", "XMA": "U"})

    def test_edition_spelling_without_accents_still_finds_the_card(self):
        self.assertEqual(carddb.build_database(self.install).get("Nazgûl").sets, {"XMA": "U"})

    def test_lookups_still_work_on_the_finished_database(self):
        db = carddb.build_database(self.install)
        self.assertEqual(db.get("fire/ice").name, "Fire // Ice")
        self.assertEqual(db.get("Insectile Aberration").name, "Delver of Secrets")
        self.assertIsNone(db.get("Card Forge Does Not Script"))


class LoadDatabaseCacheTest(_ForgeTreeCase):
    def cache_files(self):
        return sorted((self.tmp / "home" / "cache").glob("carddb-*.json.gz"))

    def test_first_load_builds_and_writes_the_cache_under_mtgsim_home(self):
        self.assertEqual(self.cache_files(), [])
        db = carddb.load_database(self.install)
        self.assertEqual(len(db), 6)
        self.assertEqual(len(self.cache_files()), 1)

    def test_second_load_comes_from_the_cache_and_is_equivalent(self):
        built = carddb.load_database(self.install)
        with mock.patch.object(carddb, "build_database", side_effect=AssertionError("cache was not used")):
            cached = carddb.load_database(self.install)
        self.assertEqual(cached.cards, built.cards)
        self.assertEqual(cached.editions, built.editions)
        self.assertEqual(cached.get("ice").name, "Fire // Ice")
        self.assertEqual(cached.get("Lightning Bolt").sets, {"LEA": "C", "XMA": "U"})
        self.assertIsNone(cached.get("Rat Colony").deck_limit)

    def test_refresh_rebuilds(self):
        carddb.load_database(self.install)
        with mock.patch.object(carddb, "build_database", wraps=carddb.build_database) as build:
            carddb.load_database(self.install, refresh=True)
        self.assertEqual(build.call_count, 1)

    def test_damaged_cache_is_rebuilt_not_fatal(self):
        carddb.load_database(self.install)
        (cache,) = self.cache_files()
        cache.write_bytes(b"this is not gzip")
        db = carddb.load_database(self.install)
        self.assertEqual(len(db), 6)
        with mock.patch.object(carddb, "build_database", side_effect=AssertionError("cache was not rewritten")):
            self.assertEqual(len(carddb.load_database(self.install)), 6)

    def test_a_changed_engine_jar_invalidates_the_cache(self):
        carddb.load_database(self.install)
        self.install.jar.write_bytes(b"a newer, longer build of the jar")
        with mock.patch.object(carddb, "build_database", wraps=carddb.build_database) as build:
            carddb.load_database(self.install)
        self.assertEqual(build.call_count, 1)
        self.assertEqual(len(self.cache_files()), 1, "the stale cache file should be removed")

    def test_empty_cardsfolder_is_an_error_and_writes_no_cache(self):
        shutil.rmtree(self.install.cardsfolder)
        self.install.cardsfolder.mkdir()
        with self.assertRaises(RuntimeError):
            carddb.load_database(self.install)
        self.assertEqual(self.cache_files(), [])


class HandBuiltCardTest(unittest.TestCase):
    """Card and Face are plain dataclasses, so other tests can build them without a script."""

    def test_hand_built_card(self):
        bear = Card(name="Grizzly Bears",
                    faces=[Face(name="Grizzly Bears", mana_cost="1 G", types=("Creature", "Bear"), pt="2/2")])
        self.assertEqual(bear.cmc, 2)
        self.assertEqual(bear.colours, "G")
        self.assertTrue(bear.is_creature)
        self.assertFalse(bear.is_land)
        self.assertEqual(bear.deck_limit, 4)
        self.assertEqual(CardDatabase([bear]).get("grizzly bears"), bear)


if __name__ == "__main__":
    unittest.main()
