"""SYNC-MS-007 — pipeline. 쓰기 조율. 자기 테이블이 없고 서비스를 순서대로 부른다.

세 입구(MCP·웹·GitHub)가 전부 save_pipeline로 들어온다. 저장소 단위 asyncio.Lock(프로세스 내).
세션은 여기서 연다(DEV-10 — 서비스는 세션을 열지 않는다). push가 DB 트랜잭션 앞이다.
B1: save_pipeline · B2: web_status 분기(apply_status) · change_status(조율 — SpecService에서 옮김).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sqlalchemy.orm import Session

from syncdoc import db
from syncdoc.core.account.models import User
from syncdoc.core.collab.service import CommentService
from syncdoc.core.errors import (
    AlreadyCurrent,
    ConventionViolation,
    ItemDeleted,
    ItemDeletionNeedsConfirm,
    NotFound,
    StatusBlocked,
    UpstreamReviewRequired,
    VersionConflict,
)
from syncdoc.core.markdown import parse_frontmatter
from syncdoc.core.project.service import ProjectService
from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import (
    Author,
    AuthorKind,
    DocStatus,
    DocType,
    DocumentSummary,
    Entry,
    SaveResult,
)
from syncdoc.infra import git

_locks: dict[str, asyncio.Lock] = {}


def _lock(code: str) -> asyncio.Lock:
    return _locks.setdefault(code, asyncio.Lock())


async def save_pipeline(
    entry: Entry,
    doc_id: str | None,
    doc_type: DocType | None,
    body: str,
    expected_version: int | None,
    project_code: str | None,
    author: Author,
    message: str,
    changed_items: list[str] | None = None,
    upstream_impact: list[str] | None = None,
    confirm_item_deletion: bool = False,
    commit_hash: str | None = None,
    reason: str | None = None,
    session: Session | None = None,
) -> SaveResult:
    """SYNC-MS-007#pipeline.save_pipeline"""
    code = project_code if doc_id is None else doc_id.split("-")[0]
    if code is None:
        raise NotFound("project", "None")
    args = (
        entry,
        doc_id,
        doc_type,
        body,
        expected_version,
        code,
        author,
        message,
        changed_items,
        upstream_impact,
        confirm_item_deletion,
        commit_hash,
        reason,
    )
    async with _lock(code):
        if session is not None:  # change_status·revert가 넘긴 세션 — 같은 세션에서
            return await _run(session, *args)
        with db.session_scope() as s:
            return await _run(s, *args)


