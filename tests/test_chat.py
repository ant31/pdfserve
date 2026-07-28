from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader
from weasyprint import HTML

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


def _bubble_widths(messages: list[ChatMessage]) -> list[tuple[float, float]]:
    """(x, width) of every rendered bubble, read out of WeasyPrint's own box tree."""
    html = ChatConverter(messages=messages).to_html()[1].getvalue().decode("utf-8")
    found: list[tuple[float, float]] = []
    for page in HTML(string=html).render().pages:
        stack = [page._page_box]
        while stack:
            box = stack.pop()
            element = getattr(box, "element", None)
            classes = element.get("class", "") if element is not None else ""
            if "message-bubble" in classes and type(box).__name__ != "TableBox":
                found.append((box.position_x + box.margin_left, box.border_width()))
            stack.extend(getattr(box, "children", []))
    return found


# A4 minus the 15mm side margins declared by @page, in CSS px.
PRINTABLE_WIDTH = 680.31
RIGHT_MARGIN = 56.69 + PRINTABLE_WIDTH


def test_bubble_hugs_short_content():
    (_, width), *_ = _bubble_widths([ChatMessage(name="Alice", message="hi")])

    assert width < PRINTABLE_WIDTH / 2  # shrink-to-fit, not a full-width block


def test_long_message_bubble_stays_within_the_page():
    # A single unbreakable token must not widen the bubble past the printable area: the width cap
    # lives on the bubble's children because a table box ignores max-width.
    long_url = "https://example.com/" + "a" * 200 + "/end"
    messages = [ChatMessage(name="Alice", message=f"look at {long_url}")]

    for x, width in _bubble_widths(messages):
        assert x + width <= RIGHT_MARGIN + 1, f"bubble runs off the page: right edge {x + width}"
        assert width <= PRINTABLE_WIDTH * 0.8


def test_multiline_message_keeps_its_width_cap():
    messages = [ChatMessage(name="Alice", message=" ".join(["lorem ipsum dolor sit amet consectetur"] * 12))]

    for _x, width in _bubble_widths(messages):
        assert width <= PRINTABLE_WIDTH * 0.8, f"bubble grew to full printable width: {width}"


def test_to_pdf_writes_file(tmp_path):
    out = tmp_path / "export"
    path, buf = ChatConverter(messages=_messages()).to_pdf(output=out)

    assert path == out.with_suffix(".pdf")
    assert path.read_bytes() == buf.getvalue()


def test_to_pdf_without_messages_raises():
    with pytest.raises(ValueError):
        ChatConverter(messages=[]).to_pdf()
