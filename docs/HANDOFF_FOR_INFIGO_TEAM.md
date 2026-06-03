# AI chat widget — implementation guide for Infigo Solutions (React site)

**From:** [Your name / team]  
**API:** Hosted separately on Vercel (no access to Infigo servers or database required)  
**Goal:** Floating chat assistant on the **main site** (all pages), answers from official site content in JSON.

---

## What we provide (you will receive separately)

| Item | Description |
|------|-------------|
| **API base URL** | e.g. `https://infigobot-xxxx.vercel.app` |
| **Public chat key** | Secret string for browser → API (`PUBLIC_CHAT_API_KEY`) — not the Groq key |
| **This repo (read-only)** | https://github.com/sameerasif189/infigobot — files to copy below |

We do **not** need SSH, hosting login, or database access to your systems.

---

## What Infigo needs to deliver (2 tasks)

### Task 1 — Public `content.json` (bot knowledge)

1. Create file in the React project:

   ```
   public/content.json
   ```

2. Use our template as the starting point (copy full file from repo):

   **Source:** `docs/examples/public-content.json`  
   **URL after deploy:** `https://infigosolutions.com/content.json`

3. Keep JSON **valid** and update when marketing copy changes (services, FAQs, contact, process).

4. **Acceptance test:** Open `https://infigosolutions.com/content.json` in a browser — must return JSON (not HTML, not 404).

**JSON structure (required fields):**

```json
{
  "company": "Infigo Solutions",
  "tagline": "...",
  "services": { "startup": { "title", "summary", "points": [] }, "enterprise": { ... } },
  "process": ["step 1", "step 2"],
  "capabilities": ["..."],
  "contact": { "website", "how_to_reach", "meeting" },
  "faqs": [{ "q": "...", "a": "..." }]
}
```

---

### Task 2 — Chat widget on every page (including homepage)

Choose **one** option.

#### Option A — React component (recommended)

1. Copy file into your repo:

   ```
   From:  docs/examples/InfigoChatWidget.tsx
   To:    src/components/InfigoChatWidget.tsx
   ```

2. Add environment variables (build-time):

   **Vite:**

   ```env
   VITE_INFIGO_CHAT_API_URL=https://YOUR-API-URL.vercel.app
   VITE_INFIGO_CHAT_API_KEY=VALUE_WE_SEND_YOU
   ```

   **Create React App:**

   ```env
   REACT_APP_INFIGO_CHAT_API_URL=https://YOUR-API-URL.vercel.app
   REACT_APP_INFIGO_CHAT_API_KEY=VALUE_WE_SEND_YOU
   ```

3. Mount **once** in the root layout (so it appears on the main page and all routes):

   ```tsx
   import { InfigoChatWidget } from "./components/InfigoChatWidget";

   export default function App() {
     return (
       <>
         {/* existing router / pages */}
         <InfigoChatWidget />
       </>
     );
   }
   ```

4. Widget behaviour: fixed button bottom-right, opens chat panel, calls our API.

#### Option B — Script tag only (no new React file)

Add to `public/index.html` before `</body>`:

```html
<script
  src="https://YOUR-API-URL.vercel.app/static/infigo-embed.js"
  data-api-url="https://YOUR-API-URL.vercel.app"
  data-api-key="VALUE_WE_SEND_YOU"
  data-title="Infigo Assistant"
  data-color="#6366f1"
  defer></script>
```

---

## CORS (already configured on API)

Our API allows requests from:

- `https://infigosolutions.com`
- `https://www.infigosolutions.com`

If you use a **staging** domain, send us the exact URL so we can add it to the API allowlist.

---

## API endpoint (for reference)

| Method | URL | Headers |
|--------|-----|---------|
| POST | `{API_URL}/chat/public` | `Content-Type: application/json`, `X-Site-Api-Key: {PUBLIC_CHAT_KEY}` |

**Body example:**

```json
{
  "message": "How long does an MVP take?",
  "session_id": null,
  "visitor_name": null,
  "visitor_email": null
}
```

**Response:** `{ "answer": "...", "session_id": "...", "booking_url": null, ... }`

---

## Acceptance checklist (Infigo sign-off)

- [ ] `https://infigosolutions.com/content.json` returns valid JSON
- [ ] Chat button visible on **homepage** and inner pages
- [ ] Sending a message returns a reply (not CORS / 401 error)
- [ ] Question *“How long does an MVP take?”* answers from your JSON content
- [ ] Production env vars set (not committed to public git if repo is public)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Chat says “could not reach server” | Wrong API URL or CORS | Check env URL; tell us staging domain |
| HTTP 401 | API key mismatch | `VITE_INFIGO_CHAT_API_KEY` must match our `PUBLIC_CHAT_API_KEY` exactly |
| Generic / empty answers | `content.json` missing | Deploy `public/content.json` |
| Button missing | Widget not in root layout | Add `<InfigoChatWidget />` to `App.tsx` / main layout |

---

## Files to copy (quick links)

| File | Purpose |
|------|---------|
| [public-content.json](https://github.com/sameerasif189/infigobot/blob/main/docs/examples/public-content.json) | → `public/content.json` |
| [InfigoChatWidget.tsx](https://github.com/sameerasif189/infigobot/blob/main/docs/examples/InfigoChatWidget.tsx) | → `src/components/` |
| [infigo-embed.js](https://github.com/sameerasif189/infigobot/blob/main/static/infigo-embed.js) | Reference only if using Option B (loaded from our API URL) |

---

## What Infigo does **not** need to do

- No Neon / Postgres / database
- No Groq or OpenAI keys on your side
- No changes to existing contact forms or backend APIs
- No Meta / WhatsApp setup

---

## Contact

Questions about API URL, keys, or CORS: [your email]  
Content accuracy (wording in `content.json`): Infigo marketing / product owner