async def _run(
    s: Session,
    entry: Entry,
    doc_id: str | None,
    doc_type: DocType | None,
    body: str,
    expected_version: int | None,
    code: str,
    author: Author,
    message: str,
    changed_items: list[str] | None,
    upstream_impact: list[str] | None,
    confirm_item_deletion: bool,
    commit_hash: str | None,
    reason: str | None,
) -> SaveResult:
    """save_pipeline 본체 — 락·세션 안."""
    spec, refs = SpecService(s), ReferenceService(s)
    tracking, collab = TrackingService(s), CommentService(s)
    project = ProjectService(s).get(code)
    repo = project.repository
    # 2·3. 대상 문서 또는 생성
    document = None
    if doc_id is not None:
        document = spec.get_document(doc_id)
        doc_type = document.doc_type
    else:
        assert doc_type is not None
        doc_id = spec.issue_doc_id(project.id, code, doc_type)
        body = spec.apply_frontmatter(body, doc_id, doc_type, DocStatus.draft)
    # 4. 규약
    vr = spec.validate(body, doc_type, entry, document.status if document else None)
    if vr.violations and entry != Entry.github:
        raise ConventionViolation(vr.violations, vr.warnings)
    # 5. 버전
    if entry != Entry.github and document and expected_version != document.current_version_no:
        raise VersionConflict(document.current_version_no, document.body)
    # 6. 삭제 확인
    deleted: list[int] = []
    if entry != Entry.web_status and document:
        deleted = spec.detect_deleted_items(document, body)
        downstream = {pk: refs.downstream(pk) for pk in deleted}
        if any(downstream.values()) and not confirm_item_deletion:
            names = {i.pk: i.item_id for i in document.items}
            raise ItemDeletionNeedsConfirm(
                [
                    {
                        "item_id": names[pk],
                        "downstream": [e.from_item_pk for e in edges if e.from_item_pk],
                    }
                    for pk, edges in downstream.items()
                    if edges
                ]
            )
    # 7. push — 여기까지 DB 쓰기 없음
    if entry != Entry.github:
        commit_hash = await git.commit_push(
            Path(repo.workdir_path),
            message,
            author,
            path=f"docs/specs/{doc_type}/{doc_id}.md",
            content=body,
        )
    assert commit_hash is not None
    # 8. 트랜잭션
    if entry == Entry.web_status:
        assert document is not None
        spec.apply_status(document, body, commit_hash, author.user, reason)
        collab.relocate(document.id, document.body, body, document.current_version_no)
        s.commit()
        return SaveResult(
            doc_id,
            document.current_version_no,
            commit_hash,
            spec.get_document(doc_id).status,
            None,
            [],
        )
    if document is None:
        version = spec.create(
            project.id, doc_id, doc_type, body, commit_hash, author, message, validate_result=vr
        )
        prev_version_id = None
    else:
        prev_version_id = document.current_version_id
        version = spec.save(
            document,
            body,
            commit_hash,
            author,
            message,
            deleted,
            validate_result=vr,  # 모든 경로 — 경고가 mcp 저장에도 남아야 승인을 막는다
        )
    document_id = version.document_id
    # 9. 끊어진 참조
    for pk in deleted:
        tracking.raise_broken(pk)
    # 10. 참조 추출
    item_pks = spec.item_pks(document_id)
    fm, _ = parse_frontmatter(body)
    upstream_ids = re.findall(r"[\w-]+", fm.get("upstream", "").strip("[]"))
    refs.extract(document_id, version.id, body, item_pks, upstream_ids)
    # 11. 변경 영향 → 전파 미결정 (UC-S3 3)
    affected = tracking.detect_impact(document_id, prev_version_id, version.id, changed_items)
    pending_id = None
    if affected:
        assert document is not None
        ids = (
            changed_items
            if changed_items is not None
            else [
                h.item_id
                for h in spec.diff(doc_id, document.current_version_no, version.version_no).hunks
                if h.item_id
            ]
        )
        tracking.create_pending(version.id, affected, spec.resolve_items(doc_id, ids))
        pending_id = version.id
    # 12. 하위→상위 되먹임
    warnings = [str(w) for w in vr.warnings]
    if upstream_impact:
        target_pks = []
        for target in upstream_impact:
            d, _, i = target.partition("#")
            try:
                target_pks.append(spec.resolve_item(d, i))
            except (NotFound, ItemDeleted):
                warnings.append(f"upstream_impact.unknown: {target}")
        if target_pks:
            tracking.raise_upstream(target_pks, document_id, version.id, None)
    # 13. 댓글 줄 이동
    if document is not None:
        collab.relocate(document_id, document.body, body, document.current_version_no)
    # 14. 커밋
    s.commit()
    status = spec.get_document(doc_id).status
    return SaveResult(doc_id, version.version_no, commit_hash, status, pending_id, warnings)


async def change_status(
    doc_id: str,
    to: DocStatus,
    user: User,
    reason: str | None,
    upstream_reviewed: bool = False,
    upstream_mismatch: list[str] = [],  # noqa: B006 — MINISPEC 시그니처 그대로
) -> DocumentSummary:
    """SYNC-MS-007#pipeline.change_status"""
    with db.session_scope() as s:
        spec = SpecService(s)
        document = spec.get_document(doc_id)
        if to == DocStatus.approved and (
            document.has_convention_error or document.incomplete_warnings
        ):
            raise StatusBlocked(document.convention_error_detail, document.incomplete_warnings)
        if to == DocStatus.approved and not upstream_reviewed:
            raise UpstreamReviewRequired()
        if document.status == to:
            return document
        new_body = re.sub(r"^status: .*$", f"status: {to}", document.body, count=1, flags=re.M)
        author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.web_status)
        await save_pipeline(
            Entry.web_status,
            doc_id,
            None,
            new_body,
            document.current_version_no,
            None,
            author,
            f"status({doc_id}): {document.status} → {to}\n\n{reason or ''}",
            reason=reason,
            session=s,
        )
        if upstream_mismatch:
            pks = [spec.resolve_item(*t.partition("#")[::2]) for t in upstream_mismatch]
            TrackingService(s).raise_upstream(pks, document.id, document.current_version_id, None)
            s.commit()
        return spec.get_document(doc_id)


async def revert(
    doc_id: str, to_version: int, user: User, confirm_item_deletion: bool = False
) -> SaveResult:
    """SYNC-MS-007#pipeline.revert"""
    with db.session_scope() as s:
        spec = SpecService(s)
        document = spec.get_document(doc_id)
        old_body = spec.version_body(doc_id, to_version)
        if to_version == document.current_version_no:
            raise AlreadyCurrent()
        author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.web_revert)
        return await save_pipeline(
            Entry.web_revert,
            doc_id,
            None,
            old_body,
            document.current_version_no,
            None,
            author,
            f"revert({doc_id}): v{document.current_version_no} → v{to_version} 내용으로",
            confirm_item_deletion=confirm_item_deletion,
            session=s,
        )
