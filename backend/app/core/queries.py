"""SYNC-MS-008 — queries. 읽기 조합. 서비스는 자기 묶음만 알고 여기서 ID로 잇는다. 쓰지 않는다.

B1: project_summary · document_list · document_view · item_view.
B2: project_detail · item_references_view. B3: project_items · diff_with_impact.
B4: graph_view · downstream_view · document_view 4a. 세션은 db.session_scope().
카드 V가 플래그·댓글·전파 조회(todo·decision_view·flag_view·upstream_checklist)를 걷어냈다.
카드 Y: ask_item이 ReAct 루프가 됐고, 도구 실행은 ask_tool이 여기 있는 조회로 닫는다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app import db
from app.config import settings
from app.core.account.models import User
from app.core.account.service import AccountService
from app.core.errors import ItemDeleted, LlmNotConfigured, LlmUnavailable, NotFound
from app.core.project.models import Project
from app.core.project.service import ProjectService
from app.core.reference.service import ReferenceService
from app.core.spec.service import SpecService
from app.core.types import (
    STAGE_OF,
    ApiAuthor,
    AskAnswer,
    AskEvent,
    AskNote,
    AskRead,
    AskStart,
    AuthorRef,
    BrokenRefSummary,
    ChainItem,
    ChainRow,
    Diff,
    DocStatus,
    Document,
    DocumentSummary,
    DownstreamDoc,
    DownstreamView,
    Graph,
    GraphEdge,
    GraphNode,
    GraphScope,
    ItemChain,
    ItemRef,
    ItemReferences,
    ItemView,
    ProjectDetail,
    ProjectSummary,
    RefEdge,
    StageSummary,
    ToolResult,
    ToolSpec,
    UserRef,
)
from app.infra import llm

_ORDER = {"draft": 0, "approved": 1}  # 둘뿐이다 — 하나라도 초안이면 초안 (UC-H14 1a)


def _summarize(
    project: Project, docs: list[DocumentSummary], per_doc: dict[int, int]
) -> ProjectSummary:
    """단계 11칸 계산(UC-H14 1a·1b).

    per_doc은 문서별 미존재 참조 수 — 단계 테두리(UI-2 2.2)에 쓴다.
    """
    stages: list[StageSummary] = []
    for doc_type, n in STAGE_OF.items():
        stage_docs = [d for d in docs if d.stage == n]
        status = min((d.status for d in stage_docs), key=lambda s: _ORDER[s], default=None)
        gate = bool(stage_docs) and any(
            s.doc_count > 0 and s.status != DocStatus.approved for s in stages
        )
        broken = sum(per_doc.get(d.id, 0) for d in stage_docs)
        stages.append(StageSummary(n, doc_type, status, len(stage_docs), gate, broken))
    counts = {
        "broken_ref": sum(per_doc.values()),  # 위에서 뜬 것을 다시 쓴다 (MS-008)
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


async def project_summary(user: User) -> list[ProjectSummary]:
    """SYNC-MS-008#queries.project_summary"""
    with db.session_scope() as s:
        out = []
        for p in ProjectService(s).list_owned(user):  # 내 것만 — 없으면 빈 목록(UI-2 빈 상태)
            docs = SpecService(s).list_by_project(p.id)
            # 프로젝트당 한 번. 단계마다 부르면 같은 프로젝트를 11번 훑는다
            per_doc = ReferenceService(s).count_missing_by_document([d.id for d in docs])
            out.append(_summarize(p, docs, per_doc))
        out.sort(key=lambda x: (x.updated_at is not None, x.updated_at), reverse=True)
        return out


async def project_detail(code: str, user: User) -> ProjectDetail:
    """SYNC-MS-008#queries.project_detail"""
    with db.session_scope() as s:
        project = ProjectService(s).get_owned(code, user)
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
    summary = next(p for p in await project_summary(user) if p.code == code)
    docs = await document_list(code, user)
    return ProjectDetail(
        **vars(summary),
        docs=docs,
        recent_changes=recent,
        last_processed_commit=last_commit,
        behind_by=behind,
    )


async def document_list(
    code: str, user: User, stage: int | None = None, status: DocStatus | None = None
) -> list[DocumentSummary]:
    """SYNC-MS-008#queries.document_list"""
    with db.session_scope() as s:
        project = ProjectService(s).get_owned(code, user)
        docs = SpecService(s).list_by_project(project.id, stage, status)
        ids = [d.id for d in docs]
        missing = ReferenceService(s).count_missing_by_document(ids)  # 쿼리 한 번 (N+1 금지)
        for d in docs:
            d.counts = {"broken_ref": missing.get(d.id, 0)}
            d.author = _api_author(s, d.last_author)
        return docs


