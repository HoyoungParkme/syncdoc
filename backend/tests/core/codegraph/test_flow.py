"""SYNC-MS-024 테스트 관점 — 흐름 키(카드 CC~CE). 순수 함수라 DB를 안 쓴다."""

from pathlib import Path

from app.core.codegraph import flow, steps


def _write(root: Path, files: dict[str, str | bytes]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))


def _fn(file: str, line: int, name: str) -> dict:
    return {"key": f"{file}:{line}", "name": name, "qual": name, "file": file, "line": line,
            "end": None, "item": None, "ms": None}  # fmt: skip


# ── files ──
def test_files_lists_code_skips_dirs_and_tests_sorted(tmp_path: Path) -> None:
    _write(tmp_path, {
        "b.py": "x = 1\n",
        "a/c.ts": "let a\nlet b",
        "node_modules/x/i.js": "1",
        ".git/hooks/h.py": "1",
        "tests/test_x.py": "1",
        "src/x.test.ts": "1",
        "main.go": "",
        "README.md": "# r",
    })  # fmt: skip
    got = flow.files(tmp_path)
    assert got == [
        {"path": "a/c.ts", "lang": "typescript", "loc": 2},
        {"path": "b.py", "lang": "python", "loc": 1},
        {"path": "main.go", "lang": "go", "loc": 0},
    ]


# ── steps ──
PY = """\
from fastapi import Depends


def helper(x):
    return x


def dep():
    pass


@decorated
def handler(a=Depends(dep)):
    v = helper(helper(1))
    if v:
        raise ValueError("나쁜 값 " * 30)
    cb = lambda: helper(2)

    def inner():
        return helper(3)

    return (v)
"""


def _graph_py(tmp_path: Path) -> dict:
    _write(tmp_path, {"app/h.py": PY})
    f = "app/h.py"
    funcs = [_fn(f, 4, "helper"), _fn(f, 8, "dep"), _fn(f, 12, "handler")]
    return {"functions": funcs, "calls": [[f"{f}:12", f"{f}:4", "graphify"]]}


def test_steps_python_order_depends_deferred_and_labels(tmp_path: Path) -> None:
    g = _graph_py(tmp_path)
    steps.steps(tmp_path, g)
    h = g["functions"][2]["steps"]
    assert h[0] == {"k": "call", "line": 13, "label": "Depends(dep)", "to": "app/h.py:8",
                    "inferred": True}  # fmt: skip
    assert [(s["k"], s["label"]) for s in h[1:]] == [
        ("call", "helper"),  # 안쪽 helper(1)이 먼저 끝난다
        ("call", "helper"),
        ("call", "ValueError"),
        ("raise", "raise " + ('ValueError("나쁜 값 " * 30)')),
        ("call", "helper"),  # lambda 안 — deferred
        ("call", "helper"),  # inner 안 — deferred, 그 안 return은 없다
        ("return", "return v"),  # 괄호를 벗긴다
    ]
    assert h[1]["to"] == "app/h.py:4" and "inferred" not in h[1]
    assert h[5].get("deferred") and h[6].get("deferred")
    assert "to" not in h[3]  # 그래프에 없는 이름


def test_steps_label_cut_at_70_chars(tmp_path: Path) -> None:
    long = "a" * 80
    _write(tmp_path, {"m.py": f"def f():\n    return {long}\n"})
    g = {"functions": [_fn("m.py", 1, "f")], "calls": []}
    steps.steps(tmp_path, g)
    label = g["functions"][0]["steps"][0]["label"]
    assert len(label) == 70 and label.endswith("…")


def test_steps_to_needs_unique_name_and_bare_call_for_guess(tmp_path: Path) -> None:
    _write(tmp_path, {
        "a.py": "def go(x):\n    x.run()\n    run()\n    split()\n",
        "b.py": "def run():\n    pass\n",
        "c.py": "def run():\n    pass\n",
        "d.ts": "export function split() {}\n",
    })  # fmt: skip
    funcs = [_fn("a.py", 1, "go"), _fn("b.py", 1, "run"), _fn("c.py", 1, "run"),
             _fn("d.ts", 1, "split")]  # fmt: skip
    g = {"functions": funcs, "calls": [["a.py:1", "b.py:1", "graphify"]]}
    steps.steps(tmp_path, g)
    s = g["functions"][0]["steps"]
    assert s[0]["to"] == "b.py:1" and s[1]["to"] == "b.py:1"  # 나가는 선의 이름 하나
    assert "to" not in s[2]  # 다른 언어의 split은 짐작하지 않는다


