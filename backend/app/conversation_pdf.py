"""Render an inspection assistant conversation as a searchable PDF."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer


def _font() -> str:
    for name, path in (
        ("ConversationArial", Path("C:/Windows/Fonts/arial.ttf")),
        ("ConversationDejaVu", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
    ):
        if path.is_file():
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
    return "Helvetica"


def render_conversation_pdf(messages: list[dict], image_name: str | None = None, conversation_title: str = "Inspection assistant conversation") -> bytes:
    output = BytesIO()
    font = _font()
    dark = colors.HexColor("#21313A")
    muted = colors.HexColor("#667982")
    accent = colors.HexColor("#C65D2A")
    title = ParagraphStyle("ConversationTitle", fontName=font, fontSize=16, leading=22, textColor=dark, spaceAfter=14)
    metadata = ParagraphStyle("ConversationMetadata", fontName=font, fontSize=9, leading=13, textColor=muted, spaceAfter=5)
    role = ParagraphStyle("ConversationRole", fontName=font, fontSize=10, leading=14, textColor=accent, spaceAfter=4)
    body = ParagraphStyle("ConversationBody", fontName=font, fontSize=10, leading=15, textColor=dark, spaceAfter=6, alignment=TA_LEFT, wordWrap="CJK")
    source = ParagraphStyle("ConversationSource", fontName=font, fontSize=8, leading=12, textColor=muted, leftIndent=12, spaceAfter=3, wordWrap="CJK")

    def paragraph(value: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(value).replace("\n", "<br/>"), style)

    story = [paragraph(conversation_title, title)]
    if image_name:
        story.append(paragraph(f"Image: {image_name}", metadata))
    story.append(paragraph(f"Saved: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", metadata))
    story.append(Spacer(1, 12))
    for message in messages:
        parts = [paragraph("You" if message["role"] == "user" else "Assistant", role), paragraph(message["text"], body)]
        for item in message.get("sources") or []:
            parts.append(paragraph(f"Local source: {item.get('filename', '')} — {item.get('locator', '')}", source))
            if item.get("excerpt"):
                parts.append(paragraph(item["excerpt"], source))
        for item in message.get("webSources") or []:
            parts.append(paragraph(f"Web source: {item.get('title') or item.get('url', '')} — {item.get('url', '')}", source))
        parts.append(Spacer(1, 10))
        story.extend(parts)

    def header_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DDE3E6"))
        canvas.line(48, 44, document.pagesize[0] - 48, 44)
        canvas.setFont(font, 8)
        canvas.setFillColor(muted)
        canvas.drawString(48, 32, "Inspection assistant conversation")
        canvas.drawRightString(document.pagesize[0] - 48, 32, f"Page {document.page}")
        canvas.restoreState()

    document = BaseDocTemplate(output, pagesize=(595.28, 841.89), leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=58,
                               title=conversation_title, author="Tower Thermal Inspector")
    frame = Frame(document.leftMargin, document.bottomMargin, document.width, document.height, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document.addPageTemplates(PageTemplate(id="conversation", frames=frame, onPage=header_footer))
    document.build(story)
    return output.getvalue()


def render_conversation_text(messages: list[dict], image_name: str | None = None, conversation_title: str = "Inspection assistant conversation") -> str:
    lines = [conversation_title, "=" * len(conversation_title)]
    if image_name:
        lines.append(f"Image: {image_name}")
    lines.extend((f"Saved: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", ""))
    for message in messages:
        lines.extend(("You" if message["role"] == "user" else "Assistant", message["text"], ""))
        for item in message.get("sources") or []:
            lines.append(f"Local source: {item.get('filename') or ''} — {item.get('locator') or ''}")
            if item.get("excerpt"):
                lines.append(item["excerpt"])
        for item in message.get("webSources") or []:
            lines.append(f"Web source: {item.get('title') or item.get('url') or ''} — {item.get('url') or ''}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
