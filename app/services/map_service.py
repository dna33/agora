from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from math import asin, cos, degrees, floor, radians, sin, sqrt

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import AnalysisVersion, Message
from app.schemas.map import (
    GridCell,
    GridResponse,
    HeatPoint,
    HeatmapResponse,
    MapPoint,
    MapPointsResponse,
    TimelapseFrame,
    TimelapseResponse,
)

EARTH_RADIUS_M = 6371000.0


def _sentiment_score(text: str, primary_topic: str | None) -> float:
    norm = text.lower()
    positive_terms = [
        "me gusta",
        "bonito",
        "tranquilo",
        "limpio",
        "agradable",
        "mejor",
        "sombra",
        "verde",
        "seguro",
    ]
    negative_terms = [
        "miedo",
        "insegur",
        "basura",
        "sucio",
        "ruido",
        "peligro",
        "oscuro",
        "robo",
        "accidente",
        "falta",
        "horrible",
        "pesimo",
    ]

    pos = sum(1 for term in positive_terms if term in norm)
    neg = sum(1 for term in negative_terms if term in norm)
    if primary_topic == "safety":
        neg += 1 if any(term in norm for term in ["miedo", "insegur", "robo", "oscuro"]) else 0

    if pos + neg == 0:
        return 0.0
    score = (pos - neg) / float(pos + neg)
    return round(max(-1.0, min(1.0, score)), 3)


def _sentiment_label(score: float) -> str:
    if score <= -0.2:
        return "negative"
    if score >= 0.2:
        return "positive"
    return "neutral"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2.0) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * asin(sqrt(max(0.0, min(1.0, a))))


def _attach_geo_avg_500m(points: list[MapPoint], radius_m: float = 500.0) -> list[MapPoint]:
    if not points:
        return points

    for i, point in enumerate(points):
        total = 0.0
        count = 0
        for j, other in enumerate(points):
            _ = j
            if _haversine_m(point.latitude, point.longitude, other.latitude, other.longitude) <= radius_m:
                total += other.sentiment_score
                count += 1
        avg = point.sentiment_score if count == 0 else (total / float(count))
        points[i].geo_avg_sentiment_score_500m = round(avg, 3)
        points[i].geo_neighbor_count_500m = count
    return points


