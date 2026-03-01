#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <base_url> <verify_token>"
  echo "Example: $0 https://abcd.ngrok-free.app my-token"
  exit 1
fi

BASE_URL="$1"
VERIFY_TOKEN="$2"
CHALLENGE="12345"

URL="${BASE_URL%/}/integrations/whatsapp/meta/webhook"
QUERY="hub.mode=subscribe&hub.verify_token=${VERIFY_TOKEN}&hub.challenge=${CHALLENGE}"

echo "Calling: ${URL}?${QUERY}"
RESPONSE=$(curl -fsS "${URL}?${QUERY}")

echo "Response: ${RESPONSE}"
if [ "${RESPONSE}" = "${CHALLENGE}" ]; then
  echo "OK: webhook verify endpoint is working"
else
  echo "ERROR: unexpected challenge response"
  exit 2
fi
