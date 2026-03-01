# Agora Backend MVP

Backend inicial para Ágora (FastAPI + PostgreSQL) enfocado en:
- ingesta de texto/audio,
- extracción estructurada con taxonomías controladas,
- versionado de análisis por corrección humana,
- enlaces de feedback con token hash,
- trazabilidad de costos por llamada OpenAI.

## Stack
- FastAPI
- SQLAlchemy + Alembic
- PostgreSQL (Docker Compose)

## Setup Docs
- Quickstart: `docs/quickstart.md`
- Local Docker setup: `docs/local-docker-setup.md`
- Local LLM setup (Ollama): `docs/local-llm-setup.md`
- WhatsApp Meta setup: `docs/whatsapp-meta-setup.md`

## Integraciones WhatsApp
- Arquitectura provider-agnostic en backend (ingesta unificada).
- Proveedor principal recomendado: Meta WhatsApp Cloud API (directo).
- Adaptador secundario disponible: Twilio.
- Runbook completo Meta setup: `docs/whatsapp-meta-setup.md`.

## Multi-Lugar
- El backend ya no está acoplado a un único corredor.
- Puedes enviar `place_code` por mensaje en `POST /ingest`.
- Si `place_code` no existe, se crea automáticamente en `places`.
- Si no se envía, usa `DEFAULT_PLACE_CODE` del entorno.
- Gestión admin de territorios/segmentos:
  - `POST /admin/places`
  - `GET /admin/places`
  - `POST /admin/places/{place_code}/segments`
  - `GET /admin/places/{place_code}/segments`
  - `POST /admin/places/{place_code}/segments/import` (CSV)

## Configuración
Prerequisito: Docker Desktop funcionando (`docker --version` y `docker compose version`).

1. Copiar variables:
```bash
cp .env.example .env
```
2. Ajustar `OPENAI_API_KEY` en `.env`.
   Configurar también `ADMIN_API_KEY` para endpoints de jobs.
3. Levantar servicios:
```bash
docker compose up --build
```
4. Aplicar migraciones:
```bash
alembic upgrade head
```

## Flujo rápido con Make
```bash
make setup
make up
make migrate
```

Comandos útiles:
```bash
make help
make test
make logs
make health
make cluster
make precommit-install
make precommit
make llm-up
make llm-pull MODEL=llama3.1:8b-instruct
make llm-check MODEL=llama3.1:8b-instruct
```

Verificación rápida webhook Meta:
```bash
./scripts/verify_webhook.sh "https://<public-domain>" "<verify-token>"
```

Smoke test flujo WhatsApp (simulado por webhook):
```bash
./scripts/smoke_whatsapp_flow.sh http://localhost:8000
```

## Postman
Archivos incluidos:
- `postman/agora-mvp.postman_collection.json`
- `postman/agora-local.postman_environment.json`

Uso recomendado:
1. Importar colección y environment en Postman.
2. Seleccionar environment `Agora Local`.
3. Ejecutar en orden:
   - `Health`
   - `Ingest (Text)` (guarda automáticamente `feedback_token`)
   - `Feedback View`
   - `Feedback Patch`
   - `Run Cluster Job`
   - `WhatsApp Meta Verify (GET)`
   - `WhatsApp Meta Webhook (POST)`

## Endpoints MVP
- `GET /health`
- `POST /ingest`
- `GET /feedback/{token}`
- `GET /feedback/{token}/edit`
- `PATCH /feedback/{token}`
- `POST /integrations/whatsapp/webhook`
- `POST /integrations/whatsapp/twilio/webhook`
- `GET /integrations/whatsapp/meta/webhook`
- `POST /integrations/whatsapp/meta/webhook`
- `POST /admin/jobs/cluster`
- `POST /admin/places`
- `GET /admin/places`
- `POST /admin/places/{place_code}/segments`
- `GET /admin/places/{place_code}/segments`
- `POST /admin/places/{place_code}/segments/import`
- `GET /admin/metrics/pipeline`
- `GET /admin/metrics/conversation`
- `GET /admin/messages/review`
- `GET /admin/messages/review.csv`
- `GET /admin/messages/review/view`
- `GET /admin/home`
- `GET /admin/sentiment/audit/view`
- `GET /admin/sentiment/audit/sample`
- `POST /admin/sentiment/audit/evaluate`
- `GET /admin/taxonomy/candidates`
- `POST /admin/taxonomy/candidates/{candidate_id}/approve`
- `POST /admin/taxonomy/candidates/{candidate_id}/reject`
- `GET /admin/places/{place_id}/map/points`
- `GET /admin/places/{place_id}/map/heatmap`
- `GET /admin/places/{place_id}/map/grid`
- `GET /admin/places/{place_id}/map/timelapse`
- `GET /admin/places/{place_id}/map/view`
- `GET /places/{place_id}/entries`
- `GET /places/{place_id}/threads`
- `GET /places/{place_id}/threads/{thread_id}/messages`

