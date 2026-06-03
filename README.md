# Infigo Site Bot API

Standalone API for the chat widget on [infigosolutions.com](https://infigosolutions.com/).  
Deploy this folder to Vercel (set **Root Directory** = `infigobot` if the repo is the parent monorepo).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Status |
| POST | `/chat/public` | Public chat (`X-Site-Api-Key`) |
| GET | `/static/infigo-embed.js` | Embed script |
| POST | `/knowledge/text` | Add FAQ text (`X-Ingest-Key`) |
| POST | `/knowledge/file` | Upload `.txt`/`.md` FAQ (`X-Ingest-Key`) |

## Local setup

```powershell
cd infigobot
copy .env.example .env
# Edit DATABASE_URL, LLM_API_KEY, PUBLIC_CHAT_API_KEY

powershell -ExecutionPolicy Bypass -File scripts/setup_db.ps1

C:\Users\PC\miniconda3\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Test: `POST http://127.0.0.1:8000/chat/public` with header `X-Site-Api-Key` and body `{"message":"How long is an MVP?"}`.

## Vercel

1. Import GitHub repo.
2. **Root Directory:** `infigobot`
3. Env vars from `.env.example` (Production).
4. Deploy → use URL in React embed (`docs/examples/InfigoChatWidget.tsx`).

## Site content (no database)

**Default:** fetches `SITE_FETCH_URL` at chat time (HTML stripped, cached ~30 min). No JSON file required.

```env
SITE_RUNTIME_FETCH_ENABLED=true
SITE_FETCH_URL=https://infigosolutions.com/
SITE_CONTENT_ENABLED=false
```

Optional later: set `SITE_CONTENT_ENABLED=true` to use `config/infigo_site_content.json` instead.

## React widget

```env
VITE_INFIGO_CHAT_API_URL=https://your-app.vercel.app
VITE_INFIGO_CHAT_API_KEY=same as PUBLIC_CHAT_API_KEY
```

Mount `<InfigoChatWidget />` once in `App.tsx`.

## Local `.env`

Copy `.env.example` to `.env` or use the generated `.env` (gitignored). Never commit `.env`.
