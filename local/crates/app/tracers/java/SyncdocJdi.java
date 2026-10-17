// 싱크독 Java 실행 기록기 (SYNC-INFRA-001 9.9 · SYNC-MS-027#trace.java_setup, 카드 L34) — view_arc `VaJdi.java`를 옮겼다.
// 대상 JVM 이 붙는 디버거(JDI). 대상 코드·빌드 설정은 고치지 않는다.
//
//   java SyncdocJdi.java <포트> <범위 표> <기록 폴더> <작업 0|1>
//   대상: JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=n,address=127.0.0.1:<포트>,suspend=y
//
// - 범위 표(`syncdoc-local trace`가 쓴다, 탭으로 나뉜 줄): S 절대 경로 시작 끝 열쇠 · R 열쇠 메서드 경로 · P 패키지 ·
//   H 호스트:포트 종류 · N 열쇠 이름. 열쇠는 그래프 함수 열쇠(`파일:줄`)다
// - 진입: 그래프에 있는 메서드의 첫 위치에만 중단점(클래스가 올라올 때 건다). 모든 메서드의 진입 사건을 켜면
//   JVM 전체가 해석 모드로 돌아 Spring 시작이 몇 분이 된다 — 중단점은 그 메서드만 느려진다.
// - 끝: 기록 중인 스레드에서만 MethodExit(프로젝트 패키지)을 켜고, 그 기록이 끝나면 끈다. 스레드별 스택으로 부모를 정한다.
//   라우트 메서드가 빈 스택에서 들어오면 요청 기록 하나. 작업(1)이면 그 밖의 맨 위 메서드도 작업 기록 하나.
// - JDBC 드라이버 문(PgPreparedStatement …)의 execute* 진입은 DB 로 나간 경계 사건(@infra) — 이것도 기록 중인 스레드만.
// - 값은 필드만 읽는다(대상 메서드 toString 등을 부르지 않는다 — 부작용·교착을 막으려고). 비밀 이름의 값은 ***.
// - Maven·Gradle 처럼 JVM 이 여럿 붙어도 모두 이어 준다(프로젝트 클래스를 돌리지 않는 JVM 은 사건이 없다).
// - 기록 꼴은 다른 기록기와 같다: <기록 폴더>/<id>.json — 기록 도구가 올리고 지운다. 300개를 넘으면 오래된 것부터 지운다.

import com.sun.jdi.AbsentInformationException;
import com.sun.jdi.ArrayReference;
import com.sun.jdi.Bootstrap;
import com.sun.jdi.Field;
import com.sun.jdi.LocalVariable;
import com.sun.jdi.Location;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.PrimitiveValue;
import com.sun.jdi.ReferenceType;
import com.sun.jdi.StackFrame;
import com.sun.jdi.StringReference;
import com.sun.jdi.ThreadReference;
import com.sun.jdi.Value;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.VMDisconnectedException;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.connect.ListeningConnector;
import com.sun.jdi.event.BreakpointEvent;
import com.sun.jdi.event.ClassPrepareEvent;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.EventSet;
import com.sun.jdi.event.ExceptionEvent;
import com.sun.jdi.event.MethodEntryEvent;
import com.sun.jdi.event.MethodExitEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import com.sun.jdi.request.BreakpointRequest;
import com.sun.jdi.request.ClassPrepareRequest;
import com.sun.jdi.request.EventRequest;
import com.sun.jdi.request.EventRequestManager;
import com.sun.jdi.request.ExceptionRequest;
import com.sun.jdi.request.MethodEntryRequest;
import com.sun.jdi.request.MethodExitRequest;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

public class SyncdocJdi {
    static final int MAX_EVENTS = 20000;
    static final int MAX_FILES = 300;
    static final Pattern SECRET = Pattern.compile("pass|secret|token|api_?key|apikey|authoriz|credential|private", Pattern.CASE_INSENSITIVE);
    static final Pattern SECRET_FIELD = Pattern.compile(
        "((?:\\w*(?:pass|secret|token|api_?key|apikey|authoriz|credential|private)\\w*)['\"]?\\s*[:=]\\s*)('[^']*'|\"[^\"]*\"|[^,)}\\s]+)",
        Pattern.CASE_INSENSITIVE);
    /** JDBC 드라이버의 문 클래스: execute* 진입이 DB 로 나가는 순간 */
    static final Set<String> DRIVERS = Set.of(
        "org.postgresql.jdbc.PgPreparedStatement", "org.postgresql.jdbc.PgStatement",
        "com.mysql.cj.jdbc.ClientPreparedStatement", "com.mysql.cj.jdbc.StatementImpl",
        "org.mariadb.jdbc.ClientPreparedStatement", "org.mariadb.jdbc.Statement",
        "org.h2.jdbc.JdbcPreparedStatement", "org.h2.jdbc.JdbcStatement",
        "org.sqlite.jdbc4.JDBC4PreparedStatement", "org.sqlite.jdbc3.JDBC3Statement");

