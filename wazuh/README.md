# Wazuh SecOps track

Wazuh observes and alerts. Bouab decides. If a SIEM could command the agents, one
forged log line would become an attack, so the bridge can only *ask* Bouab for a
quarantine (rules 100002 and 100004), and only a human lifts it.

## 1. Agent (machine running the Thiqa backend)

Paste `agent_ossec_snippet.xml` into the agent's `ossec.conf`, replace `THIQA_DIR`,
restart the agent. It ships `data/security.jsonl` and watches `config/`, `.env` and
`data/audit_anchor/` with real-time FIM.

## 2. Manager

Copy `local_rules.xml` to `/var/ossec/etc/rules/local_rules.xml` (or append the group),
then `systemctl restart wazuh-manager`. Check with `wazuh-logtest`, pasting lines like:

```
{"app":"thiqa","ts":"2026-11-08T01:12:09Z","tenant_id":"9antra","correlation_id":"cor_1","agent_id":"sahbi","event_type":"TOOL_DENIED","tool":"pay.create_intent","decision":"BLOCK","reason":"P01_TOOL_DENIED","severity":"high"}
{"app":"thiqa","ts":"2026-11-08T01:12:10Z","tenant_id":"9antra","correlation_id":"cor_2","agent_id":"client","event_type":"prompt_injection_detected","tool":"input_guard","decision":"BLOCK","reason":"ignore_instructions_derja","severity":"high"}
{"app":"thiqa","ts":"2026-11-08T01:12:11Z","tenant_id":"9antra","correlation_id":"cor_3","agent_id":"youssef","event_type":"approval_self_attempt","tool":"approval","decision":"BLOCK","reason":"A_SELF_APPROVAL","severity":"high"}
```

Paste the TOOL_DENIED line 5 times within 60 s: rule 100002 must fire once.

## 3. Bridge (where `alerts.json` is)

```
export INTERNAL_API_SECRET=<same value as Thiqa .env>
python3 security_bridge.py --api http://<thiqa-host>:8000 --test     # one fake alert, check the SecOps panel
python3 security_bridge.py --alerts /var/ossec/logs/alerts/alerts.json --api http://<thiqa-host>:8000
```

The console shows **SIEM online** while heartbeats arrive (every 20 s) and
**SIEM offline** after 90 s without one. The platform keeps working either way.

## Hero demo: the insider

1. A teammate edits `config/policy.yaml` and gives Sahbi `pay.create_intent`.
2. Wazuh FIM raises rule 100006 (level 14) in the SecOps panel within seconds.
3. Bouab raises its own `policy.tampered` alert and keeps the policy it loaded at
   startup. Press "Sahbi → pay (hijacked)": still TOOL_DENIED.
4. Even after a restart the edit does not apply: the HMAC signature no longer
   matches, so Bouab starts fail-closed. On top of that, code refuses to give
   `pay.create_intent` to anyone but Sandouk.

Undo the edit before the next run (`git checkout config/policy.yaml`).