def test_steps_method_call_is_not_guessed(tmp_path: Path) -> None:
    _write(tmp_path, {"a.py": "def go(x):\n    x.only()\n", "b.py": "def only():\n    pass\n"})
    g = {"functions": [_fn("a.py", 1, "go"), _fn("b.py", 1, "only")], "calls": []}
    steps.steps(tmp_path, g)
    assert "to" not in g["functions"][0]["steps"][0]


TS = """\
import { api } from './client'

export const load = async (id: string) => {
  const r = await api.get(`/x/${id}`)
  items.map((i) => fmt(i))
  return r
}

export function fmt(v) {
  if (!v) throw new Error('없음')
  return <Card v={v} />
}
"""


def test_steps_typescript_await_arrow_jsx_throw(tmp_path: Path) -> None:
    _write(tmp_path, {"web/p.tsx": TS})
    f = "web/p.tsx"
    g = {"functions": [_fn(f, 3, "load"), _fn(f, 9, "fmt")],
         "calls": [[f"{f}:3", f"{f}:9", "enrich"]]}  # fmt: skip
    steps.steps(tmp_path, g)
    load, fmt = g["functions"][0]["steps"], g["functions"][1]["steps"]
    assert [(s["k"], s["label"]) for s in load] == [
        ("call", "api.get"), ("call", "fmt"), ("call", "items.map"), ("return", "return r"),
    ]  # fmt: skip
    assert load[0].get("awaited") and load[1].get("deferred") and load[1]["to"] == f"{f}:9"
    assert [(s["k"], s["label"]) for s in fmt] == [
        ("raise", "throw new Error('없음')"), ("call", "<Card>"), ("return", "return <Card v={v} />"),
    ]  # fmt: skip


RS = """\
pub fn helper(x: i32) -> i32 {
    x
}

/// 문서
#[inline]
pub async fn run(db: &Db) -> i32 {
    let v = helper(Self::make(1));
    db.save(v).await;
    let c = |y| helper(y);
    return v;
}
"""


def test_steps_rust_order_await_closure_return(tmp_path: Path) -> None:
    _write(tmp_path, {"src/lib.rs": RS})
    f = "src/lib.rs"
    g = {"functions": [_fn(f, 1, "helper"), _fn(f, 7, "run")],
         "calls": [[f"{f}:7", f"{f}:1", "enrich"]]}  # fmt: skip
    steps.steps(tmp_path, g)
    run = g["functions"][1]["steps"]
    assert [(s["k"], s["label"]) for s in run] == [
        ("call", "Self::make"), ("call", "helper"), ("call", "db.save"), ("call", "helper"),
        ("return", "return v"),
    ]  # fmt: skip
    assert run[1]["to"] == f"{f}:1" and run[2].get("awaited") and run[3].get("deferred")


def test_steps_bad_file_gives_empty(tmp_path: Path) -> None:
    _write(tmp_path, {"x.py": "def f(:\n", "y.py": b"\xff\xfe def g(): pass\n"})
    g = {"functions": [_fn("x.py", 1, "f"), _fn("y.py", 1, "g"), _fn("z.go", 1, "h")],
         "calls": []}  # fmt: skip
    steps.steps(tmp_path, g)
    assert all(f["steps"] == [] for f in g["functions"])


def test_steps_cap_at_200(tmp_path: Path) -> None:
    body = "".join("    g()\n" for _ in range(250))
    _write(tmp_path, {"m.py": f"def f():\n{body}"})
    g = {"functions": [_fn("m.py", 1, "f")], "calls": []}
    steps.steps(tmp_path, g)
    assert len(g["functions"][0]["steps"]) == 200


