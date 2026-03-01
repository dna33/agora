import base64
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.security import token_hash
from app.services.model_service import ModelService


def _token_from_feedback_link(link: str) -> str:
    parts = [part for part in urlparse(link).path.split("/") if part]
    if len(parts) >= 3 and parts[-1] == "edit" and parts[-3] == "feedback":
        return parts[-2]
    if len(parts) >= 2 and parts[-2] == "feedback":
        return parts[-1]
    raise AssertionError(f"Unexpected feedback link format: {link}")


def test_ingest_and_feedback_versioning(client):
    ingest_payload = {
        "text": "Cruzar la Alameda aquí es peligroso en la noche, falta mejor iluminación y cruces más claros.",
        "place_code": "alameda-santiago",
        "latitude": -33.444,
        "longitude": -70.66,
        "presence_mode": "walking",
        "place_reference": "Alameda con Santa Rosa",
    }

    ingest_res = client.post("/ingest", json=ingest_payload)
    assert ingest_res.status_code == 200
    body = ingest_res.json()

    assert body["analysis_version"] == 1
    assert body["source_type"] == "text"
    assert body["feedback_link"].startswith(("http://", "https://"))
    token = _token_from_feedback_link(body["feedback_link"])
    assert len(token_hash(token)) == 64

    view_res = client.get(f"/feedback/{token}")
    assert view_res.status_code == 200
    view = view_res.json()
    assert view["latest_version"] == 1
    assert "place_reference" in view
    assert view["primary_topic"] in {
        "mobility",
        "safety",
        "public_space",
        "environment",
        "commerce",
        "care",
        "culture",
        "other",
    }

    edit_res = client.get(f"/feedback/{token}/edit")
    assert edit_res.status_code == 200
    assert "text/html" in edit_res.headers["content-type"]
    assert "Revisar representacion de tu mensaje" in edit_res.text
    assert "Movilidad" in edit_res.text
    assert "Noches mas seguras" in edit_res.text
    assert "Flujo vs permanencia" in edit_res.text
    assert "Cuidar lo que ya funciona" in edit_res.text
    assert "Calma vs vitalidad" in edit_res.text
    assert "Volver a WhatsApp" in edit_res.text

    patch_res = client.patch(
        f"/feedback/{token}",
        json={
            "primary_topic": "safety",
            "desired_future": "safer_nights",
            "summary_line": "Se percibe riesgo nocturno y se piden mejoras en iluminación y cruces.",
            "place_reference": "Esquina nororiente frente al paradero",
            "allow_public_quote": False,
        },
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["new_version"] == 2
    assert patched["allow_public_quote"] is False
    assert patched["place_reference"] == "Esquina nororiente frente al paradero"

    final_view = client.get(f"/feedback/{token}")
    assert final_view.status_code == 200
    final_body = final_view.json()
    assert final_body["latest_version"] == 2
    assert final_body["primary_topic"] == "safety"
    assert final_body["allow_public_quote"] is False
    assert final_body["place_reference"] == "Esquina nororiente frente al paradero"


def test_ingest_with_new_place_code(client):
    res = client.post(
        "/ingest",
        json={
            "text": "Este es un test para otro territorio fuera de Alameda.",
            "place_code": "centro-valparaiso",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["analysis_version"] == 1
    assert body["message_id"]


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_feedback_patch_validation_messages_in_spanish(client):
    ingest_res = client.post(
        "/ingest",
        json={"text": "Mensaje para validar feedback", "place_code": "alameda-santiago"},
    )
    assert ingest_res.status_code == 200
    token = _token_from_feedback_link(ingest_res.json()["feedback_link"])

    invalid_res = client.patch(
        f"/feedback/{token}",
        json={
            "primary_topic": "invalid-topic",
            "summary_line": "x",
        },
    )
    assert invalid_res.status_code == 422
    payload = invalid_res.json()
    msgs = [item["msg"] for item in payload["detail"]]
    assert any("Tema principal invalido" in msg for msg in msgs)
    assert any("El resumen debe tener al menos 3 caracteres." in msg for msg in msgs)


def test_ingest_audio_with_local_transcribe_provider(client, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_PROVIDER", "local")
    get_settings.cache_clear()
    monkeypatch.setattr(ModelService, "_transcribe_local", lambda self, _audio_b64: "transcripcion local ok")

    audio_b64 = base64.b64encode(b"fake-audio-bytes").decode("utf-8")
    ingest_res = client.post(
        "/ingest",
        json={
            "audio_base64": audio_b64,
            "audio_seconds": 2.0,
            "place_code": "alameda-santiago",
        },
    )
    assert ingest_res.status_code == 200
    body = ingest_res.json()
    assert body["source_type"] == "audio"
    assert body["analysis_version"] == 1
    get_settings.cache_clear()
