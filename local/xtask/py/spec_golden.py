"""cargo xtask spec-golden — 명세 엔진의 정답 파일을 파이썬 판으로 만든다 (SYNC-MS-014 0장 · SYNC-STD-004#DEV-7).

손으로 만든 꼴 모음을 **입력째 얼려** `crates/core/tests/golden/spec.json`에 담는다 —
실제 명세·템플릿이 바뀌어도 `--check`가 깨지지 않게(그것들은 spec-diff가 본다). 답은 spec_answers(파이썬 판)가 낸다. 손으로 고치지 않는다.
`uv run --project backend python local/xtask/py/spec_golden.py OUT`
"""

from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_answers  # noqa: E402

ENTRIES = [
    {"entry": "github", "current_status": None},
    {"entry": "mcp", "current_status": None},
    {"entry": "mcp", "current_status": "draft"},
    {"entry": "mcp", "current_status": "approved"},
    {"entry": "web_revert", "current_status": "approved"},
    {"entry": "web_status", "current_status": "draft"},
]


def fm(doc_id="SYNC-PRD-001", typ="PRD", title="예시 제품", status="draft", extra="") -> str:
    return f"---\ndoc_id: {doc_id}\ntype: {typ}\ntitle: {title}\nstatus: {status}\n{extra}---\n"


PRD = fm(extra="upstream: [SYNC-RFQ-001]\n") + """
# 예시 제품 PRD

## 1. 목표

#### G1 첫 목표
한 줄로.

## 2. 비목표

| 비목표 | 이유 |
|---|---|

## 3. 요구사항

#### R1 첫 기능
설명. 근거: [[SYNC-RFQ-001#Q2]]
##### 인수기준
- [ ] 하나

#### N1 성능
```markdown
#### R99 코드블록 안 헤딩 [[BAD REF]]
```

## 4. 성공지표

## 5. 미결사항
"""


