from pydantic import BaseModel, field_validator

from app.core.taxonomies import DESIRED_FUTURES, PRIMARY_TOPICS, TENSION_TYPES


class FeedbackViewResponse(BaseModel):
    message_id: str
    original_text: str | None
    transcript_text: str | None
    latest_version: int
    summary_line: str
    primary_topic: str
    desired_future: str
    tension_type: str
    quote_snippet: str
    allow_public_quote: bool
    clarification_note: str | None
    place_reference: str | None


class FeedbackPatchRequest(BaseModel):
    summary_line: str | None = None
    primary_topic: str | None = None
    desired_future: str | None = None
    tension_type: str | None = None
    quote_snippet: str | None = None
    clarification_note: str | None = None
    place_reference: str | None = None
    allow_public_quote: bool | None = None

    @field_validator("summary_line")
    @classmethod
    def validate_summary_line(cls, value: str | None):
        if value is None:
            return value
        if len(value.strip()) < 3:
            raise ValueError("El resumen debe tener al menos 3 caracteres.")
        if len(value) > 280:
            raise ValueError("El resumen no puede superar 280 caracteres.")
        return value

    @field_validator("quote_snippet")
    @classmethod
    def validate_quote_snippet(cls, value: str | None):
        if value is None:
            return value
        if len(value) > 280:
            raise ValueError("La cita breve no puede superar 280 caracteres.")
        return value

    @field_validator("clarification_note")
    @classmethod
    def validate_clarification_note(cls, value: str | None):
        if value is None:
            return value
        if len(value) > 1000:
            raise ValueError("La aclaracion no puede superar 1000 caracteres.")
        return value

    @field_validator("place_reference")
    @classmethod
    def validate_place_reference(cls, value: str | None):
        if value is None:
            return value
        if len(value) > 256:
            raise ValueError("La referencia del lugar no puede superar 256 caracteres.")
        return value

    @field_validator("primary_topic")
    @classmethod
    def validate_topic(cls, value: str | None):
        if value is None or value in PRIMARY_TOPICS:
            return value
        raise ValueError(f"Tema principal invalido. Valores permitidos: {', '.join(PRIMARY_TOPICS)}")

    @field_validator("desired_future")
    @classmethod
    def validate_future(cls, value: str | None):
        if value is None or value in DESIRED_FUTURES:
            return value
        raise ValueError(f"Futuro deseado invalido. Valores permitidos: {', '.join(DESIRED_FUTURES)}")

    @field_validator("tension_type")
    @classmethod
    def validate_tension(cls, value: str | None):
        if value is None or value in TENSION_TYPES:
            return value
        raise ValueError(f"Tension invalida. Valores permitidos: {', '.join(TENSION_TYPES)}")


class FeedbackPatchResponse(BaseModel):
    message_id: str
    new_version: int
    summary_line: str
    primary_topic: str
    desired_future: str
    tension_type: str
    quote_snippet: str
    allow_public_quote: bool
    place_reference: str | None
