from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.core import Sport, Term
from app.models.roster import AidRecord, RosterMembership
from app.models.submission import Adjustment, EmailIntake
from app.services.budgets import SportBudgetSummary, get_sport_budget_summary
from app.services.config_values import get_allowed_senders, get_sender_sport_map
from app.services.email_text import (
    classify_confirmation_reply,
    extract_message_text,
    normalize_reply_text,
    strip_quoted_reply_text,
)
from app.services.emailer import send_email_with_attachments, send_plain_text_email
from app.services.importer import get_active_import_academic_year
from app.services.openai_email_parser import parse_adjustment_email_with_openai
from app.services.submission_workflow import (
    AID_EDITABLE_FIELDS,
    PreparedSubmissionChange,
    create_submission_with_adjustments,
    generate_submission_artifacts,
    persist_generated_artifacts,
    serialize_editable_values,
)

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "athletic_aid_total": "Athletic Aid Total",
    "oos_tuition": "Out-of-State Tuition",
    "tuition": "Tuition",
    "general_fee": "General Fee",
    "misc_fee": "Misc. Fee",
    "room": "Room",
    "board": "Board",
    "books": "Books",
    "personal_expenses": "Personal Expenses",
    "oos_resource": "OOS Resource",
}


@dataclass
class ConfirmationTableRow:
    athlete_name: str
    field: str
    term: str
    before: Decimal
    after: Decimal
    delta: Decimal
    note: str | None = None


@dataclass
class ParsedEmailPlan:
    sport: Sport
    academic_year: str
    summary: str
    issues: list[str]
    rows: list[ConfirmationTableRow]
    changes: list[PreparedSubmissionChange]
    athlete_names: list[str]
    budget_summary: SportBudgetSummary


def process_inbound_email_message(db: Session, raw_message: bytes) -> None:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    sender_email = parseaddr(message.get("From", ""))[1].lower().strip()
    inbound_message_id = _normalize_message_id(message.get("Message-ID"))
    in_reply_to = _normalize_message_id(message.get("In-Reply-To"))
    subject = message.get("Subject", "").strip()
    raw_body = extract_message_text(message)
    cleaned_body = strip_quoted_reply_text(raw_body)

    if inbound_message_id:
        existing = db.scalar(
            select(EmailIntake).where(EmailIntake.inbound_message_id == inbound_message_id)
        )
        if existing is not None:
            return

    intake = EmailIntake(
        received_at=datetime.now(UTC),
        sender_email=sender_email or None,
        inbound_message_id=inbound_message_id,
        raw_body=raw_body,
        state="RECEIVED",
        parsed_payload={
            "subject": subject,
            "in_reply_to": in_reply_to,
            "cleaned_body": cleaned_body,
        },
    )
    db.add(intake)
    db.flush()

    if in_reply_to:
        handled = _handle_possible_confirmation_reply(
            db,
            intake=intake,
            sender_email=sender_email,
            in_reply_to=in_reply_to,
            cleaned_body=cleaned_body,
        )
        if handled:
            return

    allowed_senders = get_allowed_senders(db)
    if sender_email not in allowed_senders:
        intake.state = "IGNORED_SENDER"
        logger.info("Ignoring inbound email from non-whitelisted sender %s", sender_email)
        return

    sender_sport_map = get_sender_sport_map(db)
    configured_sport_name = sender_sport_map.get(sender_email)
    if not configured_sport_name:
        intake.state = "PARSE_FAILED"
        intake.parsed_payload = {
            **(intake.parsed_payload or {}),
            "issues": [f"No sport mapping is configured for sender {sender_email}."],
        }
        return

    sport = _find_sport_by_name(db, configured_sport_name)
    if sport is None:
        intake.state = "PARSE_FAILED"
        intake.parsed_payload = {
            **(intake.parsed_payload or {}),
            "issues": [f"Configured sport '{configured_sport_name}' was not found."],
        }
        return

    plan = _build_plan_for_new_request(
        db,
        intake=intake,
        sport=sport,
        cleaned_body=cleaned_body,
    )
    confirmation_subject = _build_confirmation_subject(
        subject=subject,
        sport_name=sport.display_name,
    )
    confirmation_body = _build_confirmation_email_body(plan)
    confirmation_message_id = send_plain_text_email(
        recipient_email=sender_email,
        subject=confirmation_subject,
        body=confirmation_body,
        html_body=_build_confirmation_email_html(plan),
        in_reply_to=inbound_message_id,
        references=[inbound_message_id] if inbound_message_id else None,
    )
    intake.confirmation_message_id = confirmation_message_id
    intake.state = "AWAITING_CONFIRMATION"
    intake.parsed_payload = _serialize_plan(plan, subject=subject)


