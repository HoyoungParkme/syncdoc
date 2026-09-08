"""SYNC-MS-008 — queries. 읽기 조합. 서비스는 자기 묶음만 알고 여기서 ID로 잇는다. 쓰지 않는다.

B1: project_summary · document_list · document_view · item_view. 세션은 db.session_scope().
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from syncdoc import db
from syncdoc.core.account.service import AccountService
from syncdoc.core.collab.service import CommentService
from syncdoc.core.project.models import Project
from syncdoc.core.project.service import ProjectService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import (
    STAGE_OF,
    ApiAuthor,
    AuthorRef,
    DocStatus,
    Document,
    DocumentSummary,
    ItemView,
    ProjectSummary,
    StageSummary,
    UserRef,
)

_ORDER = {"draft": 0, "review": 1, "approved": 2}


def build_project_summary(
    project: Project, docs: list[DocumentSummary], flags: dict[str, int], unresolved: int
) -> ProjectSummary:
    """단계 11칸 계산(UC-H14 1a·1b). ProjectService.init_project도 신규(docs=[])로 이걸 쓴다."""
    stages: list[StageSummary] = []
    for doc_type, n in STAGE_OF.items():
        stage_docs = [d for d in docs if d.stage == n]
        status = min((d.status for d in stage_docs), key=lambda s: _ORDER[s], default=None)
        gate = bool(stage_docs) and any(
            s.doc_count > 0 and s.status != DocStatus.approved for s in stages
        )
        stages.append(StageSummary(n, doc_type, status, len(stage_docs), gate))
    counts = {
        "needs_check": flags.get("needs_check", 0),
        "broken_ref": flags.get("broken_ref", 0),
        "unresolved_comments": unresolved,
        "convention_errors": sum(d.has_convention_error for d in docs),
        "incomplete": sum(bool(d.incomplete_warnings) for d in docs),
    }
    return ProjectSummary(
        code=project.code,
        name=project.name,
        remote_url=project.repository.remote_url,
        stages=stages,
        std_docs=[d for d in docs if d.doc_type == "STD"],
        counts=counts,
        updated_at=max((d.updated_at for d in docs), default=None),
    )


def _api_author(session: Session, ref: AuthorRef | None) -> ApiAuthor | None:
    if ref is None:
        return None
    names: dict[int, UserRef] = AccountService(session).users_by_ids(
        [ref.user_id, ref.instructed_by_id]
    )
    return ApiAuthor(
        kind=ref.kind,
        user=names.get(ref.user_id),
        instructed_by=names.get(ref.instructed_by_id) if ref.instructed_by_id else None,
        via=ref.via,
    )


async def project_summary() -> list[ProjectSummary]:
    """SYNC-MS-008#queries.project_summary"""
    with db.session_scope() as s:
        out = []
        for p in ProjectService(s).list_projects():
            docs = SpecService(s).list_by_project(p.id)
            flags = TrackingService(s).count_flags(p.id)
            out.append(
                build_project_summary(p, docs, flags, CommentService(s).count_unresolved(p.id))
            )
        out.sort(key=lambda x: (x.updated_at is not None, x.updated_at), reverse=True)
        return out


async def document_list(
    code: str, stage: int | None = None, status: DocStatus | None = None
) -> list[DocumentSummary]:
    """SYNC-MS-008#queries.document_list"""
    with db.session_scope() as s:
        project = ProjectService(s).get(code)
        docs = SpecService(s).list_by_project(project.id, stage, status)
        ids = [d.id for d in docs]
        flags = TrackingService(s).count_flags_by_document(ids)
        comments = CommentService(s).count_unresolved_by_document(ids)
        for d in docs:
            f = flags.get(d.id, {})
            d.counts = {
                "needs_check": f.get("needs_check", 0),
                "broken_ref": f.get("broken_ref", 0),
                "unresolved_comments": comments.get(d.id, 0),
            }
            d.author = _api_author(s, d.last_author)
        return docs


async def document_view(doc_id: str) -> Document:
    """SYNC-MS-008#queries.document_view"""
    with db.session_scope() as s:
        doc = SpecService(s).get_document(doc_id)
        flags = TrackingService(s).flags_for_items([i.pk for i in doc.items])
        for item in doc.items:
            item.flags = [f.kind for f in flags.get(item.pk, [])]
        doc.prev_doc_id, doc.next_doc_id = SpecService(s).neighbors(doc_id)
        doc.author = _api_author(s, doc.last_author)
        return doc


async def item_view(doc_id: str, item_id: str) -> ItemView:
    """SYNC-MS-008#queries.item_view"""
    with db.session_scope() as s:
        v = SpecService(s).get_item(doc_id, item_id)
        v.flags = [f.kind for f in TrackingService(s).flags_for_items([v.pk]).get(v.pk, [])]
        return v
