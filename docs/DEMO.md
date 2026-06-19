# Judge demo script (~3 minutes)

## Setup (before judging)

1. `./dev.sh seed` — loads demo TKA case into Insforge/filesystem
2. Confirm `GET /api/health/providers` shows nebius + vapi + storage pass
3. Open http://localhost:5173/prep?case=case-001 (or create new case)

## Flow

1. **Landing (30s)** — Click intro voice widget; ask *"What is a TKA?"* → Vapi intro assistant answers
2. **Prep (45s)** — Upload patient PDF or use seeded case; wait for checklist; voice warmup shows "Ready for OR"
3. **OR (90s)** — Continue to OR; allow microphone
   - Say: *"Timeout is complete"* → checklist step updates
   - Ask: *"What antibiotic should we give?"* → grounded answer spoken + card on screen
4. **Close (15s)** — End case → summary page with operative note

## Talking points

- **Nebius**: Logger routing + checklist generation on every surgeon utterance
- **Vapi**: Real-time duplex voice; server webhooks run surgical logic (not prompt-only)
- **Insforge**: Case persistence, documents, session transcript — no local JSON files in production mode

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No voice | Check `VITE_VAPI_PUBLIC_KEY` and assistant ID |
| Webhook not firing | Set `VAPI_SERVER_URL` to ngrok URL; configure in Vapi dashboard |
| LLM errors | Verify `NEBIUS_API_KEY` and model name in dashboard |
| No demo case | Run `./dev.sh seed` |
