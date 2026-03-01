import base64
import json
import logging
import tempfile
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.taxonomies import DESIRED_FUTURES, PRIMARY_TOPICS, TENSION_TYPES
from app.models import OpenAICallLog

logger = logging.getLogger(__name__)

# Placeholder costs for scaffolding. Replace with exact provider pricing before production.
PRICE_INPUT_PER_1K = 0.0004
PRICE_OUTPUT_PER_1K = 0.0016
PRICE_AUDIO_PER_SEC = 0.0001
PRICE_EMBED_PER_1K = 0.00002


@dataclass
class ExtractionResult:
    summary_line: str
    primary_topic: str
    desired_future: str
    tension_type: str
    quote_snippet: str
    raw: dict


class ModelService:
    _local_model_instance = None
    _local_model_key: tuple[str, str, str] | None = None

    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.openai_api_key if self.settings.openai_enabled else ""
        self.base_url = self.settings.openai_base_url.rstrip("/")

    def _log_call(
        self,
        db: Session,
        message_id,
        call_type: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        audio_seconds: float | None,
        total_cost: float,
        provider_request_id: str | None = None,
    ) -> float:
        entry = OpenAICallLog(
            message_id=message_id,
            call_type=call_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            audio_seconds=audio_seconds,
            unit_cost_input=PRICE_INPUT_PER_1K,
            unit_cost_output=PRICE_OUTPUT_PER_1K,
            unit_cost_audio_second=PRICE_AUDIO_PER_SEC,
            total_cost_usd=total_cost,
            pricing_version=self.settings.pricing_version,
            provider_request_id=provider_request_id,
        )
        db.add(entry)
        return total_cost

    def _get_local_whisper_model(self):
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install with: pip install -e '.[local-audio]'"
            ) from exc

        key = (
            self.settings.local_whisper_model,
            self.settings.local_whisper_device,
            self.settings.local_whisper_compute_type,
        )
        if ModelService._local_model_instance is not None and ModelService._local_model_key == key:
            return ModelService._local_model_instance

        model = WhisperModel(
            model_size_or_path=self.settings.local_whisper_model,
            device=self.settings.local_whisper_device,
            compute_type=self.settings.local_whisper_compute_type,
        )
        ModelService._local_model_instance = model
        ModelService._local_model_key = key
        return model

    def _transcribe_local(self, audio_b64: str) -> str:
        audio_bytes = base64.b64decode(audio_b64)
        model = self._get_local_whisper_model()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, _info = model.transcribe(
                tmp.name,
                language=self.settings.local_whisper_language,
                beam_size=max(1, int(self.settings.local_whisper_beam_size)),
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        return text or "[transcripcion vacia]"

    def transcribe_local_strict(self, db: Session, audio_b64: str, audio_seconds: float | None, message_id=None) -> str:
        try:
            text = self._transcribe_local(audio_b64)
            self._log_call(
                db,
                message_id,
                "transcription",
                f"faster-whisper:{self.settings.local_whisper_model}",
                None,
                None,
                audio_seconds,
                total_cost=0.0,
            )
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("Strict local transcription failed: %s", exc)
            self._log_call(
                db,
                message_id,
                "transcription",
                f"faster-whisper:{self.settings.local_whisper_model}",
                None,
                None,
                audio_seconds,
                total_cost=0.0,
            )
            return "[transcripcion no disponible temporalmente]"

    def transcribe(self, db: Session, audio_b64: str, audio_seconds: float | None, message_id=None) -> str:
        provider = (self.settings.transcribe_provider or "openai").strip().lower()
        if not self.settings.openai_enabled and provider == "openai":
            provider = "local"

        if provider == "local":
            try:
                text = self._transcribe_local(audio_b64)
                self._log_call(
                    db,
                    message_id,
                    "transcription",
                    f"faster-whisper:{self.settings.local_whisper_model}",
                    None,
                    None,
                    audio_seconds,
                    total_cost=0.0,
                )
                return text
            except Exception as exc:  # noqa: BLE001
                logger.warning("Local transcription fallback due to local provider error: %s", exc)
                self._log_call(
                    db,
                    message_id,
                    "transcription",
                    f"faster-whisper:{self.settings.local_whisper_model}",
                    None,
                    None,
                    audio_seconds,
                    total_cost=0.0,
                )
                return "[transcripcion no disponible temporalmente]"

        if not self.api_key:
            text = "[transcripcion simulada]"
            self._log_call(
                db,
                message_id,
                "transcription",
                self.settings.openai_model_transcribe,
                None,
                None,
                audio_seconds,
                total_cost=(audio_seconds or 0) * PRICE_AUDIO_PER_SEC,
            )
            return text

        audio_bytes = base64.b64decode(audio_b64)
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
        data = {"model": self.settings.openai_model_transcribe}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(f"{self.base_url}/audio/transcriptions", headers=headers, data=data, files=files)
                response.raise_for_status()
                payload = response.json()

            text = payload.get("text", "")
            cost = (audio_seconds or 0) * PRICE_AUDIO_PER_SEC
            self._log_call(
                db,
                message_id,
                "transcription",
                self.settings.openai_model_transcribe,
                None,
                None,
                audio_seconds,
                total_cost=cost,
                provider_request_id=payload.get("id"),
            )
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("Transcription fallback due to provider error: %s", exc)
            self._log_call(
                db,
                message_id,
                "transcription",
                self.settings.openai_model_transcribe,
                None,
                None,
                audio_seconds,
                total_cost=0.0,
            )
            return "[transcripcion no disponible temporalmente]"

    def _heuristic_sentiment(self, text: str) -> tuple[float, str]:
        norm = (text or "").lower()
        positive_terms = [
            "me gusta",
            "bonito",
            "tranquilo",
            "limpio",
            "agradable",
            "mejor",
            "verde",
            "seguro",
            "funciona bien",
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
            "falta",
            "horrible",
            "pesimo",
        ]
        pos = sum(1 for term in positive_terms if term in norm)
        neg = sum(1 for term in negative_terms if term in norm)
        if pos + neg == 0:
            return 0.0, "neutral"
        score = max(-1.0, min(1.0, (pos - neg) / float(pos + neg)))
        if score >= 0.2:
            return round(score, 3), "positive"
        if score <= -0.2:
            return round(score, 3), "negative"
        return round(score, 3), "neutral"

    def _derive_taxonomy_from_text(self, text: str) -> tuple[str, str, str]:
        norm = (text or "").lower()

        topic = "other"
        future = "other"
        tension = "none"

        if any(k in norm for k in ["cruce", "vereda", "micro", "bus", "bici", "acceso", "accesibilidad", "semáforo", "semaforo"]):
            topic = "mobility"
            future = "better_crossings"
            tension = "flow_vs_stay"
        elif any(k in norm for k in ["miedo", "insegur", "robo", "asalto", "oscuro", "ilumin"]):
            topic = "safety"
            future = "safer_nights"
            tension = "security_vs_privacy"
        elif any(k in norm for k in ["sombra", "árbol", "arbol", "calor", "verde", "plaza", "aire"]):
            topic = "environment"
            future = "more_shade"
            tension = "preservation_vs_change"
        elif any(k in norm for k in ["basura", "sucio", "sucia", "limpio", "limpieza", "olor"]):
            topic = "public_space"
            future = "cleaner_space"
            tension = "none"
        elif any(k in norm for k in ["feria", "comercio", "local", "vendedor", "venta"]):
            topic = "commerce"
            future = "scale_positive_use"
            tension = "commerce_vs_common_use"
        elif any(k in norm for k in ["cultura", "musica", "música", "arte", "actividad", "evento"]):
            topic = "culture"
            future = "more_cultural_activity"
            tension = "calm_vs_vitality"

        return topic, future, tension

    def extract(self, db: Session, text: str, message_id=None) -> ExtractionResult:
        provider = (self.settings.extract_provider or "openai").strip().lower()
        if not self.settings.openai_enabled and provider == "openai":
            provider = "local"

        if provider == "heuristic":
            return self._heuristic_extract(db, text, message_id)
        if provider == "local":
            return self._local_extract(db, text, message_id)
        if not self.api_key:
            return self._heuristic_extract(db, text, message_id)

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary_line": {"type": "string", "maxLength": 280},
                "primary_topic": {"type": "string", "enum": PRIMARY_TOPICS},
                "desired_future": {"type": "string", "enum": DESIRED_FUTURES},
                "tension_type": {"type": "string", "enum": TENSION_TYPES},
                "quote_snippet": {"type": "string", "maxLength": 280},
                "sentiment_score": {"type": "number", "minimum": -1, "maximum": 1},
                "sentiment_label": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "taxonomy_fit_score": {"type": "number", "minimum": 0, "maximum": 1},
                "taxonomy_gap_type": {
                    "type": "string",
                    "enum": ["none", "primary_topic", "desired_future", "tension_type"],
                },
                "taxonomy_candidate_label": {"type": ["string", "null"], "maxLength": 128},
                "taxonomy_candidate_reason": {"type": ["string", "null"], "maxLength": 280},
            },
            "required": [
                "summary_line",
                "primary_topic",
                "desired_future",
                "tension_type",
                "quote_snippet",
                "taxonomy_fit_score",
                "taxonomy_gap_type",
            ],
        }

        prompt = (
            "Extract structured representation from civic corridor testimony. "
            "Use only taxonomy values and preserve original voice in quote_snippet."
        )
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.settings.openai_model_extract,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": text}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agora_extraction",
                    "schema": schema,
                    "strict": True,
                }
            },
        }

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(f"{self.base_url}/responses", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            raw_output = data.get("output", [])
            content = raw_output[0]["content"][0]["text"] if raw_output else "{}"
            parsed = json.loads(content)

            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
            self._log_call(
                db,
                message_id,
                "structured_extraction",
                self.settings.openai_model_extract,
                input_tokens,
                output_tokens,
                None,
                total_cost,
                provider_request_id=data.get("id"),
            )

            return self._sanitize_extract_payload(parsed, text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Extraction fallback due to provider error: %s", exc)
            return self._heuristic_extract(db, text, message_id)

    def _sanitize_extract_payload(self, parsed: dict, text: str) -> ExtractionResult:
        summary = str(parsed.get("summary_line") or text.strip()[:140] or "Testimonio ciudadano")[:280]
        quote = str(parsed.get("quote_snippet") or text.strip()[:200] or "Sin contenido")[:280]

        topic = str(parsed.get("primary_topic") or "other")
        future = str(parsed.get("desired_future") or "other")
        tension = str(parsed.get("tension_type") or "other")

        if topic not in PRIMARY_TOPICS:
            topic = "other"
        if future not in DESIRED_FUTURES:
            future = "other"
        if tension not in TENSION_TYPES:
            tension = "other"

        # Hybrid guardrail: if local model is vague, derive taxonomy from text in Spanish.
        h_topic, h_future, h_tension = self._derive_taxonomy_from_text(text)
        if topic == "other" and h_topic != "other":
            topic = h_topic
        if future == "other" and h_future != "other":
            future = h_future
        if tension in {"other", "none"} and h_tension not in {"other", "none"}:
            tension = h_tension

        score_raw = parsed.get("sentiment_score")
        label_raw = parsed.get("sentiment_label")
        try:
            score = float(score_raw) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None
        if score is None or score < -1 or score > 1:
            score, default_label = self._heuristic_sentiment(text)
        else:
            score = round(score, 3)
            default_label = "neutral" if -0.2 < score < 0.2 else ("positive" if score >= 0.2 else "negative")

        label = str(label_raw or default_label).lower()
        if label not in {"positive", "neutral", "negative"}:
            label = default_label

        future = self._align_future_with_sentiment(
            desired_future=future,
            sentiment_label=label,
            sentiment_score=score,
        )

        fit_raw = parsed.get("taxonomy_fit_score")
        try:
            fit_score = float(fit_raw) if fit_raw is not None else 0.8
        except (TypeError, ValueError):
            fit_score = 0.8
        fit_score = max(0.0, min(1.0, fit_score))

        gap_type = str(parsed.get("taxonomy_gap_type") or "none")
        if gap_type not in {"none", "primary_topic", "desired_future", "tension_type"}:
            gap_type = "none"
        candidate_label = parsed.get("taxonomy_candidate_label")
        candidate_reason = parsed.get("taxonomy_candidate_reason")
        if candidate_label is not None:
            candidate_label = str(candidate_label).strip()[:128] or None
        if candidate_reason is not None:
            candidate_reason = str(candidate_reason).strip()[:280] or None

        return ExtractionResult(
            summary_line=summary,
            primary_topic=topic,
            desired_future=future,
            tension_type=tension,
            quote_snippet=quote,
            raw={
                "summary_line": summary,
                "primary_topic": topic,
                "desired_future": future,
                "tension_type": tension,
                "quote_snippet": quote,
                "sentiment_score": score,
                "sentiment_label": label,
                "taxonomy_fit_score": fit_score,
                "taxonomy_gap_type": gap_type,
                "taxonomy_candidate_label": candidate_label,
                "taxonomy_candidate_reason": candidate_reason,
            },
        )

    def _align_future_with_sentiment(self, desired_future: str, sentiment_label: str, sentiment_score: float) -> str:
        # Guardrail: positive testimonies should not default to deficit-oriented futures.
        if sentiment_label == "positive" or sentiment_score >= 0.25:
            if desired_future in {"other", "cleaner_space", "safer_nights", "better_crossings"}:
                return "preserve_what_works"
        return desired_future

    def _local_extract(self, db: Session, text: str, message_id=None) -> ExtractionResult:
        base_url = self.settings.local_llm_base_url.rstrip("/")
        model = self.settings.local_llm_model_extract
        headers = {"Content-Type": "application/json"}
        if self.settings.local_llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.local_llm_api_key}"

        system = (
            "Clasifica testimonio civico y responde JSON estricto con estas claves exactas: "
            "summary_line, primary_topic, desired_future, tension_type, quote_snippet, sentiment_score, sentiment_label, "
            "taxonomy_fit_score, taxonomy_gap_type, taxonomy_candidate_label, taxonomy_candidate_reason. "
            f"primary_topic debe ser uno de {PRIMARY_TOPICS}. "
            f"desired_future debe ser uno de {DESIRED_FUTURES}. "
            f"tension_type debe ser uno de {TENSION_TYPES}. "
            "taxonomy_gap_type debe ser none|primary_topic|desired_future|tension_type. "
            "Si la taxonomia actual no representa bien el mensaje, baja taxonomy_fit_score (<0.55) y propone "
            "taxonomy_candidate_label corto en espanol + taxonomy_candidate_reason. "
            "Usa espanol. Si hay duda, usa el valor mas cercano y evita 'other' salvo que sea realmente ambiguo."
        )
        payload = {
            "model": model,
            "temperature": 0,
            "top_p": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        "Devuelve solo JSON. summary_line max 280. quote_snippet max 280. "
                        "sentiment_score entre -1 y 1. sentiment_label en positive|neutral|negative. "
                        "taxonomy_fit_score entre 0 y 1. taxonomy_candidate_label opcional max 128. "
                        "Texto:\n"
                        f"{text}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                if response.status_code == 404:
                    # Fallback for native Ollama API (/api/chat), useful when /v1 compatibility is unavailable.
                    root = base_url[:-3] if base_url.endswith("/v1") else base_url
                    ollama_payload = {
                        "model": model,
                        "messages": payload["messages"],
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0,
                            "top_p": 0.1,
                        },
                    }
                    response = client.post(f"{root}/api/chat", headers=headers, json=ollama_payload)
                    response.raise_for_status()
                    data = response.json()
                    content = (data.get("message") or {}).get("content", "{}")
                else:
                    response.raise_for_status()
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            parsed = json.loads(content)
            result = self._sanitize_extract_payload(parsed, text)
            self._log_call(
                db,
                message_id,
                "structured_extraction",
                model,
                None,
                None,
                None,
                total_cost=0.0,
                provider_request_id=data.get("id"),
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local extraction fallback due to provider error: %s", exc)
            return self._heuristic_extract(db, text, message_id)

    def embed(self, db: Session, text: str, message_id=None) -> list[float]:
        provider = (self.settings.embed_provider or "heuristic").strip().lower()
        if not self.settings.openai_enabled and provider == "openai":
            provider = "heuristic"

        if provider != "openai" or not self.api_key:
            embedding = [float(len(text) % 10), 0.1, 0.2]
            self._log_call(
                db,
                message_id,
                "embedding",
                self.settings.openai_model_embed,
                0,
                0,
                None,
                total_cost=0.0,
            )
            return embedding

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.settings.openai_model_embed, "input": text}

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(f"{self.base_url}/embeddings", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            embedding = data["data"][0]["embedding"]
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            total_cost = (input_tokens / 1000) * PRICE_EMBED_PER_1K
            self._log_call(
                db,
                message_id,
                "embedding",
                self.settings.openai_model_embed,
                input_tokens,
                0,
                None,
                total_cost,
                provider_request_id=data.get("id"),
            )
            return embedding
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding fallback due to provider error: %s", exc)
            embedding = [float(len(text) % 10), 0.1, 0.2]
            self._log_call(
                db,
                message_id,
                "embedding",
                self.settings.openai_model_embed,
                0,
                0,
                None,
                total_cost=0.0,
            )
            return embedding

    def _heuristic_extract(self, db: Session, text: str, message_id=None) -> ExtractionResult:
        lower = text.lower()
        topic = "public_space"
        future = "other"
        tension = "none"
        sentiment_score, sentiment_label = self._heuristic_sentiment(text)

        if any(k in lower for k in ["bus", "metro", "cross", "walk", "vereda", "cruce"]):
            topic = "mobility"
            future = "better_crossings"
            tension = "flow_vs_stay"
        elif any(k in lower for k in ["safe", "miedo", "robo", "luz"]):
            topic = "safety"
            future = "safer_nights"
            tension = "security_vs_privacy"
        elif any(k in lower for k in ["sombra", "arbol", "calor", "verde"]):
            topic = "environment"
            future = "more_shade"

        if sentiment_label == "positive":
            if future in {"other", "cleaner_space"}:
                future = "preserve_what_works"
            if tension == "none":
                tension = "calm_vs_vitality"
        elif sentiment_label == "negative":
            if future == "other":
                future = "cleaner_space"
            if tension == "none":
                tension = "security_vs_privacy"
        else:
            if future == "other":
                future = "cleaner_space"

        summary = text.strip().replace("\n", " ")[:140] or "Testimonio ciudadano"
        quote = text.strip().replace("\n", " ")[:200] or "Sin contenido"
        parsed = {
            "summary_line": summary,
            "primary_topic": topic,
            "desired_future": future,
            "tension_type": tension,
            "quote_snippet": quote,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "taxonomy_fit_score": 0.8,
            "taxonomy_gap_type": "none",
            "taxonomy_candidate_label": None,
            "taxonomy_candidate_reason": None,
        }

        in_tokens = max(1, len(text) // 4)
        out_tokens = 70
        total_cost = (in_tokens / 1000) * PRICE_INPUT_PER_1K + (out_tokens / 1000) * PRICE_OUTPUT_PER_1K
        self._log_call(
            db,
            message_id,
            "structured_extraction",
            self.settings.openai_model_extract,
            in_tokens,
            out_tokens,
            None,
            total_cost,
        )

        return ExtractionResult(
            summary_line=parsed["summary_line"],
            primary_topic=parsed["primary_topic"],
            desired_future=parsed["desired_future"],
            tension_type=parsed["tension_type"],
            quote_snippet=parsed["quote_snippet"],
            raw=parsed,
        )
