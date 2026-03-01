from pydantic import BaseModel, Field


class SentimentAuditSampleItem(BaseModel):
    message_id: str
    text: str
    model_label: str
    model_score: float | None
    heuristic_label: str


class SentimentAuditSampleResponse(BaseModel):
    sample_size: int
    items: list[SentimentAuditSampleItem]


class SentimentAuditManualItem(BaseModel):
    message_id: str
    manual_label: str = Field(pattern="^(negative|neutral|positive)$")


class SentimentAuditEvaluateRequest(BaseModel):
    items: list[SentimentAuditManualItem]


class SentimentAuditEvaluateResponse(BaseModel):
    compared_count: int
    model_matches: int
    heuristic_matches: int
    model_accuracy_pct: float
    heuristic_accuracy_pct: float
