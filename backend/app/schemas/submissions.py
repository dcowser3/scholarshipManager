from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AidChangeValues(BaseModel):
    athletic_aid_total: Decimal = Field(default=0)
    oos_tuition: Decimal = Field(default=0)
    tuition: Decimal = Field(default=0)
    general_fee: Decimal = Field(default=0)
    misc_fee: Decimal = Field(default=0)
    room: Decimal = Field(default=0)
    board: Decimal = Field(default=0)
    books: Decimal = Field(default=0)
    personal_expenses: Decimal = Field(default=0)
    oos_resource: Decimal = Field(default=0)


class AidChangeRequest(BaseModel):
    membership_id: int
    after_values: AidChangeValues


class SubmitAdjustmentsRequest(BaseModel):
    sport_id: int
    recipient_email: EmailStr
    comment: str | None = None
    changes: list[AidChangeRequest]


class SubmittedAdjustmentResponse(BaseModel):
    submission_id: UUID
    adjustments_created: int
    artifacts_created: int
    recipient_email: EmailStr
