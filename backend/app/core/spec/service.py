"""SYNC-MS-002 — SpecService. documents·items·versions·status_changes만.

다른 묶음 것은 인자로 받는다. 항목 판정은 item_blocks 한 곳(SYNC-STD-001 1.3).
"""

from __future__ import annotations

import difflib
import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.core.account.models import User
from app.core.errors import (
    ConventionViolation,
    ItemDeleted,
    NotFound,
)
from app.core.markdown import DOC_ID, HEADING, REF, cut_blocks, masked_lines, parse_frontmatter
from app.core.spec.models import Document as DocumentRow
from app.core.spec.models import Item, StatusChange
from app.core.spec.models import Version as VersionRow
from app.core.spec.repository import SpecRepository
from app.core.types import (
    STAGE_OF,
    Author,
    AuthorRef,
    Diff,
    DiffLine,
    DocItem,
    DocRef,
    DocStatus,
    DocType,
    Document,
    DocumentSummary,
    Entry,
    Hunk,
    ItemBlock,
    ItemBrief,
    ItemRef,
    ItemView,
    ValidateResult,
    Version,
    VersionBrief,
    Violation,
    Warning,
    fold_via,
)

# ── SYNC-STD-001 2장 — 타입별 항목 패턴·필수 절 (tools/validate.py가 원형) ──
TYPES: dict[str, tuple[list[str], list[str]]] = {
    "RFQ": ([r"Q\d+"], ["배경", "요구", "사용자와 환경", "미정"]),
    "PRD": ([r"G\d+", r"R\d+", r"N\d+"], ["목표", "비목표", "요구사항", "성공지표", "미결사항"]),
    "SCN": ([r"P\d+", r"S\d+"], ["페르소나", "시나리오", "대응표"]),
    "UC": (
        [r"UC-[AHGS]\d+"],
        ["액터", "사용자 목표 수준 유스케이스", "하위기능 수준 유스케이스", "대응표"],
    ),
    "INFRA": (
        [r"C\d+"],
        ["제약", "구성도", "기술 스택", "데이터가 사는 곳", "인증과 접근", "미결사항"],
    ),
    "DOM": ([r"[A-Z][A-Za-z]+", r"[a-z][a-z0-9_]+"], []),
    "UI": ([r"UI-\d+"], []),
    "API": ([r"(GET|POST|PUT|PATCH|DELETE)/\S+", r"[a-z][a-z_]+"], []),
    "SEQ": ([r"SEQ-\d+", r"SEQ-C\d+"], ["생명선", "대응표", "되먹일 것"]),
    "MS": ([r"[A-Za-z_]+\.[a-z_]+"], ["함수 목록", "미결사항"]),
    "CODE": ([r"[A-Z]\d*"], ["슬라이스", "통합 테스트", "커밋", "미결사항"]),
    "STD": ([r"[A-Z]+-\d+", r"V-[A-Z]+"], ["미결사항"]),
}
SUBTYPES: dict[tuple[str, str], tuple[list[str], list[str]]] = {
    ("DOM", "도메인"): (
        [r"[A-Z][A-Za-z]+"],
        ["개념 식별", "개념 모델", "개념별 정리", "경계", "미결사항"],
    ),
    ("DOM", "클래스"): (
        [r"[A-Z][A-Za-z]+"],
        ["폴더 구조", "엔티티", "의존 관계", "설계 클래스", "미결사항"],
    ),
    ("DOM", "ERD"): ([r"[a-z][a-z0-9_]+"], ["ERD", "DD", "인덱스", "미결사항"]),
    ("UI", "화면 설계"): (
        [r"UI-\d+"],
        ["유스케이스 대응", "화면 목록", "공통 틀", "화면 흐름", "미결사항"],
    ),
    ("UI", "와이어프레임"): ([r"UI-\d+"], ["형식"]),
    ("API", "REST"): (
        [r"(GET|POST|PUT|PATCH|DELETE)/\S+"],
        ["규칙", "에러", "엔드포인트", "미결사항"],
    ),
    ("API", "MCP"): ([r"[a-z][a-z_]+"], ["규칙", "도구", "에이전트 순서", "미결사항"]),
}


