from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from pdfserve.tools.chat.chat import ChatConverter, ChatMessage


def _messages() -> list[ChatMessage]:
    return [
        ChatMessage(name="Alice", message="Hello Bob", timestamp=datetime(2026, 7, 27, 10, 0, 0)),
        ChatMessage(name="Bob", message="Hi Alice", timestamp=datetime(2026, 7, 27, 10, 1, 0)),
        ChatMessage(name="Carol", message="Explicitly incoming", direction="incoming"),
    ]


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


def test_to_html_marks_direction_classes():
    _, buf = ChatConverter(messages=_messages(), user_identifier_for_direction="Bob").to_html()
    html = buf.getvalue().decode("utf-8")

    assert 'class="message outgoing ' in html  # Bob is the user
    assert 'class="message incoming ' in html
    assert "ingoing" not in html  # the class the stylesheet no longer defines


def test_to_pdf_renders_every_message():
    _, buf = ChatConverter(messages=_messages(), user_identifier_for_direction="Bob").to_pdf()
    content = buf.getvalue()

    assert content.startswith(b"%PDF")
    text = _pdf_text(content)
    for expected in ("Alice", "Hello Bob", "Hi Alice", "Explicitly incoming", "2026-07-27 10:00:00"):
        assert expected in text


def test_to_pdf_escapes_markup():
    messages = [ChatMessage(name="Alice", message="<b>not bold</b>")]
    _, buf = ChatConverter(messages=messages).to_pdf()

    assert "<b>not bold</b>" in _pdf_text(buf.getvalue())


def test_to_pdf_keeps_a_message_too_long_for_one_page():
    # A bubble taller than a page must be split rather than clipped, so no word is lost.
    words = [f"word{i}" for i in range(3000)]
    messages = [ChatMessage(name="Alice", message=" ".join(words))]

    _, buf = ChatConverter(messages=messages).to_pdf()
    content = buf.getvalue()

    assert len(PdfReader(BytesIO(content)).pages) > 1
    text = _pdf_text(content)
    assert [w for w in words if w not in text] == []


def test_to_pdf_writes_file(tmp_path):
    out = tmp_path / "export"
    path, buf = ChatConverter(messages=_messages()).to_pdf(output=out)

    assert path == out.with_suffix(".pdf")
    assert path.read_bytes() == buf.getvalue()


def test_to_pdf_without_messages_raises():
    with pytest.raises(ValueError):
        ChatConverter(messages=[]).to_pdf()
