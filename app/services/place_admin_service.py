import csv
import io

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CorridorSegment, Place
from app.schemas.admin_places import (
    PlaceCreateRequest,
    PlaceResponse,
    SegmentCreateRequest,
    SegmentImportResponse,
    SegmentResponse,
)
from app.services.place_service import normalize_place_code


def create_place(db: Session, payload: PlaceCreateRequest) -> PlaceResponse:
    code = normalize_place_code(payload.code)
    existing = db.execute(select(Place).where(Place.code == code)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Place code already exists")

    place = Place(
        code=code,
        name=payload.name.strip(),
        wa_number=payload.wa_number,
        context_prompt=payload.context_prompt,
        settings=payload.settings or {},
        city=payload.city,
        country=payload.country,
    )
    db.add(place)
    db.commit()
    return PlaceResponse(
        code=place.code,
        name=place.name,
        wa_number=place.wa_number,
        context_prompt=place.context_prompt,
        settings=place.settings,
        city=place.city,
        country=place.country,
    )


def list_places(db: Session) -> list[PlaceResponse]:
    places = db.execute(select(Place).order_by(Place.code.asc())).scalars().all()
    return [
        PlaceResponse(
            code=p.code,
            name=p.name,
            wa_number=p.wa_number,
            context_prompt=p.context_prompt,
            settings=p.settings,
            city=p.city,
            country=p.country,
        )
        for p in places
    ]


def _get_place_or_404(db: Session, place_code: str) -> Place:
    code = normalize_place_code(place_code)
    place = db.execute(select(Place).where(Place.code == code)).scalar_one_or_none()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


def create_segment(db: Session, place_code: str, payload: SegmentCreateRequest) -> SegmentResponse:
    place = _get_place_or_404(db, place_code)

    segment = CorridorSegment(
        place_id=place.id,
        name=payload.name.strip(),
        order_index=payload.order_index,
        min_lat=payload.min_lat,
        max_lat=payload.max_lat,
        min_lon=payload.min_lon,
        max_lon=payload.max_lon,
    )
    db.add(segment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Segment already exists for place")

    return SegmentResponse(
        id=segment.id,
        place_code=place.code,
        name=segment.name,
        order_index=segment.order_index,
        min_lat=segment.min_lat,
        max_lat=segment.max_lat,
        min_lon=segment.min_lon,
        max_lon=segment.max_lon,
    )


def list_segments(db: Session, place_code: str) -> list[SegmentResponse]:
    place = _get_place_or_404(db, place_code)
    segments = db.execute(
        select(CorridorSegment)
        .where(CorridorSegment.place_id == place.id)
        .order_by(CorridorSegment.order_index.asc(), CorridorSegment.id.asc())
    ).scalars().all()

    return [
        SegmentResponse(
            id=s.id,
            place_code=place.code,
            name=s.name,
            order_index=s.order_index,
            min_lat=s.min_lat,
            max_lat=s.max_lat,
            min_lon=s.min_lon,
            max_lon=s.max_lon,
        )
        for s in segments
    ]


def replace_segments_from_csv(db: Session, place_code: str, csv_bytes: bytes) -> SegmentImportResponse:
    place = _get_place_or_404(db, place_code)

    try:
        text = csv_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "order_index", "min_lat", "max_lat", "min_lon", "max_lon"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail="CSV missing required columns")

    rows: list[CorridorSegment] = []
    for row in reader:
        if not row.get("name"):
            continue
        try:
            rows.append(
                CorridorSegment(
                    place_id=place.id,
                    name=row["name"].strip(),
                    order_index=int(row["order_index"]),
                    min_lat=float(row["min_lat"]),
                    max_lat=float(row["max_lat"]),
                    min_lon=float(row["min_lon"]),
                    max_lon=float(row["max_lon"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid numeric value in CSV") from exc

    db.execute(delete(CorridorSegment).where(CorridorSegment.place_id == place.id))
    for segment in rows:
        db.add(segment)
    db.commit()

    return SegmentImportResponse(place_code=place.code, created=len(rows))
