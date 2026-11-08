# THYQA: API guide for building your own frontend

Backend: FastAPI. Run `run.bat`, then:

| What | URL |
|---|---|
| **Swagger UI** (try every call) | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| **OpenAPI contract** (JSON, generate a typed client) | http://localhost:8000/openapi.json (a copy is saved in `docs/openapi.json`) |
| Live event stream | `ws://localhost:8000/ws/events?tenant_id=9antra` |

Generate a typed client from the contract, for example `npx openapi-typescript docs/openapi.json -o api.d.ts`.

## Rules to know before you start

- All bodies are JSON. **Money is always an integer in millimes** (1 DT = 1000). Never use floats.
- **Public calls** (no header): the visitor chat, the voice transcription, reads for dashboards.
- **Operator calls** need the header `X-Ops-Pin: <OPS_PIN from .env>` (demo PIN: `2468`). A missing or wrong PIN returns 401.
- The public door is rate limited (429 `rate limited`) and size limited: 4 KB for most public bodies, about 1.3 MB for `/api/v1/voice`. A message is at most 2000 characters in the API (the UI limits it to 600).
- Frontend on another port (for example Vite at 5173): the server already allows `http://localhost:5173`. Add other origins with the env var `THIQA_CORS_ORIGINS` (comma-separated). Vite can also proxy `/api` and `/ws` to port 8000, see `web/vite.config.js`.
- Text from the AI (replies, summaries) must be rendered as plain text, never as HTML.
- Every AI output carries a `mode`: `LIVE`, `REPLAY` or `MOCK`. Every payment is simulated: show "SIMULÉ".
- The display names of the agents (Sboui, Fouchika...) come from `thiqa/names.py`. The ids (`sahbi`, `bouab`...) never change.

## 1. Visitor chat (public)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/v1/tenants` | | `{active, tenants:[{tenant_id, display_name, kind, currency, approval_threshold, approvers, catalog:[{product_id, name, price_millimes, plans:[{plan_id, installments, due_now_millimes, total_millimes}], duration, schedule, highlights}]}]}`. Use it for the catalog and prices. |
| POST | `/api/v1/cases` | `{tenant_id?, channel?: "text"\|"voice"\|"hack_us", lang?}` | `{case_id, tenant_id, state, reply, mode, disclosure}`. Opens a conversation, `reply` is the greeting. |
| POST | `/api/v1/interaction/turn` | `{case_id, text (≤2000), payment_method?}` | `TurnResult` (below) |
| POST | `/api/v1/interaction/confirm` | `{case_id, offer_hash, payment_method?}` + optional header `Idempotency-Key` | `TurnResult` with `payment`, `decision`, `notice` |
| GET | `/api/v1/cases/{case_id}` | | public view: state, transcript, offer, payments, radar |
| POST | `/api/v1/cases/{case_id}/close` | | closes the conversation as lost |
| POST | `/api/v1/voice/transcribe` | `{audio_b64 (≤1.2 MB), mime?: "audio/wav"}` | `{text, silence?}`. 503 if no Gemini key or quota reached: tell the user to type. 16 kHz mono WAV works best. |
| GET | `/api/v1/hack/scoreboard` | | `{sessions, messages, attacks_blocked, replies_rewritten, escalated_to_human, cases_blocked, legit_test_payments}` |

`payment_method` is a sandbox token: `tok_ok` (success), `tok_insufficient` (declined), `tok_timeout` (bank does not answer), `tok_fraud` (flagged), `bank_transfer_sim` (simulated transfer). There is no card field anywhere.

`TurnResult`:

```json
{
  "case_id": "case_...", "reply": "Na3ref... tnajjem tkhallas 3la 3 marrat (500 DT).",
  "mode": "MOCK", "state": "offer_proposed", "withheld": false,
  "offer": {"offer_hash": "3b32...", "product_name": "AI Engineer Bootcamp", "plan_id": "x3",
            "total_millimes": 1500000, "due_now_millimes": 500000,
            "schedule_millimes": [500000, 500000, 500000], "currency": "TND"},
  "radar": {"price_sensitivity": 80, "trust": 55, "urgency": 30, "comprehension": 70, "intent": 65},
  "payment": null, "decision": null, "notice": null
}
```

- `withheld: true` means the security layer stopped the client message: the agent never read it.
- `decision` is `ALLOW`, `BLOCK` or `REQUIRE_APPROVAL`. With `REQUIRE_APPROVAL` the payment waits for a human, show a "waiting" state and listen to the events.
- `state` values: `new`, `conversing`, `offer_proposed`, `awaiting_approval`, `paid`, `payment_failed`, `blocked`, `closed`.

**Chat flow:** `GET /tenants` → `POST /cases` → loop `POST /interaction/turn` → when `offer` appears, show the offer card → `POST /interaction/confirm` with `offer.offer_hash` → show success, refused or waiting from `payment` and `decision`.

