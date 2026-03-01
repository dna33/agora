import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.ingest import IngestRequest
from app.schemas.integrations import WhatsAppWebhookResponse
from app.services.model_service import ModelService
from app.services.conversation_service import (
    add_turn,
    get_or_create_thread,
    handle_thread_message,
    hash_user_id,
)
from app.services.place_service import find_place_by_wa_number, get_or_create_place
from app.services.whatsapp_outbound_service import WhatsAppOutboundService
from app.services.ingest_service import ingest_message

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    text: str
    provider_msg_id: str | None = None
    provider_timestamp: datetime | None = None
    provider_metadata: dict | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_reference: str | None = None


def _short_user_phrase(text: str) -> str:
    tokens = [t for t in text.strip().split() if t]
    if not tokens:
        return "mensaje recibido"
    return " ".join(tokens[:16])


def _generate_local_reply_line(text: str) -> str | None:
    settings = get_settings()
    base_url = (settings.local_llm_base_url or "").strip().rstrip("/")
    model = (settings.local_llm_model_extract or "").strip()
    if not base_url or not model:
        return None

    headers = {"Content-Type": "application/json"}
    if settings.local_llm_api_key:
        headers["Authorization"] = f"Bearer {settings.local_llm_api_key}"

    payload = {
        "model": model,
        "temperature": 0.35,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres Agora, sistema civico. Responde en espanol Chile con 1 o 2 lineas breves, "
                    "sin emojis, sin promesas, sin inventar datos, sin usar la frase 'Te leo asi'. "
                    "Tu objetivo es responder al contenido del mensaje con tono claro y respetuoso."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Responde al mensaje de la persona con una devolucion concreta y natural. "
                    f"Mensaje: {text}"
                ),
            },
        ],
    }

    try:
        with httpx.Client(timeout=8) as client:
            res = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            if res.status_code == 404:
                root = base_url[:-3] if base_url.endswith("/v1") else base_url
                ollama_payload = {
                    "model": model,
                    "messages": payload["messages"],
                    "stream": False,
                    "options": {"temperature": 0.35},
                }
                res = client.post(f"{root}/api/chat", headers=headers, json=ollama_payload)
                res.raise_for_status()
                data = res.json()
                content = (data.get("message") or {}).get("content", "")
            else:
                res.raise_for_status()
                data = res.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        line = str(content or "").strip().replace("\n", " ")
        if not line:
            return None
        if "te leo asi" in line.lower():
            return None
        return line[:280]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local reply fallback due to local model error: %s", exc)
        return None


def _compose_location_request_reply(text: str) -> str:
    ack = _generate_local_reply_line(text) or f"Gracias por compartirlo. Entiendo tu punto sobre: {_short_user_phrase(text)}."
    return (
        f"{ack}\n"
        "Lo voy a clasificar y despues podras revisarlo y corregir lo que haga falta.\n"
        "Para ubicarlo bien en el mapa, presiona + o el clip, "
        "luego Ubicacion y Enviar ubicacion actual."
    )


def _parse_meta_timestamp(raw: str | int | None) -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _meta_fetch_media_bytes(media_id: str) -> tuple[bytes, str]:
    settings = get_settings()
    if not settings.whatsapp_access_token:
        raise ValueError("WHATSAPP_ACCESS_TOKEN is required to fetch Meta media")

    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    meta_url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{media_id}"
    with httpx.Client(timeout=30) as client:
        meta_res = client.get(meta_url, headers=headers)
        meta_res.raise_for_status()
        media_info = meta_res.json()
        download_url = media_info.get("url")
        if not download_url:
            raise ValueError("Meta media URL missing in Graph API response")

        media_res = client.get(download_url, headers=headers)
        media_res.raise_for_status()
        content_type = media_res.headers.get("Content-Type", "audio/ogg")
        return media_res.content, content_type


def _meta_transcribe_audio(db: Session, media_id: str) -> str | None:
    try:
        audio_bytes, _content_type = _meta_fetch_media_bytes(media_id)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        # WhatsApp audio path is strict-local: never call OpenAI for transcription.
        return ModelService().transcribe_local_strict(
            db=db,
            audio_b64=audio_b64,
            audio_seconds=None,
            message_id=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to process Meta audio media_id=%s: %s", media_id, exc)
        return None


def _to_float(raw: str | float | int | None) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _ingest_incoming_messages(db: Session, provider: str, messages: list[IncomingMessage]) -> WhatsAppWebhookResponse:
    if not messages:
        return WhatsAppWebhookResponse(accepted=False, detail="No supported message content", provider=provider)

    last_message_id: str | None = None
    for msg in messages:
        result = ingest_message(
            db,
            IngestRequest(
                text=msg.text,
                latitude=msg.latitude,
                longitude=msg.longitude,
                place_reference=msg.place_reference,
            ),
        )
        last_message_id = result.message_id

    return WhatsAppWebhookResponse(
        accepted=True,
        message_id=last_message_id,
        detail=f"{provider} WhatsApp message(s) ingested",
        provider=provider,
        ingested_count=len(messages),
    )


def twilio_compute_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params.keys()))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def meta_compute_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _normalize_twilio_text(body: str | None, num_media: int, media_content_type: str | None) -> str | None:
    if body and body.strip():
        return body.strip()
    if num_media > 0:
        media_desc = media_content_type or "unknown"
        return f"[WhatsApp media message: {media_desc}]"
    return None


