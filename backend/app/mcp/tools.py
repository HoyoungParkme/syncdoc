"""SYNC-API-002 — MCP 도구. core를 호출만 한다(한 묶음이면 서비스, 여럿이면 queries).

전송 streamable HTTP `POST /mcp`. 인증은 Bearer 토큰 → AccountService.authenticate_token(SEQ-C2) — web/mcp 미들웨어가
검증하고 여기서는 current_user_id로 받는다. 에러는 isError + problem+json(SYNC-API-001과 같은 형식).
B1: 도구 7개 전부. 쓰기 둘(create·update)은 pipeline.save_pipeline(entry=mcp)로.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from app import db
from app.core import pipeline, queries
from app.core.account.models import User
from app.core.errors import NotFound, Problem, Unauthorized
from app.core.markdown import masked_lines
from app.core.project.service import ProjectService
from app.core.spec.service import TYPES, patterns_for
from app.core.types import (
    STAGE_OF,
    Author,
    AuthorKind,
    Document,
    DocumentSummary,
    Entry,
    ItemView,
    ProjectSummary,
)
from app.infra import git

server = MCPServer(
    "syncdoc", instructions="싱크독 명세 도구. 쓰기 전에 get_template, 수정 전에 get_document."
)
current_user_id: ContextVar[int | None] = ContextVar("syncdoc_mcp_user_id", default=None)
_APP_SPECS = Path(__file__).resolve().parents[3] / "docs" / "specs"  # backend/app/mcp → 저장소 루트


def _problem(p: Problem) -> CallToolResult:
    return CallToolResult(
        is_error=True,
        content=[TextContent(type="text", text=json.dumps(p.to_dict(), ensure_ascii=False))],
    )


def _ok(data: Any) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(_plain(data), ensure_ascii=False))]
    )


def _plain(x: Any) -> Any:
    if is_dataclass(x) and not isinstance(x, type):
        return {k: _plain(v) for k, v in asdict(x).items()}
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_plain(v) for v in x]
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return x


def _user(session) -> User:
    uid = current_user_id.get()
    user = session.get(User, uid) if uid is not None else None
    if user is None:
        raise Unauthorized("토큰 없음")
    return user


def _agent_author(session) -> Author:
    """SEQ-C2 — 토큰으로 들어온 요청은 발급자 계정. kind=agent, instructed_by=발급자, via=mcp."""
    user = _user(session)
    return Author(kind=AuthorKind.agent, user=user, instructed_by=user, via=Entry.mcp)


def _author_json(d: DocumentSummary) -> dict | None:
    a = d.author
    if a is None:
        return None
    return {
        "kind": a.kind,
        "user": a.user.github_login if a.user else None,
        "instructed_by": a.instructed_by.github_login if a.instructed_by else None,
        "via": a.via,
    }


def _summary_json(d: DocumentSummary) -> dict:
    return {
        "doc_id": d.doc_id,
        "doc_type": d.doc_type,
        "stage": d.stage,
        "status": d.status,
        "version_no": d.current_version_no,
        "has_convention_error": d.has_convention_error,
        "incomplete_warnings": d.incomplete_warnings,
        "updated_at": d.updated_at.isoformat(),
        "last_author": _author_json(d),
        "counts": d.counts,
    }


def _project_json(p: ProjectSummary) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "remote_url": p.remote_url,
        "stages": [_plain(s) for s in p.stages],
        "std_docs": [_summary_json(d) for d in p.std_docs],
        "counts": p.counts,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@server.tool(
    description="GitHub 저장소를 싱크독 프로젝트로 등록한다. docs/specs/ 아래 11단계 디렉터리와 템플릿을 만들어 "
    "커밋한다. 새 프로젝트를 시작할 때 한 번만 부른다. 이미 등록된 저장소면 project-code-conflict, 저장소에 "
    "docs/specs/가 이미 있으면 existing-specs 에러가 나며 import_existing=true로 다시 부르면 기존 명세를 가져와 등록한다."
)
async def init_project(
    remote_url: str, code: str, name: str, import_existing: bool = False
) -> CallToolResult:
    """SYNC-API-002#init_project"""
    try:
        with db.session_scope() as s:
            await ProjectService(s).init_project(remote_url, code, name, _user(s), import_existing)
            s.commit()
        summary = next(p for p in await queries.project_summary() if p.code == code)
        return _ok(_project_json(summary))
    except Problem as p:
        return _problem(p)


