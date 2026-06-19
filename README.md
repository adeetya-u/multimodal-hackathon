# Scalpel

**Live demo:** [https://76ck2nr5.insforge.site/](https://76ck2nr5.insforge.site/)

**Scalpel** is a voice-first surgical assistant for the full case lifecycle: prep the chart, run the OR with hands-free logging and Q&A, then close with a structured post-op summary.

Built for the **Multimodal AI Hackathon** using [Nebius Token Factory](https://tokenfactory.nebius.com), [Vapi](https://vapi.ai), and [InsForge](https://insforge.dev).

**API:** [https://scalpel-api-0c8bb94f-a76e-44c2-968d-915d66581c6b.fly.dev/api/health](https://scalpel-api-0c8bb94f-a76e-44c2-968d-915d66581c6b.fly.dev/api/health)

---

## What you can do

| Stage | What Scalpel does |
|-------|----------------|
| **Landing** | Talk to a voice intro that explains the product and sends you to case prep |
| **Prep** | Upload a patient chart (PDF), extract procedure and comorbidities, generate a tailored operative checklist, warm the voice agent before entering the OR |
| **OR** | Speak naturally: report checklist progress, ask clinical questions, handle complications. Scalpel updates the checklist, searches the chart, and speaks short grounded answers |
| **Close** | Say "end surgery" or tap End. Scalpel generates an operative summary from the transcript, checklist, and events |

### Highlights

- **Hands-free OR workflow** with live transcript, checklist rail, and vitals-style UI
- **Grounded answers** pulled from the patient chart and a knee surgery reference corpus (not free-form guessing)
- **Smart utterance routing** so "patient allergies?" triggers a lookup while "allergy check done" marks the checklist
- **Voice tuned for the OR** with medical transcription and turn-taking that waits for pauses mid-sentence
- **Persistent cases** with documents, checklists, and session history stored in the cloud

---

## How the three sponsors fit in

### Nebius Token Factory (LLM)

Nebius powers the reasoning layer. Set `LLM_PROVIDER=nebius` in `backend/.env`. Every call goes through `converse_text` in `backend/cases/llm.py`.

| When | What Nebius does |
|------|------------------|
| **Chart upload (prep)** | Extracts patient ID, procedure, comorbidities, and surgeon notes from parsed PDF text |
| **Ingestion** | Compacts long chart chunks into dense summaries for retrieval |
| **Checklist creation** | Generates pre/intra/post-op milestones from the procedure, chart, and reference SOPs. You can regenerate from the prep UI |
| **Every OR utterance** | Classifies intent: clinical **question**, status **log**, **checklist** update, or **situation** (complication) |
| **Logger routing** | Decides whether to acknowledge, search the chart, or escalate. Reconciles with the intent classifier so routing stays consistent |
| **Checklist marking** | Reviews each checklist step and confirms whether the surgeon's words should mark a step in progress or complete |
| **Clinical Q&A** | Writes a short spoken answer grounded in retrieved chart snippets and live OR context |
| **Case close** | Generates the full operative summary markdown from transcript, checklist, complications, and chart context |

In short: Nebius is not one prompt. It runs at prep time (parse, compact, checklist) and on every voice turn (intent, routing, marking, answers, summary).

### Vapi (voice)

Vapi handles real-time speech in the browser and connects to Scalpel's backend over webhooks.

| When | What Vapi does |
|------|------------------|
| **Landing intro** | Separate intro assistant (`VITE_VAPI_INTRO_ASSISTANT_ID`) for product demo voice |
| **OR session** | Duplex voice via the Web SDK: mic in, agent audio out |
| **Transcription** | Deepgram `nova-3-medical` through Vapi for clinical vocabulary (allergies, arthroplasty, DVT, etc.) |
| **Turn-taking** | Custom endpointing so Scalpel waits for natural pauses instead of cutting off mid-thought |
| **Webhook orchestration** | Each final surgeon utterance hits `POST /api/vapi/webhook`. Scalpel runs logger + retrieval logic server-side, not inside a single chat prompt |
| **SSE bridge** | The UI also listens on `/api/cases/{id}/voice/stream` for checklist updates, grounded cards, and case-closed events |
| **Spoken responses** | Grounded answers are spoken back through the active Vapi call |

Voice phrases like **"end surgery"**, **"surgery is complete"**, or **"close the case"** trigger automatic case close and summary generation.

### InsForge (backend + data)

InsForge is the production backend platform: Postgres, file storage, compute, and hosted frontend deploys.

| When | What InsForge does |
|------|-------------------|
| **Case storage** | Cases, checklists, session logs, compact context, and search snippets in Postgres (`backend/scripts/insforge_schema.sql`) |
| **Documents** | Patient PDFs uploaded in prep land in the `case-docs` storage bucket |
| **Repository layer** | `backend/cases/storage/insforge_repo.py` reads and writes cases through the InsForge REST API |
| **Compute** | FastAPI runs as a container (`scalpel-api`) on InsForge Compute for production |
| **Frontend hosting** | The React app deploys to Vercel through `npx @insforge/cli deployments deploy web/` |
| **Local dev fallback** | With `STORAGE_BACKEND=filesystem`, cases stay on disk so you can run without cloud storage |

---

## Architecture (simple view)

```
Browser ── Vapi Web SDK ──► Vapi Cloud ── webhook ──► FastAPI (Scalpel API)
                              │                              │
                              │                              ├── Nebius (LLM decisions)
                              │                              └── InsForge (cases + files)
Browser ◄── SSE /api/cases/{id}/voice/stream ────────────────┘
```

---

## Setup

### Prerequisites

- Node 20+ and Python 3.12+
- Accounts and keys for **Nebius**, **Vapi**, and **InsForge**
- For local Vapi webhooks: [ngrok](https://ngrok.com) or Cloudflare Tunnel

### 1. Clone and configure

```bash
git clone https://github.com/adeetya-u/multimodal-hackathon.git
cd multimodal-hackathon

cp backend/.env.example backend/.env
cp web/.env.example web/.env
```

Fill in `backend/.env`:

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER=nebius` | Use Nebius for all LLM calls |
| `NEBIUS_API_KEY`, `NEBIUS_BASE_URL` | Token Factory credentials |
| `VAPI_PUBLIC_KEY`, `VAPI_PRIVATE_KEY` | Vapi project keys |
| `VAPI_OR_ASSISTANT_ID`, `VAPI_INTRO_ASSISTANT_ID` | OR and landing assistants |
| `VAPI_SERVER_URL` | Public HTTPS URL of your API (for webhooks) |
| `STORAGE_BACKEND=insforge` | Use InsForge instead of local files |
| `INSFORGE_URL`, `INSFORGE_SERVICE_KEY`, `INSFORGE_PROJECT_ID` | From [InsForge dashboard](https://insforge.dev) or `npx @insforge/cli link` |

Fill in `web/.env`:

| Variable | Purpose |
|----------|---------|
| `VITE_VAPI_PUBLIC_KEY` | Same as `VAPI_PUBLIC_KEY` |
| `VITE_VAPI_OR_ASSISTANT_ID` | OR assistant ID |
| `VITE_VAPI_INTRO_ASSISTANT_ID` | Landing intro assistant ID |
| `VITE_API_BASE` | Leave empty locally (Vite proxies `/api` to port 3001) |

### 2. InsForge schema (first time)

```bash
npx @insforge/cli link --project-id <your-project-id>
npx @insforge/cli db import backend/scripts/insforge_schema.sql
```

### 3. Run locally

```bash
./dev.sh seed    # optional: load demo TKA case
./dev.sh
```

| Service | URL |
|---------|-----|
| UI | http://localhost:5173/prep |
| API | http://localhost:3001 |

**Vapi webhooks locally:**

```bash
ngrok http 3001
# Set VAPI_SERVER_URL=https://xxxx.ngrok-free.app in backend/.env
# Point your Vapi assistant server URL to https://xxxx.ngrok-free.app/api/vapi/webhook
```

**Useful commands:** `./dev.sh stop`, `./dev.sh status`, `./dev.sh seed`

### 4. Production deploy

See [docs/DEPLOY.md](docs/DEPLOY.md) for InsForge Compute (API) and Vercel (UI) steps.

---

## Project layout

```
web/                 React UI (prep, OR, summary) + Vapi Web SDK
backend/
  cases/             Case lifecycle, workers, checklist, Vapi webhooks
  cases/storage/     InsForge repository (filesystem fallback for dev)
  agents/            Prep and voice agent helpers
  scripts/           Schema, seeds, tests
docs/                DEPLOY.md, DEMO.md, STACK.md
```

---

## Sponsor credits

| Sponsor | Hackathon credit | Role in Scalpel |
|---------|------------------|--------------|
| **Nebius** | $100 Token Factory | Parsing, checklist, intent, routing, answers, summary |
| **Vapi** | $50 voice | OR + landing voice, medical STT, webhooks |
| **InsForge** | $25 backend | Postgres, storage, compute, hosted deploy |

---

## More docs

- [docs/DEMO.md](docs/DEMO.md) - 3-minute judge walkthrough
- [docs/DEPLOY.md](docs/DEPLOY.md) - Production on InsForge Compute + Vercel
- [docs/STACK.md](docs/STACK.md) - Full env reference and prize-track notes
