from datetime import datetime

from pydantic import BaseModel, Field


class TaxonomyCandidateResponse(BaseModel):
    id: str
    place_id: int | None
    message_id: str | None
    taxonomy_type: str
    candidate_label: str
    normalized_label: str
    reason: str | None
    fit_score: float
    support_count: int
    status: str
    review_note: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaxonomyCandidateListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TaxonomyCandidateResponse]


class TaxonomyCandidateDecisionRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=280)


class TaxonomyCandidateDecisionResponse(BaseModel):
    id: str
    status: str
    review_note: str | None
    approved_at: datetime | None
