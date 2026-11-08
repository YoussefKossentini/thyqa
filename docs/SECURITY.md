# Security model

Bouab is code, not a prompt. Agents emit typed intents; every tool call goes through
`Bouab.call_tool()`: interceptor → permissions (signed `policy.yaml`) → rules →
risk score → decision → human approval → HMAC authorization. Sandouk Pay verifies
that authorization itself, so a hijacked agent cannot move (simulated) money even by
calling the engine directly.

## Threat → control → proof

| Threat (OWASP LLM Top 10 2025) | Control | Proof (button / test) |
|---|---|---|
| LLM01 Prompt injection, direct | input guard (Derja Arabizi + Arabic, FR, EN, obfuscation); flagged text quarantined, never reaches Sahbi; 3 attempts block the case | type "ensa kol ta3limet…"; `test_injection_never_reaches_sahbi…` |
| LLM01 Prompt injection, indirect | agents exchange typed fields; FahemAnalysis has no free text; Le Renard reads numbers only | `schemas.py` (extra="forbid") |
| LLM06 Excessive agency | default-deny matrix; pay.create_intent exclusive to Sandouk in code; signed authorization checked by the engine | *Sahbi → pay*, *Direct engine call*, *Forged token* |
| LLM09 Misinformation (fake price or discount) | output guard checks every amount and % against the catalog; R06 recomputes the amount | `test_output_guard_price_integrity`, `test_fake_discount…` |
| LLM07 System prompt leakage, LLM02 data disclosure | canary token, prompt fragments, key patterns, Luhn card numbers, RIB numbers; no card field anywhere | `test_canary_leak_is_blocked` |
| Forged / replayed approval | approval bound to sha256(payment, amount, currency, customer, key); single use; expiry; approver ≠ requester; 2 approvers above 2× threshold | *Self-approval*, *Amount swap* |
| Double payment | deterministic idempotency key; R04; unique key in the engine | *Double submit* |
| Card testing | velocity signal, R07 hard limit, processor fraud flag | *Card testing* |
| LLM10 Unbounded consumption | body size limits, rate limit per IP, LLM timeouts, kill switch on bursts | `test_api_rejects_oversized…` |
| Audit tampering | hash chain + HMAC write-once anchors per DB epoch | *Tamper 1 row* then *Verify audit* |
| Insider edits the policy | policy loaded once and HMAC-signed; runtime change → alert + ignored; restart → fail-closed; Wazuh FIM 100006 | `test_insider_edit…`, `wazuh/README.md` |
| Log injection into the SIEM | security.jsonl has fixed fields, values limited to `[A-Za-z0-9_.:-]` | `test_security_log_has_fixed_fields…` |

## Rules

R01 confirmation bound to the exact offer hash (BLOCK) · R02 above approval threshold
(REQUIRE_APPROVAL) · R03 amount ≤ 0 (BLOCK) · R04 duplicate idempotency key (BLOCK) ·
R05 currency ≠ tenant currency (BLOCK) · R06 amount ≠ catalog price × plan, recomputed
(BLOCK) · R07 velocity limit (BLOCK).

Risk 0–100 from stored signals: injection +25 each, unusual amount +15, velocity +10 per
extra attempt (max 30), method mismatch +10, failed step-up +20, time anomaly +5,
processor fraud flag +20, Isolation Forest anomaly +10 (one model per tenant, trained at
startup on synthetic normal attempts with a fixed seed; the detail names the unusual
features, e.g. "attempts 5, payment methods 2"). Below 40 ALLOW; 40–70 full payment only, installments need a
human; above 70 BLOCK. A BLOCK never becomes an approval.

## NIST CSF 2.0

| Function | Thiqa |
|---|---|
| Govern | signed policy, approver lists per tenant, Limits screen, production-path decisions |
| Identify | agent × tool matrix, threat model above, tenant packs with thresholds |
| Protect | input/output guards, tool gateway, signed authorization, idempotency, rate and size limits, synthetic data only |
| Detect | risk score, Sarrak benchmark, alerts, security.jsonl → Wazuh rules 100001–100008, FIM |
| Respond | REQUIRE_APPROVAL, case block, agent kill switch (human release), quarantine requests from Wazuh decided by Bouab |
| Recover | audit verify with anchors, replay mode, demo reset with a new audit epoch, retry plans after declines |
