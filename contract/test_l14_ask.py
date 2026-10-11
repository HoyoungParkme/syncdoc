"""카드 L14 — 대화·질문 탭 (SYNC-SCN-001 S3·S9, UC-H19 · UI-5 8장 · UI-17 7): 두 판이 같은 가짜 모델(대본: 조각
스트림·도구 호출·단발·오류)을 부르게 하고, 대화·첨부 응답, 질문 SSE 바이트, **두 판이 모델에 보낸 요청 본문**까지
파이썬 판의 것(스냅숏 `ask_closed`)과 비교한다. 시각만 가린다 — 대화·턴·첨부 id는 두 판의 새 DB에서 같은 차례로 난다.
PDF 글자는 판마다 다를 수 있어(MS-021) 모델이 PDF를 읽게 하지 않는다.
"""

from __future__ import annotations

import json
import re

import pytest

import conftest
from snapshots import check
from test_l12_code import clone, mcp, push, wait_graph, write
from wire import request

pytestmark = pytest.mark.card("L14")

STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|\+00:00)")
CODE = "LCA"
JSON = ("Content-Type", "application/json")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
PRD = (
    "---\ndoc_id: LCA-PRD-001\ntype: PRD\ntitle: 묻기 대조\nstatus: draft\n---\n# 묻기 대조\n\n## 1. 목표\n\n"
    "## 2. 비목표\n\n## 3. 요구사항\n\n#### R1 첫 기능\n첫 기능을 설명한다.\n\n#### R13 열셋째\n설명.\n\n"
    "## 4. 성공지표\n\n## 5. 미결사항\n"
)


def masked(reply) -> dict:
    c = reply.contract()
    c["body"] = STAMP.sub("T", c["body"])
    return c


def rest(server, method: str, path: str, body=None, headers=None):
    if body is None:
        return request(server.port, method, path, headers or [])
    raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
    return request(server.port, method, path, headers or [JSON], raw)


def multipart(name: str, filename: str | None, ctype: str | None, data: bytes):
    boundary = "----syncdoc-contract"
    disp = f'form-data; name="{name}"' + (
        f'; filename="{filename}"' if filename is not None else ""
    )
    head = f"--{boundary}\r\nContent-Disposition: {disp}\r\n"
    if ctype:
        head += f"Content-Type: {ctype}\r\n"
    body = head.encode() + b"\r\n" + data + b"\r\n" + f"--{boundary}--\r\n".encode()
    return [("Content-Type", f"multipart/form-data; boundary={boundary}")], body


def upload(server, conv: int, filename: str | None, ctype: str | None, data: bytes, name="file"):
    hs, body = multipart(name, filename, ctype, data)
    return request(server.port, "POST", f"/api/conversations/{conv}/attachments", hs, body)


def sse(*chunks: dict) -> tuple[int, str, bytes]:
    text = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks)
    return 200, "text/event-stream", (text + "data: [DONE]\n\n").encode()


def delta(t: str) -> dict:
    return {"choices": [{"delta": {"content": t}}]}


def call(i: int, cid: str, name: str, args: str) -> dict:
    tc = {"index": i, "id": cid, "function": {"name": name, "arguments": args}}
    return {"choices": [{"delta": {"tool_calls": [tc]}}]}


COMMIT = re.compile(r"커밋 [0-9a-f]{7}")


def seen() -> list:
    """두 판이 모델에 보낸 본문 — 그래프 커밋 7자는 판마다 다르다"""
    out = json.loads(COMMIT.sub("커밋 h", json.dumps(conftest.FAKE_SEEN, ensure_ascii=False)))
    conftest.FAKE_SEEN.clear()
    return out


