import json

MD = "mtgdecks.net archetype page, Standard 'Reality Fracture' section; search metadata put page ages at 0-10 days before 2026-11-13; the page's own time window and platform filter (MTGO / Arena events, Bo1/Bo3) are not stated in the snippet"
MD_CONV = ("Direction: mtgdecks lists '<opponent> X% WR · N matches' on an archetype's page as the PAGE archetype's win rate against that opponent. "
           "This convention was checked on pairs seen from both pages (Landfall 46%/268 vs Spellementals <-> Spellementals 54%/268 vs Landfall; "
           "Uldaros 66%/109 vs Spellementals <-> Spellementals 33.9%/109 vs Uldaros; Uldaros 73%/114 vs Azorius Control <-> Azorius Control 27.2%/114 vs Uldaros).")

def m(a, b, wr, n, url, title, date, snippet, ambiguous=False, notes=""):
    return {"a": a, "b": b, "a_win_rate": wr, "matches": n, "source_url": url, "source_title": title,
            "data_date": date, "snippet": snippet, "ambiguous": ambiguous, "notes": notes}

U_LF = "https://mtgdecks.net/Standard/mono-green-landfall"
T_LF = "MTG Standard Reality Fracture Mono Green Landfall - 4797 top decks • MTG DECKS"
U_LF1 = "https://mtgdecks.net/Standard/mono-green-landfall/min_ranking:1"
T_LF1 = "MTG Standard Reality Fracture Mono Green Landfall - 4781 top decks • MTG DECKS"
U_IS = "https://mtgdecks.net/Standard/izzet-spellementals"
T_IS = "MTG Standard Reality Fracture Izzet Spellementals - 3147 top decks • MTG DECKS"
U_DU = "https://mtgdecks.net/Standard/dimir-uldaros"
T_DU = "MTG Standard Reality Fracture Dimir Uldaros - 514 top decks • MTG DECKS"
U_DM = "https://mtgdecks.net/Standard/dimir-midrange"
T_DM = "MTG Standard The Hobbit Dimir Midrange - 6047 top decks • MTG DECKS (title as indexed; 'The Hobbit' = previous Standard season label)"
U_DMS = "https://mtgdecks.net/Standard/dimir-midrange-swing-33109"
T_DMS = "Matchup Swing [Standard]: Dimir Midrange • MTG DECKS"
U_AC = "https://mtgdecks.net/Standard/azorius-control"
T_AC = "MTG Standard Reality Fracture Azorius Control - 2419 top decks • MTG DECKS (matchup figures attributed by the search tool to an Azorius Control matchup page; exact URL among azorius-control, azorius-control/BO1, azorius-control-swing-31955 not identified)"
U_OL = "https://mtgdecks.net/Standard/orzhov-lifegain-swing-32030/vs_archetype_id:32533"
T_OL = "Matchup Swing [Standard]: Orzhov Lifegain vs Azorius Blink • MTG DECKS (figures described by the search tool as 'the Orzhov Lifegain matchup page'; could also be https://mtgdecks.net/Standard/orzhov-lifegain)"
U_BASE_LF = "https://www.basemtg.com/blog/mono-green-landfall-standard-deck-guide"
T_BASE_LF = "Mono-Green Landfall Standard Deck Guide for October 2026"
U_BASE_MOMO = "https://www.basemtg.com/blog/azorius-momo-standard-deck-guide"
T_BASE_MOMO = "Azorius Momo Standard Deck Guide: Decklist and Matchups"
U_MM = "https://magicmeta.net/formats/standard/matchups"
U_MM_JS = "https://magicmeta.net/formats/standard/archetypes/jund-sacrifice/how-to-beat"
U_OM = "https://openmagic.gg/meta"
U_KAR = "https://magic.gg/news/metagame-mentor-mapping-the-standard-frontier-before-magic-world-championship-32"
T_KAR = "Metagame Mentor: Mapping the Standard Frontier Before Magic World Championship 32"
JB = "Opponent named 'Jund Biotech' by mtgdecks. mtgdecks' Jund Biotech page says it is 'also known as ... jund sacrifice or Jund', but mtgdecks also lists a separate 'Jund Sacrifice' entry on some pages, so this may be all or only part of Magic.gg's 'Jund Sacrifice'."

