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
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
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


def test_plain_file_is_kept_an_hour(client: TestClient, built: Path) -> None:
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=3600"


def test_path_escape_still_falls_to_the_shell(client: TestClient, built: Path) -> None:
    """경로 밖(`..`)은 파일로 주지 않는다 — 지금처럼 화면 틀."""
    r = client.get("/..%2Fsecret")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
