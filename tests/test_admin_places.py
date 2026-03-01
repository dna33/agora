from app.core.config import get_settings


def _admin_headers():
    return {"X-Admin-Api-Key": "admin-secret"}


def test_admin_places_and_segments_crud(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    create_place = client.post(
        "/admin/places",
        headers=_admin_headers(),
        json={
            "code": "Valparaiso-Centro",
            "name": "Centro de Valparaiso",
            "city": "Valparaiso",
            "country": "Chile",
        },
    )
    assert create_place.status_code == 200
    assert create_place.json()["code"] == "valparaiso-centro"

    list_places = client.get("/admin/places", headers=_admin_headers())
    assert list_places.status_code == 200
    assert any(p["code"] == "valparaiso-centro" for p in list_places.json())

    create_segment = client.post(
        "/admin/places/valparaiso-centro/segments",
        headers=_admin_headers(),
        json={
            "name": "Plaza Victoria",
            "order_index": 1,
            "min_lat": -33.046,
            "max_lat": -33.044,
            "min_lon": -71.627,
            "max_lon": -71.624,
        },
    )
    assert create_segment.status_code == 200

    list_segments = client.get("/admin/places/valparaiso-centro/segments", headers=_admin_headers())
    assert list_segments.status_code == 200
    segments = list_segments.json()
    assert len(segments) == 1
    assert segments[0]["name"] == "Plaza Victoria"

    ingest = client.post(
        "/ingest",
        json={
            "text": "Camino por Plaza Victoria y necesito más sombra.",
            "place_code": "valparaiso-centro",
            "latitude": -33.045,
            "longitude": -71.625,
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["corridor_segment_id"] == segments[0]["id"]

    get_settings.cache_clear()


def test_admin_import_segments_from_csv(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    create_place = client.post(
        "/admin/places",
        headers=_admin_headers(),
        json={"code": "temuco-centro", "name": "Centro de Temuco"},
    )
    assert create_place.status_code == 200

    csv_text = (
        "name,order_index,min_lat,max_lat,min_lon,max_lon\n"
        "Segmento A,1,-38.741,-38.739,-72.600,-72.597\n"
        "Segmento B,2,-38.739,-38.736,-72.597,-72.594\n"
    )

    upload = client.post(
        "/admin/places/temuco-centro/segments/import",
        headers=_admin_headers(),
        files={"file": ("segments.csv", csv_text, "text/csv")},
    )
    assert upload.status_code == 200
    assert upload.json()["created"] == 2

    list_segments = client.get("/admin/places/temuco-centro/segments", headers=_admin_headers())
    assert list_segments.status_code == 200
    assert len(list_segments.json()) == 2

    get_settings.cache_clear()