def patterns_for(doc_type: str, title: str | None) -> tuple[re.Pattern[str] | None, list[str]]:
    pats, secs = TYPES.get(doc_type, ([], []))
    for (t, key), (p, s) in SUBTYPES.items():
        if t == doc_type and title and key in title:
            pats, secs = p, s
    return (re.compile("^(?:" + "|".join(pats) + ")$") if pats else None), secs


class SpecService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SpecRepository(session)

    def item_blocks(
        self, body: str, doc_type: DocType, title: str | None = None
    ) -> list[ItemBlock]:
        """SYNC-MS-002#SpecService.item_blocks"""
        if title is None:
            title = parse_frontmatter(body)[0].get("title")
        item_re, _ = patterns_for(doc_type, title)
        if item_re is None:
            return []
        return cut_blocks(body, lambda tok: bool(item_re.match(tok)))

    def validate(
        self,
        body: str,
        doc_type: DocType,
        entry: Entry,
        current_status: DocStatus | None = None,
    ) -> ValidateResult:
        """SYNC-MS-002#SpecService.validate"""
        V: list[Violation] = []
        W: list[Warning] = []
        fm, _ = parse_frontmatter(body)
        # 1. frontmatter
        if not fm:
            V.append(Violation(1, "frontmatter.missing", "frontmatter 블록 없음"))
        else:
            for f in ("doc_id", "type", "title", "status"):
                if f not in fm:
                    V.append(Violation(2, "frontmatter.field", f"필수 필드 {f} 없음"))
            if fm.get("type", "") not in TYPES:
                V.append(Violation(2, "frontmatter.type", f"type {fm.get('type')!r}"))
            if fm.get("status") not in ("draft", "review", "approved"):
                V.append(Violation(2, "frontmatter.status", str(fm.get("status"))))
            did = fm.get("doc_id", "")
            if not DOC_ID.match(did):
                V.append(Violation(2, "frontmatter.doc_id", f"형식 {did!r}"))
            elif did.split("-")[1] != doc_type:
                V.append(Violation(2, "frontmatter.doc_id", f"{did}의 타입 ≠ {doc_type}"))
            for u in re.findall(r"[\w-]+", fm.get("upstream", "").strip("[]")):
                if not DOC_ID.match(u):
                    V.append(Violation(2, "frontmatter.ref", f"upstream {u!r}"))
            # 2. MCP 경로의 status 변경
            if entry == Entry.mcp and current_status and fm.get("status") != current_status:
                V.append(Violation(2, "frontmatter.status_change", "상태 변경은 웹에서만(UC-H8)"))
        # 3. 헤딩 순회
        item_re, secs = patterns_for(doc_type, fm.get("title"))
        deleted = self._deleted_item_ids(fm.get("doc_id"))
        seen: set[str] = set()
        items: list[str] = []
        sections: list[str] = []
        lines = masked_lines(body)
        for i, line in enumerate(lines, start=1):
            h = HEADING.match(line)
            if not h:
                continue
            tok, text = h.group(2), h.group(2) + (" " + h.group(3) if h.group(3) else "")
            if item_re and item_re.match(tok):
                if tok in seen:
                    V.append(Violation(i, "item.duplicate", tok))
                seen.add(tok)
                items.append(tok)
                if tok in deleted:
                    V.append(Violation(i, "item.reused", f"{tok} — 삭제된 항목 ID 재사용"))
                if re.search(r"(?<![0-9])0\d", tok):
                    V.append(Violation(i, "item.padding", tok))
            else:
                if re.search(r"[.:]$", tok) and item_re and item_re.match(tok[:-1]):
                    V.append(Violation(i, "item.punct", tok))
                elif re.match(r"^[A-Z]+-?\d+$", tok) and item_re:
                    V.append(
                        Violation(
                            i, "item.pattern", f"{tok} — ID처럼 보이지만 {doc_type} 패턴 아님"
                        )
                    )
                sections.append(re.sub(r"^[\d.]+\s*", "", text))
                # 단어형 ID 타입에서만. 절 제목이 항목으로 오인될 위험이 그쪽에만 있다
                # (STD-001 1.6·4장). H1은 문서 제목이지 절이 아니다
                if (
                    len(h.group(1)) > 1
                    and item_re
                    and doc_type in ("DOM", "MS", "API")
                    and not re.match(r"^\d", tok)
                ):
                    W.append(Warning("section.unnumbered", text[:40]))
        # 4. 참조 형식
        for i, line in enumerate(lines, start=1):
            for r in REF.findall(line):
                d, _, it = r.partition("#")
                if d == "":
                    d = fm.get("doc_id", "")
                if not DOC_ID.match(d) or (it and " " in it):
                    V.append(Violation(i, "ref.format", r))
        # 5. 미완성
        for s in secs:
            if not any(sec.startswith(s) for sec in sections):
                W.append(Warning("section.missing", s))
        if not items and doc_type not in ("CODE", "STD"):
            W.append(Warning("item.none", ""))
        # 6. DOM 클래스 명세 — 2장·4장 엔티티 속성 대조
        if doc_type == "DOM" and "클래스" in (fm.get("title") or ""):
            W.extend(_entity_mismatch(body))
        return ValidateResult(V, W)

    def apply_frontmatter(
        self, body: str, doc_id: str, doc_type: DocType, status: DocStatus
    ) -> str:
        """SYNC-MS-002#SpecService.apply_frontmatter"""
        fm, fm_lines = parse_frontmatter(body)
        if not fm:
            m = re.search(r"^# (.+)$", body, re.M)
            title = m.group(1).strip() if m else doc_id
            return (
                f"---\ndoc_id: {doc_id}\ntype: {doc_type}\ntitle: {title}\nstatus: {status}\n---\n"
                + body
            )
        if fm.get("doc_id") and fm["doc_id"] != doc_id:
            raise ConventionViolation(
                [Violation(2, "frontmatter.doc_id", f"발급 {doc_id}와 다름: {fm['doc_id']}")]
            )
        forced = {"doc_id": doc_id, "type": str(doc_type), "status": str(status)}
        lines = body.split("\n")
        out: list[str] = []
        for line in lines[1 : fm_lines - 1]:
            k, sep, _ = line.partition(":")
            if sep and k.strip() in forced:
                out.append(f"{k.strip()}: {forced.pop(k.strip())}")
            else:
                out.append(line)
        out.extend(f"{k}: {v}" for k, v in forced.items())
        return "\n".join(["---", *out, "---", *lines[fm_lines:]])

    def issue_doc_id(self, project_id: int, code: str, doc_type: DocType) -> str:
        """SYNC-MS-002#SpecService.issue_doc_id"""
        return f"{code}-{doc_type}-{self.repo.max_doc_number(project_id, doc_type) + 1:03d}"

    def create(
        self,
        project_id: int,
        doc_id: str,
        doc_type: DocType,
        body: str,
        commit_hash: str,
        author: Author,
        message: str,
        validate_result: ValidateResult | None = None,
    ) -> VersionRow:
        """SYNC-MS-002#SpecService.create"""
        fm, _ = parse_frontmatter(body)
        row = DocumentRow(
            project_id=project_id,
            doc_id=doc_id,
            doc_type=str(doc_type),
            status=fm.get("status") or "draft",
            current_body=body,
            current_version_no=1,
            has_convention_error=False,
        )
        if validate_result is not None:  # save 7단계와 같은 규칙 — 첫 저장부터 경고가 남는다
            _apply_validate(row, validate_result)
        self.repo.add(row)
        for b in self.item_blocks(body, doc_type, fm.get("title")):
            self.session.add(
                Item(document_id=row.id, item_id=b.item_id, display_name=b.display_name)
            )
        version = self._new_version(row.id, 1, commit_hash, body, author, message)
        self.repo.add(version)
        return version

    def _new_version(
        self, document_id: int, no: int, commit_hash: str, body: str, author: Author, message: str
    ) -> VersionRow:
        return VersionRow(
            document_id=document_id,
            version_no=no,
            commit_hash=commit_hash,
            body=body,
            author_kind=str(author.kind),
            author_user_id=author.user.id,
            instructed_by_user_id=author.instructed_by.id if author.instructed_by else None,
            via=fold_via(author.via),
            message=message,
            created_at=now_utc(),
        )

    def get_document(self, doc_id: str) -> Document:
        """SYNC-MS-002#SpecService.get_document"""
        row = self.repo.document_by_doc_id(doc_id)
        if row is None:
            raise NotFound("document", doc_id)
        items = [
            DocItem(pk=i.id, item_id=i.item_id, display_name=i.display_name)
            for i in self.repo.items_of(row.id)
        ]
        latest = self.repo.latest_version(row.id)
        return Document(
            **self._summary_fields(row, latest),
            body=row.current_body,
            commit_hash=latest.commit_hash if latest else None,
            current_version_id=latest.id if latest else None,
            convention_error_detail=row.convention_error_detail,
            items=items,
        )

    def _summary_fields(self, row: DocumentRow, latest: VersionRow | None) -> dict:
        return {
            "id": row.id,
            "doc_id": row.doc_id,
            "doc_type": row.doc_type,
            "stage": STAGE_OF.get(row.doc_type),
            "status": row.status,
            "current_version_no": row.current_version_no,
            "has_convention_error": row.has_convention_error,
            "incomplete_warnings": json.loads(row.incomplete_warnings or "[]"),
            "updated_at": row.updated_at,
            "last_author": self._author_of(latest),
        }

    def _author_of(self, v: VersionRow | None) -> AuthorRef | None:
        """버전 행 → AuthorRef(id만). 이름은 queries가 AccountService.users_by_ids로."""
        if v is None:
            return None
        return AuthorRef(
            kind=v.author_kind,
            user_id=v.author_user_id,
            instructed_by_id=v.instructed_by_user_id,
            via=v.via,
        )

    def get_item(self, doc_id: str, item_id: str) -> ItemView:
        """SYNC-MS-002#SpecService.get_item"""
        document = self.get_document(doc_id)
        item_id = item_id.replace("~", "/")
        item = self.repo.item_of(document.id, item_id)
        if item is None:
            raise NotFound(
                "item",
                f"{doc_id}#{item_id}",
                available_items=[i.item_id for i in document.items],
            )
        if item.is_deleted:
            raise ItemDeleted(item.deleted_at.isoformat() if item.deleted_at else None)
        blocks = self.item_blocks(document.body, document.doc_type)
        block = next(b for b in blocks if b.item_id == item_id)
        return ItemView(
            pk=item.id,
            doc_id=doc_id,
            item_id=item_id,
            display_name=item.display_name,
            body=block.text,
            doc_status=document.status,
            doc_version_no=document.current_version_no,
        )

    def detect_deleted_items(self, document: Document, body: str) -> list[int]:
        """SYNC-MS-002#SpecService.detect_deleted_items"""
        new_ids = {b.item_id for b in self.item_blocks(body, document.doc_type)}
        return [i.id for i in self.repo.items_of(document.id) if i.item_id not in new_ids]

    def save(
        self,
        document: Document,
        body: str,
        commit_hash: str,
        author: Author,
        message: str,
        deleted_item_pks: list[int],
        validate_result: ValidateResult | None = None,
        rebuild: bool = False,
    ) -> VersionRow:
        """SYNC-MS-002#SpecService.save"""
        row = self.repo.document_by_id(document.id)
        assert row is not None
        # 재구축은 커밋 순서대로 다시 번호를 매긴다. current_version_no는 ≥1 제약(DOM-003)이라
        # 0으로 못 내리므로 남아 있는 버전 수 + 1 (보고)
        new_no = (self.repo.version_count(row.id) if rebuild else row.current_version_no) + 1
        version = self._new_version(row.id, new_no, commit_hash, body, author, message)
        self.repo.add(version)
        fm, _ = parse_frontmatter(body)
        for b in self.item_blocks(body, row.doc_type, fm.get("title")):
            item = self.repo.item_of(row.id, b.item_id)
            if item is not None:
                item.display_name = b.display_name
            else:
                self.session.add(
                    Item(document_id=row.id, item_id=b.item_id, display_name=b.display_name)
                )
        for item in self.repo.items_by_pks(deleted_item_pks):
            item.is_deleted, item.deleted_at = True, now_utc()
        new_status = fm.get("status", row.status) if author.via == Entry.github else row.status
        if row.status == DocStatus.approved and body != row.current_body:
            new_status = DocStatus.review
            self.session.add(
                StatusChange(
                    document_id=row.id,
                    from_status=DocStatus.approved,
                    to_status=DocStatus.review,
                    changed_by_user_id=author.user.id,
                    reason="본문 수정으로 자동 강등",
                    commit_hash=None,
                    changed_at=now_utc(),
                )
            )
        row.current_body = body
        row.current_version_no = new_no
        row.status = str(new_status)
        if validate_result is not None:
            _apply_validate(row, validate_result)
        self.session.flush()
        return version

    def list_by_project(
        self,
        project_id: int,
        stage: int | None = None,
        status: DocStatus | None = None,
        has_convention_error: bool | None = None,
    ) -> list[DocumentSummary]:
        """SYNC-MS-002#SpecService.list_by_project"""
        rows = self.repo.documents_of_project(project_id)
        if stage is not None:
            rows = [r for r in rows if STAGE_OF.get(r.doc_type) == stage]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        if has_convention_error is not None:
            rows = [r for r in rows if r.has_convention_error == has_convention_error]
        latest = self.repo.latest_versions([r.id for r in rows])
        rows.sort(key=lambda r: (STAGE_OF.get(r.doc_type, 99), r.doc_id))
        return [DocumentSummary(**self._summary_fields(r, latest.get(r.id))) for r in rows]

    def last_author(self, document_id: int) -> AuthorRef | None:
        """SYNC-MS-002#SpecService.last_author"""
        return self._author_of(self.repo.latest_version(document_id))

    def neighbors(self, doc_id: str) -> tuple[str | None, str | None]:
        """SYNC-MS-002#SpecService.neighbors"""
        row = self.repo.document_by_doc_id(doc_id)
        if row is None:
            raise NotFound("document", doc_id)
        stage = STAGE_OF.get(row.doc_type)
        if stage is None:
            return None, None
        docs = self.repo.documents_of_project(row.project_id)

        def first(n: int) -> str | None:
            ids = sorted(d.doc_id for d in docs if STAGE_OF.get(d.doc_type) == n)
            return ids[0] if ids else None

        return first(stage - 1), first(stage + 1)

    def item_pks(self, document_id: int) -> dict[str, int]:
        """SYNC-MS-002#SpecService.item_pks"""
        return {i.item_id: i.id for i in self.repo.items_of(document_id)}

    def resolve_item(self, doc_id: str, item_id: str) -> int:
        """SYNC-MS-002#SpecService.resolve_item"""
        row = self.repo.document_by_doc_id(doc_id)
        item = self.repo.item_of(row.id, item_id) if row else None
        if item is None:
            raise NotFound("item", f"{doc_id}#{item_id}")
        if item.is_deleted:
            raise ItemDeleted(item.deleted_at.isoformat() if item.deleted_at else None)
        return item.id

    def resolve_items(self, doc_id: str, item_ids: list[str]) -> list[int]:
        """SYNC-MS-002#SpecService.resolve_items"""
        row = self.repo.document_by_doc_id(doc_id)
        if row is None:
            return []
        return [i.id for i in self.repo.items_by_item_ids(row.id, item_ids)]

    def diff(
        self, doc_id: str, from_no: int, to_no: int, context: int = settings.DIFF_CONTEXT_LINES
    ) -> Diff:
        """SYNC-MS-002#SpecService.diff

        `context`는 앞뒤로 함께 보여줄 줄 수다. 한 줄이면 마크다운 문단에서 무엇이
        바뀌었는지는 보여도 어느 절의 변경인지가 안 보인다. detect_impact와 pipeline은
        hunk의 item_id만 쓰므로 이 값과 무관하게 같은 결과를 낸다.
        """
        row = self.repo.document_by_doc_id(doc_id)
        if row is None:
            raise NotFound("document", doc_id)
        bodies = self.repo.version_bodies(row.id, [from_no, to_no])
        for no in (from_no, to_no):
            if no not in bodies:
                raise NotFound("version", f"{doc_id} v{no}")
        src, dst = (
            self._split_items(bodies[from_no], row.doc_type),
            self._split_items(bodies[to_no], row.doc_type),
        )
        order = list(dst) + [k for k in src if k not in dst]
        order.sort(key=lambda k: k is None)  # 항목 밖 텍스트는 마지막
        hunks: list[Hunk] = []
        for item_id in order:
            a, b = src.get(item_id, ""), dst.get(item_id, "")
            if _normalized(a) == _normalized(b):
                continue  # 공백만 바뀜 → hunk 없음
            if not a or not b:  # 새로 생긴 항목은 전부 add, 사라진 항목은 전부 del
                op, text = ("add", b) if not a else ("del", a)
                lines = [DiffLine(op, ln) for ln in text.rstrip("\n").split("\n")]
            else:
                lines = [
                    DiffLine({"+": "add", "-": "del", " ": "ctx"}[ln[0]], ln[1:])
                    for ln in difflib.unified_diff(
                        a.split("\n"), b.split("\n"), n=context, lineterm=""
                    )
                    if ln[:3] not in ("---", "+++") and not ln.startswith("@@")
                ]
            hunks.append(Hunk(item_id=item_id, lines=lines))
        return Diff(from_version=from_no, to_version=to_no, hunks=hunks)

    def _split_items(self, body: str, doc_type: str) -> dict[str | None, str]:
        """본문 → {item_id: 블록 텍스트}. 항목 밖 텍스트는 None 키 하나 (MS-002 diff 2단계)."""
        blocks = self.item_blocks(body, DocType(doc_type))
        lines = body.split("\n")
        covered: set[int] = set()
        out: dict[str | None, str] = {}
        for blk in blocks:
            covered.update(range(blk.start_line - 1, blk.end_line))
            out[blk.item_id] = blk.text
        rest = "\n".join(ln for i, ln in enumerate(lines) if i not in covered)
        if rest.strip():
            out[None] = rest
        return out

    def apply_status(
        self,
        document: Document,
        new_body: str,
        commit_hash: str | None,
        user: User,
        reason: str | None,
        to: DocStatus | None = None,
    ) -> None:
        """SYNC-MS-002#SpecService.apply_status"""
        row = self.repo.document_by_id(document.id)
        assert row is not None
        to = to or parse_frontmatter(new_body)[0].get("status", row.status)
        self.session.add(
            StatusChange(
                document_id=row.id,
                from_status=row.status,
                to_status=str(to),
                changed_by_user_id=user.id,
                reason=reason,
                commit_hash=commit_hash,
                changed_at=now_utc(),
            )
        )
        row.status = str(to)
        row.current_body = new_body
        self.session.flush()

    def list_versions(self, doc_id: str) -> list[Version]:
        """SYNC-MS-002#SpecService.list_versions"""
        row = self.repo.document_by_doc_id(doc_id)
        if row is None:
            raise NotFound("document", doc_id)
        rows = [
            Version(
                doc_id=doc_id,
                version_no=v.version_no,
                commit_hash=v.commit_hash,
                message=v.message,
                author=self._author_of(v),  # type: ignore[arg-type]
                created_at=v.created_at,
            )
            for v in self.repo.versions_of(row.id)
        ] + [
            Version(
                doc_id=doc_id,
                version_no=None,
                commit_hash=c.commit_hash,  # type: ignore[arg-type]
                message=f"status({doc_id}): {c.from_status} → {c.to_status}",
                author=AuthorRef("human", c.changed_by_user_id, None, "web"),
                created_at=c.changed_at,
            )
            for c in self.repo.status_changes_with_commit(row.id)
        ]
        # 같은 시각이면 상태 변경을 먼저. 본문 커밋 뒤에 상태를 바꾸는 순서라
        # 시계가 같은 값을 줘도 순서가 흔들리지 않는다
        rows.sort(key=lambda r: (r.created_at, r.version_no is None), reverse=True)
        return rows

    def mark_deleted(self, document: Document, commit_hash: str, author: Author) -> list[int]:
        """SYNC-MS-002#SpecService.mark_deleted"""
        row = self.repo.document_by_id(document.id)
        assert row is not None
        pks: list[int] = []
        for item in self.repo.items_of(row.id):
            item.is_deleted, item.deleted_at = True, now_utc()
            pks.append(item.id)
        self.session.add(
            StatusChange(
                document_id=row.id,
                from_status=row.status,
                to_status=DocStatus.draft,
                changed_by_user_id=author.user.id,
                reason="파일 삭제됨",
                commit_hash=commit_hash,
                changed_at=now_utc(),
            )
        )
        row.status = str(DocStatus.draft)
        row.has_convention_error = True
        row.convention_error_detail = f"file.deleted: {commit_hash}"
        self.session.flush()
        return pks

    def list_items_by_project(
        self, project_id: int, stage: int | None = None, doc_id: str | None = None
    ) -> list[ItemBrief]:
        """SYNC-MS-002#SpecService.list_items_by_project"""
        out: list[ItemBrief] = []
        seen_docs: set[int] = set()
        docs = self.repo.documents_of_project(project_id)
        docs.sort(key=lambda r: (STAGE_OF.get(r.doc_type, 99), r.doc_id))
        for d in docs:
            if stage is not None and STAGE_OF.get(d.doc_type) != stage:
                continue
            if doc_id is not None and d.doc_id != doc_id:
                continue
            seen_docs.add(d.id)
            out.append(ItemBrief(d.id, d.doc_id, None, STAGE_OF.get(d.doc_type), None))
        for item, d in self.repo.items_of_project(project_id):
            if d.id in seen_docs:
                out.append(
                    ItemBrief(
                        item.id, d.doc_id, item.item_id, STAGE_OF.get(d.doc_type), item.display_name
                    )
                )
        return out

    def clear_index(self, project_id: int) -> None:
        """SYNC-MS-002#SpecService.clear_index"""
        # current_version_no=0(MS-002)은 DOM-003 ck_documents_version_no(≥1)에 걸린다 → 그대로 두고
        # save(rebuild=True)가 남은 버전 수로 번호를 매긴다 (보고)
        self.repo.delete_versions_of_project(project_id)
        self.session.flush()

    def version_body(self, doc_id: str, version_no: int) -> str:
        """SYNC-MS-002#SpecService.version_body"""
        row = self.repo.document_by_doc_id(doc_id)
        if row is None:
            raise NotFound("document", doc_id)
        bodies = self.repo.version_bodies(row.id, [version_no])
        if version_no not in bodies:
            raise NotFound("version", f"{doc_id} v{version_no}")
        return bodies[version_no]

    def mark_convention_error(
        self, document_id: int, violations: list | None, warnings: list | None
    ) -> None:
        """SYNC-MS-002#SpecService.mark_convention_error"""
        row = self.repo.document_by_id(document_id)
        assert row is not None
        _apply_validate(row, ValidateResult(list(violations or []), list(warnings or [])))
        self.session.flush()

    def recent_changes(self, project_id: int, n: int = 10) -> list[Version]:
        """SYNC-MS-002#SpecService.recent_changes"""
        rows: list[Version] = [
            Version(
                doc_id=doc_id,
                version_no=v.version_no,
                commit_hash=v.commit_hash,
                message=v.message,
                author=self._author_of(v),  # type: ignore[arg-type]
                created_at=v.created_at,
            )
            for v, doc_id in self.repo.recent_versions(project_id, n)
        ] + [
            Version(
                doc_id=doc_id,
                version_no=None,
                commit_hash=c.commit_hash,  # type: ignore[arg-type]
                message=f"status({doc_id}): {c.from_status} → {c.to_status}",
                author=AuthorRef("human", c.changed_by_user_id, None, "web"),
                created_at=c.changed_at,
            )
            for c, doc_id in self.repo.recent_status_changes(project_id, n)
        ]
        # 같은 시각이면 상태 변경을 먼저. 본문 커밋 뒤에 상태를 바꾸는 순서라
        # 시계가 같은 값을 줘도 순서가 흔들리지 않는다
        rows.sort(key=lambda r: (r.created_at, r.version_no is None), reverse=True)
        return rows[:n]

    def versions_instructed_by(self, version_ids: list[int], user_id: int) -> list[int]:
        """SYNC-MS-002#SpecService.versions_instructed_by"""
        return self.repo.version_ids_by_user(version_ids, user_id)

    def convention_error_docs_by(self, user_id: int) -> list[DocumentSummary]:
        """SYNC-MS-002#SpecService.convention_error_docs_by"""
        rows = [r for r in self.repo.documents_last_authored_by(user_id) if r.has_convention_error]
        latest = self.repo.latest_versions([r.id for r in rows])
        return [DocumentSummary(**self._summary_fields(r, latest.get(r.id))) for r in rows]

    def documents_authored_by(self, user_id: int) -> list[int]:
        """SYNC-MS-002#SpecService.documents_authored_by"""
        return [r.id for r in self.repo.documents_last_authored_by(user_id)]

    def describe_items(self, item_pks: list[int]) -> dict[int, ItemRef]:
        """SYNC-MS-002#SpecService.describe_items"""
        out: dict[int, ItemRef] = {}
        for item, doc_id in self.repo.items_with_doc_id(item_pks):
            out[item.id] = ItemRef(
                doc_id=doc_id,
                item_id=item.item_id,
                display_name=item.display_name,
                is_deleted=item.is_deleted,
                deleted_at=item.deleted_at,
            )
        return out

    def describe_documents(self, document_ids: list[int]) -> dict[int, DocRef]:
        """SYNC-MS-002#SpecService.describe_documents"""
        out: dict[int, DocRef] = {}
        for row in self.repo.documents_by_ids(document_ids):
            title = parse_frontmatter(row.current_body)[0].get("title") or row.doc_id
            out[row.id] = DocRef(
                document_id=row.id,
                doc_id=row.doc_id,
                title=title,
                stage=STAGE_OF.get(row.doc_type),
                status=row.status,
            )
        return out

    def versions_by_ids(self, version_ids: list[int]) -> dict[int, VersionBrief]:
        """SYNC-MS-002#SpecService.versions_by_ids"""
        return {
            v.id: VersionBrief(
                v.id,
                v.document_id,
                v.version_no,
                v.created_at,
                v.message,
                commit_hash=v.commit_hash,
                author=self._author_of(v),
            )
            for v in self.repo.versions_by_ids(version_ids)
        }

    def _deleted_item_ids(self, doc_id: str | None) -> set[str]:
        if not doc_id:
            return set()
        doc = self.repo.document_by_doc_id(doc_id)
        if doc is None:
            return set()
        return {i.item_id for i in self.repo.items_of(doc.id, include_deleted=True) if i.is_deleted}


