"""SYNC-MS-007 — pipeline. 쓰기 조율. 자기 테이블이 없고 서비스를 순서대로 부른다.

세 입구(MCP·웹·GitHub)가 전부 save_pipeline로 들어온다. 저장소 단위 asyncio.Lock(프로세스 내).
세션은 여기서 연다(DEV-10 — 서비스는 세션을 열지 않는다). push가 DB 트랜잭션 앞이다.
B1 save_pipeline · B2 web_status·change_status · B4 revert·process_commit·rebuild.
카드 V가 전파·플래그·댓글·백업 단계를 걷어냈다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app import db
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.clock import now_utc
from app.core.errors import (
    AlreadyCurrent,
    ConventionViolation,
    DocumentDeletionNeedsConfirm,
    DocumentHasHistory,
    DocumentNotTrashed,
    DocumentTrashed,
    ItemDeletionNeedsConfirm,
    NotFound,
    PreconditionUnmet,
    RebuildFailed,
    StatusBlocked,
    VersionConflict,
)
from app.core.markdown import parse_frontmatter
from app.core.project.models import Repository
from app.core.project.service import ProjectService
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
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
    TrashResult,
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
    confirm_item_deletion: bool = False,
    commit_hash: str | None = None,
    reason: str | None = None,
    session: Session | None = None,
    restore: bool = False,
) -> SaveResult:
    """SYNC-MS-007#pipeline.save_pipeline

    restore: restore_document가 부를 때 True — 휴지통 문서 저장을 막는 2단계 검사를 지난다.
    """
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
        confirm_item_deletion,
        commit_hash,
        reason,
        restore,
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
    confirm_item_deletion: bool,
    commit_hash: str | None,
    reason: str | None,
    restore: bool = False,
) -> SaveResult:
    """save_pipeline 본체 — 락·세션 안."""
    spec, refs = SpecService(s), ReferenceService(s)
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
        # 2. 휴지통 문서는 되살린 뒤 고친다. github는 파일이 다시 push된 것 — 그 자체가
        # 되살리기다(save 7이 trashed_at을 비운다) (MS-007 save_pipeline 2, 카드 R)
        if (
            document is not None
            and document.trashed_at is not None
            and entry != Entry.github
            and not restore
        ):
            raise DocumentTrashed(document.trashed_at.isoformat())
            assert (
                doc_type is not None
            )  # github 신규 파일 — 파일명이 doc_id, frontmatter는 그대로 (보고)
    else:
        assert doc_type is not None
        doc_id = spec.issue_doc_id(project.id, code, doc_type)
        body = spec.apply_frontmatter(body, doc_id, doc_type, DocStatus.draft)
        # 3a. DOM 셋의 순서 — push·DB 쓰기 전. github는 원본이 진실이라 안 본다 (STD-001 2.6)
        if entry == Entry.mcp:
            unmet = spec.precondition(
                project.id, doc_type, parse_frontmatter(body)[0].get("title", "")
            )
            if unmet:
                raise PreconditionUnmet(*unmet)
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
            # 하위 참조는 **이름으로** 준다. 에이전트는 이걸 사람에게 보여주고 확인을 받아야
            # 하는데(API-002 4장) items.id 숫자는 보여줄 수 없고 그것을 이름으로 바꾸는 MCP
            # 도구도 없다. 그러면 사람이 무엇이 끊어지는지 모르는 채로 승낙한다 (#50)
            down_pks = [
                e.from_item_pk for edges in downstream.values() for e in edges if e.from_item_pk
            ]
            refnames = spec.describe_items(down_pks)
            raise ItemDeletionNeedsConfirm(
                [
                    {
                        "item_id": names[pk],
                        "downstream": [
                            {
                                "doc_id": r.doc_id,
                                "item_id": r.item_id,
                                "display_name": r.display_name,
                            }
                            for e in edges
                            if e.from_item_pk and (r := refnames.get(e.from_item_pk))
                        ],
                    }
                    for pk, edges in downstream.items()
                    if edges
                ]
            )
    # 6a. 완료 문서를 고치면 여기서 본문의 status도 낮춘다 — **push 전에**.
    # DB에만 적으면 저장소 frontmatter가 approved로 남아 "status가 진실"(STD-001 1.2)이
    # 깨지고, 다음 저장이 frontmatter.status_change로 막힌다 — 서버가 준 본문을 서버가
    # 거부해 그 문서를 영영 못 고친다 (#47). 서버가 에이전트의 본문을 고치는 유일한 자리다
    status_commit_hash: str | None = None
    if (
        document is not None
        and document.status == DocStatus.approved
        and entry != Entry.web_status
        and body != document.body
        # github는 작성자가 스스로 내렸으면 그게 진실이다 (MS-002 save 5·6)
        and (entry != Entry.github or parse_frontmatter(body)[0].get("status") == "approved")
    ):
        body = re.sub(r"^status: .*$", f"status: {DocStatus.draft}", body, count=1, flags=re.M)
        if entry == Entry.github:
            # github 경로는 커밋이 이미 저장소에 있어 본문을 고치는 것만으로는 저장소가
            # 안 바뀐다. 커밋을 하나 더 민다. **그 해시를 StatusChange에 적어야** 다음
            # 폴링이 process_commit 3a에서 앱 커밋을 걸러낸다 — 안 적으면 앱이 민 커밋을
            # 남의 편집으로 다시 저장한다 (#58)
            #
            # **미는 사람은 저장소를 등록한 사람이다.** 커밋을 올린 사람이 아니다 —
            # 그 사람은 싱크독에 로그인한 적 없는 자리표시일 수 있어 토큰이 없다.
            # 등록자는 OAuth로 들어와 저장소를 붙인 사람이라 토큰이 있는 유일한 쪽이다.
            # 강등을 **누가 유발했는지**는 StatusChange.changed_by가 따로 들고 있다
            pusher = s.get(User, repo.registered_by_user_id)
            assert pusher is not None
            status_commit_hash = await git.commit_push(
                Path(repo.workdir_path),
                f"status({doc_id}): {DocStatus.approved} → {DocStatus.draft}"
                "\n\n본문 수정으로 자동 강등",
                # via는 커밋 신원에만 쓰인다 — 이 Author는 저장되지 않는다
                Author(
                    kind=AuthorKind.human, user=pusher, instructed_by=None, via=Entry.web_status
                ),
                path=f"docs/specs/{spec_dir(doc_type)}/{doc_id}.md",
                content=body,
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
        s.commit()
        return SaveResult(
            doc_id,
            document.current_version_no,
            commit_hash,
            spec.get_document(doc_id).status,
            [],
        )
    if document is None:
        version = spec.create(
            project.id, doc_id, doc_type, body, commit_hash, author, message, validate_result=vr
        )
    else:
        version = spec.save(
            document,
            body,
            commit_hash,
            author,
            message,
            deleted,
            validate_result=vr,  # 모든 경로 — 경고가 mcp 저장에도 남아야 승인을 막는다
            status_commit_hash=status_commit_hash,
        )
    document_id = version.document_id
    # 9. 끊어진 참조 — 사라진 항목을 가리키던 참조가 그 자리에서 미존재가 된다 (MS-007 9)
    broken = refs.mark_missing(deleted)
    # 10. 참조 추출
    item_pks = spec.item_pks(document_id)
    fm, _ = parse_frontmatter(body)
    upstream_ids = re.findall(r"[\w-]+", fm.get("upstream", "").strip("[]"))
    refs.extract(document_id, version.id, body, item_pks, upstream_ids)
    # 10a. 이 문서를 기다리던 미존재 참조를 푼다 (UC-S2 2a2)
    refs.resolve_missing(project.id, target_doc_id=doc_id)
    # 10b~13. 없음 — 끊어진 참조 해제·전파 감지·상위 불일치·댓글 재배치가 있던 자리 (카드 V)
    warnings = [str(w) for w in vr.warnings]
    if deleted:
        warnings.append(f"ref.broken: {broken}")
    # 14. 커밋
    s.commit()
    status = spec.get_document(doc_id).status
    # 15. 문서 하나 쓰고 멈추라는 규약(STD-001 1.8)을 응답이 매번 다시 말한다 — mcp만
    next_step = (
        f"{doc_id} v{version.version_no} 저장됨. 사람에게 웹에서 읽으라고 하고 멈춘다 — "
        "다음 문서는 사람이 읽고 난 뒤에 (STD-001 1.8)"
        if entry == Entry.mcp
        else None
    )
    return SaveResult(doc_id, version.version_no, commit_hash, status, warnings, next_step)


async def change_status(
    doc_id: str,
    to: DocStatus,
    user: User,
    reason: str | None = None,
) -> DocumentSummary:
    """SYNC-MS-007#pipeline.change_status"""
    with db.session_scope() as s:
        spec = SpecService(s)
        document = spec.get_document(doc_id)
        if document.trashed_at is not None:
            raise DocumentTrashed(document.trashed_at.isoformat())
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
        # 3. 없음 — 상위 대조가 있던 자리. 완료는 사람 하나가 누르는 토글이다 (카드 V)
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


