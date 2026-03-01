from pydantic import BaseModel


class WhatsAppWebhookResponse(BaseModel):
    accepted: bool
    message_id: str | None = None
    detail: str
    provider: str | None = None
    ingested_count: int = 0
