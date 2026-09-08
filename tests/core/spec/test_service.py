"""SYNC-MS-002 테스트 관점 — SpecService."""

import glob

from sqlalchemy.orm import Session

from syncdoc.core.spec.service import SpecService, parse_frontmatter
from syncdoc.core.types import DocType, Entry

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