def process_whatsapp_message(
    db: Session,
    body: str | None,
    latitude: float | None,
    longitude: float | None,
    address: str | None,
) -> WhatsAppWebhookResponse:
    text = body.strip() if body and body.strip() else None
    if not text:
        return WhatsAppWebhookResponse(accepted=False, detail="No text body provided", provider="generic")

    return _ingest_incoming_messages(
        db,
        provider="generic",
        messages=[
            IncomingMessage(
                text=text,
                latitude=latitude,
                longitude=longitude,
                place_reference=address,
            )
        ],
    )


def process_twilio_whatsapp_webhook(
    db: Session,
    url: str,
    form_data: dict[str, Any],
    twilio_signature: str | None,
) -> WhatsAppWebhookResponse:
    settings = get_settings()

    params = {k: str(v) for k, v in form_data.items()}
    if settings.twilio_validate_signature:
        if not settings.twilio_auth_token:
            raise HTTPException(status_code=500, detail="Webhook authentication misconfigured")
        if not twilio_signature:
            raise HTTPException(status_code=403, detail="Unauthorized webhook request")

        expected = twilio_compute_signature(url=url, params=params, auth_token=settings.twilio_auth_token)
        if not hmac.compare_digest(expected, twilio_signature):
            raise HTTPException(status_code=403, detail="Unauthorized webhook request")

    num_media_raw = params.get("NumMedia", "0")
    try:
        num_media = int(num_media_raw)
    except ValueError:
        num_media = 0

    text = _normalize_twilio_text(
        body=params.get("Body"),
        num_media=num_media,
        media_content_type=params.get("MediaContentType0"),
    )
    if not text:
        return WhatsAppWebhookResponse(accepted=False, detail="No supported message content", provider="twilio")

    return _ingest_incoming_messages(
        db,
        provider="twilio",
        messages=[
            IncomingMessage(
                text=text,
                latitude=_to_float(params.get("Latitude")),
                longitude=_to_float(params.get("Longitude")),
                place_reference=params.get("Address") or params.get("FromCity"),
            )
        ],
    )