# ── extend ──
def test_extend_adds_keys_and_drops_unresolved_calls(tmp_path: Path) -> None:
    g = _graph_py(tmp_path)
    flow.extend(tmp_path, g)
    assert set(g) >= {"files", "units", "http", "infra"}
    for f in g["functions"]:
        assert "steps" in f and "route" in f
        assert all(s["k"] != "call" or "to" in s or "infra" in s for s in f["steps"])
    h = g["functions"][2]["steps"]
    assert ("raise", 16) in [(s["k"], s["line"]) for s in h]  # 반환·예외는 남는다
    assert all(s.get("label") != "ValueError" for s in h)  # 대상 없는 호출은 빠진다


def test_extend_survives_a_failing_step(tmp_path: Path, monkeypatch) -> None:
    g = _graph_py(tmp_path)

    def boom(*_a):
        raise RuntimeError("x")

    monkeypatch.setattr(steps, "steps", boom)
    flow.extend(tmp_path, g)
    assert g["files"] and all(f["steps"] == [] for f in g["functions"])


# ── routes ──
from app.core.codegraph import routes  # noqa: E402


def _routes_of(tmp_path: Path, files: dict[str, str], funcs: list[dict]) -> dict[str, dict]:
    _write(tmp_path, files)
    g = {"functions": funcs, "calls": [], "files": [{"path": p} for p in files]}
    routes.routes(tmp_path, g)
    return {f["qual"]: f["route"] for f in g["functions"]}


def test_routes_python_fastapi_flask_blueprint_include(tmp_path: Path) -> None:
    files = {
        "app/main.py": "from app.api import items as items_mod\n"
                       "app.include_router(items_mod.router, prefix='/v1')\n",
        "app/api/items.py": "router = APIRouter(prefix='/items')\n\n"
                            "@router.get('/{item_id}/')\ndef read(item_id):\n    pass\n\n"
                            "@router.api_route('', methods=['POST'])\ndef make():\n    pass\n",
        "web/f.py": "bp = Blueprint('x', __name__, url_prefix='/bp')\n\n"
                    "@bp.route('/u/<int:uid>', methods=['PUT'])\ndef upd(uid):\n    pass\n\n"
                    "@app.get('/plain')\ndef plain():\n    pass\n",
    }  # fmt: skip
    funcs = [_fn("app/api/items.py", 3, "read"), _fn("app/api/items.py", 7, "make"),
             _fn("web/f.py", 4, "upd"), _fn("web/f.py", 8, "plain")]  # fmt: skip
    got = _routes_of(tmp_path, files, funcs)
    assert got["read"] == {"method": "GET", "path": "/v1/items/{item_id}"}
    assert got["make"] == {"method": "POST", "path": "/v1/items"}
    assert got["upd"] == {"method": "PUT", "path": "/bp/u/{uid}"}
    assert got["plain"] == {"method": "GET", "path": "/plain"}


def test_routes_typescript_express_nest_next(tmp_path: Path) -> None:
    files = {
        "srv/app.ts": "const app = express()\nfunction show(req, res) {}\n"
                      "app.get('/users/:id', auth, show)\napp.post('/users', (req, res) => {})\n",
        "srv/c.ts": "@Controller('cats')\nclass CatsController {\n  @Get(':id')\n  one() {}\n}\n",
        "srv/d.ts": "@Controller('dogs')\nexport class DogsController {\n  @Post()\n  make() {}\n}\n",
        "web/app/api/items/[id]/route.ts": "export async function GET(req) {}\n",
    }  # fmt: skip
    funcs = [_fn("srv/app.ts", 2, "show"), _fn("srv/app.ts", 4, "anon"),
             _fn("srv/c.ts", 4, "one"), _fn("srv/d.ts", 4, "make"),
             _fn("web/app/api/items/[id]/route.ts", 1, "GET")]  # fmt: skip
    got = _routes_of(tmp_path, files, funcs)
    assert got["show"] == {"method": "GET", "path": "/users/{id}"}
    assert got["anon"] == {"method": "POST", "path": "/users"}  # 인라인 핸들러
    assert got["one"] == {"method": "GET", "path": "/cats/{id}"}
    assert got["make"] == {"method": "POST", "path": "/dogs"}  # export class
    assert got["GET"] == {"method": "GET", "path": "/api/items/{id}"}


