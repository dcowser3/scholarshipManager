from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Athlete, ConfigEntry, Sport, Term
from app.models.imports import ImportCohortIssue, ImportDiff, ImportRun
from app.models.roster import AidRecord, RosterMembership
from app.models.user import User

CSV_REQUIRED_HEADERS = {
    "ID",
    "NAME",
    "COHORT",
    "SPORT",
    "FALL_ATHLETIC_AID",
    "FALL_ATHLETICS_PERSONAL_EXPENSES",
    "FALL_ATHLETICS_OOS_TUITION",
    "FALL_ATHLETICS_TUITION",
    "FALL_ATHLETICS_GENERAL_FEE",
    "FALL_ATHLETICS_MISC_FEE",
    "FALL_ATHLETICS_BOOKS",
    "FALL_ATHLETICS_HOUSING",
    "FALL_ATHLETICS_FOOD",
    "FALL_MERIT_SCHOLARSHIP",
    "FALL_ACADEMIC_AID",
    "FALL_OOS_RESOURCE",
    "SPRING_ATHLETIC_AID",
    "SPRING_PERSONAL_EXPENSES",
    "SPRING_ATHLETICS_OOS_TUITION",
    "SPRING_ATHLETICS_TUITION",
    "SPRING_ATHLETICS_GENERAL_FEE",
    "SPRING_ATHLETICS_GENERAL_FEE1",
    "SPRING_ATHLETICS_MISC_FEE",
    "SPRING_ATHLETICS_BOOKS",
    "SPRING_ATHLETICS_HOUSING",
    "SPRING_ATHLETICS_FOOD",
    "SPRING_MERIT_SCHOLARSHIP",
    "SPRING_ACADEMIC_AID",
    "SPRING_OOS_RESOURCE",
}

IMPORT_FIELDS = {
    "athletic_aid_total": "ATHLETIC_AID",
    "personal_expenses": "ATHLETICS_PERSONAL_EXPENSES",
    "oos_tuition": "ATHLETICS_OOS_TUITION",
    "tuition": "ATHLETICS_TUITION",
    "general_fee": "ATHLETICS_GENERAL_FEE",
    "misc_fee": "ATHLETICS_MISC_FEE",
    "books": "ATHLETICS_BOOKS",
    "room": "ATHLETICS_HOUSING",
    "board": "ATHLETICS_FOOD",
    "merit_scholarship": "MERIT_SCHOLARSHIP",
    "academic_aid": "ACADEMIC_AID",
    "oos_resource": "OOS_RESOURCE",
}

DEFAULT_IMPORT_ACADEMIC_YEAR = "25-26"


@dataclass
class ImportSummary:
    import_run: ImportRun
    rows_processed: int
    rows_changed: int
    duplicates_dropped: int
    error_log: dict


def slugify_sport_name(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace("'", "")
        .replace("/", "-")
        .replace(" ", "-")
    )


