# Scalpel Backend

FastAPI service for case prep, Vapi voice webhooks, and Insforge storage.

## Architecture

```
backend/
├── cases/          Case lifecycle, checklist, Vapi orchestration, workers
├── services/api/   HTTP gateway (FastAPI app)
├── agents/         Prep agent (LangChain + Nebius)
├── assets/         Demo chart + knee reference corpus
└── scripts/        Seed + smoke tests
```

| Component | Entrypoint |
|-----------|------------|
| **API** | `services/api/main.py` or `./dev.sh` from repo root |

Voice runs in **Vapi Cloud** — the API handles webhooks at `/api/vapi/webhook` and streams UI events over SSE.

## Setup

```bash
cd backend
uv sync
cp .env.example .env   # Nebius, Vapi, Insforge keys
```

## Run

From repo root:

```bash
./dev.sh
```

Environment:

- `SCALPEL_API_PORT` — API port (default `3001`)
- `NEBIUS_API_KEY` — Nebius Token Factory
- `VAPI_*` — Vapi public/private keys and assistant IDs
- `STORAGE_BACKEND` — `filesystem` or `insforge`

## Frontend

[`../web/`](../web/) — React UI with Vapi Web SDK.