## Ejemplo ingesta
```json
{
  "text": "Cruzar la Alameda aquí es peligroso en la noche",
  "place_code": "alameda-santiago",
  "latitude": -33.444,
  "longitude": -70.66,
  "presence_mode": "walking",
  "place_reference": "Alameda con Santa Rosa"
}
```

## Notas
- Si no hay `OPENAI_API_KEY`, el servicio usa extracción/transcripción heurística para desarrollo.
- Bloqueo total de OpenAI (local-only estricto):
  - `OPENAI_ENABLED=false`
  - con eso no se harán llamadas a `api.openai.com` aunque exista `OPENAI_API_KEY`.
- Flujo WhatsApp por defecto: `WHATSAPP_SINGLE_TURN_MODE=true` (un solo turno: ingesta inmediata + link de revisión/corrección).
 - Flujo WhatsApp por defecto: `WHATSAPP_SINGLE_TURN_MODE=true` (flujo guiado: opinion -> ubicacion -> link de revision/correccion).
- Clasificación con LLM local:
  - `EXTRACT_PROVIDER=local`
  - `LOCAL_LLM_BASE_URL=http://host.docker.internal:11434/v1`
  - `LOCAL_LLM_MODEL_EXTRACT=llama3.1:8b-instruct`
  - `LOCAL_LLM_API_KEY=` (opcional)
  - incluye clasificación interna de sentimiento (`sentiment_score`, `sentiment_label`) para mapas/heatmap
- Para transcripcion local sin OpenAI:
  - instalar dependencias: `python3 -m pip install -e '.[local-audio]'`
  - variables: `TRANSCRIBE_PROVIDER=local`, `LOCAL_WHISPER_MODEL=small`, `LOCAL_WHISPER_DEVICE=cpu`
- Embeddings sin OpenAI:
  - `EMBED_PROVIDER=heuristic` (default)
- `POST /admin/jobs/cluster` requiere header `X-Admin-Api-Key` y `ADMIN_API_KEY` configurado.
- Endpoints `/admin/*` requieren header `X-Admin-Api-Key`.
- CSV de segmentos requiere columnas: `name,order_index,min_lat,max_lat,min_lon,max_lon`.
- Revisión de calidad:
  - `GET /admin/messages/review` devuelve original + v1 + versión final para muestreo.
  - `GET /admin/messages/review.csv` exporta ese muestreo en CSV.
- El token de feedback se devuelve solo en el link generado y en DB se guarda únicamente `sha256(token)`.
- El `feedback_link` abre una vista web editable (`/feedback/{token}/edit`) para corregir representación sin exponer JSON crudo.
- En la vista de feedback, si el mensaje se percibe como positivo se priorizan opciones de `Futuro deseado` y `Tension` coherentes con valencia positiva.
- Cada corrección en `PATCH /feedback/{token}` crea una nueva versión de análisis sin recallar LLM.
- Propuestas de taxonomía (MVP):
  - el extractor local reporta `taxonomy_fit_score` y, si es bajo, puede proponer etiqueta nueva
  - se guarda en `taxonomy_candidates` con estado `pending`
  - revisión admin por endpoints `/admin/taxonomy/candidates/*`
