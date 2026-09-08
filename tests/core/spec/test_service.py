"""SYNC-MS-002 테스트 관점 — SpecService."""

import glob

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from syncdoc.core.errors import ConventionViolation, ItemDeleted, NotFound
from syncdoc.core.project.models import Project, Repository
from syncdoc.core.spec.service import SpecService, parse_frontmatter
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
    assert svc.issue_doc_id(p.id, DocType.PRD) == "EXMP-PRD-001"
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
    svc.create(
        p.id, "EXMP-PRD-002", DocType.PRD, PRD.replace("EXMP-PRD-001", "EXMP-PRD-002"), "h2", a
    )
    db_session.execute(
        text(
            "DELETE FROM versions; DELETE FROM items; DELETE FROM documents WHERE doc_id='EXMP-PRD-001'"
        )
    )
    assert svc.issue_doc_id(p.id, DocType.PRD) == "EXMP-PRD-003"
    assert svc.issue_doc_id(p.id, DocType.RFQ) == "EXMP-RFQ-001"


# ── create ──
def test_create_inserts_document_items_version(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    v = svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "abc123", a)
    assert v.version_no == 1 and v.author_kind == "agent" and v.instructed_by_user_id == a.user.id
    d = svc.get_document("EXMP-PRD-001")
    assert d.current_version_no == 1 and d.status == "draft" and d.stage == 2
    assert [i.item_id for i in d.items] == ["G1", "R1", "N1"]
    assert d.last_author is not None and d.last_author.user.id == a.user.id
    assert d.body == PRD and d.has_convention_error is False


# ── get_document ──
def test_get_document_not_found_convention_error_and_deleted_items(db_session: Session) -> None:
    svc = SpecService(db_session)
    p = make_project(db_session)
    a = author(db_session)
    with pytest.raises(NotFound) as ei:
        svc.get_document("EXMP-PRD-009")
    assert ei.value.extra == {"resource": "document", "id": "EXMP-PRD-009"}
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
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
    svc.create(p.id, "EXMP-PRD-001", DocType.PRD, PRD, "h1", a)
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
