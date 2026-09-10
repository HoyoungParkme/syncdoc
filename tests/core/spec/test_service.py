"""SYNC-MS-002 테스트 관점 — SpecService."""

import glob

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.errors import ConventionViolation, ItemDeleted, NotFound
from syncdoc.core.markdown import parse_frontmatter
from syncdoc.core.project.models import Project, Repository
from syncdoc.core.spec.service import SpecService
from syncdoc.core.types import Author, AuthorKind, DocType, Entry
from tests.core.account.test_service import make_user


def make_project(session: Session, code: str = "EXMP") -> Project:
    p = Project(code=code, name="예시")
    session.add(p)
    session.flush()
    session.add(Repository(project_id=p.id, remote_url="https://x/r.git", workdir_path="/w"))
    session.flush()
    return p


def author(session: Session, login: str = "hoyoung", kind: AuthorKind = AuthorKind.agent) -> Author:
    u = make_user(session, login=login)
    return Author(
        kind=kind, user=u, instructed_by=u if kind == AuthorKind.agent else None, via=Entry.mcp
    )


SPECS = sorted(p for p in glob.glob("docs/specs/*/*.md") if "/_templates/" not in p)

PRD = """---
doc_id: EXMP-PRD-001
type: PRD
title: 예시 제품
status: draft
upstream: [EXMP-RFQ-001]
---

# 예시 제품 PRD

## 1. 목표

#### G1 첫 목표
한 줄로.

## 2. 비목표

| 비목표 | 이유 |
|---|---|
| 하지 않을 것 | 왜 |

## 3. 요구사항

### 3.1 기능

#### R1 첫 기능
설명. 근거: [[EXMP-RFQ-001#Q2]]

- [ ] 인수기준 하나
##### 인수기준
- [ ] 인수기준 둘

### 3.2 비기능

#### N1 성능
```markdown
#### R99 코드블록 안 헤딩은 항목이 아니다 [[BAD REF]]
```
- [ ] 1초 이내

## 4. 성공지표

| 지표 | 목표 |
|---|---|

## 5. 미결사항

- [ ] 아직 못 정한 것
"""


# ── item_blocks ──
def test_item_blocks_boundaries_and_code_block_skip(db_session: Session) -> None:
    svc = SpecService(db_session)
    blocks = svc.item_blocks(PRD, DocType.PRD)
    assert [b.item_id for b in blocks] == ["G1", "R1", "N1"]
    assert [b.display_name for b in blocks] == ["첫 목표", "첫 기능", "성능"]
    r1 = blocks[1]
    assert r1.level == 4 and r1.text.startswith("#### R1 첫 기능")
    assert "##### 인수기준" in r1.text and "인수기준 둘" in r1.text  # 더 낮은 헤딩은 블록 안
    assert "### 3.2" not in r1.text  # 같은 레벨 이상 헤딩에서 끝
    n1 = blocks[2]
    assert "R99" in n1.text and "## 4." not in n1.text  # 코드블록 안 헤딩은 항목도 경계도 아니다
    assert PRD.split("\n")[n1.end_line] == "## 4. 성공지표"
    assert PRD.split("\n")[r1.start_line - 1] == "#### R1 첫 기능"
    tail = PRD.split("## 4. 성공지표")[0]  # N1이 마지막 → 문서 끝까지
    last = svc.item_blocks(tail, DocType.PRD)[-1]
    assert last.item_id == "N1" and last.end_line == len(tail.split("\n"))