def _build_plan_for_new_request(
    db: Session,
    *,
    intake: EmailIntake,
    sport: Sport,
    cleaned_body: str,
) -> ParsedEmailPlan:
    academic_year = get_active_import_academic_year(db)
    roster_memberships = list(
        db.scalars(
            select(RosterMembership)
            .join(Term, Term.id == RosterMembership.term_id)
            .options(
                joinedload(RosterMembership.athlete),
                joinedload(RosterMembership.term),
                joinedload(RosterMembership.aid_record),
            )
            .where(
                RosterMembership.sport_id == sport.id,
                Term.academic_year == academic_year,
            )
        )
    )
    parsed = parse_adjustment_email_with_openai(
        db,
        sport=sport,
        email_body=cleaned_body,
        roster_memberships=roster_memberships,
    )
    return _build_plan_from_parsed_result(
        db,
        intake=intake,
        sport=sport,
        academic_year=academic_year,
        roster_memberships=roster_memberships,
        parsed=parsed,
    )


def _build_plan_from_parsed_result(
    db: Session,
    *,
    intake: EmailIntake,
    sport: Sport,
    academic_year: str,
    roster_memberships: list[RosterMembership],
    parsed: dict[str, Any],
) -> ParsedEmailPlan:
    issues = [str(item) for item in parsed.get("issues", []) if str(item).strip()]
    if parsed.get("overall_confidence") in {"low", "medium"}:
        issues.append(f"Parser confidence: {parsed.get('overall_confidence')}.")

    memberships_by_key: dict[tuple[str, str], RosterMembership] = {}
    aid_by_membership: dict[int, AidRecord] = {}
    pending_by_membership: dict[int, Adjustment] = {}
    full_name_to_athlete_ids: dict[str, set[str]] = {}

    for membership in roster_memberships:
        term = membership.term
        if term is not None:
            memberships_by_key[(membership.athlete_id, term.semester)] = membership
        if membership.athlete is not None:
            name = _normalize_name(
                f"{membership.athlete.first_name} {membership.athlete.last_name}"
            )
            full_name_to_athlete_ids.setdefault(name, set()).add(membership.athlete_id)
        if membership.aid_record is None:
            aid_record = db.scalar(
                select(AidRecord).where(AidRecord.membership_id == membership.id)
            )
            if aid_record is not None:
                aid_by_membership[membership.id] = aid_record
        else:
            aid_by_membership[membership.id] = membership.aid_record

    if aid_by_membership:
        adjustments = db.scalars(
            select(Adjustment)
            .where(
                Adjustment.membership_id.in_(aid_by_membership.keys()),
                Adjustment.state == "SUBMITTED",
            )
            .order_by(Adjustment.created_at.desc())
        ).all()
        for adjustment in adjustments:
            pending_by_membership.setdefault(adjustment.membership_id, adjustment)

    after_values_map: dict[int, dict[str, str]] = {}
    total_deltas: dict[int, Decimal] = {}
    explicit_total_memberships: set[int] = set()
    rows: list[ConfirmationTableRow] = []
    athlete_names: list[str] = []

    for raw_change in parsed.get("changes", []):
        change_issues = _collect_change_issues(raw_change)
        if raw_change.get("confidence") in {"low", "medium"}:
            source_text = raw_change.get("source_text", "")
            fallback_label = raw_change.get("athlete_name", "requested change")
            change_issues.append(
                f"Low-confidence parse for '{str(source_text).strip() or fallback_label}'."
            )

        athlete_id = raw_change.get("rocket_id")
        athlete_name = str(raw_change.get("athlete_name") or "").strip()
        if not athlete_id and athlete_name:
            athlete_ids = full_name_to_athlete_ids.get(_normalize_name(athlete_name), set())
            if len(athlete_ids) == 1:
                athlete_id = next(iter(athlete_ids))
            elif len(athlete_ids) > 1:
                change_issues.append(f"'{athlete_name}' matches multiple athletes.")
        if not athlete_id:
            issues.extend(
                change_issues
                or [f"Could not identify athlete for '{athlete_name or 'request'}'."]
            )
            continue

        term = str(raw_change.get("term") or "").upper()
        field = str(raw_change.get("field") or "").strip()
        operation = str(raw_change.get("operation") or "").upper()
        amount_text = raw_change.get("amount")
        if not term or term not in {"FALL", "SPRING"}:
            change_issues.append(f"Could not determine term for {athlete_name or athlete_id}.")
        if field not in AID_EDITABLE_FIELDS:
            change_issues.append(f"Unsupported field '{field}' for {athlete_name or athlete_id}.")
        if operation not in {"SET", "DELTA"}:
            change_issues.append(
                f"Could not determine change type for {athlete_name or athlete_id}."
            )
        if amount_text in {None, ""}:
            change_issues.append(f"Could not determine amount for {athlete_name or athlete_id}.")
        if change_issues:
            issues.extend(change_issues)
            continue

        membership = memberships_by_key.get((athlete_id, term))
        if membership is None:
            issues.append(
                f"No {term.lower()} roster record found for {athlete_name or athlete_id}."
            )
            continue
        aid_record = aid_by_membership.get(membership.id)
        if aid_record is None:
            issues.append(
                f"No aid record found for {athlete_name or athlete_id} in {term.lower()}."
            )
            continue

        if membership.athlete is not None:
            display_name = f"{membership.athlete.first_name} {membership.athlete.last_name}"
            if display_name not in athlete_names:
                athlete_names.append(display_name)
        else:
            display_name = athlete_name or athlete_id

        after_values = after_values_map.setdefault(
            membership.id,
            serialize_editable_values(aid_record),
        )
        before = Decimal(after_values[field]).quantize(Decimal("0.01"))
        amount = Decimal(str(amount_text)).quantize(Decimal("0.01"))
        after = amount if operation == "SET" else before + amount
        after = after.quantize(Decimal("0.01"))
        delta = (after - before).quantize(Decimal("0.01"))
        after_values[field] = str(after)

        if field == "athletic_aid_total":
            explicit_total_memberships.add(membership.id)
        elif membership.id not in explicit_total_memberships:
            total_deltas[membership.id] = total_deltas.get(membership.id, Decimal("0.00")) + delta

        note = None
        pending_adjustment = pending_by_membership.get(membership.id)
        if pending_adjustment and _field_has_pending_value(pending_adjustment, field):
            note = "already pending"

        rows.append(
            ConfirmationTableRow(
                athlete_name=display_name,
                field=field,
                term=term,
                before=before,
                after=after,
                delta=delta,
                note=note,
            )
        )

    for membership_id, total_delta in total_deltas.items():
        if total_delta == Decimal("0.00"):
            continue
        membership = next(item for item in roster_memberships if item.id == membership_id)
        aid_record = aid_by_membership[membership_id]
        after_values = after_values_map[membership_id]
        before_total = Decimal(
            serialize_editable_values(aid_record)["athletic_aid_total"]
        ).quantize(Decimal("0.01"))
        after_total = (before_total + total_delta).quantize(Decimal("0.01"))
        after_values["athletic_aid_total"] = str(after_total)
        rows.append(
            ConfirmationTableRow(
                athlete_name=f"{membership.athlete.first_name} {membership.athlete.last_name}"
                if membership.athlete
                else membership.athlete_id,
                field="athletic_aid_total",
                term=membership.term.semester if membership.term else "UNKNOWN",
                before=before_total,
                after=after_total,
                delta=total_delta,
                note="auto-adjusted total",
            )
        )

    changes = [
        PreparedSubmissionChange(membership_id=membership_id, after_values=after_values)
        for membership_id, after_values in after_values_map.items()
        if _after_values_changed(after_values, aid_by_membership[membership_id])
    ]
    overrides = {
        change.membership_id: Decimal(change.after_values["athletic_aid_total"]).quantize(
            Decimal("0.01")
        )
        for change in changes
    }
    budget_summary = get_sport_budget_summary(
        db,
        sport_id=sport.id,
        academic_year=academic_year,
        athletic_aid_overrides=overrides,
    )

    summary = str(parsed.get("summary") or "").strip() or (
        intake.raw_body.strip() if intake.raw_body else "Requested scholarship adjustment."
    )
    if not changes:
        issues.append("No actionable changes were extracted from the email.")

    return ParsedEmailPlan(
        sport=sport,
        academic_year=academic_year,
        summary=summary,
        issues=_dedupe_preserve_order(issues),
        rows=rows,
        changes=changes,
        athlete_names=athlete_names,
        budget_summary=budget_summary,
    )


