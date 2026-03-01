# Local Setup With Docker (macOS)

This guide is the default way to run Agora locally.

## 1) Install Docker Desktop
Use the official installer:
- https://www.docker.com/products/docker-desktop/

After install:
1. Open Docker Desktop once
2. Wait until Docker shows as running

## 2) Verify Docker is available
Run:

```bash
docker --version
docker compose version
```

Both commands must return a version.

## 3) Start Agora backend
From repo root (`/Users/demianarancibia/PycharmProjects/agora`):

```bash
make setup
make up
make migrate
make health
```

Expected health response:

```json
{"status":"ok"}
```

## 4) Common errors
### `make: *** No rule to make target 'up'`
You are not in the project root. Run:

```bash
cd /Users/demianarancibia/PycharmProjects/agora
make help
```

### `make: docker: No such file or directory`
Docker CLI is not installed or not available in PATH.
- Install Docker Desktop
- Restart terminal after install
- Verify `docker --version`

### `Cannot connect to the Docker daemon`
Docker Desktop is installed but not running.
- Open Docker Desktop app
- Wait until engine is running

### Port already in use
If `5432` or `8000` are busy, stop conflicting services or adjust `docker-compose.yml` ports.

## 5) WhatsApp webhook readiness
Once API is healthy on `localhost:8000`, continue with:
- `docs/whatsapp-meta-setup.md`

## 6) Local LLM (optional)
For local extraction/reply with Ollama:
- `docs/local-llm-setup.md`