@pytest.fixture(scope="module")
def flow(_servers, tmp_path_factory):
    done: dict[str, dict] = {}

    def run(server) -> dict:
        if server.target in done:
            return done[server.target]
        got: dict = {}
        conftest.FAKE_SCRIPT.clear()
        conftest.FAKE_SEEN.clear()
        tmp = tmp_path_factory.mktemp(f"l14-{server.target}")
        (tmp / "client-gitconfig").write_text("")
        mcp(server, "init_project", {"storage": "server", "code": CODE, "name": "묻기 시험"})
        work = clone(server, tmp, CODE)
        write(work, "docs/specs/02-PRD/LCA-PRD-001.md", PRD)
        head = push(server, CODE, work, "PRD")
        # 코드가 없어도 그래프 행이 생긴다(함수 0) — 다 만든 뒤에 묻는다(코드에 묻기의 시작 맥락)
        wait_graph(server, CODE, lambda g: g["commit_hash"] == head)
        # 1. 대화
        base = f"/api/projects/{CODE}/conversations"
        got["list_empty"] = rest(server, "GET", base)
        got["create"] = rest(server, "POST", base, headers=[])
        conv = json.loads(got["create"].body)["id"]
        got["create_titled"] = rest(server, "POST", base, {"title": "  제목 있는 대화  "})
        conv2 = json.loads(got["create_titled"].body)["id"]
        got["create_bad"] = rest(server, "POST", base, {"title": 3})
        got["create_raw"] = rest(server, "POST", base, b"x", [("Content-Type", "text/plain")])
        got["create_other"] = rest(server, "POST", "/api/projects/NOPE/conversations")
        # 2. 첨부
        md = "# 메모\n첨부 본문이다\n".encode()
        got["up_md"] = upload(server, conv, "memo.md", "text/markdown", md)
        md_id = json.loads(got["up_md"].body)["id"]
        got["up_png"] = upload(server, conv, "pic.png", "image/png", PNG)
        png_id = json.loads(got["up_png"].body)["id"]
        got["up_pdf"] = upload(server, conv, "doc.pdf", None, b"%PDF-1.4 x")
        pdf_id = json.loads(got["up_pdf"].body)["id"]
        got["up_exe"] = upload(server, conv, "x.exe", None, b"MZ")
        got["up_mismatch"] = upload(server, conv, "x.md", "image/png", b"x")
        got["up_octet"] = upload(server, conv2, "note.txt", "application/octet-stream", b"t")
        got["up_korean"] = upload(server, conv2, "한글 이름.md", "text/markdown", "글".encode())
        got["up_empty"] = request(
            server.port,
            "POST",
            f"/api/conversations/{conv}/attachments",
            [("Content-Type", "multipart/form-data; boundary=B")],
            b"",
        )
        got["up_json"] = rest(server, "POST", f"/api/conversations/{conv}/attachments", {})
        got["up_no_boundary"] = request(
            server.port,
            "POST",
            f"/api/conversations/{conv}/attachments",
            [("Content-Type", "multipart/form-data")],
            b"x",
        )
        got["up_field"] = upload(server, conv, None, None, b"text", name="file")
        got["up_missing_conv"] = upload(server, 9999, "a.md", None, b"x")
        got["up_bad_id"] = upload(server, "abc", "a.md", None, b"x")  # type: ignore[arg-type]
        got["get_md"] = rest(server, "GET", f"/api/attachments/{md_id}")
        got["get_png"] = rest(server, "GET", f"/api/attachments/{png_id}")
        kor = json.loads(got["up_korean"].body)["id"]
        got["get_korean"] = rest(server, "GET", f"/api/attachments/{kor}")
        got["get_missing"] = rest(server, "GET", "/api/attachments/9999")
        # 3. 묻기 — 곁들인 말·도구 둘(get_item·read_attachment) → 답(링크·없는 참조)
        conftest.FAKE_SCRIPT.extend(
            [
                sse(
                    delta("먼저 "),
                    delta("R1을 읽는다"),
                    call(0, "c1", "get_item", '{"doc_id": "LCA-PRD-001", '),
                    call(0, "", "", '"item_id": "R1", "reason": "R1 본문"}'),
                    call(
                        1,
                        "c2",
                        "read_attachment",
                        f'{{"attachment_id": {md_id}, "reason": "메모"}}',
                    ),
                    {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 4}},
                ),
                sse(
                    delta("답: LCA-PRD-001#R1은 첫 기능이다. "),
                    delta("LCA-PRD-001#R99도 보라. `LCA-PRD-001#R1`"),
                ),
            ]
        )
        ask = f"/api/docs/{CODE}-PRD-001/ask"
        got["ask"] = rest(
            server,
            "POST",
            ask,
            {"question": "R1이 뭐야?", "conversation_id": conv, "item_id": "R13",
             "attachment_ids": [md_id, png_id]},
        )  # fmt: skip
        got["ask_seen"] = seen()
        got["conv_after_ask"] = rest(server, "GET", f"/api/conversations/{conv}")
        # 4. 모델 500 — error 프레임, 턴은 실패 / 단발 JSON — 조각 없이 답
        conftest.FAKE_SCRIPT.append((500, "text/plain", b"down"))
        got["ask_fail"] = rest(
            server, "POST", ask, {"question": "두 번째", "conversation_id": conv}
        )
        got["ask_fail_seen"] = seen()
        single = {
            "choices": [{"message": {"content": "단발 답이다"}}],
            "usage": {"prompt_tokens": 1},
        }
        conftest.FAKE_SCRIPT.append((200, "application/json", json.dumps(single).encode()))
        got["ask_single"] = rest(
            server, "POST", ask, {"question": "세 번째", "conversation_id": conv}
        )
        got["ask_single_seen"] = seen()
        got["conv_after_all"] = rest(server, "GET", f"/api/conversations/{conv}")
        # 5. 시작 전 실패 — 상태 코드, 턴 없음
        got["ask_no_conv"] = rest(server, "POST", ask, {"question": "q", "conversation_id": 9999})
        got["ask_bad_item"] = rest(
            server, "POST", ask, {"question": "q", "conversation_id": conv, "item_id": "R99"}
        )
        got["ask_invalid"] = rest(server, "POST", ask, {"conversation_id": "abc"})
        got["ask_other_project"] = rest(
            server, "POST", "/api/docs/NOPE-PRD-001/ask", {"question": "q", "conversation_id": conv}
        )
        got["ask_wrong_project_conv"] = rest(
            server,
            "POST",
            "/api/projects/NOPE/code/ask",
            {"question": "q", "conversation_id": conv},
        )
        got["ask_none_seen"] = seen()
        # 6. 코드에 묻기 — 그래프 없음
        conftest.FAKE_SCRIPT.append(sse(delta("그래프가 없다")))
        code_ask = f"/api/projects/{CODE}/code/ask"
        got["ask_code"] = rest(
            server, "POST", code_ask, {"question": "그래프?", "conversation_id": conv2}
        )
        got["ask_code_seen"] = seen()
        got["ask_code_key"] = rest(
            server, "POST", code_ask, {"question": "q", "conversation_id": conv2, "key": "a.py:1"}
        )
        # 7. 빼기·지우기
        got["del_sent"] = rest(server, "DELETE", f"/api/attachments/{md_id}")
        got["del_pdf"] = rest(server, "DELETE", f"/api/attachments/{pdf_id}")
        got["del_again"] = rest(server, "DELETE", f"/api/attachments/{pdf_id}")
        got["get_conv_bad"] = rest(server, "GET", "/api/conversations/abc")
        got["get_conv_huge"] = rest(server, "GET", "/api/conversations/99999999999")
        got["list_after"] = rest(server, "GET", base)
        got["del_conv"] = rest(server, "DELETE", f"/api/conversations/{conv2}")
        got["get_deleted"] = rest(server, "GET", f"/api/conversations/{conv2}")
        done[server.target] = got
        return got

    return run


