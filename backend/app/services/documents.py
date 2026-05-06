from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import resolve_backend_path, settings
from app.models.core import Sport, Term
from app.models.roster import AidRecord, RosterMembership
from app.models.submission import Adjustment
from app.models.user import User

LINE_ITEM_FIELDS = [
    "oos_tuition",
    "tuition",
    "general_fee",
    "misc_fee",
    "room",
    "board",
    "books",
    "personal_expenses",
]

LINE_ITEM_LABELS = [
    "Out-of-State Surcharge",
    "Tuition",
    "General Fee",
    "Misc. Fees",
    "Room",
    "Board",
    "Books",
    "Personal Expenses",
]

CURRENT_ROW_START = 10
ADJUSTED_ROW_START = 22


@dataclass
class GeneratedArtifact:
    kind: str
    athlete_id: str
    filename: str
    path: Path


@dataclass
class AdjustmentDocumentContext:
    athlete_id: str
    athlete_name: str
    sport_name: str
    academic_year: str
    cohort_display: str | None
    exempt: bool | None
    housing: str | None
    submission_date: date
    submitted_by_name: str | None
    reason: str | None
    current_fall: dict[str, Decimal]
    current_spring: dict[str, Decimal]
    adjusted_fall: dict[str, Decimal]
    adjusted_spring: dict[str, Decimal]
    term_start_date: date | None
    term_end_date: date | None


def generate_adjustment_artifacts(
    *,
    db: Session,
    submission_id: UUID,
    adjustments: list[Adjustment],
    submitted_by: User,
    comment: str | None,
) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    for adjustment in adjustments:
        context = build_adjustment_document_context(
            db=db,
            adjustment=adjustment,
            submitted_by=submitted_by,
            reason=comment,
        )
        athlete_slug = slugify_filename(context.athlete_name)
        workbook_name = f"{context.athlete_id}_{athlete_slug}_Adjustment.xlsx"
        pdf_name = f"{context.athlete_id}_{athlete_slug}_Tender.pdf"

        submission_dir = ensure_submission_storage_dir(submission_id)
        workbook_path = submission_dir / workbook_name
        pdf_path = submission_dir / pdf_name

        build_adjustment_workbook(context, workbook_path)
        build_tender_pdf(context, pdf_path, submission_id)

        artifacts.append(
            GeneratedArtifact(
                kind="ADJUSTMENT_FORM",
                athlete_id=context.athlete_id,
                filename=workbook_name,
                path=workbook_path,
            )
        )
        artifacts.append(
            GeneratedArtifact(
                kind="TENDER",
                athlete_id=context.athlete_id,
                filename=pdf_name,
                path=pdf_path,
            )
        )
    return artifacts


