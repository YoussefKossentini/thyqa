# Thiqa API v1 (frozen contract)

Base URL `http://<demo-pc>:8000`. All bodies are JSON. Money is always integer
**millimes** (1 TND = 1000). Types live in `thiqa/schemas.py`; if this file and
`schemas.py` disagree, `schemas.py` wins.

Ops actions need the header `X-Ops-Pin: <OPS_PIN from .env>`. Reads are open on
the LAN for the dashboard. The public door is rate limited and size limited
(4 KB body, 600 characters per message).

## Public door

The client app, Zbayen (simulator), Sarrak (red team) and the Hack Thiqa page
all use these three calls. Nobody gets a side entrance.

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/v1/cases` | `{"tenant_id"?: "9antra", "channel": "text" \| "voice" \| "hack_us"}` | `{case_id, tenant_id, state, reply, mode, disclosure}` |
| POST | `/api/v1/interaction/turn` | `{"case_id", "text", "payment_method"?}` | `TurnResult` |
| POST | `/api/v1/interaction/confirm` | `{"case_id", "offer_hash", "payment_method"?}` + optional `Idempotency-Key` header | `TurnResult` with `payment`, `decision`, `notice` |
| GET | `/api/v1/cases/{case_id}` | | public case view: state, transcript, offer, payments, radar |
| POST | `/api/v1/cases/{case_id}/close` | `{}` | case closed as lost |

`payment_method` is a sandbox token: `tok_ok`, `tok_insufficient`, `tok_timeout`,
`tok_fraud`, `bank_transfer_sim`. No card number field exists anywhere.

`TurnResult`:

```json
{
  "case_id": "case_...", "reply": "Na3ref... tnajjem tkhallas 3la 3 marrat (500 DT).",
  "mode": "MOCK", "state": "offer_proposed", "withheld": false,
  "offer": {"offer_hash": "3b32...", "product_name": "AI Engineer Bootcamp", "plan_id": "x3",
            "total_millimes": 1500000, "due_now_millimes": 500000, "schedule_millimes": [500000, 500000, 500000], "currency": "TND"},
  "radar": {"price_sensitivity": 80, "trust": 55, "urgency": 30, "comprehension": 70, "intent": 65},
  "payment": null, "decision": null, "notice": null
}
```

A client confirms an offer in one of two ways, both deterministic: the
`/interaction/confirm` call with the offer hash (the button on the offer card),
or by typing an explicit phrase such as `nconfirmi` / `je confirme` / `I confirm`
while an offer is on the table. Fahem's opinion never triggers a payment.

## Ops dashboard

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/kpis?tenant_id=&scope=live` | `KpiSnapshot`; `scope` is `live` or a `run_id` |
| GET | `/api/v1/events?tenant_id=&after_seq=0&limit=200` | catch-up for the Majlis feed |
| WS | `/ws/events?tenant_id=` | live stream, one `EventEnvelope` per message |
| GET | `/api/v1/approvals?tenant_id=&status=pending` | |
| POST | `/api/v1/approvals/{approval_id}/approve` | PIN, `{"approver_id": "mouna"}` |
| POST | `/api/v1/approvals/{approval_id}/reject` | PIN, `{"approver_id": "mouna"}` |
| GET | `/api/v1/audit?limit=50` | latest audit rows |
| POST | `/api/v1/audit/verify` | `{ok, checked, first_bad_seq, reason, anchors_ok}` |
| GET | `/api/v1/security/status` | policy hash + signature state, SIEM online/offline, quarantines |
| GET | `/api/v1/security/alerts?tenant_id=` | Bouab and Wazuh alerts |
| GET | `/api/v1/agents` | the 6 agents + Sarrak: status, permissions, quarantine |
| POST | `/api/v1/agents/{agent_id}/release` | PIN, `{"case_id"?: "...", "by": "youssef"}`; only a human lifts a quarantine |
| GET | `/api/v1/policy` | permission matrix as loaded at startup |
| GET | `/api/v1/tenants` / POST `/api/v1/tenants/active` | live tenant switch (PIN) |
| GET | `/api/v1/limits` | content of the Limits screen |
| GET | `/api/v1/scripts?tenant_id=` | script versions and status |
| POST | `/api/v1/strategy/propose` | PIN, `{"tenant_id", "run_id"?}`: Le Renard recommends + drafts v(N+1), Bouab checks it |
| POST | `/api/v1/scripts/{version}/activate` | PIN, `{"tenant_id", "approver_id"}`: a human activates |
| POST | `/api/v1/runs` | PIN, `{"tenant_id", "n": 50, "seed": 42, "script_version"?}`: Zbayen batch run |
| GET | `/api/v1/runs?tenant_id=` / `/api/v1/runs/compare?a=&b=` | Run 1 vs Run 2 panel |
| POST | `/api/v1/redteam/benchmark` | PIN: Sarrak runs the attack corpus, returns block rate and false positives |
| GET | `/api/v1/hack/scoreboard` | attacks / blocked / escalated for the Hack Thiqa page |
| POST | `/api/v1/payments/{payment_id}/simulate-transfer` | PIN: settles a `bank_transfer_sim` payment |
| GET | `/api/v1/recommendations?tenant_id=` | Le Renard's latest recommendations |
| POST | `/api/v1/cases/{case_id}/reopen` | PIN, `{"by": "mouna"}`: only a human takes a case out of BLOCKED |

