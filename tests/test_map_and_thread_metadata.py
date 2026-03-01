import json

from app.core.config import get_settings


def _admin_headers():
    return {"X-Admin-Api-Key": "admin-secret"}


def test_admin_map_points_and_heatmap_endpoints(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    payloads = [
        {
            "text": "Me gusta este lugar, esta mas tranquilo y verde.",
            "place_code": "alameda-santiago",
            "latitude": -33.444,
            "longitude": -70.66,
        },
        {
            "text": "Da miedo caminar de noche, esta oscuro y peligroso.",
            "place_code": "alameda-santiago",
            "latitude": -33.446,
            "longitude": -70.662,
        },
    ]
    for payload in payloads:
        res = client.post("/ingest", json=payload)
        assert res.status_code == 200

    points_res = client.get(
        "/admin/places/1/map/points?period_days=30&limit=100",
        headers=_admin_headers(),
    )
    assert points_res.status_code == 200
    points = points_res.json()
    assert points["place_id"] == 1
    assert points["total"] >= 2
    assert all("sentiment_score" in item for item in points["points"])
    assert all("geo_avg_sentiment_score_500m" in item for item in points["points"])
    assert all("geo_neighbor_count_500m" in item for item in points["points"])

    heat_res = client.get(
        "/admin/places/1/map/heatmap?period_days=30&mode=negative&limit=100",
        headers=_admin_headers(),
    )
    assert heat_res.status_code == 200
    heat = heat_res.json()
    assert heat["place_id"] == 1
    assert heat["mode"] == "negative"
    assert "points" in heat

    heat_geo_res = client.get(
        "/admin/places/1/map/heatmap?period_days=30&mode=geo_avg&limit=100",
        headers=_admin_headers(),
    )
    assert heat_geo_res.status_code == 200
    heat_geo = heat_geo_res.json()
    assert heat_geo["mode"] == "geo_avg"

    grid_res = client.get(
        "/admin/places/1/map/grid?period_days=30&cell_m=100&limit=100",
        headers=_admin_headers(),
    )
    assert grid_res.status_code == 200
    grid = grid_res.json()
    assert grid["place_id"] == 1
    assert "cells" in grid
    assert grid["total_cells"] >= 1
    assert "sentiment_scale_label_es" in grid["cells"][0]
    assert "sentiment_scale_value" in grid["cells"][0]

    tl_res = client.get(
        "/admin/places/1/map/timelapse?period_days=30&mode=negative&granularity=day&limit=100",
        headers=_admin_headers(),
    )
    assert tl_res.status_code == 200
    tl = tl_res.json()
    assert tl["place_id"] == 1
    assert tl["mode"] == "negative"
    assert tl["granularity"] == "day"
    assert tl["total_points"] >= 2
    assert tl["total_frames"] >= 1
    assert len(tl["frames"]) >= 1

    get_settings.cache_clear()


def test_admin_map_view_page_renders_with_query_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    res = client.get("/admin/places/1/map/view?admin_api_key=admin-secret&period_days=30&mode=grid_avg")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "leaflet" in res.text.lower()
    assert "/admin/places/" in res.text
    assert "map/grid" in res.text
    assert "Diametro" in res.text

    get_settings.cache_clear()


def test_admin_session_cookie_allows_map_access(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()


def test_admin_review_table_view_renders_with_query_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    ingest = client.post(
        "/ingest",
        json={
            "text": "Mensaje para tabla admin",
            "place_code": "alameda-santiago",
        },
    )
    assert ingest.status_code == 200

    res = client.get("/admin/messages/review/view?admin_api_key=admin-secret&limit=50&offset=0")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Mensajes del sistema" in res.text
    assert "Mensaje para tabla admin" in res.text

    get_settings.cache_clear()

    login = client.post(
        "/admin/session/login",
        data={"admin_api_key": "admin-secret", "place_id": 1},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert "admin_session=" in login.headers.get("set-cookie", "")
    assert login.headers.get("location") == "/admin/home?place_id=1"

    # Cookie should be attached automatically by TestClient.
    home = client.get("/admin/home?place_id=1")
    assert home.status_code == 200
    assert "Admin Home" in home.text

    view = client.get("/admin/places/1/map/view")
    assert view.status_code == 200

    points = client.get("/admin/places/1/map/points?period_days=30&limit=10")
    assert points.status_code == 200

    get_settings.cache_clear()


def test_admin_home_renders_with_query_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    res = client.get("/admin/home?admin_api_key=admin-secret&place_id=1")
    assert res.status_code == 200
    assert "Admin Home" in res.text
    assert "/admin/messages/review/view" in res.text
    assert "/admin/places/1/map/view" in res.text

    get_settings.cache_clear()


def test_thread_messages_endpoint_returns_provider_metadata(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"display_phone_number": "100200300"},
                            "messages": [
                                {
                                    "id": "wamid.location.1",
                                    "from": "56970000001",
                                    "timestamp": "1700000000",
                                    "type": "location",
                                    "location": {
                                        "latitude": -33.447,
                                        "longitude": -70.665,
                                        "address": "Alameda test",
                                        "name": "Punto test",
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    hook = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert hook.status_code == 200

    threads = client.get("/places/1/threads?limit=5", headers=_admin_headers())
    assert threads.status_code == 200
    items = threads.json()
    assert len(items) >= 1
    thread_id = items[0]["id"]

    turns = client.get(f"/places/1/threads/{thread_id}/messages?limit=20", headers=_admin_headers())
    assert turns.status_code == 200
    turn_items = turns.json()
    assert len(turn_items) >= 1
    first_in = next(item for item in turn_items if item["direction"] == "IN")
    assert first_in["provider_msg_id"] == "wamid.location.1"
    assert first_in["provider_metadata"]["type"] == "location"
    assert first_in["provider_metadata"]["address"] == "Alameda test"

    get_settings.cache_clear()


def test_whatsapp_location_context_is_persisted_to_corpus_message(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    first_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"display_phone_number": "100200300"},
                            "messages": [
                                {
                                    "id": "wamid.loc.42",
                                    "from": "56970000042",
                                    "timestamp": "1700000000",
                                    "type": "location",
                                    "location": {
                                        "latitude": -33.448,
                                        "longitude": -70.666,
                                        "address": "Alameda location context",
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    second_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"display_phone_number": "100200300"},
                            "messages": [
                                {
                                    "id": "wamid.txt.42",
                                    "from": "56970000042",
                                    "timestamp": "1700000100",
                                    "type": "text",
                                    "text": {"body": "en la noche se pone peligroso"},
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }

    r1 = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(first_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(second_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert r2.status_code == 200

    points = client.get("/admin/places/1/map/points?period_days=365&limit=500", headers=_admin_headers())
    assert points.status_code == 200
    data = points.json()
    assert any(
        abs(p["latitude"] - (-33.448)) < 1e-6 and abs(p["longitude"] - (-70.666)) < 1e-6 for p in data["points"]
    )

    get_settings.cache_clear()
