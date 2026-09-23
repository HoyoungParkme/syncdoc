"""SYNC-INFRA-001 4.1 — 정적 파일 캐시 규칙 (#124).

서버가 캐시 규칙을 말하지 않아 배포 뒤에도 옛 화면이 떴다. 번들 폴더에 없는 파일은
화면 틀(index.html)로 떨어져, 옛 탭이 HTML을 스크립트로 읽다 깨졌다.
빌드 결과에 기대지 않도록 임시 폴더를 빌드 결과인 척 끼운다.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "index-Ab12Cd34.js").write_text("export {}", encoding="utf-8")
    (tmp_path / "howto").mkdir()
    (tmp_path / "howto" / "term-add.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(main, "STATIC", tmp_path)
    return tmp_path


def test_shell_revalidates_every_time(client: TestClient, built: Path) -> None:
    """화면 틀은 매번 새 판인지 묻는다 — 배포하면 다음 요청에 새 번들을 가리킨다."""
    for url in ("/", "/index.html", "/p/SYNC/d/SYNC-PRD-001"):
        r = client.get(url)
        assert r.status_code == 200 and "id=root" in r.text, url
        assert r.headers["cache-control"] == "no-cache", url


def test_hashed_bundle_is_immutable(client: TestClient, built: Path) -> None:
    r = client.get("/assets/index-Ab12Cd34.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_missing_bundle_is_404_not_the_shell(client: TestClient, built: Path) -> None:
    """번들 폴더에 없는 파일을 화면 틀로 떨어뜨리지 않는다. 저장도 하지 않게."""
    r = client.get("/assets/index-Gone9999.js")
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"
    assert "id=root" not in r.text


def test_plain_file_revalidates_every_time(client: TestClient, built: Path) -> None:
    """이름이 안 바뀌는 그림(사용 방법)은 매번 묻는다 — 바꿔도 옛 그림이 보였다 (#151)."""
    r = client.get("/howto/term-add.png")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    # 바뀌지 않았으면 본문 없이 304 — 매번 묻는 값이 싸다. 에지가 붙이는 약한 표시(W/)도 같다
    etag = r.headers["etag"]
    for asked in (etag, f"W/{etag}", f'"other", {etag}'):
        again = client.get("/howto/term-add.png", headers={"If-None-Match": asked})
        assert again.status_code == 304 and again.content == b"", asked
        assert again.headers["cache-control"] == "no-cache" and again.headers["etag"] == etag
    # 바뀌었으면(다른 ETag) 새 본문
    assert client.get("/howto/term-add.png", headers={"If-None-Match": '"old"'}).status_code == 200


def test_shell_answers_304_when_unchanged(client: TestClient, built: Path) -> None:
    """화면 틀도 같은 규칙 — 서버가 304를 돌려준다 (#151, INFRA 4.1).

    Cloudflare를 거친 화면 틀에는 ETag가 떨어져 브라우저는 수정 시각으로만 묻는다.
    """
    first = client.get("/")
    r = client.get("/p/SYNC", headers={"If-None-Match": first.headers["etag"]})
    assert r.status_code == 304 and r.headers["cache-control"] == "no-cache"
    since = first.headers["last-modified"]
    assert client.get("/p/SYNC", headers={"If-Modified-Since": since}).status_code == 304
    before = "Thu, 01 Jan 1970 00:00:00 GMT"
    assert client.get("/p/SYNC", headers={"If-Modified-Since": before}).status_code == 200
    assert client.get("/p/SYNC", headers={"If-Modified-Since": "not a date"}).status_code == 200


def test_path_escape_still_falls_to_the_shell(client: TestClient, built: Path) -> None:
    """경로 밖(`..`)은 파일로 주지 않는다 — 지금처럼 화면 틀."""
    r = client.get("/..%2Fsecret")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