## 2. Team console (reads are open, actions need the PIN)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/kpis?tenant_id=&scope=live` | `{interactions, interested, offers_proposed, conversions, conversion_rate, payments:{succeeded, declined, pending, blocked, awaiting_approval}, revenue_collected_millimes, contract_value_millimes, top_objections, revenue_lost_by_objection, satisfaction:{positive, neutral, negative, score_0_100}}`. `scope` is `live` or a `run_id`. |
| GET | `/api/v1/events?tenant_id=&after_seq=&limit=&case_id=&run_id=` | catch-up for the live feed. Event: `{event_id, seq, ts, tenant_id, case_id, run_id, correlation_id, type, source, target, decision, severity, mode, simulated, summary, payload}` |
| WS | `/ws/events?tenant_id=` | on connect: the last 60 events, then one event per message (same shape). Reconnect on close. |
| GET | `/api/v1/agents` | `[{agent_id, name, role, built_with, color, allowed_tools, quarantines}]` |
| GET | `/api/v1/approvals?tenant_id=&status=pending` | payments waiting for a human |
| POST | `/api/v1/approvals/{approval_id}/approve` | PIN. `{approver_id}`. The requester cannot approve their own request. |
| POST | `/api/v1/approvals/{approval_id}/reject` | PIN. `{approver_id}` |
| POST | `/api/v1/agents/{agent_id}/release` | PIN. `{by, case_id?, tenant_id?}`. Only a human lifts a quarantine. |
| POST | `/api/v1/cases/{case_id}/reopen` | PIN. `{by, tenant_id?}`. Only a human reopens a blocked case. |
| POST | `/api/v1/payments/{payment_id}/simulate-transfer` | PIN. Settles a `bank_transfer_sim` payment (`{succeed?: bool}`). |
| POST | `/api/v1/tenants/active` | PIN. `{tenant_id}`. Switches the active tenant (`9antra`, `nakhla`). |

## 3. Learning loop (Run 1 vs Run 2)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/runs` | PIN. `{tenant_id?, n: 50, seed: 42, script_version?}`. Si Zahi simulates n clients. Returns the run summary. |
| GET | `/api/v1/runs?tenant_id=` | list of runs |
| GET | `/api/v1/runs/compare?a=<run_id>&b=<run_id>` | data for the before/after panel |
| POST | `/api/v1/strategy/propose` | PIN. `{tenant_id?, run_id?}`. Zeineb recommends and drafts script v(N+1), Fouchika checks it. |
| GET | `/api/v1/recommendations?tenant_id=` | latest recommendations with evidence |
| GET | `/api/v1/scripts?tenant_id=` | script versions and status |
| POST | `/api/v1/scripts/{version}/activate` | PIN. `{tenant_id?, approver_id}`. A human activates. |

## 4. Security and audit

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/security/status` | policy hash and signature, SIEM online, LLM providers and health, fraud model, ledger balance per tenant |
| GET | `/api/v1/security/alerts?tenant_id=&limit=` | alerts from the security layer and Wazuh |
| GET | `/api/v1/policy` | permission matrix loaded at startup |
| GET | `/api/v1/audit?tenant_id=&limit=` | latest audit rows (hash chain) |
| POST | `/api/v1/audit/verify?tenant_id=` | `{ok, checked, first_bad_seq, reason, anchors_ok}` |
| POST | `/api/v1/redteam/benchmark?tenant_id=` | PIN. Béji Matrix runs the attack corpus: attacks run, stopped, false positives. Takes a few seconds. |
| GET | `/api/v1/limits?lang=fr` | the limits text (the page is not in the app, the endpoint still exists) |

## 5. Utility and demo

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/netinfo` | `{addresses:[...], port}` LAN addresses, for a QR code |
| POST | `/api/v1/llm/test` | PIN. Pings each LLM provider: `{providers:[{provider, model, ok, ms\|error}], voice}` |
| POST | `/api/v1/demo/{name}` | PIN. Scripted demo scenarios (the "Scénarios" drawer). Body `{case_id?, approval_id?, tenant_id?}` |

## 6. Internal (do not call from a frontend)

`POST /internal/siem/alerts`, `/internal/siem/heartbeat`, `/internal/bouab/quarantine-request`: used by the Wazuh bridge.

## Errors

- `401` missing or wrong PIN. `404` unknown id. `413` body too large. `422` invalid body (Swagger shows the schema). `429` rate limited.
- Body of an error: `{"detail": "text"}` or `{"detail": {"message"|"refusal": "..."}}`.

## Schemas (request bodies)

```
CreateCaseIn   {tenant_id?: string, channel?: "text"|"voice"|"hack_us", lang?: Lang}
TurnIn         {case_id: string≤64, text: string≤2000, payment_method?: string}
ConfirmIn      {case_id: string≤64, offer_hash: string≤80, payment_method?: string}
TranscribeIn   {audio_b64: string≤1_200_000, mime?: string}
VoteIn         {approver_id: string≤40}
ByIn           {by: string≤40, case_id?: string, tenant_id?: string}
RunIn          {tenant_id?: string, n?: int, seed?: int, script_version?: int}
ProposeIn      {tenant_id?: string, run_id?: string}
ActivateIn     {tenant_id?: string, approver_id: string≤40}
TenantIn       {tenant_id: string}
SettleIn       {succeed?: boolean}
DemoIn         {case_id?: string, approval_id?: string, tenant_id?: string}
```

Reference implementation: the React app in `web/src` (`lib/api.js`, `lib/useOps.js` for the WebSocket, `pages/Client.jsx` for the chat flow, `lib/voice.js` for the microphone).
