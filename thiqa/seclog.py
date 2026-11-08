"""security.jsonl: the only thing Wazuh reads from the app.

Fixed fields, values cut to [A-Za-z0-9_.:-] and 64 characters. Client text, PII
and keys never reach this file, so a forged message cannot become a forged log
line (log injection).
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .schemas import utcnow

_UNSAFE = re.compile(r"[^A-Za-z0-9_.:\-]")
FIELDS = ("app", "ts", "tenant_id", "correlation_id", "agent_id", "event_type", "tool", "decision", "reason", "severity")


def clean(value: object) -> str:
    text = _UNSAFE.sub("_", str(value if value not in (None, "") else "-"))
    return text[:64] or "-"


class SecurityLog:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, *, tenant_id: str, correlation_id: str, agent_id: str, event_type: str,
              tool: str | None = None, decision: str | None = None, reason: str | None = None,
              severity: str = "info") -> dict[str, str]:
        line = {
            "app": "thiqa",
            "ts": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tenant_id": clean(tenant_id),
            "correlation_id": clean(correlation_id),
            "agent_id": clean(agent_id),
            "event_type": clean(event_type),
            "tool": clean(tool),
            "decision": clean(decision),
            "reason": clean(reason),
            "severity": clean(severity),
        }
        with self.lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, separators=(",", ":")) + "\n")
        return line

    def tail(self, n: int = 50) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
