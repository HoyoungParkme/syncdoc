"""SYNC-MS-007 — pipeline. 쓰기 조율. 자기 테이블이 없고 서비스를 순서대로 부른다.

세 입구(MCP·웹·GitHub)가 전부 save_pipeline로 들어온다. 저장소 단위 asyncio.Lock(프로세스 내).
세션은 여기서 연다(DEV-10 — 서비스는 세션을 열지 않는다). push가 DB 트랜잭션 앞이다.
B1 save_pipeline · B2 web_status·change_status · B3 11단계 · B4 revert·process_commit·rebuild.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import db
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.clock import now_utc
from app.core.collab.service import CommentService
from app.core.errors import (
    AlreadyCurrent,
    BackupInvalid,
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
    RestoreDecision,
    RestoreFlag,
    RestoreResult,
    SaveResult,
    Violation,
    spec_dir,
    type_of_dir,
)
from app.infra import git
from app.infra.git import GitError

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
            row.last_processed_commit, row.synced_at = head_hash, now_utc()
            # 방금 head까지 처리했으니 뒤처짐은 0이다. 다음 폴링까지 낡은 값을 안 보이게
            row.behind_by, row.fetched_at = 0, now_utc()
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
                " flags_cause_version_id_fkey, flags_target_version_id_fkey DEFERRED"
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
                # c.path로 읽는다 — 이름이 바뀐 문서는 옛 커밋에서 옛 경로에 있다 (#39)
                body = await git.read(workdir, c.path or path, c.hash)
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
        repo.last_processed_commit, repo.synced_at = head, now_utc()
        repo.behind_by, repo.fetched_at = 0, now_utc()  # 재구축은 head까지 읽었다
        s.commit()
    except Exception as e:  # noqa: BLE001 — 어느 단계든 실패하면 롤백 (MS-007)
        s.rollback()
        log.warning("rebuild %s 실패: %s", code, e)
        raise RebuildFailed(str(e)) from e
    return result


# ── 추적 데이터 백업 (SYNC-INFRA-001 6.1, #16) ──
_BACKUP_PATH = "backup/tracking.json"
_BACKUP_VERSION = 2  # 2에서 플래그에 target_version이 생겼다 (#17)
_BACKUP_VERSIONS_READ = (1, 2)  # 형식을 올려도 이미 떠 둔 백업은 계속 읽는다 (MS-007)


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt is not None else None


def _ckey(at: str | None, by: str | None) -> str:
    """댓글 자연키 `{작성시각}|{작성자}`. 배열 index를 안 쓰는 이유는 MS-007에 적었다."""
    return f"{at}|{by}"


async def export_tracking(code: str) -> str:
    """SYNC-MS-007#pipeline.export_tracking"""
    # save_pipeline·rebuild와 같은 락이다 — commit_push가 reset --hard로 작업 사본을
    # 갈아엎으므로 저장 중인 파이프라인과 같은 자물쇠 아래 있어야 한다
    async with _lock(code):
        with db.session_scope() as s:
            project = ProjectService(s).get(code)
            repo = project.repository
            user = s.get(User, repo.registered_by_user_id)
            if user is None:
                raise NotFound("user", repo.registered_by_user_id)
            spec, tracking, collab = SpecService(s), TrackingService(s), CommentService(s)
            flags = tracking.all_flags(project.id)
            decisions = tracking.all_decisions(project.id)
            comments = collab.all_in_project(project.id)

            # 지도 넷을 한 번씩만 뜬다
            item_pks = {f.target_item_id for f in flags} | {
                f.cause_item_id for f in flags if f.cause_item_id
            }
            for d in decisions:
                item_pks |= set(d.affected_pks) | set(d.changed_pks)
            items = spec.describe_items(sorted(item_pks))  # 삭제된 항목도 준다
            vkeys = spec.version_keys(project.id)
            doc_ids = {c.document_id for c in comments} | {doc for doc, _ in vkeys.values()}
            docs = spec.describe_documents(sorted(doc_ids))
            user_ids = {f.assignee_user_id for f in flags} | {f.resolved_by_user_id for f in flags}
            user_ids |= {d.decided_by_user_id for d in decisions} | {
                c.author_user_id for c in comments
            }
            users = AccountService(s).users_by_ids([i for i in user_ids if i])

            def item_key(pk: int | None) -> str | None:
                r = items.get(pk) if pk is not None else None
                return f"{r.doc_id}#{r.item_id}" if r else None

            def version_key(vid: int | None) -> str | None:
                pair = vkeys.get(vid) if vid is not None else None
                if pair is None:
                    return None
                doc = docs.get(pair[0])
                return f"{doc.doc_id}@{pair[1]}" if doc else None

            def login(uid: int | None) -> str | None:
                r = users.get(uid) if uid is not None else None
                return r.github_login if r else None

            def item_keys(pks: list[int]) -> list[str]:
                # JSONB라 FK가 없다 — 지도에 없는 pk는 원소만 뺀다
                out = []
                for pk in pks:
                    k = item_key(pk)
                    if k is None:
                        log.warning("backup %s: 항목 pk %s를 못 찾았다", code, pk)
                    else:
                        out.append(k)
                return sorted(out)

            payload = {
                "backup_version": _BACKUP_VERSION,
                "project": code,
                "flags": sorted(
                    (
                        {
                            "kind": f.kind,
                            "target": item_key(f.target_item_id),
                            "cause": item_key(f.cause_item_id),
                            "cause_version": version_key(f.cause_version_id),
                            "target_version": version_key(f.target_version_id),
                            "assignee": login(f.assignee_user_id),
                            "raised_at": _iso(f.raised_at),
                            "resolved_by": login(f.resolved_by_user_id),
                            "resolved_at": _iso(f.resolved_at),
                            "resolved_with_edit": f.resolved_with_edit,
                        }
                        for f in flags
                    ),
                    key=lambda r: (
                        r["target"] or "",
                        r["raised_at"] or "",
                        r["kind"],
                        r["cause"] or "",
                        r["cause_version"] or "",
                    ),
                ),
                "propagation_decisions": sorted(
                    (
                        {
                            "version": version_key(d.version_id),
                            "choice": d.choice,
                            "affected": item_keys(list(d.affected_pks)),
                            "changed": item_keys(list(d.changed_pks)),
                            "decided_by": login(d.decided_by_user_id),
                            "decided_at": _iso(d.decided_at),
                        }
                        for d in decisions
                    ),
                    key=lambda r: r["version"] or "",
                ),
                "comments": sorted(
                    (
                        {
                            "doc": (docs[c.document_id].doc_id if c.document_id in docs else None),
                            "line_no": c.line_no,
                            "line_hash": c.line_hash,
                            "by": login(c.author_user_id),
                            "is_resolved": c.is_resolved,
                            "at": _iso(c.created_at),
                            "original_location": c.original_location,
                            "parent": None,  # 아래에서 채운다
                        }
                        for c in comments
                    ),
                    key=lambda r: (r["doc"] or "", r["at"] or "", r["by"] or ""),
                ),
            }
            # 부모를 자연키로. 원본 행과 같은 순서가 아니므로 id로 먼저 지도를 만든다
            by_id = {c.id: _ckey(_iso(c.created_at), login(c.author_user_id)) for c in comments}
            key_of = {_ckey(_iso(c.created_at), login(c.author_user_id)): c for c in comments}
            for row in payload["comments"]:
                src = key_of[_ckey(row["at"], row["by"])]
                row["parent"] = by_id.get(src.parent_comment_id) if src.parent_comment_id else None

            # 결정적 직렬화 — 시각 필드를 안 넣는다(넣으면 매 주기 빈 커밋이 쌓인다)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            author = Author(kind=AuthorKind.human, user=user, instructed_by=None, via=Entry.backup)
            message = (
                f"chore({code}): 추적 데이터 백업"
                f" (플래그 {len(flags)} · 전파결정 {len(decisions)} · 댓글 {len(comments)})"
            )
            # 내용이 같으면 커밋이 안 생기고 현재 HEAD가 온다 (MS-009 commit_push)
            return await git.commit_push(
                Path(repo.workdir_path), message, author, path=_BACKUP_PATH, content=text
            )


