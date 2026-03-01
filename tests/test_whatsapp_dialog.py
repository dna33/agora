import json

from app.core.config import get_settings
from app.services.whatsapp_outbound_service import WhatsAppOutboundService


def _payload(text: str, sender: str = "56999999999") -> bytes:
    return json.dumps(
        {
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
                                        "id": "wamid.test",
                                        "from": sender,
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        }
    ).encode("utf-8")


def test_dialog_greeting_threshold_reply(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    sent: list[str] = []

    def fake_send(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent.append(body)
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send)
    get_settings.cache_clear()

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("hola"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert len(sent) == 1
    assert "presiona + o el clip" in sent[0].lower()
    assert "te leo asi" not in sent[0].lower()

    get_settings.cache_clear()


def test_dialog_anhelo_named_and_spatial_question(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    sent: list[str] = []

    def fake_send(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent.append(body)
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send)
    get_settings.cache_clear()

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("ojala hubiera mas arboles y sombra"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert len(sent) == 1
    assert "clasificar" in sent[0].lower()
    assert "ubicacion actual" in sent[0].lower()

    get_settings.cache_clear()


def test_dialog_queja_general_question(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    sent: list[str] = []

    def fake_send(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent.append(body)
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send)
    get_settings.cache_clear()

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("esta mal"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert len(sent) == 1
    assert "presiona + o el clip" in sent[0].lower()

    get_settings.cache_clear()


def test_dialog_emotional_question(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    sent: list[str] = []

    def fake_send(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent.append(body)
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send)
    get_settings.cache_clear()

    res = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("me da miedo caminar de noche aqui"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert len(sent) == 1
    assert "clasificar" in sent[0].lower()

    get_settings.cache_clear()


def test_dialog_message_then_location_creates_corpus_and_link(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    sent: list[str] = []

    def fake_send(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent.append(body)
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send)
    get_settings.cache_clear()

    first = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("ojala hubiera mas sombra", sender="56922222222"),
        headers={"Content-Type": "application/json"},
    )
    assert first.status_code == 200

    second = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=json.dumps(
            {
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
                                            "id": "wamid.loc.test",
                                            "from": "56922222222",
                                            "type": "location",
                                            "location": {
                                                "latitude": -33.445,
                                                "longitude": -70.662,
                                                "address": "Alameda con San Antonio",
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ],
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert second.status_code == 200

    assert len(sent) == 2
    assert "ubicacion" in sent[0].lower()
    assert "/feedback/" in sent[1]

    review = client.get(
        "/admin/messages/review?limit=20",
        headers={"X-Admin-Api-Key": "admin-secret"},
    )
    assert review.status_code == 200
    assert review.json()["total"] >= 1

    get_settings.cache_clear()


def test_dialog_without_location_gets_reminder(client, monkeypatch):
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    sent: list[str] = []

    def fake_send(self, to_wa_id: str, body: str):  # noqa: ANN001
        sent.append(body)
        return True

    monkeypatch.setattr(WhatsAppOutboundService, "send_text", fake_send)
    get_settings.cache_clear()

    first = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("me da miedo de noche en el paradero"),
        headers={"Content-Type": "application/json"},
    )
    assert first.status_code == 200

    second = client.post(
        "/integrations/whatsapp/meta/webhook",
        content=_payload("no se"),
        headers={"Content-Type": "application/json"},
    )
    assert second.status_code == 200

    assert len(sent) == 2
    assert "presiona + o el clip" in sent[1].lower()

    get_settings.cache_clear()