def process_meta_whatsapp_webhook(
    db: Session,
    raw_body: bytes,
    meta_signature: str | None,
) -> WhatsAppWebhookResponse:
    settings = get_settings()

    if settings.meta_validate_signature:
        if not settings.meta_app_secret:
            raise HTTPException(status_code=500, detail="Webhook authentication misconfigured")
        if not meta_signature:
            raise HTTPException(status_code=403, detail="Unauthorized webhook request")

        expected = meta_compute_signature(raw_body=raw_body, app_secret=settings.meta_app_secret)
        if not hmac.compare_digest(expected, meta_signature):
            raise HTTPException(status_code=403, detail="Unauthorized webhook request")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    messages_to_ingest: list[IncomingMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                msg_type = msg.get("type")

                if msg_type == "text":
                    text = (msg.get("text") or {}).get("body", "").strip()
                    if text:
                        messages_to_ingest.append(
                            IncomingMessage(
                                text=text,
                                provider_msg_id=msg.get("id"),
                                provider_timestamp=_parse_meta_timestamp(msg.get("timestamp")),
                                provider_metadata={"type": "text"},
                            )
                        )
                elif msg_type == "location":
                    location = msg.get("location") or {}
                    address = location.get("address") or location.get("name")
                    lat = _to_float(location.get("latitude"))
                    lon = _to_float(location.get("longitude"))
                    text = f"[WhatsApp location message] {address or 'no address'}"
                    messages_to_ingest.append(
                        IncomingMessage(
                            text=text,
                            provider_msg_id=msg.get("id"),
                            provider_timestamp=_parse_meta_timestamp(msg.get("timestamp")),
                            provider_metadata={
                                "type": "location",
                                "latitude": lat,
                                "longitude": lon,
                                "address": address,
                                "name": location.get("name"),
                            },
                            latitude=lat,
                            longitude=lon,
                            place_reference=address,
                        )
                    )
                elif msg_type in {"audio", "image", "video", "document"}:
                    if msg_type == "audio":
                        audio_obj = msg.get("audio") or {}
                        media_id = audio_obj.get("id")
                        if media_id:
                            transcript = _meta_transcribe_audio(db, str(media_id))
                            if transcript and transcript.strip():
                                messages_to_ingest.append(
                                    IncomingMessage(
                                        text=transcript.strip(),
                                        provider_msg_id=msg.get("id"),
                                        provider_timestamp=_parse_meta_timestamp(msg.get("timestamp")),
                                        provider_metadata={
                                            "type": "audio",
                                            "media_id": media_id,
                                            "mime_type": audio_obj.get("mime_type"),
                                        },
                                    )
                                )
                            else:
                                messages_to_ingest.append(
                                    IncomingMessage(
                                        text="[WhatsApp audio message: transcription unavailable]",
                                        provider_msg_id=msg.get("id"),
                                        provider_timestamp=_parse_meta_timestamp(msg.get("timestamp")),
                                        provider_metadata={
                                            "type": "audio",
                                            "media_id": media_id,
                                            "mime_type": audio_obj.get("mime_type"),
                                            "transcription": "unavailable",
                                        },
                                    )
                                )
                        else:
                            messages_to_ingest.append(
                                IncomingMessage(
                                    text="[WhatsApp audio message: missing media id]",
                                    provider_msg_id=msg.get("id"),
                                    provider_timestamp=_parse_meta_timestamp(msg.get("timestamp")),
                                    provider_metadata={"type": "audio", "media_id": None},
                                )
                            )
                    else:
                        messages_to_ingest.append(
                            IncomingMessage(
                                text=f"[WhatsApp media message: {msg_type}]",
                                provider_msg_id=msg.get("id"),
                                provider_timestamp=_parse_meta_timestamp(msg.get("timestamp")),
                                provider_metadata={"type": msg_type},
                            )
                        )

    if not messages_to_ingest:
        return WhatsAppWebhookResponse(accepted=False, detail="No supported message content", provider="meta")

    outbound = WhatsAppOutboundService()
    metadata_wa_number = None
    sender_wa_id = None
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            metadata_wa_number = metadata_wa_number or metadata.get("display_phone_number")
            for msg in value.get("messages", []):
                sender_wa_id = sender_wa_id or msg.get("from")

    place = find_place_by_wa_number(db, metadata_wa_number)
    if place is None:
        place = get_or_create_place(
            db,
            code=settings.default_place_code,
            default_name=settings.default_place_name,
            city=settings.default_place_city,
            country=settings.default_place_country,
        )

    user_id = hash_user_id(sender_wa_id or "unknown")
    max_turns = 3
    if place.settings and isinstance(place.settings, dict):
        max_turns = int(place.settings.get("max_turns", 3))
    thread = get_or_create_thread(db, place_id=place.id, user_id=user_id, max_turns=max_turns)
    single_turn_mode = bool(settings.whatsapp_single_turn_mode)

    for msg in messages_to_ingest:
        add_turn(
            db,
            thread_id=thread.id,
            direction="IN",
            raw_text=msg.text,
            provider_msg_id=msg.provider_msg_id,
            provider_metadata=msg.provider_metadata,
            timestamp=msg.provider_timestamp,
        )

        if single_turn_mode:
            # UX flow:
            # 1) user sends content (text/audio) -> ask for location
            # 2) user sends location -> ingest with geo + send feedback link
            if thread.state == "NEW":
                if msg.latitude is not None and msg.longitude is not None:
                    thread.context_latitude = msg.latitude
                    thread.context_longitude = msg.longitude
                    thread.context_place_reference = msg.place_reference
                    thread.state = "WAITING_TEXT"
                    thread.turn_count = max(thread.turn_count + 1, 1)
                    db.flush()
                    remind = (
                        "Recibi tu ubicacion.\n"
                        "Ahora cuentame en una frase que esta pasando en ese lugar."
                    )
                    if sender_wa_id and outbound.send_text(sender_wa_id, remind):
                        add_turn(
                            db,
                            thread_id=thread.id,
                            direction="OUT",
                            raw_text=remind,
                            provider_msg_id=None,
                        )
                    continue

                thread.initial_text = msg.text
                thread.state = "WAITING_LOCATION"
                thread.turn_count = max(thread.turn_count + 1, 1)
                db.flush()

                reply = _compose_location_request_reply(msg.text)
                if sender_wa_id and outbound.send_text(sender_wa_id, reply):
                    add_turn(
                        db,
                        thread_id=thread.id,
                        direction="OUT",
                        raw_text=reply,
                        provider_msg_id=None,
                    )
                continue

            if thread.state == "WAITING_TEXT":
                if msg.latitude is not None and msg.longitude is not None:
                    thread.context_latitude = msg.latitude
                    thread.context_longitude = msg.longitude
                    thread.context_place_reference = msg.place_reference
                    db.flush()
                    remind = "Ya tengo tu ubicacion. Ahora cuentame el mensaje en una frase."
                    if sender_wa_id and outbound.send_text(sender_wa_id, remind):
                        add_turn(
                            db,
                            thread_id=thread.id,
                            direction="OUT",
                            raw_text=remind,
                            provider_msg_id=None,
                        )
                    continue

                corpus = ingest_message(
                    db,
                    IngestRequest(
                        text=msg.text,
                        place_code=place.code,
                        latitude=thread.context_latitude,
                        longitude=thread.context_longitude,
                        place_reference=thread.context_place_reference,
                    ),
                )
                thread.initial_text = msg.text
                thread.state = "CLOSED"
                thread.turn_count = max(thread.turn_count + 1, 2)
                db.flush()

                reply = (
                    "Perfecto, ya lo incorpore con ubicacion.\n"
                    "Revisa y corrige su representacion aqui (tambien puedes nombrar el lugar): "
                    f"{corpus.feedback_link}"
                )
                if sender_wa_id and outbound.send_text(sender_wa_id, reply):
                    add_turn(
                        db,
                        thread_id=thread.id,
                        direction="OUT",
                        raw_text=reply,
                        provider_msg_id=None,
                    )
                continue

            if thread.state == "WAITING_LOCATION":
                if msg.latitude is None or msg.longitude is None:
                    remind = (
                        "Gracias. Para dejarlo bien ubicado en el mapa, presiona + o el clip, "
                        "luego Ubicacion y Enviar ubicacion actual."
                    )
                    if sender_wa_id and outbound.send_text(sender_wa_id, remind):
                        add_turn(
                            db,
                            thread_id=thread.id,
                            direction="OUT",
                            raw_text=remind,
                            provider_msg_id=None,
                        )
                    continue

                corpus = ingest_message(
                    db,
                    IngestRequest(
                        text=thread.initial_text or msg.text,
                        place_code=place.code,
                        latitude=msg.latitude,
                        longitude=msg.longitude,
                        place_reference=msg.place_reference,
                    ),
                )
                thread.state = "CLOSED"
                thread.turn_count = max(thread.turn_count + 1, 2)
                db.flush()

                reply = (
                    "Perfecto, ya lo incorpore con ubicacion.\n"
                    "Revisa y corrige su representacion aqui (tambien puedes nombrar el lugar): "
                    f"{corpus.feedback_link}"
                )
                if sender_wa_id and outbound.send_text(sender_wa_id, reply):
                    add_turn(
                        db,
                        thread_id=thread.id,
                        direction="OUT",
                        raw_text=reply,
                        provider_msg_id=None,
                    )
                continue

            # CLOSED
            closed = "Este registro ya quedo guardado. Si quieres, envia un nuevo mensaje para abrir otro."
            if sender_wa_id and outbound.send_text(sender_wa_id, closed):
                add_turn(
                    db,
                    thread_id=thread.id,
                    direction="OUT",
                    raw_text=closed,
                    provider_msg_id=None,
                )
            continue

        result = handle_thread_message(
            db,
            thread,
            msg.text,
            place,
            latitude=msg.latitude,
            longitude=msg.longitude,
            place_reference=msg.place_reference,
        )
        if result.reply and sender_wa_id and outbound.send_text(sender_wa_id, result.reply):
            add_turn(
                db,
                thread_id=thread.id,
                direction="OUT",
                raw_text=result.reply,
                provider_msg_id=None,
            )
        if result.secondary_reply and sender_wa_id and outbound.send_text(sender_wa_id, result.secondary_reply):
            add_turn(
                db,
                thread_id=thread.id,
                direction="OUT",
                raw_text=result.secondary_reply,
                provider_msg_id=None,
            )

    db.commit()
    return WhatsAppWebhookResponse(
        accepted=True,
        message_id=thread.id,
        detail="meta WhatsApp message(s) processed",
        provider="meta",
        ingested_count=len(messages_to_ingest),
    )


def verify_meta_webhook(mode: str | None, verify_token: str | None, challenge: str | None) -> str:
    settings = get_settings()
    if mode != "subscribe":
        raise HTTPException(status_code=400, detail="Invalid hub.mode")
    if not settings.meta_webhook_verify_token:
        raise HTTPException(status_code=500, detail="Webhook verification misconfigured")
    if verify_token != settings.meta_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Unauthorized webhook verification")
    if challenge is None:
        raise HTTPException(status_code=400, detail="Missing hub.challenge")
    return challenge