async def import_tracking(code: str) -> RestoreResult:
    """SYNC-MS-007#pipeline.import_tracking"""
    # 재구축이 같은 락 안에서 versions를 지우고 다시 만든다 — 복원이 그 사이에 끼면
    # 곧 사라질 버전에 결정을 붙인다
    async with _lock(code):
        with db.session_scope() as s:
            project = ProjectService(s).get(code)
            workdir = Path(project.repository.workdir_path)
            await git.fetch(workdir)
            try:
                # origin/HEAD로 읽는다 — 로컬 HEAD는 뒤처질 수 있고 백업은 원격이 진실이다
                text = await git.read(workdir, _BACKUP_PATH, "origin/HEAD")
            except GitError as e:
                raise NotFound("backup", code) from e
            data = json.loads(text)
            if data.get("backup_version") not in _BACKUP_VERSIONS_READ:
                raise BackupInvalid("version")
            if data.get("project") != code:
                raise BackupInvalid("project")  # 다른 프로젝트의 백업을 붓지 않는다

            spec, tracking, collab = SpecService(s), TrackingService(s), CommentService(s)
            account = AccountService(s)
            result = RestoreResult()
            drops: dict[tuple[str, str], int] = {}

            def drop(kind: str, reason: str, n: int = 1) -> None:
                drops[(kind, reason)] = drops.get((kind, reason), 0) + n

            NO_DOC = "가리키던 문서가 저장소에 없습니다"
            NO_ITEM = "가리키던 항목이 저장소에 없습니다"
            NO_COMMIT = "가리키던 커밋이 저장소에 없습니다"
            NO_PARENT = "부모 댓글을 못 찾았습니다"

            # 지도 넷. 행마다 조회하지 않는다
            doc_ids = {r["doc"] for r in data["comments"] if r["doc"]}
            for r in data["flags"]:
                doc_ids |= {k.split("#")[0] for k in (r["target"], r["cause"]) if k}
                # 형식 1에는 target_version이 없다 — get으로 읽어 null로 본다 (MS-007)
                for key in (r["cause_version"], r.get("target_version")):
                    if key:
                        doc_ids.add(key.split("@")[0])
            for r in data["propagation_decisions"]:
                if r["version"]:
                    doc_ids.add(r["version"].split("@")[0])
                doc_ids |= {k.split("#")[0] for k in r["affected"] + r["changed"]}
            documents = {}
            for doc_id in sorted(doc_ids):
                try:
                    documents[doc_id] = spec.get_document(doc_id)
                except NotFound:
                    pass
            item_of: dict[str, int] = {}
            for doc_id, doc in documents.items():
                # 삭제 포함 — broken_ref의 원인 항목은 정의상 is_deleted다
                for item_id, pk in spec.item_pks(doc.id, include_deleted=True).items():
                    item_of[f"{doc_id}#{item_id}"] = pk
            # version_keys를 뒤집는다 — 새 함수가 필요 없다
            id_to_doc = {d.id: k for k, d in documents.items()}
            version_of = {
                f"{id_to_doc[doc_id]}@{h}": vid
                for vid, (doc_id, h) in spec.version_keys(project.id).items()
                if doc_id in id_to_doc
            }
            user_of: dict[str, int] = {}
            for login in sorted(
                {r["by"] for r in data["comments"] if r["by"]}
                | {r[k] for r in data["flags"] for k in ("assignee", "resolved_by") if r[k]}
                | {r["decided_by"] for r in data["propagation_decisions"] if r["decided_by"]}
            ):
                u = account.user_by_login(login) or account.create_placeholder(login)
                user_of[login] = u.id

            # 플래그
            rows: list[RestoreFlag] = []
            for r in data["flags"]:
                target = item_of.get(r["target"])
                if target is None:
                    drop("flag", NO_DOC if r["target"].split("#")[0] not in documents else NO_ITEM)
                    continue
                if r["cause"] and r["cause"] not in item_of:
                    # 비우지 않고 버린다 — 비우면 UI-11의 원인 diff·중복 방지가 죽는다
                    drop("flag", NO_ITEM)
                    continue
                if r["cause_version"] and r["cause_version"] not in version_of:
                    drop("flag", NO_COMMIT)
                    continue
                rows.append(
                    RestoreFlag(
                        kind=r["kind"],
                        target_item_id=target,
                        cause_item_id=item_of.get(r["cause"]) if r["cause"] else None,
                        cause_version_id=version_of.get(r["cause_version"])
                        if r["cause_version"]
                        else None,
                        # 못 찾으면 비우고 행은 넣는다 — 원인과 달리 판단의 뼈대가 아니다
                        target_version_id=version_of.get(r.get("target_version") or ""),
                        assignee_user_id=user_of.get(r["assignee"]) if r["assignee"] else None,
                        raised_at=datetime.fromisoformat(r["raised_at"]),
                        resolved_by_user_id=user_of.get(r["resolved_by"])
                        if r["resolved_by"]
                        else None,
                        resolved_at=datetime.fromisoformat(r["resolved_at"])
                        if r["resolved_at"]
                        else None,
                        resolved_with_edit=r["resolved_with_edit"],
                    )
                )
            result.flags, skipped = tracking.restore_flags(rows)
            result.skipped += skipped

            # 전파결정
            drows: list[RestoreDecision] = []
            for r in data["propagation_decisions"]:
                vid = version_of.get(r["version"]) if r["version"] else None
                if vid is None:
                    drop("propagation_decision", NO_COMMIT)
                    continue
                aff = [item_of[k] for k in r["affected"] if k in item_of]
                chg = [item_of[k] for k in r["changed"] if k in item_of]
                missing = len(r["affected"]) + len(r["changed"]) - len(aff) - len(chg)
                if missing:
                    drop("decision_item", NO_ITEM, missing)  # 원소만 뺀다. 행은 넣는다
                drows.append(
                    RestoreDecision(
                        version_id=vid,
                        choice=r["choice"],
                        affected_pks=aff,
                        changed_pks=chg,
                        decided_by_user_id=user_of.get(r["decided_by"])
                        if r["decided_by"]
                        else None,
                        decided_at=datetime.fromisoformat(r["decided_at"])
                        if r["decided_at"]
                        else None,
                    )
                )
            result.decisions, skipped = tracking.restore_decisions(drows)
            result.skipped += skipped

            # 댓글 — 파일 순서대로 한 행씩. 이미 있던 행도 지도에 넣는다
            new_id: dict[str, int] = {}
            for r in data["comments"]:
                doc = documents.get(r["doc"])
                if doc is None:
                    drop("comment", NO_DOC)
                    continue
                parent_id = None
                if r["parent"]:
                    parent_id = new_id.get(r["parent"])
                    if parent_id is None:
                        drop("comment", NO_PARENT)  # 최상위로 올리지 않는다
                        continue
                row, created = collab.restore(
                    document_id=doc.id,
                    parent_comment_id=parent_id,
                    line_no=r["line_no"],
                    line_hash=r["line_hash"],
                    author_user_id=user_of[r["by"]],
                    is_resolved=r["is_resolved"],
                    created_at=datetime.fromisoformat(r["at"]),
                    original_location=r["original_location"],
                )
                new_id[_ckey(r["at"], r["by"])] = row.id
                if created:
                    result.comments += 1
                else:
                    result.skipped += 1

            result.dropped = [
                {"kind": k, "count": n, "reason": reason}
                for (k, reason), n in sorted(drops.items())
            ]
            s.commit()
            return result