def cases() -> list[dict]:
    out: list[dict] = []

    def body(name, b, doc_type="PRD", title=None, deleted=(), apply=True):
        checks = [{**e, "deleted": list(deleted)} for e in ENTRIES]
        app = []
        if apply:
            app = [
                {"doc_id": "SYNC-PRD-001", "doc_type": doc_type, "status": "draft"},
                {"doc_id": "SYNC-PRD-009", "doc_type": doc_type, "status": "approved"},
            ]
        out.append(
            {"kind": "body", "name": name, "body": b, "doc_type": doc_type, "title": title,
             "checks": checks, "apply": app}
        )

    # ── frontmatter ──
    body("prd", PRD, deleted=["R15"])
    body("prd.deleted_reuse", PRD, deleted=["R1", "G1"])
    body("fm.none", "# 제목만\n\n#### R1 하나\n")
    body("fm.none.no_h1", "본문만\n")
    body("fm.empty", "")
    body("fm.bom", "﻿" + PRD)
    body("fm.crlf", PRD.replace("\n", "\r\n"))
    body("fm.crlf_tail", PRD.replace("status: draft\n", "status: draft\r\n"))
    body("fm.bad_close", PRD.replace("upstream: [SYNC-RFQ-001]\n---\n", "upstream: [SYNC-RFQ-001]\n--- \n") + "\n---\n끝\n")
    body("fm.two_dashes", "---\n---\n# x\n")
    body("fm.blank_line", "---\n\n---\n# x\n")
    body("fm.dup_keys", fm(extra="title: 두 번째\ndoc_id: SYNC-PRD-002\n") + "# x\n")
    body("fm.no_colon", fm(extra="그냥 줄\n") + "# x\n")
    body("fm.missing_fields", "---\ntitle: t\n---\n# x\n")
    body("fm.quotes", '---\ndoc_id: "SYNC-PRD-001"\ntype: \'PRD\'\ntitle: "q"\nstatus: draft\n---\n# x\n')
    body("fm.type_bad", fm(typ="PRDX") + "# x\n")
    body("fm.type_missing", "---\ndoc_id: SYNC-PRD-001\ntitle: t\nstatus: draft\n---\n# x\n")
    body("fm.status_bad", fm(status="done") + "# x\n")
    body("fm.status_missing", "---\ndoc_id: SYNC-PRD-001\ntype: PRD\ntitle: t\n---\n# x\n")
    body("fm.doc_id_empty", fm(doc_id="") + "# x\n")
    body("fm.doc_id_bad", fm(doc_id="sync-prd-1") + "# x\n")
    body("fm.doc_id_repr_quote", fm(doc_id="it's") + "# x\n")
    body("fm.doc_id_repr_ctrl", fm(doc_id="A\x1cB C​") + "# x\n")
    body("fm.doc_id_type_mismatch", fm(doc_id="SYNC-RFQ-001") + "# x\n")
    body("fm.doc_id_fullwidth", fm(doc_id="SYNC-PRD-００１") + "# x\n")
    body("fm.upstream_bad", fm(extra="upstream: [SYNC-RFQ-001, bad, SYNC-X-1, 가나-다]\n") + "# x\n")
    body("fm.upstream_plain", fm(extra="upstream: SYNC-RFQ-001 SYNC-SCN-001\n") + "# x\n")
    body("fm.value_ws", fm(extra="upstream:\x1c[SYNC-RFQ-001]　\n") + "# x\n")
    body("fm.colon_value", fm(title="제목: 부제") + "# x\n")
    body("fm.dom_no_subtype", fm(doc_id="SYNC-DOM-001", typ="DOM", title="그냥") + "# x\n", doc_type="DOM")
    body("fm.ui_no_subtype", fm(doc_id="SYNC-UI-001", typ="UI", title="화면") + "# x\n", doc_type="UI")
    body("fm.api_no_subtype", fm(doc_id="SYNC-API-001", typ="API", title="입구") + "# x\n", doc_type="API")
    body("fm.api_empty_title", fm(doc_id="SYNC-API-001", typ="API", title="") + "# x\n", doc_type="API")

    # ── 헤딩·항목 ──
    heads = [
        "#### R1 하나", "#### R01 앞자리", "#### R10 열", "#### R100 백", "#### R1. 점", "#### R1: 콜론",
        "#### R1a 꼬리", "#### R１ 전각", "#### ０R1", "####\tR2 탭", "####  R3 두 칸", "####### R4 일곱",
        "#### R5", "#### R6 ", "#### R7 a `x` b", "#### `R8` 코드", "#### G1 목표", "#### N1 비기능",
        "#### Q1 다른 타입", "#### UC-A1 다른 타입", "#### AB-12 대시", "#### X1-2 이상", "### 3.1 절",
        "## 2 번호만", "## 절 번호 없음", "# 제목", "#### R2\x1c꼬리", "#### R2 nbsp", "#### R9 [[SYNC-RFQ-001#Q1]]",
        "##### R11 아래 레벨", "## 4. 다음 장", "#### R12 끝 항목",
    ]
    body("heads.prd", fm() + "\n" + "\n본문\n".join(heads) + "\n마지막 줄\n")
    body("heads.dup", fm() + "#### R1 하나\n#### R1 둘\n#### R2\n#### R2 셋\n")
    body("heads.crlf_no_title", fm() + "#### R1\r\n#### R2 제목\r\n")
    body("heads.nested", fm() + "## 1. 장\n### 1.1 절\n#### R1 a\n##### 소\n###### 더\n#### R2 b\n### 1.2 절\n#### R3 c\n# 끝\n")
    body("heads.code_blocks", fm() + "```\n#### R1 펜스 안\n```\n  ```\n#### R2 들여쓴 펜스는 펜스가 아니다\n  ```\n````\n#### R3 네 개\n````\n~~~\n#### R4 물결\n~~~\n```python\nx\n```lang\n#### R5 닫힘 뒤\n")
    body("heads.unclosed_fence", fm() + "#### R1 앞\n```\n#### R2 닫히지 않음\n끝\n")
    body("heads.inline_code", fm() + "#### R1 `a` 와 `가나다` 그리고 ``두 개`` `\n본문 `[[BAD]]` 와 `x`\n")
    body("heads.only_hashes", fm() + "####\n#### \n#\n")

    # ── 참조 ──
    refs = fm() + "\n".join([
        "#### R1 참조",
        "[[SYNC-RFQ-001]] [[SYNC-RFQ-001#Q1]] [[#R1]] [[#R 1]] [[bad]] [[SYNC-RFQ-001#Q 2]]",
        "[[SYNC-RFQ-001#]] [[#]] [[a]]] [[[b]] [[SYNC-RFQ-001#Q1#x]] [[ SYNC-RFQ-001]] [[SYNC-RFQ-001 ]]",
        "`[[BAD]]` ```[[BAD]]``` [[SYNC-RFQ-001#Q 1]] [[SYNC-RFQ-00１]]",
        "```", "[[IN CODE]]", "```",
    ]) + "\n"
    body("refs", refs)
    body("refs.no_doc_id", "---\ntype: PRD\ntitle: t\nstatus: draft\n---\n[[#R1]]\n")

    # ── 타입마다 ──
    def typed(name, typ, title, text, deleted=()):
        body(name, fm(doc_id=f"SYNC-{typ}-001", typ=typ, title=title) + text, doc_type=typ, deleted=deleted)

    typed("rfq", "RFQ", "요청", "## 1. 배경\n## 2. 요구\n#### Q1 하나\n#### Q01 둘\n## 3. 사용자와 환경\n## 4. 미정\n")
    typed("rfq.missing_sections", "RFQ", "요청", "## 1. 배경\n#### Q1 하나\n")
    typed("scn", "SCN", "시나리오", "## 1. 페르소나\n#### P1 사람\n## 2. 시나리오\n#### S1 흐름\n#### S01 패딩\n## 3. 대응표\n")
    typed("uc", "UC", "유스케이스", "## 1. 액터\n## 2. 사용자 목표 수준 유스케이스\n#### UC-A1 가\n#### UC-Z1 패턴 밖\n#### UC-H01 패딩\n## 3. 하위기능 수준 유스케이스\n## 4. 대응표\n")
    typed("infra", "INFRA", "인프라", "## 1. 제약\n#### C1 하나\n출처: RFQ\n#### C2 둘\n근거: [[SYNC-RFQ-001]]\n#### C3 셋\n```\n출처: 코드 안\n```\n#### C4 넷\n  출처: 들여씀\n## 2. 구성도\n## 3. 기술 스택\n## 4. 데이터가 사는 곳\n## 5. 인증과 접근\n## 6. 미결사항\n")
    typed("ui", "UI", "화면 설계", "#### UI-1 첫 화면\n#### UI-01 패딩\n## 9. 미결사항\n")
    typed("ui.wire", "UI", "와이어프레임", "#### UI-2 둘\n")
    typed("seq", "SEQ", "시퀀스", "## 1. 생명선\n#### SEQ-1 하나\n#### SEQ-C2 둘\n#### SEQ-01 패딩\n## 2. 대응표\n## 3. 되먹일 것\n")
    typed("ms", "MS", "MINISPEC", "## 1. 함수 목록\n## 2. 함수\n#### SpecService.save 저장\n#### markdown.parse_frontmatter 파싱\n#### Bad.Name 대문자\n### 절 번호 없음\n### 2.1 번호 있음\n#### SpecService.save 중복\n## 3. 미결사항\n")
    typed("code", "CODE", "구현 계획", "## 1. 슬라이스\n#### A 기반\n#### B12 묶음\n#### AB 두 글자\n#### L05 패딩\n## 2. 통합 테스트\n## 3. 커밋\n## 4. 미결사항\n")
    typed("code.no_items", "CODE", "구현 계획", "## 1. 슬라이스\n")
    typed("std", "STD", "규약", "#### DEV-1 하나\n#### V-PRD 뷰\n#### DEV-01 패딩\n## 9. 미결사항\n")
    typed("api.rest", "API", "REST API", "## 1. 규칙\n## 2. 에러\n## 3. 엔드포인트\n#### GET/api/me 나\n#### POST/api/docs/{docId}/status 상태\n#### get/api/x 소문자\n### 3.1 묶음\n### 묶음 번호 없음\n## 4. 미결사항\n")
    typed("api.mcp", "API", "MCP 도구", "## 1. 규칙\n## 2. 도구\n#### create_document 만들기\n#### get_item 항목\n#### Bad 대문자\n## 3. 에이전트 순서\n## 4. 미결사항\n")
    typed("dom.domain", "DOM", "도메인 모델", "## 1. 개념 식별\n## 2. 개념 모델\n## 3. 개념별 정리\n#### Document 문서\n#### document 소문자\n## 4. 경계\n## 5. 미결사항\n")
    typed("dom.erd", "DOM", "ERD·DD", "## 1. ERD\n## 2. DD\n#### documents 표\n#### Documents 대문자\n## 3. 인덱스\n## 4. 미결사항\n")
    cls = """## 1. 폴더 구조

| 경로 | 층 | 명세 |
|---|---|---|
| `a` | b | c |

## 2. 엔티티

#### Document 문서

```mermaid
classDiagram
    class Document {
        +int id
        +str doc_id
    }
    class Item {
        +int id
    }
    class Only2 {
        +int a
    }
```

## 3. 의존 관계

## 4. 설계 클래스

```mermaid
classDiagram
    class Document {
        +int id
        +str title
    }
    class Item {
        +int id
    }
    class subclass Foo {
        +x
    }
```

## 5. 미결사항
"""
    typed("dom.class", "DOM", "클래스 명세", cls)
    typed("dom.class.no_layer", "DOM", "클래스 명세", cls.replace("| 경로 | 층 | 명세 |", "| 경로 | 층 |"))
    typed("dom.class.layer_in_code", "DOM", "클래스 명세", cls.replace("| 경로 | 층 | 명세 |\n|---|---|---|\n| `a` | b | c |", "```\n| 경로 | 층 | 명세 |\n```"))
    typed("dom.class.layer_spaces", "DOM", "클래스 명세", cls.replace("| 경로 | 층 | 명세 |", "  |경로|  층 |명세| ").replace("## 1. 폴더 구조", "## 1.1  폴더 구조와 층"))
    typed("dom.class.unicode_chapter", "DOM", "클래스 명세", cls.replace("## 2. 엔티티", "## ２. 엔티티"))
    typed("dom.title_order", "DOM", "클래스와 도메인 ERD", "#### Document x\n#### documents y\n")

    return out


