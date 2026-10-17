"""싱크독 실행 기록기 (SYNC-INFRA-001 9.9 · SYNC-MS-027, 카드 L29). view_arc 기록기를 옮겼다.

웹 요청 하나(FastAPI·Starlette·Flask·Django) 또는 작업 하나(Celery 작업, 봇·배치의 맨 위 함수)가 처리되는 동안
실행된 **프로젝트 코드**의 함수 호출을 실제 인자·반환값·예외와 함께 기록해 SYNCDOC_TRACE_OUT 에 하나마다 JSON 파일로 남긴다.
기록 도구(`syncdoc-local trace`)가 그 폴더를 지켜보다가 서버에 올린다. 프로젝트 코드는 고치지 않는다:
sitecustomize.py가 프로세스 시작 때 install()을 부르고, 프레임워크 모듈은 import 될 때 감싼다.

- 사건의 함수(`fn`)는 싱크독 코드 그래프의 함수 열쇠(`파일:def 줄`)다 — 범위 파일(SYNCDOC_TRACE_SPANS)로 맞춘다.
  그래프에 없는 프로젝트 함수(중첩 함수 등)도 같은 꼴(`파일:def 줄`)로 남긴다.
- Python 3.12+: sys.monitoring(PEP 669). 라이브러리 코드는 첫 호출 뒤 이벤트를 꺼서(DISABLE) 거의 느려지지 않는다.
- 3.10~3.11: sys.setprofile 로 대신한다(더 느리다).
- 호출의 부모는 프레임 사슬(f_back)로 찾는다. 그래서 asyncio로 동시에 도는 코루틴도 서로 섞이지 않는다.
- 요청 구분은 contextvars: Starlette.__call__ · Flask.wsgi_app · Django BaseHandler.get_response 를 감싸 요청마다 기록기를 둔다.
- 작업 기록(SYNCDOC_TRACE_JOB=1, `trace --job`): 라이브러리나 모듈 맨 위에서 불린 프로젝트 함수 하나가 작업 하나다.
- 경계 호출: 코드가 DB·외부로 나가는 순간(SQLAlchemy 쿼리, httpx·requests HTTP, Redis 명령, S3 API)을
  fn="@infra" 사건으로 남긴다(대상 호스트·SQL 앞부분·걸린 시간). 계정·비밀번호는 남기지 않는다(INFRA C13).

환경변수
- SYNCDOC_TRACE_OUT    기록을 쓸 폴더(필수, 없으면 아무것도 하지 않음)
- SYNCDOC_TRACE_ROOT   저장소 뿌리 — 그래프 경로의 기준(기본: 현재 폴더)
- SYNCDOC_TRACE_SPANS  범위 파일 {files: {절대 경로: [[시작 줄, 끝 줄, 열쇠]…]}}
- SYNCDOC_TRACE_JOB    1 이면 웹 요청이 아닌 작업도 기록(봇·배치)
"""

from __future__ import annotations

import contextvars
import importlib.abc
import inspect
import json
import linecache
import os
import re
import reprlib
import sys
import threading
import time
from datetime import datetime, timezone

TRACE_DIR = os.environ.get("SYNCDOC_TRACE_OUT", "")
ROOT = os.path.realpath(os.environ.get("SYNCDOC_TRACE_ROOT") or os.getcwd())
MAX_EVENTS = 20000
MAX_FILES = 300
SKIP_PATHS = ("/docs", "/redoc", "/openapi.json", "/favicon.ico", "/static/", "/media/", "/__debug__/")
JOBS = os.environ.get("SYNCDOC_TRACE_JOB") == "1"
SPLIT_MS = 2000  # 작업의 맨 위 함수가 이보다 오래 열려 있으면 직접 부른 한 단위씩 끊는다
LIB_MARKERS = (os.sep + "site-packages" + os.sep, os.sep + ".venv" + os.sep, os.sep + "node_modules" + os.sep)

_current: contextvars.ContextVar["Recorder | None"] = contextvars.ContextVar("syncdoc_recorder", default=None)
_project_cache: dict[str, str | None] = {}  # 파일 경로 → 루트 기준 상대 경로(프로젝트 밖이면 None)
_installed = False
_spans: dict[str, list] | None = None  # 상대 경로 → [[시작 줄, 끝 줄, 열쇠]]
_keys: dict[tuple[str, int], str] = {}

