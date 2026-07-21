// Local dev defaults (backend run via `uvicorn app.main:app`).
// Before deploying to Netlify, swap these for the real Render URL, e.g.:
//   const API_BASE_URL = "https://ticker-backend.onrender.com";
//   const WS_URL = "wss://ticker-backend.onrender.com/ws";
const API_BASE_URL = "http://127.0.0.1:8000";
const WS_URL = "ws://127.0.0.1:8000/ws";