def test_item_blocks_matches_validate_py_on_all_specs(db_session: Session) -> None:
    """_tools/validate.py와 같은 결과 — 27개 명세의 항목 ID 목록."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("v", "tools/validate.py")
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    svc = SpecService(db_session)
    for path in SPECS:
        body = open(path, encoding="utf-8").read()
        fm, _ = parse_frontmatter(body)
        _, _, info = v.validate(path)
        got = [b.item_id for b in svc.item_blocks(body, fm["type"])]
        assert got == info["items"], path


# ── validate ──
def test_validate_all_27_specs_pass(db_session: Session) -> None:
    svc = SpecService(db_session)
    for path in SPECS:
        body = open(path, encoding="utf-8").read()
        fm, _ = parse_frontmatter(body)
        r = svc.validate(body, fm["type"], Entry.github)
        assert (r.violations, r.warnings) == ([], []), (path, r)


def test_validate_example_passes_and_variants(db_session: Session) -> None:
    svc = SpecService(db_session)
    r = svc.validate(PRD, DocType.PRD, Entry.mcp)
    assert r.violations == [] and r.warnings == []
    # frontmatter 없음 → 위반 하나만
    r = svc.validate(PRD.split("---\n", 2)[2], DocType.PRD, Entry.mcp)
    assert [v.rule for v in r.violations] == ["frontmatter.missing"]
    # 패딩·마침표
    r = svc.validate(
        PRD.replace("#### R1 첫", "#### R01 첫").replace("#### N1 ", "#### N1. "),
        DocType.PRD,
        Entry.mcp,
    )
    assert sorted(v.rule for v in r.violations) == ["item.padding", "item.punct"]
    # MCP에서 status 바꿈 → 위반, GitHub에서는 통과
    body = PRD.replace("status: draft", "status: approved")
    assert [v.rule for v in svc.validate(body, DocType.PRD, Entry.mcp, "draft").violations] == [
        "frontmatter.status_change"
    ]
    assert svc.validate(body, DocType.PRD, Entry.github, "draft").violations == []
    # 필수 절 하나 빼면 경고 하나
    r = svc.validate(PRD.replace("## 4. 성공지표", "## 4. 지표"), DocType.PRD, Entry.mcp)
    assert r.violations == [] and [str(w) for w in r.warnings] == ["section.missing: 성공지표"]
    # 중복·타입 불일치·참조 형식
    r = svc.validate(PRD.replace("#### N1 성능", "#### R1 성능"), DocType.PRD, Entry.mcp)
    assert [v.rule for v in r.violations] == ["item.duplicate"]
    r = svc.validate(PRD.replace("[[EXMP-RFQ-001#Q2]]", "[[bad-ref]]"), DocType.PRD, Entry.mcp)
    assert [v.rule for v in r.violations] == ["ref.format"]
    r = svc.validate(PRD, DocType.RFQ, Entry.mcp)
    assert "frontmatter.doc_id" in [v.rule for v in r.violations]


def test_validate_entity_mismatch_warning(db_session: Session) -> None:
    body = """---
