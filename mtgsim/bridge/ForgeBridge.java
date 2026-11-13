/*
 * ForgeBridge - a small headless driver that lets mtgsim run AI-vs-AI games on the Forge engine.
 *
 * Forge already ships a "sim" command, but it plays every game after the first inside one match,
 * where the previous game's loser always goes first. That correlates play/draw with results and
 * pulls measured win rates towards 50%. This driver instead starts a fresh match for every game
 * (so each game gets its own coin flip), seeds each game individually, and reports structured
 * results (who went first, turns, mulligans, which cards were seen and played) as one JSON object
 * per line, instead of a text log that has to be scraped.
 *
 * Protocol (line based, UTF-8):
 *   stdout: {"type":"ready",...} once the card database is loaded, then one result line per job.
 *   stdin : one job per line, tab separated key=value fields:
 *             id=<text> seed=<long> timeout=<seconds> format=<GameType> mc=<off|on|max>
 *             log=<path or empty> deck=<path> deck=<path> ... profile=<name or empty> ...
 *             seatmc=<off|on|max|empty> ...   (per seat, in deck order; empty follows mc=)
 *           the line "quit" ends the process.
 * Everything Forge itself prints is redirected to stderr so stdout carries only the protocol.
 *
 * This file is compiled against the Forge jar by `mtgsim setup`. Forge is licensed under
 * GPL-3.0 and this driver links against its classes, so GPL-3.0 terms apply to this driver
 * if it is distributed.
 */

import java.io.BufferedReader;
import java.io.File;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;

import com.google.common.eventbus.Subscribe;

import forge.GuiDesktop;
import forge.LobbyPlayer;
import forge.deck.Deck;
import forge.deck.DeckSection;
import forge.deck.io.DeckSerializer;
import forge.game.Game;
import forge.game.GameEndReason;
import forge.game.GameLogEntry;
import forge.game.GameOutcome;
import forge.game.GameRules;
import forge.game.GameType;
import forge.game.Match;
import forge.game.card.Card;
import forge.game.card.CardView;
import forge.game.event.GameEvent;
import forge.game.event.GameEventCardChangeZone;
import forge.game.event.GameEventLandPlayed;
import forge.game.event.GameEventSpellAbilityCast;
import forge.game.event.GameEventTurnBegan;
import forge.game.player.Player;
import forge.game.player.PlayerOutcome;
import forge.game.player.PlayerStatistics;
import forge.game.player.PlayerView;
import forge.game.player.RegisteredPlayer;
import forge.game.spellability.StackItemView;
import forge.game.zone.ZoneType;
import forge.gui.GuiBase;
import forge.item.IPaperCard;
import forge.localinstance.properties.ForgePreferences.FPref;
import forge.model.FModel;
import forge.player.GamePlayerUtil;
import forge.util.BuildInfo;
import forge.util.MyRandom;

// Used only by the Tracker's misplay signals (kept together so edits elsewhere merge cleanly).
import java.util.Set;
import java.util.TreeSet;
import forge.ai.ComputerUtilCard;
import forge.card.CardStateName;
import forge.card.mana.ManaAtom;
import forge.card.mana.ManaCost;
import forge.card.mana.ManaCostShard;
import forge.game.ability.ApiType;
import forge.game.cost.Cost;
import forge.game.cost.CostPart;
import forge.game.cost.CostPartMana;
import forge.game.cost.CostPayLife;
import forge.game.cost.CostSacrifice;
import forge.game.cost.CostTap;
import forge.game.event.GameEventSpellResolved;
import forge.game.event.GameEventTurnPhase;
import forge.game.keyword.Keyword;
import forge.game.phase.PhaseType;
import forge.game.spellability.AbilityManaPart;
import forge.game.spellability.AbilitySub;
import forge.game.spellability.SpellAbility;
import forge.game.spellability.SpellAbilityRestriction;
import forge.game.spellability.SpellAbilityStackInstance;
import forge.game.spellability.TargetRestrictions;

public final class ForgeBridge {
    /** Exit code telling the Python runner that the JVM is no longer trustworthy and must be restarted. */
    private static final int EXIT_RESTART = 3;
    /** Game threads get a large stack: deep trigger chains otherwise overflow the default one. */
    private static final long GAME_STACK_BYTES = 64L * 1024 * 1024;

    private static final Map<String, Deck> DECK_CACHE = new HashMap<>();

    private ForgeBridge() { }