async def trash_list(code: str, user: User) -> list[DocumentSummary]:
    """SYNC-MS-008#queries.trash_list"""
    with db.session_scope() as s:
        project = ProjectService(s).get_owned(code, user)
        docs = SpecService(s).list_trashed(project.id)
        for d in docs:
            d.author = _api_author(s, d.last_author)
        return docs


async def document_view(doc_id: str, user: User) -> Document:
    """SYNC-MS-008#queries.document_view"""
    with db.session_scope() as s:
        # 0. 본문을 읽기 전에 소유를 가른다 — 남의 문서가 잠깐이라도 비치면 안 된다
        project = ProjectService(s).get_owned(doc_id.split("-")[0], user)
        doc = SpecService(s).get_document(doc_id)
        doc.prev_doc_id, doc.next_doc_id = SpecService(s).neighbors(doc_id)
        # 4a — 유저용 탭이 링크를 회색 ?로, 미완성 배너가 완료 못 하는 이유로.
        # 중복은 접는다: 완료 게이트가 보는 값과 같아야 한다(MS-007 change_status 2단계)
        missing = [
            e
            for e in ReferenceService(s).upstream_of_document(doc.id, include_missing=True)
            if e.is_missing
        ]
        doc.missing_refs = sorted(dict.fromkeys(e.raw_target for e in missing))
        # 항목마다 자기 것 — UI-5 6.1 표시된 항목의 근거. 절 본문에서 온 것은 항목이 없다
        by_item: dict[int, list[str]] = {}
        for e in missing:
            if e.from_item_pk is None:
                continue
            targets = by_item.setdefault(e.from_item_pk, [])
            if e.raw_target not in targets:
                targets.append(e.raw_target)
        for item in doc.items:
            item.missing_refs = by_item.get(item.pk, [])
        doc.author = _api_author(s, doc.last_author)
        # 브레드크럼은 코드가 아니라 이름으로 시작한다 — 사람이 부르는 이름이 프로젝트다
        doc.project_name = project.name
        return doc


async def item_view(doc_id: str, item_id: str, user: User) -> ItemView:
    """SYNC-MS-008#queries.item_view"""
    with db.session_scope() as s:
        ProjectService(s).get_owned(doc_id.split("-")[0], user)
        return SpecService(s).get_item(doc_id, item_id)


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


async def item_references_view(doc_id: str, item_id: str, user: User) -> ItemReferences:
    """SYNC-MS-008#queries.item_references_view"""
    with db.session_scope() as s:
        ProjectService(s).get_owned(doc_id.split("-")[0], user)
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
        return ItemReferences(doc_id, item_id, upstream, downstream)


async def diff_with_impact(doc_id: str, from_no: int, to_no: int, user: User) -> Diff:
    """SYNC-MS-008#queries.diff_with_impact"""
    with db.session_scope() as s:
        ProjectService(s).get_owned(doc_id.split("-")[0], user)
        spec = SpecService(s)
        d = spec.diff(doc_id, from_no, to_no)
        ids = [h.item_id for h in d.hunks if h.item_id]
        pks = dict(zip(ids, spec.resolve_items(doc_id, ids), strict=False))
        by_id = {names.item_id: pk for pk, names in spec.describe_items(list(pks.values())).items()}
        counts = ReferenceService(s).count_downstream(list(by_id.values()))
        for h in d.hunks:
            h.downstream_count = counts.get(by_id.get(h.item_id or ""), 0)  # 새 항목은 0
        return d


async def project_items(code: str, kind: str, user: User) -> list:
    """SYNC-MS-008#queries.project_items"""
    with db.session_scope() as s:
        project = ProjectService(s).get_owned(code, user)
        spec = SpecService(s)
        if kind == "broken_ref":
            edges = ReferenceService(s).missing_in_project(project.id)
            names = spec.describe_items([e.from_item_pk for e in edges if e.from_item_pk])
            docs = _doc_refs(spec, [e.from_document_id for e in edges if e.from_item_pk is None])
            out: list[BrokenRefSummary] = []
            for e in edges:
                src = names.get(e.from_item_pk) if e.from_item_pk else docs.get(e.from_document_id)
                if src is None:
                    continue
                out.append(BrokenRefSummary(src, e.raw_target))
            return out
        if kind == "convention_errors":
            return spec.list_by_project(project.id, has_convention_error=True)
        if kind == "incomplete":
            return [d for d in spec.list_by_project(project.id) if d.incomplete_warnings]
        raise ValueError(f"unknown kind {kind}")  # 라우터가 enum으로 422를 낸다


