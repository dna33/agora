from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CorridorSegment


def assign_corridor_segment(
    db: Session,
    latitude: float | None,
    longitude: float | None,
    place_id: int | None = None,
) -> int | None:
    if latitude is None or longitude is None:
        return None

    stmt = select(CorridorSegment)
    if place_id is not None:
        stmt = stmt.where(CorridorSegment.place_id == place_id)

    segments = db.execute(stmt.order_by(CorridorSegment.order_index.asc())).scalars().all()
    for segment in segments:
        if (
            segment.min_lat is not None
            and segment.max_lat is not None
            and segment.min_lon is not None
            and segment.max_lon is not None
            and segment.min_lat <= latitude <= segment.max_lat
            and segment.min_lon <= longitude <= segment.max_lon
        ):
            return segment.id
    return None