matchups = [
 # ---------- mtgdecks.net, cross-checked from both sides ----------
 m("Mono-Green Landfall", "Izzet Spellementals", 46, 268, U_LF, T_LF, MD,
   "One lists Dimir Midrange at 51% over 351 matches and Izzet Spellementals at 46% over 268 matches. The newer snapshot shows Dimir Midrange at 52% over 355 matches and Izzet Spellementals at 46% over 274 matches.",
   False, MD_CONV + " Reverse side seen: Izzet Spellementals page lists Mono Green Landfall at 54% over 268 matches. Newer snapshot: 46% over 274 matches."),
 m("Izzet Spellementals", "Mono-Green Landfall", 54, 268, U_IS, T_IS, MD,
   "Izzet Spellementals: Mono Green Landfall is listed at 54% over 268 matches, and Boros Dragons at 63% over 109.",
   False, MD_CONV + " Same pairing as the row above, seen from the other page; do not count twice."),
 m("Mono-Green Landfall", "Dimir Midrange", 51, 351, U_LF, T_LF, MD,
   "mtgdecks.net lists Mono Green Landfall's overall win rate against Dimir Midrange at 51% over 351 matches ... Its Dimir Midrange page shows the same matchup at 49% over 353 matches.",
   False, MD_CONV + " Newer snapshot of the Landfall page: 52% over 355 matches. Reverse: Dimir Midrange page 'Mono Green Landfall 49% WR · 353 matches'."),
 m("Dimir Midrange", "Mono-Green Landfall", 49, 353, U_DM, T_DM, MD,
   "Mono Green Landfall: The matchup page lists about 49% win rate across 353 matches, roughly even. Mono Green Landfall 49% WR · 353 matches",
   False, MD_CONV + " Same pairing as the row above from the other page; do not count twice."),
 m("Dimir Uldaros", "Izzet Spellementals", 66, 109, U_DU, T_DU, MD,
   "Dimir Uldaros: Azorius Control appears at 73% over 114 matches, and Izzet Spellementals at 66% over 109.",
   False, MD_CONV + " Reverse: Izzet Spellementals page 'Dimir Uldaros 33.9% WR · 109 matches'."),
 m("Izzet Spellementals", "Dimir Uldaros", 33.9, 109, U_IS, T_IS, MD,
   "Dimir Uldaros: About 34% over 109 matches, which makes it one of the worse matchups for Izzet Spellementals. (Dimir Uldaros 33.9% WR · 109 matches)",
   False, "Same pairing as the row above from the other page; do not count twice."),
 m("Dimir Uldaros", "Azorius Control", 73, 114, U_DU, T_DU, MD,
   "Dimir Uldaros: Azorius Control appears at 73% over 114 matches, and Izzet Spellementals at 66% over 109.",
   False, MD_CONV + " Reverse: Azorius Control page 'Dimir Uldaros at 27.2% over 114 matches'. Karsten (magic.gg, 2026-11-05) also writes that Azorius Control 'has struggled against Dimir Midrange and Dimir Uldaros over the past few weeks'."),
 m("Azorius Control", "Dimir Uldaros", 27.2, 114, U_AC, T_AC, MD,
   "A matchup page for Azorius Control lists Mono Green Landfall at 48% over 173 matches, Dimir Midrange at 25.9% over 143 matches, Izzet Spellementals at 56.3% over 112 matches, Jund Biotech at 43.9% over 139 matches, and Dimir Uldaros at 27.2% over 114 matches.",
   False, "Same pairing as the row above from the other page; do not count twice."),
 m("Dimir Midrange", "Izzet Spellementals", 52.8, 235, U_DMS, T_DMS, MD,
   "Izzet Spellementals: On the main Dimir Midrange page, Dimir wins 52.8% WR · 235 matches against it.",
   False, MD_CONV + " Reverse: Izzet Spellementals page 'Dimir Midrange 46.7% WR · 227 matches' (and an outlier snapshot '68.2% WR · 22 matches')."),
 m("Izzet Spellementals", "Dimir Midrange", 46.7, 227, U_IS, T_IS, MD,
   "Dimir Midrange: One snapshot puts Izzet Spellementals at about 47% against it over 227 matches, while another shows about 68% over only 22 matches. ... (Dimir Midrange 46.7% WR · 227 matches; Dimir Midrange 68.2% WR · 22 matches)",
   False, "Same pairing as the row above from the other page; do not count twice. The 68.2%/22 figure is an unexplained second snapshot, not recorded as its own row."),
 m("Izzet Spellementals", "Azorius Control", 43.6, 117, U_IS, T_IS, MD,
   "Azorius Control: About 44% over 117 matches, a slight underdog. (Azorius Control 43.6% WR · 117 matches)",
   False, MD_CONV + " Reverse: Azorius Control page 'Izzet Spellementals at 56.3% over 112 matches'."),
 m("Azorius Control", "Izzet Spellementals", 56.3, 112, U_AC, T_AC, MD,
   "A matchup page for Azorius Control lists ... Izzet Spellementals at 56.3% over 112 matches ...",
   False, "Same pairing as the row above from the other page; do not count twice."),
 m("Orzhov Lifegain", "Dimir Midrange", 55.9, 136, U_OL, T_OL, MD,
   "Dimir Midrange: Orzhov Lifegain wins 55.9% across 136 matches. Dimir Midrange 55.9% WR · 136 matches",
   False, MD_CONV + " Reverse: Dimir Midrange page 'Orzhov Lifegain 45.1% WR · 215 matches' (different sample size, so a different snapshot or filter)."),
 m("Dimir Midrange", "Orzhov Lifegain", 45.1, 215, U_DM, T_DM, MD,
   "Orzhov Lifegain: This is the weakest of the three. The page shows roughly 45% across 215 matches, so Dimir Midrange is slightly unfavored. Orzhov Lifegain 45.1% WR · 215 matches",
   False, "Same pairing as the row above from the other page, but different sample (215 vs 136); do not count twice."),
 m("Orzhov Lifegain", "Mono-Green Landfall", 45.7, 162, U_OL, T_OL, MD,
   "Mono Green Landfall: Orzhov Lifegain wins 45.7% of its 162 matches against this deck, so it is slightly unfavorable. Mono Green Landfall 45.7% WR · 162 matches",
   False, MD_CONV + " Reverse seen with a much smaller sample: Landfall page 'Orzhov Lifegain 61% WR · 41 matches'."),
 m("Mono-Green Landfall", "Orzhov Lifegain", 61, 41, U_LF, T_LF + " (or its Matchup Swing page; the search tool did not say which)", MD,
   "Orzhov Lifegain: 61% over 41 matches, a favorable matchup. Orzhov Lifegain 61% WR · 41 matches",
   False, "Same pairing as the row above, smaller sample (41 vs 162) and stronger edge; the same result block gave the deck's overall record as 50% over 224 matches, so this is a different, smaller window than the 351-match Dimir Midrange figure."),
 # ---------- mtgdecks.net, one side only ----------
 m("Mono-Green Landfall", "Dimir Uldaros", 61, 257, U_LF, T_LF, MD,
   "Mono Green Landfall: Dimir Uldaros is listed at 61% over 257 matches, and Azorius Blink at 61% over 101.",
   False, MD_CONV + " Not cross-checked from the Uldaros page."),
 m("Mono-Green Landfall", "Jund Sacrifice", 48.1, 79, U_LF, T_LF + " (or its Matchup Swing page)", MD,
   "Jund Sacrifice: 48.1% over 79 matches, so roughly even. Jund Sacrifice 48.1% WR · 79 matches",
   False, "Opponent named 'Jund Sacrifice' here; mtgdecks separately tracks 'Jund Biotech' (see the 44%/382 row). The same result block gave the deck's overall record as 50% over 224 matches, i.e. a smaller window than other Landfall snapshots."),
 m("Mono-Green Landfall", "Boros Dragons", 47.6, 42, U_LF, T_LF + " (or its Matchup Swing page)", MD,
   "Boros Dragons: 47.6% over 42 matches, slightly unfavorable. Boros Dragons 47.6% WR · 42 matches", False, ""),
 m("Mono-Green Landfall", "Azorius Control", 79.2, 24, U_LF, T_LF + " (or its Matchup Swing page)", MD,
   "Azorius Control: 79.2% over 24 matches, the strongest of the three. Azorius Control 79.2% WR · 24 matches",
   True, "Conflicts with the Azorius Control page, which lists Mono Green Landfall at 48% over 173 matches (i.e. Azorius Control 48% vs Landfall, implying Landfall ~52%). Small sample; likely a different window. Treat as unreliable."),
 m("Azorius Control", "Mono-Green Landfall", 48, 173, U_AC, T_AC, MD,
   "A matchup page for Azorius Control lists Mono Green Landfall at 48% over 173 matches ...",
   False, MD_CONV + " Conflicts with the 79.2%/24 row from the Landfall page."),
 m("Azorius Control", "Dimir Midrange", 25.9, 143, U_AC, T_AC, MD,
   "A matchup page for Azorius Control lists ... Dimir Midrange at 25.9% over 143 matches ...",
   False, MD_CONV + " Agrees in direction with Karsten's statement that Azorius Control 'has struggled against Dimir Midrange and Dimir Uldaros'."),
 m("Azorius Control", "Jund Biotech (=Jund Sacrifice?)", 43.9, 139, U_AC, T_AC, MD,
   "A matchup page for Azorius Control lists ... Jund Biotech at 43.9% over 139 matches ...", False, JB),
 m("Izzet Spellementals", "Jund Biotech (=Jund Sacrifice?)", 38.7, 230, U_IS, T_IS, MD,
   "Jund: The closest listing is Jund Biotech at about 39% over 230 matches. (Jund Biotech 38.7% WR · 230 matches) I found no \"Jund Sacrifice\" archetype in these results.",
   False, JB + " Another snapshot of the same page (tooltip format) gave 'Archetype: Jund Biotech; Winrate: 39%; Available Matches: 192 matches'."),
 m("Izzet Spellementals", "Boros Dragons", 63, 109, U_IS, T_IS, MD,
   "Izzet Spellementals: Mono Green Landfall is listed at 54% over 268 matches, and Boros Dragons at 63% over 109.", False, MD_CONV),
 m("Dimir Midrange", "Jund Biotech (=Jund Sacrifice?)", 51.6, 310, U_DM, T_DM, MD,
   "The closest entry is Jund Biotech at about 51.6% across 310 matches. Jund Biotech 51.6% WR · 310 matches.",
   False, JB + " Page title as indexed carried the previous-season label 'The Hobbit', so the snapshot date is uncertain."),
 m("Dimir Midrange", "Jund Sacrifice", 61.7, 81, "https://mtgdecks.net/Standard/dimir-midrange-swing-33109/vs_archetype_id:31955",
   "Matchup Swing [Standard]: Dimir Midrange vs Azorius Control • MTG DECKS", "unknown; mtgdecks swing page",
   "The one Matchup Swing result is for a different opponent. It lists Dimir Midrange vs. Jund Sacrifice at 61.7% WR · 81 matches.",
   True, "Found on the 'Dimir Midrange vs Azorius Control' swing page, so the figure's context is unclear. The same search also reported 'Jund Sacrifice — 63% (46 matches)' on an older (about 52 days old, 'The Hobbit'-labelled) Dimir Midrange page; that older value is not recorded as a row. Conflicts with magicmeta's 4-7 record and with the 51.6%/310 Jund Biotech row."),
 m("Dimir Midrange", "Dimir Uldaros", 54.4, 204, U_DMS, T_DMS, MD,
   "vs. Dimir Midrange: The Dimir Midrange matchup page lists Dimir Uldaros at 54.4% over 204 matches, from Dimir Midrange's perspective.", False, MD_CONV),
 m("Dimir Midrange", "Boros Dragons", 40.2, 117, U_DMS, T_DMS, MD,
   "Boros Dragons: Dimir's overall record is 40.2% WR · 117 matches.", False, MD_CONV),
 m("Orzhov Lifegain", "Izzet Spellementals", 58.6, 87, U_OL, T_OL, MD,
   "Izzet Spellementals: Orzhov Lifegain wins 58.6% across 87 matches, the best of the four for it. Izzet Spellementals 58.6% WR · 87 matches", False, MD_CONV),
 m("Orzhov Lifegain", "Jund Sacrifice", 51.7, 87, U_OL, T_OL, MD,
   "Jund: The page lists Jund Sacrifice, not Jund Biotech. Orzhov Lifegain wins 51.7% of 87 matches against it. Jund Sacrifice 51.7% WR · 87 matches", False, MD_CONV),
 m("Orzhov Lifegain", "Azorius Control", 41, 78, "https://mtgdecks.net/Standard/orzhov-lifegain", "MTG Standard Reality Fracture Orzhov Lifegain - 1101 top decks • MTG DECKS", MD,
   "MTG Decks' Orzhov Lifegain page lists Azorius Control at 41% over 78 matches, and Boros Dragons at 54.4% over 57 matches on its matchup page.", False, MD_CONV),
 m("Orzhov Lifegain", "Boros Dragons", 54.4, 57, "https://mtgdecks.net/Standard/orzhov-lifegain", "MTG Standard Reality Fracture Orzhov Lifegain - 1101 top decks • MTG DECKS", MD,
   "MTG Decks' Orzhov Lifegain page lists Azorius Control at 41% over 78 matches, and Boros Dragons at 54.4% over 57 matches on its matchup page.", False, MD_CONV),
 # ---------- mtgdecks tooltip format: direction not cross-checked ----------
 m("Mono-Green Landfall", "Jund Biotech (=Jund Sacrifice?)", 44, 382, U_LF1, T_LF1, MD,
   "Mono Green Landfall: 44% over 382 matches (Archetype: Jund Biotech; Winrate: 44%; Available Matches: 382 matches)",
   True, JB + " The search tool presented this as Jund Biotech's win rate against Landfall; by the page convention it is more likely Landfall's win rate against Jund Biotech (the same tool format on the Spellementals page, 39%/192, matches Spellementals' own 38.7%/230 vs Jund Biotech). Direction therefore not certain."),
 m("Dimir Uldaros", "Jund Biotech (=Jund Sacrifice?)", 43, 159, U_DU, T_DU, MD,
   "Dimir Uldaros: 43% over 159 matches (Archetype: Jund Biotech; Winrate: 43%; Available Matches: 159 matches)",
   True, JB + " Same direction caveat as the 44%/382 row: probably Uldaros' win rate vs Jund Biotech, but the search tool read it the other way."),
 m("Boros Dragons", "Jund Biotech (=Jund Sacrifice?)", 62, 123, "https://mtgdecks.net/Standard/boros-dragons", "MTG Standard Reality Fracture Boros Dragons - 953 top decks • MTG DECKS", MD,
   "Boros Dragons: 62% over 123 matches (Archetype: Jund Biotech; Winrate: 62%; Available Matches: 123 matches)",
   True, JB + " Same direction caveat: by page convention Boros Dragons 62% vs Jund Biotech, but the search tool read it as Jund Biotech 62% vs Boros Dragons. The direction matters a lot here."),
 m("Dimir Midrange", "Izzet Spellementals", 45.4, 130, "https://mtgdecks.net/Standard/dimir-midrange-swing-33109/vs_archetype_id:31955",
   "Matchup Swing [Standard]: Dimir Midrange vs Azorius Control • MTG DECKS", "unknown",
   "On the Azorius Control variant page, the figure drops to 45.4% WR · 130 matches.",
   True, "From the 'Dimir Midrange vs Azorius Control' swing page; unclear what subset this is. The main-page value is 52.8%/235. Do not use."),
 m("Dimir Midrange", "Boros Dragons", 31.6, 38, "https://mtgdecks.net/Standard/dimir-midrange-swing-33109/vs_archetype_id:31955",
   "Matchup Swing [Standard]: Dimir Midrange vs Azorius Control • MTG DECKS", "unknown",
   "Against Azorius Control it is 31.6% WR · 38 matches.",
   True, "The sentence is garbled ('Boros Dragons ... Against Azorius Control it is 31.6%'), so it is unclear which pairing this is. Do not use."),
 # ---------- mtgpile records via BaseMTG ----------
 m("Mono-Green Landfall", "Jund Sacrifice", 9/26*100, 26, U_BASE_LF, T_BASE_LF, "2026-09-29 to 2026-10-21 (mtgpile win matrix, MTGO)",
   "It reports a real-match record against Jund Sacrifice of 9-17 from September 29 through October 21, so Mono-Green has won 9 and lost 17 against that deck. The snippet attributes that record to mtgpile's win matrix.",
   False, "a_win_rate computed from the stated 9-17 record (9/26). The same guide reports Forge simulations (500 games per matchup, run 2026-10-13) separately; another search result said 'in Forge, Mono-Green wins 58 of 100 against Jund'."),
 m("Mono-Green Landfall", "Dimir Midrange", 18/44*100, 44, U_BASE_LF, T_BASE_LF, "2026-09-29 to 2026-10-21 (mtgpile win matrix, MTGO)",
   "BaseMTG's October 2026 guide reports real match records of 18-26 against Dimir Midrange and 11-22 against Izzet Spellementals, which would make both matchups unfavorable for Landfall.",
   True, "The 18-26 figure appeared in three independent search summaries, but a search targeted at the guide said the snippet it saw did not contain it and named the blue-black opponent 'Dimir Reanimator'. Not verified. a_win_rate computed from 18-26."),
 m("Mono-Green Landfall", "Izzet Spellementals", 11/33*100, 33, U_BASE_LF, T_BASE_LF, "2026-09-29 to 2026-10-21 (mtgpile win matrix, MTGO)",
   "BaseMTG's October 2026 guide reports real match records of 18-26 against Dimir Midrange and 11-22 against Izzet Spellementals ... [another search:] real-match records of 11-22 for Izzet players in that matchup.",
   True, "Direction conflicts between two search results: one reads 11-22 as Landfall's record, the other as the Izzet players' record. a_win_rate (33.3) assumes Landfall's perspective; if it is Izzet's, Landfall would be 66.7. Do not use without checking."),
 m("Azorius Momo", "Dimir Midrange", 12/20*100, 20, U_BASE_MOMO, T_BASE_MOMO, "Reality Fracture release to 2026-10-21 snapshot (mtgpile)",
   "Real matches (basemtg, citing mtgpile, snapshot Oct 21): The deck is 65-65 overall. Its best common matchup is Dimir Midrange at 12-8",
   False, "a_win_rate computed from the stated 12-8 record."),
 m("Azorius Momo", "Azorius Control", 3/9*100, 9, U_BASE_MOMO, T_BASE_MOMO, "Reality Fracture release to 2026-10-21 snapshot (mtgpile)",
   "Real records since Reality Fracture show 3-6 against Azorius Control, 2-4 against Jeskai Artifacts and 3-6 against 4c Control.",
   False, "a_win_rate computed from 3-6."),
 m("Azorius Momo", "Jeskai Artifacts (=Azorius Artifacts?)", 2/6*100, 6, U_BASE_MOMO, T_BASE_MOMO, "Reality Fracture release to 2026-10-21 snapshot (mtgpile)",
   "Real records since Reality Fracture show 3-6 against Azorius Control, 2-4 against Jeskai Artifacts and 3-6 against 4c Control.",
   True, "Opponent named 'Jeskai Artifacts'; whether that is Magic.gg's 'Azorius Artifacts' is unknown. a_win_rate computed from 2-4."),
 m("Azorius Momo", "Orzhov Lifegain", 5/13*100, 13, U_BASE_MOMO, T_BASE_MOMO, "Reality Fracture release to 2026-10-21 snapshot (mtgpile)",
   "Basemtg also lists Jund Sacrifice at 5-1 and Orzhov Life Gain at 5-8.", False, "a_win_rate computed from 5-8."),
 m("Azorius Momo", "Jund Sacrifice", 5/6*100, 6, U_BASE_MOMO, T_BASE_MOMO, "Reality Fracture release to 2026-10-21 snapshot (mtgpile)",
   "Basemtg also lists Jund Sacrifice at 5-1 and Orzhov Life Gain at 5-8.",
   True, "Another search result attributed a 5-1 record to Boros Dragons instead ('Momo went 5-1 against Boros Dragons in real matches, and the Forge simulation gave it 35 wins in 100 games'). Which opponent the 5-1 belongs to is unresolved."),
 m("Azorius Momo", "Boros Dragons", 5/6*100, 6, U_BASE_MOMO, T_BASE_MOMO, "Reality Fracture release to 2026-10-21 snapshot (mtgpile)",
   "Momo went 5-1 against Boros Dragons in real matches, and the Forge simulation gave it 35 wins in 100 games. The article says the two methods disagree hard on Izzet and Boros.",
   True, "Conflicts with the row above (same 5-1 attributed to Jund Sacrifice). Only one of the two can be right."),
 # ---------- magicmeta.net ----------
 m("Izzet Spellementals", "Mono-Green Landfall", 72, 18, U_MM, "Standard Matchup Matrix (magicmeta.net)", "unknown",
   "The magicmeta.net matrix lists Izzet Spellementals at 72% against Mono-Green Landfall, based on 18 matches (13-5), with the reverse row showing Landfall at 28%.",
   False, "Small sample, conflicts with the 268-match mtgdecks figure (Spellementals 54%). Date window not stated."),
 m("Dimir Midrange", "Jund Sacrifice", 36.4, 11, U_MM_JS, "How to beat Jund Sacrifice in Standard (magicmeta.net)", "unknown",
   "Vs. Dimir Midrange: Dimir has a 4-7 record over 11 matches against Jund Sacrifice, a 36.4% win rate for Dimir. ... 95% range 15%–65%.",
   False, "Tiny sample; date window not stated."),
 m("Lifegain (=Orzhov Lifegain?)", "Jund Sacrifice", 40.0, 5, U_MM_JS, "How to beat Jund Sacrifice in Standard (magicmeta.net)", "unknown",
   "Vs. Lifegain: Lifegain has a 2-3 record over 5 matches against Jund Sacrifice, a 40.0% win rate for Lifegain. That is a low-sample result with a very wide 95% range of 12%–77%.",
   True, "Opponent named only 'Lifegain' (colours unstated). 5 matches."),
 # ---------- openmagic.gg ----------
 m("Mono-Green Landfall", "Dimir (unspecified)", 48, None, U_OM, "Current MTG Standard Meta — Meta Decks & Tier List (openmagic.gg)", "unknown",
   "Its matchup matrix shows Mono-Green at 48% against Dimir, 50% against Jund, 53% against Orzhov, and 36% against Mono-White.",
   True, "Which Dimir deck is unspecified; no sample size; the page says 'dashed cells are assumed 50% because no data is available', and one search result called it 'OpenMagic's Forge-based matrix', so it may be simulated rather than real."),
 m("Mono-Green Landfall", "Jund (unspecified)", 50, None, U_OM, "Current MTG Standard Meta — Meta Decks & Tier List (openmagic.gg)", "unknown",
   "Its matchup matrix shows Mono-Green at 48% against Dimir, 50% against Jund, 53% against Orzhov, and 36% against Mono-White.",
   True, "Same caveats as above; 50% may be an 'assumed 50%' cell."),
 m("Mono-Green Landfall", "Orzhov (unspecified)", 53, None, U_OM, "Current MTG Standard Meta — Meta Decks & Tier List (openmagic.gg)", "unknown",
   "Its matchup matrix shows Mono-Green at 48% against Dimir, 50% against Jund, 53% against Orzhov, and 36% against Mono-White.",
   True, "Same caveats as above."),
 m("Orzhov Lifegain", "Boros Dragons", 52, None, U_OM, "Current MTG Standard Meta — Meta Decks & Tier List (openmagic.gg)", "unknown",
   "OpenMagic's matchup matrix lists Orzhov Lifegain vs. Boros Dragons (Boros column) at 52%, and Azorius Control vs. Orzhov at 48%, with Boros Dragons vs. Azorius at 55%.",
   True, "Same caveats as above; also unclear whether 52% is Orzhov's or Boros' side."),
 m("Azorius Control", "Orzhov (unspecified)", 48, None, U_OM, "Current MTG Standard Meta — Meta Decks & Tier List (openmagic.gg)", "unknown",
   "OpenMagic's matchup matrix lists ... Azorius Control vs. Orzhov at 48% ...", True, "Same caveats as above."),
 m("Boros Dragons", "Azorius (unspecified)", 55, None, U_OM, "Current MTG Standard Meta — Meta Decks & Tier List (openmagic.gg)", "unknown",
   "OpenMagic's matchup matrix lists ... Boros Dragons vs. Azorius at 55%.", True, "Same caveats as above."),
 # ---------- Karsten, qualitative only ----------
 m("Izzet Spellementals", "Mono-Green Landfall", None, None, "https://magic.gg/news/metagame-mentor-hottest-standard-decks-winning-september-2026-rcqs",
   "Metagame Mentor: Hottest Standard Decks Winning September 2026 RCQs", "September 2026",
   "Traditionally, Izzet Spellementals has been favored against Mono-Green Landfall.",
   False, "Qualitative only, no number. The 2026-11-05 article adds that Sunderflock is 'still effective against Mono-Green Landfall—the most-played deck, though the strategy struggles against the rest of the field'."),
 m("Azorius Control", "Dimir Midrange / Dimir Uldaros", None, None, U_KAR, T_KAR, "weeks before 2026-11-05",
   "The article also says Azorius Control has struggled against Dimir Midrange and Dimir Uldaros over the past few weeks, and its win rate has been underwhelming so far.",
   False, "Qualitative only, no number. Agrees with mtgdecks (Azorius Control 25.9% vs Dimir Midrange, 27.2% vs Dimir Uldaros)."),
]