def test_routes_rust_axum_chain_and_actix(tmp_path: Path) -> None:
    files = {
        "src/lib.rs": 'fn app() -> Router {\n    Router::new()\n'
                      '        .route("/api/x", get(list).post(handlers::make))\n}\n'
                      "async fn list() {}\nasync fn make() {}\n\n"
                      '#[get("/hi/")]\nasync fn hi() {}\n',
    }  # fmt: skip
    funcs = [_fn("src/lib.rs", 5, "list"), _fn("src/lib.rs", 6, "make"), _fn("src/lib.rs", 9, "hi")]
    got = _routes_of(tmp_path, files, funcs)
    assert got["list"] == {"method": "GET", "path": "/api/x"}
    assert got["make"] == {"method": "POST", "path": "/api/x"}
    assert got["hi"] == {"method": "GET", "path": "/hi"}


# ── http_links ──
def _http(tmp_path: Path, front: str, extra: list[dict] | None = None) -> list[dict]:
    _write(tmp_path, {"web/p.tsx": front})
    funcs = [_fn("web/p.tsx", 1, "load")] + (extra or [])
    funcs_routes = [
        ("api/a.py:1", "GET", "/api/projects/{code}/flow"),
        ("api/a.py:2", "POST", "/api/projects/{code}/traces"),
        ("api/a.py:3", "GET", "/api/projects/list"),
        ("api/a.py:4", "GET", "/api/projects/{code}"),
    ]
    for key, m, p in funcs_routes:
        f = _fn("api/a.py", int(key.rsplit(":", 1)[1]), "r")
        f["route"] = {"method": m, "path": p}
        funcs.append(f)
    return routes.http_links(tmp_path, {"functions": funcs, "calls": [], "units": []})


def test_http_template_exact_and_fetch_method(tmp_path: Path) -> None:
    got = _http(tmp_path, "export async function load(code) {\n"
                          "  await api.get(`/api/projects/${code}/flow?x=1`)\n"
                          "  await fetch(`/api/projects/${code}/traces`, { method: 'POST' })\n}\n")  # fmt: skip
    assert got == [
        {"from": "web/p.tsx:1", "to": "api/a.py:1", "inferred": False},
        {"from": "web/p.tsx:1", "to": "api/a.py:2", "inferred": False},
    ]


def test_http_literal_beats_param_and_wildcard_on_literal_is_guess(tmp_path: Path) -> None:
    got = _http(tmp_path, "export function load(x) {\n"
                          "  api.get('/api/projects/list')\n  api.get(`/api/${x}/list`)\n}\n")  # fmt: skip
    assert {"from": "web/p.tsx:1", "to": "api/a.py:3", "inferred": False} in got
    assert {"from": "web/p.tsx:1", "to": "api/a.py:4", "inferred": False} not in got


def test_http_suffix_match_and_router_registration(tmp_path: Path) -> None:
    _write(tmp_path, {"web/p.tsx": "const app = express()\nexport function load() {\n"
                                   "  app.get('/projects/{c}/flow', h)\n"
                                   "  api.get('/projects/a/flow')\n}\n"})  # fmt: skip
    f = _fn("api/a.py", 1, "r")
    f["route"] = {"method": "GET", "path": "/api/projects/{code}/flow"}
    g = {"functions": [_fn("web/p.tsx", 2, "load"), f], "calls": [], "units": []}
    # 라우트 등록(app.get)은 요청이 아니고, api.get은 끝맞춤이라 짐작이다
    assert routes.http_links(tmp_path, g) == [
        {"from": "web/p.tsx:2", "to": "api/a.py:1", "inferred": True}
    ]
    _write(tmp_path, {"web/p.tsx": "const app = express()\nexport function load() {\n"
                                   "  app.get('/api/projects/{c}/flow', h)\n}\n"})  # fmt: skip
    assert routes.http_links(tmp_path, g) == []


