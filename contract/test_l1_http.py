"""카드 L1 몫 — /health·/api/me·Host·Origin 가드·API 앞머리·405·정적 파일·/specs.

기대 값은 파이썬 폐쇄망판의 바이트다(SYNC-API-001 2장 · SYNC-SEQ-001#SEQ-C3 · SYNC-INFRA-001 4.1).
계약 밖(끝 슬래시·HEAD·Range·ETag 꼴 등)은 묻지 않는다 — SYNC-CODE-002 2장.
"""

import re

import pytest

pytestmark = pytest.mark.card("L1")

FORBIDDEN = "폐쇄망판은 이 PC(또는 PUBLIC_BASE_URL)에서만 쓴다"


def test_health(server):
    r = server.client().get("/health")
    assert (r.status_code, r.headers["content-type"], r.text) == (
        200, "application/json", '{"status":"ok"}')  # fmt: skip


def test_me_is_the_local_user(server):
    r = server.client().get("/api/me")
    assert r.status_code == 200 and r.headers["content-type"] == "application/json"
    me = r.json()
    assert list(me) == ["id", "github_login", "display_name", "created_at", "llm_enabled",
                        "storage_modes", "edition", "repo_private"]  # fmt: skip
    assert {k: me[k] for k in list(me)[1:] if k != "created_at"} == {
        "github_login": "local", "display_name": "local", "llm_enabled": True,
        "storage_modes": ["server"], "edition": "closed", "repo_private": True}  # fmt: skip
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{6})?Z", me["created_at"])


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "LOCALHOST", "[::1]", "evil@127.0.0.1"])
def test_local_hosts_pass(server, host):
    r = server.client().get("/health", headers={"host": f"{host}:{server.port}"})
    assert r.status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.evil.example", "[::1", "0.0.0.0"])
def test_other_hosts_are_refused(server, host):
    r = server.client().get("/health", headers={"host": host})
    assert r.status_code == 403
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json() == {"type": "urn:syncdoc:forbidden-origin", "title": "forbidden-origin",
                        "status": 403, "detail": FORBIDDEN, "host": host}  # fmt: skip


@pytest.mark.parametrize("origin", ["http://evil.example", "null", "http://127.0.0.1:1"])
def test_write_from_other_origin_is_refused(server, origin):
    r = server.client().post("/api/me", headers={"origin": origin})
    assert r.status_code == 403
    assert r.json()["origin"] == origin


def test_same_origin_write_passes_the_guard(server):
    for headers in ({"origin": server.url}, {"origin": f"https://127.0.0.1:{server.port}"}, {}):
        r = server.client().post("/api/me", headers=headers)
        assert r.status_code == 405, headers  # 가드는 지나고 경로가 POST를 안 받는다


def test_read_ignores_origin(server):
    assert (
        server.client().get("/health", headers={"origin": "http://evil.example"}).status_code == 200
    )


def test_github_paths_are_404_and_login_redirects(server):
    c = server.client()
    r = c.get("/auth/github")
    assert r.status_code == 404
    assert r.json() == {"type": "urn:syncdoc:not-found", "title": "not-found", "status": 404,
                        "detail": "path /auth/github 없음", "resource": "path",
                        "id": "/auth/github"}  # fmt: skip
    assert c.post("/hooks/github").status_code == 404
    r = c.get("/login?next=/p/X")
    assert (r.status_code, r.headers["location"], r.content) == (302, "/", b"")


@pytest.mark.parametrize("path", ["/api/nonexistent", "/api"])
def test_api_prefix_unknown_is_404_problem(server, path):
    r = server.client().get(path)
    assert r.status_code == 404
    assert r.json() == {"type": "urn:syncdoc:not-found", "title": "not-found", "status": 404,
                        "detail": f"path {path} 없음", "resource": "path", "id": path}  # fmt: skip


def test_method_not_allowed(server):
    r = server.client().post("/health")
    assert r.status_code == 405
    assert r.headers["allow"] == "GET"
    assert r.json() == {"type": "urn:syncdoc:method-not-allowed", "title": "method-not-allowed",
                        "status": 405, "detail": "이 경로에 POST 메서드는 없습니다",
                        "allow": ["GET"]}  # fmt: skip


def test_static_shell_bundle_and_304(server):
    c = server.client()
    for path in ("/", "/p/SYNC", "/index.html"):
        r = c.get(path)
        assert (r.status_code, r.headers["cache-control"]) == (200, "no-cache"), path
        assert r.headers["content-type"] == "text/html; charset=utf-8"
    asset = re.search(r'src="(/assets/[^"]+\.js)"', c.get("/").text).group(1)
    r = c.get(asset)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["content-type"] == "text/javascript; charset=utf-8"
    again = c.get(asset, headers={"if-none-match": r.headers["etag"]})
    assert (again.status_code, again.content) == (304, b"")
    assert again.headers["cache-control"] == "public, max-age=31536000, immutable"
    for missing in ("/assets/nope.js", "/fonts/nope.woff2"):
        r = c.get(missing)
        assert (r.status_code, r.headers["cache-control"], r.content) == (404, "no-store", b"")


def test_specs_copy(server):
    c = server.client()
    r = c.get("/specs/STD")
    assert r.status_code == 200 and r.headers["content-type"] == "text/html; charset=utf-8"
    assert r.text.startswith(
        '<!doctype html><meta charset="utf-8"><title>STD</title><h1>STD</h1><ul>'
    )
    assert '<li><a href="/specs/STD/SYNC-STD-001.md">SYNC-STD-001.md</a></li>' in r.text
    r = c.get("/specs/STD/SYNC-STD-001.md")
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert r.text.startswith("---\ndoc_id: SYNC-STD-001")
    for path, rid in (
        ("/specs/10-MS/SYNC-MS-012.md", "10-MS/SYNC-MS-012.md"),
        ("/specs/STD/nope.md", "STD/nope.md"),
    ):
        r = c.get(path)
        assert r.status_code == 404
        assert (r.json()["resource"], r.json()["id"]) == ("specs", rid)
