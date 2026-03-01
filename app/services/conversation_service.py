import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConversationEntry, ConversationThread, ConversationTurn, Place
from app.schemas.ingest import IngestRequest
from app.services.ingest_service import ingest_message

Intent = Literal["GREETING", "GENERAL", "ANELO", "QUEJA", "PROPUESTA", "RELATO", "EMOCIONAL"]

GREETING_SET = {
    "hola",
    "buenas",
    "hey",
    "?",
    "buen dia",
    "buen día",
    "holi",
}

THEME_KEYWORDS = {
    "seguridad": ["miedo", "insegur", "robo", "asalto", "noche", "oscuro", "ilumin"],
    "ruido": ["ruido", "bulla", "gritos", "musica", "música"],
    "limpieza": ["basura", "sucio", "sucia", "olor", "desecho"],
    "movilidad": ["cruce", "vereda", "transito", "tránsito", "micro", "bus", "auto", "bici", "acces"],
    "sombra": ["arbol", "árbol", "sombra", "sol", "calor"],
}

ZONE_KEYWORDS = [
    "paradero",
    "esquina norte",
    "esquina sur",
    "esquina oriente",
    "esquina poniente",
    "metro",
    "entrada",
    "salida",
    "plaza",
    "puente",
]

TIME_KEYWORDS = [
    "noche",
    "dia",
    "mañana",
    "tarde",
    "madrugada",
    "hora punta",
]


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def hash_user_id(phone: str) -> str:
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()


def classify_intent_heuristic(text: str) -> Intent | None:
    raw = text.strip()
    norm = _normalize_text(raw)

    if len(norm) <= 5 or norm in GREETING_SET:
        return "GREETING"

    if any(x in norm for x in ["deberia", "debería", "propongo", "seria bueno", "sería bueno", "hagamos", "quiero que haya"]):
        return "PROPUESTA"

    if any(x in norm for x in ["ojala", "ojalá", "me gustaria", "me gustaría", "sueño con", "sueño", "quisiera"]):
        return "ANELO"

    if any(x in norm for x in ["me da miedo", "me siento", "ansiedad", "inseguro", "insegura", "triste", "rabia"]):
        return "EMOCIONAL"

    if any(x in norm for x in ["mal", "horrible", "pesimo", "pésimo", "asqueroso", "no hay", "falta", "basura", "ruido"]):
        return "QUEJA"

    if len(raw) > 240 or any(x in norm for x in ["ayer", "hoy", "anoche", "cuando"]):
        return "RELATO"

    if len(norm) <= 18:
        return "GENERAL"

    return None


def _short_name(text: str) -> str:
    tokens = text.strip().split()
    if not tokens:
        return "sin contenido"
    return " ".join(tokens[:9])


def _question_by_intent(intent: Intent) -> str:
    if intent in {"ANELO", "PROPUESTA"}:
        return "¿En que parte exacta del lugar se nota mas?"
    if intent == "QUEJA":
        return "¿Que lo provoca o que lo hace peor?"
    if intent == "EMOCIONAL":
        return "¿Que situacion concreta te hace sentir asi en este lugar?"
    if intent == "RELATO":
        return "Si pudieras cambiar una sola cosa primero, ¿cual seria?"
    return "¿Que te inquieta mas de este lugar hoy?"


def _pick_variant(seed: str, options: list[str]) -> str:
    idx = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(options)
    return options[idx]


def _detect_themes(text: str) -> list[str]:
    norm = _normalize_text(text)
    themes: list[str] = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword in norm for keyword in keywords):
            themes.append(theme)
    if not themes:
        themes.append("general")
    return themes[:3]


def _extract_context_memory(text: str) -> tuple[str | None, str | None, str | None]:
    norm = _normalize_text(text)

    themes = _detect_themes(text)
    theme = themes[0] if themes and themes[0] != "general" else None

    zone = next((keyword for keyword in ZONE_KEYWORDS if keyword in norm), None)
    if zone is None:
        if "esquina" in norm:
            zone = "esquina"
        elif "cuadra" in norm:
            zone = "cuadra"

    time_ref = next((keyword for keyword in TIME_KEYWORDS if keyword in norm), None)

    return theme, zone, time_ref


