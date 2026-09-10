"""SYNC-MS-008 — queries. 읽기 조합. 서비스는 자기 묶음만 알고 여기서 ID로 잇는다. 쓰지 않는다.

B1: project_summary · document_list · document_view · item_view.
B2: project_detail · item_references_view · upstream_checklist.
B3: todo · decision_view · flag_view · project_items · diff_with_impact.
B4: graph_view · downstream_view · document_view 4a. 세션은 db.session_scope().
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import db
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.collab.service import CommentService
from app.core.project.models import Project
from app.core.project.service import ProjectService
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.tracking.service import TrackingService
from app.core.types import (
    STAGE_OF,
    AffectedItem,
    ApiAuthor,
    AuthorRef,
    ChainItem,
    ChainRow,
    DecisionDetail,
    Diff,
    DocStatus,
    Document,
    DocumentSummary,
    DownstreamDoc,
    DownstreamView,
    FlagDetail,
    FlagKind,
    FlagSummary,
    Graph,
    GraphEdge,
    GraphNode,
    GraphScope,
    ItemChain,
    ItemRef,
    ItemReferences,
    ItemView,
    PendingDecision,
    ProjectDetail,
    ProjectSummary,
    RefEdge,
    StageSummary,
    Todo,
    UpstreamCheck,
    UserRef,
    Version,
)

_ORDER = {"draft": 0, "review": 1, "approved": 2}


def _summarize(
    project: Project,
    docs: list[DocumentSummary],
    flags: dict[str, int],
    unresolved: int,
    per_doc: dict[int, dict[str, int]],
) -> ProjectSummary:
    """단계 11칸 계산(UC-H14 1a·1b). per_doc은 문서별 플래그 건수 — 단계 테두리(UI-2 2.2)에 쓴다."""
    stages: list[StageSummary] = []
    for doc_type, n in STAGE_OF.items():
        stage_docs = [d for d in docs if d.stage == n]
        status = min((d.status for d in stage_docs), key=lambda s: _ORDER[s], default=None)
        gate = bool(stage_docs) and any(
            s.doc_count > 0 and s.status != DocStatus.approved for s in stages
        )
        flag_count = sum(sum(per_doc.get(d.id, {}).values()) for d in stage_docs)
        stages.append(StageSummary(n, doc_type, status, len(stage_docs), gate, flag_count))
    counts = {
        "needs_check": flags.get("needs_check", 0),
        "broken_ref": flags.get("broken_ref", 0),
        # 세 종류를 다 싣는다. 빼면 내 할 일에는 뜨는데 요약에는 안 잡힌다 (UI-4 3.6)
        "upstream_impact": flags.get("upstream_impact", 0),
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
            # 프로젝트당 한 번. 단계마다 부르면 같은 프로젝트를 11번 훑는다
            per_doc = TrackingService(s).count_flags_by_document([d.id for d in docs])
            unresolved = CommentService(s).count_unresolved(p.id)
            out.append(_summarize(p, docs, flags, unresolved, per_doc))
        out.sort(key=lambda x: (x.updated_at is not None, x.updated_at), reverse=True)
        return out


async def project_detail(code: str) -> ProjectDetail:
    """SYNC-MS-008#queries.project_detail"""
    with db.session_scope() as s:
        project = ProjectService(s).get(code)
        recent = SpecService(s).recent_changes(project.id, 10)
        ids = [r.author.user_id for r in recent] + [
            r.author.instructed_by_id for r in recent if r.author.instructed_by_id
        ]
        names: dict[int, UserRef] = AccountService(s).users_by_ids(ids)
        for r in recent:
            r.author_view = ApiAuthor(
                kind=r.author.kind,
                user=names.get(r.author.user_id),
                instructed_by=names.get(r.author.instructed_by_id)
                if r.author.instructed_by_id
                else None,
                via=r.author.via,
            )
        # DB에 적힌 값 그대로 (MS-008 5). 폴링이 갱신하고 화면은 읽기만 한다
        repo = project.repository
        last_commit, behind = repo.last_processed_commit, repo.behind_by
    summary = next(p for p in await project_summary() if p.code == code)
    docs = await document_list(code)
    return ProjectDetail(
        **vars(summary),
        docs=docs,
        recent_changes=recent,
        last_processed_commit=last_commit,
        behind_by=behind,
    )


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
        doc.missing_refs = [
            e.raw_target
            for e in ReferenceService(s).upstream_of_document(doc.id, include_missing=True)
            if e.is_missing
        ]  # 4a — 유저용 탭이 링크를 회색 ?로
        doc.author = _api_author(s, doc.last_author)
        # 브레드크럼은 코드가 아니라 이름으로 시작한다 — 사람이 부르는 이름이 프로젝트다
        doc.project_name = ProjectService(s).get(doc_id.split("-")[0]).name
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
    versions = spec.versions_by_ids([f.cause_version_id for f in rows if f.cause_version_id])
    return [
        FlagSummary(
            id=f.id,
            kind=f.kind,
            target=names.get(f.target_item_id) or ItemRef(None, None, None),
            cause=names.get(f.cause_item_id) if f.cause_item_id else None,
            cause_version_no=(
                versions[f.cause_version_id].version_no if f.cause_version_id in versions else None
            ),
            assignee=users.get(f.assignee_user_id) if f.assignee_user_id else None,
            raised_at=f.raised_at,
            resolved_at=f.resolved_at,
        )
        for f in rows
    ]


