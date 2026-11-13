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

    /** Listens on the game's event bus and records, per seat, which cards were seen and played. */
    public static final class Tracker {
        private final Game game;
        private final Map<Integer, Integer> seatByPlayerId = new HashMap<>();
        final List<Map<String, Integer>> opening = new ArrayList<>();
        final List<Map<String, Integer>> drawn = new ArrayList<>();
        final List<Map<String, Integer>> played = new ArrayList<>();
        volatile int firstSeat = -1;
        volatile int lastTurn = 0;
        private boolean started = false;

        Tracker(final Game game, final List<RegisteredPlayer> seats) {
            this.game = game;
            for (final Player p : game.getRegisteredPlayers()) {
                seatByPlayerId.put(p.getId(), seats.indexOf(p.getRegisteredPlayer()));
            }
            for (int i = 0; i < seats.size(); i++) {
                opening.add(new TreeMap<>());
                drawn.add(new TreeMap<>());
                played.add(new TreeMap<>());
            }
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
                }
            } catch (final Throwable t) {
                System.err.println("mtgsim: tracker ignored " + t);
            }
        }

        private void onTurnBegan(final GameEventTurnBegan event) {
            lastTurn = Math.max(lastTurn, event.turnNumber());
            if (started) {
                return;
            }
            // The first turn begins after mulligans, so hands are the kept opening hands.
            started = true;
            firstSeat = seatOf(event.turnOwner());
            for (final Player p : game.getRegisteredPlayers()) {
                final Integer seat = seatByPlayerId.get(p.getId());
                if (seat == null || seat < 0) {
                    continue;
                }
                for (final Card c : p.getCardsIn(ZoneType.Hand)) {
                    opening.get(seat).merge(nameOf(c), 1, Integer::sum);
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
            count(drawn, seatOf(event.to().player()), event.card());
        }

        private void onCast(final GameEventSpellAbilityCast event) {
            final StackItemView item = event.si();
            if (item == null || item.isAbility() || item.isTrigger()) {
                return;
            }
            count(played, seatOf(item.getActivatingPlayer()), item.getSourceCard());
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