def _lonlat_to_xy_m(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    x = radians(lon) * EARTH_RADIUS_M * cos(radians(ref_lat))
    y = radians(lat) * EARTH_RADIUS_M
    return x, y


def _xy_m_to_lonlat(x: float, y: float, ref_lat: float) -> tuple[float, float]:
    lat = degrees(y / EARTH_RADIUS_M)
    lon = degrees(x / (EARTH_RADIUS_M * max(1e-8, cos(radians(ref_lat)))))
    return lon, lat


def _scale_label_es_from_avg(avg_sentiment_score: float) -> tuple[str, int]:
    value = int(round(max(-1.0, min(1.0, avg_sentiment_score)) * 100))
    if value <= -60:
        return "muy negativo", value
    if value <= -20:
        return "negativo", value
    if value < 20:
        return "neutral", value
    if value < 60:
        return "positivo", value
    return "muy positivo", value


def _fetch_geolocated_rows(
    db: Session,
    place_id: int,
    since: datetime | None,
    limit: int,
) -> Sequence:
    latest_version = (
        select(
            AnalysisVersion.message_id.label("message_id"),
            func.max(AnalysisVersion.version).label("max_version"),
        )
        .group_by(AnalysisVersion.message_id)
        .subquery()
    )

    query = (
        select(
            Message.id,
            Message.latitude,
            Message.longitude,
            Message.created_at,
            Message.source_type,
            Message.place_reference,
            Message.original_text,
            Message.transcript_text,
            AnalysisVersion.summary_line,
            AnalysisVersion.primary_topic,
            AnalysisVersion.extraction_json,
        )
        .outerjoin(
            latest_version,
            latest_version.c.message_id == Message.id,
        )
        .outerjoin(
            AnalysisVersion,
            and_(
                AnalysisVersion.message_id == Message.id,
                AnalysisVersion.version == latest_version.c.max_version,
            ),
        )
        .where(
            Message.place_id == place_id,
            Message.latitude.is_not(None),
            Message.longitude.is_not(None),
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )

    if since is not None:
        query = query.where(Message.created_at >= since)

    return db.execute(query).all()


def get_place_map_points(
    db: Session,
    place_id: int,
    limit: int = 1000,
    period_days: int | None = None,
) -> MapPointsResponse:
    since = None
    if period_days:
        since = datetime.now(timezone.utc) - timedelta(days=period_days)

    rows = _fetch_geolocated_rows(db, place_id=place_id, since=since, limit=limit)
    points: list[MapPoint] = []
    for row in rows:
        text = row.transcript_text or row.original_text or row.summary_line or ""
        score_from_model = None
        label_from_model = None
        if isinstance(row.extraction_json, dict):
            raw_score = row.extraction_json.get("sentiment_score")
            raw_label = row.extraction_json.get("sentiment_label")
            try:
                if raw_score is not None:
                    score_from_model = float(raw_score)
            except (TypeError, ValueError):
                score_from_model = None
            if isinstance(raw_label, str):
                label_from_model = raw_label.lower()

        if score_from_model is not None and -1 <= score_from_model <= 1:
            score = round(score_from_model, 3)
            label = label_from_model if label_from_model in {"positive", "neutral", "negative"} else _sentiment_label(score)
        else:
            score = _sentiment_score(text, row.primary_topic)
            label = _sentiment_label(score)
        points.append(
            MapPoint(
                message_id=row.id,
                latitude=float(row.latitude),
                longitude=float(row.longitude),
                created_at=row.created_at,
                source_type=row.source_type,
                place_reference=row.place_reference,
                summary_line=row.summary_line,
                primary_topic=row.primary_topic,
                sentiment_score=score,
                sentiment_label=label,
            )
        )
    points = _attach_geo_avg_500m(points, radius_m=500.0)
    return MapPointsResponse(place_id=place_id, total=len(points), points=points)


def get_place_heatmap(
    db: Session,
    place_id: int,
    mode: str = "negative",
    limit: int = 5000,
    period_days: int | None = None,
) -> HeatmapResponse:
    mode_norm = (mode or "negative").lower()
    if mode_norm not in {"negative", "positive", "absolute", "geo_avg"}:
        mode_norm = "negative"

    since = None
    if period_days:
        since = datetime.now(timezone.utc) - timedelta(days=period_days)

    mapped = get_place_map_points(db, place_id=place_id, limit=limit, period_days=period_days)
    points: list[HeatPoint] = []
    for p in mapped.points:
        score = p.sentiment_score
        geo_score = p.geo_avg_sentiment_score_500m if p.geo_avg_sentiment_score_500m is not None else score
        base_score = geo_score if mode_norm == "geo_avg" else score
        neg = round(max(0.0, -base_score), 3)
        pos = round(max(0.0, base_score), 3)
        absw = round(abs(base_score), 3)
        if absw == 0:
            continue
        points.append(
            HeatPoint(
                latitude=float(p.latitude),
                longitude=float(p.longitude),
                sentiment_score=score,
                negative_weight=neg,
                positive_weight=pos,
                absolute_weight=absw,
            )
        )

    return HeatmapResponse(place_id=place_id, total=len(points), mode=mode_norm, points=points)


def _bucket_label(ts: datetime, granularity: str) -> str:
    if granularity == "week":
        iso = ts.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if granularity == "month":
        return ts.strftime("%Y-%m")
    return ts.strftime("%Y-%m-%d")


def _bucket_cutoff(ts: datetime, granularity: str) -> datetime:
    if granularity == "week":
        start = ts - timedelta(days=ts.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "month":
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def get_place_timelapse(
    db: Session,
    place_id: int,
    mode: str = "negative",
    granularity: str = "day",
    period_days: int | None = 30,
    limit: int = 3000,
) -> TimelapseResponse:
    mode_norm = (mode or "negative").lower()
    if mode_norm not in {"negative", "positive", "absolute", "geo_avg"}:
        mode_norm = "negative"

    gran = (granularity or "day").lower()
    if gran not in {"day", "week", "month"}:
        gran = "day"

    mapped = get_place_map_points(db, place_id=place_id, limit=limit, period_days=period_days)
    ordered = sorted(mapped.points, key=lambda p: p.created_at)

    frames: list[TimelapseFrame] = []
    cumulative: list[MapPoint] = []
    current_label = None
    frame_idx = 0

    for point in ordered:
        label = _bucket_label(point.created_at, gran)
        cutoff = _bucket_cutoff(point.created_at, gran)
        if current_label is None:
            current_label = label
        if label != current_label:
            frames.append(
                TimelapseFrame(
                    frame_index=frame_idx,
                    frame_label=current_label,
                    cutoff_at=_bucket_cutoff(cumulative[-1].created_at, gran),
                    total_points=len(cumulative),
                    points=list(cumulative),
                )
            )
            frame_idx += 1
            current_label = label
        cumulative.append(point)

        # refresh cutoff variable for mypy/clarity
        _ = cutoff

    if cumulative:
        frames.append(
            TimelapseFrame(
                frame_index=frame_idx,
                frame_label=current_label or "frame",
                cutoff_at=_bucket_cutoff(cumulative[-1].created_at, gran),
                total_points=len(cumulative),
                points=list(cumulative),
            )
        )

    return TimelapseResponse(
        place_id=place_id,
        mode=mode_norm,
        granularity=gran,
        total_points=len(ordered),
        total_frames=len(frames),
        frames=frames,
    )


def get_place_sentiment_grid(
    db: Session,
    place_id: int,
    cell_meters: float = 100.0,
    period_days: int | None = 30,
    limit: int = 5000,
    min_points: int = 1,
) -> GridResponse:
    cell_m = max(20.0, min(1000.0, float(cell_meters)))
    min_pts = max(1, int(min_points))

    mapped = get_place_map_points(db, place_id=place_id, limit=limit, period_days=period_days)
    points = mapped.points
    if not points:
        return GridResponse(place_id=place_id, total_cells=0, cell_meters=cell_m, cells=[])

    ref_lat = sum(p.latitude for p in points) / len(points)
    buckets: dict[tuple[int, int], dict[str, float | int]] = {}
    for p in points:
        x, y = _lonlat_to_xy_m(p.latitude, p.longitude, ref_lat=ref_lat)
        i = int(floor(x / cell_m))
        j = int(floor(y / cell_m))
        key = (i, j)
        if key not in buckets:
            buckets[key] = {"sum": 0.0, "count": 0}
        buckets[key]["sum"] = float(buckets[key]["sum"]) + p.sentiment_score
        buckets[key]["count"] = int(buckets[key]["count"]) + 1

    cells: list[GridCell] = []
    for (i, j), agg in buckets.items():
        count = int(agg["count"])
        if count < min_pts:
            continue
        avg = float(agg["sum"]) / float(count)
        x0, y0 = i * cell_m, j * cell_m
        x1, y1 = (i + 1) * cell_m, (j + 1) * cell_m
        min_lon, min_lat = _xy_m_to_lonlat(x0, y0, ref_lat=ref_lat)
        max_lon, max_lat = _xy_m_to_lonlat(x1, y1, ref_lat=ref_lat)
        avg_clamped = round(max(-1.0, min(1.0, avg)), 3)
        scale_label_es, scale_value = _scale_label_es_from_avg(avg_clamped)
        cells.append(
            GridCell(
                min_latitude=float(min_lat),
                min_longitude=float(min_lon),
                max_latitude=float(max_lat),
                max_longitude=float(max_lon),
                avg_sentiment_score=avg_clamped,
                sentiment_scale_label_es=scale_label_es,
                sentiment_scale_value=scale_value,
                message_count=count,
            )
        )

    return GridResponse(
        place_id=place_id,
        total_cells=len(cells),
        cell_meters=cell_m,
        cells=cells,
    )
