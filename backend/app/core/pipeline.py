"""SYNC-MS-007 — pipeline. 쓰기 조율. 자기 테이블이 없고 서비스를 순서대로 부른다.

세 입구(MCP·웹·GitHub)가 전부 save_pipeline로 들어온다. 저장소 단위 asyncio.Lock(프로세스 내).
세션은 여기서 연다(DEV-10 — 서비스는 세션을 열지 않는다). push가 DB 트랜잭션 앞이다.
B1 save_pipeline · B2 web_status·change_status · B3 11단계 · B4 revert·process_commit·rebuild.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import db
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.collab.service import CommentService
from app.core.errors import (
    AlreadyCurrent,
    ConventionViolation,
    ItemDeleted,
    ItemDeletionNeedsConfirm,
    NotFound,
    RebuildFailed,
    StatusBlocked,
    UpstreamReviewRequired,
    VersionConflict,
)
from app.core.markdown import parse_frontmatter
from app.core.project.models import Repository
from app.core.project.service import ProjectService
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.tracking.service import TrackingService
from app.core.types import (
    STAGE_OF,
    Author,
    AuthorKind,
    DocStatus,
    DocType,
    DocumentSummary,
    Entry,
    RebuildResult,
    SaveResult,
    Violation,
    spec_dir,
    type_of_dir,
)
from app.infra import git

log = logging.getLogger(__name__)
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
    code = project_code or (doc_id.split("-")[0] if doc_id else None)
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
        try:
            document = spec.get_document(doc_id)
            doc_type = document.doc_type
        except NotFound:
            if entry != Entry.github:
                raise
            assert (
                doc_type is not None
            )  # github 신규 파일 — 파일명이 doc_id, frontmatter는 그대로 (보고)
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
        # github 진입은 물어볼 상대가 없다 — 커밋이 진실(SEQ-2). 삭제는 끊어진 참조로 통보 (보고)
        if any(downstream.values()) and not confirm_item_deletion and entry != Entry.github:
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
            path=f"docs/specs/{spec_dir(doc_type)}/{doc_id}.md",
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
    # 10a. 이 문서를 기다리던 미존재 참조를 푼다 (UC-S2 2a2)
    refs.resolve_missing(project.id, target_doc_id=doc_id)
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
        # 끊어진 참조는 읽을 때 센다 — 컬럼에 없다(SYNC-STD-001 4장, #35). 참조가 살았는지는
        # 프로젝트 전체 상태라 문서 하나만 보는 validate가 못 만들고, 굳혀 두면 상대 문서가
        # 들어와도 그 문서를 다시 저장하기 전까지 낡은 값이 남는다
        missing = sorted(
            dict.fromkeys(
                e.raw_target
                for e in ReferenceService(s).upstream_of_document(document.id, include_missing=True)
                if e.is_missing
            )
        )
        if to == DocStatus.approved and (
            document.has_convention_error or document.incomplete_warnings or missing
        ):
            raise StatusBlocked(
                document.convention_error_detail,
                document.incomplete_warnings + [f"ref.missing: {t}" for t in missing],
            )
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


async def process_commit(repo: Repository, head_hash: str) -> list[SaveResult]:
    """SYNC-MS-007#pipeline.process_commit"""
    if repo.last_processed_commit == head_hash:
        return []
    workdir = Path(repo.workdir_path)
    await git.fetch(workdir)
    rng = f"{repo.last_processed_commit}..{head_hash}" if repo.last_processed_commit else head_hash
    files = await git.changed_files(workdir, rng, "docs/specs/")
    # 같은 커밋의 상·하위 문서는 11단계 순서로 — 하위가 먼저 저장되면 참조가 미존재로 남는다 (보고)
    files.sort(
        key=lambda f: (
            STAGE_OF.get(Path(f.path).parts[2] if len(Path(f.path).parts) > 3 else "", 99),
            f.path,
        )
    )
    with db.session_scope() as s:
        code = next(p.code for p in ProjectService(s).list_projects() if p.id == repo.project_id)
    results: list[SaveResult] = []
    failed: list[str] = []
    for f in files:
        try:
            results.extend(await _process_file(workdir, code, f, head_hash))
        except Exception as e:  # noqa: BLE001 — 파일 하나 실패해도 다음 파일 계속 (MS-007)
            log.warning("process_commit %s %s: %s", code, f.path, e)
            failed.append(f.path)
    if not failed:
        with db.session_scope() as s:
            row = s.get(Repository, repo.id)
            assert row is not None
            row.last_processed_commit, row.synced_at = head_hash, datetime.now(UTC)
            # 방금 head까지 처리했으니 뒤처짐은 0이다. 다음 폴링까지 낡은 값을 안 보이게
            row.behind_by, row.fetched_at = 0, datetime.now(UTC)
            s.commit()
        repo.last_processed_commit = head_hash
    return results