def test_http_ignores_non_front_files(tmp_path: Path) -> None:
    _write(tmp_path, {"srv/x.ts": "export function load() {\n  api.get('/api/projects/list')\n}\n"})
    f = _fn("api/a.py", 3, "r")
    f["route"] = {"method": "GET", "path": "/api/projects/list"}
    g = {"functions": [_fn("srv/x.ts", 1, "load"), f], "calls": [], "units": []}
    assert routes.http_links(tmp_path, g) == []
    g["units"] = [{"kind": "web", "dir": "srv"}]
    assert routes.http_links(tmp_path, g)[0]["to"] == "api/a.py:3"


# ── units ──
from app.core.codegraph import infra  # noqa: E402


def test_units_node_python_rust(tmp_path: Path) -> None:
    _write(tmp_path, {
        "api/package.json": '{"dependencies": {"express": "4"}, "scripts": {"dev": "tsx w --port 4100"}}',
        "api/tsconfig.json": "{}",
        "web/package.json": '{"devDependencies": {"vite": "5"}, "dependencies": {"react": "18"},'
                            ' "scripts": {"dev": "vite"}}',
        "site/package.json": '{"dependencies": {"next": "15"}, "scripts": {"start": "next start"}}',
        "broken/package.json": "{nope",
        "srv/pyproject.toml": "[project]\nname='x'\n",
        "srv/uv.lock": "",
        "srv/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "fl/requirements.txt": "flask\n",
        "fl/web.py": "server = Flask(__name__)\n",
        "dj/manage.py": "",
        "wk/requirements.txt": "celery\n",
        "wk/tasks.py": "celery_app = Celery('t')\n",
        "rs/Cargo.toml": '[package]\nname = "svc"\n\n[dependencies]\naxum = "0.8"\n',
        "ws/Cargo.toml": "[workspace]\nmembers = []\n",
        "a/b/c/d/package.json": '{"dependencies": {"express": "4"}}',
    })  # fmt: skip
    got = {u["dir"]: u for u in infra.units(tmp_path, {"functions": []})}
    assert got["api"] == {"name": "api", "kind": "server", "dir": "api", "lang": "typescript",
                          "framework": "Express", "command": "npm run dev", "port": 4100}  # fmt: skip
    assert (got["web"]["kind"], got["web"]["framework"], got["web"]["port"]) == (
        "web",
        "Vite",
        5173,
    )
    assert (got["site"]["framework"], got["site"]["command"], got["site"]["port"]) == (
        "Next.js", "npm start", 3000)  # fmt: skip
    assert got["srv"]["command"] == "uv run uvicorn app.main:app --port 8000"
    assert got["fl"]["command"] == "flask --app web run --port 5000"
    assert got["dj"]["framework"] == "Django" and got["dj"]["port"] == 8000
    assert (got["wk"]["kind"], got["wk"]["command"]) == ("job", "celery -A tasks worker")
    assert got["rs"]["command"] == "cargo run -p svc" and got["rs"]["lang"] == "rust"
    assert "broken" not in got and "ws" not in got and "a/b/c/d" not in got
    assert [u["dir"] for u in infra.units(tmp_path, {"functions": []})] == sorted(got)


# ── infra ──
def _infra(tmp_path: Path, files: dict[str, str], funcs: list[dict], units: list | None = None):
    _write(tmp_path, files)
    g = {"functions": funcs, "calls": [], "units": units or [], "http": []}
    from app.core.codegraph import steps as st

    st.steps(tmp_path, g)
    infra.infra(tmp_path, g)
    return g