def ensure_submission_storage_dir(submission_id: UUID) -> Path:
    root = resolve_backend_path(settings.storage_root)
    path = root / "submissions" / str(submission_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_adjustment_document_context(
    *,
    db: Session,
    adjustment: Adjustment,
    submitted_by: User,
    reason: str | None,
) -> AdjustmentDocumentContext:
    membership = db.get(RosterMembership, adjustment.membership_id)
    if membership is None:
        raise RuntimeError(f"Missing membership for adjustment {adjustment.id}")

    term = db.get(Term, adjustment.term_id)
    sport = db.get(Sport, membership.sport_id)
    if term is None or sport is None:
        raise RuntimeError(f"Missing term or sport for adjustment {adjustment.id}")

    athlete_name = f"{membership.athlete.first_name} {membership.athlete.last_name}"
    same_year_memberships = db.scalars(
        select(RosterMembership)
        .join(Term, Term.id == RosterMembership.term_id)
        .where(
            RosterMembership.athlete_id == membership.athlete_id,
            RosterMembership.sport_id == membership.sport_id,
            Term.academic_year == term.academic_year,
        )
    ).all()

    membership_by_semester: dict[str, RosterMembership] = {}
    for other in same_year_memberships:
        other_term = db.get(Term, other.term_id)
        if other_term is not None:
            membership_by_semester[other_term.semester] = other

    current_fall = _line_items_for_membership(db, membership_by_semester.get("FALL"))
    current_spring = _line_items_for_membership(db, membership_by_semester.get("SPRING"))
    adjusted_fall = dict(current_fall)
    adjusted_spring = dict(current_spring)

    after_values = _normalize_values(adjustment.after_values or {})
    if term.semester == "FALL":
        adjusted_fall = _merge_line_items(current_fall, after_values)
    else:
        adjusted_spring = _merge_line_items(current_spring, after_values)

    year_terms = db.scalars(select(Term).where(Term.academic_year == term.academic_year)).all()
    start_dates = [item.start_date for item in year_terms if item.start_date]
    end_dates = [item.end_date for item in year_terms if item.end_date]

    return AdjustmentDocumentContext(
        athlete_id=membership.athlete_id,
        athlete_name=athlete_name,
        sport_name=sport.display_name,
        academic_year=term.academic_year,
        cohort_display=membership.cohort_display,
        exempt=membership.exempt,
        housing=membership.housing,
        submission_date=datetime.now(UTC).date(),
        submitted_by_name=submitted_by.display_name or submitted_by.email,
        reason=reason,
        current_fall=current_fall,
        current_spring=current_spring,
        adjusted_fall=adjusted_fall,
        adjusted_spring=adjusted_spring,
        term_start_date=min(start_dates) if start_dates else None,
        term_end_date=max(end_dates) if end_dates else None,
    )


def build_adjustment_workbook(context: AdjustmentDocumentContext, output_path: Path) -> None:
    workbook = load_workbook(resolve_backend_path(settings.adjustment_template_path))
    sheet = workbook["Sheet1"]

    sheet["B2"] = display_adjustment_year(context.academic_year)
    sheet["F3"] = context.submission_date
    sheet["B4"] = context.athlete_name
    sheet["C4"] = context.athlete_id
    sheet["F4"] = context.cohort_display or ""
    sheet["B6"] = context.sport_name
    sheet["D6"] = display_housing(context.housing)
    sheet["F6"] = f"Exempt ({'Yes' if context.exempt else 'No'})"

    for index, field in enumerate(LINE_ITEM_FIELDS):
        current_row = CURRENT_ROW_START + index
        adjusted_row = ADJUSTED_ROW_START + index
        sheet[f"D{current_row}"] = float(context.current_fall[field])
        sheet[f"E{current_row}"] = float(context.current_spring[field])
        sheet[f"D{adjusted_row}"] = float(context.adjusted_fall[field])
        sheet[f"E{adjusted_row}"] = float(context.adjusted_spring[field])

    sheet["A33"] = context.reason or "Coach-submitted scholarship adjustment."
    workbook.save(output_path)


def build_tender_pdf(
    context: AdjustmentDocumentContext,
    output_path: Path,
    submission_id: UUID,
) -> None:
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TenderTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#13233f"),
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "TenderBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        spaceAfter=6,
    )
    small = ParagraphStyle(
        "TenderSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#39465a"),
        spaceAfter=4,
    )

    table_rows = [
        [
            Paragraph("<b>Line Item</b>", body),
            Paragraph("<b>Fall</b>", body),
            Paragraph("<b>Spring</b>", body),
        ]
    ]
    for label, field in zip(LINE_ITEM_LABELS, LINE_ITEM_FIELDS, strict=True):
        table_rows.append(
            [
                Paragraph(label, body),
                Paragraph(format_currency(context.adjusted_fall[field]), body),
                Paragraph(format_currency(context.adjusted_spring[field]), body),
            ]
        )

    story = [
        Paragraph("University of Toledo Athletics", title),
        Paragraph(
            f"Tender of Athletic Grant-in-Aid {display_tender_year(context.academic_year)}",
            title,
        ),
        Paragraph(
            (
                f"<b>Student-athlete:</b> {context.athlete_name}<br/>"
                f"<b>Rocket #:</b> {context.athlete_id}<br/>"
                f"<b>Sport:</b> {context.sport_name}<br/>"
                f"<b>Cohort:</b> {context.cohort_display or 'Unassigned'}<br/>"
                f"<b>Housing:</b> {display_housing(context.housing) or 'Not specified'}<br/>"
                f"<b>Exempt:</b> {'Yes' if context.exempt else 'No'}"
            ),
            body,
        ),
        Paragraph(
            (
                f"<b>Effective period:</b> {display_date(context.term_start_date)} to "
                f"{display_date(context.term_end_date)}"
            ),
            body,
        ),
        Paragraph(
            (
                "This MVP tender is generated from the coach-submitted adjustment "
                "workflow for review and testing."
            ),
            body,
        ),
        _styled_table(table_rows),
        Spacer(1, 0.2 * inch),
        Paragraph(
            f"<b>Recommended - Athletic Department:</b> {settings.tender_recommended_signatory}",
            body,
        ),
        Paragraph(
            f"<b>Approved - Financial Aid Office:</b> {settings.tender_approved_signatory}",
            body,
        ),
        Paragraph(
            "Return a signed copy through the department's signature workflow after review.",
            body,
        ),
        Spacer(1, 0.2 * inch),
        Paragraph(
            f"Submission trace: {submission_id}",
            small,
        ),
        PageBreak(),
        Paragraph("Conditions for Athletic Financial Aid", title),
        Paragraph(
            (
                "This MVP attachment includes a simplified conditions page for "
                "testing. Final production text should match the university-approved "
                "tender language."
            ),
            body,
        ),
        Paragraph(
            (
                "1. Aid is subject to institutional, conference, and NCAA rules. "
                "2. Adjustments may require additional documentation depending on "
                "circumstance. 3. Amounts may change if fees or charges are finalized "
                "after the tender is generated. 4. The student-athlete is responsible "
                "for reviewing all related university policies and deadlines."
            ),
            body,
        ),
        Paragraph(
            "This document was generated automatically by the scholarship management MVP.",
            small,
        ),
    ]
    document.build(story)