def _handle_possible_confirmation_reply(
    db: Session,
    *,
    intake: EmailIntake,
    sender_email: str,
    in_reply_to: str,
    cleaned_body: str,
) -> bool:
    original = db.scalar(
        select(EmailIntake).where(
            EmailIntake.confirmation_message_id == in_reply_to,
            EmailIntake.state == "AWAITING_CONFIRMATION",
        )
    )
    if original is None:
        return False
    if original.sender_email != sender_email:
        intake.state = "IGNORED_REPLY"
        intake.parsed_payload = {
            **(intake.parsed_payload or {}),
            "issues": ["Reply sender did not match the original sender."],
        }
        return True

    action = classify_confirmation_reply(cleaned_body)
    intake.parsed_payload = {
        **(intake.parsed_payload or {}),
        "normalized_reply": normalize_reply_text(cleaned_body),
        "matched_request_id": str(original.id),
    }

    if action is None:
        clarification_subject = _build_confirmation_subject(
            subject=str((original.parsed_payload or {}).get("subject") or ""),
            sport_name="",
        )
        references = [
            value
            for value in [
                original.inbound_message_id,
                original.confirmation_message_id,
                in_reply_to,
            ]
            if value
        ]
        new_message_id = send_plain_text_email(
            recipient_email=sender_email,
            subject=clarification_subject,
            body=(
                "I couldn't tell whether that reply was a confirmation or a cancellation.\n\n"
                "Reply YES to confirm, or NO to cancel.\n"
                "To change anything, send a new email."
            ),
            in_reply_to=in_reply_to,
            references=references,
        )
        original.confirmation_message_id = new_message_id
        intake.state = "INVALID_REPLY"
        return True

    if action == "REJECT":
        original.state = "CANCELLED"
        intake.state = "CANCELLED"
        send_plain_text_email(
            recipient_email=sender_email,
            subject="Aid change request cancelled",
            body=(
                "Your email request has been cancelled. "
                "If you want different numbers, send a new email."
            ),
            in_reply_to=in_reply_to,
            references=[in_reply_to],
        )
        return True

    try:
        _complete_confirmed_request(
            db,
            original=original,
            reply_intake=intake,
            in_reply_to=in_reply_to,
        )
    except Exception as caught:
        logger.exception("Failed to complete confirmed email request %s", original.id)
        original.state = "PARSE_FAILED"
        intake.state = "PARSE_FAILED"
        intake.parsed_payload = {
            **(intake.parsed_payload or {}),
            "issues": [str(caught)],
        }
        send_plain_text_email(
            recipient_email=sender_email,
            subject="Aid change request could not be completed",
            body=(
                "The request was confirmed, but the system could not finish the document run.\n\n"
                f"Details: {caught}"
            ),
            in_reply_to=in_reply_to,
            references=[in_reply_to],
        )
        return True

    return True


