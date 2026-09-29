"""SYNC-MS-010 첨부 여섯 — add·remove·meta·bytes·text·pending_images (카드 AR)."""

import pytest
from sqlalchemy.orm import Session

from app.core.conversation.service import ConversationService
from app.core.errors import (
    AttachmentLimit,
    AttachmentSent,
    AttachmentTooLarge,
    AttachmentType,
    NotFound,
)
from tests.core.spec.test_service import make_project, owner

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

def _pdf(text: str) -> bytes:
    """글자 한 줄이 든 최소 PDF — xref 표까지 갖춘다(pypdf가 읽으려면 있어야 한다)."""
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


PDF = _pdf("Hello syncdoc")


def _conv(session: Session):
    make_project(session)
    u = owner(session)
    svc = ConversationService(session)
    return svc, svc.create("EXMP", u).id, u


def test_add_attachment_kinds_text_cache_and_meta(db_session: Session) -> None:
    svc, conv, u = _conv(db_session)
    md = svc.add_attachment(conv, u, "회의록.md", "text/markdown", "# 회의\n\n결정 하나".encode())
    assert md.mime == "text/markdown" and md.turn_id is None and md.text_cache == "# 회의\n\n결정 하나"
    png = svc.add_attachment(conv, u, "캡처.PNG", "", PNG)  # 확장자로 정한다. 대소문자 무관
    assert png.mime == "image/png" and png.text_cache is None and png.size == len(PNG)
    pdf = svc.add_attachment(conv, u, "회의록.pdf", "application/octet-stream", PDF)
    assert pdf.mime == "application/pdf" and "Hello syncdoc" in (pdf.text_cache or "")
    for name in ("a.jpg", "a.jpeg", "a.webp", "a.gif", "a.txt", "a.csv", "a.json", "a.yaml", "a.yml"):
        if len(svc.get(conv, u).pending) >= 8:  # 상한에 닿으면 보내고 계속 — 열 가지 전부 통과
            svc.add_turn(conv, "q", [m.id for m in svc.get(conv, u).pending])
        assert svc.add_attachment(conv, u, name, "", b"x").id
    meta = svc.attachment_meta(md.id, u)
    assert (meta.id, meta.name, meta.size) == (md.id, "회의록.md", md.size)  # 보낸 뒤라 turn_id가 있다
    assert svc.attachment_bytes(png.id, u) == ("캡처.PNG", "image/png", PNG)
    view = svc.get(conv, u)
    assert [m.name for m in view.turns[0].attachments][:3] == ["회의록.md", "캡처.PNG", "회의록.pdf"]


def test_add_attachment_rejects_type_size_and_limit(db_session: Session) -> None:
    svc, conv, u = _conv(db_session)
    with pytest.raises(AttachmentType):
        svc.add_attachment(conv, u, "a.exe", "", b"x")
    with pytest.raises(AttachmentType):
        svc.add_attachment(conv, u, "a.docx", "application/vnd.openxmlformats", b"x")
    with pytest.raises(AttachmentType):  # 확장자와 mime이 어긋난다
        svc.add_attachment(conv, u, "a.md", "image/png", b"x")
    with pytest.raises(AttachmentTooLarge) as e:
        svc.add_attachment(conv, u, "big.md", "", b"x" * (1024 * 1024 + 1))
    assert e.value.extra["limit"] == 1024 * 1024
    with pytest.raises(AttachmentTooLarge):
        svc.add_attachment(conv, u, "big.png", "", b"x" * (10 * 1024 * 1024 + 1))
    assert svc.add_attachment(conv, u, "ok.png", "", b"x" * (10 * 1024 * 1024)).size  # 딱 상한은 통과
    for i in range(7):
        svc.add_attachment(conv, u, f"f{i}.txt", "", b"x")
    with pytest.raises(AttachmentLimit):  # 아홉째
        svc.add_attachment(conv, u, "f9.txt", "", b"x")
    # 보내면 다시 8개 가능
    svc.add_turn(conv, "q", [m.id for m in svc.get(conv, u).pending])
    assert svc.add_attachment(conv, u, "again.txt", "", b"x").id


def test_add_turn_attaches_pending_and_pending_images(db_session: Session) -> None:
    svc, conv, u = _conv(db_session)
    a = svc.add_attachment(conv, u, "a.png", "", PNG)
    b = svc.add_attachment(conv, u, "b.md", "", "글".encode())
    other = svc.create("EXMP", u).id
    c = svc.add_attachment(other, u, "c.png", "", PNG)  # 다른 대화의 것 — 안 붙는다
    t = svc.add_turn(conv, "q", [a.id, b.id, c.id, 9999])
    view = svc.get(conv, u)
    assert [m.name for m in view.turns[0].attachments] == ["a.png", "b.md"] and view.pending == []
    assert svc.pending_images(t.id) == [("image/png", PNG)]  # 이미지만
    t2 = svc.add_turn(conv, "q2", [a.id])  # 이미 보낸 것은 다시 안 붙는다
    assert svc.get(conv, u).turns[1].attachments == [] and svc.pending_images(t2.id) == []


def test_attachment_text_only_this_conversation_and_not_images(db_session: Session) -> None:
    svc, conv, u = _conv(db_session)
    md = svc.add_attachment(conv, u, "a.md", "", "본문".encode())
    png = svc.add_attachment(conv, u, "a.png", "", PNG)
    assert svc.attachment_text(conv, md.id) == "본문"
    assert svc.attachment_text(conv, png.id) is None
    assert svc.attachment_text(conv + 999, md.id) is None
    assert svc.attachment_text(conv, 9999) is None


def test_remove_attachment_pending_only_and_ownership(db_session: Session) -> None:
    svc, conv, u = _conv(db_session)
    minjun = owner(db_session, "minjun")
    a = svc.add_attachment(conv, u, "a.md", "", b"x")
    with pytest.raises(NotFound) as e:
        svc.attachment_meta(a.id, minjun)
    assert e.value.extra["resource"] == "attachment"
    with pytest.raises(NotFound):
        svc.remove_attachment(a.id, minjun)
    with pytest.raises(NotFound):
        svc.add_attachment(conv, minjun, "b.md", "", b"x")
    svc.add_turn(conv, "q", [a.id])
    with pytest.raises(AttachmentSent):
        svc.remove_attachment(a.id, u)
    b = svc.add_attachment(conv, u, "b.md", "", b"x")
    svc.remove_attachment(b.id, u)
    with pytest.raises(NotFound):
        svc.attachment_meta(b.id, u)