def _dir_type(path: str) -> str:
    parts = Path(path).parts  # docs/specs/<NN-TYPE>/<doc_id>.md
    return type_of_dir(parts[2]) if len(parts) > 3 else ""


async def _process_file(workdir: Path, code: str, f, head_hash: str) -> list[SaveResult]:
    """process_commit 4단계 — 파일 하나. 삭제면 mark_deleted, 아니면 github 저장 + 위반 덧붙임."""
    doc_id, dir_type = Path(f.path).stem, _dir_type(f.path)
    with db.session_scope() as s:
        account = AccountService(s)
        user = account.user_for_commit(f.author_email, f.author_login)
        # 「자리표시인가」로 판정한다. 「방금 만들었나」로 하면 같은 사람의 둘째
        # 문서부터 이미 행이 있어 오류가 안 붙는다 (SYNC-DOM-002 5장 결정 3, #34)
        unknown = user.github_user_id is None
        s.commit()
        author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.github)
        if f.status == "D":
            spec, tracking = SpecService(s), TrackingService(s)
            document = spec.get_document(doc_id)
            for pk in spec.mark_deleted(document, f.commit_hash, author):
                tracking.raise_broken(pk)
            s.commit()
            return []
    with db.session_scope() as s:
        # 앱이 직접 push한 커밋(mcp·web 저장·상태 변경·되돌리기)은 이미 기록돼 있다 — 폴링이
        # 그것을 github 커밋으로 다시 저장하면 같은 커밋의 버전이 둘 생긴다. MS-007에 없음 (보고)
        try:
            known = {v.commit_hash for v in SpecService(s).list_versions(doc_id)}
        except NotFound:
            known = set()
    if f.commit_hash in known:
        return []
    body = await git.read(workdir, f.path, head_hash)
    doc_type = DocType(dir_type)
    r = await save_pipeline(
        Entry.github,
        doc_id,
        doc_type,
        body,
        None,
        code,
        author,
        f.message,
        changed_items=None,
        commit_hash=f.commit_hash,
    )
    fm, _ = parse_frontmatter(body)
    extra: list[Violation] = []
    if fm.get("doc_id") != doc_id:
        extra.append(Violation(2, "frontmatter.doc_id", f"파일명 {doc_id} ≠ {fm.get('doc_id')!r}"))
    if fm.get("type") != dir_type:
        extra.append(
            Violation(2, "frontmatter.doc_id", f"디렉터리 {dir_type} ≠ type {fm.get('type')!r}")
        )
    if unknown:
        extra.append(Violation(1, "author.unknown", f.author_login))
    if extra:
        with db.session_scope() as s:
            spec = SpecService(s)
            vr = spec.validate(body, doc_type, Entry.github, None)
            spec.mark_convention_error(
                spec.get_document(doc_id).id, vr.violations + extra, vr.warnings
            )
            s.commit()
    return [r]


async def rebuild(code: str, session: Session | None = None) -> RebuildResult:
    """SYNC-MS-007#pipeline.rebuild

    session: init_project(import_existing)가 아직 커밋 안 된 프로젝트 행이 있는 자기 세션을 넘긴다
    (save_pipeline의 session과 같은 방식. MS-007 시그니처에 없음 — 보고).
    """
    async with _lock(code):
        if session is not None:
            return await _rebuild(session, code)
        with db.session_scope() as s:
            return await _rebuild(s, code)


