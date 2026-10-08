"""카드 L7 — 저장 파이프라인과 MCP 읽기·쓰기 도구 (SYNC-SCN-001 S1·S3·S4): `create_document`·`update_document`·
`list_documents`·`get_document`·`get_item`·`get_references`.

응답 바이트를 파이썬 판의 것(스냅숏 `documents_closed`)과 비교한다. 커밋 해시와 시각만 가린다 — 판마다 다르다.
사례는 차례대로 상태를 쌓는다(만들기 → 읽기 → 고치기 → 삭제 확인 → 끊긴 참조 → 나중 상위가 잇기).
코드는 두 판 차이 시험의 단어(SYNC·PRD·DOM·MCP)와 겹치지 않게 쓴다.
"""

from __future__ import annotations

import json
import random
import re

import pytest

from conftest import token_for
from snapshots import check
from wire import request

pytestmark = pytest.mark.card("L7")

ACCEPT = ("Accept", "application/json, text/event-stream")
JSON = ("Content-Type", "application/json")

HASH = re.compile(r"\b[0-9a-f]{40}\b")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00")


def masked(reply) -> dict:
    """비교할 꼴 — 커밋 해시와 시각(`+00:00`)은 판마다 다르다"""
    c = reply.contract()
    c["body"] = STAMP.sub("T", HASH.sub("H", c["body"]))
    return c


def mcp(server, name: str, args: dict):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        ensure_ascii=False,
    ).encode()
    hs = [("Authorization", f"Bearer {token_for(server)}"), ACCEPT, JSON]
    return request(server.port, "POST", "/mcp", hs, body)


def result(reply) -> dict:
    """SSE 한 사건의 CallToolResult 안의 JSON"""
    data = json.loads(reply.body.decode().split("data: ", 1)[1])
    return json.loads(data["result"]["content"][0]["text"])


PRD = (
    "# 문서 시험\n\n## 1. 목표\n\n#### G1 첫 목표\n한 줄.\n\n## 2. 비목표\n\n## 3. 요구사항\n\n"
    "#### R1 첫 기능\n설명. 근거 [[LDA-RFQ-001#Q1]]\n\n#### R2 둘째 기능\n설명.\n\n## 4. 성공지표\n\n## 5. 미결사항\n"
)
SCN = (
    "---\ndoc_id: \ntype: SCN\ntitle: 시나리오\nstatus: draft\nupstream: [LDA-PRD-001]\n---\n# 시나리오\n\n"
    "## 1. 페르소나\n\n#### P1 사람\n누구.\n\n## 2. 시나리오\n\n#### S1 첫 흐름\n근거: [[LDA-PRD-001#R2]] · [[LDA-UC-001#UC-A1]] · [[#P1]]\n\n"
    "## 3. 대응표\n\n표에서 [[LDA-PRD-001#R1]] · [[LDA-PRD-001]]\n"
)
UC = (
    "# 유스케이스\n\n## 1. 액터\n\n## 2. 사용자 목표 수준 유스케이스\n\n#### UC-A1 첫 일\n근거 [[LDA-SCN-001#S1]]\n\n"
    "## 3. 하위기능 수준 유스케이스\n\n## 4. 대응표\n"
)


def prd_v1() -> str:
    """서버가 frontmatter를 채운 PRD v1 — 고치기 사례가 쓴다(만들기 사례가 같은 것을 만든다)"""
    return "---\ndoc_id: LDA-PRD-001\ntype: PRD\ntitle: 문서 시험\nstatus: draft\n---\n" + PRD


def without_r2(body: str) -> str:
    return body.replace("#### R2 둘째 기능\n설명.\n\n", "")