async def graph_view(code: str, user: User, scope: GraphScope = GraphScope.all) -> Graph:
    """SYNC-MS-008#queries.graph_view

    11단계를 다 그리되 범위로 골라낸다. 잘라내는 게 아니다 (SYNC-UI-001#UI-8 7장 3).
    끝점이 범위 밖인 간선은 버린다 — 범위 밖과 미존재 참조는 다르다.
    """
    with db.session_scope() as s:
        project = ProjectService(s).get_owned(code, user)
        spec, refs = SpecService(s), ReferenceService(s)
        briefs = spec.list_items_by_project(project.id)
        if scope is GraphScope.approved:
            ok = {d.doc_id for d in spec.list_by_project(project.id, status=DocStatus.approved)}
            briefs = [b for b in briefs if b.doc_id in ok]
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
                GraphNode(n.id, n.doc_id, n.item_id, n.stage, n.id not in touched)
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


async def item_chain(doc_id: str, item_id: str, user: User) -> ItemChain:
    """SYNC-MS-008#queries.item_chain

    직접 참조가 아니라 전이적 폐포다. 역할은 어느 폐포에서 나왔는지로 정한다 —
    단계 번호로 정하면 되돌아오는 참조에서 근거를 파생으로 잘못 적는다.
    """
    with db.session_scope() as s:
        ProjectService(s).get_owned(doc_id.split("-")[0], user)
        spec, refs = SpecService(s), ReferenceService(s)
        pk = spec.resolve_item(doc_id, item_id)
        ups = _closure(pk, refs.upstream)
        downs = _closure(pk, refs.downstream)
        described = spec.describe_items([*ups, *downs, pk])
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
                ChainItem(ref, role, statuses.get(ref.doc_id, "draft"))
            )
        types = ["RFQ", "PRD", "SCN", "UC", "INFRA", "DOM", "UI", "API", "SEQ", "MS", "CODE"]
        return ItemChain(
            item=described[pk],
            upstream_count=len(ups),
            downstream_count=len(downs),
            # 항상 11행. 빈 단계도 남긴다 — 체인이 어디서 끊겼는지가 이 화면의 목적이다
            rows=[ChainRow(i + 1, t, by_stage.get(i + 1, [])) for i, t in enumerate(types)],
        )


async def downstream_view(doc_id: str, user: User) -> DownstreamView:
    """SYNC-MS-008#queries.downstream_view"""
    with db.session_scope() as s:
        ProjectService(s).get_owned(doc_id.split("-")[0], user)
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


_log = logging.getLogger(__name__)

_ASK_SYSTEM = """당신은 명세를 읽는 사람 옆에서 그 자리를 설명한다. 문서 하나가 열려 있고, 당신은 도구로
같은 프로젝트의 다른 문서와 항목을 읽을 수 있다. 읽기만 한다 — 쓰는 도구는 없다.

읽은 것만으로 답한다. 처음에는 아래 문서의 항목 목록만 있고 본문은 없다. 답에 필요한
본문은 도구로 읽는다. 보고 있는 항목 자체를 묻는 질문(이게 뭐야·왜 이렇게 했어)은 그
항목을 get_item으로 읽고 본문으로 답한다. 근거·영향을 물으면 get_references나
item_chain으로 관계를 따라간 뒤 필요한 항목만 get_item으로 읽는다. get_document는
문서 전체를 훑어야 할 때만 쓴다 — 크다. 앞 대화에서 읽은 것은 다시 실리지 않으므로
필요하면 다시 읽는다.

도구를 부를 때마다 reason에 한 줄로 무엇을 왜 읽는지 적는다. 그 줄이 사람에게 보인다.

도구는 여덟 번까지, 전체 두 분 안이다. 「지금까지 읽은 것으로 답하라」는 말을 받으면
더 읽지 않고 그때까지 읽은 것으로 답한다.

근거나 참조를 물으면 먼저 보고 있는 항목을 get_item으로 읽는다 — 본문의 [[문서#항목]]
링크가 정확한 문서 ID다. 항목 ID만으로 지금 문서를 짚지 않는다.

모른다는 읽어도 정말 없을 때만 말하고, 그때는 어느 명세 단계(RFQ~CODE)가 아직 안
쓰였는지 짚어 준다 — item_chain의 빈 단계나 「아직 없음」 참조가 그 근거다.
지어내지 않는다.

답에 근거를 댈 때는 읽은 항목 ID(문서ID#항목ID)를 그대로 쓴다. 없는 ID를 만들지 않는다.

명세를 고치라고 하지 않는다. 당신은 읽기를 돕는 자리이고, 본문을 쓰는 것은 사람과
그 사람의 에이전트가 한다.

[문서] {doc_id} {title} · 상태 {status} · v{version_no}
[이 문서의 항목]
{items}
{viewing}"""

