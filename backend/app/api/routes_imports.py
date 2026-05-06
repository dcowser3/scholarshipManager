from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import record_audit_event, require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.imports import ImportRunResponse
from app.services.importer import import_csv_file

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/csv", response_model=ImportRunResponse)
def import_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> ImportRunResponse:
    if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a CSV file.",
        )

    summary = import_csv_file(
        db,
        file_obj=csv_file.file,
        source_filename=csv_file.filename,
        imported_by=user,
    )
    record_audit_event(
        db,
        user_id=user.id,
        action="IMPORT_CSV",
        entity_type="import_run",
        entity_id=str(summary.import_run.id),
        request=request,
        after={
            "rows_processed": summary.rows_processed,
            "rows_changed": summary.rows_changed,
            "duplicates_dropped": summary.duplicates_dropped,
        },
    )
    db.commit()
    return ImportRunResponse(
        id=summary.import_run.id,
        rows_processed=summary.rows_processed,
        rows_changed=summary.rows_changed,
        duplicates_dropped=summary.duplicates_dropped,
        source_filename=summary.import_run.source_filename,
        error_log=summary.error_log,
    )