def _normalized(text: str) -> list[str]:
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def _apply_validate(row: DocumentRow, vr: ValidateResult) -> None:
    """규약 결과 → documents 오류·경고 컬럼 (MS-002 create 1단계 · save 7단계)."""
    v, w = vr.violations, vr.warnings
    row.has_convention_error = bool(v)
    row.convention_error_detail = "\n".join(f"{x.rule}: {x.message}" for x in v) or None
    row.incomplete_warnings = json.dumps([str(x) for x in w], ensure_ascii=False) if w else None


_CLASS = re.compile(r"class (\w+) \{(.*?)\}", re.S)


def _entity_mismatch(body: str) -> list[Warning]:
    """DOM 클래스 명세: 2장(엔티티)과 4장(설계) mermaid의 같은 클래스 속성이 다르면 경고."""
    chapters: dict[str, str] = {}
    cur = None
    for line in body.split("\n"):
        m = re.match(r"^## (\d+)\.", line)
        if m:
            cur = m.group(1)
        if cur:
            chapters[cur] = chapters.get(cur, "") + line + "\n"

    def attrs(text: str) -> dict[str, set[str]]:
        return {
            m.group(1): {a.strip() for a in m.group(2).split("\n") if a.strip().startswith("+")}
            for m in _CLASS.finditer(text)
        }

    a2, a4 = attrs(chapters.get("2", "")), attrs(chapters.get("4", ""))
    return [
        Warning("entity.mismatch", name)
        for name in sorted(a2)
        if name in a4 and a2[name] != a4[name]
    ]


def now_utc() -> datetime:
    return datetime.now(UTC)