_ASK_WRAP_UP = "도구 호출 상한(또는 시간 상한)에 닿았다. 지금까지 읽은 것으로 답하라. 못 읽은 것이 있으면 무엇을 못 읽었는지 말한다."

_ASK_MISSING_HINT = "이 문서에 그 항목이 없다. 다른 문서의 항목일 수 있다 — 보고 있는 항목을 get_item으로 읽어 본문의 참조 링크(문서ID#항목ID)에서 문서 ID를 확인하거나, get_references로 실제 위치를 찾아라"
_ASK_MAX_CALLS = 8  # 도구 호출 상한. 설정이 아니라 상수다 (사용자 결정 2026-09-22)
_ASK_TIME_LIMIT = 120.0  # 초. 호출 사이에서만 본다 — 호출 하나가 60초라 최악 180초

_REASON = {"type": "string", "description": "한 줄로 무엇을 왜 읽는지. 사람에게 보인다"}
_DOC = {"type": "string", "description": "문서 ID. 예: SYNC-PRD-001"}
_ITEM = {"type": "string", "description": "항목 ID. 예: R11, queries.ask_item"}


def _tool(name: str, description: str, props: dict[str, Any]) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {**props, "reason": _REASON},
            "required": [*props, "reason"],
        },
    )


# 설명은 SYNC-API-002 도구 설명 원문. 같은 이름·같은 뜻 — 에이전트가 이미 보는 것과 같다
_ASK_TOOLS: list[ToolSpec] = [
    _tool(
        "get_item",
        "문서 안 항목 하나의 본문 블록과 소속 문서의 상태·버전을 돌려준다. get_document로 문서 전체를 받는 대신 필요한 항목만 볼 때, 또는 본문에서 발견한 [[문서ID#항목ID]] 참조를 따라갈 때 부른다.",
        {"doc_id": _DOC, "item_id": _ITEM},
    ),
    _tool(
        "get_references",
        "항목의 상위 참조(이 항목이 근거로 삼은 것)와 하위 참조(이 항목을 근거로 삼은 것)를 나눠 돌려준다. 이 항목이 왜 있는지, 바꾸면 어디에 영향이 가는지 알아야 할 때 부른다. 목록만 주고 본문은 펼치지 않는다. 필요한 항목만 get_item으로 다시 요청한다. 문서 단위 참조는 제목·상태만, 아직 없는 대상은 note가 「아직 없음」이다.",
        {"doc_id": _DOC, "item_id": _ITEM},
    ),
    _tool(
        "item_chain",
        "항목에서 전이적으로 이어지는 상위·하위 항목을 11단계(RFQ~CODE) 행으로 돌려준다. ID와 이름만. 빈 단계도 행으로 남는다 — 어느 명세 단계가 아직 안 쓰였는지의 근거다.",
        {"doc_id": _DOC, "item_id": _ITEM},
    ),
    _tool(
        "list_documents",
        "이 프로젝트의 11단계별 문서 목록과 각 문서의 제목·상태·버전을 돌려준다. 어느 단계까지 채워졌는지 알아야 할 때 부른다. 문서 본문은 포함하지 않는다.",
        {},
    ),
    _tool(
        "get_document",
        "문서 원본 MD 전체와 상태·버전·항목 목록을 돌려준다. 크다 — 문서 전체를 훑어야 할 때만 쓴다. 본문 안 [[문서ID#항목ID]]는 다른 항목 참조이며 get_item으로 따라갈 수 있다.",
        {"doc_id": _DOC},
    ),
]


