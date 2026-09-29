"""카드 AR — ask_item이 이미지를 그 턴의 user 항목에만 싣고, read_attachment가 글자 첨부를 읽는다.

SYNC-MS-008#queries.ask_item 1·3 · #queries.ask_tool read_attachment · SYNC-MS-009#llm.step images.
"""

import base64
import json

from sqlalchemy.orm import Session

from app.core import queries
from app.core.conversation.service import ConversationService
from app.core.types import AskAnswer, AskNote, AskRead, AskStart
from app.infra.llm import _wire
from tests.core.conversation.test_attachments import PNG
from tests.core.spec.test_service import owner
from tests.core.test_queries import _call, _collect, _conv, _seed_refs, _step
from tests.core.test_queries import script as script_fixture  # noqa: F401 — 픽스처 재사용

script = script_fixture


async def test_images_ride_only_on_their_turn_and_attachments_are_listed(
    scoped: Session, script
) -> None:
    _seed_refs(scoped)
    conv = _conv(scoped)
    svc = ConversationService(scoped)
    u = owner(scoped)
    png = svc.add_attachment(conv, u, "캡처.png", "", PNG)
    md = svc.add_attachment(conv, u, "회의록.md", "", "결정: R13을 쓴다".encode())
    seen = script([_step("첫 답")])
    await _collect(
        queries.ask_item("EXMP-PRD-001", "G1", conv, "이 캡처 뭐야?", [png.id, md.id], u)
    )
    system, messages, _ = seen[0]
    assert "[첨부]" in system and f"{png.id} 캡처.png (image/png" in system
    assert f"{md.id} 회의록.md (text/markdown" in system and "read_attachment로 읽는다" in system
    assert messages[-1] == {"role": "user", "text": "이 캡처 뭐야?", "images": [("image/png", PNG)]}
    # 다음 턴 — 앞 턴의 이미지는 다시 안 실린다(history는 글자뿐), 첨부 목록은 남는다
    seen = script([_step("둘째 답")])  # seen은 픽스처 안에서 이어진다 — 마지막 호출을 본다
    await _collect(queries.ask_item("EXMP-PRD-001", "G1", conv, "그럼?", [], u))
    system, messages, _ = seen[-1]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert all("images" not in m for m in messages)
    assert "캡처.png" in system
    view = svc.get(conv, u)
    assert [m.name for m in view.turns[0].attachments] == ["캡처.png", "회의록.md"]


async def test_read_attachment_tool_reads_text_and_rejects_images(scoped: Session, script) -> None:
    _seed_refs(scoped)
    conv = _conv(scoped)
    svc = ConversationService(scoped)
    u = owner(scoped)
    md = svc.add_attachment(conv, u, "회의록.md", "", "결정: R13을 쓴다".encode())
    png = svc.add_attachment(conv, u, "캡처.png", "", PNG)
    other = svc.add_attachment(_conv(scoped), u, "남.md", "", b"x")
    seen = script(
        [
            _step(None, [_call("read_attachment", attachment_id=md.id, reason="회의록을 읽는다")]),
            _step(None, [_call("read_attachment", attachment_id=png.id, reason="캡처를 읽는다")]),
            _step(None, [_call("read_attachment", attachment_id=other.id, reason="남의 것")]),
            _step("R13 얘기다"),
        ]
    )
    events = await _collect(queries.ask_item("EXMP-PRD-001", "G1", conv, "회의록 내용?", [], u))
    assert events == [
        AskStart("EXMP-PRD-001", "G1"),
        AskNote("회의록을 읽는다"),
        AskRead("read_attachment", "첨부:회의록.md"),
        AskNote("캡처를 읽는다"),
        AskRead("read_attachment", None),
        AskNote("남의 것"),
        AskRead("read_attachment", None),
        AskAnswer("R13 얘기다", ["첨부:회의록.md"]),
    ]
    _, messages, _ = seen[3]
    tool_texts = [json.loads(m["text"]) for m in messages if m["role"] == "tool"]
    assert tool_texts[0]["text"] == "결정: R13을 쓴다" and tool_texts[0]["name"] == "회의록.md"
    assert tool_texts[1]["error"] == "없음" and "이미지" in tool_texts[1]["hint"]
    assert tool_texts[2]["error"] == "없음"
    assert svc.get(conv, u).turns[0].context_item_ids == ["첨부:회의록.md"]


def test_wire_puts_images_as_content_parts() -> None:
    m = {"role": "user", "text": "이건?", "images": [("image/png", b"\x89PNG")]}
    out = _wire(m)
    assert out["role"] == "user" and out["content"][0] == {"type": "text", "text": "이건?"}
    url = out["content"][1]["image_url"]["url"]
    assert url == "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode()
    assert _wire({"role": "user", "text": "없음", "images": []}) == {"role": "user", "content": "없음"}