def _styled_table(rows: list[list[Paragraph]]) -> Table:
    table = Table(rows, colWidths=[3.55 * inch, 1.15 * inch, 1.15 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#13233f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b8c1d1")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _line_items_for_membership(
    db: Session,
    membership: RosterMembership | None,
) -> dict[str, Decimal]:
    zeroes = {field: Decimal("0.00") for field in LINE_ITEM_FIELDS}
    if membership is None:
        return zeroes
    aid_record = db.scalar(select(AidRecord).where(AidRecord.membership_id == membership.id))
    if aid_record is None:
        return zeroes
    return {field: getattr(aid_record, field) for field in LINE_ITEM_FIELDS}


def _normalize_values(values: dict[str, str]) -> dict[str, Decimal]:
    return {
        field: Decimal(str(values.get(field, "0.00"))).quantize(Decimal("0.01"))
        for field in LINE_ITEM_FIELDS
    }


def _merge_line_items(
    baseline: dict[str, Decimal],
    overrides: dict[str, Decimal],
) -> dict[str, Decimal]:
    merged = dict(baseline)
    merged.update(overrides)
    return merged


def format_currency(value: Decimal) -> str:
    return f"${value:,.2f}"


def display_adjustment_year(academic_year: str) -> str:
    start, end = academic_year.split("-")
    return f"20{start}-{end}"


def display_tender_year(academic_year: str) -> str:
    start, end = academic_year.split("-")
    return f"20{start}-20{end}"


def display_housing(value: str | None) -> str:
    if not value:
        return ""
    mapping = {
        "ON_CAMPUS": "On-Campus",
        "OFF_CAMPUS": "Off-Campus",
    }
    return mapping.get(value, value.replace("_", " ").title())


def display_date(value: date | None) -> str:
    if not value:
        return "TBD"
    return value.strftime("%m/%d/%Y")


def slugify_filename(value: str) -> str:
    return "_".join(part for part in value.replace("'", "").split() if part)
