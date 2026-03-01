from pydantic import BaseModel, Field


class PlaceCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=128)
    wa_number: str | None = Field(default=None, max_length=64)
    context_prompt: str | None = Field(default=None, max_length=1000)
    settings: dict | None = None
    city: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=64)


class PlaceResponse(BaseModel):
    code: str
    name: str
    wa_number: str | None
    context_prompt: str | None
    settings: dict | None
    city: str | None
    country: str | None


class SegmentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    order_index: int = Field(ge=0)
    min_lat: float | None = None
    max_lat: float | None = None
    min_lon: float | None = None
    max_lon: float | None = None


class SegmentResponse(BaseModel):
    id: int
    place_code: str
    name: str
    order_index: int
    min_lat: float | None
    max_lat: float | None
    min_lon: float | None
    max_lon: float | None


class SegmentImportResponse(BaseModel):
    place_code: str
    created: int