def _complete_confirmed_request(
    db: Session,
    *,
    original: EmailIntake,
    reply_intake: EmailIntake,
    in_reply_to: str,
) -> None:
    payload = original.parsed_payload or {}
    sport = db.get(Sport, payload.get("sport_id"))
    if sport is None:
        raise ValueError("Original email request is missing its sport mapping.")

    changes = [
        PreparedSubmissionChange(
            membership_id=int(change["membership_id"]),
            after_values={field: str(value) for field, value in change["after_values"].items()},
        )
        for change in payload.get("changes", [])
    ]
    if not changes:
        raise ValueError("There are no actionable changes to confirm for this request.")

    original.state = "CONFIRMED"
    workflow = create_submission_with_adjustments(
        db=db,
        sport_id=sport.id,
        submitted_by_user_id=None,
        source="EMAIL",
        comment=(payload.get("summary") or original.raw_body or "").strip() or None,
        changes=changes,
        intake_id=original.id,
    )
    if not original.sender_email:
        raise ValueError("Original sender email is missing on the intake record.")

    generated_artifacts = generate_submission_artifacts(
        db=db,
        submission=workflow.submission,
        adjustments=workflow.adjustments,
        submitted_by_name=original.sender_email,
        comment=workflow.submission.comment,
    )
    thread_subject = _build_confirmation_subject(
        subject=str(payload.get("subject") or ""),
        sport_name=str(payload.get("sport_name") or ""),
    )
    thread_references = [
        value
        for value in [
            original.inbound_message_id,
            original.confirmation_message_id,
            reply_intake.inbound_message_id,
        ]
        if value
    ]
    send_email_with_attachments(
        recipient_email=original.sender_email,
        subject=thread_subject,
        body=_build_generated_docs_body(original=original, payload=payload),
        attachments=[artifact.path for artifact in generated_artifacts],
        in_reply_to=reply_intake.inbound_message_id,
        references=thread_references,
    )
    persist_generated_artifacts(
        db=db,
        submission_id=workflow.submission.id,
        recipient_email=original.sender_email,
        generated_artifacts=generated_artifacts,
    )
    original.submission_id = workflow.submission.id
    original.state = "COMPLETED"
    reply_intake.state = "CONFIRMED"