def _err(text: str, **extra: Any) -> ToolResult:
    return ToolResult(target=None, text=json.dumps({"error": text, **extra}, ensure_ascii=False))


def _ref_json(r: ItemRef) -> dict[str, Any]:
    if r.is_missing or (r.doc_id is None and r.item_id is None):
        return {"raw_target": r.raw_target, "note": "아직 없음"}
    if r.item_id is None:
        return {"doc_id": r.doc_id, "title": r.display_name}
    return {"id": f"{r.doc_id}#{r.item_id}", "name": r.display_name}


async def ask_tool(name: str, args: dict, code: str, user: User) -> ToolResult:
    """SYNC-MS-008#queries.ask_tool

    도구 하나 실행. 없음·삭제·다른 프로젝트·인자 빠짐은 예외가 아니라 {"error": …} 텍스트다 —
    모델이 되짚게 한다. 그 밖의 예외는 전파한다(→ error 이벤트). 소유 검사는 get_owned.
    """
    spec = next((t for t in _ASK_TOOLS if t.name == name), None)
    if spec is None:
        return _err(f"모르는 도구 {name}")
    missing = [k for k in spec.parameters["required"] if k not in args]
    if missing:
        return _err(f"인자 {'·'.join(missing)}가 없다")
    doc_id = str(args.get("doc_id", ""))
    if "doc_id" in spec.parameters["properties"] and doc_id.split("-")[0] != code:
        return _err("없음", doc_id=doc_id)  # 다른 프로젝트는 소유해도 없는 것과 같다
    item_id = str(args.get("item_id", "")).replace("~", "/")
    with db.session_scope() as s:  # 남의 프로젝트는 텍스트가 아니라 not-found 전파(→ error 이벤트)
        ProjectService(s).get_owned(code, user)
    try:
        if name == "get_item":
            v = await item_view(doc_id, item_id, user)
            data = {
                "doc_id": v.doc_id,
                "item_id": v.item_id,
                "display_name": v.display_name,
                "doc_status": v.doc_status,
                "doc_version_no": v.doc_version_no,
                "body": v.body,
            }
            return ToolResult(f"{doc_id}#{v.item_id}", json.dumps(data, ensure_ascii=False))
        if name == "get_references":
            r = await item_references_view(doc_id, item_id, user)
            with db.session_scope() as s:
                spec_svc = SpecService(s)
                doc_ids = [x.doc_id for x in r.upstream if x.item_id is None and x.doc_id]
                status = {}
                for did in doc_ids:
                    try:
                        status[did] = spec_svc.get_document(did).status
                    except NotFound:
                        pass
            up = [_ref_json(x) for x in r.upstream]
            for u in up:
                if "doc_id" in u:
                    u["status"] = status.get(u["doc_id"])
            data = {"upstream": up, "downstream": [_ref_json(x) for x in r.downstream]}
            return ToolResult(f"{doc_id}#{item_id}", json.dumps(data, ensure_ascii=False))
        if name == "item_chain":
            c = await item_chain(doc_id, item_id, user)
            data = {
                "item": _ref_json(c.item),
                "rows": [
                    {
                        "stage": row.stage,
                        "doc_type": row.doc_type,
                        "items": [
                            {**_ref_json(ci.ref), "role": ci.role, "status": ci.status}
                            for ci in row.items
                        ],
                    }
                    for row in c.rows
                ],
            }
            return ToolResult(f"{doc_id}#{item_id}", json.dumps(data, ensure_ascii=False))
        if name == "list_documents":
            docs = await document_list(code, user)
            with db.session_scope() as s:
                titles = SpecService(s).describe_documents([d.id for d in docs])
            data = [
                {
                    "doc_id": d.doc_id,
                    "stage": d.stage,
                    "doc_type": d.doc_type,
                    "title": titles[d.id].title if d.id in titles else "",
                    "status": d.status,
                    "version_no": d.current_version_no,
                }
                for d in docs
            ]
            return ToolResult(None, json.dumps(data, ensure_ascii=False))
        # get_document
        d = await document_view(doc_id, user)
        with db.session_scope() as s:
            title = _title_of(SpecService(s), doc_id)
        data = {
            "doc_id": d.doc_id,
            "title": title,
            "status": d.status,
            "version_no": d.current_version_no,
            "items": [{"item_id": i.item_id, "display_name": i.display_name} for i in d.items],
            "body": d.body,
        }
        return ToolResult(doc_id, json.dumps(data, ensure_ascii=False))
    except NotFound as e:
        extra = {k: v for k, v in e.extra.items() if k in ("resource", "id")}
        return _err("없음", hint=_ASK_MISSING_HINT, **extra)  # 되짚을 실마리 (#110)
    except ItemDeleted:
        return _err("삭제된 항목", doc_id=doc_id, item_id=item_id)