def _doc_refs(spec: SpecService, document_ids: list[int]) -> dict[int, ItemRef]:
    """문서 단위 참조 대상 → ItemRef(item_id=None, 제목). describe_documents(MS-008 5단계)."""
    return {
        i: ItemRef(doc_id=r.doc_id, item_id=None, display_name=r.title)
        for i, r in spec.describe_documents(document_ids).items()
    }


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
        doc_names = _doc_refs(
            spec, [e.to_document_id for e in up if e.to_document_id and not e.to_item_pk]
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
        doc_names = _doc_refs(spec, [k[1] for k in grouped if k[0] == "doc"])
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


async def diff_with_impact(doc_id: str, from_no: int, to_no: int) -> Diff:
    """SYNC-MS-008#queries.diff_with_impact"""
    with db.session_scope() as s:
        spec = SpecService(s)
        d = spec.diff(doc_id, from_no, to_no)
        ids = [h.item_id for h in d.hunks if h.item_id]
        pks = dict(zip(ids, spec.resolve_items(doc_id, ids), strict=False))
        by_id = {names.item_id: pk for pk, names in spec.describe_items(list(pks.values())).items()}
        counts = ReferenceService(s).count_downstream(list(by_id.values()))
        for h in d.hunks:
            h.downstream_count = counts.get(by_id.get(h.item_id or ""), 0)  # 새 항목은 0
        return d


async def project_items(code: str, kind: str) -> list:
    """SYNC-MS-008#queries.project_items"""
    with db.session_scope() as s:
        project = ProjectService(s).get(code)
        spec = SpecService(s)
        if kind in ("needs_check", "broken_ref", "upstream_impact"):
            return flag_summaries(
                s, TrackingService(s).flags_in_project(project.id, FlagKind(kind))
            )
        if kind == "comments":
            ids = [d.id for d in spec.list_by_project(project.id)]
            return CommentService(s).unresolved_in(ids)
        if kind == "convention_errors":
            return spec.list_by_project(project.id, has_convention_error=True)
        if kind == "incomplete":
            return [d for d in spec.list_by_project(project.id) if d.incomplete_warnings]
        raise ValueError(f"unknown kind {kind}")  # 라우터가 enum으로 422를 낸다


async def todo(user: User) -> Todo:
    """SYNC-MS-008#queries.todo"""
    with db.session_scope() as s:
        spec, tracking, collab = SpecService(s), TrackingService(s), CommentService(s)
        nc, br, ui = tracking.flags_for_assignee(user.id)
        un = tracking.flags_unassigned()
        summaries = {f.id: f for f in flag_summaries(s, nc + br + ui + un)}  # describe 한 번
        pick = lambda rows: sorted((summaries[f.id] for f in rows), key=lambda f: f.raised_at)  # noqa: E731
        mine = spec.versions_instructed_by(tracking.pending_decisions_for(user.id), user.id)
        vb = spec.versions_by_ids(mine)
        docs = spec.describe_documents([v.document_id for v in vb.values()])
        pending = sorted(
            (
                PendingDecision(
                    version_id=v.id,
                    doc_id=docs[v.document_id].doc_id,
                    version_no=v.version_no,
                    message=v.message,
                    affected_count=tracking.get_decision(v.id).affected_count,
                    created_at=v.created_at,
                )
                for v in vb.values()
            ),
            key=lambda p: p.created_at,
        )
        errors = spec.convention_error_docs_by(user.id)
        for d in errors:
            d.author = _api_author(s, d.last_author)
        comments = sorted(
            collab.unresolved_in(spec.documents_authored_by(user.id)), key=lambda c: c.created_at
        )
        groups = (pick(nc), pick(br), pick(ui), pending, errors, comments)
        return Todo(*groups, unassigned=pick(un), total=sum(len(g) for g in groups))


async def decision_view(version_id: int) -> DecisionDetail:
    """SYNC-MS-008#queries.decision_view"""
    with db.session_scope() as s:
        spec, tracking, refs = SpecService(s), TrackingService(s), ReferenceService(s)
        dec = tracking.get_decision(version_id)
        vb = spec.versions_by_ids([version_id])[version_id]
        doc_id = spec.describe_documents([vb.document_id])[vb.document_id].doc_id
        prev_no = vb.version_no - 1
        # 미결정은 이전 버전이 있을 때만 생긴다(UC-S3 1a) — prev_no == 0은 오지 않는다
        change_diff = spec.diff(doc_id, prev_no, vb.version_no) if prev_no else Diff(0, 1, [])
        changed = set(dec.changed_pks)
        names = spec.describe_items(list(dec.affected_pks) + list(changed))
        authors: dict[str, AuthorRef | None] = {}
        affected: list[AffectedItem] = []
        for pk in dec.affected_pks:
            ref = names.get(pk)
            if ref is None:
                continue
            if ref.doc_id not in authors:
                authors[ref.doc_id] = spec.get_document(ref.doc_id).last_author
            causes = [
                names[e.to_item_pk].item_id for e in refs.upstream(pk) if e.to_item_pk in changed
            ]
            affected.append(
                AffectedItem(
                    **vars(ref),
                    caused_by_items=[c for c in causes if c],
                    assignee=_user_ref(s, authors[ref.doc_id]),
                )
            )
        version = Version(
            doc_id=doc_id,
            version_no=vb.version_no,
            commit_hash=vb.commit_hash,
            message=vb.message,
            author=vb.author,  # type: ignore[arg-type]
            created_at=vb.created_at,
            author_view=_api_author(s, vb.author),
        )
        return DecisionDetail(version, doc_id, change_diff, affected, dec.choice)


def _user_ref(s: Session, ref: AuthorRef | None) -> UserRef | None:
    return AccountService(s).users_by_ids([ref.user_id]).get(ref.user_id) if ref else None


async def flag_view(flag_id: int) -> FlagDetail:
    """SYNC-MS-008#queries.flag_view"""
    with db.session_scope() as s:
        spec, tracking = SpecService(s), TrackingService(s)
        f = tracking.get_flag(flag_id)
        base = flag_summaries(s, [f])[0]
        names = spec.describe_items(
            [f.target_item_id] + ([f.cause_item_id] if f.cause_item_id else [])
        )
        cause = names.get(f.cause_item_id) if f.cause_item_id else None
        detail = FlagDetail(**vars(base))
        if f.kind == FlagKind.needs_check and cause and cause.doc_id and base.cause_version_no:
            cur_no = spec.get_document(cause.doc_id).current_version_no
            detail.cause_change_count = cur_no - base.cause_version_no
            detail.cause_diff = (
                spec.diff(cause.doc_id, base.cause_version_no, cur_no)
                if cur_no != base.cause_version_no
                else Diff(cur_no, cur_no, [])
            )
        elif f.kind == FlagKind.broken_ref and cause:
            detail.cause_deleted_at = cause.deleted_at
        elif f.kind == FlagKind.upstream_impact:
            if cause and cause.doc_id and cause.item_id:
                detail.cause_body = spec.get_item(cause.doc_id, cause.item_id).body
            elif f.cause_version_id:
                vb = spec.versions_by_ids([f.cause_version_id])[f.cause_version_id]
                doc = spec.describe_documents([vb.document_id])[vb.document_id]
                detail.cause_body = f"{doc.title} (문서 단위 지목)"
        target = names[f.target_item_id]
        assert target.doc_id and target.item_id
        item = spec.get_item(target.doc_id, target.item_id)
        detail.target_body, detail.target_version_no = item.body, item.doc_version_no
        tdoc = spec.get_document(target.doc_id)
        latest = spec.versions_by_ids([tdoc.current_version_id])[tdoc.current_version_id]  # type: ignore[index]
        detail.target_changed_since_raise = latest.created_at > f.raised_at
        return detail


async def graph_view(code: str, scope: GraphScope = GraphScope.all) -> Graph:
    """SYNC-MS-008#queries.graph_view

    11단계를 다 그리되 범위로 골라낸다. 잘라내는 게 아니다 (SYNC-UI-001#UI-8 7장 3).
    끝점이 범위 밖인 간선은 버린다 — 범위 밖과 미존재 참조는 다르다.
    """
    with db.session_scope() as s:
        project = ProjectService(s).get(code)
        spec, refs = SpecService(s), ReferenceService(s)
        briefs = spec.list_items_by_project(project.id)
        flags = TrackingService(s).flags_for_items([b.pk for b in briefs if b.item_id])
        if scope is GraphScope.approved:
            ok = {d.doc_id for d in spec.list_by_project(project.id, status=DocStatus.approved)}
            briefs = [b for b in briefs if b.doc_id in ok]
        elif scope is GraphScope.flagged:
            briefs = [b for b in briefs if b.item_id and flags.get(b.pk)]
        item_ids = {b.pk: f"{b.doc_id}#{b.item_id}" for b in briefs if b.item_id}
        doc_ids = {b.pk: b.doc_id for b in briefs if b.item_id is None}
        edges = refs.references_among(set(item_ids), include_document_targets=True)
        nodes: dict[str, GraphNode] = {
            (f"{b.doc_id}#{b.item_id}" if b.item_id else b.doc_id): GraphNode(
                f"{b.doc_id}#{b.item_id}" if b.item_id else b.doc_id,
                b.doc_id,
                b.item_id,
                b.stage,
                True,
                bool(flags.get(b.pk)),
            )
            for b in briefs
        }
        out_edges: list[GraphEdge] = []
        touched: set[str] = set()
        for e in edges:
            src = (
                item_ids.get(e.from_item_pk) if e.from_item_pk else doc_ids.get(e.from_document_id)
            )
            if src is None:
                continue
            dst = None
            if e.to_item_pk is not None:
                dst = item_ids.get(e.to_item_pk)
                if dst is None:
                    continue  # 대상이 범위 밖이다. 미존재 참조가 아니므로 그리지 않는다
            elif e.to_document_id is not None:
                dst = doc_ids.get(e.to_document_id)
                if dst is None:
                    continue
            out_edges.append(GraphEdge(src, dst, e.raw_target, e.is_missing))
            touched.add(src)
            if dst:
                touched.add(dst)
        return Graph(
            nodes=[
                GraphNode(n.id, n.doc_id, n.item_id, n.stage, n.id not in touched, n.has_flag)
                for n in nodes.values()
            ],
            edges=out_edges,
            project_name=project.name,
        )


def _closure(start: int, step) -> set[int]:
    """한 방향으로 너비 우선. 방문 표시로 사이클을 멈추고 자기 자신은 뺀다 (MS-008)."""
    seen: set[int] = set()
    queue = [start]
    while queue:
        pk = queue.pop(0)
        for e in step(pk):
            nxt = e.to_item_pk if step.__name__ == "upstream" else e.from_item_pk
            if nxt is not None and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    seen.discard(start)
    return seen


async def item_chain(doc_id: str, item_id: str) -> ItemChain:
    """SYNC-MS-008#queries.item_chain

    직접 참조가 아니라 전이적 폐포다. 역할은 어느 폐포에서 나왔는지로 정한다 —
    단계 번호로 정하면 되돌아오는 참조에서 근거를 파생으로 잘못 적는다.
    """
    with db.session_scope() as s:
        spec, refs = SpecService(s), ReferenceService(s)
        pk = spec.resolve_item(doc_id, item_id)
        ups = _closure(pk, refs.upstream)
        downs = _closure(pk, refs.downstream)
        described = spec.describe_items([*ups, *downs, pk])
        flags = TrackingService(s).flags_for_items([*ups, *downs, pk])
        doc_ids = {r.doc_id for r in described.values() if r.doc_id}
        statuses = {did: spec.get_document(did).status for did in doc_ids}
        by_stage: dict[int, list[ChainItem]] = {}
        for p_, role in [
            (pk, "self"),
            *[(u, "upstream") for u in ups],
            *[(d, "downstream") for d in downs],
        ]:
            ref = described.get(p_)
            if ref is None or ref.doc_id is None:
                continue
            stage = STAGE_OF.get(ref.doc_id.split("-")[1])
            if stage is None:
                continue  # STD는 단계 밖이라 체인에 안 놓는다
            by_stage.setdefault(stage, []).append(
                ChainItem(ref, role, statuses.get(ref.doc_id, "draft"), bool(flags.get(p_)))
            )
        types = ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE"]
        return ItemChain(
            item=described[pk],
            upstream_count=len(ups),
            downstream_count=len(downs),
            # 항상 11행. 빈 단계도 남긴다 — 체인이 어디서 끊겼는지가 이 화면의 목적이다
            rows=[ChainRow(i + 1, t, by_stage.get(i + 1, [])) for i, t in enumerate(types)],
        )


async def downstream_view(doc_id: str) -> DownstreamView:
    """SYNC-MS-008#queries.downstream_view"""
    with db.session_scope() as s:
        spec, refs = SpecService(s), ReferenceService(s)
        document = spec.get_document(doc_id)
        pks = spec.item_pks(document.id)
        by_pk = {pk: item_id for item_id, pk in pks.items()}
        edges = [
            e
            for e in refs.references_among(set(pks.values()), include_document_targets=True)
            if (e.to_item_pk in by_pk) or e.to_document_id == document.id
        ]
        names = spec.describe_items([e.from_item_pk for e in edges if e.from_item_pk])
        docs = spec.describe_documents(
            [e.from_document_id for e in edges if e.from_document_id is not None]
        )
        by_item: dict[str, list[ItemRef]] = {}
        by_doc: dict[str, set[str]] = {}
        for e in edges:
            key = by_pk[e.to_item_pk] if e.to_item_pk in by_pk else "(문서)"
            if e.from_item_pk and e.from_item_pk in names:
                ref = names[e.from_item_pk]
            elif e.from_document_id in docs:
                d = docs[e.from_document_id]
                ref = ItemRef(d.doc_id, None, d.title, raw_target=e.raw_target)
            else:
                continue
            if ref.doc_id == doc_id:
                continue  # 같은 문서 안 참조는 추적표 대상이 아니다
            by_item.setdefault(key, []).append(ref)
            by_doc.setdefault(ref.doc_id or "", set()).add(key)
        titles = {d.doc_id: d.title for d in spec.describe_documents(list(docs)).values()} | {
            r.doc_id: "" for rs in by_item.values() for r in rs if r.doc_id
        }
        for did in list(titles):
            if not titles[did]:
                titles[did] = _title_of(spec, did)
        by_document = sorted(
            (DownstreamDoc(d, titles.get(d, d), sorted(items)) for d, items in by_doc.items()),
            key=lambda x: (STAGE_OF.get(x.doc_id.split("-")[1], 99), x.doc_id),
        )
        return DownstreamView(by_item, by_document)


def _title_of(spec: SpecService, doc_id: str) -> str:
    try:
        d = spec.get_document(doc_id)
    except Exception:  # noqa: BLE001
        return doc_id
    refs = spec.describe_documents([d.id])
    return refs[d.id].title if d.id in refs else doc_id
