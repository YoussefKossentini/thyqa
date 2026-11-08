#!/usr/bin/env python3
"""Thiqa Security Bridge: Wazuh alerts.json -> Thiqa SecOps panel. Standard library only.

Run it where the Wazuh MANAGER writes alerts.json:
    export INTERNAL_API_SECRET=...        # same value as in Thiqa's .env
    python3 security_bridge.py --alerts /var/ossec/logs/alerts/alerts.json --api http://<thiqa-host>:8000
    python3 security_bridge.py --api http://<thiqa-host>:8000 --test      # sends one fake alert

Wazuh observes and asks; Bouab decides; only a human lifts a quarantine.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections import deque

THIQA_RULES = {"100001", "100002", "100003", "100004", "100005", "100006", "100007", "100008"}
QUARANTINE_RULES = {"100002", "100004"}


def post(api: str, secret: bytes, path: str, payload: dict) -> dict:
    if not api.startswith(("http://", "https://")):
        raise ValueError("--api must be an http(s) URL")
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = "sha256=" + hmac.new(secret, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(api.rstrip("/") + path, data=body, method="POST", headers={
        "content-type": "application/json", "x-thiqa-timestamp": ts, "x-thiqa-signature": sig})
    with urllib.request.urlopen(req, timeout=5) as r:  # nosec B310 - scheme checked above
        return json.loads(r.read() or b"{}")


def follow(path: str, from_start: bool):
    """Yield new lines (or None when idle). Survives log rotation."""
    fh, inode, first = None, None, True
    while True:
        try:
            st = os.stat(path)
            if fh is None or st.st_ino != inode or st.st_size < fh.tell():
                if fh:
                    fh.close()
                fh, inode = open(path, encoding="utf-8", errors="replace"), st.st_ino
                if first and not from_start:
                    fh.seek(0, os.SEEK_END)
                first = False
            line = fh.readline()
            if line:
                yield line
                continue
        except FileNotFoundError:
            pass
        yield None
        time.sleep(0.5)


def to_payload(alert: dict) -> dict | None:
    rule = alert.get("rule", {})
    rid = str(rule.get("id", ""))
    if rid not in THIQA_RULES and "thiqa" not in rule.get("groups", []):
        return None
    data, sys = alert.get("data", {}) or {}, alert.get("syscheck", {}) or {}
    return {"alert_id": alert.get("id") or f"{rid}-{alert.get('timestamp')}", "rule_id": rid, "level": rule.get("level", 0),
            "description": rule.get("description", ""), "agent_id": data.get("agent_id"), "tenant_id": data.get("tenant_id"),
            "event_type": data.get("event_type") or (f"fim_{sys.get('event')}" if sys else None), "file": sys.get("path")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alerts", default="/var/ossec/logs/alerts/alerts.json")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--secret-env", default="INTERNAL_API_SECRET")
    ap.add_argument("--from-start", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    secret = os.environ.get(args.secret_env, "").encode()
    if not secret:
        raise SystemExit(f"{args.secret_env} is not set")
    if args.test:
        print(post(args.api, secret, "/internal/siem/heartbeat", {"bridge": "wazuh"}))
        print(post(args.api, secret, "/internal/siem/alerts", {"alert_id": f"test-{int(time.time())}", "rule_id": "100006",
                                                              "level": 14, "description": "TEST: protected file changed: policy.yaml"}))
        return
    seen: deque[str] = deque(maxlen=5000)
    last_beat = 0.0
    print(f"bridge: {args.alerts} -> {args.api}")
    for line in follow(args.alerts, args.from_start):
        now = time.time()
        if now - last_beat > 20:
            try:
                post(args.api, secret, "/internal/siem/heartbeat", {"bridge": "wazuh"})
            except (urllib.error.URLError, OSError) as exc:
                print("heartbeat failed:", exc)
            last_beat = now
        if not line:
            continue
        try:
            payload = to_payload(json.loads(line))
        except ValueError:
            continue
        if not payload or payload["alert_id"] in seen:
            continue
        seen.append(payload["alert_id"])
        try:
            post(args.api, secret, "/internal/siem/alerts", payload)
            if payload["rule_id"] in QUARANTINE_RULES and payload.get("agent_id"):
                print("quarantine request:", post(args.api, secret, "/internal/bouab/quarantine-request", {
                    "agent_id": payload["agent_id"], "rule_id": payload["rule_id"], "alert_id": payload["alert_id"]}))
            print(f"forwarded rule {payload['rule_id']} level {payload['level']}: {payload['description']}")
        except (urllib.error.URLError, OSError) as exc:
            print("forward failed (Thiqa keeps working, SIEM shows offline):", exc)


if __name__ == "__main__":
    main()