for x in matchups:
    if isinstance(x["a_win_rate"], float):
        x["a_win_rate"] = round(x["a_win_rate"], 1)

K = "Combined Arena Championship 13 + Magic Spotlight: Fracture (two events) data, 1,810 Standard decklists, mirrors/byes/draws excluded; published 2026-11-05"
deck_win_rates = [
 {"deck": "Mono-Green Landfall", "win_rate": 53.4, "matches": None, "source_url": U_KAR, "snippet": "Mono-Green Landfall | 12.7% | 53.4%", "data_date": K},
 {"deck": "Dimir Midrange", "win_rate": 54.5, "matches": None, "source_url": U_KAR, "snippet": "Dimir Midrange | 8.9% | 54.5%", "data_date": K},
 {"deck": "Dimir Uldaros", "win_rate": 49.2, "matches": None, "source_url": U_KAR, "snippet": "A Metagame Mentor piece puts Uldaros at 8.3% of the field with a 49.2% match win rate.", "data_date": K},
 {"deck": "Izzet Spellementals", "win_rate": 44.3, "matches": None, "source_url": U_KAR, "snippet": "Izzet Spellementals | 7.5% ↓↓ | 44.3% |", "data_date": K},
 {"deck": "Jund Sacrifice", "win_rate": 57.6, "matches": None, "source_url": U_KAR, "snippet": "Jund Sacrifice | 7.4% | 57.6% ✓✓ | ... In terms of performance, Jund Sacrifice excelled with a 57.6% match win rate.", "data_date": K},
 {"deck": "Orzhov Lifegain", "win_rate": 53.6, "matches": None, "source_url": U_KAR, "snippet": "Its overall match win rates for the three archetypes are Orzhov Life Gain at 53.6%, Azorius Control at 46.6%, and Boros Dragons at 45.0%", "data_date": K},
 {"deck": "Azorius Control", "win_rate": 46.6, "matches": None, "source_url": U_KAR, "snippet": "Orzhov Life Gain at 53.6%, Azorius Control at 46.6%, and Boros Dragons at 45.0%", "data_date": K},
 {"deck": "Boros Dragons", "win_rate": 45.0, "matches": None, "source_url": U_KAR, "snippet": "Orzhov Life Gain at 53.6%, Azorius Control at 46.6%, and Boros Dragons at 45.0%", "data_date": K},
 {"deck": "Azorius Artifacts", "win_rate": 54.8, "matches": None, "source_url": U_KAR, "snippet": "A Magic.gg metagame report puts it at a 54.8% match win rate in a field where it was about 3.5% of play. It also says the deck posted the second-highest match win rate among the twelve archetypes covered here, trailing behind only Jund Sacrifice.", "data_date": K},
 {"deck": "Boros Dwarves", "win_rate": 50.2, "matches": None, "source_url": U_KAR, "snippet": "Boros Dwarves had a 50.2% match win rate and Azorius Momo had 48.8%, both excluding mirrors, byes, and draws.", "data_date": K},
 {"deck": "Azorius Momo", "win_rate": 48.8, "matches": None, "source_url": U_KAR, "snippet": "Boros Dwarves had a 50.2% match win rate and Azorius Momo had 48.8%", "data_date": K},
 # other sources, for comparison
 {"deck": "Mono-Green Landfall", "win_rate": 53.3, "matches": 88000, "source_url": "https://mtga.untapped.gg/constructed/standard/archetypes/1397/mono-green-landfall", "snippet": "The Reality Fracture archetype page lists Mono-Green Landfall as Tier B with a 53.3% winrate across 88,000 matches.", "data_date": "Untapped.gg Arena ladder, Reality Fracture season; page freshness unclear (search metadata ~44 days old)"},
 {"deck": "Boros Dwarves (Untapped 'Boros Dwarf')", "win_rate": 55.3, "matches": 32000, "source_url": "https://mtga.untapped.gg/constructed/standard/archetypes/1101/boros-dwarf", "snippet": "Boros Dwarf is listed at a WINRATE 55.3% over 32,000 matches", "data_date": "Untapped.gg Arena ladder, Reality Fracture; ~33-45 days old"},
 {"deck": "Azorius Momo", "win_rate": 53.5, "matches": 3400, "source_url": "https://mtga.untapped.gg/constructed/standard/archetypes/5386/azorius-momo", "snippet": "Azorius Momo at a WINRATE 53.5% over 3,400 matches", "data_date": "Untapped.gg Arena ladder; page title says 'Marvel Super Heroes' season, so possibly stale"},
 {"deck": "Artifacts (Untapped; =Azorius Artifacts?)", "win_rate": 57.3, "matches": 44000, "source_url": "https://mtga.untapped.gg/constructed/standard/archetypes/2398/artifacts", "snippet": "Its Artifacts page lists a WINRATE 57.3% across 44,000 matches for the archetype overall.", "data_date": "Untapped.gg Arena ladder, Reality Fracture"},
 {"deck": "Jund Sacrifice", "win_rate": 62.2, "matches": 172, "source_url": "https://decklistdata.com/standard", "snippet": "decklistdata.com (Oct 23 snapshot): Jund Sacrifice shows a 62.2% win rate across 172 matches.", "data_date": "2026-10-23 snapshot, MTGO"},
 {"deck": "Mono-Green Landfall", "win_rate": 51, "matches": None, "source_url": "https://mydeckstats.com/matchups", "snippet": "Its Standard matrix covers the last 60 days, and it lists Mono Green Landfall at 51% overall and Dimir Midrange at 52% overall. The page also shows 31 decks and 20,496 matches for Standard, updated 30 October.", "data_date": "60 days to 2026-10-30"},
 {"deck": "Dimir Midrange", "win_rate": 52, "matches": None, "source_url": "https://mydeckstats.com/matchups", "snippet": "lists Mono Green Landfall at 51% overall and Dimir Midrange at 52% overall", "data_date": "60 days to 2026-10-30"},
 {"deck": "Azorius Momo", "win_rate": 50.0, "matches": 130, "source_url": U_BASE_MOMO, "snippet": "Real matches (basemtg, citing mtgpile, snapshot Oct 21): The deck is 65-65 overall.", "data_date": "Reality Fracture release to 2026-10-21 (mtgpile)"},
]

