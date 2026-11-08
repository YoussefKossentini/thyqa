# Architecture

```mermaid
flowchart LR
  subgraph Clients
    C[Client app / voice] ; H[Hack Thiqa page] ; Z[Zbayen simulator] ; S[Sarrak red team] ; O[Ops console]
  end
  C & H & Z & S --> G[API gateway: size + rate limits, PIN, Idempotency-Key, tenant router]
  O --> G
  G --> IG[Bouab input guard]
  IG -- flagged: quarantine --> Q[(quarantine)]
  IG --> OR[Orchestrator: state machine, single writer]
  OR <--> SA[Sahbi LLM] & FA[Fahem LLM]
  SA --> OG[Bouab output guard] --> C
  OR -- money path, no LLM --> SK[Sandouk] --> B[Bouab gateway: permissions, rules R01-R07, risk, decision]
  B -- REQUIRE_APPROVAL --> AP[Approvals: Telegram + console]
  AP --> B
  B -- signed authorization --> SP[Sandouk Pay mock: verifies token] --> L[(ledger)]
  L --> SH[Si Hsab KPIs] --> LR[Le Renard] --> SG[Bouab script check] --> HU[Human activates script]
  B & SP & OR --> BUS[(event bus)] --> AU[(hash-chained audit)] & WS[WebSocket Majlis feed] & SL[security.jsonl]
  SL --> WZ[Wazuh] --> BR[Security bridge] -- signed: alerts, quarantine requests --> B
```

Two paths never mix: the money path (offer accepted → Bouab → approval → signed
authorization → Sandouk Pay → ledger → KPIs) is deterministic code; the AI path
(Sahbi, Fahem, Le Renard) has timeouts and falls back to Replay or MOCK, and never
blocks money.