CASES = [
    ("init", "init_project", {"storage": "server", "code": "LDA", "name": "문서 시험"}),
    # 만들기 — 발급·frontmatter·경고·next_step, 그리고 막히는 것들(아무것도 안 남는다)
    (
        "prd_create",
        "create_document",
        {"project_code": "LDA", "doc_type": "PRD", "body": PRD, "message": "PRD 첫 판"},
    ),
    (
        "prd_padding",
        "create_document",
        {
            "project_code": "LDA",
            "doc_type": "PRD",
            "body": PRD.replace("R2", "R02"),
            "message": "m",
        },
    ),
    (
        "unknown_type",
        "create_document",
        {"project_code": "LDA", "doc_type": "XYZ", "body": "본문", "message": "m"},
    ),
    (
        "lower_type",
        "create_document",
        {"project_code": "LDA", "doc_type": "prd", "body": "# 제목\n", "message": "m"},
    ),
    (
        "dom_class_unmet",
        "create_document",
        {"project_code": "LDA", "doc_type": "DOM", "body": "# 클래스 명세\n", "message": "m"},
    ),
    (
        "dom_no_subtype",
        "create_document",
        {"project_code": "LDA", "doc_type": "DOM", "body": "# 그냥\n", "message": "m"},
    ),
    (
        "create_no_project",
        "create_document",
        {"project_code": "NOPE", "doc_type": "PRD", "body": PRD, "message": "m"},
    ),
    (
        "create_empty_project",
        "create_document",
        {"project_code": "", "doc_type": "PRD", "body": PRD, "message": "m"},
    ),
    (
        "create_other_id",
        "create_document",
        {
            "project_code": "LDA",
            "doc_type": "PRD",
            "body": prd_v1().replace("LDA-PRD-001", "LDA-PRD-007"),
            "message": "m",
        },
    ),
    (
        "scn_create",
        "create_document",
        {"project_code": "LDA", "doc_type": "SCN", "body": SCN, "message": "SCN 첫 판"},
    ),
    # 읽기
    ("get_prd", "get_document", {"doc_id": "LDA-PRD-001"}),
    ("get_scn", "get_document", {"doc_id": "LDA-SCN-001"}),
    ("get_missing_doc", "get_document", {"doc_id": "LDA-PRD-404"}),
    ("get_empty", "get_document", {"doc_id": ""}),
    ("get_other_project", "get_document", {"doc_id": "NOPE-PRD-001"}),
    ("list_all", "list_documents", {"project_code": "LDA"}),
    ("list_stage2", "list_documents", {"project_code": "LDA", "stage": 2}),
    ("list_stage_str", "list_documents", {"project_code": "LDA", "stage": "3"}),
    ("list_stage0", "list_documents", {"project_code": "LDA", "stage": 0}),
    ("list_stage_huge", "list_documents", {"project_code": "LDA", "stage": 10**30}),
    ("list_draft", "list_documents", {"project_code": "LDA", "status": "draft"}),
    ("list_status_other", "list_documents", {"project_code": "LDA", "status": "review"}),
    ("list_no_project", "list_documents", {"project_code": "NOPE"}),
    ("item_r1", "get_item", {"doc_id": "LDA-PRD-001", "item_id": "R1"}),
    ("item_last", "get_item", {"doc_id": "LDA-SCN-001", "item_id": "S1"}),
    ("item_missing", "get_item", {"doc_id": "LDA-PRD-001", "item_id": "R9"}),
    ("item_tilde", "get_item", {"doc_id": "LDA-PRD-001", "item_id": "R~1"}),
    ("item_no_doc", "get_item", {"doc_id": "LDA-PRD-404", "item_id": "R1"}),
    ("refs_r2", "get_references", {"doc_id": "LDA-PRD-001", "item_id": "R2"}),
    ("refs_r1", "get_references", {"doc_id": "LDA-PRD-001", "item_id": "R1"}),
    ("refs_s1", "get_references", {"doc_id": "LDA-SCN-001", "item_id": "S1"}),
    ("refs_lonely", "get_references", {"doc_id": "LDA-PRD-001", "item_id": "G1"}),
    ("refs_missing", "get_references", {"doc_id": "LDA-PRD-001", "item_id": "R9"}),
    # 고치기
    (
        "update_stale",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": prd_v1(),
            "expected_version": 9,
            "message": "m",
            "changed_items": [],
        },
    ),
    (
        "update_status_change",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": prd_v1().replace("status: draft", "status: approved"),
            "expected_version": 1,
            "message": "m",
            "changed_items": [],
        },
    ),
    (
        "update_same_body",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": prd_v1(),
            "expected_version": 1,
            "message": "그대로",
            "changed_items": [],
        },
    ),
    (
        "update_r1",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": prd_v1().replace("설명. 근거", "고친 설명. 근거"),
            "expected_version": 2,
            "message": "R1 고침",
            "changed_items": ["R1"],
        },
    ),
    (
        "delete_r2_ask",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": without_r2(prd_v1()),
            "expected_version": 3,
            "message": "R2 지움",
            "changed_items": [],
        },
    ),
    (
        "delete_r2_confirm",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": without_r2(prd_v1()),
            "expected_version": 3,
            "message": "R2 지움",
            "changed_items": [],
            "confirm_item_deletion": True,
        },
    ),
    ("item_r2_deleted", "get_item", {"doc_id": "LDA-PRD-001", "item_id": "R2"}),
    ("refs_r2_deleted", "get_references", {"doc_id": "LDA-PRD-001", "item_id": "R2"}),
    ("get_scn_broken", "get_document", {"doc_id": "LDA-SCN-001"}),
    (
        "reuse_r2",
        "update_document",
        {
            "doc_id": "LDA-PRD-001",
            "body": prd_v1(),
            "expected_version": 4,
            "message": "m",
            "changed_items": [],
        },
    ),
    (
        "update_no_doc",
        "update_document",
        {
            "doc_id": "LDA-PRD-404",
            "body": "x",
            "expected_version": 1,
            "message": "m",
            "changed_items": [],
        },
    ),
    (
        "update_empty_id",
        "update_document",
        {"doc_id": "", "body": "x", "expected_version": 1, "message": "m", "changed_items": []},
    ),
    (
        "update_empty_message",
        "update_document",
        {
            "doc_id": "LDA-SCN-001",
            "body": SCN.replace("doc_id: ", "doc_id: LDA-SCN-001").replace("누구.", "누구?"),
            "expected_version": 1,
            "message": "",
            "changed_items": [],
        },
    ),
    # 나중에 만든 상위 문서가 기다리던 미존재 참조를 잇는다
    (
        "uc_create",
        "create_document",
        {"project_code": "LDA", "doc_type": "UC", "body": UC, "message": "UC"},
    ),
    ("refs_s1_after_uc", "get_references", {"doc_id": "LDA-SCN-001", "item_id": "S1"}),
    ("list_after", "list_documents", {"project_code": "LDA"}),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_mcp_tools(server, case):
    name, tool, args = case
    check("documents_closed", name, masked(mcp(server, tool, args)), server.target)


