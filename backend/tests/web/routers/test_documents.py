"""SYNC-API-001 3.4 — GET /api/docs/{docId} · POST /status(토글) · 참조 · ask(SSE)."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core import queries
from app.core.errors import LlmUnavailable
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.types import DocType, LlmStep, LlmUsage, ToolCall
from tests.core.reference.test_service import PRD, RFQ
from tests.core.spec.test_service import PRD as FULL_PRD
from tests.core.spec.test_service import author, make_project
from tests.core.test_pipeline import create
from tests.web.conftest import login


def _seed(scoped: Session):
    svc, ref = SpecService(scoped), ReferenceService(scoped)
    p = make_project(scoped)
    a = author(scoped)
    svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ, "h0", a, "spec: 테스트")
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    pks = {i.item_id: i.pk for i in d.items}
    ref.extract(d.id, v.id, d.body, pks, ["EXMP-RFQ-001"])
    return d


def test_get_document_upstream_references(client: TestClient, scoped: Session) -> None:
    login(client, scoped, "hoyoung")  # make_project의 소유자
    _seed(scoped)
    d = client.get("/api/docs/EXMP-PRD-001").json()
    assert (d["doc_id"], d["stage"], d["status"], d["current_version_no"], d["commit_hash"]) == (
        "EXMP-PRD-001",
        2,
        "draft",
        1,
        "h1",
    )
    # 항목마다 대상이 없는 참조의 raw_target (API-002 items[].missing_refs). R1 → Q9는 아직 없다
    assert d["items"] == [
        {"item_id": "G1", "display_name": "목표", "missing_refs": []},
        {"item_id": "R1", "display_name": "기능", "missing_refs": ["EXMP-RFQ-001#Q9"]},
    ]
    assert (
        d["prev_doc_id"] == "EXMP-RFQ-001"
        and d["body"] == PRD
        and d["last_author"]["kind"] == "agent"
    )
    assert client.get("/api/docs/EXMP-PRD-404").status_code == 404
    refs = client.get("/api/docs/EXMP-PRD-001/items/G1/references").json()
    assert sorted((r["doc_id"], r["item_id"]) for r in refs["upstream"]) == [
        ("EXMP-PRD-001", "R1"),
        ("EXMP-RFQ-001", "Q1"),
    ]
    assert "flags" not in refs
    r1 = client.get("/api/docs/EXMP-PRD-001/items/R1/references").json()
    assert r1["upstream"] == [
        {
            "doc_id": None,
            "item_id": None,
            "display_name": None,
            "raw_target": "EXMP-RFQ-001#Q9",
            "is_missing": True,
        }
    ]
    r = client.get("/api/docs/EXMP-PRD-001/items/R9/references")
    assert (
        r.status_code == 404 and r.json()["available_items"]
        if "available_items" in r.json()
        else r.status_code == 404
    )
    scoped.execute(text("UPDATE items SET is_deleted=true, deleted_at=now() WHERE item_id='R1'"))
    assert client.get("/api/docs/EXMP-PRD-001/items/R1/references").status_code == 410


async def test_change_status_via_api(client: TestClient, scoped: Session, proj) -> None:
    """토글 하나 — 초안 ⇄ 완료 (UC-H8). 상위 대조가 없고, 완료 게이트(status-blocked)만 남는다."""
    login(client, scoped)
    await create(proj, DocType.RFQ, RFQ)
    await create(proj, DocType.PRD, FULL_PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1"))
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["current_version_no"] == 1  # 상태 변경은 Version을 안 만든다
    # 검토중은 없다 — 값 자체가 안 받아진다
    assert client.post("/api/docs/EXMP-PRD-001/status", json={"to": "review"}).status_code == 422
    # 절이 빠진(미완성) 문서는 생성 직후부터 완료 불가
    incomplete = await create(
        proj,
        DocType.PRD,
        PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1").replace(
            "doc_id: EXMP-PRD-001", "doc_id: "
        ),
    )
    r = client.post(f"/api/docs/{incomplete.doc_id}/status", json={"to": "approved"})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:status-blocked"
    assert "section.missing: 비목표" in r.json()["warnings"]
    # 다시 초안으로. reason은 선택 — 이력(UI-7)에 남는다
    r = client.post("/api/docs/EXMP-PRD-001/status", json={"to": "draft", "reason": "다시 본다"})
    assert (
        r.status_code == 200
        and r.json()["status"] == "draft"
        and r.json()["current_version_no"] == 1
    )
    scoped.execute(
        text(
            "UPDATE documents SET has_convention_error=true, convention_error_detail='x' WHERE doc_id='EXMP-RFQ-001'"
        )
    )
    r = client.post("/api/docs/EXMP-RFQ-001/status", json={"to": "approved"})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:status-blocked"


def test_other_owner_document_is_not_found(client: TestClient, scoped: Session) -> None:
    """R12 — 남의 프로젝트 문서는 없는 것과 같다. 없는 문서와 답이 구분되지 않는다(UC-A2 1a)."""
    _seed(scoped)
    login(client, scoped, "minjun")
    r = client.get("/api/docs/EXMP-PRD-001")
    assert r.status_code == 404 and r.json()["type"] == "urn:syncdoc:not-found"
    assert (r.json()["resource"], r.json()["id"]) == ("project", "EXMP")
    assert client.get("/api/docs/EXMP-PRD-001/items/R1/references").status_code == 404
    assert client.get("/api/docs/EXMP-PRD-001/downstream").status_code == 404
    assert client.post("/api/docs/EXMP-PRD-001/status", json={"to": "approved"}).status_code == 404
    assert client.delete("/api/docs/EXMP-PRD-001").status_code == 404
    # 소유자에게는 그대로 열린다
    login(client, scoped, "hoyoung")
    assert client.get("/api/docs/EXMP-PRD-001").status_code == 200


def _sse(text: str) -> list[tuple[str, dict]]:
    """event:/data: 프레임 → (이름, JSON) 목록."""
    out = []
    for frame in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_ask_endpoint_streams_start_note_read_answer(
    client: TestClient, scoped: Session, monkeypatch
) -> None:
    """POST /api/docs/{docId}/ask (UC-H19, 카드 Y). SSE — 첫 이벤트 전 오류는 상태 코드, 뒤는 error 이벤트."""
    _seed(scoped)
    login(client, scoped, "hoyoung")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    steps: list = [
        LlmStep(
            None,
            [
                ToolCall(
                    "c1",
                    "get_item",
                    {"doc_id": "EXMP-PRD-001", "item_id": "G1", "reason": "G1을 읽는다"},
                )
            ],
            LlmUsage(),
        ),
        LlmStep("G1은 Q1을 근거로 한다", [], LlmUsage()),
    ]
    seen: list[list[dict]] = []

    async def step(system, messages, tools, tool_choice="auto"):
        seen.append(list(messages))
        return steps.pop(0)

    monkeypatch.setattr(queries.llm, "step", step)
    body = {
        "question": "이게 뭐야?",
        "history": [{"role": "user", "text": "앞"}, {"role": "assistant", "text": "답"}],
        "item_id": "G1",
    }
    r = client.post("/api/docs/EXMP-PRD-001/ask", json=body)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
    assert _sse(r.text) == [
        ("start", {"doc_id": "EXMP-PRD-001", "item_id": "G1"}),
        ("note", {"text": "G1을 읽는다"}),
        ("read", {"tool": "get_item", "target": "EXMP-PRD-001#G1"}),
        ("answer", {"answer": "G1은 Q1을 근거로 한다", "context_item_ids": ["EXMP-PRD-001#G1"]}),
    ]
    assert seen[0][-1] == {"role": "user", "text": "이게 뭐야?"} and len(seen[0]) == 3
    assert scoped.execute(text("SELECT count(*) FROM versions")).scalar() == 2  # 아무것도 안 쓴다

    # 항목 없이도 묻는다 — 문서 단위 시작
    steps.append(LlmStep("문서 전체 답", [], LlmUsage()))
    r = client.post("/api/docs/EXMP-PRD-001/ask", json={"question": "이 문서가 뭐야?"})
    assert _sse(r.text)[0] == ("start", {"doc_id": "EXMP-PRD-001", "item_id": None})

    # 루프 중 모델 실패 → 200 스트림 안 error 이벤트(problem+json 그대로)
    async def down(system, messages, tools, tool_choice="auto"):
        raise LlmUnavailable("HTTP 429")

    monkeypatch.setattr(queries.llm, "step", down)
    r = client.post("/api/docs/EXMP-PRD-001/ask", json={"question": "?"})
    assert r.status_code == 200
    ev = _sse(r.text)
    assert ev[0][0] == "start" and ev[1][0] == "error"
    assert ev[1][1]["type"] == "urn:syncdoc:llm-unavailable" and ev[1][1]["reason"] == "HTTP 429"

    # 키 없음 → 스트림 전 503 (상태 코드)
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    r = client.post("/api/docs/EXMP-PRD-001/ask", json={"question": "?"})
    assert r.status_code == 503 and r.json()["type"] == "urn:syncdoc:llm-not-configured"
    # 없는 항목 힌트 → 스트림 전 404
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    r = client.post("/api/docs/EXMP-PRD-001/ask", json={"question": "?", "item_id": "G9"})
    assert r.status_code == 404 and r.json()["resource"] == "item"
    # 남의 문서 → 404 (R12)
    login(client, scoped, "minjun")
    r = client.post("/api/docs/EXMP-PRD-001/ask", json={"question": "?"})
    assert r.status_code == 404 and r.json()["resource"] == "project"
    # 옛 경로는 없다
    login(client, scoped, "hoyoung")
    assert client.post(
        "/api/docs/EXMP-PRD-001/items/G1/ask", json={"question": "?"}
    ).status_code in (404, 405)
