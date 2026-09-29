"""SYNC-API-001 3.5 — 첨부 올리기·바이트·빼기 (카드 AR)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.conversation.service import ConversationService
from tests.core.conversation.test_attachments import PNG
from tests.core.spec.test_service import make_project
from tests.web.conftest import login


def test_upload_get_delete_and_errors(client: TestClient, scoped: Session) -> None:
    make_project(scoped)
    login(client, scoped, "hoyoung")
    conv = client.post("/api/projects/EXMP/conversations", json={}).json()["id"]
    r = client.post(f"/api/conversations/{conv}/attachments", files={"file": ("메모.md", "# 메모".encode(), "text/markdown")})
    assert r.status_code == 201
    meta = r.json()
    assert meta["name"] == "메모.md" and meta["mime"] == "text/markdown" and meta["size"] == len("# 메모".encode()) and meta["turn_id"] is None
    r = client.post(f"/api/conversations/{conv}/attachments", files={"file": ("캡처.png", PNG, "image/png")})
    assert r.status_code == 201
    png = r.json()["id"]
    # 바이트 그대로 + 미리보기 헤더
    r = client.get(f"/api/attachments/{png}")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"].startswith("image/png")
    assert r.headers["content-disposition"].startswith("inline;") and r.headers["cache-control"] == "private, max-age=3600"
    # 대화 조회에 pending으로
    c = client.get(f"/api/conversations/{conv}").json()
    assert [m["name"] for m in c["pending"]] == ["메모.md", "캡처.png"] and "bytes" not in str(c)
    # 오류 셋
    r = client.post(f"/api/conversations/{conv}/attachments", files={"file": ("a.exe", b"x", "application/octet-stream")})
    assert r.status_code == 415 and r.json()["type"] == "urn:syncdoc:attachment-type"
    r = client.post(f"/api/conversations/{conv}/attachments", files={"file": ("big.md", b"x" * (1024 * 1024 + 1), "text/markdown")})
    assert r.status_code == 413 and r.json()["type"] == "urn:syncdoc:attachment-too-large" and r.json()["limit"] == 1024 * 1024
    for i in range(6):
        assert client.post(f"/api/conversations/{conv}/attachments", files={"file": (f"f{i}.txt", b"x", "text/plain")}).status_code == 201
    r = client.post(f"/api/conversations/{conv}/attachments", files={"file": ("f9.txt", b"x", "text/plain")})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:attachment-limit"
    # 빼기 — 안 보낸 것만
    assert client.delete(f"/api/attachments/{meta['id']}").status_code == 204
    assert client.get(f"/api/attachments/{meta['id']}").status_code == 404
    svc = ConversationService(scoped)
    svc.add_turn(conv, "q", [png])
    scoped.flush()
    r = client.delete(f"/api/attachments/{png}")
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:attachment-sent"
    # 남의 것은 없는 것과 같다
    login(client, scoped, "minjun")
    assert client.get(f"/api/attachments/{png}").status_code == 404
    assert client.post(f"/api/conversations/{conv}/attachments", files={"file": ("x.md", b"x", "text/markdown")}).status_code == 404