    public static void main(final String[] args) throws Exception {
        final PrintStream proto = new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8");
        System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.err), true, "UTF-8"));
        System.setProperty("java.awt.headless", "true");

        try {
            GuiBase.setInterface(new GuiDesktop());
            FModel.initialize(null, prefs -> {
                // Pin every preference that changes how games play out, so results do not depend
                // on whatever a local Forge profile happens to contain.
                prefs.setPref(FPref.UI_CURRENT_AI_PROFILE, "Default");
                prefs.setPref(FPref.UI_ENABLE_AI_CHEATS, false);
                prefs.setPref(FPref.FILTERED_HANDS, false);
                return null;
            });
        } catch (final Throwable t) {
            proto.println("{\"type\":\"fatal\",\"error\":" + quote(stackTrace(t)) + "}");
            System.exit(2);
        }

        proto.println("{\"type\":\"ready\",\"forgeVersion\":" + quote(BuildInfo.getVersionString())
                + ",\"java\":" + quote(System.getProperty("java.version")) + "}");

        final BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            line = line.strip();
            if (line.isEmpty()) {
                continue;
            }
            if ("quit".equals(line)) {
                break;
            }
            final Job job = Job.parse(line);
            final Result result = runGame(job);
            proto.println(result.json);
            if (result.jvmTainted) {
                System.exit(EXIT_RESTART);
            }
        }
        System.exit(0);
    }

    // ------------------------------------------------------------------ jobs

    private static final class Job {
        String id = "";
        long seed;
        int timeoutSeconds = 180;
        String format = "Constructed";
        String monteCarlo = "off";
        String logPath = "";
        final List<String> decks = new ArrayList<>();
        final List<String> profiles = new ArrayList<>();
        final List<String> seatMonteCarlo = new ArrayList<>();

        static Job parse(final String line) {
            final Job job = new Job();
            for (final String field : line.split("\t")) {
                final int eq = field.indexOf('=');
                if (eq < 0) {
                    continue;
                }
                final String key = field.substring(0, eq);
                final String value = field.substring(eq + 1);
                switch (key) {
                    case "id": job.id = value; break;
                    case "seed": job.seed = Long.parseLong(value); break;
                    case "timeout": job.timeoutSeconds = Integer.parseInt(value); break;
                    case "format": job.format = value; break;
                    case "mc": job.monteCarlo = value; break;
                    case "log": job.logPath = value; break;
                    case "deck": job.decks.add(value); break;
                    case "profile": job.profiles.add(value); break;
                    case "seatmc": job.seatMonteCarlo.add(value); break;
                    default: break;
                }
            }
            return job;
        }
    }

    private static final class Result {
        final String json;
        final boolean jvmTainted;

        Result(final String json, final boolean jvmTainted) {
            this.json = json;
            this.jvmTainted = jvmTainted;
        }
    }

    // ------------------------------------------------------------- game loop

    private static Result runGame(final Job job) {
        final long started = System.currentTimeMillis();
        try {
            return runGameUnchecked(job, started);
        } catch (final Throwable t) {
            final StringBuilder sb = new StringBuilder();
            sb.append("{\"type\":\"result\",\"id\":").append(quote(job.id));
            sb.append(",\"status\":\"error\",\"winner\":-1,\"error\":").append(quote(stackTrace(t)));
            sb.append(",\"ms\":").append(System.currentTimeMillis() - started).append('}');
            return new Result(sb.toString(), false);
        }
    }

    private static Result runGameUnchecked(final Job job, final long started) throws Exception {
        if (job.decks.size() < 2) {
            throw new IllegalArgumentException("a game needs at least two decks");
        }

        // Seed before anything that might consume randomness (deck preparation, coin flip, shuffles).
        MyRandom.setRandom(new Random(job.seed));

        final GameType type = GameType.valueOf(job.format);
        final GameRules rules = new GameRules(type);
        rules.setAppliedVariants(EnumSet.of(type));
        rules.setGamesPerMatch(1);
        rules.setSimTimeout(job.timeoutSeconds);

        final List<RegisteredPlayer> seats = new ArrayList<>();
        final List<Deck> decks = new ArrayList<>();
        for (int i = 0; i < job.decks.size(); i++) {
            final Deck deck = loadDeck(job.decks.get(i));
            decks.add(deck);
            final RegisteredPlayer rp = type == GameType.Commander
                    ? RegisteredPlayer.forCommander(deck) : new RegisteredPlayer(deck);
            final String profile = i < job.profiles.size() ? job.profiles.get(i) : "";
            rp.setPlayer(createAi("Seat" + (i + 1), profile));
            seats.add(rp);
        }

        final Match match = new Match(rules, seats, "mtgsim");
        final Game game = match.createGame();
        invokeIfPresent(game, "setNoGUIUser");
        if (!"off".equals(job.monteCarlo)) {
            setFieldIfPresent(game, "AI_FLAT_MONTE_CARLO", Boolean.TRUE);
            if ("max".equals(job.monteCarlo)) {
                setFieldIfPresent(game, "AI_FLAT_MONTE_CARLO_MAX", Boolean.TRUE);
            }
        }

        applySeatMonteCarlo(game, seats, job.seatMonteCarlo);

        final Tracker tracker = new Tracker(game, seats);
        game.subscribeToEvents(tracker);

        final Throwable[] failure = new Throwable[1];
        final Thread gameThread = new Thread(null, () -> {
            try {
                match.startGame(game);
            } catch (final Throwable t) {
                failure[0] = t;
            }
        }, "mtgsim-game", GAME_STACK_BYTES);
        gameThread.setDaemon(true);
        gameThread.start();
        gameThread.join(job.timeoutSeconds * 1000L);

        boolean timedOut = false;
        boolean tainted = false;
        if (gameThread.isAlive()) {
            timedOut = true;
            try {
                game.setGameOver(GameEndReason.Draw);
            } catch (final Throwable ignored) {
                // the game thread may be mid-update; ending it is best effort
            }
            gameThread.interrupt();
            gameThread.join(15000L);
            // A game thread that will not stop keeps consuming the shared random stream and CPU;
            // nothing run after it in this JVM can be trusted, so ask to be restarted.
            tainted = gameThread.isAlive();
        }
        if (game.getOutcome() == null && !tainted) {
            try {
                game.setGameOver(GameEndReason.Draw);
            } catch (final Throwable ignored) {
                // reported as an error below
            }
        }

        final GameOutcome outcome = tainted ? null : game.getOutcome();
        final String status = timedOut ? "timeout" : (failure[0] != null || outcome == null) ? "error" : "ok";

        int winner = -1;
        if ("ok".equals(status) && !outcome.isDraw()) {
            final RegisteredPlayer winningSeat = outcome.getWinningPlayer();
            winner = winningSeat == null ? -1 : seats.indexOf(winningSeat);
        }

        final StringBuilder sb = new StringBuilder(1024);
        sb.append("{\"type\":\"result\",\"id\":").append(quote(job.id));
        sb.append(",\"status\":").append(quote(status));
        sb.append(",\"seed\":").append(job.seed);
        sb.append(",\"winner\":").append(winner);
        sb.append(",\"first\":").append(tracker.firstSeat);
        sb.append(",\"turns\":").append(tracker.lastTurn);
        sb.append(",\"endReason\":").append(outcome == null ? "null" : quote(String.valueOf(outcome.getWinCondition())));
        sb.append(",\"ms\":").append(System.currentTimeMillis() - started);
        sb.append(",\"restart\":").append(tainted);
        if (failure[0] != null) {
            sb.append(",\"error\":").append(quote(stackTrace(failure[0])));
        }

        final Map<RegisteredPlayer, PlayerStatistics> stats = new HashMap<>();
        if (outcome != null) {
            for (final Map.Entry<RegisteredPlayer, PlayerStatistics> e : outcome) {
                stats.put(e.getKey(), e.getValue());
            }
        }
        if (!tainted) {
            tracker.finish(); // reads the final hands; never throws
        }
        sb.append(",\"players\":[");
        for (int i = 0; i < seats.size(); i++) {
            if (i > 0) {
                sb.append(',');
            }
            final Deck deck = decks.get(i);
            final PlayerStatistics ps = stats.get(seats.get(i));
            final PlayerOutcome po = ps == null ? null : ps.getOutcome();
            sb.append("{\"mainCount\":").append(deck.getMain().countAll());
            sb.append(",\"sideCount\":").append(deck.get(DeckSection.Sideboard) == null ? 0
                    : deck.get(DeckSection.Sideboard).countAll());
            sb.append(",\"life\":").append(tainted ? "null" : String.valueOf(tracker.lifeOf(i)));
            sb.append(",\"mulligans\":").append(ps == null ? "null" : String.valueOf(ps.getMulliganCount()));
            sb.append(",\"turns\":").append(ps == null ? "null" : String.valueOf(ps.getTurnsPlayed()));
            sb.append(",\"lossReason\":").append(po == null || po.lossState == null ? "null"
                    : quote(String.valueOf(po.lossState)));
            sb.append(",\"altWin\":").append(po == null || po.altWinSourceName == null ? "null"
                    : quote(po.altWinSourceName));
            sb.append(",\"opening\":").append(countsJson(tracker.opening.get(i)));
            sb.append(",\"drawn\":").append(countsJson(tracker.drawn.get(i)));
            sb.append(",\"played\":").append(countsJson(tracker.played.get(i)));
            sb.append(tracker.misplayJson(i, !tainted));
            sb.append('}');
        }
        sb.append("]}");

        if (!job.logPath.isEmpty() && !tainted) {
            writeGameLog(game, job.logPath);
        }
        return new Result(sb.toString(), tainted);
    }

    private static Deck loadDeck(final String path) {
        Deck deck = DECK_CACHE.get(path);
        if (deck == null) {
            final File file = new File(path);
            if (!file.isFile()) {
                throw new IllegalArgumentException("deck file not found: " + path);
            }
            deck = DeckSerializer.fromFile(file);
            if (deck == null) {
                throw new IllegalArgumentException("could not read deck file: " + path);
            }
            DECK_CACHE.put(path, deck);
        }
        return deck;
    }

    /**
     * Gives individual seats their own Monte Carlo setting, so the search can be switched on just
     * for the decks the plain heuristics play badly. Forge exposes this per player for its own
     * A/B tests; on versions without it the request fails rather than being silently ignored.
     */
    private static void applySeatMonteCarlo(final Game game, final List<RegisteredPlayer> seats, final List<String> modes) {
        if (modes.isEmpty()) {
            return;
        }
        for (final Player p : game.getRegisteredPlayers()) {
            final int seat = seats.indexOf(p.getRegisteredPlayer());
            final String mode = seat >= 0 && seat < modes.size() ? modes.get(seat) : "";
            if (mode.isEmpty()) {
                continue;
            }
            try {
                final Object ai = p.getController().getClass().getMethod("getAi").invoke(p.getController());
                ai.getClass().getMethod("setFlatMonteCarloOverride", Boolean.class).invoke(ai, !"off".equals(mode));
                ai.getClass().getMethod("setFlatMonteCarloMaxOverride", Boolean.class).invoke(ai, "max".equals(mode));
            } catch (final ReflectiveOperationException e) {
                throw new IllegalArgumentException("this Forge version does not support per-player Monte Carlo settings");
            }
        }
    }

    private static LobbyPlayer createAi(final String name, final String profile) throws Exception {
        if (profile == null || profile.isEmpty()) {
            return GamePlayerUtil.createAiPlayer(name, 0, 0);
        }
        // Per-player AI profiles are a recent Forge addition; look the overload up reflectively so
        // this driver still compiles against releases that predate it.
        try {
            final Method m = GamePlayerUtil.class.getMethod("createAiPlayer",
                    String.class, int.class, int.class, java.util.Set.class, String.class);
            return (LobbyPlayer) m.invoke(null, name, 0, 0, null, profile);
        } catch (final NoSuchMethodException e) {
            throw new IllegalArgumentException("this Forge version does not support per-player AI profiles");
        }
    }

    private static void writeGameLog(final Game game, final String path) {
        try {
            final List<GameLogEntry> entries = new ArrayList<>(game.getGameLog().getLogEntries(null));
            Collections.reverse(entries);
            final File file = new File(path);
            if (file.getParentFile() != null) {
                file.getParentFile().mkdirs();
            }
            try (PrintWriter out = new PrintWriter(file, "UTF-8")) {
                for (final GameLogEntry entry : entries) {
                    out.println(entry);
                }
            }
        } catch (final Throwable t) {
            System.err.println("mtgsim: could not write game log " + path + ": " + t);
        }
    }

    // --------------------------------------------------------- event tracker

    /**
     * Listens on the game's event bus and records, per seat, which cards were seen and played, plus
     * the misplay signals defined in mtgsim/bridge/AGENTS.md: cards left in hand, castable cards that
     * sat idle, what removal was pointed at and the counterspell windows that went unused.
     *
     * Handlers run synchronously on the game thread, so everything here must leave the game exactly
     * as it found it: it only reads state and never touches MyRandom or the AI's memory. That rules
     * out the AI's own payment test (ComputerUtilMana.canPayManaCost can roll MyRandom and writes AI
     * memory), so mana availability is worked out here from the untapped sources. Spell abilities
     * the engine has not yet given an activating player are skipped rather than given one.
     */
    public static final class Tracker {
        /** A removal target worth less than this share of the best legal opposing target is "poor". */
        static final double POOR_TARGET = 2.0 / 3.0;
        private static final int ANY_COLOR = ManaAtom.ALL_MANA_COLORS;
        private static final int COLORLESS = ManaAtom.COLORLESS;

        private final Game game;
        private final Map<Integer, Integer> seatByPlayerId = new HashMap<>();
        final List<Map<String, Integer>> opening = new ArrayList<>();
        final List<Map<String, Integer>> drawn = new ArrayList<>();
        final List<Map<String, Integer>> played = new ArrayList<>();
        // Misplay signals, per seat and card name.
        final List<Map<String, Integer>> idleOwn = new ArrayList<>();
        final List<Map<String, Integer>> idleOpp = new ArrayList<>();
        /** passed windows, highest mana value let through, casts, spells targeted, their total mana value */
        final List<Map<String, int[]>> counter = new ArrayList<>();
        /** casts at permanents, casts hitting the caster's own permanent, poor casts, summed target quality */
        final List<Map<String, double[]>> removal = new ArrayList<>();
        final List<Map<String, Set<String>>> roles = new ArrayList<>();
        final List<Map<String, Integer>> endHand = new ArrayList<>();
        final int[] endHandLands;
        private final List<Window> windows = new ArrayList<>();
        private int checkpointTurn = -1;
        private boolean finished = false;
        private int errors = 0;
        private int unknownActivator = 0;
        private final Set<String> skippedNames = new TreeSet<>();
        volatile int firstSeat = -1;
        volatile int lastTurn = 0;
        private boolean started = false;

        /** A spell an opponent cast while this seat held a counterspell it could have cast in response. */
        private static final class Window {
            final int spellId;
            final int seat;
            final int cardId;
            final String name;
            final int manaValue;

            Window(final int spellId, final int seat, final int cardId, final String name, final int manaValue) {
                this.spellId = spellId;
                this.seat = seat;
                this.cardId = cardId;
                this.name = name;
                this.manaValue = manaValue;
            }
        }

        /** One mana an untapped source could make now; mana with a spending rule only counts where it applies. */
        private static final class Unit {
            int freeMask;
            final List<AbilityManaPart> restrictedParts = new ArrayList<>();
            final List<Integer> restrictedMasks = new ArrayList<>();

            void addRestricted(final AbilityManaPart part, final int mask) {
                restrictedParts.add(part);
                restrictedMasks.add(mask);
            }

            int maskFor(final SpellAbility sa) {
                int mask = freeMask;
                for (int i = 0; i < restrictedParts.size(); i++) {
                    final int extra = restrictedMasks.get(i);
                    if ((mask | extra) != mask && restrictedParts.get(i).meetsManaRestrictions(sa)) {
                        mask |= extra;
                    }
                }
                return mask;
            }
        }

        Tracker(final Game game, final List<RegisteredPlayer> seats) {
            this.game = game;
            for (final Player p : game.getRegisteredPlayers()) {
                seatByPlayerId.put(p.getId(), seats.indexOf(p.getRegisteredPlayer()));
            }
            for (int i = 0; i < seats.size(); i++) {
                opening.add(new TreeMap<>());
                drawn.add(new TreeMap<>());
                played.add(new TreeMap<>());
                idleOwn.add(new TreeMap<>());
                idleOpp.add(new TreeMap<>());
                counter.add(new TreeMap<>());
                removal.add(new TreeMap<>());
                roles.add(new TreeMap<>());
                endHand.add(new TreeMap<>());
            }
            endHandLands = new int[seats.size()];
        }

        int lifeOf(final int seat) {
            for (final Player p : game.getRegisteredPlayers()) {
                final Integer s = seatByPlayerId.get(p.getId());
                if (s != null && s == seat) {
                    return p.getLife();
                }
            }
            return 0;
        }

        @Subscribe
        public void receive(final GameEvent event) {
            // Tracking must never be able to break a game, so nothing may escape from here.
            try {
                if (event instanceof GameEventTurnBegan) {
                    onTurnBegan((GameEventTurnBegan) event);
                } else if (event instanceof GameEventCardChangeZone) {
                    onZoneChange((GameEventCardChangeZone) event);
                } else if (event instanceof GameEventSpellAbilityCast) {
                    onCast((GameEventSpellAbilityCast) event);
                } else if (event instanceof GameEventLandPlayed) {
                    final GameEventLandPlayed lp = (GameEventLandPlayed) event;
                    count(played, seatOf(lp.player()), lp.land());
                } else if (event instanceof GameEventTurnPhase) {
                    onPhase((GameEventTurnPhase) event);
                } else if (event instanceof GameEventSpellResolved) {
                    onResolved((GameEventSpellResolved) event);
                }
            } catch (final Throwable t) {
                ignored(t);
            }
        }

        private void ignored(final Throwable t) {
            errors++;
            if (errors <= 5) {
                System.err.println("mtgsim: tracker ignored " + t
                        + (t.getStackTrace().length > 0 ? " at " + t.getStackTrace()[0] : ""));
            }
        }

        private void guarded(final Runnable step) {
            try {
                step.run();
            } catch (final Throwable t) {
                ignored(t);
            }
        }

        private void onTurnBegan(final GameEventTurnBegan event) {
            lastTurn = Math.max(lastTurn, event.turnNumber());
            // The stack is empty between turns, so a spell still waiting here was countered or removed.
            windows.clear();
            if (started) {
                return;
            }
            // The first turn begins after mulligans, so hands are the kept opening hands.
            started = true;
            firstSeat = seatOf(event.turnOwner());
            for (final Player p : game.getRegisteredPlayers()) {
                final int seat = seatOfPlayer(p);
                if (seat < 0) {
                    continue;
                }
                for (final Card c : p.getCardsIn(ZoneType.Hand)) {
                    opening.get(seat).merge(nameOf(c), 1, Integer::sum);
                    noteRoles(seat, c);
                }
            }
        }

        private void onZoneChange(final GameEventCardChangeZone event) {
            if (!started || event.from() == null || event.to() == null) {
                return;
            }
            if (event.to().zoneType() != ZoneType.Hand || event.from().zoneType() != ZoneType.Library) {
                return;
            }
            final int seat = seatOf(event.to().player());
            count(drawn, seat, event.card());
            if (seat >= 0 && event.card() != null) {
                noteRoles(seat, game.findById(event.card().getId()));
            }
        }

        private void onCast(final GameEventSpellAbilityCast event) {
            final StackItemView item = event.si();
            if (item == null || item.isAbility() || item.isTrigger()) {
                return;
            }
            final int seat = seatOf(item.getActivatingPlayer());
            count(played, seat, item.getSourceCard());
            if (seat < 0 || event.sa() == null) {
                return;
            }
            final SpellAbility sa = findOnStack(event.sa().getId());
            if (sa == null || !sa.isSpell() || sa.isCopied() || sa.getHostCard() == null || sa.getActivatingPlayer() == null) {
                return;
            }
            final Card host = sa.getHostCard();
            final Player caster = sa.getActivatingPlayer();
            final String name = nameOf(host);
            noteRoles(seat, host);
            guarded(() -> recordCounterCast(seat, name, sa));
            guarded(() -> recordRemovalTargets(seat, name, sa, caster));
            guarded(() -> openCounterWindows(sa, caster));
        }

        /** Once per turn, when the cleanup step begins: which cards could still have been cast. */
        private void onPhase(final GameEventTurnPhase event) {
            if (!started || event.phase() != PhaseType.CLEANUP) {
                return;
            }
            final int turn = game.getPhaseHandler().getTurn();
            if (turn == checkpointTurn) {
                return; // a repeated cleanup step
            }
            checkpointTurn = turn;
            final Player active = game.getPhaseHandler().getPlayerTurn();
            for (final Player p : game.getRegisteredPlayers()) {
                final int seat = seatOfPlayer(p);
                if (seat >= 0 && p.isInGame()) {
                    recordIdle(p, seat, p == active);
                }
            }
        }

        private void onResolved(final GameEventSpellResolved event) {
            if (event.spell() == null || windows.isEmpty()) {
                return;
            }
            final int id = event.spell().getId();
            for (int i = windows.size() - 1; i >= 0; i--) {
                final Window w = windows.get(i);
                if (w.spellId != id) {
                    continue;
                }
                windows.remove(i);
                if (event.hasFizzled()) {
                    continue;
                }
                final Card c = game.findById(w.cardId);
                if (c == null || !c.isInZone(ZoneType.Hand)) {
                    continue; // cast or otherwise gone before the spell resolved
                }
                final int[] rec = counterRecord(w.seat, w.name);
                rec[0]++;
                rec[1] = Math.max(rec[1], w.manaValue);
            }
        }

        /** Hand contents at the end of the game; called once from the driver thread after the game stopped. */
        void finish() {
            if (finished) {
                return;
            }
            finished = true;
            try {
                for (final Player p : game.getRegisteredPlayers()) {
                    final int seat = seatOfPlayer(p);
                    if (seat < 0) {
                        continue;
                    }
                    for (final Card c : p.getCardsIn(ZoneType.Hand)) {
                        if (c.isLand()) {
                            endHandLands[seat]++;
                        } else {
                            endHand.get(seat).merge(nameOf(c), 1, Integer::sum);
                            noteRoles(seat, c);
                        }
                    }
                }
            } catch (final Throwable t) {
                ignored(t);
            }
            if (errors > 0 || unknownActivator > 0) {
                System.err.println("mtgsim: tracker: " + errors + " ignored errors, " + unknownActivator
                        + " castability checks skipped (no activating player: " + String.join(", ", skippedNames) + ")");
            }
        }

        // ------------------------------------------------------ misplay signals

        private void recordIdle(final Player p, final int seat, final boolean ownTurn) {
            final List<Unit> units = manaUnits(p);
            final Set<String> idle = new TreeSet<>();
            for (final Card c : p.getCardsIn(ZoneType.Hand)) {
                try {
                    if (c.isLand()) {
                        continue;
                    }
                    noteRoles(seat, c);
                    final String name = nameOf(c);
                    // On the opponent's turn only instant-speed cards could have been cast.
                    if (!idle.contains(name) && castableNow(p, c, units, !ownTurn)) {
                        idle.add(name);
                    }
                } catch (final Throwable t) {
                    ignored(t);
                }
            }
            final Map<String, Integer> target = (ownTurn ? idleOwn : idleOpp).get(seat);
            for (final String name : idle) {
                target.merge(name, 1, Integer::sum);
            }
        }

        private boolean castableNow(final Player p, final Card c, final List<Unit> units, final boolean instantSpeed) {
            if (c.getType().isLegendary() && controlsNamed(p, nameOf(c))) {
                return false; // a second copy would only be lost to the legend rule
            }
            for (final SpellAbility sa : spellsOf(c)) {
                if (sa.getActivatingPlayer() != p) {
                    unknownActivator++;
                    if (skippedNames.size() < 8) {
                        skippedNames.add(nameOf(c));
                    }
                    continue;
                }
                if (instantSpeed && !sa.withFlash(c, p)) {
                    continue;
                }
                if (payableNow(p, c, sa, units) && targetsAvailable(sa)) {
                    return true;
                }
            }
            return false;
        }

        /** Casting restrictions (timing aside), additional costs and the mana cost, with X = 0. */
        private boolean payableNow(final Player p, final Card c, final SpellAbility sa, final List<Unit> units) {
            if (c.isPhasedOut() || c.isUsedToPay()) {
                return false;
            }
            final Cost cost = sa.getPayCosts();
            if (cost == null) {
                return false;
            }
            final ManaCost mana = cost.getTotalMana();
            if (mana == null || mana.isNoCost()) {
                return false;
            }
            final SpellAbilityRestriction r = sa.getRestrictions();
            if (r != null && (!r.checkActivatorRestrictions(c, sa) || !r.checkZoneRestrictions(c, sa)
                    || !r.checkOtherRestrictions(c, sa, p))) {
                return false;
            }
            if (!sa.checkRestrictions(c, p)) {
                return false;
            }
            for (final CostPart part : cost.getCostParts()) {
                if (!(part instanceof CostPartMana) && !part.canPay(sa, p, false)) {
                    return false;
                }
            }
            return canPayMana(units, mana, p, sa);
        }

        private static boolean controlsNamed(final Player p, final String name) {
            for (final Card c : p.getCardsIn(ZoneType.Battlefield)) {
                if (name.equals(nameOf(c))) {
                    return true;
                }
            }
            return false;
        }

        private boolean targetsAvailable(final SpellAbility sa) {
            if (sa.getApi() == ApiType.Charm) {
                final List<AbilitySub> choices = sa.getAdditionalAbilityList("Choices");
                if (choices == null || choices.isEmpty()) {
                    return true;
                }
                for (final AbilitySub choice : choices) {
                    if (chainTargetsAvailable(choice)) {
                        return true;
                    }
                }
                return false;
            }
            return chainTargetsAvailable(sa);
        }

        /** Required targets exist; a harmful effect also needs an opposing target, even when its targets are optional. */
        private boolean chainTargetsAvailable(final SpellAbility first) {
            for (SpellAbility s = first; s != null; s = s.getSubAbility()) {
                if (!s.usesTargeting() || (s != first && isConditional(s))) {
                    continue;
                }
                final TargetRestrictions tr = s.getTargetRestrictions();
                final boolean harmful = isHarmful(s);
                if ((harmful || tr.getMinTargets(s.getHostCard(), s) > 0) && !hasCandidate(s, tr, harmful)) {
                    return false;
                }
            }
            return true;
        }

        private boolean hasCandidate(final SpellAbility s, final TargetRestrictions tr, final boolean opposingOnly) {
            final Player me = s.getActivatingPlayer();
            for (final Player pl : game.getPlayers()) {
                if ((!opposingOnly || pl.isOpponentOf(me)) && s.canTarget(pl)) {
                    return true;
                }
            }
            for (final Card c : game.getCardsIn(tr.getZone())) {
                if ((!opposingOnly || (c.getController() != null && c.getController().isOpponentOf(me))) && s.canTarget(c)) {
                    return true;
                }
            }
            return false;
        }

        private static boolean isConditional(final SpellAbility s) {
            for (final String key : s.getMapParams().keySet()) {
                if (key.startsWith("Condition") || "OptionalDecider".equals(key)) {
                    return true;
                }
            }
            return false;
        }

        private void openCounterWindows(final SpellAbility spell, final Player caster) {
            final int manaValue = spell.getHostCard().getCMC();
            for (final Player p : game.getRegisteredPlayers()) {
                final int seat = seatOfPlayer(p);
                if (seat < 0 || p == caster || !p.isInGame() || !p.isOpponentOf(caster)) {
                    continue;
                }
                List<Unit> units = null;
                final Set<String> done = new TreeSet<>();
                for (final Card c : p.getCardsIn(ZoneType.Hand)) {
                    try {
                        final String name = nameOf(c);
                        if (c.isLand() || done.contains(name)) {
                            continue;
                        }
                        for (final SpellAbility csa : spellsOf(c)) {
                            if (csa.getActivatingPlayer() != p || !csa.withFlash(c, p) || !canCounter(csa, spell)) {
                                continue;
                            }
                            if (units == null) {
                                units = manaUnits(p);
                            }
                            if (payableNow(p, c, csa, units)) {
                                done.add(name);
                                windows.add(new Window(spell.getId(), seat, c.getId(), name, manaValue));
                                break;
                            }
                        }
                    } catch (final Throwable t) {
                        ignored(t);
                    }
                }
            }
        }

        /** Whether this spell, or one of its modes if it is a charm, could counter the spell on the stack. */
        private static boolean canCounter(final SpellAbility csa, final SpellAbility spell) {
            final List<SpellAbility> modes = new ArrayList<>();
            if (csa.getApi() == ApiType.Counter) {
                modes.add(csa);
            } else if (csa.getApi() == ApiType.Charm) {
                final List<AbilitySub> choices = csa.getAdditionalAbilityList("Choices");
                if (choices != null) {
                    modes.addAll(choices);
                }
            }
            for (final SpellAbility mode : modes) {
                if (mode.getApi() == ApiType.Counter && mode.usesTargeting() && mode.getActivatingPlayer() != null
                        && mode.canTargetSpellAbility(spell) && spell.isCounterableBy(mode)) {
                    return true;
                }
            }
            return false;
        }

        private void recordCounterCast(final int seat, final String name, final SpellAbility sa) {
            boolean counters = false;
            int targets = 0;
            int manaValue = 0;
            for (final SpellAbility s : chainOf(sa)) {
                if (s.getApi() != ApiType.Counter) {
                    continue;
                }
                counters = true;
                for (final SpellAbility t : s.getTargets().getTargetSpells()) {
                    targets++;
                    if (t.getHostCard() != null) {
                        manaValue += t.getHostCard().getCMC();
                    }
                }
            }
            if (counters) {
                final int[] rec = counterRecord(seat, name);
                rec[2]++;
                rec[3] += targets;
                rec[4] += manaValue;
            }
        }

        private int[] counterRecord(final int seat, final String name) {
            return counter.get(seat).computeIfAbsent(name, k -> new int[5]);
        }

        /**
         * For a spell with a harmful targeted effect on permanents: how its targets compare with the
         * best legal opposing targets it could have killed instead, and whether it hit its caster's own.
         */
        private void recordRemovalTargets(final int seat, final String name, final SpellAbility sa, final Player caster) {
            final List<SpellAbility> chain = chainOf(sa);
            if (isBlink(chain)) {
                return;
            }
            boolean any = false;
            boolean own = false;
            double quality = 0;
            int compared = 0;
            for (final SpellAbility s : chain) {
                if (!s.usesTargeting() || !isHarmful(s)) {
                    continue;
                }
                final List<Card> theirs = new ArrayList<>();
                boolean mine = false;
                for (final Card t : s.getTargets().getTargetCards()) {
                    if (!t.isInZone(ZoneType.Battlefield)) {
                        continue;
                    }
                    if (t.getController() == caster) {
                        mine = true;
                    } else {
                        theirs.add(t);
                    }
                }
                // A fight needs one of your own creatures; that half is not a misplay.
                if (s.getApi() == ApiType.Fight) {
                    mine = false;
                }
                if (!mine && theirs.isEmpty()) {
                    continue;
                }
                any = true;
                own |= mine;
                compared++;
                if (!theirs.isEmpty()) {
                    quality += targetQuality(s, caster, theirs);
                }
            }
            if (!any) {
                return;
            }
            final double q = quality / compared;
            final double[] rec = removal.get(seat).computeIfAbsent(name, k -> new double[4]);
            rec[0] += 1;
            rec[1] += own ? 1 : 0;
            rec[2] += own || q < POOR_TARGET ? 1 : 0;
            rec[3] += q;
        }

        /** Value of the chosen targets over the value of the best ones the effect could have killed (at most 1). */
        private double targetQuality(final SpellAbility s, final Player caster, final List<Card> chosen) {
            final boolean creatures = chosen.get(0).isCreature();
            final List<Double> picked = new ArrayList<>();
            for (final Card t : chosen) {
                if (t.isCreature() == creatures) {
                    picked.add(valueOf(t));
                }
            }
            final List<Double> options = new ArrayList<>(picked);
            for (final Card c : game.getCardsIn(ZoneType.Battlefield)) {
                if (c.isCreature() != creatures || chosen.contains(c)) {
                    continue;
                }
                final Player controller = c.getController();
                if (controller == null || controller == caster || !controller.isOpponentOf(caster)) {
                    continue;
                }
                if (s.canTarget(c) && wouldKill(s, c)) {
                    options.add(valueOf(c));
                }
            }
            options.sort(Collections.reverseOrder());
            double ideal = 0;
            double got = 0;
            for (int i = 0; i < picked.size(); i++) {
                ideal += options.get(i);
                got += picked.get(i);
            }
            return ideal <= 0 ? 1.0 : Math.min(1.0, got / ideal);
        }

        private static double valueOf(final Card c) {
            // Forge's own creature score; other permanents by mana value.
            return c.isCreature() ? ComputerUtilCard.evaluateCreature(c) : c.getCMC() + 1.0;
        }

        private static boolean wouldKill(final SpellAbility s, final Card c) {
            final ApiType api = s.getApi();
            if (api == ApiType.Destroy) {
                return !c.hasKeyword(Keyword.INDESTRUCTIBLE);
            }
            Integer amount = null;
            if (api == ApiType.DealDamage) {
                amount = intParam(s, "NumDmg", null);
            } else if (api == ApiType.Pump) {
                final Integer def = intParam(s, "NumDef", null);
                amount = def == null ? null : -def;
            } else if (api == ApiType.PutCounter) {
                amount = intParam(s, "CounterNum", 1);
            }
            if (amount == null) {
                return true;
            }
            if (c.isCreature()) {
                return c.getNetToughness() - c.getDamage() <= amount;
            }
            if (c.isPlaneswalker() && api == ApiType.DealDamage) {
                return c.getCurrentLoyalty() <= amount;
            }
            return true;
        }

        private static Integer intParam(final SpellAbility s, final String key, final Integer fallback) {
            final String value = s.getParam(key);
            if (value == null) {
                return fallback;
            }
            try {
                return Integer.parseInt(value.trim());
            } catch (final NumberFormatException e) {
                return null; // X or a computed amount
            }
        }

        /**
         * Destroy, exile/bounce from the battlefield, damage, -X/-X, -1/-1 counters, fight, steal; not
         * when it can only target your own permanents (saving a creature by bouncing it, for one).
         */
        private static boolean isHarmful(final SpellAbility s) {
            final ApiType api = s.getApi();
            if (api == null || (s.usesTargeting() && ownTargetsOnly(s.getTargetRestrictions()))) {
                return false;
            }
            switch (api) {
                case Destroy:
                case DealDamage:
                case Fight:
                case GainControl:
                    return true;
                case ChangeZone:
                    return s.getParamOrDefault("Origin", "").contains("Battlefield")
                            && !s.getParamOrDefault("Destination", "").contains("Battlefield");
                case Pump:
                    return s.getParamOrDefault("NumDef", "").trim().startsWith("-");
                case PutCounter:
                    return "M1M1".equals(s.getParamOrDefault("CounterType", ""));
                default:
                    return false;
            }
        }

        private static boolean ownTargetsOnly(final TargetRestrictions tr) {
            final String[] valid = tr.getValidTgts();
            if (valid == null || valid.length == 0) {
                return false;
            }
            for (final String v : valid) {
                if (!v.contains("YouCtrl") && !v.contains("YouOwn")) {
                    return false;
                }
            }
            return true;
        }

        /** Exile-and-return effects (flicker) only look like removal. */
        private static boolean isBlink(final List<SpellAbility> chain) {
            for (final SpellAbility s : chain) {
                final ApiType api = s.getApi();
                if (api == ApiType.DelayedTrigger) {
                    return true;
                }
                if (api == ApiType.ChangeZone && s.getParamOrDefault("Destination", "").contains("Battlefield")
                        && s.getParamOrDefault("Origin", "").contains("Exile")) {
                    return true;
                }
            }
            return false;
        }

        private void noteRoles(final int seat, final Card c) {
            if (seat < 0 || c == null) {
                return;
            }
            final String name = nameOf(c);
            final Map<String, Set<String>> known = roles.get(seat);
            if (name == null || known.containsKey(name)) {
                return;
            }
            final Set<String> tags = new TreeSet<>();
            known.put(name, tags);
            try {
                if (c.isLand()) {
                    tags.add("land");
                }
                if (c.isCreature()) {
                    tags.add("creature");
                }
                if (c.isInstant() || c.hasKeyword(Keyword.FLASH)) {
                    tags.add("instant");
                }
                for (final SpellAbility sa : spellsOf(c)) {
                    final List<List<SpellAbility>> modes = new ArrayList<>();
                    if (sa.getApi() == ApiType.Charm) {
                        final List<AbilitySub> choices = sa.getAdditionalAbilityList("Choices");
                        if (choices != null) {
                            for (final AbilitySub choice : choices) {
                                modes.add(chainOf(choice));
                            }
                        }
                    } else {
                        modes.add(chainOf(sa));
                    }
                    for (final List<SpellAbility> chain : modes) {
                        tagEffects(chain, tags);
                    }
                }
            } catch (final Throwable t) {
                ignored(t);
            }
        }

        private static void tagEffects(final List<SpellAbility> chain, final Set<String> tags) {
            final boolean blink = isBlink(chain);
            for (final SpellAbility s : chain) {
                final ApiType api = s.getApi();
                if (api == null) {
                    continue;
                }
                if (api == ApiType.Counter) {
                    tags.add("counter");
                } else if (!blink && s.usesTargeting() && isHarmful(s)
                        && s.getTargetRestrictions().getZone().contains(ZoneType.Battlefield)) {
                    tags.add("removal");
                } else if (api == ApiType.DestroyAll || api == ApiType.DamageAll || api == ApiType.SacrificeAll
                        || (api == ApiType.ChangeZoneAll && s.getParamOrDefault("Origin", "").contains("Battlefield")
                            && !s.getParamOrDefault("Destination", "").contains("Battlefield"))
                        || (api == ApiType.PumpAll && s.getParamOrDefault("NumDef", "").trim().startsWith("-"))
                        || (api == ApiType.PutCounterAll && "M1M1".equals(s.getParamOrDefault("CounterType", "")))) {
                    tags.add("sweeper");
                } else if (api == ApiType.Sacrifice
                        && (s.usesTargeting() || s.getParamOrDefault("Defined", "").contains("Opp"))) {
                    tags.add("edict");
                }
            }
        }

        // ------------------------------------------------------------ mana

        /** The mana the player's untapped sources could make right now, one entry per mana. */
        private static List<Unit> manaUnits(final Player p) {
            final List<Unit> units = new ArrayList<>();
            for (final Card c : p.getCardsIn(ZoneType.Battlefield)) {
                if (c.isPhasedOut()) {
                    continue;
                }
                Unit single = null; // a source making one mana: any of its abilities, one use
                int[] multi = null; // otherwise its biggest ability
                AbilityManaPart multiRule = null;
                for (final SpellAbility ma : c.getManaAbilities()) {
                    final AbilityManaPart part = ma.getManaPart();
                    if (part == null || !freeToActivate(ma, c)) {
                        continue;
                    }
                    final int[] made = produced(ma, part);
                    if (made.length == 0) {
                        continue;
                    }
                    final boolean restricted = !isEmpty(part.getManaRestrictions()) || !isEmpty(part.getExtraManaRestriction());
                    if (made.length == 1) {
                        if (single == null) {
                            single = new Unit();
                        }
                        if (restricted) {
                            single.addRestricted(part, made[0]);
                        } else {
                            single.freeMask |= made[0];
                        }
                    } else if (multi == null || made.length > multi.length) {
                        multi = made;
                        multiRule = restricted ? part : null;
                    }
                }
                if (multi != null) {
                    for (final int mask : multi) {
                        final Unit u = new Unit();
                        if (multiRule == null) {
                            u.freeMask = mask;
                        } else {
                            u.addRestricted(multiRule, mask);
                        }
                        units.add(u);
                    }
                } else if (single != null) {
                    units.add(single);
                }
            }
            return units;
        }

        private static boolean isEmpty(final String s) {
            return s == null || s.isEmpty();
        }

        /** Only free sources count: a tap (no summoning sickness), sacrificing itself, or life. */
        private static boolean freeToActivate(final SpellAbility ma, final Card c) {
            final Cost cost = ma.getPayCosts();
            if (cost == null) {
                return true;
            }
            for (final CostPart part : cost.getCostParts()) {
                if (part instanceof CostTap) {
                    if (c.isTapped() || c.isSick()) {
                        return false;
                    }
                } else if (part instanceof CostSacrifice) {
                    if (!part.payCostFromSource()) {
                        return false;
                    }
                } else if (!(part instanceof CostPayLife)) {
                    return false; // filters, counters, discards and the like are not free mana
                }
            }
            return true;
        }

        /** Colour masks (ManaAtom bits) of the mana one activation makes; empty when it cannot be told safely. */
        private static int[] produced(final SpellAbility ma, final AbilityManaPart part) {
            final String text = part.getOrigProduced();
            if (text == null || text.isEmpty() || text.contains("Special")) {
                return new int[0];
            }
            int amount = 1;
            try {
                amount = Math.max(1, Integer.parseInt(ma.getParamOrDefault("Amount", "1").trim()));
            } catch (final NumberFormatException e) {
                amount = 1; // a computed amount: count the one mana it surely makes
            }
            final List<Integer> masks = new ArrayList<>();
            if (text.startsWith("Combo") || text.contains("Any") || text.contains("Chosen")) {
                int mask = text.contains("Any") || text.contains("Chosen") || text.contains("ColorIdentity") ? ANY_COLOR : 0;
                for (final String token : text.split("\\s+")) {
                    mask |= colourOf(token);
                }
                if (mask != 0) {
                    masks.add(mask);
                }
            } else {
                for (final String token : text.trim().split("\\s+")) {
                    final int mask = colourOf(token);
                    if (mask != 0) {
                        masks.add(mask);
                    }
                }
            }
            final int[] out = new int[masks.size() * amount];
            for (int i = 0; i < out.length; i++) {
                out[i] = masks.get(i % masks.size());
            }
            return out;
        }

        private static int colourOf(final String token) {
            switch (token) {
                case "W": return ManaAtom.WHITE;
                case "U": return ManaAtom.BLUE;
                case "B": return ManaAtom.BLACK;
                case "R": return ManaAtom.RED;
                case "G": return ManaAtom.GREEN;
                case "C": return COLORLESS;
                default: return 0;
            }
        }

        /**
         * Whether the units can pay the cost with X = 1 (casting for X = 0 is rarely a real option):
         * coloured symbols are matched to distinct sources (bipartite matching), the rest must cover
         * the generic part. Phyrexian symbols are paid with life while the player has more than 2;
         * {2/W} falls back to two generic. Cost reductions are ignored, so a reduced spell can be
         * missed but never wrongly counted.
         */
        static boolean canPayMana(final List<Unit> units, final ManaCost cost, final Player p, final SpellAbility sa) {
            int generic = cost.getGenericCost();
            final List<Integer> need = new ArrayList<>();
            final List<Integer> orTwo = new ArrayList<>();
            int life = p.getLife();
            for (final ManaCostShard shard : cost) {
                final int bits = shard.getShard();
                final int colours = bits & (ANY_COLOR | COLORLESS);
                if ((bits & ManaAtom.IS_X) != 0) {
                    generic++;
                    continue;
                }
                if ((bits & ManaAtom.OR_2_LIFE) != 0 && life > 2) {
                    life -= 2;
                    continue;
                }
                if (colours == 0 || (bits & ManaAtom.IS_SNOW) != 0) {
                    generic++;
                } else if ((bits & ManaAtom.OR_2_GENERIC) != 0) {
                    orTwo.add(colours);
                } else {
                    need.add(colours);
                }
            }
            final int n = units.size();
            final int[] mask = new int[n];
            final int[] owner = new int[n];
            for (int i = 0; i < n; i++) {
                mask[i] = units.get(i).maskFor(sa);
                owner[i] = -1;
            }
            final List<Integer> all = new ArrayList<>(need);
            all.addAll(orTwo);
            int matched = 0;
            for (int k = 0; k < all.size(); k++) {
                if (augment(k, all, mask, owner, new boolean[n])) {
                    matched++;
                } else if (k >= need.size()) {
                    generic += 2;
                } else {
                    return false;
                }
            }
            return n - matched >= generic;
        }

        private static boolean augment(final int k, final List<Integer> need, final int[] mask, final int[] owner, final boolean[] seen) {
            for (int u = 0; u < mask.length; u++) {
                if (seen[u] || (mask[u] & need.get(k)) == 0) {
                    continue;
                }
                seen[u] = true;
                if (owner[u] < 0 || augment(owner[u], need, mask, owner, seen)) {
                    owner[u] = k;
                    return true;
                }
            }
            return false;
        }

        // ----------------------------------------------------------- helpers

        /** The spells a card in hand offers: its face, plus the other half or face it can be cast as. */
        private static List<SpellAbility> spellsOf(final Card c) {
            final List<SpellAbility> out = new ArrayList<>();
            addSpells(out, c.getSpells());
            if (c.getCurrentStateName() == CardStateName.Original) {
                if (c.isModal() && c.hasState(CardStateName.Backside)) {
                    addSpells(out, c.getState(CardStateName.Backside).getSpellAbilities());
                }
                if (c.hasState(CardStateName.Secondary)) {
                    addSpells(out, c.getState(CardStateName.Secondary).getSpellAbilities());
                }
                if (c.isSplitCard()) {
                    for (final CardStateName half : new CardStateName[] {CardStateName.LeftSplit, CardStateName.RightSplit}) {
                        if (c.hasState(half)) {
                            addSpells(out, c.getState(half).getSpellAbilities());
                        }
                    }
                }
            }
            return out;
        }

        private static void addSpells(final List<SpellAbility> out, final Iterable<SpellAbility> from) {
            for (final SpellAbility sa : from) {
                if (sa != null && sa.isSpell() && !sa.isLandAbility()) {
                    out.add(sa);
                }
            }
        }

        private static List<SpellAbility> chainOf(final SpellAbility first) {
            final List<SpellAbility> out = new ArrayList<>();
            for (SpellAbility s = first; s != null && out.size() < 32; s = s.getSubAbility()) {
                out.add(s);
            }
            return out;
        }

        private SpellAbility findOnStack(final int id) {
            for (final SpellAbilityStackInstance si : game.getStack()) {
                final SpellAbility sa = si.getSpellAbility();
                if (sa != null && sa.getId() == id) {
                    return sa;
                }
            }
            return null;
        }

        private int seatOfPlayer(final Player p) {
            final Integer seat = p == null ? null : seatByPlayerId.get(p.getId());
            return seat == null ? -1 : seat;
        }

        private int seatOf(final PlayerView view) {
            if (view == null) {
                return -1;
            }
            final Integer seat = seatByPlayerId.get(view.getId());
            return seat == null ? -1 : seat;
        }

        private void count(final List<Map<String, Integer>> target, final int seat, final CardView view) {
            if (seat < 0 || view == null) {
                return;
            }
            final Card card = game.findById(view.getId());
            final String name = card != null ? nameOf(card) : view.getName();
            if (name != null && !name.isEmpty()) {
                target.get(seat).merge(name, 1, Integer::sum);
            }
        }

        private static String nameOf(final Card card) {
            final IPaperCard paper = card.getPaperCard();
            return paper != null ? paper.getName() : card.getName();
        }

        // ------------------------------------------------------------- JSON

        /** The misplay fields of one seat's result, each starting with a comma; null values if unknown. */
        String misplayJson(final int seat, final boolean available) {
            if (!available || !finished) {
                return ",\"endHand\":null,\"endHandLands\":null,\"idleOwn\":null,\"idleOpp\":null,"
                        + "\"counter\":null,\"removal\":null,\"roles\":null";
            }
            try {
                final StringBuilder sb = new StringBuilder(512);
                sb.append(",\"endHand\":").append(countsJson(endHand.get(seat)));
                sb.append(",\"endHandLands\":").append(endHandLands[seat]);
                sb.append(",\"idleOwn\":").append(countsJson(idleOwn.get(seat)));
                sb.append(",\"idleOpp\":").append(countsJson(idleOpp.get(seat)));
                sb.append(",\"counter\":{");
                boolean first = true;
                for (final Map.Entry<String, int[]> e : counter.get(seat).entrySet()) {
                    final int[] v = e.getValue();
                    sb.append(first ? "" : ",").append(quote(e.getKey()))
                            .append(":{\"passed\":").append(v[0]).append(",\"passedMaxMv\":").append(v[1])
                            .append(",\"cast\":").append(v[2]).append(",\"targets\":").append(v[3])
                            .append(",\"targetMv\":").append(v[4]).append('}');
                    first = false;
                }
                sb.append("},\"removal\":{");
                first = true;
                for (final Map.Entry<String, double[]> e : removal.get(seat).entrySet()) {
                    final double[] v = e.getValue();
                    sb.append(first ? "" : ",").append(quote(e.getKey()))
                            .append(":{\"casts\":").append((int) v[0]).append(",\"own\":").append((int) v[1])
                            .append(",\"poor\":").append((int) v[2])
                            .append(",\"quality\":").append(Math.round(v[3] * 1000) / 1000.0).append('}');
                    first = false;
                }
                sb.append("},\"roles\":{");
                first = true;
                for (final Map.Entry<String, Set<String>> e : roles.get(seat).entrySet()) {
                    sb.append(first ? "" : ",").append(quote(e.getKey())).append(":[");
                    boolean firstTag = true;
                    for (final String tag : e.getValue()) {
                        sb.append(firstTag ? "" : ",").append(quote(tag));
                        firstTag = false;
                    }
                    sb.append(']');
                    first = false;
                }
                return sb.append('}').toString();
            } catch (final Throwable t) {
                ignored(t);
                return misplayJson(seat, false);
            }
        }
    }

    // --------------------------------------------------------------- helpers

    private static void invokeIfPresent(final Object target, final String method) {
        try {
            target.getClass().getMethod(method).invoke(target);
        } catch (final ReflectiveOperationException ignored) {
            // optional API, absent on some Forge versions
        }
    }

    private static void setFieldIfPresent(final Object target, final String field, final Object value) {
        try {
            final Field f = target.getClass().getField(field);
            f.set(target, value);
        } catch (final ReflectiveOperationException e) {
            throw new IllegalArgumentException("this Forge version does not support the requested AI mode (" + field + ")");
        }
    }

    private static String countsJson(final Map<String, Integer> counts) {
        final StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (final Map.Entry<String, Integer> e : counts.entrySet()) {
            if (!first) {
                sb.append(',');
            }
            first = false;
            sb.append(quote(e.getKey())).append(':').append(e.getValue());
        }
        return sb.append('}').toString();
    }

    private static String stackTrace(final Throwable t) {
        final StringWriter sw = new StringWriter();
        t.printStackTrace(new PrintWriter(sw));
        final String text = sw.toString();
        return text.length() > 4000 ? text.substring(0, 4000) : text;
    }

    static String quote(final String s) {
        if (s == null) {
            return "null";
        }
        final StringBuilder sb = new StringBuilder(s.length() + 2).append('"');
        for (int i = 0; i < s.length(); i++) {
            final char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.append('"').toString();
    }
}