def test_saved_document_reads_back_with_next_step(server):
    """S1 — 만든 문서를 읽으면 같은 본문·판, 저장 결과는 사람에게 멈추라고 한다"""
    made = result(
        mcp(
            server,
            "create_document",
            {
                "project_code": "LDA",
                "doc_type": "RFQ",
                "body": "# 요청\n\n## 1. 배경\n\n#### Q1 첫 요청\n무엇.\n",
                "message": "RFQ",
            },
        )
    )
    assert made["doc_id"] == "LDA-RFQ-001" and made["version_no"] == 1
    assert made["next_step"].startswith("LDA-RFQ-001 v1 저장됨.")
    got = result(mcp(server, "get_document", {"doc_id": "LDA-RFQ-001"}))
    assert got["version_no"] == 1 and got["commit_hash"] == made["commit_hash"]
    assert got["last_author"]["kind"] == "agent" and got["last_author"]["via"] == "mcp"
    # PRD R1이 기다리던 Q1이 이어졌다
    refs = result(mcp(server, "get_references", {"doc_id": "LDA-PRD-001", "item_id": "R1"}))
    assert [r["is_missing"] for r in refs["upstream"]] == [False]


# ── 두 판 차이 시험 — 문서 도구만 겨냥한다(L3 차이 시험의 무작위 인자는 저장까지 거의 닿지 않는다) ──

D_TYPES = [
    "PRD",
    "PRD",
    "SCN",
    "RFQ",
    "UC",
    "INFRA",
    "DOM",
    "API",
    "UI",
    "MS",
    "CODE",
    "STD",
    "XYZ",
    "prd",
    "",
]
D_TOKENS = [
    "R1",
    "R2",
    "R3",
    "R01",
    "R1.",
    "G1",
    "N1",
    "S1",
    "S2",
    "P1",
    "UC-A1",
    "UC-H2",
    "Q1",
    "C1",
    "C2",
    "X1",
    "GET/api/me",
    "POST/api/x",
    "UI-1",
    "SEQ-1",
    "AccountService.local_user",
    "L1",
    "1.",
    "목적",
]
D_TITLES = [
    "시험",
    "클래스 명세",
    "ERD",
    "도메인 모델",
    "REST",
    "MCP",
    "화면 설계",
    "와이어프레임",
    "",
    "제목 R1",
]
D_TEXT = [
    "설명.",
    "한글 문장 😀",
    "`[[LDB-PRD-001#R1]]` 코드 안",
    "출처: 사용자",
    "- [ ] 할 일",
    "é \t탭",
    "",
    "| a | b |",
]


def d_ref(r, known: list[str]) -> str:
    doc = (
        r.choice([*known, "LDB-PRD-001", "LDB-UC-009", "", "bad ref", "LDB-SCN-001"])
        if known
        else "LDB-PRD-001"
    )
    item = r.choice(["", "#R1", "#R2", "#S1", "#UC-A1", "#Q1", "#", "#R 1"])
    return f"[[{doc}{item}]]"


