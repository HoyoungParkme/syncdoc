"""CODE-001 B4 E2E — SYNC-SCN-001#S7(플랫폼 없이) + 복구 둘(UC-S6 재구축 · UC-H7 되돌리기).

GitHub에 직접 push → webhook → 문서 갱신 · 서버 꺼둔 뒤 push → 켜면 따라잡음(catch_up) · 플래그 있는 채로 재구축 →
참조 복원, 플래그 유지 · 되돌리기 → 새 버전 + 삭제 확인. GitHub 대신 임시 bare 저장소, 사람은 웹(TestClient).
"""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc import scheduler
from syncdoc.config import settings
from syncdoc.core.spec.service import SpecService
from tests.conftest import git as g
from tests.conftest import write_commit_push
from tests.core.reference.test_service import RFQ
from tests.core.test_pipeline import PRD_BODY, PRD_FILE, RFQ_FILE
from tests.web.conftest import login

SCN_FILE = "docs/specs/SCN/EXMP-SCN-001.md"
SCN = "---\ndoc_id: EXMP-SCN-001\ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [EXMP-PRD-001]\n---\n# 시나리오\n\n## 1. 페르소나\n\n#### P1 사람\n근거 [[EXMP-PRD-001#R1]]\n"


def _hook(client: TestClient, remote, head: str) -> int:
    body = json.dumps({"after": head, "repository": {"clone_url": str(remote)}}).encode()
    sig = "sha256=" + hmac.new(settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/hooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    ).status_code


async def test_s7_direct_push_catch_up_rebuild_and_revert(
    client: TestClient, scoped: Session, proj
) -> None:
    other, remote = proj["repos"]["other"], proj["repos"]["remote"]
    repo = proj["project"].repository
    repo.last_processed_commit = g(remote, "rev-parse", "main")
    scoped.flush()
    svc = SpecService(scoped)
    for f in (RFQ_FILE, PRD_FILE, SCN_FILE):
        (other / f).parent.mkdir(parents=True, exist_ok=True)

    # 1. 호영이 플랫폼 없이 RFQ·PRD를 직접 push → webhook → 새 버전, 참조 추출 (UC-G1)
    write_commit_push(other, RFQ_FILE, RFQ, "spec(EXMP-RFQ-001): 초안")
    write_commit_push(other, PRD_FILE, PRD_BODY, "spec(EXMP-PRD-001): 초안")
    assert _hook(client, remote, g(remote, "rev-parse", "main")) == 202
    prd = svc.get_document("EXMP-PRD-001")
    assert (prd.current_version_no, prd.last_author.via) == (1, "github")
    assert (
        scoped.execute(text('SELECT count(*) FROM "references" WHERE NOT is_missing')).scalar() == 2
    )

    # 2. 서버가 꺼진 사이(webhook 없음) 시나리오가 push됨 → 켜질 때 따라잡기 (UC-G1 1a)
    write_commit_push(other, SCN_FILE, SCN, "spec(EXMP-SCN-001): 초안")
    login(client, scoped)
    assert client.get("/api/admin/repos").json()[0]["behind_by"] == 1
    assert [r.doc_id for r in await scheduler.catch_up()] == ["EXMP-SCN-001"]
    assert client.get("/api/admin/repos").json()[0]["behind_by"] == 0

    # 3. 플래그·댓글이 있는 채로 재구축 → 참조·버전 복원, 플래그·댓글 유지 (UC-S6)
    write_commit_push(
        other, PRD_FILE, PRD_BODY.replace("한 줄로.", "두 줄로."), "spec(EXMP-PRD-001): 수정"
    )
    assert _hook(client, remote, g(remote, "rev-parse", "main")) == 202
    q1 = next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q1")
    from syncdoc.core.tracking.service import TrackingService

    TrackingService(scoped).raise_broken(q1)
    client.post("/api/docs/EXMP-PRD-001/comments", json={"line_no": 3, "body": "댓글"})
    scoped.commit()
    rb = client.post("/api/admin/repos/EXMP/rebuild").json()
    assert (rb["docs"], rb["versions"]) == (4, 5)  # 시드 SYNC-PRD-001 + RFQ 1 + PRD 2 + SCN 1
    assert scoped.execute(text("SELECT count(*) FROM flags")).scalar() == 1
    assert scoped.execute(text("SELECT count(*) FROM comments")).scalar() == 1
    assert scoped.execute(text('SELECT count(*) FROM "references" WHERE is_missing')).scalar() == 0
    vs = client.get("/api/docs/EXMP-PRD-001/versions").json()
    assert [v["version_no"] for v in vs] == [2, 1] and vs[0]["author"]["via"] == "github"
    gr = client.get("/api/projects/EXMP/graph").json()
    assert {
        "from": "EXMP-SCN-001#P1",
        "to": "EXMP-PRD-001#R1",
        "raw_target": "EXMP-PRD-001#R1",
        "is_missing": False,
    } in gr["edges"]

    # 4. 되돌리기 → 새 버전 (UC-H7). 직접 push로 R2가 생기고 시나리오가 R2를 참조한 뒤(밀린 커밋은 최종 상태 하나)
    #    R2 없는 버전으로 되돌리면 하위(SCN P2)가 있어 삭제 확인을 거친다 (UC-A6 4b)
    r = client.post("/api/docs/EXMP-PRD-001/revert", json={"to_version": 1})
    assert r.status_code == 201 and r.json()["version_no"] == 3
    assert "한 줄로." in svc.get_document("EXMP-PRD-001").body
    g(other, "pull", "-q", "--rebase", "origin", "main")  # 되돌리기 커밋이 원격에 먼저 들어갔다
    write_commit_push(other, PRD_FILE, PRD_BODY.replace("한 줄로.", "중간."), "spec: 중간")
    write_commit_push(other, PRD_FILE, PRD_BODY + "#### R2 둘째 기능\n내용\n", "spec: R2 추가")
    write_commit_push(
        other, SCN_FILE, SCN + "\n#### P2 개발자\n근거 [[EXMP-PRD-001#R2]]\n", "spec: P2"
    )
    assert _hook(client, remote, g(remote, "rev-parse", "main")) == 202
    prd = svc.get_document("EXMP-PRD-001")
    assert prd.current_version_no == 4 and [i.item_id for i in prd.items] == [
        "G1",
        "R1",
        "N1",
        "R2",
    ]
    assert svc.get_document("EXMP-SCN-001").current_version_no == 2
    r = client.post("/api/docs/EXMP-PRD-001/revert", json={"to_version": 3})
    assert r.status_code == 409 and r.json()["type"] == "urn:syncdoc:item-deletion-needs-confirm"
    assert r.json()["deleted_items"][0]["item_id"] == "R2"
    r = client.post(
        "/api/docs/EXMP-PRD-001/revert", json={"to_version": 3, "confirm_item_deletion": True}
    )
    assert r.status_code == 201 and r.json()["version_no"] == 5
    assert (
        scoped.execute(text("SELECT count(*) FROM flags WHERE kind='broken_ref'")).scalar() == 2
    )  # P2에 추가
    # 삭제된 R2 ID를 되살리는 본문(v4)으로는 못 돌아간다 — item.reused 규약 위반 (UC-H7 4a · MS-002 미결)
    r = client.post("/api/docs/EXMP-PRD-001/revert", json={"to_version": 4})
    assert r.status_code == 422 and r.json()["type"] == "urn:syncdoc:convention-violation"
    assert any(v["rule"] == "item.reused" for v in r.json()["violations"])