async def trash_document(doc_id: str, author: Author, confirm: bool) -> TrashResult:
    """SYNC-MS-007#pipeline.trash_document"""
    code = doc_id.split("-")[0]
    async with _lock(code):
        with db.session_scope() as s:
            spec, refs = SpecService(s), ReferenceService(s)
            document = spec.get_document(doc_id)
            if document.trashed_at is not None:
                raise DocumentTrashed(document.trashed_at.isoformat())
            repo = ProjectService(s).get(code).repository
            # 2. 끊어질 것 — 막지 않는다, 보여준다
            inbound = _inbound_names(spec, refs.inbound_of_document(document.id))
            if not confirm:
                title = parse_frontmatter(document.body)[0].get("title", "")
                raise DocumentDeletionNeedsConfirm(
                    doc_id, title, document.current_version_no, inbound
                )
            # 4. push — 여기까지 DB 쓰기 없음
            commit_hash = await git.commit_push(
                Path(repo.workdir_path),
                f"spec({doc_id}): 휴지통",
                author,
                delete=[f"docs/specs/{spec_dir(document.doc_type)}/{doc_id}.md"],
            )
            # 5. 트랜잭션 — 항목 삭제됨 + 휴지통 표시 + 그것을 가리키던 참조는 미존재로
            pks = spec.trash(document, commit_hash, author)
            broken = refs.mark_missing(pks)
            s.commit()
    return TrashResult(
        doc_id,
        commit_hash,
        broken,
        f"{doc_id} 휴지통에 넣음 — 끊어진 참조 {broken}. 사람에게 알리고 멈춘다",
    )