def _start_context(spec: SpecService, doc_id: str, item_id: str | None) -> tuple[str, Document]:
    """시작 맥락 — 제목·상태·버전·항목 ID·이름. 본문은 안 실는다(사용자 결정 3)."""
    d = spec.get_document(doc_id)
    refs = spec.describe_documents([d.id])
    title = refs[d.id].title if d.id in refs else doc_id
    viewing = ""
    if item_id is not None:
        item_id = item_id.replace("~", "/")
        it = next((i for i in d.items if i.item_id == item_id), None)
        if it is None:
            raise NotFound("item", f"{doc_id}#{item_id}")
        viewing = f"[지금 보는 항목] {it.item_id} {it.display_name or ''}".rstrip()
    items = "\n".join(f"{i.item_id} {i.display_name or ''}".rstrip() for i in d.items) or "(없음)"
    return _ASK_SYSTEM.format(
        doc_id=doc_id,
        title=title,
        status=d.status,
        version_no=d.current_version_no,
        items=items,
        viewing=viewing,
    ), d


async def ask_item(
    doc_id: str, item_id: str | None, question: str, history: list[dict], user: User
) -> AsyncIterator[AskEvent]:
    """SYNC-MS-008#queries.ask_item

    ReAct 루프. DOM-002 3.2 — queries가 어댑터를 직접 부르는 것은 llm 하나뿐이고, 도구 실행은
    여기 있는 조회(ask_tool)로 닫힌다. DB에 아무것도 쓰지 않는다. 첫 이벤트(start) 전의 오류는
    예외(상태 코드), 뒤의 오류는 라우터가 error 이벤트로 낸다.
    """
    if not settings.LLM_API_KEY:
        raise LlmNotConfigured()  # 네트워크를 타기 전에 막는다 (MS-008 0)
    history = history[-settings.LLM_MAX_TURNS :] if settings.LLM_MAX_TURNS > 0 else []
    code = doc_id.split("-")[0]
    with db.session_scope() as s:
        ProjectService(s).get_owned(code, user)
        system, _ = _start_context(SpecService(s), doc_id, item_id)
    yield AskStart(doc_id=doc_id, item_id=item_id)
    t0 = time.monotonic()
    calls = 0
    reads: list[str] = []
    prompt_tokens = completion_tokens = 0
    log: list[dict] = [{"role": m["role"], "text": m["text"]} for m in history]
    log.append({"role": "user", "text": question})
    answer: str | None = None
    while True:
        step = await llm.step(system, log, _ASK_TOOLS)
        prompt_tokens += step.usage.prompt_tokens
        completion_tokens += step.usage.completion_tokens
        if not step.tool_calls:
            answer = step.text or ""
            break
        if step.text:
            yield AskNote(step.text)
        log.append({"role": "assistant", "text": step.text or "", "tool_calls": step.tool_calls})
        for call in step.tool_calls:
            reason = str(call.arguments.get("reason") or "").strip()
            if reason:
                yield AskNote(reason)
            r = await ask_tool(call.name, call.arguments, code, user)
            yield AskRead(call.name, r.target)
            if r.target and r.target not in reads:
                reads.append(r.target)
            log.append({"role": "tool", "tool_call_id": call.id, "text": r.text})
            calls += 1
        if calls >= _ASK_MAX_CALLS or time.monotonic() - t0 >= _ASK_TIME_LIMIT:
            log.append({"role": "user", "text": _ASK_WRAP_UP})
            last = await llm.step(system, log, _ASK_TOOLS, tool_choice="none")
            prompt_tokens += last.usage.prompt_tokens
            completion_tokens += last.usage.completion_tokens
            if not last.text:
                raise LlmUnavailable("상한 뒤에도 답이 없다")
            answer = last.text
            break
    _log.info(
        "ask doc=%s item=%s user=%s calls=%d prompt=%d completion=%d elapsed=%.1fs",
        doc_id,
        item_id,
        user.id,
        calls,
        prompt_tokens,
        completion_tokens,
        time.monotonic() - t0,
    )
    yield AskAnswer(answer=answer, context_item_ids=reads)
