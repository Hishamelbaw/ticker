# Ticker

A live market-ticker system for CS 3660 Sprint 2, built to demonstrate
messaging patterns under load rather than to be a real trading tool. A
background generator produces synthetic price ticks for five symbols
(AAPL, GOOG, MSFT, TSLA, AMZN). Ticks flow through a real Enterprise
Integration Pattern (EIP) pipeline — routed, enriched, aggregated into
OHLC candles — and are broadcast to browser clients over WebSockets.
Users can arm price alerts ("notify me when AAPL crosses $150") that
are evaluated against the live tick stream and driven by an explicit
state chart. Every tick and every alert state transition is written to
an append-only event log, so any alert's state at any past moment can
be reconstructed.

Synthetic data sidesteps any real-market-data licensing/TOS question
entirely, while still producing a continuous, realistic message stream
to demonstrate pub-sub under load.

**Live:**
- Frontend: https://ticker2.netlify.app
- Backend: https://ticker-backend-t7n3.onrender.com

> The backend is on Render's free tier, which spins down after a
> period of inactivity. If the frontend looks stuck on "connecting…",
> give it 30-60s for the first request to cold-start the service — see
> [DEPLOY.md](DEPLOY.md) for the demo-day mitigation.

## Setup / local dev

Backend:

```bash
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Runs a SQLite-backed FastAPI app at `http://127.0.0.1:8000`, with a
background task producing ticks every second and a WebSocket endpoint
at `/ws`.

Tests:

```bash
pytest
```

Frontend (plain HTML/JS, no framework, no build step):

```bash
cd frontend
python -m http.server 5500
```

Then open `http://127.0.0.1:5500`. `frontend/config.js` currently
points at the deployed Render backend — for local-only testing, edit
it back to the `127.0.0.1:8000` values noted in that file's comment
(and make sure `CORS_ALLOWED_ORIGINS` in your `.env` includes
`http://127.0.0.1:5500`, which the `.env.example` default already
does).

Full deploy instructions (Render + Netlify, including the env vars
each needs): [DEPLOY.md](DEPLOY.md).

## Enterprise Integration Patterns

Four implemented (three required). Each is independently unit-tested —
see `tests/`.

| Pattern | What it does here | File(s) | Reference |
|---|---|---|---|
| **Publish-Subscribe** | `ConnectionManager` tracks each WebSocket connection's subscribed symbol set; a broadcast for a symbol only reaches connections subscribed to it. Clients pick a subset of symbols over `/ws` and only receive those topics. | [`app/messaging/connection_manager.py`](app/messaging/connection_manager.py), [`app/routes/ws.py`](app/routes/ws.py) | [Publish-Subscribe Channel](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PublishSubscribeChannel.html) |
| **Message Router** | Internal events (`tick`, `alert_check`, `candle_close`) are dispatched by type to registered handlers from one place, instead of scattered `if` checks. | [`app/messaging/router.py`](app/messaging/router.py) | [Message Router](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageRouter.html) |
| **Content Enricher** | Each raw tick is enriched with computed fields — percent change from the previous tick and a rolling moving average — before publishing. | [`app/messaging/enricher.py`](app/messaging/enricher.py) | [Content Enricher](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DataEnricher.html) |
| **Aggregator** | Raw ticks are combined over a rolling time window into OHLC candle bars, published on a `candles` topic separate from raw `ticks`. | [`app/messaging/aggregator.py`](app/messaging/aggregator.py) | [Aggregator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html) |

The pipeline is wired together in [`app/main.py`](app/main.py): each
generated tick is logged to the audit trail, evaluated against armed
alerts, dispatched through the router to the enricher, broadcast on
`ticks`, fed into the aggregator, and — if a candle closes — dispatched
again as a `candle_close` event and broadcast on `candles`.

## State chart: alert lifecycle

Hand-rolled (not XState — the backend is Python) and implemented with
the GoF **State** pattern in
[`app/alerts/state_machine.py`](app/alerts/state_machine.py): each
state is its own class (`ArmedState`, `TriggeredState`,
`AcknowledgedState`, `ExpiredState`, `CancelledState`) with its own
`on_tick`/`on_ack`/`on_cancel`/`on_time_check` handlers. An event with
no transition defined for the current state is an explicit no-op
(inherited from the base class), not something that silently falls
through.

| From | Event | To | Guard |
|---|---|---|---|
| Armed | `PRICE_TICK` | Triggered | tick price crosses the alert's threshold in the specified direction |
| Armed | `USER_CANCEL` | Cancelled | — |
| Armed | `TIME_EXPIRE` | Expired | `now > alert.expires_at` |
| Triggered | `USER_ACK` | Acknowledged | — |
| Triggered | `TIME_EXPIRE` | Expired | not acknowledged within the acknowledgment window |

Every other (state, event) combination — e.g. `USER_ACK` while Armed,
`USER_CANCEL` while Triggered — is a deliberate no-op; see
`tests/test_state_machine.py` for explicit coverage of both the legal
transitions and these illegal ones.

[`app/alerts/engine.py`](app/alerts/engine.py) drives the machine: it
evaluates armed/triggered alerts against each tick (`PRICE_TICK` and,
piggybacking on tick arrival, `TIME_EXPIRE`) and against REST actions
(`USER_ACK`, `USER_CANCEL` via
[`app/routes/alerts.py`](app/routes/alerts.py)), persisting the new
state and appending an audit-trail event for every real transition.