def diffs() -> list[dict]:
    out: list[dict] = []

    def d(name, a, b, doc_type="PRD", context=3, nos=(1, 2)):
        out.append({"kind": "diff", "name": name, "from": a, "to": b, "doc_type": doc_type,
                    "from_no": nos[0], "to_no": nos[1], "context": context})

    d("one_item", PRD, PRD.replace("한 줄로.", "두 줄로."))
    d("one_item.reverse", PRD.replace("한 줄로.", "두 줄로."), PRD, nos=(2, 1))
    d("whitespace_only", PRD, PRD.replace("한 줄로.", "  한 줄로.  "))
    d("blank_lines_only", PRD, PRD.replace("한 줄로.\n", "한 줄로.\n\n\n"))
    d("add_item", PRD, PRD + "\n#### N2 새 항목\n내용\n")
    d("remove_item", PRD + "\n#### N2 새 항목\n내용\n", PRD)
    d("outside_text", PRD, PRD.replace("# 예시 제품 PRD", "# 예시 제품 PRD v3"))
    d("dash_line_delete", PRD.replace("한 줄로.\n", "한 줄로.\n---\n"), PRD.replace("한 줄로.\n", "한 줄로.\n++x\n"))
    d("plus_minus_lines", PRD.replace("한 줄로.\n", "-a\n+b\n--c\n++d\n @@ e\n"), PRD.replace("한 줄로.\n", "+b\n-a\n@@ f\n---\n+++\n"))
    for n in (0, 1, 5):
        d(f"context.{n}", PRD, PRD.replace("한 줄로.", "두 줄로.").replace("- [ ] 하나", "- [ ] 하나 둘"), context=n)
    d("dup_ids", PRD.replace("#### N1 성능", "#### R1 다시"), PRD.replace("#### N1 성능", "#### R1 또"))
    d("title_changes_patterns", fm(doc_id="SYNC-DOM-001", typ="DOM", title="클래스 명세") + "#### Document a\n#### documents b\n",
      fm(doc_id="SYNC-DOM-001", typ="DOM", title="ERD") + "#### Document a\n#### documents c\n", doc_type="DOM")
    d("crlf", PRD, PRD.replace("\n", "\r\n"))
    d("same", PRD, PRD)
    rng = random.Random(345)
    pool = ["a", "b", "c", "- [ ] 하나", "", "|---|", "내용"]
    big_a = [rng.choice(pool) for _ in range(260)]
    big_b = list(big_a)
    for _ in range(25):
        i = rng.randrange(len(big_b))
        if rng.random() < 0.5:
            big_b.insert(i, rng.choice(pool + ["새 줄"]))
        else:
            del big_b[i]
    d("autojunk_block", fm() + "#### R1 큰 항목\n" + "\n".join(big_a) + "\n", fm() + "#### R1 큰 항목\n" + "\n".join(big_b) + "\n")
    return out


def difflibs() -> list[dict]:
    out: list[dict] = []
    rng = random.Random(20261008)
    alphabet = ["x", "y", "z", "", "가", "---", "+++", "@@"]
    for k in range(40):
        la = rng.choice([0, 1, 2, 5, 20, 199, 200, 201, 260])
        a = [rng.choice(alphabet[: 2 + k % 7]) for _ in range(la)]
        b = list(a)
        for _ in range(rng.randrange(0, 12)):
            if b and rng.random() < 0.5:
                del b[rng.randrange(len(b))]
            else:
                b.insert(rng.randrange(len(b) + 1), rng.choice(alphabet))
        out.append({"kind": "difflib", "name": f"seq.{k}", "a": a, "b": b, "n": rng.choice([0, 1, 3, 4])})
    return out


def main() -> None:
    data = {
        "_": "생성물 — cargo xtask spec-golden이 파이썬 판으로 만든다. 손으로 고치지 않는다",
        "versions": spec_answers.versions(),
        "patterns": spec_answers.patterns(),
        "cases": [spec_answers.answer(c) for c in cases() + diffs() + difflibs()],
    }
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