def d_body(r, doc_type: str, doc_id: str | None, status: str, known: list[str]) -> str:
    lines: list[str] = []
    if r.random() < 0.8:
        fm = ["---"]
        if r.random() < 0.95:
            fm.append(
                f"doc_id: {doc_id if doc_id and r.random() < 0.9 else r.choice(['', 'LDB-PRD-077', 'x'])}"
            )
        if r.random() < 0.95:
            fm.append(f"type: {doc_type if r.random() < 0.9 else r.choice(D_TYPES)}")
        if r.random() < 0.95:
            fm.append(f"title: {r.choice(D_TITLES)}")
        if r.random() < 0.95:
            fm.append(
                f"status: {status if r.random() < 0.92 else r.choice(['draft', 'approved', 'review'])}"
            )
        if r.random() < 0.5:
            ups = (
                [r.choice([*known, "LDB-RFQ-001", "LDB-XYZ-1"]) for _ in range(r.randint(0, 2))]
                if known
                else []
            )
            fm.append(f"upstream: [{', '.join(ups)}]")
        fm.append("---")
        lines += fm
    if r.random() < 0.8:
        lines.append(f"# {r.choice(D_TITLES) or '문서'}")
    for n in range(r.randint(0, 5)):
        lines.append(
            f"## {n + 1}. {r.choice(['목표', '요구사항', '시나리오', '배경', '페르소나', '액터', '대응표', '미결사항', '기타'])}"
        )
        for _ in range(r.randint(0, 3)):
            lvl = r.choice(["###", "####", "####", "#####"])
            lines.append(
                f"{lvl} {r.choice(D_TOKENS)} {r.choice(['이름', '둘째', '', '한글 이름'])}".rstrip()
            )
            for _ in range(r.randint(0, 3)):
                t = r.choice(D_TEXT)
                if r.random() < 0.5:
                    t += " " + d_ref(r, known)
                lines.append(t)
            if r.random() < 0.15:
                lines += ["```", f"#### R99 안 {d_ref(r, known)}", "```"]
        if r.random() < 0.3:
            lines.append("표에서 " + d_ref(r, known))
    return "\n".join(lines) + ("\n" if r.random() < 0.8 else "")


VALID = {
    "PRD": ["G1", "R1", "R2", "R3", "N1"],
    "SCN": ["P1", "S1", "S2"],
    "RFQ": ["Q1", "Q2"],
    "UC": ["UC-A1", "UC-A2", "UC-H1"],
    "INFRA": ["C1", "C2"],
}


def d_valid(r, doc_type: str, doc_id: str | None, status: str, known_items: list[str]) -> str:
    """규약을 지키는 본문 — 항목은 그 타입의 것, 참조는 있는 항목·없는 항목을 섞는다"""
    lines = [
        "---",
        f"doc_id: {doc_id or ''}",
        f"type: {doc_type}",
        "title: 시험",
        f"status: {status}",
    ]
    if r.random() < 0.5 and known_items:
        lines.append(f"upstream: [{r.choice(known_items).split('#')[0]}]")
    lines += ["---", "# 시험", "", "## 1. 첫 절", ""]
    for tok in r.sample(VALID[doc_type], r.randint(1, len(VALID[doc_type]))):
        lines.append(f"#### {tok} {r.choice(['이름', '한글 이름', '둘'])}")
        for _ in range(r.randint(0, 2)):
            pool = known_items + ["LDB-UC-009#UC-A1", f"#{tok}"]
            lines.append(r.choice(D_TEXT) + " " + f"[[{r.choice(pool)}]]")
        lines.append("")
    if r.random() < 0.3 and known_items:
        lines.append("표에서 [[" + r.choice(known_items) + "]]")
    return "\n".join(lines) + "\n"


def d_mutate(r, body: str, doc_type: str, known_items: list[str]) -> str:
    """지금 본문을 조금 바꾼다 — 항목 하나 지우기·더하기·글 고치기"""
    lines = body.split("\n")
    heads = [i for i, ln in enumerate(lines) if ln.startswith("#### ")]
    k = r.random()
    if k < 0.4 and heads:
        h = r.choice(heads)
        end = next((j for j in heads if j > h), len(lines))
        del lines[h:end]
    elif k < 0.7:
        tok = r.choice(VALID.get(doc_type, ["R9"]))
        ref = f" [[{r.choice(known_items)}]]" if known_items else ""
        lines += [f"#### {tok} 새 항목", "새 글." + ref, ""]
    else:
        lines.append(r.choice(D_TEXT) + (f" [[{r.choice(known_items)}]]" if known_items else ""))
    return "\n".join(lines)


