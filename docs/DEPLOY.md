# Deploying Scalpel

Production stack: **FastAPI on InsForge Compute** + **Vite UI on Vercel** + **Vapi** (voice webhooks) + **Nebius** (LLM) + **Insforge** (Postgres + storage).

## Architecture

| Layer | Host | URL |
|-------|------|-----|
| Frontend | Vercel (via InsForge `deployments deploy` or direct Vercel import) | `https://76ck2nr5.insforge.site` or your Vercel domain |
| API | InsForge Compute (Fly.io) | `https://scalpel-api-0c8bb94f-a76e-44c2-968d-915d66581c6b.fly.dev` |
| Database / files | InsForge Postgres + Storage | `https://76ck2nr5.us-west.insforge.app` |

## Backend (InsForge Compute)

1. Apply `backend/scripts/insforge_schema.sql` in the InsForge SQL editor.
2. Install flyctl (required for source deploys): `curl -L https://fly.io/install.sh | sh`
3. Deploy or update the API container:

```bash
cd backend
npx @insforge/cli compute deploy . \
  --name scalpel-api \
  --port 8080 \
  --env-file .env
```

4. Set production env on the compute service (if not using `--env-file`):
   - `STORAGE_BACKEND=insforge`
   - `INSFORGE_URL`, `INSFORGE_SERVICE_KEY`, `INSFORGE_PROJECT_ID`
   - `NEBIUS_*`, `VAPI_*`
   - `VAPI_SERVER_URL=https://<your-api-host>` (must match the compute endpoint — Vapi webhooks)
   - `CORS_ORIGINS=https://76ck2nr5.insforge.site,https://your-vercel-domain.vercel.app`

5. Point the Vapi assistant server URL to `https://<your-api>/api/vapi/webhook`.

## Frontend (Vercel)

The UI reads `VITE_API_BASE` at build time and calls the InsForge Compute API directly (no local proxy).

### Option A — InsForge CLI (already linked)

```bash
# Set persistent build env vars (once)
npx @insforge/cli deployments env set VITE_API_BASE https://scalpel-api-0c8bb94f-a76e-44c2-968d-915d66581c6b.fly.dev
npx @insforge/cli deployments env set VITE_VAPI_PUBLIC_KEY <key>
npx @insforge/cli deployments env set VITE_VAPI_OR_ASSISTANT_ID <id>
npx @insforge/cli deployments env set VITE_VAPI_INTRO_ASSISTANT_ID <id>

# Deploy from web/ source
cd web && npm ci && npm run build   # verify locally first
cd .. && npx @insforge/cli deployments deploy web/
```

Live URL: **https://76ck2nr5.insforge.site**

### Option B — Direct Vercel (GitHub)

1. Import `adeetya-u/multimodal-hackathon` on [vercel.com](https://vercel.com).
2. Root directory: `web`
3. Build: `npm run build` · Output: `dist`
4. Environment variables (Production):
   - `VITE_API_BASE` → your InsForge Compute API URL
   - `VITE_VAPI_PUBLIC_KEY`, `VITE_VAPI_OR_ASSISTANT_ID`, `VITE_VAPI_INTRO_ASSISTANT_ID`

## Local dev

```bash
cp backend/.env.example backend/.env
cp web/.env.example web/.env
./dev.sh seed
./dev.sh
```

Leave `VITE_API_BASE` empty locally — Vite proxies `/api` to `localhost:3001`.

For Vapi webhooks locally, tunnel with ngrok/cloudflared and set `VAPI_SERVER_URL`.
