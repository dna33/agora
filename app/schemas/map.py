from datetime import datetime

from pydantic import BaseModel


class MapPoint(BaseModel):
    message_id: str
    latitude: float
    longitude: float
    created_at: datetime
    source_type: str
    place_reference: str | None
    summary_line: str | None
    primary_topic: str | None
    sentiment_score: float
    sentiment_label: str
    geo_avg_sentiment_score_500m: float | None = None
    geo_neighbor_count_500m: int | None = None


class MapPointsResponse(BaseModel):
    place_id: int
    total: int
    points: list[MapPoint]


class HeatPoint(BaseModel):
    latitude: float
    longitude: float
    sentiment_score: float
    negative_weight: float
    positive_weight: float
    absolute_weight: float


class HeatmapResponse(BaseModel):
    place_id: int
    total: int
    mode: str
    points: list[HeatPoint]


class GridCell(BaseModel):
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float
    avg_sentiment_score: float
    sentiment_scale_label_es: str
    sentiment_scale_value: int
    message_count: int


class GridResponse(BaseModel):
    place_id: int
    total_cells: int
    cell_meters: float
    cells: list[GridCell]


class TimelapseFrame(BaseModel):
    frame_index: int
    frame_label: str
    cutoff_at: datetime
    total_points: int
    points: list[MapPoint]


class TimelapseResponse(BaseModel):
    place_id: int
    mode: str
    granularity: str
    total_points: int
    total_frames: int
    frames: list[TimelapseFrame]