@server.tool(
    description="프로젝트의 11단계별 문서 목록과 각 문서의 상태·버전을 돌려준다. 프로젝트에 처음 붙었거나 어느 단계까지 "
    "채워졌는지 알아야 할 때 부른다. 문서 본문은 포함하지 않는다. 본문은 get_document로."
)
async def list_documents(
    project_code: str, stage: int | None = None, status: str | None = None
) -> CallToolResult:
    """SYNC-API-002#list_documents"""
    try:
        with db.session_scope() as s:
            _user(s)
        docs = await queries.document_list(project_code, stage, status)
    except Problem as p:
        return _problem(p)
    stages = []
    for doc_type, n in STAGE_OF.items():
        if stage is not None and n != stage:
            continue
        mine = [d for d in docs if d.stage == n]
        order = {"draft": 0, "review": 1, "approved": 2}
        lowest = min((d.status for d in mine), key=lambda x: order[x], default=None)
        stages.append(
            {
                "stage": n,
                "doc_type": doc_type,
                "status": lowest,
                "doc_count": len(mine),
                "docs": [_summary_json(d) for d in mine],
            }
        )
    return _ok({"project_code": project_code, "stages": stages})


@server.tool(
    description="문서 원본 MD 전체와 상태·버전을 돌려준다. 명세를 근거로 작업하기 전에 부른다. 응답의 version_no를 "
    "기억했다가 update_document에 expected_version으로 보내야 한다. status가 approved가 아니면 확정 명세가 아니다. "
    "본문 안 [[문서ID#항목ID]]는 다른 항목 참조이며 get_item으로 따라갈 수 있다."
)
async def get_document(doc_id: str) -> CallToolResult:
    """SYNC-API-002#get_document"""
    try:
        with db.session_scope() as s:
            _user(s)
        d: Document = await queries.document_view(doc_id)
    except Problem as p:
        return _problem(p)
    return _ok(
        {
            **_summary_json(d),
            "commit_hash": d.commit_hash,
            "convention_error_detail": d.convention_error_detail,
            "body": d.body,
            "items": [
                {"item_id": i.item_id, "display_name": i.display_name, "flags": i.flags}
                for i in d.items
            ],
            "prev_doc_id": d.prev_doc_id,
            "next_doc_id": d.next_doc_id,
        }
    )


@server.tool(
    description="문서 안 항목 하나의 본문 블록과 소속 문서의 상태·버전을 돌려준다. get_document로 문서 전체를 받는 대신 "
    "필요한 항목만 볼 때, 또는 본문에서 발견한 [[문서ID#항목ID]] 참조를 따라갈 때 부른다. 삭제된 항목이면 item-deleted "
    "에러에 삭제 시점이 담긴다."
)
async def get_item(doc_id: str, item_id: str) -> CallToolResult:
    """SYNC-API-002#get_item"""
    try:
        with db.session_scope() as s:
            _user(s)
        v: ItemView = await queries.item_view(doc_id, item_id)
    except Problem as p:
        return _problem(p)
    return _ok(
        {
            "doc_id": v.doc_id,
            "item_id": v.item_id,
            "display_name": v.display_name,
            "doc_status": v.doc_status,
            "doc_version_no": v.doc_version_no,
            "body": v.body,
            "flags": v.flags,
        }
    )


@server.tool(
    description="항목의 상위 참조(이 항목이 근거로 삼은 것)와 하위 참조(이 항목을 근거로 삼은 것)를 나눠 돌려준다. "
    "이 항목이 왜 있는지, 바꾸면 어디에 영향이 가는지 알아야 할 때 부른다. 목록만 주고 본문은 펼치지 않는다. "
    "필요한 항목만 get_item으로 다시 요청한다. 빈 목록이면 고립 항목이다."
)
async def get_references(doc_id: str, item_id: str) -> CallToolResult:
    """SYNC-API-002#get_references"""
    try:
        with db.session_scope() as s:
            _user(s)
        r = await queries.item_references_view(doc_id, item_id)
    except Problem as p:
        return _problem(p)

    def ref(x) -> dict:
        return {
            "doc_id": x.doc_id,
            "item_id": x.item_id,
            "display_name": x.display_name,
            "raw_target": x.raw_target,
            "is_missing": x.is_missing,
        }

    return _ok(
        {
            "doc_id": r.doc_id,
            "item_id": r.item_id,
            "upstream": [ref(x) for x in r.upstream],
            "downstream": [ref(x) for x in r.downstream],
            "flags": [
                {
                    "kind": f.kind,
                    "cause": f"{f.cause.doc_id}#{f.cause.item_id}" if f.cause else None,
                    "cause_version_no": f.cause_version_no,
                    "raised_at": f.raised_at,
                }
                for f in r.flags
            ],
        }
    )


def _section(text: str, heading_prefix: str) -> str:
    """'## N. 제목' 절 하나. 다음 '## '까지. 코드블록 안 헤딩은 무시(마스킹)."""
    lines = text.split("\n")
    masked = masked_lines(text)
    start = next((i for i, m in enumerate(masked) if m.startswith(f"## {heading_prefix}")), None)
    if start is None:
        return ""
    end = next(
        (i for i in range(start + 1, len(masked)) if masked[i].startswith("## ")), len(lines)
    )
    return "\n".join(lines[start:end]).strip()


