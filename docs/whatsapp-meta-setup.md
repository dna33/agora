# WhatsApp Meta Cloud API Setup

This runbook takes you from a fresh Meta developer account to first inbound messages in Agora.

## Prerequisites
- Backend running and publicly reachable
- Meta App with WhatsApp product enabled
- Test phone number, temporary access token, phone number ID available

## 1) Configure local backend
Set these values in `.env`:

```env
META_WEBHOOK_VERIFY_TOKEN=choose-a-random-verify-token
META_VALIDATE_SIGNATURE=true
META_APP_SECRET=your_meta_app_secret
WHATSAPP_ACCESS_TOKEN=your_whatsapp_cloud_api_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
```

Then restart API.

## 2) Expose backend publicly
If running local API on port `8000`:

```bash
ngrok http 8000
```

Use the generated HTTPS URL. Webhook endpoint must be:

```text
https://<public-domain>/integrations/whatsapp/meta/webhook
```

## 3) Configure webhook in Meta
In Meta Developers:
1. Open your app
2. Go to `WhatsApp > Configuration`
3. In Webhook section click `Edit`
4. Set callback URL to:
   - `https://<public-domain>/integrations/whatsapp/meta/webhook`
5. Set verify token to exactly the same value as `META_WEBHOOK_VERIFY_TOKEN`
6. Click `Verify and save`

## 4) Subscribe webhook fields
Still in webhook configuration, subscribe at least:
- `messages`

Optional later:
- `message_template_status_update`
- `message_deliveries`

## 5) Validate verify endpoint from terminal
Use helper script:

```bash
./scripts/verify_webhook.sh "https://<public-domain>" "<verify-token>"
```

Expected output should include:
- `12345`

## 6) Send first test message
1. Add your own phone as test recipient in Meta WhatsApp setup
2. Send a WhatsApp message to the test number
3. Check API logs:

```bash
make logs
```

4. Validate ingestion with admin endpoints:
- `GET /admin/metrics/pipeline`
- `GET /admin/messages/review`

5. Validate conversational reply (Agora -> user):
- After inbound message, user should receive:
  - first turn: short system reply + one narrowing question
  - closing turn: corpus confirmation + feedback link

## Troubleshooting
### Verify fails in Meta UI
- Ensure callback URL is HTTPS and public
- Ensure `META_WEBHOOK_VERIFY_TOKEN` matches exactly
- Ensure route is `GET /integrations/whatsapp/meta/webhook`

### Webhook POST 403
- Signature mismatch likely
- Confirm `META_APP_SECRET` comes from same Meta app
- Confirm `META_VALIDATE_SIGNATURE=true`

### No inbound events
- Ensure webhook field `messages` is subscribed
- Ensure test recipient is added in Meta test mode
- Check ngrok tunnel is alive

### Inbound works but no reply message is sent
- Ensure `WHATSAPP_ACCESS_TOKEN` is set
- Ensure `WHATSAPP_PHONE_NUMBER_ID` is set
- Ensure token and phone number belong to the same Meta app/WhatsApp setup

## Production notes
- Replace temporary access token with long-lived/system-user token
- Keep `META_VALIDATE_SIGNATURE=true`
- Use stable domain (not temporary tunnel) before real pilot