Pages served by the backend: `/console` (ops console, reference implementation of every
call), `/client` (client app), `/hack` (same app in Hack Thiqa mode with scoreboard).

### Demo buttons (PIN)

`POST /api/v1/demo/<name>` with `{"case_id"?}`:

| name | What happens |
|---|---|
| `compromised-tool-call` | a hijacked Sahbi calls `pay.create_intent` through the gateway: TOOL_DENIED |
| `direct-engine-call` | a hijacked agent calls Sandouk Pay directly with no token: rejected by the engine |
| `forged-token` | same call with a hand-made token: bad signature, rejected |
| `amount-swap` | uses an approved approval with a changed amount: hash mismatch, refused |
| `self-approval` | the requester tries to approve its own request: refused |
| `double-submit` | confirms the same offer twice: R04, one payment |
| `card-testing` | 6 quick attempts with failing tokens: R07 velocity BLOCK + alert |
| `tamper-audit` | edits one audit row in SQLite; the next Verify turns red |
| `fake-events` | emits a scripted event sequence so the frontend can work without agents |
| `reset` | wipes the demo database (keeps policy and tenant packs) |

## Internal API (Wazuh Security Bridge only)

Signed with `X-Thiqa-Timestamp` and `X-Thiqa-Signature: sha256=<hex>`, where the
hex is `HMAC_SHA256(INTERNAL_API_SECRET, timestamp + "." + raw_body)`. Requests
older than 60 s are refused.

| Method | Path | Body |
|---|---|---|
| POST | `/internal/siem/alerts` | `{"alert_id", "rule_id", "level", "description", "agent_id"?, "case_id"?, "event_type"?}` |
| POST | `/internal/siem/heartbeat` | `{"bridge": "wazuh"}` |
| POST | `/internal/bouab/quarantine-request` | `{"agent_id", "case_id"?, "rule_id", "alert_id"}` |

Wazuh can ask for a quarantine. Bouab decides, and only a human lifts it.

## Event envelope (WebSocket, events table, audit, replay)

```json
{
  "event_id": "ev_...", "seq": 412, "ts": "2026-11-08T01:12:09.123Z",
  "tenant_id": "9antra", "case_id": "case_...", "run_id": null, "correlation_id": "cor_...",
  "type": "bouab.decision", "source": "bouab", "target": "sandouk",
  "decision": "REQUIRE_APPROVAL", "severity": "medium", "mode": null, "simulated": true,
  "summary": "Bouab: REQUIRE_APPROVAL for 1,500 TND (R02 above approval threshold)",
  "payload": {"decision_id": "dec_...", "risk_score": 15, "reasons": [{"code": "R02_APPROVAL_THRESHOLD", "rule_id": "R02", "message": "..."}]}
}
```

`type` values:

| type | source → target | Feed chip |
|---|---|---|
| `case.opened`, `case.state_changed` | orchestrator | |
| `turn.client` | client → sahbi | |
| `turn.sahbi` | sahbi → client | LIVE / REPLAY / MOCK |
| `guard.input_flagged` | bouab → client | BLOCK |
| `guard.output_rewritten` | bouab → sahbi | BLOCK |
| `fahem.analysis` | fahem → orchestrator | radar in payload |
| `offer.proposed`, `offer.accepted` | sahbi / client → sandouk | |
| `bouab.tool_denied` | bouab → agent | BLOCK |
| `bouab.decision` | bouab → sandouk | ALLOW / BLOCK / REQUIRE_APPROVAL |
| `approval.requested`, `approval.vote`, `approval.granted`, `approval.rejected`, `approval.refused` | bouab / human | APPROVAL |
| `bouab.authorization_issued` | bouab → sandouk | |
| `payment.created`, `payment.updated`, `payment.engine_rejected`, `payment.retry_proposed` | sandouk | SIMULATED |
| `ledger.posted` | sandouk → si_hsab | |
| `kpi.updated` | si_hsab | |
| `security.alert`, `agent.quarantined`, `agent.released`, `policy.tampered` | bouab | |
| `script.proposed`, `script.checked`, `script.activated`, `strategy.recommendations` | le_renard / bouab / human | |
| `audit.verified` | bouab | green / red |
| `run.started`, `run.finished`, `redteam.benchmark`, `tenant.switched` | system | |
| `siem.alert`, `siem.status` | wazuh | |

Rendering rule for the frontend: `turn.client` carries the client's text in
`payload.text`. Render it as text, never as HTML (injection attempts land there).

## security.jsonl (for Wazuh)

One JSON object per line, fixed fields only, values limited to `[A-Za-z0-9_.:-]`
and 64 characters. Never client text, PII or keys.

```json
{"app":"thiqa","ts":"2026-11-08T01:12:09Z","tenant_id":"9antra","correlation_id":"cor_ab12","agent_id":"sahbi","event_type":"TOOL_DENIED","tool":"pay.create_intent","decision":"BLOCK","reason":"P01_TOOL_DENIED","severity":"high"}
```

`event_type` values: `TOOL_DENIED`, `prompt_injection_detected`, `output_guard_rewrite`,
`payment_blocked`, `payment_engine_rejected`, `approval_self_attempt`,
`approval_replay`, `approval_hash_mismatch`, `agent_quarantined`,
`audit_chain_invalid`, `policy_file_changed`, `velocity_block`.
