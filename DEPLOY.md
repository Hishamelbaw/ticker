# Deploy

Same shape as Sprint 1: FastAPI backend on Render, static frontend on
Netlify. Two separate services, deployed independently.

## Backend — Render

1. New Web Service, connect this repo. Render should detect
   `render.yaml` (Blueprint); if it doesn't, set these manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. Environment variables (already declared in `render.yaml`, but the
   values need real content before/after the Netlify site exists):
   - `PYTHON_VERSION=3.12.7` — pinned deliberately. Render's default
     Python is new enough that `pydantic-core` has no prebuilt wheel for
     it, which breaks the build (Sprint 1 lesson). `runtime.txt` is
     **ignored** by Render — this env var is what actually pins the
     version.
   - `CORS_ALLOWED_ORIGINS` — currently a placeholder
     (`https://REPLACE-WITH-NETLIFY-URL.netlify.app`). Once the Netlify
     site exists, replace it with the real URL and redeploy (or restart)
     the Render service so the new value takes effect. Comma-separate if
     you need more than one origin (e.g. a Netlify preview URL alongside
     prod).
   - `DATABASE_URL=sqlite:///./ticker.db` — SQLite on the service's own
     filesystem. That filesystem is ephemeral (resets on redeploy/restart
     unless you attach a paid Disk), which is fine here: the ticker data
     is synthetic and regenerates from scratch on every boot anyway, and
     alerts/audit history resetting on redeploy is an acceptable tradeoff
     for a demo, not a production system.

## Frontend — Netlify

1. New site, connect this repo. `netlify.toml` sets:
   - `base = "frontend"` — scopes the build to the `frontend/` directory
     so Netlify never scans the repo root and tries to `pip install`
     the backend's `requirements.txt`.
   - `publish = "."` — relative to `base`, so it publishes `frontend/`
     itself. No build command needed; it's static HTML/JS/CSS.
2. **Before** deploying (or before the final deploy), edit
   `frontend/config.js` to point at the real Render URL:
   ```js
   const API_BASE_URL = "https://<your-service>.onrender.com";
   const WS_URL = "wss://<your-service>.onrender.com/ws";
   ```
   (`wss://`, not `ws://` — Render terminates TLS.)

## After both exist

1. Set Render's `CORS_ALLOWED_ORIGINS` to the real Netlify URL, redeploy.
2. Confirm `frontend/config.js` points at the real Render URL, redeploy
   the Netlify site if it changed after the first deploy.
3. Open the Netlify URL and confirm the ticker table goes live and an
   alert can be created/triggered/acked, same checks as the local
   verification in step 8.

## Demo-day risk: Render free-tier cold start

Render's free tier spins the service down after a period of
inactivity. This app's core requirement is a **persistent WebSocket
connection** — if the backend is asleep when a demo starts, the first
connection attempt triggers a cold start (can take 30-60s+), and to an
audience that looks exactly like a dropped or failed connection, not
"the site is loading."

**Mitigation:** hit `GET /health` on the Render URL a minute or two
before demoing to warm the instance up, and keep that tab open (or
ping it again) during any waiting period beforehand so it doesn't spin
back down mid-setup. If a live demo slot is high-stakes, consider
temporarily upgrading to a paid instance for that day so this risk is
removed entirely — optional, not required for grading.