def translate_cohort(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if cleaned == "TGN":
        return "GRAD/NON"
    if len(cleaned) == 6 and cleaned.startswith("TG") and cleaned[2:].isdigit():
        return f"{cleaned[2:4]}-{cleaned[4:6]}"
    return cleaned


def cohort_display_to_internal(value: str) -> str:
    cleaned = value.strip().upper()
    if len(cleaned) != 5 or cleaned[2] != "-":
        raise ValueError(f"Unsupported cohort display value: {value}")
    start_year, end_year = cleaned.split("-", 1)
    if not (start_year.isdigit() and end_year.isdigit()):
        raise ValueError(f"Unsupported cohort display value: {value}")
    return f"TG{start_year}{end_year}"


def parse_name(value: str) -> tuple[str, str]:
    if "," not in value:
        parts = value.strip().split()
        if len(parts) == 1:
            return parts[0], ""
        return parts[-1], " ".join(parts[:-1])
    last_name, first_name = [part.strip() for part in value.split(",", 1)]
    return last_name, first_name


def decimal_or_zero(value: str | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    stripped = value.strip()
    if not stripped:
        return Decimal("0.00")
    return Decimal(stripped).quantize(Decimal("0.01"))


def decode_csv(file_obj: BinaryIO) -> list[dict[str, str]]:
    raw = file_obj.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV is missing headers")
    missing = CSV_REQUIRED_HEADERS - set(reader.fieldnames)
    if missing:
        raise ValueError(f"CSV is missing required headers: {sorted(missing)}")
    return list(reader)


def ensure_default_sports(db: Session, sport_names: set[str]) -> None:
    existing = {sport.csv_name for sport in db.scalars(select(Sport))}
    for index, csv_name in enumerate(sorted(sport_names), start=1):
        if csv_name in existing:
            continue
        db.add(
            Sport(
                csv_name=csv_name,
                display_name=csv_name,
                slug=slugify_sport_name(csv_name),
                display_order=index,
            )
        )
    db.flush()


def get_term_map(db: Session) -> dict[tuple[str, str], Term]:
    terms = db.scalars(select(Term)).all()
    return {(term.academic_year, term.semester): term for term in terms}


def get_active_import_academic_year(db: Session) -> str:
    entry = db.get(ConfigEntry, "active_roster_academic_year")
    if entry and entry.value:
        return entry.value
    return DEFAULT_IMPORT_ACADEMIC_YEAR


def get_sport_map(db: Session) -> dict[str, Sport]:
    sports = db.scalars(select(Sport)).all()
    return {sport.csv_name: sport for sport in sports}


def upsert_athlete(db: Session, row: dict[str, str]) -> Athlete:
    rocket_id = row["ID"].strip()
    athlete = db.get(Athlete, rocket_id)
    last_name, first_name = parse_name(row["NAME"])
    if athlete is None:
        athlete = Athlete(rocket_id=rocket_id, first_name=first_name, last_name=last_name)
        db.add(athlete)
    else:
        athlete.first_name = first_name
        athlete.last_name = last_name
        athlete.is_active = True
    db.flush()
    return athlete


def resolve_import_cohort(athlete: Athlete, row: dict[str, str]) -> tuple[str | None, str | None]:
    source_internal = (row.get("COHORT") or "").strip() or None
    source_display = translate_cohort(source_internal)
    if source_internal and source_display and source_display != "GRAD/NON":
        return source_internal, source_display

    if athlete.cohort_override_internal and athlete.cohort_override_display:
        return athlete.cohort_override_internal, athlete.cohort_override_display

    return None, None


def upsert_cohort_issue(
    db: Session,
    *,
    import_run: ImportRun,
    athlete: Athlete,
    sport: Sport,
    row: dict[str, str],
) -> None:
    issue = db.scalar(
        select(ImportCohortIssue).where(
            ImportCohortIssue.athlete_id == athlete.rocket_id,
            ImportCohortIssue.sport_id == sport.id,
        )
    )
    if issue is None:
        issue = ImportCohortIssue(
            athlete_id=athlete.rocket_id,
            sport_id=sport.id,
            source_row=row,
        )
        db.add(issue)

    issue.import_run_id = import_run.id
    issue.source_cohort = (row.get("COHORT") or "").strip() or None
    issue.source_row = row
    issue.status = "PENDING"
    issue.resolved_cohort_display = None
    issue.resolved_by = None
    issue.resolved_at = None


def resolve_existing_issue(
    db: Session,
    *,
    athlete_id: str,
    sport_id: int,
    import_run_id: int,
    cohort_display: str,
) -> None:
    issue = db.scalar(
        select(ImportCohortIssue).where(
            ImportCohortIssue.athlete_id == athlete_id,
            ImportCohortIssue.sport_id == sport_id,
        )
    )
    if issue is None:
        return

    issue.import_run_id = import_run_id
    issue.status = "RESOLVED"
    issue.resolved_cohort_display = cohort_display


def apply_saved_cohort_override(
    db: Session,
    *,
    athlete: Athlete,
    sport: Sport,
    row: dict[str, str],
    cohort_internal: str,
    cohort_display: str,
) -> None:
    term_map = get_term_map(db)
    active_academic_year = get_active_import_academic_year(db)
    for semester in ("FALL", "SPRING"):
        term = term_map.get((active_academic_year, semester))
        if term is None:
            continue
        membership, _aid_record, _before, _after, _changed = upsert_membership_and_aid(
            db,
            athlete=athlete,
            sport=sport,
            term=term,
            row=row,
        )
        membership.cohort_internal = cohort_internal
        membership.cohort_display = cohort_display


def resolve_cohort_issue(
    db: Session,
    *,
    issue: ImportCohortIssue,
    academic_year: str,
    resolved_by: User,
) -> ImportCohortIssue:
    cohort_internal = cohort_display_to_internal(academic_year)
    athlete = db.get(Athlete, issue.athlete_id)
    sport = db.get(Sport, issue.sport_id)
    if athlete is None or sport is None:
        raise ValueError("Cohort issue references missing athlete or sport")

    athlete.cohort_override_internal = cohort_internal
    athlete.cohort_override_display = academic_year
    athlete.cohort_override_updated_at = datetime.now(UTC)

    apply_saved_cohort_override(
        db,
        athlete=athlete,
        sport=sport,
        row=issue.source_row,
        cohort_internal=cohort_internal,
        cohort_display=academic_year,
    )

    issue.status = "RESOLVED"
    issue.resolved_cohort_display = academic_year
    issue.resolved_by = resolved_by.id
    issue.resolved_at = datetime.now(UTC)
    db.flush()
    return issue


def serialize_aid_record(record: AidRecord | None) -> dict[str, str]:
    if record is None:
        return {}
    return {
        "athletic_aid_total": str(record.athletic_aid_total),
        "personal_expenses": str(record.personal_expenses),
        "oos_tuition": str(record.oos_tuition),
        "tuition": str(record.tuition),
        "general_fee": str(record.general_fee),
        "misc_fee": str(record.misc_fee),
        "books": str(record.books),
        "room": str(record.room),
        "board": str(record.board),
        "merit_scholarship": str(record.merit_scholarship),
        "academic_aid": str(record.academic_aid),
        "oos_resource": str(record.oos_resource),
        "coa_total": str(record.coa_total),
        "source": record.source or "",
    }


def build_aid_payload(row: dict[str, str], semester: str) -> dict[str, Decimal | str | datetime]:
    prefix = semester.upper()
    payload: dict[str, Decimal | str | datetime] = {}
    for field_name, csv_suffix in IMPORT_FIELDS.items():
        column_name = f"{prefix}_{csv_suffix}"
        payload[field_name] = decimal_or_zero(row.get(column_name))
    payload["coa_total"] = Decimal("0.00")
    payload["source"] = "IMPORT"
    payload["last_synced_at"] = datetime.now(UTC)
    return payload


def upsert_membership_and_aid(
    db: Session,
    *,
    athlete: Athlete,
    sport: Sport,
    term: Term,
    row: dict[str, str],
) -> tuple[RosterMembership, AidRecord, dict[str, str], dict[str, str], bool]:
    membership = db.scalar(
        select(RosterMembership).where(
            RosterMembership.athlete_id == athlete.rocket_id,
            RosterMembership.sport_id == sport.id,
            RosterMembership.term_id == term.id,
        )
    )
    if membership is None:
        membership = RosterMembership(
            athlete_id=athlete.rocket_id,
            sport_id=sport.id,
            term_id=term.id,
            status="ACTIVE",
        )
        db.add(membership)
        db.flush()

    membership.cohort_internal = (row.get("COHORT") or "").strip() or None
    membership.cohort_display = translate_cohort(row.get("COHORT"))
    membership.status = "ACTIVE"

    aid_record = db.scalar(select(AidRecord).where(AidRecord.membership_id == membership.id))
    before = serialize_aid_record(aid_record)
    if aid_record is None:
        aid_record = AidRecord(membership_id=membership.id)
        db.add(aid_record)
        db.flush()

    payload = build_aid_payload(row, term.semester)
    for key, value in payload.items():
        setattr(aid_record, key, value)

    after = serialize_aid_record(aid_record)
    changed = before != after
    return membership, aid_record, before, after, changed


def import_csv_file(
    db: Session,
    *,
    file_obj: BinaryIO,
    source_filename: str,
    imported_by: User | None,
) -> ImportSummary:
    rows = decode_csv(file_obj)
    duplicate_counter = Counter(row["ID"].strip() for row in rows)
    duplicates_dropped = sum(count - 1 for count in duplicate_counter.values() if count > 1)

    deduped_rows: dict[str, dict[str, str]] = {}
    for row in rows:
        deduped_rows[row["ID"].strip()] = row

    ensure_default_sports(db, {row["SPORT"].strip() for row in deduped_rows.values()})
    sport_map = get_sport_map(db)
    term_map = get_term_map(db)
    active_academic_year = get_active_import_academic_year(db)

    error_log: dict[str, list[str] | int | list[dict[str, str]]] = {
        "duplicates_dropped": duplicates_dropped,
        "blank_cohort_ids": [],
        "unknown_terms": [],
        "active_import_academic_year": active_academic_year,
    }
    rows_changed = 0

    import_run = ImportRun(
        imported_by=imported_by.id if imported_by else None,
        source_filename=source_filename,
        rows_processed=len(rows),
        rows_changed=0,
        duplicates_dropped=duplicates_dropped,
        error_log={},
    )
    db.add(import_run)
    db.flush()

    for row in deduped_rows.values():
        athlete = upsert_athlete(db, row)
        sport = sport_map[row["SPORT"].strip()]
        cohort_internal, cohort_display = resolve_import_cohort(athlete, row)

        if cohort_display is None:
            if (row.get("COHORT") or "").strip():
                error_log["unknown_terms"].append(
                    {"athlete_id": athlete.rocket_id, "cohort": (row.get("COHORT") or "").strip()}
                )
            else:
                error_log["blank_cohort_ids"].append(athlete.rocket_id)
            upsert_cohort_issue(
                db,
                import_run=import_run,
                athlete=athlete,
                sport=sport,
                row=row,
            )

        for semester in ("FALL", "SPRING"):
            term = term_map.get((active_academic_year, semester))
            if term is None:
                error_log["unknown_terms"].append(
                    {
                        "athlete_id": athlete.rocket_id,
                        "active_import_academic_year": active_academic_year,
                        "semester": semester,
                    }
                )
                continue

            membership, _aid_record, before, after, changed = upsert_membership_and_aid(
                db, athlete=athlete, sport=sport, term=term, row=row
            )
            membership.cohort_internal = cohort_internal
            membership.cohort_display = cohort_display
            if changed:
                rows_changed += 1
                for field, new_value in after.items():
                    old_value = before.get(field)
                    if old_value == new_value:
                        continue
                    db.add(
                        ImportDiff(
                            import_run_id=import_run.id,
                            athlete_id=athlete.rocket_id,
                            term_id=term.id,
                            field=field,
                            old_value=old_value,
                            new_value=new_value,
                        )
                    )

        if cohort_display is not None:
            resolve_existing_issue(
                db,
                athlete_id=athlete.rocket_id,
                sport_id=sport.id,
                import_run_id=import_run.id,
                cohort_display=cohort_display,
            )
        elif not db.scalar(
            select(ImportCohortIssue).where(
                ImportCohortIssue.athlete_id == athlete.rocket_id,
                ImportCohortIssue.sport_id == sport.id,
            )
        ):
            error_log["unknown_terms"].append(
                {
                    "athlete_id": athlete.rocket_id,
                    "problem": "missing cohort issue was not persisted",
                }
            )

    import_run.rows_changed = rows_changed
    import_run.error_log = error_log
    db.flush()
    return ImportSummary(
        import_run=import_run,
        rows_processed=len(rows),
        rows_changed=rows_changed,
        duplicates_dropped=duplicates_dropped,
        error_log=error_log,
    )


def import_csv_path(db: Session, csv_path: str, imported_by: User | None = None) -> ImportSummary:
    path = Path(csv_path)
    with path.open("rb") as file_obj:
        return import_csv_file(
            db, file_obj=file_obj, source_filename=path.name, imported_by=imported_by
        )