def test_infra_code_calls_mark_steps(tmp_path: Path) -> None:
    files = {
        "app/db.py": "from sqlalchemy import select\nfrom sqlalchemy.orm import Session\n"
                     "def save(s: Session):\n    q = select(1)\n    s.execute(q)\n",
        "app/llm.py": "from openai import OpenAI\nclass Bot:\n    def __init__(self):\n"
                      "        self.client = OpenAI()\n    def ask(self):\n"
                      "        return self.client.chat.completions.create(model='x')\n",
        "srv/p.ts": "import { PrismaClient } from '@prisma/client'\nconst prisma = new PrismaClient()\n"
                    "export async function list() {\n  return prisma.user.findMany()\n}\n",
        "core/src/q.rs": "use sqlx::PgPool;\npub async fn one(pool: &PgPool) {\n"
                         "    sqlx::query(\"x\").fetch_one(pool).await;\n}\n",
        "scripts/seed.py": "import redis\ndef go():\n    redis.Redis().set('a', 1)\n",
    }  # fmt: skip
    funcs = [_fn("app/db.py", 3, "save"), _fn("app/llm.py", 5, "ask"), _fn("srv/p.ts", 3, "list"),
             _fn("core/src/q.rs", 2, "one"), _fn("scripts/seed.py", 2, "go")]  # fmt: skip
    g = _infra(tmp_path, files, funcs)
    marks = {f["name"]: [(s["label"], s.get("infra")) for s in f["steps"]] for f in g["functions"]}
    assert ("s.execute", "infra:db") in marks["save"] and ("select", None) in marks["save"]
    assert ("self.client.chat.completions.create", "infra:openai") in marks["ask"]
    assert ("prisma.user.findMany", "infra:db") in marks["list"]
    assert ('sqlx::query("x").fetch_one', "infra:db") in marks["one"]
    assert all(m is None for _, m in marks["go"])  # 스크립트는 앱 코드가 아니다
    ids = [n["id"] for n in g["infra"]["nodes"]]
    assert ids == ["infra:backend", "infra:db", "infra:openai"]
    db = next(n for n in g["infra"]["nodes"] if n["id"] == "infra:db")
    assert db["evidence"][0] == "코드: sqlalchemy, @prisma/client, sqlx — app/db.py 외 2개 파일"


def test_infra_deps_compose_config_host_only(tmp_path: Path) -> None:
    files = {
        "package.json": '{"dependencies": {"express": "4", "ioredis": "5"}}',
        "web/package.json": '{"dependencies": {"react": "18", "pg": "8"}}',
        "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    ports:\n"
                              "      - \"15432:5432\"\n  cache:\n    image: redis:7\n",
        ".env.example": "DATABASE_URL=postgresql://user:secret@localhost:15432/app\n"
                        "REDIS_HOST=your-redis-host\n",
        "app/config.py": "MONGO = 'mongodb://admin:pw@mongo.example.org:27017/x'\n",
    }  # fmt: skip
    g = _infra(tmp_path, files, [])
    nodes = {n["id"]: n for n in g["infra"]["nodes"]}
    assert (
        nodes["infra:db"]["where"] == "container" and nodes["infra:db"]["host"] == "localhost:15432"
    )
    assert nodes["infra:redis"]["evidence"][0] == "의존성: ioredis — package.json"
    assert "infra:mongo" not in nodes  # example.org는 자리 표시
    text = repr(g["infra"])
    assert "secret" not in text and "user:" not in text  # 비밀번호가 남지 않는다
    assert not any("pg —" in e for n in nodes.values() for e in n["evidence"])  # 화면 전용 의존성


def test_infra_links_split_by_server_dir(tmp_path: Path) -> None:
    files = {
        "a/db.py": "import psycopg\ndef q(c: psycopg.Connection):\n    c.execute('x')\n",
        "b/h.py": "import httpx\ndef g():\n    httpx.get('https://x')\n",
    }  # fmt: skip
    units = [{"name": "a", "kind": "server", "dir": "a", "framework": "FastAPI", "port": 8000},
             {"name": "b", "kind": "server", "dir": "b", "framework": "Flask", "port": None}]  # fmt: skip
    g = _infra(tmp_path, files, [_fn("a/db.py", 2, "q"), _fn("b/h.py", 2, "g")], units)
    links = [(link["from"], link["to"]) for link in g["infra"]["links"]]
    assert ("infra:server:a", "infra:db") in links and ("infra:server:b", "infra:db") not in links
    assert ("infra:server:b", "infra:http") in links and (
        "infra:server:a",
        "infra:http",
    ) not in links
    servers = [n for n in g["infra"]["nodes"] if n["kind"] == "backend"]
    assert servers[0]["host"] == "localhost:8000" and servers[1]["host"] is None
