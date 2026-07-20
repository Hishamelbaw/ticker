# Ticker — Architecture Plan (Sprint 2: Messaging-Rich System)

Solo build. Target: 4-week Python/FastAPI system, same deploy shape as
Job Pack (Netlify frontend + Render backend), so infra risk is low and
sprint time goes into the messaging/state-chart requirements.

## Concept

A live market-ticker system. A background generator produces synthetic
price ticks for a handful of symbols. Ticks flow through a real EIP
pipeline (routed, enriched, aggregated) and are broadcast to browser
clients over WebSockets. Users can arm price alerts ("notify me when
AAPL crosses $150") that are evaluated against the live tick stream and
driven by an explicit state chart. Every tick and every alert state
transition is written to an append-only event log, so any alert's state
at any past moment can be reconstructed — the audit trail requirement.

Using synthetic data sidesteps any real-market-data licensing/TOS
question entirely (same spirit as Sprint 1's "no scraping" constraint)
while still producing a continuous, realistic message stream to
demonstrate pub-sub under load.

## Enterprise Integration Patterns (4 implemented, ≥3 required)

1. **Publish-Subscribe (required, via WebSockets).** A
   `ConnectionManager` maintains per-symbol subscriber lists; clients
   subscribe to specific symbols over a WebSocket connection and receive
   only the topics they asked for. This is also where GoF **Observer**
   lives in the code (see below) — the manager is the subject, each
   WebSocket connection is an observer.
2. **Message Router.** Incoming internal events (`tick`, `alert_check`,
   `candle_close`) are routed by type to the correct handler/topic
   before anything else happens to them — a single dispatch point, not
   scattered `if` checks.
3. **Content Enricher.** Each raw tick is enriched with computed fields
   (percent change from previous tick, rolling moving average) before
   being published — the enriched message carries more information than
   the raw input.
4. **Aggregator.** Raw ticks are combined over a rolling time window
   into OHLC candle bars (open/high/low/close), published on a separate
   `candles` topic distinct from the raw `ticks` topic.

## State chart (required, ≥1)

**Alert lifecycle**, hand-rolled (not XState, since the backend is
Python) and implemented using the GoF **State** pattern — each state is
its own class with its own `on_tick`/`on_ack`/`on_cancel` handlers,
selected by the alert's current state.

States: `Armed`, `Triggered`, `Acknowledged`, `Expired`, `Cancelled`.

Events: `PRICE_TICK`, `USER_ACK`, `USER_CANCEL`, `TIME_EXPIRE`.

Transitions:
- `Armed` --`PRICE_TICK`--> `Triggered` **[guard: tick price crosses the
  alert's threshold in the specified direction]**
- `Armed` --`USER_CANCEL`--> `Cancelled`
- `Armed` --`TIME_EXPIRE`--> `Expired` **[guard: now > alert.expires_at]**
- `Triggered` --`USER_ACK`--> `Acknowledged`
- `Triggered` --`TIME_EXPIRE`--> `Expired` **[guard: not acknowledged
  within the acknowledgment window]**

This gets documented as a table plus a short diagram in the README,
exactly as the rubric asks (states / events / transitions / guards).

## GoF design patterns (2 implemented, ≥2 required for presentation)

1. **Observer** — `ConnectionManager` (subject) / WebSocket connections
   (observers), underlying the Publish-Subscribe EIP.
2. **State** — the alert lifecycle, one class per state, swapped out on
   the `Alert` object as transitions fire.

## Persistence + audit trail (Perfect Framework concern #1, required)

Event-sourced: an append-only `EventLog` table (`id`, `entity_type`,
`entity_id`, `event_type`, `payload_json`, `occurred_at`) records every
tick ingested and every alert state transition. Current alert state is
a materialized view for fast reads, but it is always derivable by
replaying `EventLog` from the beginning — a `reconstruct_alert_state
(alert_id, as_of)` function replays events up to a timestamp and
returns what the alert's state was at that moment. This is what "every
mutation must be reconstructable" means in practice, and it's exercised
by an actual test, not just asserted in prose.

## Other Perfect Framework concerns (2 more, ≥3 total required)

- **Secrets management** — same discipline as Sprint 1: WebSocket
  origin allowlist, any config values via `.env`, nothing hardcoded,
  `.env` gitignored. (No LLM this sprint, so no API keys — but CORS/WS
  origin config still needs to not be hardcoded per environment.)
- **Deploy** — split frontend (Netlify, static) / backend (Render,
  FastAPI + WebSocket endpoint), reusing the proven Sprint 1 deploy
  shape.

## File structure

```
ticker/
├── .env.example
├── .gitignore
├── requirements.txt
├── render.yaml
├── netlify.toml
├── README.md
├── app/
│   ├── main.py                    # FastAPI app, WebSocket route, lifespan
│   ├── config.py                  # env-based config (origins, DB url)
│   ├── db.py                      # SQLAlchemy engine/session
│   ├── models.py                  # EventLog, Alert (materialized) ORM models
│   ├── schemas.py                 # Pydantic models
│   ├── messaging/
│   │   ├── connection_manager.py  # Observer subject; Pub-Sub EIP
│   │   ├── router.py              # Message Router EIP
│   │   ├── enricher.py            # Content Enricher EIP
│   │   └── aggregator.py          # Aggregator EIP (candle building)
│   ├── alerts/
│   │   ├── state_machine.py       # State pattern: Armed/Triggered/.../Cancelled
│   │   └── engine.py              # evaluates ticks against armed alerts
│   ├── audit/
│   │   ├── event_log.py           # append-only writer
│   │   └── reconstruct.py         # replay-to-timestamp reconstruction
│   ├── generator.py                # synthetic tick generator (background task)
│   └── routes/
│       ├── ws.py                   # WebSocket endpoint (subscribe/unsubscribe)
│       └── alerts.py               # REST: create/list/ack/cancel alerts
├── frontend/
│   ├── index.html                  # live ticker + candle view + alert UI
│   ├── app.js                      # WebSocket client, renders live updates
│   ├── config.js                   # WS_URL / API_BASE_URL
│   └── style.css
└── tests/
    ├── test_router.py
    ├── test_enricher.py
    ├── test_aggregator.py
    ├── test_state_machine.py
    └── test_reconstruct.py         # proves audit-trail replay actually works
```

## Suggested build order

1. FastAPI skeleton + WebSocket echo endpoint + deploy config early
   (same lesson as Sprint 1: get something live fast).
2. `generator.py` — synthetic tick production on an interval, no
   pipeline yet, just prove ticks flow.
3. `messaging/router.py`, `enricher.py`, `aggregator.py` — the 3
   non-pub-sub EIPs, each independently unit-testable.
4. `messaging/connection_manager.py` + `routes/ws.py` — wire
   Publish-Subscribe (Observer) on top of the pipeline; verify multiple
   browser tabs receive the same live stream, each able to subscribe to
   a subset of symbols.
5. `models.py` + `audit/event_log.py` — start logging every tick and
   (once it exists) every alert transition.
6. `alerts/state_machine.py` (State pattern) + `alerts/engine.py` +
   `routes/alerts.py` — the alert feature end-to-end, transitions
   written to the event log as they fire.
7. `audit/reconstruct.py` + `tests/test_reconstruct.py` — prove replay
   works, not just that events get logged.
8. Frontend: live ticker table, candle display, alert creation/ack UI.
9. Deploy (Render + Netlify, same shape as Sprint 1) and confirm
   multi-subscriber pub-sub actually survives a disconnect/reconnect —
   that's the difference between the rubric's 25pt and 15pt pub-sub
   tiers.
10. Tests + README (EIP citations to enterpriseintegrationpatterns.com,
    state chart table, audit trail explanation, Perfect Framework
    concerns named with file pointers) + presentation prep.

## First prompt to give Claude Code

> I'm building "Ticker" for CS 3660 Sprint 2 — a live market-ticker
> system demonstrating messaging patterns under load. Read
> ARCHITECTURE.md in this repo for the full design: 4 Enterprise
> Integration Patterns (Publish-Subscribe via WebSockets, Message
> Router, Content Enricher, Aggregator), an explicit hand-rolled state
> chart for a price-alert lifecycle implemented with the GoF State
> pattern, Observer underlying the pub-sub layer, and an event-sourced
> audit trail that can reconstruct any alert's state at any past
> moment. Scaffold the project per the file structure and build order
> in ARCHITECTURE.md, starting with step 1 (FastAPI skeleton, a working
> WebSocket echo endpoint, .env.example, .gitignore, deploy config
> stubs). Stop after each step so I can review before continuing.
