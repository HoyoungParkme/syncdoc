"""CODE-001 B3 E2E — SYNC-SCN-001#S4 흐름 그대로.

에이전트가 PRD R1 수정(changed_items) → 호영 내 할 일에 전파 미결정 → 예 → 하위 4건 플래그 → 민준 내 할 일
→ 확인 처리(수정 없음·수정 동반 둘 다) · 항목 삭제 → 끊어진 참조 · API가 어긋남 지정(upstream_impact) → 하위 불일치.
GitHub 대신 임시 bare 저장소, 에이전트 저장은 MCP(인프로세스)·pipeline, 사람은 웹(TestClient).
"""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import pipeline
from app.core.spec.service import SpecService
from app.core.types import Author, AuthorKind, DocType, Entry
from app.mcp import tools
from tests.core.account.test_service import make_user
from tests.core.reference.test_service import RFQ
from tests.core.spec.test_service import PRD
from tests.core.test_pipeline import create
from tests.mcp.test_tools import call
from tests.web.conftest import login

PRD_BODY = PRD.replace("EXMP-RFQ-001#Q2", "EXMP-RFQ-001#Q1")
SCN_BODY = """---
doc_id:
type: SCN
title: 시나리오
status: draft
upstream: [EXMP-PRD-001]
---

# 시나리오

## 1. 페르소나

#### P1 기획자
근거 [[EXMP-PRD-001#R1]]

#### P2 개발자
근거 [[EXMP-PRD-001#R1]]

## 2. 시나리오

#### S1 첫 흐름
근거 [[EXMP-PRD-001#R1]]

#### S2 둘째 흐름
근거 [[EXMP-PRD-001#R1]]

## 3. 대응표
"""


async def _mcp(user_id: int, tool: str, **args):
    ctx = tools.current_user_id.set(user_id)
    try:
        return await call(tool, **args)
    finally:
        tools.current_user_id.reset(ctx)


