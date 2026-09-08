"""SYNC-MS-008 — queries. 읽기 조합. 서비스는 자기 묶음만 알고 여기서 ID로 잇는다. 쓰지 않는다.

B1: project_summary · document_list · document_view · item_view.
B2: item_references_view · upstream_checklist. 세션은 db.session_scope().
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from syncdoc import db
from syncdoc.core.account.service import AccountService
from syncdoc.core.collab.service import CommentService
from syncdoc.core.markdown import parse_frontmatter
from syncdoc.core.project.models import Project
from syncdoc.core.project.service import ProjectService
from syncdoc.core.reference.service import ReferenceService
from syncdoc.core.spec.service import SpecService
from syncdoc.core.tracking.service import TrackingService
from syncdoc.core.types import (
    STAGE_OF,
    ApiAuthor,
    AuthorRef,
    DocStatus,
    Document,
    DocumentSummary,
    FlagSummary,
    ItemRef,
    ItemReferences,
    ItemView,
    ProjectSummary,
    RefEdge,
    StageSummary,
    UpstreamCheck,
    UserRef,
)

_ORDER = {"draft": 0, "review": 1, "approved": 2}


def _summarize(
    project: Project, docs: list[DocumentSummary], flags: dict[str, int], unresolved: int
) -> ProjectSummary:
    """단계 11칸 계산(UC-H14 1a·1b)."""
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
            out.append(_summarize(p, docs, flags, CommentService(s).count_unresolved(p.id)))
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


def flag_summaries(s: Session, rows: list) -> list[FlagSummary]:
    """Flag 행 → FlagSummary. target·cause는 describe_items, assignee는 users_by_ids. 각 한 번."""
    spec = SpecService(s)
    names = spec.describe_items(
        [f.target_item_id for f in rows] + [f.cause_item_id for f in rows if f.cause_item_id]
    )
    users = AccountService(s).users_by_ids([f.assignee_user_id for f in rows if f.assignee_user_id])
    return [
        FlagSummary(
            id=f.id,
            kind=f.kind,
            target=names.get(f.target_item_id) or ItemRef(None, None, None),
            cause=names.get(f.cause_item_id) if f.cause_item_id else None,
            cause_version_no=None,  # 버전 id → 번호 조회 함수가 MS에 없다 (B3 get_flag에서)
            assignee=users.get(f.assignee_user_id) if f.assignee_user_id else None,
            raised_at=f.raised_at,
            resolved_at=f.resolved_at,
        )
        for f in rows
    ]


def _doc_refs(spec: SpecService, project_id: int, doc_pks: list[int]) -> dict[int, ItemRef]:
    """문서 pk → ItemRef(item_id=None, 제목). describe_items는 항목만 — pk 공간이 겹친다."""
    wanted = set(doc_pks)
    out: dict[int, ItemRef] = {}
    for d in spec.list_by_project(project_id):
        if d.id in wanted:
            title = parse_frontmatter(spec.get_document(d.doc_id).body)[0].get("title", d.doc_id)
            out[d.id] = ItemRef(doc_id=d.doc_id, item_id=None, display_name=title)
    return out


def _to_ref(e: RefEdge, names: dict[int, ItemRef]) -> ItemRef:
    """RefEdge → ItemRef. 항목이면 names[pk], 문서 전체면 item_id=None, 미존재면 raw_target만."""
    if e.is_missing:
        return ItemRef(None, None, None, raw_target=e.raw_target, is_missing=True)
    pk = e.to_item_pk if e.to_item_pk is not None else e.to_document_id
    ref = names.get(pk) or ItemRef(None, None, None, raw_target=e.raw_target, is_missing=True)
    ref.raw_target = e.raw_target
    return ref


async def item_references_view(doc_id: str, item_id: str) -> ItemReferences:
    """SYNC-MS-008#queries.item_references_view"""
    with db.session_scope() as s:
        spec, refs = SpecService(s), ReferenceService(s)
        pk = spec.resolve_item(doc_id, item_id)
        document_id = spec.get_document(doc_id).id
        up = refs.upstream(pk)
        down = refs.downstream(pk) + refs.downstream_of_document(document_id)
        need = [e.to_item_pk for e in up if e.to_item_pk] + [
            e.from_item_pk for e in down if e.from_item_pk
        ]
        names = spec.describe_items(need)
        project_id = ProjectService(s).get(doc_id.split("-")[0]).id
        doc_names = _doc_refs(
            spec,
            project_id,
            [e.to_document_id for e in up if e.to_document_id and not e.to_item_pk],
        )
        upstream = [_to_ref(e, {**doc_names, **names} if e.to_item_pk else doc_names) for e in up]
        downstream = []
        for e in down:
            if e.from_item_pk is None:
                continue  # 절 본문·frontmatter에서 온 참조 — 출발 항목이 없어 패널에 못 그린다
            r = names.get(e.from_item_pk)
            if r is not None:
                downstream.append(
                    ItemRef(r.doc_id, r.item_id, r.display_name, raw_target=e.raw_target)
                )
        rows = TrackingService(s).flags_for_items([pk]).get(pk, [])
        return ItemReferences(doc_id, item_id, upstream, downstream, flag_summaries(s, rows))


async def upstream_checklist(doc_id: str) -> list[UpstreamCheck]:
    """SYNC-MS-008#queries.upstream_checklist"""
    with db.session_scope() as s:
        spec, refs = SpecService(s), ReferenceService(s)
        doc = spec.get_document(doc_id)
        by_item = {i.pk: i.item_id for i in doc.items}
        grouped: dict[tuple[str, int], list[str]] = {}
        for e in refs.upstream_of_document(doc.id):
            key = ("item", e.to_item_pk) if e.to_item_pk else ("doc", e.to_document_id)
            src = by_item.get(e.from_item_pk, "(문서)") if e.from_item_pk else "(문서)"
            if src not in grouped.setdefault(key, []):
                grouped[key].append(src)
        item_names = spec.describe_items([k[1] for k in grouped if k[0] == "item"])
        project_id = ProjectService(s).get(doc_id.split("-")[0]).id
        doc_names = _doc_refs(spec, project_id, [k[1] for k in grouped if k[0] == "doc"])
        out: list[UpstreamCheck] = []
        for (kind, pk), sources in grouped.items():
            ref = (item_names if kind == "item" else doc_names).get(pk)
            if ref is None or ref.doc_id is None:
                continue
            target_doc = spec.get_document(ref.doc_id)
            out.append(
                UpstreamCheck(ref, target_doc.current_version_no, target_doc.status, sources)
            )
        out.sort(
            key=lambda u: (
                STAGE_OF.get(u.target.doc_id.split("-")[1], 99),
                u.target.doc_id,
                u.target.item_id or "",
            )
        )
        return out