out = {
 "collected": "2026-11-13",
 "method": ("WebSearch only (standard and extended modes), 38 queries. The container proxy blocks MTG sites and WebFetch cannot resolve external hosts, so no page was opened. "
            "IMPORTANT: this WebSearch tool returns a model-written summary of the result pages, with quoted fragments, not raw search-engine snippets. Each 'snippet' field is copied "
            "from that summary text, so it is one step removed from the page. Numbers were recorded only where the search output stated them; a_win_rate values marked 'computed from' "
            "in notes are W/(W+L) from a W-L record the output stated, rounded to 0.1. Direction convention for mtgdecks.net was checked on three pairings seen from both pages. "
            "Many pairings appear twice (once from each deck's page); these are flagged in notes and must not be counted as independent evidence."),
 "blocked": [
  "Direct page access to every site (curl 403 from proxy; WebFetch cannot resolve hosts): magic.gg, mtgdecks.net, untapped.gg, mtggoldfish.com, melee.gg, mtgpile.com, basemtg.com, magicmeta.net, openmagic.gg, mydeckstats.com, decklistdata.com",
  "magic.gg 'Mapping the Standard Frontier' (2026-11-05): search output shows only the per-archetype table and qualitative matchup remarks; no matchup grid was visible, and per-archetype match counts were not shown",
  "Untapped.gg archetype 'Matchups' tables: loaded dynamically, not present in indexed text",
  "mtgdecks.net Standard winrate matrix (/Standard/winrates, /Standard/winrates/platform:mtgo): table not captured (indexed version labelled 'Secrets of Strixhaven May 2026' or 'The Hobbit October 2026', i.e. stale)",
  "mtgpile.com 'Top 8 win-rate matrix': grid empty in indexed text",
  "mydeckstats.com matchup heat map, magicmeta.net matrix cells, decklistdata.com matchup grid: cells not captured",
  "Magic World Championship 32 (Atlanta, 2026-11-13 to 15) is in progress today; only a metagame breakdown exists (128 players, 29 archetypes), no win rates yet",
  "No Reddit/Google Sheets matchup spreadsheet for this metagame was found",
  "No matchup numbers found at all for Boros Dwarves, and none for Azorius Artifacts under that name"
 ],
 "matchups": matchups,
 "deck_win_rates": deck_win_rates,
}
path = "/tmp/claude-0/-home-user-Mtg-simulator/ac175026-a9a0-5278-9b10-d7c0563130a0/scratchpad/real-matchups.json"
with open(path, "w") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
num = [x for x in matchups if x["a_win_rate"] is not None]
print(len(matchups), "rows;", len(num), "numeric;", sum(1 for x in num if not x["ambiguous"]), "numeric unambiguous")
for x in num:
    print(("AMB " if x["ambiguous"] else "    "), x["a"], "vs", x["b"], x["a_win_rate"], x["matches"], x["source_url"].split("/")[2])
