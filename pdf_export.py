"""
Task 14: تصدير تقرير PDF منسّق (على شكل جداول) لأي سؤال/مقارنة صار
عليها رد من المساعد. بيستخدم reportlab (Platypus) عشان نبني جداول
نظيفة بدل نص عادي مبعثر.
"""

import os
import time
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

EXPORT_FOLDER = "exports"

_styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "ReportTitle",
    parent=_styles["Title"],
    fontSize=20,
    spaceAfter=2,
    textColor=colors.HexColor("#4338ca"),
)
META_STYLE = ParagraphStyle(
    "Meta",
    parent=_styles["Normal"],
    fontSize=9,
    textColor=colors.HexColor("#64748b"),
)
SECTION_STYLE = ParagraphStyle(
    "Section",
    parent=_styles["Heading2"],
    fontSize=13,
    spaceBefore=16,
    spaceAfter=8,
    textColor=colors.HexColor("#1e1b4b"),
)
BODY_STYLE = ParagraphStyle(
    "Body",
    parent=_styles["Normal"],
    fontSize=10.5,
    leading=15,
)
CELL_STYLE = ParagraphStyle(
    "Cell",
    parent=_styles["Normal"],
    fontSize=9.5,
    leading=13,
)
CELL_HEADER_STYLE = ParagraphStyle(
    "CellHeader",
    parent=_styles["Normal"],
    fontSize=9.5,
    leading=13,
    textColor=colors.white,
    fontName="Helvetica-Bold",
)

TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4338ca")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
)


def _cell(text):
    """يحوّل نص عادي لـ Paragraph جوا خلية الجدول عشان يلف (wrap) صح
    بدل ما يطلع براني الجدول."""
    text = (text or "-").replace("\n", "<br/>")
    return Paragraph(text, CELL_STYLE)


def _header_row(*labels):
    return [Paragraph(label, CELL_HEADER_STYLE) for label in labels]


def build_report_pdf(question, answer, evidence=None, comparison_cards=None):
    """يبني PDF منسّق (عناوين + جداول) لسؤال/جواب واحد من الشات، وبيرجع
    مسار الملف الناتج.

    - لو فيه comparison_cards: بيطلع جدول مقارنة (مرشح / أبرز النقاط / المصدر).
    - لو فيه evidence بس: بيطلع جدول أدلة (ملف السيرة / المقطع الداعم).
    - بكل الحالات بيضيف نص السؤال والجواب الكامل تحت.
    """
    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    filename = f"candidate_report_{int(time.time())}.pdf"
    path = os.path.join(EXPORT_FOLDER, filename)

    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        title="CV Assistant Report",
    )
    story = []

    story.append(Paragraph("CV Assistant — Candidate Report", TITLE_STYLE))
    story.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · Recruiter workspace",
            META_STYLE,
        )
    )
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Question", SECTION_STYLE))
    story.append(Paragraph(question or "-", BODY_STYLE))

    if comparison_cards:
        story.append(Paragraph("Candidate Comparison", SECTION_STYLE))
        rows = [_header_row("Candidate", "Key Points", "Source CV")]
        for card in comparison_cards:
            points = card.get("points") or []
            points_text = "<br/>".join(f"• {pt}" for pt in points) if points else "-"
            rows.append(
                [
                    _cell(card.get("name")),
                    _cell(points_text),
                    _cell(card.get("source")),
                ]
            )
        table = Table(rows, colWidths=[3.3 * cm, 9.7 * cm, 3.5 * cm], repeatRows=1)
        table.setStyle(TABLE_STYLE)
        story.append(table)
        story.append(Spacer(1, 14))

    if evidence:
        story.append(Paragraph("Evidence from the CVs", SECTION_STYLE))
        rows = [_header_row("CV File", "Supporting Snippet")]
        for item in evidence:
            rows.append(
                [
                    _cell(item.get("source")),
                    _cell(item.get("snippet")),
                ]
            )
        table = Table(rows, colWidths=[4 * cm, 12.5 * cm], repeatRows=1)
        table.setStyle(TABLE_STYLE)
        story.append(table)
        story.append(Spacer(1, 14))

    story.append(Paragraph("Assistant's Answer", SECTION_STYLE))
    story.append(Paragraph((answer or "-").replace("\n", "<br/>"), BODY_STYLE))

    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Generated automatically by CV Assistant, based only on the uploaded CV documents.",
            META_STYLE,
        )
    )

    doc.build(story)
    return path