## GoF design patterns

1. **State** — the alert lifecycle above, one class per state, swapped
   on the `Alert` object as transitions fire.
   [`app/alerts/state_machine.py`](app/alerts/state_machine.py)
2. **Observer** — `ConnectionManager` is the subject, each WebSocket
   connection is an observer; this underlies the Publish-Subscribe EIP.
   [`app/messaging/connection_manager.py`](app/messaging/connection_manager.py)
3. **Builder** — `_CandleBuilder` assembles an OHLC `Candle` from a
   sequence of staged `add()` calls (tracking running open/high/low/close)
   before a final `build()` produces the immutable `Candle`.
   [`app/messaging/aggregator.py`](app/messaging/aggregator.py)

## Audit trail

Event-sourced: an append-only `EventLog` table
([`app/models.py`](app/models.py) — `id`, `entity_type`, `entity_id`,
`event_type`, `payload_json`, `occurred_at`) records every tick
ingested and every alert state transition (including creation — an
alert's first event is `CREATED`, not just its first real transition).
Writes go through
[`append_event()`](app/audit/event_log.py), which only ever adds rows,
never updates or deletes.

The `Alert` table's `current_state` column is a materialized view for
fast reads, but it's always derivable by replaying `EventLog` from the
start.
[`reconstruct_alert_state(session, alert_id, as_of)`](app/audit/reconstruct.py)
does exactly that: it replays an alert's `EventLog` rows up to and
including `as_of`, in chronological order, and returns the resulting
state — reading only `EventLog`, never the materialized `Alert` row.

**Proof it actually replays, not just reads the current row:**
[`tests/test_reconstruct.py::test_reconstruct_returns_the_state_as_of_a_point_between_two_real_transitions`](tests/test_reconstruct.py)
drives an alert through two real transitions (`PRICE_TICK` then
`USER_ACK`, with a real wall-clock gap between them), reconstructs
state at a timestamp sampled between the two, and asserts it returns
`"triggered"` — the alert's state at that point in time — even though
the alert's current row already reads `"acknowledged"`.

## Perfect Framework concerns

1. **Audit trail** — event-sourced `EventLog` + point-in-time replay,
   as above.
   [`app/models.py`](app/models.py),
   [`app/audit/event_log.py`](app/audit/event_log.py),
   [`app/audit/reconstruct.py`](app/audit/reconstruct.py)
2. **Secrets management** — all environment-dependent config (CORS/WS
   origin allowlist, database URL) comes from `.env`
   ([`app/config.py`](app/config.py)), nothing hardcoded, `.env`
   gitignored (`.env.example` documents the shape). The WebSocket
   endpoint enforces the origin allowlist at connect time, not just
   CORS on the REST side.
   [`app/routes/ws.py`](app/routes/ws.py)
3. **Deploy** — split frontend (Netlify, static) / backend (Render,
   FastAPI + WebSocket), including a pinned Python version (Render
   ignores `runtime.txt`) and a documented cold-start risk/mitigation
   for demo day.
   [`render.yaml`](render.yaml), [`netlify.toml`](netlify.toml),
   [`DEPLOY.md`](DEPLOY.md)

## Design note: alert-trigger broadcast scope

When an alert transitions to Triggered, the notification is broadcast
on the alert's **symbol topic** — the same mechanism as ticks and
candles — rather than to a specific "owning" client, since this sprint
has no auth/session model to identify one. Any client subscribed to
that symbol sees the trigger. See
[`app/main.py`](app/main.py) (`_serialize_alert_triggered`).

## Presentation notes

Everything below in one place for the 15-minute walkthrough:

- **Demo flow:** open the live frontend → point out the live ticker
  table updating every second → uncheck a symbol and show its row
  freeze while others keep updating (pub-sub topic filtering, visibly)
  → point out the candles table → create an alert with a threshold
  just past a symbol's current price → watch it trigger (notification
  + row flips state) → click Ack.
- **4 EIPs**, each with a one-line description, file, and
  enterpriseintegrationpatterns.com citation: see the table above.
- **State chart**: states/events/transitions/guards table above,
  implemented via GoF **State** in `state_machine.py`, driven by
  `engine.py`.
- **3 GoF patterns**: State (`state_machine.py`), Observer
  (`connection_manager.py`, underlying Publish-Subscribe), and Builder
  (`_CandleBuilder` in `aggregator.py`, staged `add()`/`build()` calls
  assembling an OHLC `Candle`).
- **Audit trail**: `EventLog` (event-sourced, append-only) +
  `reconstruct_alert_state` — cite the specific test
  (`test_reconstruct_returns_the_state_as_of_a_point_between_two_real_transitions`)
  as the concrete proof of point-in-time reconstruction, not just an
  assertion in prose.
- **3 Perfect Framework concerns**: audit trail, secrets management,
  deploy — file pointers above.
- **Known scope decision**: alert triggers broadcast per-symbol, not
  per-owning-client, because there's no auth this sprint.
- **Test suite**: 47 tests, `pytest` from repo root — router, enricher,
  aggregator, connection manager, event log, state machine, alerts
  engine, alerts REST routes, WS integration (two concurrent clients +
  clean disconnect), and reconstruction, all covered independently.
