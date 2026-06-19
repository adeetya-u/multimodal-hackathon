# Stack — Nebius + Vapi + Insforge

## Environment variables

### Backend (`backend/.env`)

```bash
# LLM — MiniMax (current) or Nebius Token Factory
LLM_PROVIDER=minimax          # minimax | nebius | bedrock
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_LLM_MODEL=MiniMax-M2.1

# Nebius — set LLM_PROVIDER=nebius when credits return
NEBIUS_API_KEY=
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_MODEL_DEFAULT=meta-llama/Meta-Llama-3.1-70B-Instruct

# Voice — Vapi
VAPI_PUBLIC_KEY=
VAPI_PRIVATE_KEY=
VAPI_OR_ASSISTANT_ID=
VAPI_INTRO_ASSISTANT_ID=
VAPI_SERVER_URL=             # public HTTPS URL → /api/vapi/webhook

# Storage — Insforge-compatible REST (`/api/database/records/...`)
STORAGE_BACKEND=insforge     # insforge | filesystem
INSFORGE_URL=
INSFORGE_ANON_KEY=
INSFORGE_SERVICE_KEY=

# API
CORS_ORIGINS=*
SCALPEL_API_PORT=3001
```

### Web (`web/.env`)

```bash
VITE_API_BASE=
VITE_VAPI_PUBLIC_KEY=
VITE_VAPI_OR_ASSISTANT_ID=
VITE_VAPI_INTRO_ASSISTANT_ID=
```

## Prize track alignment

| Track | What we use |
|-------|-------------|
| **Nebius** | `LLM_PROVIDER=nebius` — all `converse_text` / prep agent via Token Factory |
| **MiniMax** | `LLM_PROVIDER=minimax` — interim OpenAI-compatible LLM until Nebius credits return |
| **Vapi** | OR + landing voice assistants; webhooks call `run_logger` / `run_answer` |
| **Insforge** | Postgres tables + Storage bucket `case-docs`; seed script for demo case |

## Architecture

```
Browser ──Vapi SDK──► Vapi Cloud ──webhook──► FastAPI (vapi_webhooks.py)
                                                      │
                      Insforge ◄── repository ────────┤
                      Nebius   ◄── llm.py ────────────┘
Browser ◄── SSE /api/cases/{id}/voice/stream ── voice_events hub
```

## Insforge schema

Link your project (once):

```bash
npx @insforge/cli link --project-id 0c8bb94f-a76e-44c2-968d-915d66581c6b
```

Apply schema (or use the CLI):

```bash
npx @insforge/cli db import backend/scripts/insforge_schema.sql
# — or paste backend/scripts/insforge_schema.sql in the Insforge SQL editor
```

Set `STORAGE_BACKEND=insforge` and `INSFORGE_*` in `backend/.env`, then:

```bash
./scripts/sync-mcp-env.sh   # Cursor Insforge MCP
./dev.sh seed
```

### HIPAA reminder (before storing real PHI)

Scalpel stores case notes, transcripts, and documents — treat as ePHI in production.

1. **BAA** — Request Insforge Enterprise HIPAA add-on and execute a Business Associate Agreement before any real patient data.
2. **RLS on every table** — `cases`, `checklists`, `session_logs`, `case_documents`, `compact_context`, and `snippets` must have Row Level Security policies scoped via `auth.uid()` (or your IdP JWT). The base schema ships without RLS for dev; do not go live without policies.
3. **Advisor scan** — Run `npx @insforge/cli diagnose advisor` after migrations; fix any permissive-policy findings.
4. **Keys** — Use `INSFORGE_SERVICE_KEY` only in the FastAPI backend. Never ship the service key to the browser; client access needs the anon key plus strict RLS.
5. **Storage** — Keep `case-docs` private; use presigned URLs with short TTL. No public buckets for PHI.
6. **Auth** — Enable email verification / SSO; tighten password policy in the Insforge dashboard before prod.
7. **Full stack** — Insforge alone is not enough: also sign BAAs with **Vapi** (voice recordings/transcripts) and confirm **Nebius** data handling for LLM prompts that include case context.

Dashboard: https://insforge.dev/dashboard/project/0c8bb94f-a76e-44c2-968d-915d66581c6b


## Optional (not required for demo)

| Service | Role | MVP |
|---------|------|-----|
| MOSS | Vector search | Keyword search in `search.py` |
| Tavily | External web answers | Disabled |
| Unsiloed | PDF API | `pypdf` fallback only |