def _local_consolidate(initial_text: str, user_text: str, intent: Intent | None) -> tuple[str, dict]:
    pieces = [piece.strip() for piece in [initial_text, user_text] if piece and piece.strip()]
    refined = "\n".join(pieces)[:600]
    theme_source = " ".join(pieces)
    themes = _detect_themes(theme_source)

    urgency = "media"
    if any(x in _normalize_text(theme_source) for x in ["peligro", "miedo", "urgente", "asalto", "accidente"]):
        urgency = "alta"
    elif intent in {"ANELO", "PROPUESTA"}:
        urgency = "baja"

    valence = "mixto"
    if intent in {"QUEJA", "EMOCIONAL"}:
        valence = "negativo"
    elif intent in {"ANELO", "PROPUESTA"}:
        valence = "positivo"

    labels = {"themes": themes, "urgency": urgency, "valence": valence}
    return refined, labels


def _merge_context(existing: str | None, incoming: str | None) -> str | None:
    return incoming or existing


def _merge_float(existing: float | None, incoming: float | None) -> float | None:
    return incoming if incoming is not None else existing


def _compose_first_reply(intent: Intent, text: str, thread_id: str, named: str | None = None, question: str | None = None) -> str:
    if intent in {"GREETING", "GENERAL"}:
        prompt = _pick_variant(
            seed=f"{thread_id}:greeting",
            options=[
                "¿Que parte te preocupa mas hoy?",
                "¿Que te gustaria que cambiara primero?",
                "¿En que punto se nota mas lo que mencionas?",
            ],
        )
        return (
            "Te lei. Quiero entenderlo bien en una linea mas.\n"
            f"{prompt}"
        )

    line = named or _short_name(text)
    if intent in {"QUEJA", "EMOCIONAL"}:
        q = "¿Es mas por seguridad, ruido, limpieza o movilidad?"
    else:
        q = question or _pick_variant(
            seed=f"{thread_id}:{intent}",
            options=[
                _question_by_intent(intent),
                "¿En que momento del dia ocurre mas?",
                "¿A quien afecta mas directamente?",
            ],
        )
    return f"Te leo asi: {line}.\n{q}"


CLOSING_TEXT = (
    "Tu mensaje ya se incorporo al corpus de este lugar.\n"
    "Se suma a otras voces que tambien lo estan pensando.\n"
    "Si quieres, puedo dejarlo mas preciso en un ultimo mensaje."
)


@dataclass
class ConversationResult:
    reply: str | None
    state: str
    entry_id: str | None = None
    corpus_message_id: str | None = None
    secondary_reply: str | None = None


def _is_low_info(text: str) -> bool:
    norm = _normalize_text(text)
    return norm in {"no se", "no sé", "da igual", "nada", "no"} or len(norm) < 4


def _compose_followup_from_memory(thread: ConversationThread) -> str:
    if thread.context_zone:
        return f"Para ubicarlo bien: ¿que pasa exactamente en {thread.context_zone}?"
    if thread.context_time:
        return f"¿Que cambia en la {thread.context_time} frente a otros horarios?"
    if thread.context_theme:
        if thread.context_theme == "seguridad":
            return "¿Lo principal ahi es iluminacion, presencia de gente o vigilancia?"
        if thread.context_theme == "movilidad":
            return "¿El problema es cruce, vereda, velocidad o senaletica?"
        if thread.context_theme == "limpieza":
            return "¿Es un punto puntual o algo constante durante el dia?"
    return _question_by_intent(thread.last_intent or "GENERAL")


def get_or_create_thread(db: Session, place_id: int, user_id: str, max_turns: int = 3) -> ConversationThread:
    thread = db.execute(
        select(ConversationThread)
        .where(
            ConversationThread.place_id == place_id,
            ConversationThread.user_id == user_id,
            ConversationThread.state.in_(["NEW", "COLLECTING", "CLOSING", "WAITING_LOCATION", "WAITING_TEXT"]),
        )
        .order_by(ConversationThread.updated_at.desc())
    ).scalar_one_or_none()

    if thread:
        return thread

    thread = ConversationThread(
        place_id=place_id,
        channel="whatsapp",
        user_id=user_id,
        state="NEW",
        turn_count=0,
        max_turns=max_turns,
    )
    db.add(thread)
    db.flush()
    return thread


