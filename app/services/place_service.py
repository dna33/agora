from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Place


def normalize_place_code(code: str) -> str:
    return code.strip().lower().replace(" ", "-")


def get_or_create_place(
    db: Session,
    code: str,
    default_name: str,
    city: str | None = None,
    country: str | None = None,
) -> Place:
    normalized = normalize_place_code(code)
    existing = db.execute(select(Place).where(Place.code == normalized)).scalar_one_or_none()
    if existing:
        return existing

    place = Place(
        code=normalized,
        name=default_name,
        city=city,
        country=country,
    )
    db.add(place)
    db.flush()
    return place


def find_place_by_wa_number(db: Session, wa_number: str | None) -> Place | None:
    if not wa_number:
        return None
    return db.execute(select(Place).where(Place.wa_number == wa_number)).scalar_one_or_none()
