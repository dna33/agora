import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WhatsAppOutboundService:
    def __init__(self) -> None:
        settings = get_settings()
        self.access_token = settings.whatsapp_access_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.api_version = settings.meta_graph_api_version

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def send_text(self, to_wa_id: str, body: str) -> bool:
        if not self.is_configured() or not to_wa_id or not body.strip():
            return False

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "text",
            "text": {"body": body.strip()},
        }

        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send WhatsApp outbound message: %s", exc)
            return False