async def restore_document(doc_id: str, author: Author) -> SaveResult:
    """SYNC-MS-007#pipeline.restore_document"""
    code = doc_id.split("-")[0]
    with db.session_scope() as s:
        spec = SpecService(s)
        document = spec.get_document(doc_id)
        if document.trashed_at is None:
            raise DocumentNotTrashed()
        repo = ProjectService(s).get(code).repository
        h = spec.trash_commit(document.id)
        assert h is not None  # trash가 늘 남긴다
        path = f"docs/specs/{spec_dir(document.doc_type)}/{doc_id}.md"
        body = await git.read(Path(repo.workdir_path), path, f"{h}^")
        # 3. DB가 draft다 — mcp 경로의 frontmatter.status_change에 안 걸리게
        body = re.sub(r"^status: .*$", f"status: {DocStatus.draft}", body, count=1, flags=re.M)
        entry = Entry.mcp if author.via == Entry.mcp else Entry.web_revert
        r = await save_pipeline(
            entry,
            doc_id,
            None,
            body,
            document.current_version_no,
            None,
            author,
            f"spec({doc_id}): 되살림 — 휴지통에서",
            changed_items=[] if entry == Entry.mcp else None,
            session=s,
            restore=True,
        )
        # 5. 없음 — 되살아난 항목을 가리키던 미존재 참조는 save_pipeline 10a가 이미 이었다
    return r