doc_id: X-DOM-002
type: DOM
title: 클래스 명세 — X
status: draft
---
## 1. 폴더 구조
## 2. 엔티티
#### Foo 푸
```mermaid
classDiagram
    class Foo {
        +int id
        +str name
    }
```
## 3. 의존 관계
## 4. 설계 클래스
#### FooService
```mermaid
classDiagram
    class Foo {
        +int id
    }
```
## 5. 미결사항
"""
    r = SpecService(db_session).validate(body, DocType.DOM, Entry.github)
    assert r.violations == [] and [str(w) for w in r.warnings] == ["entity.mismatch: Foo"]


# ── apply_frontmatter ──
def test_apply_frontmatter_creates_fills_and_rejects(db_session: Session) -> None:
    svc = SpecService(db_session)
    body = "# 제목 줄\n\n본문\n"
    out = svc.apply_frontmatter(body, "EXMP-PRD-001", DocType.PRD, "draft")
    fm, n = parse_frontmatter(out)
    assert fm == {"doc_id": "EXMP-PRD-001", "type": "PRD", "title": "제목 줄", "status": "draft"}
    assert out.endswith(body)
    # doc_id 비움 → 채워짐, upstream 보존, 순서 유지
    body = (
        "---\ndoc_id: \ntype: RFQ\ntitle: T\nstatus: approved\nupstream: [EXMP-RFQ-001]\n---\n# T\n"
    )
    out = svc.apply_frontmatter(body, "EXMP-PRD-002", DocType.PRD, "draft")
    assert out.split("\n")[1:7] == [
        "doc_id: EXMP-PRD-002",
        "type: PRD",
        "title: T",
        "status: draft",
        "upstream: [EXMP-RFQ-001]",
        "---",
    ]
    # doc_id 다른 값 → 위반
    with pytest.raises(ConventionViolation) as ei:
        svc.apply_frontmatter(
            body.replace("doc_id: ", "doc_id: EXMP-PRD-009"), "EXMP-PRD-002", DocType.PRD, "draft"
        )
    assert ei.value.extra["violations"][0]["rule"] == "frontmatter.doc_id"
    # 헤딩 없으면 title = doc_id
    assert "title: EXMP-PRD-003" in svc.apply_frontmatter(
        "본문", "EXMP-PRD-003", DocType.PRD, "draft"
    )


# ── issue_doc_id ──
def test_issue_doc_id_sequence_no_reuse(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    assert svc.issue_doc_id(p.id, "EXMP", DocType.PRD) == "EXMP-PRD-001"
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    svc.create(
        p.id,
        "EXMP-PRD-002",
        DocType.PRD,
        PRD.replace("EXMP-PRD-001", "EXMP-PRD-002"),
        "h2",
        a,
        "spec: 테스트",
    )
    db_session.execute(
        text(
            "DELETE FROM versions; DELETE FROM items; DELETE FROM documents WHERE doc_id='EXMP-PRD-001'"
        )
    )
    assert svc.issue_doc_id(p.id, "EXMP", DocType.PRD) == "EXMP-PRD-003"
    assert svc.issue_doc_id(p.id, "EXMP", DocType.RFQ) == "EXMP-RFQ-001"


# ── create ──
def test_create_inserts_document_items_version(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    v = svc.create(
        p.id, "EXMP-PRD-001", DocType.PRD, PRD, "abc123", a, "spec(EXMP-PRD-001): 초안\n\n이유"
    )
    assert v.version_no == 1 and v.author_kind == "agent" and v.instructed_by_user_id == a.user.id
    assert v.message == "spec(EXMP-PRD-001): 초안\n\n이유"  # versions.message 사본 (DOM-003)
    d = svc.get_document("EXMP-PRD-001")
    assert d.current_version_no == 1 and d.status == "draft" and d.stage == 2
    assert [i.item_id for i in d.items] == ["G1", "R1", "N1"]
    assert d.last_author is not None and d.last_author.user_id == a.user.id
    assert (d.last_author.kind, d.last_author.instructed_by_id, d.last_author.via) == (
        "agent",
        a.user.id,
        "mcp",
    )
    assert d.body == PRD and d.has_convention_error is False


# ── get_document ──
def test_get_document_not_found_convention_error_and_deleted_items(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    with pytest.raises(NotFound) as ei:
        svc.get_document("EXMP-PRD-009")
    assert ei.value.extra == {"resource": "document", "id": "EXMP-PRD-009"}
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    db_session.execute(
        text(
            "UPDATE documents SET has_convention_error=true, convention_error_detail='author.unknown: x', "
            "incomplete_warnings='[\"section.missing: 목표\"]'; "
            "UPDATE items SET is_deleted=true WHERE item_id='N1'"
        )
    )
    d = svc.get_document("EXMP-PRD-001")
    assert d.has_convention_error and d.convention_error_detail == "author.unknown: x"
    assert d.incomplete_warnings == ["section.missing: 목표"]
    assert [i.item_id for i in d.items] == ["G1", "R1"]
    assert d.items[0].flags == [] and d.prev_doc_id is None


# ── get_item ──
def test_get_item_block_not_found_deleted(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a, "spec: 테스트")
    v = svc.get_item("EXMP-PRD-001", "R1")
    assert (
        v.body.startswith("#### R1 첫 기능")
        and "##### 인수기준" in v.body
        and "### 3.2" not in v.body
    )
    assert (v.doc_status, v.doc_version_no, v.display_name, v.flags) == ("draft", 1, "첫 기능", [])
    last = svc.get_item("EXMP-PRD-001", "N1")
    assert last.body.rstrip().endswith("- [ ] 1초 이내")  # 코드블록 포함, 다음 절 전까지
    with pytest.raises(NotFound) as ei:
        svc.get_item("EXMP-PRD-001", "R9")
    assert ei.value.extra["available_items"] == ["G1", "R1", "N1"]
    db_session.execute(
        text("UPDATE items SET is_deleted=true, deleted_at=now() WHERE item_id='N1'")
    )
    with pytest.raises(ItemDeleted) as ei2:
        svc.get_item("EXMP-PRD-001", "N1")
    assert ei2.value.extra["deleted_at"]
    with pytest.raises(NotFound):
        svc.get_item("EXMP-PRD-404", "R1")


# ── detect_deleted_items ──
def test_detect_deleted_items(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", author(db_session), "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    n1_pk = next(i.pk for i in d.items if i.item_id == "N1")
    without_n1 = PRD.split("### 3.2 비기능")[0] + "## 4. 성공지표\n\n## 5. 미결사항\n"
    assert svc.detect_deleted_items(d, without_n1) == [n1_pk]
    assert svc.detect_deleted_items(d, PRD.replace("#### N1 성능", "#### N1 속도")) == []
    reordered = PRD.replace("#### G1 첫 목표\n한 줄로.\n", "").replace(
        "## 5. 미결사항", "#### G1 첫 목표\n한 줄로.\n\n## 5. 미결사항"
    )
    assert svc.detect_deleted_items(d, reordered) == []


# ── save ──
def _seed(db_session: Session, status: str = "draft"):
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    body = PRD.replace("status: draft", f"status: {status}")
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, body, "h1", a, "spec: 테스트")
    return svc, a, svc.get_document("EXMP-PRD-001")


def test_save_bumps_version_and_upserts_items(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    body = PRD.replace("#### N1 성능", "#### N1 속도") + "\n#### N2 새 항목\n내용\n"
    v = svc.save(d, body, "h2", a, "spec: 테스트", [])
    assert v.version_no == 2 and v.body == body
    d2 = svc.get_document("EXMP-PRD-001")
    assert d2.current_version_no == 2 and d2.body == body and d2.status == "draft"
    assert [(i.item_id, i.display_name) for i in d2.items][2:] == [
        ("N1", "속도"),
        ("N2", "새 항목"),
    ]
    assert d2.incomplete_warnings == []


def test_save_approved_document_demotes_to_review_with_status_change(db_session: Session) -> None:
    svc, a, d = _seed(db_session, "approved")
    svc.save(d, d.body.replace("한 줄로.", "두 줄로."), "h2", a, "spec: 테스트", [])
    assert svc.get_document("EXMP-PRD-001").status == "review"
    rows = db_session.execute(
        text("SELECT from_status, to_status, reason, commit_hash FROM status_changes")
    ).all()
    assert rows == [("approved", "review", "본문 수정으로 자동 강등", None)]
    # github 경로에서 frontmatter status가 진실
    d2 = svc.get_document("EXMP-PRD-001")
    gh = Author(kind=AuthorKind.human, user=a.user, instructed_by=None, via=Entry.github)
    svc.save(
        d2, d2.body.replace("status: approved", "status: approved\n"), "h3", gh, "spec: 테스트", []
    )
    assert svc.get_document("EXMP-PRD-001").status == "approved"


def test_save_deleted_pks_and_warnings(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    n1 = next(i.pk for i in d.items if i.item_id == "N1")
    from syncdoc.core.types import ValidateResult, Violation
    from syncdoc.core.types import Warning as W

    vr = ValidateResult(
        [Violation(3, "author.unknown", "ghost")], [W("section.missing", "성공지표")]
    )
    svc.save(d, PRD, "h2", a, "spec: 테스트", [n1], validate_result=vr)
    row = db_session.execute(
        text("SELECT is_deleted, deleted_at FROM items WHERE item_id='N1'")
    ).one()
    assert row[0] is True and row[1] is not None
    d2 = svc.get_document("EXMP-PRD-001")
    assert d2.has_convention_error and d2.convention_error_detail == "author.unknown: ghost"
    assert d2.incomplete_warnings == ["section.missing: 성공지표"]
    assert [i.item_id for i in d2.items] == ["G1", "R1"]
    svc.save(d2, PRD, "h3", a, "spec: 테스트", [])  # validate_result 없음 → 오류·경고 컬럼 그대로
    assert svc.get_document("EXMP-PRD-001").has_convention_error is True
    svc.save(
        d2, PRD, "h4", a, "spec: 테스트", [], validate_result=ValidateResult([], [])
    )  # 통과 → 해제
    d4 = svc.get_document("EXMP-PRD-001")
    assert (
        d4.has_convention_error is False
        and d4.convention_error_detail is None
        and d4.incomplete_warnings == []
    )
    assert db_session.execute(text("SELECT via FROM versions WHERE version_no=4")).scalar() == "mcp"


# ── list_by_project ──
def test_list_by_project_filters_and_order(db_session: Session) -> None:
    svc = SpecService(db_session)
    p, other = make_project(db_session), make_project(db_session, "OTHR")
    a = author(db_session)

    def mk(pid: int, did: str, typ: str, status: str = "draft", title: str = "x") -> None:
        body = f"---\ndoc_id: {did}\ntype: {typ}\ntitle: {title}\nstatus: {status}\n---\n# {did}\n"
        svc.create(pid, did, typ, body, "h", a, "spec: 테스트")

    mk(p.id, "EXMP-DOM-003", "DOM", title="ERD·DD")
    mk(p.id, "EXMP-DOM-001", "DOM", "approved", title="도메인")
    mk(p.id, "EXMP-DOM-002", "DOM", title="클래스")
    mk(p.id, "EXMP-PRD-001", "PRD", "approved")
    mk(p.id, "EXMP-STD-001", "STD")
    mk(other.id, "OTHR-PRD-001", "PRD")

    def ids(xs):
        return [d.doc_id for d in xs]

    assert ids(svc.list_by_project(p.id)) == [
        "EXMP-PRD-001",
        "EXMP-DOM-001",
        "EXMP-DOM-002",
        "EXMP-DOM-003",
        "EXMP-STD-001",
    ]
    assert ids(svc.list_by_project(p.id, stage=6)) == [
        "EXMP-DOM-001",
        "EXMP-DOM-002",
        "EXMP-DOM-003",
    ]
    assert ids(svc.list_by_project(p.id, status="approved")) == ["EXMP-PRD-001", "EXMP-DOM-001"]
    assert ids(svc.list_by_project(p.id, has_convention_error=True)) == []
    got = svc.list_by_project(p.id)
    assert got[-1].stage is None and got[0].last_author.user_id == a.user.id and got[0].counts == {}


# ── last_author · neighbors · resolve_item ──
def test_last_author_neighbors_resolve_item(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)

    def mk(did: str, typ: str, title: str = "x") -> None:
        svc.create(
            p.id,
            did,
            typ,
            f"---\ndoc_id: {did}\ntype: {typ}\ntitle: {title}\nstatus: draft\n---\n# {did}\n#### Q1 첫\n",
            "h",
            a,
            "spec: 테스트",
        )

    for did, typ, title in [
        ("EXMP-INFRA-001", "INFRA", "x"),
        ("EXMP-DOM-003", "DOM", "ERD"),
        ("EXMP-DOM-001", "DOM", "도메인"),
        ("EXMP-DOM-002", "DOM", "클래스"),
        ("EXMP-UI-002", "UI", "와이어프레임"),
        ("EXMP-UI-001", "UI", "화면 설계"),
        ("EXMP-STD-001", "STD", "s"),
    ]:
        mk(did, typ, title)
    assert svc.neighbors("EXMP-DOM-002") == (
        "EXMP-INFRA-001",
        "EXMP-UI-001",
    )  # 앞뒤 단계, doc_id 순 첫 것
    assert svc.neighbors("EXMP-INFRA-001") == (None, "EXMP-DOM-001")
    assert svc.neighbors("EXMP-STD-001") == (None, None)
    with pytest.raises(NotFound):
        svc.neighbors("EXMP-PRD-009")
    # last_author
    d = svc.get_document("EXMP-DOM-001")
    la = svc.last_author(d.id)
    assert (la.kind, la.user_id, la.instructed_by_id, la.via) == (
        "agent",
        a.user.id,
        a.user.id,
        "mcp",
    )
    assert svc.last_author(999_999) is None
    # resolve_item
    rfq_item = svc.create(
        p.id,
        "EXMP-RFQ-001",
        DocType.RFQ,
        "---\ndoc_id: EXMP-RFQ-001\ntype: RFQ\ntitle: r\nstatus: draft\n---\n#### Q1 a\n#### Q2 b\n",
        "h",
        a,
        "spec: 테스트",
    )
    pk = svc.resolve_item("EXMP-RFQ-001", "Q2")
    assert pk == next(i.pk for i in svc.get_document("EXMP-RFQ-001").items if i.item_id == "Q2")
    with pytest.raises(NotFound):
        svc.resolve_item("EXMP-RFQ-001", "Q9")
    with pytest.raises(NotFound):
        svc.resolve_item("EXMP-RFQ-404", "Q1")
    db_session.execute(
        text("UPDATE items SET is_deleted=true, deleted_at=now() WHERE item_id='Q2'")
    )
    with pytest.raises(ItemDeleted):
        svc.resolve_item("EXMP-RFQ-001", "Q2")
    assert rfq_item.version_no == 1


# ── apply_status ──
def test_apply_status_records_change_without_version(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    new_body = PRD.replace("status: draft", "status: review")
    svc.apply_status(d, new_body, "c0ffee", a.user, "검토 시작")
    d2 = svc.get_document("EXMP-PRD-001")
    assert d2.status == "review" and d2.body == new_body and d2.current_version_no == 1
    assert db_session.execute(text("SELECT count(*) FROM versions")).scalar() == 1
    row = db_session.execute(
        text("SELECT from_status, to_status, reason, commit_hash FROM status_changes")
    ).one()
    assert row == ("draft", "review", "검토 시작", "c0ffee")
    svc.apply_status(
        d2,
        new_body.replace("status: review", "status: approved"),
        None,
        a.user,
        None,
        to="approved",
    )
    assert svc.get_document("EXMP-PRD-001").status == "approved"


# ── describe_items ──
def test_describe_items_items_and_documents(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    pks = {i.item_id: i.pk for i in d.items}
    db_session.execute(text("UPDATE items SET is_deleted=true WHERE item_id='N1'"))
    got = svc.describe_items([pks["G1"], pks["N1"], 999_999])
    assert (got[pks["G1"]].doc_id, got[pks["G1"]].item_id, got[pks["G1"]].display_name) == (
        "EXMP-PRD-001",
        "G1",
        "첫 목표",
    )
    assert got[pks["N1"]].is_deleted is True and 999_999 not in got
    assert svc.describe_items([]) == {}
    # 문서 pk는 받지 않는다 — items.id와 documents.id가 겹친다. 문서는 describe_documents


# ── describe_documents · versions_by_ids ──
def test_describe_documents_and_versions_by_ids(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    got = svc.describe_documents([d.id, 999_999])
    assert list(got) == [d.id]
    assert (got[d.id].doc_id, got[d.id].title, got[d.id].stage, got[d.id].status) == (
        "EXMP-PRD-001",
        "예시 제품",
        2,
        "draft",
    )
    assert svc.describe_documents([]) == {}
    v2 = svc.save(d, d.body + "\n", "h2", a, "spec(EXMP-PRD-001): 한 줄\n\n이유", [])
    vb = svc.versions_by_ids([d.current_version_id, v2.id, 999_999])
    assert sorted((b.version_no, b.message) for b in vb.values()) == [
        (1, "spec: 테스트"),
        (2, "spec(EXMP-PRD-001): 한 줄\n\n이유"),
    ]
    assert vb[v2.id].document_id == d.id and svc.versions_by_ids([]) == {}


# ── recent_changes ──
def test_recent_changes_merges_versions_and_status_commits_desc(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    v2 = svc.save(d, d.body + "\n", "h2", a, "spec(EXMP-PRD-001): 한 줄 추가\n\n이유", [])
    d2 = svc.get_document("EXMP-PRD-001")
    svc.apply_status(d2, d2.body.replace("status: draft", "status: review"), "c1", a.user, "검토")
    svc.apply_status(d2, d2.body, None, a.user, "commit 없는 자동 강등은 안 나온다", to="draft")
    pid = _project_id(db_session, "EXMP")
    got = svc.recent_changes(pid, 10)
    assert [(r.doc_id, r.version_no, r.commit_hash) for r in got] == [
        ("EXMP-PRD-001", None, "c1"),
        ("EXMP-PRD-001", 2, "h2"),
        ("EXMP-PRD-001", 1, "h1"),
    ]
    assert got[0].message == "status(EXMP-PRD-001): draft → review"
    assert (got[0].author.kind, got[0].author.user_id, got[0].author.via) == (
        "human",
        a.user.id,
        "web",
    )
    assert (
        got[1].message.startswith("spec(EXMP-PRD-001): 한 줄 추가")
        and got[1].author.kind == "agent"
    )
    assert [r.version_no for r in svc.recent_changes(pid, 2)] == [None, 2]
    assert v2.version_no == 2


def _project_id(session: Session, code: str) -> int:
    return session.execute(text("SELECT id FROM projects WHERE code=:c"), {"c": code}).scalar_one()


# ── diff · resolve_items ──
def test_diff_hunks_per_item_whitespace_ignored_new_item_reverse(db_session: Session) -> None:
    svc, a, d = _seed(db_session)
    body2 = PRD.replace("한 줄로.", "두 줄로.")  # G1만 고침
    svc.save(d, body2, "h2", a, "spec: v2", [])
    df = svc.diff("EXMP-PRD-001", 1, 2)
    assert (df.from_version, df.to_version, [h.item_id for h in df.hunks]) == (1, 2, ["G1"])
    ops = [(ln.op, ln.text) for ln in df.hunks[0].lines if ln.op != "ctx"]
    assert ops == [("del", "한 줄로."), ("add", "두 줄로.")]
    assert all(h.downstream_count == 0 for h in df.hunks)  # queries가 채운다
    # 역방향 → op 뒤집힘
    rev = svc.diff("EXMP-PRD-001", 2, 1)
    assert [(ln.op, ln.text) for ln in rev.hunks[0].lines if ln.op != "ctx"] == [
        ("del", "두 줄로."),
        ("add", "한 줄로."),
    ]
    # 공백만 바꿈 → hunk 없음 · 항목 추가 → 전부 add · 항목 밖 텍스트는 None 키
    d2 = svc.get_document("EXMP-PRD-001")
    body3 = body2.replace("두 줄로.", "두 줄로.  \n") + "\n#### N2 새 항목\n내용\n"
    svc.save(d2, body3.replace("# 예시 제품 PRD", "# 예시 제품 PRD v3"), "h3", a, "spec: v3", [])
    df3 = svc.diff("EXMP-PRD-001", 2, 3)
    assert [h.item_id for h in df3.hunks] == ["N2", None]
    assert {ln.op for ln in df3.hunks[0].lines} == {"add"}
    assert svc.diff("EXMP-PRD-001", 3, 3).hunks == []
    with pytest.raises(NotFound):
        svc.diff("EXMP-PRD-001", 1, 9)
    with pytest.raises(NotFound):
        svc.diff("EXMP-PRD-404", 1, 2)
    # resolve_items — IN 하나, 없는 것·삭제된 것 건너뜀
    pks = {i.item_id: i.pk for i in svc.get_document("EXMP-PRD-001").items}
    assert svc.resolve_items("EXMP-PRD-001", ["R1", "N2", "R9"]) == [pks["R1"], pks["N2"]]
    db_session.execute(text("UPDATE items SET is_deleted=true WHERE item_id='N2'"))
    assert (
        svc.resolve_items("EXMP-PRD-001", ["N2"]) == [] and svc.resolve_items("NOPE", ["R1"]) == []
    )


# ── versions_instructed_by · convention_error_docs_by · documents_authored_by ──
def test_my_versions_error_docs_and_authored_documents(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a, b = author(db_session, "aa"), author(db_session, "bb")
    v1 = svc.create(p.id, "EXMP-RFQ-001", DocType.RFQ, RFQ_MIN, "h0", a, "spec: 테스트")
    v2 = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", b, "spec: 테스트")
    d = svc.get_document("EXMP-PRD-001")
    v3 = svc.save(d, d.body + "\n", "h2", a, "spec: v2", [])  # PRD 최근 작성자 → a
    assert svc.versions_instructed_by([v1.id, v2.id, v3.id], a.user.id) == [v1.id, v3.id]
    assert svc.versions_instructed_by([], a.user.id) == []
    assert sorted(svc.documents_authored_by(a.user.id)) == sorted([v1.document_id, d.id])
    assert svc.documents_authored_by(b.user.id) == []  # b의 PRD는 a가 덮어썼다
    db_session.execute(
        text("UPDATE documents SET has_convention_error=true WHERE doc_id='EXMP-PRD-001'")
    )
    assert [x.doc_id for x in svc.convention_error_docs_by(a.user.id)] == ["EXMP-PRD-001"]
    assert svc.convention_error_docs_by(b.user.id) == []


RFQ_MIN = """---
doc_id: EXMP-RFQ-001
type: RFQ
title: 요청
status: draft
---

## 1. 요구

#### Q1 첫 요구
내용
"""