REPLIES = [
    "list_empty",
    "create",
    "create_titled",
    "create_bad",
    "create_raw",
    "create_other",
    "up_md",
    "up_png",
    "up_pdf",
    "up_exe",
    "up_mismatch",
    "up_octet",
    "up_korean",
    "up_empty",
    "up_json",
    "up_no_boundary",
    "up_field",
    "up_missing_conv",
    "up_bad_id",
    "get_md",
    "get_png",
    "get_korean",
    "get_missing",
    "ask",
    "conv_after_ask",
    "ask_fail",
    "ask_single",
    "conv_after_all",
    "ask_no_conv",
    "ask_bad_item",
    "ask_invalid",
    "ask_other_project",
    "ask_wrong_project_conv",
    "ask_code",
    "ask_code_key",
    "del_sent",
    "del_pdf",
    "del_again",
    "get_conv_bad",
    "get_conv_huge",
    "list_after",
    "del_conv",
    "get_deleted",
]


@pytest.mark.parametrize("key", REPLIES)
def test_ask_replies(server, flow, key):
    check("ask_closed", key, masked(flow(server)[key]), server.target)


@pytest.mark.parametrize(
    "key", ["ask_seen", "ask_fail_seen", "ask_single_seen", "ask_none_seen", "ask_code_seen"]
)
def test_model_saw_the_same_requests(server, flow, key):
    """두 판이 모델에 보낸 본문 — 지시문·대화록·이미지·도구 아홉·도구 결과까지"""
    check("ask_closed", key, flow(server)[key], server.target)