def _block_structure(std_text: str, doc_type: str, title_key: str | None) -> str:
    """STD-001 2장의 타입 표에서 '항목 블록' 행."""
    sec = _section(std_text, "2.")
    part = re.split(r"^### 2\.\d+ ", sec, flags=re.M)
    for chunk in part[1:]:
        if not chunk.startswith(doc_type):
            continue
        if title_key and title_key not in chunk:
            continue
        m = re.search(r"^\| 항목 블록 \| (.+?) \|$", chunk, re.M)
        if m:
            return m.group(1)
    return ""


@server.tool(
    description="문서 타입의 템플릿과 작성 규약을 돌려준다. create_document 전에 반드시 부른다. 반환에는 (1) 그 타입의 "
    "항목 ID 패턴·필수 절·항목 블록 구조, (2) 템플릿 MD 뼈대, (3) 채워진 예시가 담긴다. 항목은 ID로 시작하는 헤딩이어야 "
    "하고, 표 행은 항목이 아니며, 번호에 패딩을 두지 않는다는 공통 규약도 함께 온다."
)
async def get_template(project_code: str, doc_type: str) -> CallToolResult:
    """SYNC-API-002#get_template"""
    try:
        if doc_type not in TYPES:
            raise NotFound("doc_type", doc_type)
        with db.session_scope() as s:
            _user(s)
            workdir = Path(ProjectService(s).get(project_code).repository.workdir_path)
        template = await _read_spec_file(workdir, f"docs/specs/_templates/{doc_type}.md")
        std = await _read_spec_file(workdir, "docs/specs/STD/SYNC-STD-001.md")  # STD는 번호 없음
    except Problem as p:
        return _problem(p)
    item_re, secs = patterns_for(doc_type, None)
    return _ok(
        {
            "doc_type": doc_type,
            "common_rules": _section(std, "1."),
            "type_rules": {
                "item_patterns": TYPES[doc_type][0],
                "required_sections": secs,
                "block_structure": _block_structure(std, doc_type, None),
            },
            "template": template,
            "example": _section(std, "5."),
        }
    )


async def _read_spec_file(workdir: Path, path: str) -> str:
    """프로젝트 저장소의 파일. 없으면 앱에 내장된 사본(docs/specs/)으로."""
    try:
        return await git.read(workdir, path)
    except (git.GitError, OSError):  # 작업 사본이 없거나(OSError) 파일이 없으면(GitError) 내장 사본
        local = _APP_SPECS / path.removeprefix("docs/specs/")
        if local.exists():
            return local.read_text(encoding="utf-8")
        raise NotFound("file", path) from None


@server.tool(
    description="새 문서를 만든다. 문서 ID는 서버가 발급한다({코드}-{타입}-{번호}). 저장소의 docs/specs/_templates/ 템플릿이 적용되므로 body는 템플릿 구조를 따라야 한다. 항목 ID(#R12 같은 것)는 body에 직접 붙인다. 서버는 발급하지 않고 형식·유일성만 검사한다. 기존 문서를 고치려면 이 도구가 아니라 update_document를 써야 한다."
)
async def create_document(
    project_code: str,
    doc_type: str,
    body: str,
    message: str,
    upstream_impact: list[str] | None = None,
) -> CallToolResult:
    """SYNC-API-002#create_document"""
    try:
        with db.session_scope() as s:
            author = _agent_author(s)
        r = await pipeline.save_pipeline(
            Entry.mcp,
            None,
            doc_type,
            body,
            None,
            project_code,
            author,
            message,
            upstream_impact=upstream_impact,
        )
    except Problem as p:
        return _problem(p)
    return _ok(r.to_dict())


@server.tool(
    description="기존 문서의 본문을 교체해 새 버전을 만든다. 반드시 get_document로 받은 version_no를 expected_version에 넣어야 한다. 그 사이 문서가 바뀌었으면 version-conflict 에러에 현재 버전과 본문이 담기니, 그것을 읽고 병합해 다시 부른다. 본문에서 항목 ID가 사라지면 하위 참조 목록과 함께 item-deletion-needs-confirm 에러가 나며, 사람에게 확인받은 뒤 confirm_item_deletion=true로 다시 부른다. 저장 후 하위에 영향이 있으면 결과의 pending_decision_version_id가 채워지고, 전파 여부는 지시한 사람이 웹에서 결정한다. 승인 상태 문서를 고치면 검토중으로 내려간다. 이 변경이 상위 항목과 어긋나게 됐음을 알면 upstream_impact에 그 상위 항목을 넣는다."
)
async def update_document(
    doc_id: str,
    body: str,
    expected_version: int,
    message: str,
    changed_items: list[str],
    upstream_impact: list[str] | None = None,
    confirm_item_deletion: bool = False,
) -> CallToolResult:
    """SYNC-API-002#update_document"""
    try:
        with db.session_scope() as s:
            author = _agent_author(s)
        r = await pipeline.save_pipeline(
            Entry.mcp,
            doc_id,
            None,
            body,
            expected_version,
            None,
            author,
            message,
            changed_items=changed_items,
            upstream_impact=upstream_impact,
            confirm_item_deletion=confirm_item_deletion,
        )
    except Problem as p:
        return _problem(p)
    return _ok(r.to_dict())
