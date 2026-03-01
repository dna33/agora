import json
from datetime import datetime, timezone

from app.core.config import get_settings
from app.services.conversation_service import ConversationResult
from app.services.whatsapp_service import meta_compute_signature, twilio_compute_signature
from app.services.whatsapp_outbound_service import WhatsAppOutboundService


def test_whatsapp_webhook_ingests_text(client):
    res = client.post(
        "/integrations/whatsapp/webhook",
        data={
            "Body": "Desde WhatsApp: falta sombra y lugares para esperar sin calor.",
            "Latitude": "-33.445",
            "Longitude": "-70.662",
            "Address": "Alameda con San Antonio",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] is True
    assert body["message_id"] is not None


def test_twilio_webhook_rejects_invalid_signature_when_enabled(client, monkeypatch):
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "super-secret")
    get_settings.cache_clear()

    res = client.post(
        "/integrations/whatsapp/twilio/webhook",
        headers={"X-Twilio-Signature": "invalid-signature"},
        data={"Body": "Mensaje de prueba Twilio"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "Unauthorized webhook request"

    get_settings.cache_clear()


def test_twilio_webhook_accepts_valid_signature(client, monkeypatch):
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "super-secret")
    get_settings.cache_clear()

    endpoint = "http://testserver/integrations/whatsapp/twilio/webhook"
    payload = {
        "Body": "Twilio firma válida",
        "Latitude": "-33.445",
        "Longitude": "-70.662",
        "Address": "Alameda",
    }
    signature = twilio_compute_signature(endpoint, payload, "super-secret")

    res = client.post(
        "/integrations/whatsapp/twilio/webhook",
        headers={"X-Twilio-Signature": signature},
        data=payload,
    )
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    assert res.json()["message_id"] is not None
    assert res.json()["provider"] == "twilio"

    get_settings.cache_clear()


def test_meta_webhook_verify_success(client, monkeypatch):
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "meta-verify-token")
    get_settings.cache_clear()

    res = client.get(
        "/integrations/whatsapp/meta/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "meta-verify-token",
            "hub.challenge": "12345",
        },
    )
    assert res.status_code == 200
    assert res.text == "12345"

    get_settings.cache_clear()


def test_meta_webhook_ingests_message_with_valid_signature(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "true")
    monkeypatch.setenv("META_APP_SECRET", "meta-secret")
    get_settings.cache_clear()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {"type": "text", "text": {"body": "Hola desde Meta WhatsApp"}},
                                {
                                    "type": "location",
                                    "location": {
                                        "latitude": -33.445,
                                        "longitude": -70.662,
                                        "address": "Alameda",
                                    },
                                },
                            ]
                        },
                    }
                ]
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    signature = meta_compute_signature(raw_body=raw, app_secret="meta-secret")

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] is True
    assert body["provider"] == "meta"
    assert body["ingested_count"] == 2

    get_settings.cache_clear()


def test_meta_webhook_sends_dialog_reply(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    get_settings.cache_clear()

    sent_messages: list[tuple[str, str]] = []

    def fake_send_text(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent_messages.append((to_wa_id, body))
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send_text)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": "56911111111",
                                    "type": "text",
                                    "text": {"body": "Hola Agora"},
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "56911111111"
    assert "presiona + o el clip" in sent_messages[0][1].lower()

    get_settings.cache_clear()


def test_meta_webhook_processes_audio_message(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    get_settings.cache_clear()

    sent_messages: list[tuple[str, str]] = []

    def fake_send_text(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent_messages.append((to_wa_id, body))
        return True

    def fake_transcribe(_db, _media_id: str):  # noqa: ANN001
        return "Ojala hubiera mas sombra en el paradero central"

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send_text)
    monkeypatch.setattr("app.services.whatsapp_service._meta_transcribe_audio", fake_transcribe)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": "56911111111",
                                    "type": "audio",
                                    "audio": {"id": "media123"},
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "56911111111"
    assert "presiona + o el clip" in sent_messages[0][1].lower()

    get_settings.cache_clear()


def test_meta_webhook_maps_location_and_timestamp_metadata(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    get_settings.cache_clear()

    captured_in_turns: list[dict] = []

    def fake_add_turn(db, thread_id, direction, raw_text, provider_msg_id, provider_metadata=None, timestamp=None):  # noqa: ANN001
        if direction == "IN":
            captured_in_turns.append(
                {
                    "thread_id": thread_id,
                    "direction": direction,
                    "raw_text": raw_text,
                    "provider_msg_id": provider_msg_id,
                    "provider_metadata": provider_metadata,
                    "timestamp": timestamp,
                }
            )
        return None

    def fake_handle(_db, thread, _text, _place, **_kwargs):  # noqa: ANN001
        return ConversationResult(reply=None, state=thread.state)

    monkeypatch.setattr("app.services.whatsapp_service.add_turn", fake_add_turn)
    monkeypatch.setattr("app.services.whatsapp_service.handle_thread_message", fake_handle)

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
                                    "id": "wamid.loc.1",
                                    "from": "56911111111",
                                    "timestamp": "1700000000",
                                    "type": "location",
                                    "location": {
                                        "latitude": -33.445,
                                        "longitude": -70.662,
                                        "address": "Alameda con San Antonio",
                                        "name": "Esquina",
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    assert len(captured_in_turns) == 1
    turn = captured_in_turns[0]
    assert turn["provider_msg_id"] == "wamid.loc.1"
    assert turn["provider_metadata"]["type"] == "location"
    assert turn["provider_metadata"]["latitude"] == -33.445
    assert turn["provider_metadata"]["longitude"] == -70.662
    assert turn["provider_metadata"]["address"] == "Alameda con San Antonio"
    assert turn["timestamp"] == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    get_settings.cache_clear()


def test_cluster_job_rejects_without_admin_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    res = client.post("/admin/jobs/cluster", json={"similarity_threshold": 0.7, "min_cluster_size": 2})
    assert res.status_code == 403
    assert res.json()["detail"] == "Forbidden"

    get_settings.cache_clear()


def test_cluster_job_creates_clusters(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    texts = [
        "Necesitamos mejores cruces para caminar seguro por la Alameda.",
        "Caminar por la Alameda en la noche da miedo por los cruces y poca luz.",
        "Más árboles y sombra para esperar la micro en verano.",
    ]
    for text in texts:
        ingest_res = client.post("/ingest", json={"text": text})
        assert ingest_res.status_code == 200

    cluster_res = client.post(
        "/admin/jobs/cluster",
        json={"similarity_threshold": 0.7, "min_cluster_size": 2},
        headers={"X-Admin-Api-Key": "admin-secret"},
    )
    assert cluster_res.status_code == 200
    payload = cluster_res.json()
    assert payload["processed_messages"] == 3
    assert payload["clusters_created"] >= 1
    assert payload["assignments_created"] >= 2

    get_settings.cache_clear()