def add_turn(
    db: Session,
    thread_id: str,
    direction: str,
    raw_text: str,
    provider_msg_id: str | None,
    provider_metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> ConversationTurn:
    turn = ConversationTurn(
        thread_id=thread_id,
        direction=direction,
        raw_text=raw_text,
        provider_msg_id=provider_msg_id,
        provider_metadata=provider_metadata,
    )
    if timestamp is not None:
        turn.timestamp = timestamp
    db.add(turn)
    db.flush()
    return turn


def handle_thread_message(
    db: Session,
    thread: ConversationThread,
    text: str,
    place: Place,
    latitude: float | None = None,
    longitude: float | None = None,
    place_reference: str | None = None,
) -> ConversationResult:
    if thread.turn_count >= thread.max_turns:
        return ConversationResult(reply=None, state=thread.state)

    if thread.state == "NEW":
        heuristic = classify_intent_heuristic(text)
        intent = heuristic or "GENERAL"
        named = _short_name(text)
        question = _question_by_intent(intent)
        theme, zone, time_ref = _extract_context_memory(text)

        reply = _compose_first_reply(intent, text, thread_id=thread.id, named=named, question=question)
        thread.state = "COLLECTING"
        thread.turn_count += 1
        thread.initial_text = text
        thread.last_intent = intent
        thread.context_theme = theme
        thread.context_zone = zone
        thread.context_time = time_ref
        thread.context_latitude = _merge_float(thread.context_latitude, latitude)
        thread.context_longitude = _merge_float(thread.context_longitude, longitude)
        thread.context_place_reference = _merge_context(thread.context_place_reference, place_reference)
        db.flush()
        return ConversationResult(reply=reply, state=thread.state)

    if thread.state == "COLLECTING":
        theme, zone, time_ref = _extract_context_memory(text)
        thread.context_theme = _merge_context(thread.context_theme, theme)
        thread.context_zone = _merge_context(thread.context_zone, zone)
        thread.context_time = _merge_context(thread.context_time, time_ref)
        thread.context_latitude = _merge_float(thread.context_latitude, latitude)
        thread.context_longitude = _merge_float(thread.context_longitude, longitude)
        thread.context_place_reference = _merge_context(thread.context_place_reference, place_reference)

        if _is_low_info(text) and thread.turn_count < max(2, thread.max_turns - 1):
            followup = _compose_followup_from_memory(thread)
            thread.turn_count += 1
            db.flush()
            return ConversationResult(reply=followup, state=thread.state)

        initial = thread.initial_text or ""
        refined_text, labels = _local_consolidate(initial, text, thread.last_intent)

        entry = ConversationEntry(
            thread_id=thread.id,
            place_id=thread.place_id,
            user_id=thread.user_id,
            initial_text=initial,
            refined_text=refined_text,
            labels=labels,
        )
        db.add(entry)
        db.flush()

        corpus = ingest_message(
            db,
            IngestRequest(
                text=refined_text,
                place_code=place.code,
                latitude=thread.context_latitude,
                longitude=thread.context_longitude,
                place_reference=thread.context_place_reference,
            ),
        )

        entry.corpus_message_id = corpus.message_id
        thread.state = "CLOSED"
        thread.turn_count += 1
        db.flush()

        return ConversationResult(
            reply=CLOSING_TEXT,
            state=thread.state,
            entry_id=entry.id,
            corpus_message_id=corpus.message_id,
            secondary_reply=(
                "Si quieres corregir o ajustar la representacion, usa este enlace: "
                f"{corpus.feedback_link}"
            ),
        )

    # CLOSED
    if thread.turn_count < thread.max_turns:
        thread.turn_count += 1
        db.flush()
        return ConversationResult(
            reply="Este hilo ya quedo incorporado. Si quieres, deja un nuevo mensaje para abrir otro.",
            state=thread.state,
        )

    return ConversationResult(reply=None, state=thread.state)