def test_documents_both_editions_answer_alike(both, request):
    py, rs = both
    count = request.config.getoption("--diff-count") // 3
    seed = request.config.getoption("--diff-seed")
    r = random.Random(seed)
    for s in (py, rs):
        mcp(s, "init_project", {"storage": "server", "code": "LDB", "name": "차이"})
    known: list[str] = []
    versions: dict[str, int] = {}
    types: dict[str, str] = {}
    statuses: dict[str, str] = {}
    bodies: dict[str, str] = {}
    items: dict[str, list[str]] = {}
    diffs = []
    for i in range(count):
        k = r.random()
        known_items = [f"{d}#{it}" for d in known for it in items.get(d, [])]
        if k < 0.3 or not known:
            t = r.choice(D_TYPES)
            body = (
                d_valid(r, t, None, "draft", known_items)
                if t in VALID and r.random() < 0.6
                else d_body(r, t, None, "draft", known)
            )
            tool, args = (
                "create_document",
                {
                    "project_code": r.choice(["LDB"] * 9 + ["NOPE"]),
                    "doc_type": t,
                    "body": body,
                    "message": r.choice(["만들기"] * 6 + ["m", "", " "]),
                },
            )
        elif k < 0.55:
            d = r.choice(known)
            v = versions[d] if r.random() < 0.85 else r.choice([0, versions[d] + 1, -1])
            t = types[d]
            body = (
                d_mutate(r, bodies[d], t, known_items)
                if r.random() < 0.6
                else d_valid(r, t, d, statuses[d], known_items)
                if t in VALID and r.random() < 0.6
                else d_body(r, t, d, statuses[d], known)
            )
            tool, args = (
                "update_document",
                {
                    "doc_id": d,
                    "body": body,
                    "expected_version": v,
                    "message": r.choice(["고침"] * 6 + ["m", ""]),
                    "changed_items": [],
                    "confirm_item_deletion": r.random() < 0.5,
                },
            )
        elif k < 0.67:
            tool, args = "get_document", {"doc_id": r.choice([*known, "LDB-PRD-404", ""])}
        elif k < 0.8:
            pool = [x.split("#")[1] for x in known_items] or ["R1"]
            tool, args = (
                "get_item",
                {"doc_id": r.choice(known), "item_id": r.choice(pool + D_TOKENS[:4] + ["R~1"])},
            )
        elif k < 0.94:
            pick = (
                r.choice(known_items)
                if known_items and r.random() < 0.85
                else f"{r.choice(known)}#R1"
            )
            tool, args = (
                "get_references",
                {"doc_id": pick.split("#")[0], "item_id": pick.split("#")[1]},
            )
        else:
            args = {"project_code": "LDB"}
            if r.random() < 0.5:
                args["stage"] = r.choice([1, 2, 3, 6, 11, 12, 0])
            if r.random() < 0.3:
                args["status"] = r.choice(["draft", "approved", "x"])
            tool = "list_documents"
        a, b = masked(mcp(py, tool, args)), masked(mcp(rs, tool, args))
        if a != b:
            diffs.append((i, tool, args, a, b))
        # 상태는 파이썬 판의 답으로 따라간다
        if tool in ("create_document", "update_document") and '\\"next_step\\"' in a["body"]:
            out = result(
                mcp(
                    py,
                    "get_document",
                    {
                        "doc_id": json.loads(
                            json.loads(a["body"].split("data: ", 1)[1])["result"]["content"][0][
                                "text"
                            ]
                        )["doc_id"]
                    },
                )
            )
            if out["doc_id"] not in known:
                known.append(out["doc_id"])
            versions[out["doc_id"]] = out["version_no"]
            types[out["doc_id"]] = out["doc_type"]
            statuses[out["doc_id"]] = out["status"]
            bodies[out["doc_id"]] = out["body"]
            items[out["doc_id"]] = [x["item_id"] for x in out["items"]]
            mcp(rs, "get_document", {"doc_id": out["doc_id"]})  # 두 판에 같은 차례로 부른다
    detail = "\n".join(
        f"#{i} {tool} {json.dumps(args, ensure_ascii=False)[:400]}\n  파이썬 {a}\n  Rust   {b}"
        for i, tool, args, a, b in diffs[:3]
    )
    assert not diffs, f"{len(diffs)}/{count}개가 다르다 (문서 {len(known)}):\n{detail}"
