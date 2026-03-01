# Local LLM Setup (Ollama)

Use this if you want local extraction/reply support without external model providers.

## Option A: Run Ollama via Docker Compose (recommended for repo reproducibility)

From project root:

```bash
make llm-up
make llm-pull MODEL=llama3.1:8b-instruct
make llm-check MODEL=llama3.1:8b-instruct
```

You can also start the full stack including Ollama:

```bash
make up-llm
```

## Option B: Run Ollama on host

Install and run:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama pull llama3.1:8b-instruct
```

Then validate:

```bash
LOCAL_LLM_BASE_URL=http://localhost:11434/v1 make llm-check MODEL=llama3.1:8b-instruct
```

## Env configuration for Agora API

Set these in `.env`:

```env
OPENAI_ENABLED=false
EXTRACT_PROVIDER=local
TRANSCRIBE_PROVIDER=local
EMBED_PROVIDER=heuristic
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434/v1
LOCAL_LLM_MODEL_EXTRACT=llama3.1:8b-instruct
LOCAL_LLM_API_KEY=
```

If using Ollama inside Docker Compose, `LOCAL_LLM_BASE_URL` can also be:

```env
LOCAL_LLM_BASE_URL=http://ollama:11434/v1
```

## Apply env changes

After editing `.env`:

```bash
docker compose up -d --force-recreate api
```