    record Span(String file, int start, int end, String id) {}
    record Route(String method, String path) {}

    static final List<Span> SPANS = new ArrayList<>();
    static final Map<String, Route> ROUTES = new HashMap<>();
    static final List<String> PACKAGES = new ArrayList<>();
    static final Map<String, String> HOSTS = new LinkedHashMap<>();
    static final Map<String, String> NAMES = new HashMap<>();
    static Path traceDir;
    static boolean jobs;
    static final AtomicInteger SEQ = new AtomicInteger();
    static final Object WRITE = new Object();

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(args[0]);
        readSpans(Path.of(args[1]));
        traceDir = Path.of(args[2]);
        jobs = args.length > 3 && args[3].equals("1");
        ListeningConnector conn = null;
        for (ListeningConnector c : Bootstrap.virtualMachineManager().listeningConnectors())
            if (c.name().equals("com.sun.jdi.SocketListen")) conn = c;
        if (conn == null) {
            System.err.println("[syncdoc] JDI 소켓 커넥터가 없습니다");
            System.exit(1);
        }
        Map<String, Connector.Argument> ca = conn.defaultArguments();
        ca.get("port").setValue(String.valueOf(port));
        if (ca.containsKey("localAddress")) ca.get("localAddress").setValue("127.0.0.1");
        try {
            conn.startListening(ca);
        } catch (Exception e) {
            System.err.println("[syncdoc] 포트 " + port + " 을 열지 못했습니다: " + e.getMessage());
            System.exit(1);
        }
        System.out.println("LISTENING " + port);
        System.out.flush();
        while (true) {
            VirtualMachine vm = conn.accept(ca);
            Thread t = new Thread(() -> attach(vm), "syncdoc-jdi-" + SEQ.incrementAndGet());
            t.setDaemon(false);
            t.start();
        }
    }

    static void readSpans(Path file) throws IOException {
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            String[] p = line.split("\t");
            switch (p[0]) {
                case "S" -> SPANS.add(new Span(p[1], Integer.parseInt(p[2]), Integer.parseInt(p[3]), p[4]));
                case "R" -> ROUTES.put(p[1], new Route(p[2], p[3]));
                case "P" -> PACKAGES.add(p[1]);
                case "H" -> HOSTS.put(p[1], p[2]);
                case "N" -> NAMES.put(p[1], p[2]);
                default -> {}
            }
        }
    }

    // ------------------------------------------------------------ JVM 하나
    static void attach(VirtualMachine vm) {
        Session s = new Session(vm);
        try {
            EventRequestManager erm = vm.eventRequestManager();
            for (String pkg : PACKAGES) {
                ClassPrepareRequest cp = erm.createClassPrepareRequest();
                cp.addClassFilter(pkg + ".*");
                cp.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                cp.enable();
            }
            for (ReferenceType t : vm.allClasses()) if (s.mine(t.name())) s.breakpoints(t);
            vm.resume();
            while (true) {
                EventSet set = vm.eventQueue().remove();
                for (Event ev : set) {
                    if (ev instanceof ClassPrepareEvent cp) s.breakpoints(cp.referenceType());
                    else if (ev instanceof BreakpointEvent bp) s.onEntry(bp.thread(), bp.location().method());
                    else if (ev instanceof MethodEntryEvent me) s.onDriver(me);
                    else if (ev instanceof MethodExitEvent mx) s.onExit(mx);
                    else if (ev instanceof ExceptionEvent ex) s.onException(ex);
                    else if (ev instanceof VMDeathEvent || ev instanceof VMDisconnectEvent) {
                        s.closeAll();
                        return;
                    }
                }
                set.resume();
            }
        } catch (VMDisconnectedException | InterruptedException e) {
            s.closeAll();
        } catch (Exception e) {
            System.err.println("[syncdoc] JVM 기록을 멈춥니다: " + e);
            s.closeAll();
            try {
                vm.dispose();
            } catch (Exception ignored) {
                // 이미 끊김
            }
        }
    }

    /** 기록 하나(요청·작업) */
    static final class Rec {
        final String id = System.currentTimeMillis() + "-" + ProcessHandle.current().pid() + "-" + SEQ.incrementAndGet();
        final String method;
        final String path;
        final String kind;
        final String startedAt = java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(java.time.ZoneOffset.UTC).format(Instant.now());
        final long start = System.nanoTime();
        final List<Map<String, Object>> events = new ArrayList<>();
        boolean truncated;
        boolean done;

        Rec(String method, String path, String kind) {
            this.method = method;
            this.path = path;
            this.kind = kind;
        }

        double now() {
            return Math.round((System.nanoTime() - start) / 10_000.0) / 100.0;
        }
    }

    /** 스택 한 칸: 그 메서드와 스레드 프레임 깊이(같은 메서드의 반복 진입·끝을 가린다) */
    record Frame(Method method, int depth, String id, Rec rec, int i, boolean root) {}

    static final class Session {
        final VirtualMachine vm;
        final EventRequestManager erm;
        final Map<Long, Deque<Frame>> stacks = new HashMap<>();
        final Map<Long, List<EventRequest>> tracking = new HashMap<>();
        final Map<Long, int[]> driverDepth = new HashMap<>();
        final Map<Long, Map<String, Object>> pendingInfra = new HashMap<>();
        final Map<Method, String> ids = new ConcurrentHashMap<>();
        final Map<String, List<Span>> bySource = new HashMap<>();
        final List<Rec> open = new ArrayList<>();

        Session(VirtualMachine vm) {
            this.vm = vm;
            this.erm = vm.eventRequestManager();
        }

        boolean mine(String cname) {
            for (String p : PACKAGES) if (cname.startsWith(p + ".")) return true;
            return false;
        }

        /** 클래스의 그래프 메서드 첫 위치에 중단점(프록시·익명 클래스·람다·생성자는 뺀다) */
        void breakpoints(ReferenceType t) {
            String cname = t.name();
            if (cname.contains("$$") || cname.matches(".*\\$\\d+.*")) return;
            try {
                for (Method m : t.methods()) {
                    if (m.isAbstract() || m.isNative() || m.isSynthetic() || m.isBridge() || m.isConstructor() || m.isStaticInitializer() || m.name().startsWith("lambda$")) continue;
                    if (idOf(m) == null) continue;
                    Location loc = m.location();
                    if (loc == null) continue;
                    BreakpointRequest br = erm.createBreakpointRequest(loc);
                    br.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                    br.enable();
                }
            } catch (Exception ignored) {
                // 아직 준비 안 된 클래스
            }
        }

        void onEntry(ThreadReference thread, Method m) {
            long tid = thread.uniqueID();
            Deque<Frame> st = stacks.computeIfAbsent(tid, k -> new ArrayDeque<>());
            int depth;
            try {
                depth = thread.frameCount();
            } catch (Exception e) {
                return;
            }
            Frame top = st.peek();
            if (top != null && top.method().equals(m) && top.depth() == depth) return; // 메서드 첫 줄로 되돌아오는 반복문
            // 이 깊이 이하의 칸은 이미 사라진 프레임(끝 사건을 못 받은 것): 닫는다
            while (top != null && top.depth() >= depth) {
                close(st.pop(), tid, null);
                top = st.peek();
            }
            String id = idOf(m);
            if (id == null) return;
            Frame parent = nearest(st);
            Rec rec;
            int parentIdx = -1;
            boolean root = false;
            if (parent == null) {
                Route r = ROUTES.get(id);
                if (r != null) rec = new Rec(r.method(), r.path(), null);
                else if (jobs) rec = new Rec("JOB", shortName(id), "job");
                else return;
                open.add(rec);
                root = true;
                track(thread);
            } else {
                rec = parent.rec();
                parentIdx = parent.i();
            }
            if (rec.events.size() >= MAX_EVENTS) {
                rec.truncated = true;
                return;
            }
            Map<String, Object> ev = new LinkedHashMap<>();
            ev.put("i", rec.events.size());
            ev.put("parent", parentIdx);
            ev.put("fn", id);
            ev.put("name", NAMES.getOrDefault(id, m.name()));
            ev.put("args", args(thread, m));
            ev.put("t0", rec.now());
            rec.events.add(ev);
            st.push(new Frame(m, depth, id, rec, (Integer) ev.get("i"), root));
        }

        /** 기록을 시작한 스레드에서만 끝(프로젝트 패키지)과 드라이버 진입·끝을 받는다 */
        void track(ThreadReference thread) {
            List<EventRequest> reqs = new ArrayList<>();
            for (String pkg : PACKAGES) {
                MethodExitRequest ex = erm.createMethodExitRequest();
                ex.addThreadFilter(thread);
                ex.addClassFilter(pkg + ".*");
                reqs.add(ex);
            }
            for (String d : DRIVERS) {
                MethodEntryRequest en = erm.createMethodEntryRequest();
                en.addThreadFilter(thread);
                en.addClassFilter(d);
                reqs.add(en);
                MethodExitRequest ex = erm.createMethodExitRequest();
                ex.addThreadFilter(thread);
                ex.addClassFilter(d);
                reqs.add(ex);
            }
            ExceptionRequest exr = erm.createExceptionRequest(null, true, true);
            exr.addThreadFilter(thread);
            reqs.add(exr);
            for (EventRequest r : reqs) {
                r.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                r.enable();
            }
            tracking.put(thread.uniqueID(), reqs);
        }

        void untrack(long tid) {
            List<EventRequest> reqs = tracking.remove(tid);
            if (reqs != null) erm.deleteEventRequests(reqs);
            driverDepth.remove(tid);
            pendingInfra.remove(tid);
        }

        /** 예외: 잡는 프레임보다 깊은 기록 칸은 예외로 빠져나간다 — 그 칸들을 닫는다(끝 사건이 오지 않을 수 있어서) */
        void onException(ExceptionEvent e) {
            long tid = e.thread().uniqueID();
            Deque<Frame> st = stacks.get(tid);
            if (st == null || st.isEmpty()) return;
            int catcher = 0; // 잡는 프레임의 깊이. 0 = 아무도 안 잡음(스레드 끝까지)
            try {
                Location c = e.catchLocation();
                List<StackFrame> frames = e.thread().frames();
                if (c != null)
                    for (int k = 0; k < frames.size(); k++)
                        if (frames.get(k).location().method().equals(c.method())) {
                            catcher = frames.size() - k;
                            break;
                        }
            } catch (Exception ignored) {
                return;
            }
            if (st.peek().depth() <= catcher) return; // 기록 칸 안에서 잡힌다
            String what = exceptionText(e.exception());
            while (!st.isEmpty() && st.peek().depth() > catcher) close(st.pop(), tid, what);
        }

        /** 칸 하나를 닫는다(끝 시각·예외). 뿌리면 기록을 쓴다 */
        void close(Frame f, long tid, String exc) {
            Map<String, Object> ev = f.rec().events.get(f.i());
            ev.putIfAbsent("t1", f.rec().now());
            if (exc != null) ev.put("exc", exc);
            if (f.root()) {
                untrack(tid);
                finish(f.rec());
            }
        }

        void onDriver(MethodEntryEvent e) {
            if (!e.method().name().startsWith("execute")) return;
            Deque<Frame> st = stacks.get(e.thread().uniqueID());
            if (st != null) driverEntry(e, st, e.thread().uniqueID());
        }

        void onExit(MethodExitEvent e) {
            Method m = e.method();
            long tid = e.thread().uniqueID();
            if (DRIVERS.contains(m.declaringType().name())) {
                if (m.name().startsWith("execute")) driverExit(tid);
                return;
            }
            Deque<Frame> st = stacks.get(tid);
            if (st == null || st.isEmpty()) return;
            Frame f = st.peek();
            if (!f.method().equals(m)) return; // 기록하지 않는 메서드의 끝
            try {
                if (e.thread().frameCount() != f.depth()) return; // 같은 메서드의 안쪽 재귀
            } catch (Exception ignored) {
                // 깊이를 못 읽으면 메서드로만
            }
            st.pop();
            Map<String, Object> ev = f.rec().events.get(f.i());
            ev.put("t1", f.rec().now());
            try {
                Value v = e.returnValue();
                if (!m.returnTypeName().equals("void")) ev.put("ret", repr(v, 0));
            } catch (Exception ignored) {
                // 예외로 빠져나간 메서드·돌려받을 수 없는 값
            }
            if (f.root()) {
                untrack(tid);
                finish(f.rec());
            }
        }

        /** 스택에서 가장 가까운 기록 칸 */
        Frame nearest(Deque<Frame> st) {
            for (Frame f : st) if (!f.rec().done) return f;
            return null;
        }

        void driverEntry(MethodEntryEvent e, Deque<Frame> st, long tid) {
            int[] depth = driverDepth.computeIfAbsent(tid, k -> new int[1]);
            if (depth[0]++ > 0) return; // executeQuery → executeWithFlags … 안쪽은 같은 한 번
            Frame parent = nearest(st);
            if (parent == null || parent.rec().events.size() >= MAX_EVENTS) return;
            Rec rec = parent.rec();
            String sql = sqlOf(e);
            if (sql != null && sql.isBlank()) return; // 연결 확인용 빈 문
            String op = sql != null ? sql : e.method().name();
            String cname = e.method().declaringType().name();
            String scheme = cname.startsWith("org.postgresql") ? "postgresql" : cname.contains("mysql") || cname.contains("mariadb") ? "mysql" : cname.startsWith("org.h2") ? "h2" : cname.startsWith("org.sqlite") ? "sqlite" : "jdbc";
            String host = null;
            for (Map.Entry<String, String> h : HOSTS.entrySet()) if (h.getValue().equals("db")) {
                host = h.getKey();
                break;
            }
            Map<String, Object> infra = new LinkedHashMap<>();
            infra.put("kind", "db");
            infra.put("target", scheme + "://" + (host != null ? host : "?"));
            infra.put("op", op.length() > 160 ? op.substring(0, 160) : op);
            Map<String, Object> ev = new LinkedHashMap<>();
            ev.put("i", rec.events.size());
            ev.put("parent", parent.i());
            ev.put("fn", "@infra");
            ev.put("name", op.length() > 60 ? op.substring(0, 60) : op);
            ev.put("infra", infra);
            ev.put("t0", rec.now());
            ev.put("__rec", rec);
            rec.events.add(ev);
            pendingInfra.put(tid, ev);
        }

        void driverExit(long tid) {
            int[] depth = driverDepth.get(tid);
            if (depth == null || depth[0] == 0) return;
            if (--depth[0] > 0) return;
            Map<String, Object> ev = pendingInfra.remove(tid);
            if (ev != null) ev.put("t1", ((Rec) ev.remove("__rec")).now());
        }

        /** 실행 중인 SQL: 첫 인자가 글자면 그것, 아니면 문 객체 필드(PgPreparedStatement.preparedQuery.query.nativeQuery.nativeSql …) */
        String sqlOf(MethodEntryEvent e) {
            try {
                var frame = e.thread().frame(0);
                List<Value> vals = frame.getArgumentValues();
                if (!vals.isEmpty() && vals.get(0) instanceof StringReference s) return oneLine(s.value());
                ObjectReference self = frame.thisObject();
                Value v = path(self, "preparedQuery", "query", "nativeQuery", "nativeSql");
                if (v == null) v = path(self, "query", "originalSql");
                if (v == null) v = path(self, "sql");
                if (v == null) v = path(self, "sqlWithParams");
                if (v instanceof StringReference s) return oneLine(s.value());
            } catch (Exception ignored) {
                // 드라이버 판마다 필드가 달라 못 읽으면 메서드 이름만
            }
            return null;
        }

        String idOf(Method m) {
            String cached = ids.get(m);
            if (cached != null) return cached.isEmpty() ? null : cached;
            String found = null;
            try {
                var loc = m.location();
                if (loc != null) {
                    String sp = loc.sourcePath().replace('\\', '/');
                    int line = loc.lineNumber();
                    List<Span> list = bySource.computeIfAbsent(sp, k -> SPANS.stream().filter(s -> s.file().endsWith("/" + k)).toList());
                    Span best = null;
                    for (Span s : list)
                        if (s.start() <= line && line <= s.end() && (best == null || s.end() - s.start() < best.end() - best.start())) best = s;
                    if (best != null) found = best.id();
                }
            } catch (AbsentInformationException ignored) {
                // 디버그 정보 없이 컴파일된 클래스
            }
            ids.put(m, found == null ? "" : found);
            return found;
        }

        Map<String, String> args(ThreadReference thread, Method m) {
            Map<String, String> out = new LinkedHashMap<>();
            try {
                List<Value> vals = thread.frame(0).getArgumentValues();
                List<String> names = new ArrayList<>();
                try {
                    for (LocalVariable lv : m.arguments()) names.add(lv.name());
                } catch (AbsentInformationException ignored) {
                    // -g 없이 컴파일: arg0 …
                }
                for (int k = 0; k < vals.size() && k < 6; k++) {
                    String name = k < names.size() ? names.get(k) : "arg" + k;
                    out.put(name, SECRET.matcher(name).find() ? "***" : repr(vals.get(k), 0));
                }
            } catch (Exception ignored) {
                // 프레임을 못 읽으면 인자 없이
            }
            return out;
        }

        void finish(Rec rec) {
            if (rec.done) return;
            rec.done = true;
            open.remove(rec);
            if (rec.kind != null && rec.events.size() < 2 && rec.now() < 50) return; // 아주 작은 작업
            // JDI는 HTTP 상태를 못 읽는다 — 맨 위 메서드가 예외로 빠져나갔으면 500, 아니면 200
            Object exc = rec.events.isEmpty() ? null : rec.events.get(0).get("exc");
            write(rec, exc != null ? 500 : 200);
        }

        void closeAll() {
            for (long tid : new ArrayList<>(tracking.keySet()))
                try {
                    untrack(tid);
                } catch (Exception ignored) {
                    // 끊긴 JVM
                }
            for (Rec rec : new ArrayList<>(open)) {
                double end = rec.now();
                for (Map<String, Object> ev : rec.events) ev.putIfAbsent("t1", end);
                finish(rec);
            }
        }
    }

    // ------------------------------------------------------------ 값
    static Value path(ObjectReference o, String... fields) {
        Value cur = o;
        for (String f : fields) {
            if (!(cur instanceof ObjectReference obj)) return null;
            Field fld = obj.referenceType().fieldByName(f);
            if (fld == null) return null;
            cur = obj.getValue(fld);
        }
        return cur;
    }

    static String oneLine(String s) {
        String t = s.replaceAll("\\s+", " ").trim();
        return t.length() > 100 ? t.substring(0, 100) : t;
    }

    static final Set<String> BOXES = Set.of("java.lang.Integer", "java.lang.Long", "java.lang.Short", "java.lang.Byte", "java.lang.Double",
        "java.lang.Float", "java.lang.Boolean", "java.lang.Character");

    /** 필드만 읽는 짧은 표현(160자). 대상 메서드는 부르지 않는다 */
    static String repr(Value v, int depth) {
        String text = reprRaw(v, depth);
        return depth == 0 ? SECRET_FIELD.matcher(text).replaceAll("$1***") : text;
    }

    static String reprRaw(Value v, int depth) {
        try {
            if (v == null) return "null";
            if (v instanceof StringReference s) {
                String str = s.value();
                return quote(str.length() > 60 ? str.substring(0, 59) + "…" : str);
            }
            if (v instanceof PrimitiveValue p) return p.toString();
            if (v instanceof ArrayReference a) return simple(a.referenceType().name()).replace("[]", "") + "[" + a.length() + "]";
            if (v instanceof ObjectReference o) {
                ReferenceType t = o.referenceType();
                String name = t.name();
                if (BOXES.contains(name)) return reprRaw(o.getValue(t.fieldByName("value")), depth);
                if (name.equals("java.util.Optional")) {
                    Value inner = o.getValue(t.fieldByName("value"));
                    return inner == null ? "Optional.empty" : "Optional[" + reprRaw(inner, depth + 1) + "]";
                }
                String simple = simple(name);
                if (depth > 0 || name.startsWith("java.") || name.startsWith("jakarta.") || name.startsWith("org.springframework.")) return simple + "{…}";
                StringBuilder sb = new StringBuilder(simple).append("{");
                int n = 0;
                for (Field f : t.allFields()) {
                    if (f.isStatic()) continue;
                    if (n++ == 4) {
                        sb.append(", …");
                        break;
                    }
                    if (n > 1) sb.append(", ");
                    sb.append(f.name()).append(": ").append(SECRET.matcher(f.name()).find() ? "***" : reprRaw(o.getValue(f), depth + 1));
                }
                String out = sb.append("}").toString();
                return out.length() > 160 ? out.substring(0, 159) + "…" : out;
            }
            return v.toString();
        } catch (Exception e) {
            return "?";
        }
    }

    /** 예외 이름과 메시지(detailMessage 필드, 메서드는 부르지 않는다) */
    static String exceptionText(ObjectReference ex) {
        String name = simple(ex.referenceType().name());
        try {
            for (ReferenceType t = ex.referenceType(); t != null; t = t instanceof com.sun.jdi.ClassType ct ? ct.superclass() : null) {
                Field f = t.fieldByName("detailMessage");
                if (f != null) {
                    Value v = ex.getValue(f);
                    if (v instanceof StringReference s) return name + ": " + (s.value().length() > 120 ? s.value().substring(0, 120) : s.value());
                    break;
                }
            }
        } catch (Exception ignored) {
            // 이름만
        }
        return name;
    }

    static String simple(String name) {
        String s = name.substring(name.lastIndexOf('.') + 1);
        return s.substring(s.lastIndexOf('$') + 1);
    }

    static String shortName(String id) {
        return NAMES.getOrDefault(id, id);
    }

    // ------------------------------------------------------------ 쓰기
    static void write(Rec rec, Integer status) {
        double ms = rec.now();
        for (Map<String, Object> ev : rec.events) {
            ev.putIfAbsent("t1", ms);
            ev.remove("__rec");
        }
        String root = null;
        String error = null;
        for (Map<String, Object> ev : rec.events)
            if ((Integer) ev.get("parent") == -1 && !"@infra".equals(ev.get("fn"))) {
                root = (String) ev.get("fn");
                error = (String) ev.get("exc");
                break;
            }
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("version", 1);
        if (rec.kind != null) record.put("kind", rec.kind);
        record.put("id", rec.id);
        record.put("method", rec.method);
        record.put("path", rec.path);
        record.put("query", "");
        record.put("status", status);
        record.put("error", error);
        record.put("startedAt", rec.startedAt);
        record.put("ms", ms);
        record.put("truncated", rec.truncated);
        record.put("events", rec.events);
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("id", rec.id);
        if (rec.kind != null) summary.put("kind", rec.kind);
        summary.put("method", rec.method);
        summary.put("path", rec.path);
        summary.put("status", status);
        summary.put("error", error);
        summary.put("startedAt", rec.startedAt);
        summary.put("ms", ms);
        summary.put("calls", rec.events.size());
        summary.put("root", root);
        synchronized (WRITE) {
            try {
                Files.createDirectories(traceDir);
                Path tmp = traceDir.resolve("." + rec.id + ".tmp");
                Files.writeString(tmp, json(record), StandardCharsets.UTF_8);
                Files.move(tmp, traceDir.resolve(rec.id + ".json"), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
                Files.writeString(traceDir.resolve("index.jsonl"), json(summary) + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                prune();
            } catch (IOException e) {
                System.err.println("[syncdoc] 기록을 쓰지 못했습니다: " + e.getMessage());
            }
        }
    }

    static void prune() throws IOException {
        try (var files = Files.list(traceDir)) {
            List<Path> list = files.filter(p -> p.getFileName().toString().endsWith(".json")).sorted().toList();
            for (int k = 0; k < list.size() - MAX_FILES; k++) Files.deleteIfExists(list.get(k));
        }
    }

    static String json(Object o) {
        StringBuilder sb = new StringBuilder();
        json(o, sb);
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    static void json(Object o, StringBuilder sb) {
        if (o == null) sb.append("null");
        else if (o instanceof String s) sb.append(quote(s));
        else if (o instanceof Number || o instanceof Boolean) sb.append(o);
        else if (o instanceof Map<?, ?> m) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if (!first) sb.append(',');
                first = false;
                sb.append(quote(String.valueOf(e.getKey()))).append(':');
                json(e.getValue(), sb);
            }
            sb.append('}');
        } else if (o instanceof List<?> l) {
            sb.append('[');
            for (int k = 0; k < l.size(); k++) {
                if (k > 0) sb.append(',');
                json(l.get(k), sb);
            }
            sb.append(']');
        } else sb.append(quote(o.toString()));
    }

    static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
                }
            }
        }
        return sb.append('"').toString();
    }
}
