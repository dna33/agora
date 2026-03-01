# Quickstart

1. Install Docker Desktop
   - See `docs/local-docker-setup.md`
2. Start backend:

```bash
cd /Users/demianarancibia/PycharmProjects/agora
make setup
make up
make migrate
make health
```

3. Configure WhatsApp Meta webhook
   - See `docs/whatsapp-meta-setup.md`

4. (Optional but recommended) Configure local LLM
   - See `docs/local-llm-setup.md`