- El webhook de WhatsApp recibe `Body`, `Latitude`, `Longitude`, `Address` como `form-data`.
- Meta WhatsApp Cloud API:
  - verificación webhook: `GET /integrations/whatsapp/meta/webhook` con `hub.mode`, `hub.verify_token`, `hub.challenge`
  - recepción eventos: `POST /integrations/whatsapp/meta/webhook`
  - diálogo automático habilitado: acuse + link de feedback al usuario por WhatsApp
  - se guarda metadata del proveedor por turno (`provider_metadata`) y la hora original del mensaje (`timestamp` de WhatsApp cuando viene)
  - variables: `META_WEBHOOK_VERIFY_TOKEN`, `META_VALIDATE_SIGNATURE`, `META_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`
  - flujo multimodal operativo:
    1. usuario envia opinion por texto o audio
    2. si es audio, se transcribe primero con whisper local (`ModelService.transcribe_local_strict`)
    3. desde ahi audio/texto siguen el mismo flujo textual
    4. se genera clasificacion + sentimiento con LLM local (`EXTRACT_PROVIDER=local`)
    5. Agora responde de forma personalizada y pide ubicacion
    6. usuario envia ubicacion por WhatsApp
    7. se ingesta al corpus con `lat/lon` + `place_reference`
    8. Agora envia link de feedback para revisar/corregir; `PATCH /feedback/{token}` crea nueva version
- Mapa geolocalizado:
  - `GET /admin/places/{place_id}/map/points` para puntos con score de sentimiento
  - `GET /admin/places/{place_id}/map/grid?cell_m=100` (grilla de celdas con `avg_sentiment` y escala en espanol de negativo a positivo)
  - `GET /admin/places/{place_id}/map/view` para vista Leaflet
    - vista unica de grilla (sin timelapse)
    - selector de diametro de celda: 50m, 100m, 200m
    - cada celda se colorea de rojo a verde segun `avg_sentiment`
    - popup muestra escala en espanol: muy negativo, negativo, neutral, positivo, muy positivo
  - login recomendado (cookie de sesión):
    - abrir `http://localhost:8000/admin/session/login`
    - luego abrir `http://localhost:8000/admin/places/1/map/view?period_days=30&mode=negative`
  - alternativa para scripts/API: header `X-Admin-Api-Key`
- Para Twilio WhatsApp:
  - endpoint: `POST /integrations/whatsapp/twilio/webhook`
  - activar verificación: `TWILIO_VALIDATE_SIGNATURE=true`
  - secret: `TWILIO_AUTH_TOKEN=<tu_auth_token_twilio>`
- El batch de clustering también puede ejecutarse como script:
```bash
python -m app.workers.cluster_messages
```

## Seguridad Para Repo Público
- Secretos fuera de git: usa `.env` local y placeholders en `.env.example`.
- Escaneo automático de secretos y llaves en commits con `pre-commit` + `gitleaks`.
- Instalación:
```bash
python3 -m pip install -e '.[dev]'
make precommit-install
```
- Escaneo manual completo:
```bash
make precommit
```

## Troubleshooting Rápido
- `make: *** No rule to make target 'up'`:
  - Ejecuta comandos desde la raíz del repo.
- `make: docker: No such file or directory`:
  - Docker no está instalado o no está en PATH.
- `Cannot connect to the Docker daemon`:
  - Docker Desktop no está corriendo.
- Webhook Meta responde 200 pero no hay respuesta al usuario:
  - revisar `WHATSAPP_ACCESS_TOKEN` (si expiro, Meta devuelve 401 en envio outbound).
  - revisar que el remitente este agregado como test recipient en Meta.
  - revisar `WHATSAPP_PHONE_NUMBER_ID` correcto del numero emisor.
- Audio no se transcribe:
  - revisar logs: fallo de descarga media de Meta (401/403) o fallo local de whisper.
  - confirmar dependencia local instalada: `python3 -m pip install -e '.[local-audio]'`.
  - confirmar vars: `TRANSCRIBE_PROVIDER=local`, `LOCAL_WHISPER_MODEL`, `LOCAL_WHISPER_DEVICE`.
- Aparecen llamadas a OpenAI en logs y no deberia:
  - fijar `OPENAI_ENABLED=false`.
  - fijar `EXTRACT_PROVIDER=local`, `TRANSCRIBE_PROVIDER=local`, `EMBED_PROVIDER=heuristic`.
  - reiniciar backend luego de cambiar `.env`: `docker compose restart api`.
- El flujo se queda pidiendo ubicacion o texto:
  - en WhatsApp, enviar ubicacion como mensaje tipo `location` (no solo texto con direccion).
  - revisar estado del hilo en `/places/{place_id}/threads` y turnos en `/places/{place_id}/threads/{thread_id}/messages`.