async def _rebuild(s: Session, code: str) -> RebuildResult:
    project = ProjectService(s).get(code)
    repo = project.repository
    workdir = Path(repo.workdir_path)
    spec, refs, account = SpecService(s), ReferenceService(s), AccountService(s)
    tracking = TrackingService(s)
    result = RebuildResult(0, 0, 0, 0)
    try:
        head = await git.fetch(workdir)  # 2단계도 실패하면 rebuild-failed (MS-007 예외)
        await git.checkout(workdir, "origin/HEAD")
        # 재구축이 versions를 갈아 끼우는 동안 전파결정·플래그는 사라진 버전을 가리킨다.
        # 이 트랜잭션에서만 검사를 끝으로 미룬다 — 평소에는 문장마다 검사한다 (0007, #38)
        s.execute(
            text(
                "SET CONSTRAINTS propagation_decisions_version_id_fkey,"
                " flags_cause_version_id_fkey DEFERRED"
            )
        )
        # 3a — 지우기 전에 옛 지도를 뜬다. 버전 행이 사라지면 document_id·commit_hash를
        # 알 방법이 없다 — 전파결정도 플래그도 version_id 하나만 들고 있다 (MS-007 3a, #38)
        old_keys = spec.version_keys(project.id)
        new_keys: dict[tuple[int, str], int] = {}
        refs.clear(project.id)
        spec.clear_index(project.id)
        for path in await git.list(workdir, "docs/specs/*/*.md", head):
            doc_id, dir_type = Path(path).stem, _dir_type(path)
            try:
                doc_type = DocType(dir_type)
            except ValueError:
                result.convention_errors.append(
                    {
                        "doc_id": doc_id,
                        "detail": f"frontmatter.doc_id: 알 수 없는 디렉터리 {dir_type}",
                    }
                )
                continue
            document = None
            try:
                document = spec.get_document(doc_id)
            except NotFound:
                pass
            last_unknown, last_login = False, ""
            for c in await git.log(workdir, path):
                body = await git.read(workdir, path, c.hash)
                user = account.user_for_commit(c.email, c.login)
                author = Author(
                    kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.github
                )
                if c.message.startswith("status(") and document is not None:
                    spec.apply_status(document, body, c.hash, user, None)
                else:
                    vr = spec.validate(body, doc_type, Entry.github, None)
                    if document is None:
                        version = spec.create(
                            project.id, doc_id, doc_type, body, c.hash, author, c.message, vr
                        )
                    else:
                        deleted = spec.detect_deleted_items(document, body)
                        version = spec.save(
                            document, body, c.hash, author, c.message, deleted, vr, rebuild=True
                        )
                    # 7a가 쓴다 — 옛 버전을 이 지도로 찾아 다시 잇는다
                    new_keys[(version.document_id, c.hash)] = version.id
                    result.versions += 1
                    # 마지막 본문 커밋의 작성자로 판정한다 — UI-5 배너가 last_author와
                    # 함께 보여주는 값이고 _process_file도 방금 저장한 버전으로 본다
                    last_unknown, last_login = user.github_user_id is None, c.login
                document = spec.get_document(doc_id)
            if document is None:
                continue
            fm, _ = parse_frontmatter(document.body)
            upstream_ids = re.findall(r"[\w-]+", fm.get("upstream", "").strip("[]"))
            ex = refs.extract(
                document.id,
                document.current_version_id,  # type: ignore[arg-type]
                document.body,
                spec.item_pks(document.id),
                upstream_ids,
            )
            vr = spec.validate(document.body, doc_type, Entry.github, None)
            # 작성자 위반을 여기서 얹는다. mark_convention_error는 항상 전량 교체라
            # 안 얹으면 사라진다 — 실물 인덱스에 규약 오류가 0건이던 이유다 (#34)
            extra = [Violation(1, "author.unknown", last_login)] if last_unknown else []
            violations = vr.violations + extra
            spec.mark_convention_error(document.id, violations, vr.warnings)
            if violations:
                detail = "\n".join(f"{v.rule}: {v.message}" for v in violations)
                result.convention_errors.append({"doc_id": doc_id, "detail": detail})
            result.docs += 1
            result.items += len(document.items)
            result.references += ex.added
        refs.resolve_missing(project.id)
        # 7a — 전파결정·플래그가 옛 버전 id를 가리킨다. 커밋 해시로 새 id에 다시 잇는다
        relink = tracking.relink_versions(project.id, old_keys, new_keys)
        result.dropped = relink.dropped
        # 7b — 담당자는 대상 문서의 최근 버전에서 오므로 재연결 뒤라야 한다 (MS-007 rebuild 7b)
        tracking.reassign_open_flags(project.id)
        repo.last_processed_commit, repo.synced_at = head, datetime.now(UTC)
        repo.behind_by, repo.fetched_at = 0, datetime.now(UTC)  # 재구축은 head까지 읽었다
        s.commit()
    except Exception as e:  # noqa: BLE001 — 어느 단계든 실패하면 롤백 (MS-007)
        s.rollback()
        log.warning("rebuild %s 실패: %s", code, e)
        raise RebuildFailed(str(e)) from e
    return result