def _serialize_plan(plan: ParsedEmailPlan, *, subject: str) -> dict[str, Any]:
    return {
        "subject": subject,
        "sport_id": plan.sport.id,
        "sport_name": plan.sport.display_name,
        "academic_year": plan.academic_year,
        "summary": plan.summary,
        "issues": plan.issues,
        "changes": [
            {
                "membership_id": change.membership_id,
                "after_values": change.after_values,
            }
            for change in plan.changes
        ],
        "rows": [
            {
                "athlete_name": row.athlete_name,
                "field": row.field,
                "term": row.term,
                "before": str(row.before),
                "after": str(row.after),
                "delta": str(row.delta),
                "note": row.note,
            }
            for row in plan.rows
        ],
        "athlete_names": plan.athlete_names,
        "budget": {
            "budget_amount": str(plan.budget_summary.budget_amount),
            "allocated_amount": str(plan.budget_summary.allocated_amount),
            "percent_used": str(plan.budget_summary.percent_used),
        },
    }


def _build_confirmation_subject(*, subject: str, sport_name: str) -> str:
    base = subject or f"{sport_name} aid change request"
    if base.lower().startswith("re:"):
        return base
    return f"Re: {base}"


def _build_confirmation_email_body(plan: ParsedEmailPlan) -> str:
    lines = [
        "This is the demo confirmation for the requested scholarship adjustment.",
        "",
        "What I understood:",
        plan.summary,
        "",
        "Numeric breakdown:",
        _format_confirmation_table(plan.rows),
    ]
    if plan.changes:
        lines.extend(
            [
                "",
                (
                    f"After change: {_format_percent(plan.budget_summary.percent_used)} of budget "
                    f"({ _format_currency(plan.budget_summary.allocated_amount) } allocated "
                    f"of { _format_currency(plan.budget_summary.budget_amount) })"
                ),
            ]
        )
    if plan.issues:
        lines.extend(
            [
                "",
                "Flags to review before confirming:",
                *[f"- {issue}" for issue in plan.issues],
            ]
        )
    lines.extend(
        [
            "",
            "Reply YES to confirm, or NO to cancel.",
            "To change anything, send a new email.",
        ]
    )
    return "\n".join(lines)


