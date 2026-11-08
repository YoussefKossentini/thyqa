"""Agent kill switch: 3 denied calls or an abnormal burst puts one agent on one case
in quarantine. Only a human lifts it."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from ..db import Repo
from ..schemas import utcnow


class KillSwitch:
    def __init__(self, repo: Repo, denied_calls: int = 3, window_s: int = 60, burst_calls: int = 40, burst_window_s: int = 10):
        self.repo = repo
        self.denied_calls = denied_calls
        self.window_s = window_s
        self.burst_calls = burst_calls
        self.burst_window_s = burst_window_s
        self._denied: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._calls: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    @staticmethod
    def _push(q: deque[float], window: int) -> int:
        now = time.monotonic()
        q.append(now)
        while q and now - q[0] > window:
            q.popleft()
        return len(q)

    def record_call(self, agent_id: str, case_id: str) -> bool:
        """True when this call makes the agent exceed the burst limit."""
        return self._push(self._calls[(agent_id, case_id)], self.burst_window_s) > self.burst_calls

    def record_denied(self, agent_id: str, case_id: str) -> bool:
        """True when this denial reaches the quarantine threshold."""
        return self._push(self._denied[(agent_id, case_id)], self.window_s) >= self.denied_calls

    def quarantine(self, agent_id: str, case_id: str, tenant_id: str, reason: str, requested_by: str = "bouab") -> None:
        if not self.repo.is_quarantined(agent_id, case_id):
            self.repo.quarantine_agent(agent_id, case_id, tenant_id, reason, requested_by, utcnow().isoformat())

    def is_quarantined(self, agent_id: str, case_id: str) -> bool:
        return self.repo.is_quarantined(agent_id, case_id)

    def lift(self, agent_id: str, case_id: str | None, by_human: str) -> int:
        self._denied = defaultdict(deque, {k: v for k, v in self._denied.items() if k[0] != agent_id})
        return self.repo.lift_quarantine(agent_id, case_id, by_human, utcnow().isoformat())
