"""SYNC-MS-002 — SpecService. documents·items·versions·status_changes만.

다른 묶음 것은 인자로 받는다. 항목 판정은 item_blocks 한 곳(SYNC-STD-001 1.3).
"""

import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from syncdoc.core.account.models import User
from syncdoc.core.errors import ConventionViolation, ItemDeleted, NotFound
from syncdoc.core.project.models import Project
from syncdoc.core.spec.models import Document as DocumentRow
from syncdoc.core.spec.models import Item, StatusChange, Version
from syncdoc.core.spec.repository import SpecRepository
from syncdoc.core.types import (
    STAGE_OF,
    Author,
    AuthorKind,
    DocItem,
    DocStatus,
    DocType,
    Document,
    DocumentSummary,
    Entry,
    ItemBlock,
    ItemView,
    ValidateResult,
    Violation,
    Warning,
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
    "CODE": ([r"[A-C]\d*"], ["슬라이스", "통합 테스트", "커밋", "미결사항"]),
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
DOC_ID = re.compile(r"^[A-Z]{1,4}-[A-Z]+-\d{3}$")
REF = re.compile(r"\[\[([^\]]+)\]\]")
HEADING = re.compile(r"^(#{1,6}) (\S+)(?: (.*))?$")
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def parse_frontmatter(body: str) -> tuple[dict[str, str], int]:
    """frontmatter → (필드 dict, 차지하는 줄 수). 없으면 ({}, 0)."""
    m = FRONTMATTER.match(body)
    if not m:
        return {}, 0
    fm: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm, m.group(0).count("\n")


def patterns_for(doc_type: str, title: str | None) -> tuple[re.Pattern[str] | None, list[str]]:
    pats, secs = TYPES.get(doc_type, ([], []))
    for (t, key), (p, s) in SUBTYPES.items():
        if t == doc_type and title and key in title:
            pats, secs = p, s
    return (re.compile("^(?:" + "|".join(pats) + ")$") if pats else None), secs


def masked_lines(body: str) -> list[str]:
    """frontmatter·코드블록·인라인 코드를 같은 길이 공백으로. 줄 수 유지 (STD-001 1.3·1.5)."""
    _, fm_lines = parse_frontmatter(body)
    out: list[str] = []
    in_block = False
    for i, line in enumerate(body.split("\n")):
        if i < fm_lines:
            out.append("")
            continue
        if line.startswith("```"):
            in_block = not in_block
            out.append("")
            continue
        if in_block:
            out.append("")
        else:
            out.append(re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line))
    return out


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
        lines = body.split("\n")
        heads = []  # (line_idx, level, token, rest)
        for i, line in enumerate(masked_lines(body)):
            h = HEADING.match(line)
            if h:
                heads.append((i, len(h.group(1)), h.group(2), h.group(3) or ""))
        blocks: list[ItemBlock] = []
        for n, (i, level, tok, rest) in enumerate(heads):
            if not item_re.match(tok):
                continue
            end = len(lines) - 1
            for j, lvl, _, _ in heads[n + 1 :]:
                if lvl <= level:
                    end = j - 1
                    break
            blocks.append(
                ItemBlock(
                    item_id=tok,
                    display_name=rest.strip(),
                    level=level,
                    start_line=i + 1,
                    end_line=end + 1,
                    text="\n".join(lines[i : end + 1]),
                )
            )
        return blocks

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

    def issue_doc_id(self, project_id: int, doc_type: DocType) -> str:
        """SYNC-MS-002#SpecService.issue_doc_id"""
        code = self.session.get(Project, project_id).code
        return f"{code}-{doc_type}-{self.repo.max_doc_number(project_id, doc_type) + 1:03d}"

    def create(
        self,
        project_id: int,
        doc_id: str,
        doc_type: DocType,
        body: str,
        commit_hash: str,
        author: Author,
    ) -> Version:
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
        self.repo.add(row)
        for b in self.item_blocks(body, doc_type, fm.get("title")):
            self.session.add(
                Item(document_id=row.id, item_id=b.item_id, display_name=b.display_name)
            )
        version = self._new_version(row.id, 1, commit_hash, body, author)
        self.repo.add(version)
        return version

    def _new_version(
        self, document_id: int, no: int, commit_hash: str, body: str, author: Author
    ) -> Version:
        return Version(
            document_id=document_id,
            version_no=no,
            commit_hash=commit_hash,
            body=body,
            author_kind=str(author.kind),
            author_user_id=author.user.id,
            instructed_by_user_id=author.instructed_by.id if author.instructed_by else None,
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
            convention_error_detail=row.convention_error_detail,
            items=items,
        )

    def _summary_fields(self, row: DocumentRow, latest: Version | None) -> dict:
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

    def _author_of(self, v: Version | None) -> Author | None:
        """버전 행 → Author. via는 DB에 없어 kind로 추정(agent→mcp, human→github)."""
        if v is None:
            return None
        user = self.session.get(User, v.author_user_id)
        instructed = (
            self.session.get(User, v.instructed_by_user_id) if v.instructed_by_user_id else None
        )
        kind = AuthorKind(v.author_kind)
        return Author(
            kind=kind,
            user=user,
            instructed_by=instructed,
            via=Entry.mcp if kind == AuthorKind.agent else Entry.github,
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
        deleted_item_pks: list[int],
        has_convention_error: bool = False,
        warnings: list | None = None,
        rebuild: bool = False,
    ) -> Version:
        """SYNC-MS-002#SpecService.save"""
        row = self.repo.document_by_id(document.id)
        assert row is not None
        new_no = row.current_version_no + 1
        version = self._new_version(row.id, new_no, commit_hash, body, author)
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
        row.has_convention_error = has_convention_error
        if not has_convention_error:
            row.convention_error_detail = None
        row.incomplete_warnings = (
            json.dumps([str(w) for w in warnings], ensure_ascii=False) if warnings else None
        )
        self.session.flush()
        return version

    def _deleted_item_ids(self, doc_id: str | None) -> set[str]:
        if not doc_id:
            return set()
        doc = self.repo.document_by_doc_id(doc_id)
        if doc is None:
            return set()
        return {i.item_id for i in self.repo.items_of(doc.id, include_deleted=True) if i.is_deleted}


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
