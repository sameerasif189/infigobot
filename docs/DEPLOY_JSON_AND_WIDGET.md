# Deploy with JSON + widget on main page

Scenario 2: Infigo hosts `public/content.json` on the React site. The API fetches it on each chat.

---

## Part 1 — You: Vercel (API)

### 1. Redeploy from GitHub

Repo: https://github.com/sameerasif189/infigobot  
Pull latest `main` in Vercel (or trigger **Redeploy**).

### 2. Environment variables (Production)

Set these in Vercel → Settings → Environment Variables:

```env
LLM_API_BASE=https://api.groq.com/openai/v1
LLM_API_KEY=your_groq_key
LLM_MODEL=llama-3.1-8b-instant
LLM_ORDER=api

SITE_BOT_ENABLED=true
PUBLIC_CHAT_API_KEY=your_public_chat_secret
INGEST_API_KEY=your_ingest_secret

SITE_COMPANY_NAME=Infigo Solutions
SITE_CONTACT_EMAIL=hello@infigosolutions.com
SITE_BOOKING_URL=
SITE_PROPOSAL_URL=https://infigosolutions.com/
CORS_ALLOWED_ORIGINS=https://infigosolutions.com,https://www.infigosolutions.com

SITE_JSON_URL=https://infigosolutions.com/content.json
SITE_RUNTIME_FETCH_ENABLED=false
SITE_CONTENT_ENABLED=false
```

**Important:** `SITE_JSON_URL` must be set. Turn off runtime HTML and bundled JSON.

### 3. Redeploy after saving env

### 4. Verify API

Replace `YOUR-APP` with your Vercel URL:

- `https://YOUR-APP.vercel.app/health` → `"ok": true`
- `https://YOUR-APP.vercel.app/integrations/site/status` → `"content_mode": "json_url"`
- After Infigo adds JSON: open `https://infigosolutions.com/content.json` in browser (must show JSON)

Test chat:

```powershell
$headers = @{ "X-Site-Api-Key" = "your_public_chat_secret"; "Content-Type" = "application/json" }
$body = '{"message":"How long does an MVP take?"}'
Invoke-RestMethod -Uri "https://YOUR-APP.vercel.app/chat/public" -Method POST -Headers $headers -Body $body
```

---

## Part 2 — Infigo: add `content.json` (React)

### 1. Copy the file

From this repo copy:

`docs/examples/public-content.json`

Into the Infigo React project:

`public/content.json`

(Vite/CRA serve everything in `public/` at the site root.)

### 2. Confirm it is public

After deploy, this URL must work in a browser:

`https://infigosolutions.com/content.json`

You should see JSON (not HTML, not 404).

### 3. Update when marketing changes

Edit `public/content.json` whenever services, FAQs, or contact info change. Redeploy the React site only (no API redeploy required).

---

## Part 3 — Infigo: widget on main page

### Option A — React component (recommended)

1. Copy `docs/examples/InfigoChatWidget.tsx` → `src/components/InfigoChatWidget.tsx`

2. Add to `.env` / `.env.production` on the React app:

```env
VITE_INFIGO_CHAT_API_URL=https://YOUR-APP.vercel.app
VITE_INFIGO_CHAT_API_KEY=same_value_as_PUBLIC_CHAT_API_KEY_on_Vercel
```

(Create React App: use `REACT_APP_` prefix instead of `VITE_`.)

3. Mount on the **main layout** so every page (including home) has the widget:

```tsx
// App.tsx or src/layouts/MainLayout.tsx
import { InfigoChatWidget } from "./components/InfigoChatWidget";

export default function App() {
  return (
    <>
      {/* your routes / homepage */}
      <InfigoChatWidget />
    </>
  );
}
```

4. Build and deploy the React site.

### Option B — Script tag only (no TSX)

In `public/index.html` before `</body>`:

```html
<script
  src="https://YOUR-APP.vercel.app/static/infigo-embed.js"
  data-api-url="https://YOUR-APP.vercel.app"
  data-api-key="your_public_chat_secret"
  data-title="Infigo Assistant"
  defer></script>
```

Redeploy React site.

---

## Checklist

**You**

- [ ] Vercel env includes `SITE_JSON_URL=https://infigosolutions.com/content.json`
- [ ] `SITE_RUNTIME_FETCH_ENABLED=false` and `SITE_CONTENT_ENABLED=false`
- [ ] Redeploy API
- [ ] `/integrations/site/status` shows `content_mode: json_url`

**Infigo**

- [ ] `public/content.json` deployed
- [ ] `https://infigosolutions.com/content.json` loads in browser
- [ ] Widget on main layout + frontend env vars
- [ ] React site redeployed

**End-to-end**

- [ ] Open homepage → chat bubble bottom-right
- [ ] Ask: “How long does an MVP take?” → answer from JSON

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| 401 on chat | `X-Site-Api-Key` / `VITE_INFIGO_CHAT_API_KEY` must match Vercel `PUBLIC_CHAT_API_KEY` |
| CORS error | Add exact site origin to `CORS_ALLOWED_ORIGINS` |
| `content.json` 404 | File must be in React `public/` folder |
| `content_mode` not `json_url` | Set `SITE_JSON_URL` on Vercel and redeploy |
| Empty answers | Check JSON is valid; test URL in browser |
