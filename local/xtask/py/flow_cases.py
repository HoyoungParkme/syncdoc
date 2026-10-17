"""흐름 사례 — 파이썬 판 흐름 시험(`backend/tests/core/codegraph/test_flow.py`)의 입력을 그대로 모은다(카드 L22~L24).

`codegraph_golden.py`가 사례마다 파일을 임시 자리에 쓰고 파이썬 판 흐름 함수를 돌려 답을 얼린다. Rust 시험
(`crates/codegraph/tests/flow_cases.rs`)이 같은 파일·같은 그래프로 같은 답을 내는지 본다.
파일 값이 `{"hex": …}`면 바이트다.
"""

from __future__ import annotations

import copy
import importlib.util
import tempfile
from pathlib import Path

from app.core.codegraph import flow, infra, routes, steps

_TEST = Path(__file__).resolve().parents[3] / "backend" / "tests" / "core" / "codegraph" / "test_flow.py"
_spec = importlib.util.spec_from_file_location("test_flow", _TEST)
T = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(T)  # type: ignore[union-attr]
_fn = T._fn


def _http_routes(front_fn: dict) -> list[dict]:
    funcs = [front_fn]
    for key, m, p in [
        ("api/a.py:1", "GET", "/api/projects/{code}/flow"),
        ("api/a.py:2", "POST", "/api/projects/{code}/traces"),
        ("api/a.py:3", "GET", "/api/projects/list"),
        ("api/a.py:4", "GET", "/api/projects/{code}"),
    ]:
        f = _fn("api/a.py", int(key.rsplit(":", 1)[1]), "r")
        f["route"] = {"method": m, "path": p}
        funcs.append(f)
    return funcs


def _routed(file: str, line: int, method: str, path: str) -> dict:
    f = _fn(file, line, "r")
    f["route"] = {"method": method, "path": path}
    return f