_repr = reprlib.Repr()
_repr.maxstring = 80
_repr.maxother = 80
_repr.maxlist = 5
_repr.maxdict = 5
_repr.maxset = 5
_repr.maxtuple = 5
_repr.maxlevel = 3


# 이런 이름의 값은 기록하지 않는다(매개변수 이름, 객체·사전 안의 키)
SECRET = re.compile(r"pass|secret|token|api_?key|apikey|authoriz|credential|private", re.I)
_SECRET_FIELD = re.compile(
    r"""((?:\w*(?:pass|secret|token|api_?key|apikey|authoriz|credential|private)\w*)['"]?\s*[:=]\s*)('[^']*'|"[^"]*"|[^,)}\s]+)""", re.I
)


def safe_repr(value) -> str:
    try:
        text = _repr.repr(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    if " object at 0x" in text:  # 기본 repr은 주소만 보여서 쓸모가 없다
        text = f"<{type(value).__name__}>"
    text = _SECRET_FIELD.sub(r"\1***", text)
    return text if len(text) <= 120 else text[:119] + "…"


def project_rel(filename: str) -> str | None:
    hit = _project_cache.get(filename, "")
    if hit != "":
        return hit
    rel = None
    real = os.path.realpath(filename) if filename and not filename.startswith("<") else ""
    if real.startswith(ROOT + os.sep) and not any(m in real for m in LIB_MARKERS) and real != os.path.realpath(__file__):
        rel = os.path.relpath(real, ROOT).replace(os.sep, "/")
    _project_cache[filename] = rel
    return rel


def _load_spans() -> dict[str, list]:
    global _spans
    if _spans is None:
        _spans = {}
        try:
            with open(os.environ.get("SYNCDOC_TRACE_SPANS", ""), encoding="utf-8") as f:
                files = json.load(f).get("files", {})
            for path, spans in files.items():
                rel = os.path.relpath(os.path.realpath(path), ROOT).replace(os.sep, "/")
                _spans[rel] = spans
        except (OSError, ValueError):
            pass
    return _spans


def function_key(code, rel: str) -> str:
    """그래프 함수 열쇠 `파일:def 줄` — 데코레이터가 있으면 co_firstlineno는 그 줄이라 def 줄을 찾는다."""
    first = code.co_firstlineno
    hit = _keys.get((rel, first))
    if hit is not None:
        return hit
    line = first
    for n in range(first, first + 40):
        text = linecache.getline(code.co_filename, n).lstrip()
        if text.startswith(("def ", "async def ")):
            line = n
            break
    key = f"{rel}:{line}"
    for start, _end, k in _load_spans().get(rel, []):
        if start in (line, first):
            key = k
            break
    _keys[(rel, first)] = key
    return key


class Recorder:
    """요청 하나의 기록. 이벤트는 호출 하나당 하나(시작·끝을 한 줄에)."""

    def __init__(self, scope: dict, kind: str | None = None):
        self.scope = scope  # 라우팅이 끝나면 scope["endpoint"] 에 맞은 핸들러가 들어온다
        self.kind = kind  # None: 웹 요청, "job": 작업(Celery·봇·배치)
        self.root_frame: int | None = None  # 작업 기록: 맨 위 함수의 프레임(끝나면 기록을 닫는다)
        self.method = scope.get("method", "")
        self.path = scope.get("path", "")
        self.query = (scope.get("query_string") or b"").decode("latin-1")[:200]
        self.status: int | None = None
        self.error: str | None = None
        self.started = datetime.now(timezone.utc)
        self.t0 = time.perf_counter_ns()
        self.events: list[dict] = []
        self.open: dict[int, int] = {}  # id(frame) → 이벤트 번호(아직 안 끝난 호출)
        self.truncated = False
        self.lock = threading.Lock()

    def now(self) -> float:
        return round((time.perf_counter_ns() - self.t0) / 1e6, 3)

    def start(self, code, frame, rel: str, kind: str = "call") -> None:
        if code.co_name.startswith("<"):
            return  # 생성기 식·람다는 그래프 함수가 아니다 — 그 안의 호출은 바깥 함수에 붙는다
        with self.lock:
            if len(self.events) >= MAX_EVENTS:
                self.truncated = True
                return
            parent, call_line = -1, None
            back = frame.f_back
            for _ in range(64):  # 열린 호출 중 가장 가까운 조상 프레임이 부모
                if back is None:
                    break
                idx = self.open.get(id(back))
                if idx is not None:
                    parent, call_line = idx, back.f_lineno
                    break
                back = back.f_back
            qualname = getattr(code, "co_qualname", code.co_name)
            self.open[id(frame)] = len(self.events)
            self.events.append({
                "i": len(self.events),
                "parent": parent,
                "fn": function_key(code, rel),
                "name": qualname,
                "line": code.co_firstlineno,
                "callLine": call_line,
                "args": arguments(code, frame) if kind == "call" else None,
                "kind": kind,
                "t0": self.now(),
            })

    def end(self, frame, ret=None, exc=None, yielded=False) -> None:
        with self.lock:
            idx = self.open.pop(id(frame), None)
            if idx is None:
                return
            ev = self.events[idx]
            ev["t1"] = self.now()
            if exc is not None:
                ev["exc"] = f"{type(exc).__name__}: {safe_repr(str(exc))[1:-1]}" if str(exc) else type(exc).__name__
            else:
                ev["ret"] = safe_repr(ret)
            if yielded:
                ev["yield"] = True
            # 다른 열린 호출(동시에 도는 작업)이 뒤에 있으면 끊지 않는다(번호가 꼬인다)
            split = (
                self.kind == "job" and ev["parent"] == 0 and self.root_frame is not None
                and self.now() > SPLIT_MS and all(v < idx for v in self.open.values())
            )
        if split:
            self.split(idx)

    def split(self, idx: int) -> None:
        """오래 도는 작업(봇 루프)에서 맨 위 함수가 직접 부른 한 단위(idx 이후)를 따로 기록하고 이 기록에서 뗀다."""
        with self.lock:
            part = self.events[idx:]
            if len(part) < 2 and part[0].get("t1", 0) - part[0]["t0"] < 50:
                del self.events[idx:]  # 아주 짧은 한 번(대기·확인)은 남기지 않는다
                return
            del self.events[idx:]
        child = Recorder({"method": "JOB", "path": part[0].get("name") or part[0]["fn"]}, kind="job")
        child.started = datetime.now(timezone.utc)
        base = part[0]["t0"]
        for e in part:
            e["i"] -= idx
            e["parent"] = -1 if e["parent"] < idx else e["parent"] - idx
            e["t0"] = round(e["t0"] - base, 3)
            if "t1" in e:
                e["t1"] = round(e["t1"] - base, 3)
        child.events = part
        child.status = 500 if part[0].get("exc") else 200
        child.write(part[0].get("t1", 0))

    def boundary(self, kind: str, target: str, op: str) -> int | None:
        """DB·외부로 나가는 호출 시작. 부모는 가장 가까운 열린 프로젝트 함수(라이브러리 프레임을 거슬러 올라간다)."""
        with self.lock:
            if len(self.events) >= MAX_EVENTS:
                self.truncated = True
                return None
            parent, call_line = -1, None
            back = sys._getframe(2)
            for _ in range(160):
                if back is None:
                    break
                idx = self.open.get(id(back))
                if idx is not None:
                    parent, call_line = idx, back.f_lineno
                    break
                back = back.f_back
            self.events.append({
                "i": len(self.events),
                "parent": parent,
                "fn": "@infra",
                "name": op[:60],
                "callLine": call_line,
                "infra": {"kind": kind, "target": target, "op": op[:160]},
                "t0": self.now(),
            })
            return len(self.events) - 1

    def boundary_end(self, idx: int | None, ret: str | None = None, exc: BaseException | None = None) -> None:
        if idx is None:
            return
        with self.lock:
            ev = self.events[idx]
            ev["t1"] = self.now()
            if exc is not None:
                ev["exc"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            elif ret is not None:
                ev["ret"] = ret

    def endpoint_id(self) -> str | None:
        """라우터가 고른 핸들러(scope["endpoint"])의 함수 id. 기록에 그 함수가 있을 때만."""
        endpoint = self.scope.get("endpoint")
        try:
            code = inspect.unwrap(endpoint).__code__
        except Exception:
            return None
        rel = project_rel(code.co_filename)
        if rel is None:
            return None
        fid = function_key(code, rel)
        return fid if any(e["fn"] == fid for e in self.events) else None

    def finish(self) -> None:
        if not self.events or not TRACE_DIR:
            return
        end = self.now()
        for idx in self.open.values():  # 끝나지 않은 호출(취소된 코루틴 등)
            self.events[idx].setdefault("t1", end)
        if self.kind == "job" and len(self.events) < 2 and end < 50:
            return  # import 때 잠깐 불린 함수 같은 아주 작은 작업은 남기지 않는다
        self.write(end)

    def write(self, end: float) -> None:
        rid = f"{int(time.time() * 1000)}-{os.getpid()}-{id(self) % 100000}"
        record = {
            "version": 1,
            "id": rid,
            "method": self.method,
            "path": self.path,
            "query": self.query,
            "status": self.status,
            "error": self.error,
            "startedAt": self.started.isoformat(),
            "ms": end,
            "truncated": self.truncated,
            "events": self.events,
        }
        record["kind"] = self.kind or "back"
        root = self.endpoint_id()
        if root is None:
            # FastAPI는 Depends를 먼저 부르고 엔드포인트를 마지막에 부른다. 단 yield 의존성(get_session)은 응답 뒤에
            # 다시 깨어나(resume) 맨 끝에 오므로 뺀다
            tops = [e["fn"] for e in self.events if e["parent"] == -1 and e.get("kind") != "resume"]
            root = tops[-1] if tops else None
        summary = {k: record[k] for k in ("id", "method", "path", "status", "error", "startedAt", "ms")}
        summary.update(calls=len(self.events), root=root)
        if self.kind:
            summary["kind"] = self.kind
        try:
            os.makedirs(TRACE_DIR, exist_ok=True)
            tmp = os.path.join(TRACE_DIR, f".{rid}.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(TRACE_DIR, f"{rid}.json"))
            with open(os.path.join(TRACE_DIR, "index.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(summary, ensure_ascii=False) + "\n")
            prune()
        except OSError as e:
            print(f"[syncdoc] 기록을 쓰지 못했습니다: {e}", file=sys.stderr)


def arguments(code, frame) -> dict[str, str]:
    n = code.co_argcount + code.co_kwonlyargcount
    if code.co_flags & inspect.CO_VARARGS:
        n += 1
    if code.co_flags & inspect.CO_VARKEYWORDS:
        n += 1
    out = {}
    local = frame.f_locals
    for name in code.co_varnames[:n]:
        if name in ("self", "cls") or name not in local:
            continue
        out[name] = "***" if SECRET.search(name) else safe_repr(local[name])
    return out


def prune() -> None:
    """오래된 기록부터 지워 MAX_FILES 개만 남긴다."""
    files = sorted(f for f in os.listdir(TRACE_DIR) if f.endswith(".json"))
    for f in files[:-MAX_FILES]:
        try:
            os.remove(os.path.join(TRACE_DIR, f))
        except OSError:
            pass


# ---------------------------------------------------------------- 이벤트 받기

def _install_monitoring() -> None:
    mon = sys.monitoring
    tool = mon.PROFILER_ID
    try:
        mon.use_tool_id(tool, "syncdoc")
    except ValueError:  # 다른 프로파일러가 이미 쓰는 중이면 디버거 칸을 빌린다
        tool = mon.DEBUGGER_ID
        mon.use_tool_id(tool, "syncdoc")
    E = mon.events
    DISABLE = mon.DISABLE
    CO_GEN = inspect.CO_GENERATOR

    def on_start(code, offset):
        rel = project_rel(code.co_filename)
        if rel is None:
            return DISABLE  # 라이브러리 함수: 이 코드의 이 이벤트는 다시 부르지 않는다
        rec = _current.get()
        frame = sys._getframe(1)
        if rec is None and JOBS:
            rec = _job_root(code, frame)
        if rec is not None:
            rec.start(code, frame, rel)

    def on_return(code, offset, retval):
        if project_rel(code.co_filename) is None:
            return DISABLE
        rec = _current.get()
        if rec is not None:
            frame = sys._getframe(1)
            rec.end(frame, ret=retval)
            if rec.root_frame == id(frame):
                _job_done(rec)

    def on_unwind(code, offset, exc):
        rec = _current.get()
        if rec is not None and project_rel(code.co_filename) is not None:
            frame = sys._getframe(1)
            rec.end(frame, exc=exc)
            if rec.root_frame == id(frame):
                rec.error = f"{type(exc).__name__}: {exc}"[:200]
                _job_done(rec)

    # 제너레이터는 yield 마다 프레임을 떠나므로 yield = 한 번 끝남, resume = 다시 시작으로 본다.
    # 코루틴의 await 대기(yield/resume)는 같은 호출이 이어지는 것이라 무시한다.
    def on_yield(code, offset, value):
        if project_rel(code.co_filename) is None:
            return DISABLE
        rec = _current.get()
        if rec is not None and code.co_flags & CO_GEN:
            rec.end(sys._getframe(1), ret=value, yielded=True)

    def on_resume(code, offset):
        rel = project_rel(code.co_filename)
        if rel is None:
            return DISABLE
        rec = _current.get()
        if rec is not None and code.co_flags & CO_GEN:
            rec.start(code, sys._getframe(1), rel, kind="resume")

    mon.register_callback(tool, E.PY_START, on_start)
    mon.register_callback(tool, E.PY_RETURN, on_return)
    mon.register_callback(tool, E.PY_UNWIND, on_unwind)
    mon.register_callback(tool, E.PY_YIELD, on_yield)
    mon.register_callback(tool, E.PY_RESUME, on_resume)
    mon.set_events(tool, E.PY_START | E.PY_RETURN | E.PY_UNWIND | E.PY_YIELD | E.PY_RESUME)


def _job_root(code, frame) -> "Recorder | None":
    """작업 기록: 라이브러리(스케줄러·이벤트 루프·Celery …)나 모듈 맨 위 코드가 부른 프로젝트 함수면 새 작업을 연다."""
    if not code.co_flags & inspect.CO_NEWLOCALS or code.co_name.startswith("<"):
        return None  # 모듈·클래스 본문, 람다·제너레이터 식
    back = frame.f_back
    if back is not None and project_rel(back.f_code.co_filename) is not None and back.f_code.co_name != "<module>":
        return None  # 프로젝트 함수가 부른 것(작업 안쪽)
    qualname = getattr(code, "co_qualname", code.co_name)
    rec = Recorder({"method": "JOB", "path": qualname}, kind="job")
    rec.root_frame = id(frame)
    _install_boundaries()
    _current.set(rec)
    return rec


def _job_done(rec: "Recorder") -> None:
    if rec.status is None:
        rec.status = 500 if rec.error else 200
    _current.set(None)
    rec.finish()


def _install_profile() -> None:
    def profile(frame, event, arg):
        if event not in ("call", "return"):
            return
        rec = _current.get()
        if rec is None:
            return
        code = frame.f_code
        rel = project_rel(code.co_filename)
        if rel is None:
            return
        if event == "call":
            rec.start(code, frame, rel)
        else:
            rec.end(frame, ret=arg)

    sys.setprofile(profile)
    threading.setprofile(profile)


def _patch_starlette(Starlette) -> None:
    original = Starlette.__call__

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or _current.get() is not None or scope.get("path", "").startswith(SKIP_PATHS):
            return await original(self, scope, receive, send)
        _install_boundaries()  # 첫 요청 때: 앱이 쓰는 라이브러리가 이미 import 된 뒤라 그때 건다
        rec = Recorder(scope)
        token = _current.set(rec)

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                rec.status = message.get("status")
            await send(message)

        try:
            await original(self, scope, receive, send_wrapper)
        except BaseException as e:
            rec.error = f"{type(e).__name__}: {e}"[:200]
            raise
        finally:
            _current.reset(token)
            rec.finish()

    Starlette.__call__ = __call__


def _patch_flask(Flask) -> None:
    original = Flask.wsgi_app

    def wsgi_app(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if _current.get() is not None or path.startswith(SKIP_PATHS):
            return original(self, environ, start_response)
        _install_boundaries()
        rec = Recorder({"method": environ.get("REQUEST_METHOD", ""), "path": path, "query_string": environ.get("QUERY_STRING", "").encode("latin-1")})
        token = _current.set(rec)

        def start(status, headers, exc_info=None):
            try:
                rec.status = int(str(status).split()[0])
            except ValueError:
                pass
            return start_response(status, headers, exc_info) if exc_info else start_response(status, headers)

        try:
            return original(self, environ, start)
        except BaseException as e:
            rec.error = f"{type(e).__name__}: {e}"[:200]
            raise
        finally:
            _current.reset(token)
            rec.finish()

    dispatch = Flask.dispatch_request

    def dispatch_request(self, *args, **kwargs):
        rec = _current.get()
        if rec is not None:  # 라우터가 고른 뷰 함수
            try:
                from flask import request

                if request.url_rule is not None:
                    rec.scope["endpoint"] = self.view_functions.get(request.url_rule.endpoint)
            except Exception:
                pass
        return dispatch(self, *args, **kwargs)

    Flask.wsgi_app = wsgi_app
    Flask.dispatch_request = dispatch_request


def _django_endpoint(request):
    """Django 가 고른 뷰: 함수 뷰는 그대로, 클래스 뷰·DRF ViewSet 은 이 요청 메서드의 메서드"""
    match = getattr(request, "resolver_match", None)
    func = getattr(match, "func", None)
    if func is None:
        return None
    cls = getattr(func, "view_class", None) or getattr(func, "cls", None)
    if cls is None:
        return func
    actions = getattr(func, "actions", None)
    name = (actions or {}).get(request.method.lower()) or request.method.lower()
    return getattr(cls, name, None) or func


def _patch_django(BaseHandler) -> None:
    original = BaseHandler.get_response

    def begin(request):
        _install_boundaries()
        rec = Recorder({"method": request.method, "path": request.path, "query_string": request.META.get("QUERY_STRING", "").encode("latin-1")})
        return rec, _current.set(rec)

    def end(rec, token, request, response):
        rec.status = getattr(response, "status_code", rec.status)
        rec.scope["endpoint"] = _django_endpoint(request)
        _current.reset(token)
        rec.finish()

    def get_response(self, request):
        if _current.get() is not None or request.path.startswith(SKIP_PATHS):
            return original(self, request)
        rec, token = begin(request)
        response = None
        try:
            response = original(self, request)
            return response
        except BaseException as e:
            rec.error = f"{type(e).__name__}: {e}"[:200]
            raise
        finally:
            end(rec, token, request, response)

    BaseHandler.get_response = get_response
    original_async = getattr(BaseHandler, "get_response_async", None)
    if original_async is not None:

        async def get_response_async(self, request):
            if _current.get() is not None or request.path.startswith(SKIP_PATHS):
                return await original_async(self, request)
            rec, token = begin(request)
            response = None
            try:
                response = await original_async(self, request)
                return response
            except BaseException as e:
                rec.error = f"{type(e).__name__}: {e}"[:200]
                raise
            finally:
                end(rec, token, request, response)

        BaseHandler.get_response_async = get_response_async


def _patch_celery(module) -> None:
    """Celery 작업 하나 = 기록 하나(작업 이름). 신호로 걸어 작업 실행 방식(__call__ · run)과 상관없이."""
    from celery import signals

    open_jobs: dict = {}

    def prerun(task_id=None, task=None, **_):
        if _current.get() is not None:
            return
        _install_boundaries()
        rec = Recorder({"method": "TASK", "path": getattr(task, "name", None) or type(task).__name__}, kind="job")
        open_jobs[task_id] = (rec, _current.set(rec))

    def postrun(task_id=None, state=None, **_):
        entry = open_jobs.pop(task_id, None)
        if entry is None:
            return
        rec, token = entry
        rec.status = 200 if state in (None, "SUCCESS") else 500
        if state not in (None, "SUCCESS"):
            rec.error = rec.error or str(state)
        try:
            _current.reset(token)
        except ValueError:
            _current.set(None)
        rec.finish()

    signals.task_prerun.connect(prerun, weak=False)
    signals.task_postrun.connect(postrun, weak=False)


# 모듈 이름 → (감쌀 것, 설명). import 가 끝난 직후에 감싼다
_PATCHES = {
    "starlette.applications": (lambda m: _patch_starlette(m.Starlette), "Starlette·FastAPI"),
    "flask.app": (lambda m: _patch_flask(m.Flask), "Flask"),
    "django.core.handlers.base": (lambda m: _patch_django(m.BaseHandler), "Django"),
    "celery.app.task": (_patch_celery, "Celery"),
}


class _PostImport(importlib.abc.MetaPathFinder):
    """프레임워크 모듈을 import 하는 순간 원래 로더로 읽은 뒤 감싼다(시작 때 미리 import 하지 않는다)."""

    def find_spec(self, name, path=None, target=None):
        entry = _PATCHES.get(name)
        if entry is None:
            return None
        spec = None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                break
        loader = getattr(spec, "loader", None)
        if spec is None or loader is None or not hasattr(loader, "exec_module"):
            return spec
        exec_module = loader.exec_module

        def run(module):
            exec_module(module)
            _apply(name, module)

        loader.exec_module = run
        return spec


def _apply(name: str, module) -> None:
    patch, label = _PATCHES[name]
    try:
        patch(module)
    except Exception as error:
        print(f"[syncdoc] {label} 를 감싸지 못했습니다: {error}", file=sys.stderr)
        return
    _ensure_monitoring(label)


_monitoring = False


def _ensure_monitoring(label: str) -> None:
    global _monitoring
    if _monitoring:
        return
    _monitoring = True
    if hasattr(sys, "monitoring"):
        _install_monitoring()
    else:
        _install_profile()
    print(f"[syncdoc] 실행 기록 켜짐({label}) → {TRACE_DIR} (루트 {ROOT})", file=sys.stderr)


def install() -> None:
    global _installed
    if _installed or not TRACE_DIR:
        return
    _installed = True
    for name in _PATCHES:  # 이미 import 된 것은 바로
        if name in sys.modules:
            _apply(name, sys.modules[name])
    sys.meta_path.insert(0, _PostImport())
    if JOBS:
        _ensure_monitoring("작업")


# -------------------------------------------------------------------- 경계 호출(DB·외부)
_boundaries = False


def _url_label(url) -> str:
    """접속 주소에서 계정·비밀번호를 뺀 scheme://host:port/db"""
    try:
        host = url.host or ""
        port = f":{url.port}" if url.port else ""
        db = f"/{url.database}" if url.database else ""
        return f"{url.drivername}://{host}{port}{db}"
    except Exception:
        return "db"


def _wrap(owner, name: str, kind: str, describe, result=None) -> None:
    """owner.name 을 감싸 경계 사건을 남긴다. describe(args, kwargs) → (target, op). 기록 중인 요청이 없으면 그대로."""
    original = getattr(owner, name, None)
    if original is None or getattr(original, "_syncdoc", False):
        return
    if inspect.iscoroutinefunction(original):
        async def wrapper(*args, **kwargs):
            rec = _current.get()
            if rec is None:
                return await original(*args, **kwargs)
            try:
                target, op = describe(args, kwargs)
            except Exception:
                target, op = kind, name
            idx = rec.boundary(kind, target, op)
            try:
                value = await original(*args, **kwargs)
            except BaseException as e:
                rec.boundary_end(idx, exc=e)
                raise
            rec.boundary_end(idx, ret=result(value) if result else None)
            return value
    else:
        def wrapper(*args, **kwargs):
            rec = _current.get()
            if rec is None:
                return original(*args, **kwargs)
            try:
                target, op = describe(args, kwargs)
            except Exception:
                target, op = kind, name
            idx = rec.boundary(kind, target, op)
            try:
                value = original(*args, **kwargs)
            except BaseException as e:
                rec.boundary_end(idx, exc=e)
                raise
            rec.boundary_end(idx, ret=result(value) if result else None)
            return value
    wrapper._syncdoc = True
    wrapper.__name__ = getattr(original, "__name__", name)
    setattr(owner, name, wrapper)


def _install_boundaries() -> None:
    global _boundaries
    if _boundaries:
        return
    _boundaries = True
    # SQLAlchemy: 엔진 이벤트(동기·비동기 엔진 모두 동기 엔진에서 실행된다)
    sa = sys.modules.get("sqlalchemy")
    if sa is not None:
        try:
            from sqlalchemy import event
            from sqlalchemy.engine import Engine

            def before(conn, cursor, statement, parameters, context, executemany):
                rec = _current.get()
                if rec is not None and context is not None:
                    op = " ".join(str(statement).split())
                    context._syncdoc = rec.boundary("db", _url_label(conn.engine.url), op)

            def after(conn, cursor, statement, parameters, context, executemany):
                rec = _current.get()
                if rec is not None and context is not None:
                    rows = getattr(cursor, "rowcount", -1)
                    rec.boundary_end(getattr(context, "_syncdoc", None), ret=f"행 {rows}" if rows is not None and rows >= 0 else "완료")

            def failed(ctx):
                rec = _current.get()
                if rec is not None and ctx.execution_context is not None:
                    rec.boundary_end(getattr(ctx.execution_context, "_syncdoc", None), exc=ctx.original_exception)

            event.listen(Engine, "before_cursor_execute", before)
            event.listen(Engine, "after_cursor_execute", after)
            event.listen(Engine, "handle_error", failed)
        except Exception:
            pass
    # HTTP: httpx(OpenAI·Anthropic SDK 도 이것으로 나간다), requests
    if "httpx" in sys.modules:
        import httpx

        def http_desc(args, kwargs):
            req = args[1] if len(args) > 1 else kwargs.get("request")
            return f"{req.url.scheme}://{req.url.host}{':' + str(req.url.port) if req.url.port else ''}", f"{req.method} {req.url.path}"

        status = lambda r: str(getattr(r, "status_code", ""))  # noqa: E731
        _wrap(httpx.Client, "send", "http", http_desc, status)
        _wrap(httpx.AsyncClient, "send", "http", http_desc, status)
    if "requests" in sys.modules:
        import requests
        from urllib.parse import urlsplit

        def req_desc(args, kwargs):
            req = args[1] if len(args) > 1 else kwargs.get("request")
            u = urlsplit(req.url)
            return f"{u.scheme}://{u.hostname}{':' + str(u.port) if u.port else ''}", f"{req.method} {u.path}"

        _wrap(requests.Session, "send", "http", req_desc, lambda r: str(getattr(r, "status_code", "")))
    # Redis
    if "redis" in sys.modules:
        try:
            import redis

            def redis_desc(args, kwargs):
                client = args[0]
                kw = getattr(getattr(client, "connection_pool", None), "connection_kwargs", {}) or {}
                return f"redis://{kw.get('host', '')}:{kw.get('port', '')}", " ".join(str(a) for a in args[1:3])

            _wrap(redis.Redis, "execute_command", "redis", redis_desc, lambda r: safe_repr(r))
            try:
                import redis.asyncio as aredis

                _wrap(aredis.Redis, "execute_command", "redis", redis_desc, lambda r: safe_repr(r))
            except Exception:
                pass
        except Exception:
            pass
    # S3·MinIO(boto3/botocore): 모든 API 호출이 지나는 곳
    if "botocore" in sys.modules:
        try:
            from botocore.client import BaseClient

            def s3_desc(args, kwargs):
                client, operation = args[0], args[1]
                params = args[2] if len(args) > 2 else kwargs.get("api_params", {})
                host = getattr(getattr(client, "_endpoint", None), "host", "aws")
                where = "/".join(str(params.get(k)) for k in ("Bucket", "Key", "Prefix") if isinstance(params, dict) and params.get(k))
                return host, f"{operation} {where}".strip()

            _wrap(BaseClient, "_make_api_call", "s3", s3_desc, lambda r: "완료")
        except Exception:
            pass
