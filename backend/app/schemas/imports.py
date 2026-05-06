from pydantic import BaseModel


class ImportRunResponse(BaseModel):
    id: int
    rows_processed: int
    rows_changed: int
    duplicates_dropped: int
    source_filename: str | None
    error_log: dict | None

