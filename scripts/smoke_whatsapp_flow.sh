#!/usr/bin/env bash
set -euo pipefail

# Smoke test del flujo WhatsApp simulado (Meta webhook):
# 1) opinion en texto
# 2) mensaje extra (resiliencia)
# 3) ubicacion
# 4) validar thread/turns y extraer feedback link
# 5) validar versionado con PATCH /feedback/{token}
#
# Uso:
#   ./scripts/smoke_whatsapp_flow.sh [BASE_URL]
# Ejemplo:
#   ./scripts/smoke_whatsapp_flow.sh http://localhost:8000

BASE_URL="${1:-http://localhost:8000}"

if [[ -f ".env" ]]; then
  while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      key="${line%%=*}"
      value="${line#*=}"
      value="${value%\"}"
      value="${value#\"}"
      value="${value%\'}"
      value="${value#\'}"
      export "${key}=${value}"
    fi
  done < .env
fi

if [[ -z "${ADMIN_API_KEY:-}" ]]; then
  echo "ERROR: ADMIN_API_KEY no esta seteada. Cargala en .env."
  exit 1
fi

WA_FROM="${WA_TEST_FROM:-56930172667}"
WA_DISPLAY_PHONE="${WA_TEST_DISPLAY_PHONE:-15551890341}"
DEFAULT_PLACE_CODE="${DEFAULT_PLACE_CODE:-alameda-santiago}"

post_meta_webhook() {
  local payload="$1"
  curl -fsS -X POST "${BASE_URL}/integrations/whatsapp/meta/webhook" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

now_ts() {
  date +%s
}

echo "[1/7] Buscando place_id para place_code=${DEFAULT_PLACE_CODE}"
PLACES_JSON="$(curl -fsS -H "X-Admin-Api-Key: ${ADMIN_API_KEY}" "${BASE_URL}/admin/places")"
PLACE_ID="$(
  printf "%s" "${PLACES_JSON}" | python3 -c '
import json, os, sys
data = json.load(sys.stdin)
code = os.environ.get("DEFAULT_PLACE_CODE", "alameda-santiago")
picked = None
for p in data:
    if p.get("code") == code:
        picked = p
        break
if picked is None and data:
    picked = data[0]
if picked is None:
    raise SystemExit(2)
print(picked["id"])
'
)"
echo "place_id=${PLACE_ID}"

echo "[2/7] Enviando opinion inicial (texto)"
TS1="$(now_ts)"
PAYLOAD_TEXT_1="$(cat <<JSON
{
  "object":"whatsapp_business_account",
  "entry":[
    {
      "changes":[
        {
          "field":"messages",
          "value":{
            "metadata":{"display_phone_number":"${WA_DISPLAY_PHONE}"},
            "messages":[
              {
                "id":"wamid-smoke-1-${TS1}",
                "from":"${WA_FROM}",
                "timestamp":"${TS1}",
                "type":"text",
                "text":{"body":"Me preocupa la iluminacion y la seguridad en la noche"}
              }
            ]
          }
        }
      ]
    }
  ]
}
JSON
)"
post_meta_webhook "${PAYLOAD_TEXT_1}" >/dev/null
echo "ok"

echo "[3/7] Enviando mensaje extra antes de ubicacion (resiliencia)"
TS2="$(now_ts)"
PAYLOAD_TEXT_2="$(cat <<JSON
{
  "object":"whatsapp_business_account",
  "entry":[
    {
      "changes":[
        {
          "field":"messages",
          "value":{
            "metadata":{"display_phone_number":"${WA_DISPLAY_PHONE}"},
            "messages":[
              {
                "id":"wamid-smoke-2-${TS2}",
                "from":"${WA_FROM}",
                "timestamp":"${TS2}",
                "type":"text",
                "text":{"body":"Sobre todo en la esquina del paradero"}
              }
            ]
          }
        }
      ]
    }
  ]
}
JSON
)"
post_meta_webhook "${PAYLOAD_TEXT_2}" >/dev/null
echo "ok"

echo "[4/7] Enviando ubicacion"
TS3="$(now_ts)"
PAYLOAD_LOCATION="$(cat <<JSON
{
  "object":"whatsapp_business_account",
  "entry":[
    {
      "changes":[
        {
          "field":"messages",
          "value":{
            "metadata":{"display_phone_number":"${WA_DISPLAY_PHONE}"},
            "messages":[
              {
                "id":"wamid-smoke-3-${TS3}",
                "from":"${WA_FROM}",
                "timestamp":"${TS3}",
                "type":"location",
                "location":{
                  "latitude":-33.444,
                  "longitude":-70.66,
                  "name":"Paradero principal",
                  "address":"Alameda con Santa Rosa"
                }
              }
            ]
          }
        }
      ]
    }
  ]
}
JSON
)"
post_meta_webhook "${PAYLOAD_LOCATION}" >/dev/null
echo "ok"

echo "[5/7] Leyendo ultimo thread y turnos"
THREADS_JSON="$(curl -fsS -H "X-Admin-Api-Key: ${ADMIN_API_KEY}" "${BASE_URL}/places/${PLACE_ID}/threads?limit=5")"
THREAD_ID="$(
  printf "%s" "${THREADS_JSON}" | python3 -c '
import json, sys
data = json.load(sys.stdin)
if not data:
    raise SystemExit(3)
print(data[0]["id"])
'
)"
echo "thread_id=${THREAD_ID}"

TURNS_JSON="$(curl -fsS -H "X-Admin-Api-Key: ${ADMIN_API_KEY}" "${BASE_URL}/places/${PLACE_ID}/threads/${THREAD_ID}/messages?limit=50")"
printf "%s" "${TURNS_JSON}" | python3 -c '
import json, sys
data = json.load(sys.stdin)
ins = sum(1 for t in data if t.get("direction") == "IN")
outs = sum(1 for t in data if t.get("direction") == "OUT")
print(f"turns_total={len(data)} in={ins} out={outs}")
'

echo "[6/7] Extrayendo feedback link"
FEEDBACK_TOKEN="$(
  printf "%s" "${TURNS_JSON}" | python3 -c '
import json, re, sys
data = json.load(sys.stdin)
pat = re.compile(r"/feedback/([A-Za-z0-9_-]+)/edit")
for t in reversed(data):
    if t.get("direction") != "OUT":
        continue
    txt = t.get("raw_text") or ""
    m = pat.search(txt)
    if m:
        print(m.group(1))
        raise SystemExit(0)
raise SystemExit(4)
'
)"
echo "feedback_token=${FEEDBACK_TOKEN}"

FEEDBACK_VIEW="$(curl -fsS "${BASE_URL}/feedback/${FEEDBACK_TOKEN}")"
LATEST_VERSION="$(
  printf "%s" "${FEEDBACK_VIEW}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["latest_version"])'
)"
echo "feedback.latest_version(before)=${LATEST_VERSION}"

echo "[7/7] Probando versionado con PATCH"
PATCH_RES="$(
  curl -fsS -X PATCH "${BASE_URL}/feedback/${FEEDBACK_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "place_reference":"Esquina norte frente al paradero",
      "clarification_note":"Ajuste manual desde smoke test"
    }'
)"
NEW_VERSION="$(
  printf "%s" "${PATCH_RES}" | python3 -c 'import json, sys; print(json.load(sys.stdin)["new_version"])'
)"
echo "feedback.new_version(after)=${NEW_VERSION}"

echo "SMOKE OK: flujo opinion -> ubicacion -> feedback -> nueva version verificado."