async def purge_document(doc_id: str, author: Author) -> None:
    """SYNC-MS-007#pipeline.purge_document"""
    code = doc_id.split("-")[0]
    async with _lock(code):
        with db.session_scope() as s:
            spec, refs = SpecService(s), ReferenceService(s)
            document = spec.get_document(doc_id)
            if document.trashed_at is None:
                raise DocumentNotTrashed()
            # 2. 문지기 하나 — 아직 가리키는 곳. 미존재 참조는 to_*가 비어 여기 안 잡힌다 —
            # 그것은 가리키는 쪽의 사정이다 (MS-007 purge 2)
            inbound = _inbound_names(spec, refs.inbound_of_document(document.id))
            if inbound:
                raise DocumentHasHistory(inbound)
            # 3. 파일은 이미 저장소에 없다(휴지통 커밋) — push 없음
            spec.delete_document(document)
            s.commit()


def _inbound_names(spec: SpecService, inbound: list) -> list[str]:
    """들어오는 참조를 사람이 읽을 이름으로 — 문서ID#항목ID 또는 문서ID."""
    names = spec.describe_items([e.from_item_pk for e in inbound if e.from_item_pk])
    docs = spec.describe_documents([e.from_document_id for e in inbound if not e.from_item_pk])
    return sorted(
        f"{r.doc_id}#{r.item_id}"
        if e.from_item_pk and (r := names.get(e.from_item_pk))
        else (d.doc_id if (d := docs.get(e.from_document_id or -1)) else "?")
        for e in inbound
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
            spec, refs = SpecService(s), ReferenceService(s)
            try:
                document = spec.get_document(doc_id)
            except NotFound:
                # 앱이 purge_document로 지운 문서의 삭제 커밋이거나 등록 전에 사라진 파일이다.
                # mark_deleted로 가면 not-found가 나서 이 커밋이 영영 「처리 실패」로 남고
                # last_processed_commit이 안 나아간다 (MS-007 process_commit 4)
                return []
            if document.trashed_at is not None:
                return []  # 앱이 trash_document로 만든 삭제 커밋 — 이미 반영돼 있다 (카드 R)
            refs.mark_missing(spec.mark_deleted(document, f.commit_hash, author))
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
    result = RebuildResult(0, 0, 0, 0)
    try:
        head = await git.fetch(workdir)  # 2단계도 실패하면 rebuild-failed (MS-007 예외)
        await git.checkout(workdir, "origin/main")
        # 4a. versions를 가리키는 FK는 references.extracted_version_id 하나 — 먼저 지운다.
        # 전파결정·플래그가 사라지면서 DEFERRED·재연결(옛 3a·7a·7b)도 사라졌다 (카드 V)
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
                        spec.create(
                            project.id, doc_id, doc_type, body, c.hash, author, c.message, vr
                        )
                    else:
                        deleted = spec.detect_deleted_items(document, body)
                        spec.save(
                            document, body, c.hash, author, c.message, deleted, vr, rebuild=True
                        )
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
        # 7a~7b. 없음 — 전파결정·플래그를 새 버전에 다시 잇던 자리 (카드 V)
        repo.last_processed_commit, repo.synced_at = head, now_utc()
        repo.behind_by, repo.fetched_at = 0, now_utc()  # 재구축은 head까지 읽었다
        s.commit()
    except Exception as e:  # noqa: BLE001 — 어느 단계든 실패하면 롤백 (MS-007)
        s.rollback()
        log.warning("rebuild %s 실패: %s", code, e)
        raise RebuildFailed(str(e)) from e
    return result