async def test_s4_change_propagates_to_downstream_owner(
    client: TestClient, scoped: Session, proj
) -> None:
    svc = SpecService(scoped)
    hoyoung = proj["user"]
    minjun = make_user(scoped, login="minjun")
    minjun_agent = Author(kind=AuthorKind.agent, user=minjun, instructed_by=minjun, via=Entry.mcp)
    # 호영의 에이전트가 RFQ·PRD, 민준의 에이전트가 PRD#R1을 근거로 시나리오 4항목
    await create(proj, DocType.RFQ, RFQ)
    await create(proj, DocType.PRD, PRD_BODY)
    scn = await pipeline.save_pipeline(
        Entry.mcp, None, DocType.SCN, SCN_BODY, None, "EXMP", minjun_agent, "spec(SCN): 시나리오"
    )
    assert (
        scn.doc_id == "EXMP-SCN-001" and scn.pending_decision_version_id is None
    )  # 신규 (UC-S3 1a)

    # 1. 에이전트가 PRD R1을 고친다 (MCP, changed_items) → 전파 미결정
    err, r = await _mcp(
        hoyoung.id,
        "update_document",
        doc_id="EXMP-PRD-001",
        body=PRD_BODY.replace("설명. 근거", "바뀐 설명. 근거"),
        expected_version=1,
        message="spec(EXMP-PRD-001): R1 설명 변경",
        changed_items=["R1"],
    )
    assert not err and r["version_no"] == 2 and r["pending_decision_version_id"] is not None
    vid = r["pending_decision_version_id"]

    # 2. 호영 내 할 일 → 전파 미결정 → 상세(UI-12) → 예 → 하위 4건 플래그 (UC-H10 → UC-S4)
    login(client, scoped, "hoyoung")
    td = client.get("/api/todo").json()
    assert td["total"] == 1 and td["pending_decisions"][0] == {
        **td["pending_decisions"][0],
        "version_id": vid,
        "doc_id": "EXMP-PRD-001",
        "version_no": 2,
        "affected_count": 4,
    }
    dv = client.get(f"/api/decisions/{vid}").json()
    assert [h["item_id"] for h in dv["change_diff"]["hunks"]] == ["R1"]
    assert sorted(a["item_id"] for a in dv["affected"]) == ["P1", "P2", "S1", "S2"]
    assert {(a["caused_by_items"][0], a["assignee"]["github_login"]) for a in dv["affected"]} == {
        ("R1", "minjun")
    }
    assert client.post(f"/api/decisions/{vid}", json={"choice": "propagate"}).json() == {
        "choice": "propagate",
        "flags_raised": 4,
    }
    assert client.get("/api/todo").json()["total"] == 0

    # 3. 민준 내 할 일 → 확인 필요 4건 (UC-H15) → 수정 없음으로 확인 (UC-H11 3b)
    login(client, scoped, "minjun")
    td = client.get("/api/todo").json()
    flags = td["needs_check"]
    assert td["total"] == 4 and {f["cause"]["item_id"] for f in flags} == {"R1"}
    f1 = client.get(f"/api/flags/{flags[0]['id']}").json()
    assert (f1["cause_change_count"], f1["target_changed_since_raise"]) == (0, False)
    assert [ln["op"] for ln in f1["cause_diff"]["hunks"]] == [] and f1["target_body"].startswith(
        "#### P1"
    )
    assert client.post(f"/api/flags/{flags[0]['id']}/resolve").json()["resolved_at"] is not None
    # 4. 에이전트에게 시나리오를 고치게 한 뒤 확인 → 수정 동반 (UC-H11 4~6)
    scn_doc = svc.get_document("EXMP-SCN-001")
    await pipeline.save_pipeline(
        Entry.mcp,
        "EXMP-SCN-001",
        None,
        scn_doc.body.replace("#### P2 개발자\n근거", "#### P2 개발자\n바뀐 근거"),
        1,
        None,
        minjun_agent,
        "spec(EXMP-SCN-001): P2 반영",
        changed_items=[],
    )
    assert client.get(f"/api/flags/{flags[1]['id']}").json()["target_changed_since_raise"] is True
    client.post(f"/api/flags/{flags[1]['id']}/resolve")
    assert scoped.execute(
        text("SELECT resolved_with_edit FROM flags WHERE resolved_at IS NOT NULL ORDER BY id")
    ).scalars().all() == [False, True]
    assert client.get("/api/todo").json()["total"] == 2

    # 5. 호영의 에이전트가 R1을 삭제 → 확인 요구 → 확인 후 저장 → 하위 4건 끊어진 참조 (UC-H13)
    prd = svc.get_document("EXMP-PRD-001")
    start, end = prd.body.index("#### R1 첫 기능"), prd.body.index("### 3.2")
    without_r1 = prd.body[:start] + prd.body[end:]
    err, r = await _mcp(
        hoyoung.id,
        "update_document",
        doc_id="EXMP-PRD-001",
        body=without_r1,
        expected_version=2,
        message="spec(EXMP-PRD-001): R1 삭제",
        changed_items=[],
    )
    assert err and r["type"] == "urn:syncdoc:item-deletion-needs-confirm"
    assert (
        r["deleted_items"][0]["item_id"] == "R1" and len(r["deleted_items"][0]["downstream"]) == 4
    )
    err, r = await _mcp(
        hoyoung.id,
        "update_document",
        doc_id="EXMP-PRD-001",
        body=without_r1,
        expected_version=2,
        message="spec(EXMP-PRD-001): R1 삭제",
        changed_items=[],
        confirm_item_deletion=True,
    )
    assert not err and r["version_no"] == 3
    td = client.get("/api/todo").json()
    assert (len(td["broken_ref"]), td["total"]) == (4, 6)
    bv = client.get(f"/api/flags/{td['broken_ref'][0]['id']}").json()
    assert (
        bv["cause"]["item_id"] == "R1"
        and bv["cause_deleted_at"] is not None
        and bv["cause_diff"] is None
    )

    # 6. 민준의 에이전트가 저장하며 상위 G1이 어긋났다고 지정 → G1(호영)에 하위 불일치 (UC-S4 · UC-A6)
    scn_doc = svc.get_document("EXMP-SCN-001")
    r2 = await pipeline.save_pipeline(
        Entry.mcp,
        "EXMP-SCN-001",
        None,
        scn_doc.body + "\n",
        2,
        None,
        minjun_agent,
        "spec(EXMP-SCN-001): G1 어긋남",
        changed_items=[],
        upstream_impact=["EXMP-PRD-001#G1"],
    )
    assert r2.version_no == 3
    login(client, scoped, "hoyoung")
    td = client.get("/api/todo").json()
    assert [(f["kind"], f["target"]["item_id"]) for f in td["upstream_impact"]] == [
        ("upstream_impact", "G1")
    ]
    uv = client.get(f"/api/flags/{td['upstream_impact'][0]['id']}").json()
    assert uv["cause_body"] == "시나리오 (문서 단위 지목)" and uv["cause_version_no"] == 3
    assert td["total"] == 1