def cases() -> list[dict]:
    """[{name, op, files, graph}] — op는 files·steps·extend·routes·http·units·infra(steps 뒤)."""
    py = "app/h.py"
    ts = "web/p.tsx"
    rs = "src/lib.rs"
    items = (
        "router = APIRouter(prefix='/items')\n\n@router.get('/{item_id}/')\ndef read(item_id):\n"
        "    pass\n\n@router.api_route('', methods=['POST'])\ndef make():\n    pass\n"
    )
    out = [
        {"name": "files", "op": "files", "graph": {},
         "files": {"b.py": "x = 1\n", "a/c.ts": "let a\nlet b", "node_modules/x/i.js": "1",
                   ".hidden/hooks/h.py": "1", "tests/test_x.py": "1", "src/x.test.ts": "1",
                   "main.go": "", "README.md": "# r"}},
        {"name": "steps_py", "op": "steps", "files": {py: T.PY},
         "graph": {"functions": [_fn(py, 4, "helper"), _fn(py, 8, "dep"), _fn(py, 12, "handler")],
                   "calls": [[f"{py}:12", f"{py}:4", "graphify"]]}},
        {"name": "steps_label_cut", "op": "steps",
         "files": {"m.py": "def f():\n    return " + "a" * 80 + "\n",
                   "k.py": "def g():\n    return '" + "한글" * 50 + "'\n"},
         "graph": {"functions": [_fn("m.py", 1, "f"), _fn("k.py", 1, "g")], "calls": []}},
        {"name": "steps_unique_name", "op": "steps",
         "files": {"a.py": "def go(x):\n    x.run()\n    run()\n    split()\n",
                   "b.py": "def run():\n    pass\n", "c.py": "def run():\n    pass\n",
                   "d.ts": "export function split() {}\n"},
         "graph": {"functions": [_fn("a.py", 1, "go"), _fn("b.py", 1, "run"), _fn("c.py", 1, "run"),
                                 _fn("d.ts", 1, "split")],
                   "calls": [["a.py:1", "b.py:1", "graphify"]]}},
        {"name": "steps_method_not_guessed", "op": "steps",
         "files": {"a.py": "def go(x):\n    x.only()\n", "b.py": "def only():\n    pass\n"},
         "graph": {"functions": [_fn("a.py", 1, "go"), _fn("b.py", 1, "only")], "calls": []}},
        {"name": "steps_ts", "op": "steps", "files": {ts: T.TS},
         "graph": {"functions": [_fn(ts, 3, "load"), _fn(ts, 9, "fmt")],
                   "calls": [[f"{ts}:3", f"{ts}:9", "enrich"]]}},
        {"name": "steps_rs", "op": "steps", "files": {rs: T.RS},
         "graph": {"functions": [_fn(rs, 1, "helper"), _fn(rs, 7, "run")],
                   "calls": [[f"{rs}:7", f"{rs}:1", "enrich"]]}},
        {"name": "steps_bad_file", "op": "steps",
         "files": {"x.py": "def f(:\n", "y.py": {"hex": b"\xff\xfe def g(): pass\n".hex()},
                   "w.py": "\ufeffdef h():\n    k()\n"},
         "graph": {"functions": [_fn("x.py", 1, "f"), _fn("y.py", 1, "g"), _fn("z.go", 1, "h"),
                                 _fn("w.py", 1, "h")], "calls": []}},
        {"name": "steps_cap", "op": "steps",
         "files": {"m.py": "def f():\n" + "".join("    g()\n" for _ in range(250))},
         "graph": {"functions": [_fn("m.py", 1, "f")], "calls": []}},
        {"name": "extend_py", "op": "extend", "files": {py: T.PY},
         "graph": {"functions": [_fn(py, 4, "helper"), _fn(py, 8, "dep"), _fn(py, 12, "handler")],
                   "calls": [[f"{py}:12", f"{py}:4", "graphify"]]}},
        {"name": "routes_py", "op": "routes",
         "files": {"app/main.py": "from app.api import items as items_mod\n"
                                  "app.include_router(items_mod.router, prefix='/v1')\n",
                   "app/api/items.py": items,
                   "web/f.py": "bp = Blueprint('x', __name__, url_prefix='/bp')\n\n"
                               "@bp.route('/u/<int:uid>', methods=['PUT'])\ndef upd(uid):\n    pass\n\n"
                               "@app.get('/plain')\ndef plain():\n    pass\n"},
         "graph": {"functions": [_fn("app/api/items.py", 3, "read"), _fn("app/api/items.py", 7, "make"),
                                 _fn("web/f.py", 4, "upd"), _fn("web/f.py", 8, "plain")],
                   "calls": [], "files": [{"path": "app/main.py"}]}},
        {"name": "routes_ts", "op": "routes",
         "files": {"srv/app.ts": "const app = express()\nfunction show(req, res) {}\n"
                                 "app.get('/users/:id', auth, show)\napp.post('/users', (req, res) => {})\n",
                   "srv/c.ts": "@Controller('cats')\nclass CatsController {\n  @Get(':id')\n  one() {}\n}\n",
                   "srv/d.ts": "@Controller('dogs')\nexport class DogsController {\n  @Post()\n  make() {}\n}\n",
                   "web/app/api/items/[id]/route.ts": "export async function GET(req) {}\n"},
         "graph": {"functions": [_fn("srv/app.ts", 2, "show"), _fn("srv/app.ts", 4, "anon"),
                                 _fn("srv/c.ts", 4, "one"), _fn("srv/d.ts", 4, "make"),
                                 _fn("web/app/api/items/[id]/route.ts", 1, "GET")], "calls": []}},
        {"name": "routes_rs", "op": "routes",
         "files": {rs: 'fn app() -> Router {\n    Router::new()\n'
                       '        .route("/api/x", get(list).post(handlers::make))\n}\n'
                       "async fn list() {}\nasync fn make() {}\n\n#[get(\"/hi/\")]\nasync fn hi() {}\n"},
         "graph": {"functions": [_fn(rs, 5, "list"), _fn(rs, 6, "make"), _fn(rs, 9, "hi")], "calls": []}},
        {"name": "http_template_fetch", "op": "http",
         "files": {ts: "export async function load(code) {\n"
                       "  await api.get(`/api/projects/${code}/flow?x=1`)\n"
                       "  await fetch(`/api/projects/${code}/traces`, { method: 'POST' })\n}\n"},
         "graph": {"functions": _http_routes(_fn(ts, 1, "load")), "calls": [], "units": []}},
        {"name": "http_literal_wins", "op": "http",
         "files": {ts: "export function load(x) {\n  api.get('/api/projects/list')\n  api.get(`/api/${x}/list`)\n}\n"},
         "graph": {"functions": _http_routes(_fn(ts, 1, "load")), "calls": [], "units": []}},
        {"name": "http_suffix_and_router", "op": "http",
         "files": {ts: "const app = express()\nexport function load() {\n"
                       "  app.get('/projects/{c}/flow', h)\n  api.get('/projects/a/flow')\n}\n"},
         "graph": {"functions": [_fn(ts, 2, "load"), _routed("api/a.py", 1, "GET", "/api/projects/{code}/flow")],
                   "calls": [], "units": []}},
        {"name": "http_non_front", "op": "http",
         "files": {"srv/x.ts": "export function load() {\n  api.get('/api/projects/list')\n}\n"},
         "graph": {"functions": [_fn("srv/x.ts", 1, "load"), _routed("api/a.py", 3, "GET", "/api/projects/list")],
                   "calls": [], "units": []}},
        {"name": "http_web_unit", "op": "http",
         "files": {"srv/x.ts": "export function load() {\n  api.get('/api/projects/list')\n}\n"},
         "graph": {"functions": [_fn("srv/x.ts", 1, "load"), _routed("api/a.py", 3, "GET", "/api/projects/list")],
                   "calls": [], "units": [{"kind": "web", "dir": "srv"}]}},
        {"name": "units", "op": "units", "graph": {"functions": []},
         "files": {"api/package.json": '{"dependencies": {"express": "4"}, "scripts": {"dev": "tsx w --port 4100"}}',
                   "api/tsconfig.json": "{}",
                   "web/package.json": '{"devDependencies": {"vite": "5"}, "dependencies": {"react": "18"},'
                                       ' "scripts": {"dev": "vite"}}',
                   "site/package.json": '{"dependencies": {"next": "15"}, "scripts": {"start": "next start"}}',
                   "broken/package.json": "{nope",
                   "srv/pyproject.toml": "[project]\nname='x'\n", "srv/uv.lock": "",
                   "srv/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
                   "fl/requirements.txt": "flask\n", "fl/web.py": "server = Flask(__name__)\n",
                   "dj/manage.py": "", "wk/requirements.txt": "celery\n",
                   "wk/tasks.py": "celery_app = Celery('t')\n",
                   "rs/Cargo.toml": '[package]\nname = "svc"\n\n[dependencies]\naxum = "0.8"\n',
                   "ws/Cargo.toml": "[workspace]\nmembers = []\n",
                   "a/b/c/d/package.json": '{"dependencies": {"express": "4"}}'}},
        {"name": "infra_code_calls", "op": "infra",
         "files": {"app/db.py": "from sqlalchemy import select\nfrom sqlalchemy.orm import Session\n"
                                "def save(s: Session):\n    q = select(1)\n    s.execute(q)\n",
                   "app/llm.py": "from openai import OpenAI\nclass Bot:\n    def __init__(self):\n"
                                 "        self.client = OpenAI()\n    def ask(self):\n"
                                 "        return self.client.chat.completions.create(model='x')\n",
                   "app/w.py": "import httpx\nasync def pull():\n    async with httpx.AsyncClient() as c:\n"
                               "        await c.get('https://x')\n",
                   "srv/p.ts": "import { PrismaClient } from '@prisma/client'\nconst prisma = new PrismaClient()\n"
                               "export async function list() {\n  return prisma.user.findMany()\n}\n",
                   "core/src/q.rs": "use sqlx::PgPool;\npub async fn one(pool: &PgPool) {\n"
                                    "    sqlx::query(\"x\").fetch_one(pool).await;\n}\n",
                   "scripts/seed.py": "import redis\ndef go():\n    redis.Redis().set('a', 1)\n"},
         "graph": {"functions": [_fn("app/db.py", 3, "save"), _fn("app/llm.py", 5, "ask"),
                                 _fn("app/w.py", 2, "pull"), _fn("srv/p.ts", 3, "list"),
                                 _fn("core/src/q.rs", 2, "one"), _fn("scripts/seed.py", 2, "go")],
                   "calls": [], "units": [], "http": []}},
        {"name": "infra_deps_compose_config", "op": "infra",
         "files": {"package.json": '{"dependencies": {"express": "4", "ioredis": "5"}}',
                   "web/package.json": '{"dependencies": {"react": "18", "pg": "8"}}',
                   "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    ports:\n"
                                         "      - \"15432:5432\"\n  cache:\n    image: redis:7\n",
                   ".env.example": "DATABASE_URL=postgresql://user:secret@localhost:15432/app\n"
                                   "REDIS_HOST=your-redis-host\n",
                   "app/config.py": "MONGO = 'mongodb://admin:pw@mongo.example.org:27017/x'\n",
                   "conf/application.yml": "spring:\n  datasource:\n    url: jdbc:mysql://mysql:3306/x\n"
                                           "redis:\n  host: cache\n  port: 6380\n",
                   "prisma/schema.prisma": 'datasource db {\n  provider = "postgresql"\n}\n',
                   "requirements.txt": "boto3==1\n-e .\n# c\n",
                   "pyproject.toml": '[project]\ndependencies = ["neo4j>=5", "elasticsearch"]\n'},
         "graph": {"functions": [], "calls": [], "units": [], "http": []}},
        {"name": "infra_links_by_dir", "op": "infra",
         "files": {"a/db.py": "import psycopg\ndef q(c: psycopg.Connection):\n    c.execute('x')\n",
                   "b/h.py": "import httpx\ndef g():\n    httpx.get('https://x')\n"},
         "graph": {"functions": [_fn("a/db.py", 2, "q"), _fn("b/h.py", 2, "g")], "calls": [],
                   "units": [{"name": "a", "kind": "server", "dir": "a", "framework": "FastAPI", "port": 8000},
                             {"name": "b", "kind": "server", "dir": "b", "framework": "Flask", "port": None}],
                   "http": []}},
    ]  # fmt: skip
    return out


def write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(bytes.fromhex(text["hex"]) if isinstance(text, dict) else text.encode("utf-8"))


def run(case: dict) -> object:
    """사례 하나를 파이썬 판으로 — 답."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, case["files"])
        g = copy.deepcopy(case["graph"])
        op = case["op"]
        if op == "files":
            return flow.files(root)
        if op == "steps":
            steps.steps(root, g)
            g.pop("_idents", None)
            return g
        if op == "extend":
            return flow.extend(root, g)
        if op == "routes":
            routes.routes(root, g)
            return g
        if op == "http":
            return routes.http_links(root, g)
        if op == "units":
            return infra.units(root, g)
        steps.steps(root, g)
        infra.infra(root, g)
        g.pop("_idents", None)
        return g
