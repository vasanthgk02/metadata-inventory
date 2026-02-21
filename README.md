# HTTP Metadata Inventory Service

Async FastAPI service that fetches and stores HTTP metadata for given URLs.

## Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn (ASGI) |
| Database | MongoDB via Motor (async) |
| HTTP client | httpx (shared AsyncClient, connection pooling) |
| Retry logic | tenacity (exponential backoff) |
| Config | pydantic-settings (env vars) |
| Tests | pytest + pytest-asyncio |

## Architecture

```
app/
  core/          config.py, database.py (singleton), collections.py
  models/        common.py, metadata/document.py, metadata/schemas.py
  repositories/  base.py (ABC + factory), metadata/repository.py
  services/      metadata/service.py
  api/           router.py, metadata/routes.py
  workers/       fetcher.py
  main.py        lifespan, app factory, logging setup
```

## Setup & Running

### With Docker Compose (recommended)

```bash
docker compose up --build
```

MongoDB starts first with a healthcheck; the app waits until it's ready.

### Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit as needed
uvicorn app.main:app --reload
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI |
| `MONGO_DB` | `metadata_inventory` | Database name |
| `MONGO_MAX_POOL_SIZE` | `10` | Motor connection pool size |
| `HTTP_TIMEOUT` | `10.0` | HTTP request timeout (seconds) |
| `HTTP_MAX_RETRIES` | `3` | Max retry attempts on transient errors |
| `LOG_LEVEL` | `INFO` | Python logging level |

## API

Interactive docs: **http://localhost:8000/docs**

### `POST /metadata`

Fetch and store HTTP metadata for a URL (blocking).

```bash
curl -X POST http://localhost:8000/metadata \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'

# 200 OK
{"message": "Metadata stored for https://example.com/"}
```

| Status | Meaning |
|---|---|
| `200` | Fetch completed and metadata stored (synchronous — response is returned after fetch finishes) |
| `400` | URL unreachable (DNS / timeout / network) |
| `422` | Invalid URL format |
| `500` | Database error |

### `GET /metadata?url=<url>`

Return cached metadata. On a miss, returns 202 immediately and triggers background collection without blocking.

```bash
curl 'http://localhost:8000/metadata?url=https://example.com'

# 200 OK — cached
{"url": "https://example.com/", "status_code": 200, "headers": {...}, "cookies": {}, "created_at": "...", "updated_at": "..."}

# 202 Accepted — not yet stored, background fetch triggered
{"message": "No metadata yet for https://example.com/. Collection triggered."}
```

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Testing

```bash
pytest tests/ -v
```

All tests use mocked MongoDB and httpx — no external network calls required.