def _build_confirmation_email_html(plan: ParsedEmailPlan) -> str:
    issue_block = ""
    if plan.issues:
        issue_items = "".join(f"<li>{html.escape(issue)}</li>" for issue in plan.issues)
        issue_block = (
            "<h3 style=\"margin:24px 0 8px;font-size:16px;\">Flags to review before confirming</h3>"
            f"<ul style=\"margin:0 0 0 18px;padding:0;color:#374151;\">{issue_items}</ul>"
        )

    if plan.rows:
        row_html = "".join(
            (
                "<tr>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;\">{html.escape(row.athlete_name)}</td>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;\">{html.escape(FIELD_LABELS.get(row.field, row.field))}</td>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;\">{html.escape(row.term)}</td>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;white-space:nowrap;\">{html.escape(_format_currency(row.before))}</td>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;white-space:nowrap;\">{html.escape(_format_currency(row.after))}</td>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;white-space:nowrap;\">{html.escape(_format_signed_currency(row.delta))}</td>"
                f"<td style=\"padding:10px 12px;border-bottom:1px solid #e5e7eb;white-space:nowrap;\">{html.escape(row.note or '')}</td>"
                "</tr>"
            )
            for row in plan.rows
        )
        table_html = (
            "<div style=\"overflow-x:auto;\">"
            "<table style=\"border-collapse:collapse;width:100%;min-width:760px;font-family:Arial,sans-serif;font-size:15px;\">"
            "<thead>"
            "<tr style=\"background:#f8fafc;color:#111827;\">"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:left;\">Athlete</th>"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:left;\">Field</th>"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:left;\">Term</th>"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:right;\">Before</th>"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:right;\">After</th>"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:right;\">Delta</th>"
            "<th style=\"padding:10px 12px;border-bottom:2px solid #d1d5db;text-align:left;\">Note</th>"
            "</tr>"
            "</thead>"
            f"<tbody>{row_html}</tbody>"
            "</table>"
            "</div>"
        )
    else:
        table_html = "<p style=\"margin:0;color:#374151;\">No actionable numeric changes were extracted.</p>"

    budget_html = ""
    if plan.changes:
        budget_html = (
            f"<p style=\"margin:24px 0 0;font-size:16px;\"><strong>After change:</strong> "
            f"{html.escape(_format_percent(plan.budget_summary.percent_used))} of budget "
            f"({html.escape(_format_currency(plan.budget_summary.allocated_amount))} allocated "
            f"of {html.escape(_format_currency(plan.budget_summary.budget_amount))})</p>"
        )

    return (
        "<html><body style=\"margin:0;padding:24px;font-family:Arial,sans-serif;color:#111827;line-height:1.5;\">"
        "<div style=\"max-width:920px;\">"
        "<p style=\"margin:0 0 24px;\">This is the demo confirmation for the requested scholarship adjustment.</p>"
        "<h3 style=\"margin:0 0 8px;font-size:16px;\">What I understood</h3>"
        f"<p style=\"margin:0 0 24px;\">{html.escape(plan.summary)}</p>"
        "<h3 style=\"margin:0 0 12px;font-size:16px;\">Numeric breakdown</h3>"
        f"{table_html}"
        f"{budget_html}"
        f"{issue_block}"
        "<p style=\"margin:24px 0 0;\"><strong>Reply YES</strong> to confirm, or <strong>NO</strong> to cancel.<br>"
        "To change anything, send a new email.</p>"
        "</div></body></html>"
    )


def _format_confirmation_table(rows: list[ConfirmationTableRow]) -> str:
    if not rows:
        return "No actionable numeric changes were extracted."
    header = (
        f"{'Athlete':<22} {'Field':<21} {'Term':<8} "
        f"{'Before':>10} {'After':>10} {'Delta':>10}  Note"
    )
    divider = "-" * len(header)
    formatted_rows = [header, divider]
    for row in rows:
        formatted_rows.append(
            f"{row.athlete_name[:22]:<22} "
            f"{FIELD_LABELS.get(row.field, row.field)[:21]:<21} "
            f"{row.term:<8} "
            f"{_format_currency(row.before):>10} "
            f"{_format_currency(row.after):>10} "
            f"{_format_signed_currency(row.delta):>10}  "
            f"{row.note or ''}"
        )
    return "\n".join(formatted_rows)


def _build_generated_docs_subject(athlete_names: list[str]) -> str:
    if not athlete_names:
        return "[DEMO] Generated documents"
    if len(athlete_names) == 1:
        return f"[DEMO] Generated documents for {athlete_names[0]}"
    return f"[DEMO] Generated documents for {athlete_names[0]} and {len(athlete_names) - 1} more"


def _build_generated_docs_body(*, original: EmailIntake, payload: dict[str, Any]) -> str:
    return (
        "The demo document run has completed.\n\n"
        f"Original sender: {original.sender_email}\n"
        f"Sport: {payload.get('sport_name')}\n"
        f"Summary: {payload.get('summary')}\n"
    )


def _find_sport_by_name(db: Session, name: str) -> Sport | None:
    normalized = name.strip().lower()
    return db.scalar(
        select(Sport).where(
            or_(
                Sport.display_name.ilike(normalized),
                Sport.csv_name.ilike(normalized),
                Sport.slug.ilike(normalized.replace(" ", "-")),
            )
        )
    )


def _normalize_message_id(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_name(value: str) -> str:
    return " ".join(value.lower().split())


def _collect_change_issues(raw_change: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    issue = str(raw_change.get("issue") or "").strip()
    if issue:
        issues.append(issue)
    return issues


def _field_has_pending_value(adjustment: Adjustment, field: str) -> bool:
    before = (adjustment.before_values or {}).get(field)
    after = (adjustment.after_values or {}).get(field)
    return before != after


def _after_values_changed(after_values: dict[str, str], aid_record: AidRecord) -> bool:
    before_values = serialize_editable_values(aid_record)
    return any(before_values.get(field) != after_values.get(field) for field in AID_EDITABLE_FIELDS)


def _format_currency(value: Decimal) -> str:
    return f"${value:,.2f}"


def _format_signed_currency(value: Decimal) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


def _format_percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}%"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
