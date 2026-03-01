#!/usr/bin/env bash
set -euo pipefail

# Check local LLM availability for Agora.
# Works with either:
# - docker compose profile local-llm (service: ollama), or
# - host ollama server (http://localhost:11434)

MODEL="${1:-${LOCAL_LLM_MODEL_EXTRACT:-llama3.1:8b-instruct}}"
BASE_URL="${LOCAL_LLM_BASE_URL:-http://localhost:11434/v1}"
TAGS_URL="${BASE_URL%/v1}/api/tags"

echo "Checking local LLM endpoint: ${TAGS_URL}"
if ! curl -fsS "${TAGS_URL}" >/tmp/agora_llm_tags.json; then
  echo "ERROR: local LLM endpoint is not reachable."
  echo "Start one of these:"
  echo "  1) docker compose --profile local-llm up -d ollama"
  echo "  2) ollama serve"
  exit 1
fi

if ! python3 - "${MODEL}" /tmp/agora_llm_tags.json <<'PY'
import json
import sys

model = sys.argv[1]
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    payload = json.load(fh)

names = {item.get("name") for item in payload.get("models", []) if isinstance(item, dict)}
if model in names:
    print(f"OK: model installed -> {model}")
    sys.exit(0)

print(f"ERROR: model not found -> {model}")
print("Installed models:")
for n in sorted(x for x in names if x):
    print(f"  - {n}")
sys.exit(2)
PY
then
  echo
  echo "To install the model:"
  echo "  docker compose --profile local-llm exec ollama ollama pull ${MODEL}"
  echo "or (host):"
  echo "  ollama pull ${MODEL}"
  exit 2
fi

echo "Local LLM check passed."
