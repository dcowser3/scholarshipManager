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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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


_TENDER_FONT_FAMILY = "Carlito"
_TENDER_FONTS_REGISTERED = False


def _register_tender_fonts() -> None:
    global _TENDER_FONTS_REGISTERED
    if _TENDER_FONTS_REGISTERED:
        return
    fonts_dir = resolve_backend_path("fonts")
    variants = {
        _TENDER_FONT_FAMILY: "Carlito-Regular.ttf",
        f"{_TENDER_FONT_FAMILY}-Bold": "Carlito-Bold.ttf",
        f"{_TENDER_FONT_FAMILY}-Italic": "Carlito-Italic.ttf",
        f"{_TENDER_FONT_FAMILY}-BoldItalic": "Carlito-BoldItalic.ttf",
    }
    for name, filename in variants.items():
        pdfmetrics.registerFont(TTFont(name, str(fonts_dir / filename)))
    pdfmetrics.registerFontFamily(
        _TENDER_FONT_FAMILY,
        normal=_TENDER_FONT_FAMILY,
        bold=f"{_TENDER_FONT_FAMILY}-Bold",
        italic=f"{_TENDER_FONT_FAMILY}-Italic",
        boldItalic=f"{_TENDER_FONT_FAMILY}-BoldItalic",
    )
    _TENDER_FONTS_REGISTERED = True
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
    _register_tender_fonts()
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "TenderBody",
        parent=styles["BodyText"],
        fontName="Carlito",
        fontSize=9.5,
        leading=11.5,
        spaceAfter=3,
    )
    tight = ParagraphStyle("TenderTight", parent=body, spaceAfter=0)
    body_just = ParagraphStyle("TenderBodyJust", parent=body, alignment=4)
    body_right = ParagraphStyle("TenderBodyRight", parent=body, alignment=2)
    body_bold = ParagraphStyle("TenderBodyBold", parent=body, fontName="Carlito-Bold")
    section_heading = ParagraphStyle(
        "TenderSectionHeading",
        parent=body_bold,
        fontSize=11,
        spaceAfter=8,
    )
    signature_label = ParagraphStyle(
        "TenderSigLabel",
        parent=body,
        fontSize=9,
        leading=11,
        spaceAfter=2,
    )
    signature_name = ParagraphStyle(
        "TenderSigName",
        parent=body,
        fontName="Times-Italic",
        fontSize=12,
        leading=14,
        spaceAfter=0,
    )
    fine = ParagraphStyle(
        "TenderFine",
        parent=body,
        fontSize=8.5,
        leading=10.5,
        spaceAfter=4,
    )
    p2_body = ParagraphStyle(
        "TenderP2Body",
        parent=body,
        fontSize=10,
        leading=13,
        spaceAfter=8,
    )
    p2_bullet = ParagraphStyle(
        "TenderP2Bullet",
        parent=p2_body,
        leftIndent=28,
        bulletIndent=12,
        spaceAfter=4,
    )
    accept_warning = ParagraphStyle(
        "TenderAcceptWarning",
        parent=fine,
        alignment=4,
        spaceBefore=6,
    )

    housing_on = "X" if (context.housing or "").upper() == "ON_CAMPUS" else "____"
    housing_off = "X" if (context.housing or "").upper() == "OFF_CAMPUS" else "____"
    exempt_mark = "X" if context.exempt else "____"
    award_year = display_tender_year(context.academic_year)
    cohort_label = context.cohort_display or "—"

    header_left = Paragraph(
        "<b>Tender of Athletic Grant-in-Aid</b><br/>"
        "<b>The University of Toledo</b><br/>"
        "2801 West Bancroft Street<br/>"
        "Toledo OH 43606-3390",
        tight,
    )
    header_center = Paragraph(f"<b>{award_year}</b>", tight)
    header_right = Paragraph(
        f"Cohort: {cohort_label}<br/>"
        f"Sport: {context.sport_name}<br/>"
        f"<b>Exempt:</b> {exempt_mark}",
        tight,
    )
    header_table = Table(
        [[header_left, header_center, header_right]],
        colWidths=[3.1 * inch, 1.4 * inch, 2.6 * inch],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (1, 0), 18),
                ("RIGHTPADDING", (2, 0), (2, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    fall_total = sum(context.adjusted_fall.values(), Decimal("0"))
    spring_total = sum(context.adjusted_spring.values(), Decimal("0"))

    award_label_overrides = {
        "tuition": "Tuition**",
        "general_fee": "General Fee**",
        "misc_fee": "Miscellaneous Fees*",
        "room": "Room**",
        "board": "Board**",
        "books": "Loan-of-Books",
    }

    award_rows: list[list[Paragraph]] = [
        [
            Paragraph("", body_bold),
            Paragraph("Fall Semester", body_bold),
            Paragraph("Spring Semester", body_bold),
        ]
    ]
    for label, field in zip(LINE_ITEM_LABELS, LINE_ITEM_FIELDS, strict=True):
        display_label = award_label_overrides.get(field, label)
        award_rows.append(
            [
                Paragraph(display_label, body),
                Paragraph(format_currency(context.adjusted_fall[field]), body_right),
                Paragraph(format_currency(context.adjusted_spring[field]), body_right),
            ]
        )
    award_rows.append(
        [
            Paragraph("<b>Total</b>", body_bold),
            Paragraph(f"<b>{format_currency(fall_total)}</b>", body_right),
            Paragraph(f"<b>{format_currency(spring_total)}</b>", body_right),
        ]
    )

    award_table = Table(award_rows, colWidths=[3.4 * inch, 1.85 * inch, 1.85 * inch])
    award_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe5f1")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dbe5f1")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    signature_table = Table(
        [
            [
                Paragraph(settings.tender_recommended_signatory, signature_name),
                Paragraph(settings.tender_approved_signatory, signature_name),
            ],
            [
                Paragraph("Recommended – Athletic Department", signature_label),
                Paragraph("Approved – Financial Aid Office", signature_label),
            ],
        ],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2),
                ("LINEBELOW", (0, 0), (0, 0), 0.75, colors.black),
                ("LINEBELOW", (1, 0), (1, 0), 0.75, colors.black),
            ]
        )
    )

    accept_table = Table(
        [
            [
                Paragraph("", body),
                Paragraph("", body),
            ],
            [
                Paragraph("Accepted – Recipient&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Date", fine),
                Paragraph(
                    "Accepted – Parent or Guardian&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Date<br/>"
                    "<i>(If student is under 18 years of age)</i>",
                    fine,
                ),
            ],
        ],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    accept_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 1), (0, 1), 0.75, colors.black),
                ("LINEABOVE", (1, 1), (1, 1), 0.75, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 14),
            ]
        )
    )

    period_start = display_date(context.term_start_date)
    period_end = display_date(context.term_end_date)

    story = [
        header_table,
        Spacer(1, 0.18 * inch),
        Paragraph(f"DATE: {context.submission_date.strftime('%-m/%-d/%Y')}", body_right),
        Spacer(1, 0.05 * inch),
        Paragraph(f"TO:&nbsp;&nbsp;&nbsp;&nbsp;{context.athlete_name}", body),
        Spacer(1, 0.08 * inch),
        Table(
            [
                [
                    [
                        Paragraph("Housing:", body),
                        Paragraph(
                            f"On-campus&nbsp;&nbsp;{housing_on}"
                            f"&nbsp;&nbsp;&nbsp;&nbsp;Off-campus&nbsp;&nbsp;{housing_off}",
                            body,
                        ),
                    ],
                    Paragraph(f"ROCKET #: {context.athlete_id}", body_right),
                ]
            ],
            colWidths=[4.0 * inch, 3.1 * inch],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            ),
        ),
        Spacer(1, 0.05 * inch),
        Paragraph(
            f"The benefits of this award are effective for the period beginning: "
            f"<u>{period_start}</u> and ending <u>{period_end}</u>.",
            body,
        ),
        Paragraph(
            "This is to advise you that the Financial Aid Committee of The University "
            "of Toledo has awarded you an athletic grant-in-aid as described below to "
            "assist with continuing your education, provided you meet the academic and "
            "athletic regulations of the Mid-American Conference and this institution. "
            "This award is made in accordance with the rules of this institution as well "
            "as applicable provision of the Constitution and Bylaws of the NCAA and "
            "Mid-American Conference. Your signature indicates that you accept these "
            "provisions and agree to abide by them.",
            body_just,
        ),
        Paragraph("A summary of applicable rules may be found on the reverse side of this form.", body),
        Paragraph("Your award includes the following:", body),
        award_table,
        Paragraph("*Dollar amounts are estimated and will be adjusted to actual costs", fine),
        Paragraph(
            "**Dollar amounts are estimated and will be adjusted as fees are finalized "
            "by the Board of Trustees.",
            fine,
        ),
        Paragraph(
            "The University of Toledo requires student-athletes to conform to all "
            "regulations applicable to all students as described in The University of "
            "Toledo Student Handbook and The University of Toledo Catalog.",
            body_just,
        ),
        Spacer(1, 0.12 * inch),
        signature_table,
        Spacer(1, 0.06 * inch),
        Paragraph(
            "I have read and understand the terms of my athletic grant-in-aid as "
            "indicated by my signature:",
            body,
        ),
        Spacer(1, 0.12 * inch),
        accept_table,
        Paragraph(
            "&middot; " * 60,
            ParagraphStyle("dotted", parent=fine, textColor=colors.black, spaceAfter=2),
        ),
        Paragraph(
            "IF YOU WISH TO ACCEPT THIS ATHLETIC GRANT-IN-AID, YOU ARE REQUIRED TO SIGN "
            "AND RETURN A COPY BY EMAIL (VIA DOCUSIGN) OR MAIL A COPY BACK TO THE "
            "ATHLETIC DEPARTMENT, THE UNIVERSITY OF TOLEDO, 2801 WEST BANCROFT, MS 302, "
            "TOLEDO, OH, 43606-3390. NO ATHLETIC GRANT-IN-AID WILL BE RELEASED TO THE "
            "STUDENT-ATHLETE WITHOUT RECEIPT OF A SIGNED COPY OF THIS FORM BY THIS "
            "UNIVERSITY. PLEASE KEEP A COPY FOR YOUR OWN FILES.",
            accept_warning,
        ),
        PageBreak(),
        Paragraph("Conditions for Athletic Financial Aid", section_heading),
        Paragraph("I understand that in order to qualify for this financial aid, I must:", p2_body),
        Paragraph(
            "Fulfill the admission requirements of The University of Toledo, and",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "Meet and maintain the eligibility requirements for athletic participation "
            "and financial aid established by the NCAA, the Mid-American Conference, "
            "and The University of Toledo.",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "NCAA regulations restrict the total amount of financial aid a student-athlete "
            "may receive. If I receive a state grant or other scholarship or financial aid, "
            "I will notify the Office of Student Financial Aid. Those funds may be used to "
            "replace a portion of my athletic grant-in-aid in order to meet NCAA and "
            "conference regulations.",
            p2_body,
        ),
        Paragraph(
            "I understand that any amount awarded for room or board expenses (on or off "
            "campus) and personal expenses are taxable according to the IRS and that I am "
            "responsible for reporting these scholarship dollars as taxable income, if I am "
            "required to file a tax return. (Please refer to IRS Publication 970 at "
            "www.irs.gov for more information.)",
            p2_body,
        ),
        Paragraph(
            "My financial aid will not be increased, reduced, or canceled during the period "
            "of this award on the basis of my athletic ability, performance, or contribution "
            "to my team's success, because of an injury or illness which prevents me from "
            "participating in athletics, or for any other athletic reason.",
            p2_body,
        ),
        Paragraph(
            "I understand that the amount of this award may be immediately reduced or "
            "canceled during the term of this award if:",
            p2_body,
        ),
        Paragraph(
            "I become ineligible for intercollegiate competition (e.g., less than full-time "
            "enrollment each term, academically ineligible, noncompliance with NCAA/MAC "
            "rules, or noncompliance with any eligibility requirements in NCAA Bylaw 14).",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "I fail to comply with the terms of agreement as outlined on my National Letter "
            "of Intent, MAC Letter of Intent, University of Toledo Tender of Athletic "
            "Grant-in-Aid, NCAA Student-Athlete Statement, individual team policies, "
            "training, work and competition requirements.",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "I engage in serious misconduct, which brings disciplinary action by The "
            "University of Toledo.",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "I voluntarily withdraw from my sport for personal reasons. Should I withdraw "
            "from my sport, my aid may be reduced or canceled on or after the date I "
            "withdraw, as specified by my coach on the Aid Cancellation Recommendation form.",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph("I also understand that this aid must be reduced or canceled if:", p2_body),
        Paragraph(
            "I violate NCAA amateurism regulations (Bylaw 12.1).",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "I accept money for playing in an athletic contest.",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "I receive other aid that causes me to exceed my individual limits.",
            p2_bullet,
            bulletText="•",
        ),
        Paragraph(
            "I also understand that my aid may be subject to non-renewal upon completion of "
            "my undergraduate degree/graduation.",
            p2_body,
        ),
        Paragraph(
            "If your athletically related financial aid is reduced or canceled for any "
            "reason, you will be notified in writing. You will be provided an opportunity to "
            "appeal before a committee outside of the Athletics Department. Procedures and a "
            "deadline by which you must request an appeal will be provided to you.",
            p2_body,
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
