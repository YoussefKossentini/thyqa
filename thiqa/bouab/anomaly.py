"""ML fraud signal: an Isolation Forest per tenant, trained at startup on synthetic
*normal* payment attempts (fixed seed, so the same input always gets the same score).

It is one signal among others (+10 risk when the attempt looks anomalous), never a
decision on its own: rules and thresholds stay deterministic. The detail names the
features that look unusual, so the score explains itself. If scikit-learn is not
installed the signal is simply off.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..tenants import TenantPack

FEATURES = ("amount_ratio", "attempts_window", "distinct_methods", "night", "injections", "client_turns", "minutes_open")
_FITTED: dict[tuple, tuple] = {}

LABELS = {"amount_ratio": "amount vs usual", "attempts_window": "attempts", "distinct_methods": "payment methods",
          "night": "night time", "injections": "injection attempts", "client_turns": "client messages",
          "minutes_open": "minutes in chat"}


@dataclass
class AnomalyResult:
    anomaly: bool
    score: float            # IsolationForest decision_function: below 0 means anomalous
    features: dict[str, float]
    unusual: list[str]

    def detail(self) -> str:
        parts = ", ".join(self.unusual) or "unusual combination"
        return f"isolation forest score {self.score:.2f} ({parts})"


class FraudModel:
    def __init__(self, tenants: list[TenantPack], seed: int = 42, n_samples: int = 800, contamination: float = 0.03):
        self.seed = seed
        self.models: dict[str, tuple] = {}
        try:
            import numpy as np  # noqa: F401
            from sklearn.ensemble import IsolationForest  # noqa: F401
        except ImportError:
            self.enabled = False
            return
        self.enabled = True
        for tenant in tenants:
            key = (tenant.tenant_id, tenant.file_sha256, seed, n_samples, contamination)
            if key not in _FITTED:  # same pack + seed -> same model, fit once per process
                _FITTED[key] = self._fit(tenant, n_samples, contamination)
            self.models[tenant.tenant_id] = _FITTED[key]

    @staticmethod
    def reference_price(tenant: TenantPack) -> int:
        return int(median(p.price_millimes for p in tenant.catalog))

    def _fit(self, tenant: TenantPack, n: int, contamination: float):
        import numpy as np
        from sklearn.ensemble import IsolationForest

        rng = np.random.default_rng(self.seed)
        ref = self.reference_price(tenant)
        due_now = [tenant.price_for(p.product_id, plan)[1][0] for p in tenant.catalog for plan in p.plans]
        X = np.column_stack([
            rng.choice(due_now, n) / ref * rng.normal(1.0, 0.02, n),          # people buy catalog items
            rng.choice([1, 2, 3], n, p=[0.85, 0.12, 0.03]),                   # most pay on the first try
            rng.choice([1, 2], n, p=[0.94, 0.06]),
            rng.choice([0, 1], n, p=[0.94, 0.06]),
            rng.choice([0, 1], n, p=[0.97, 0.03]),
            np.clip(rng.poisson(4, n) + 1, 1, 20),                            # a short chat before paying
            np.clip(rng.lognormal(1.2, 0.8, n), 0.2, 60),                     # minutes between opening and paying
        ])
        model = IsolationForest(n_estimators=150, contamination=contamination, random_state=self.seed).fit(X)
        return model, X.mean(axis=0), X.std(axis=0) + 1e-6

    def score(self, tenant: TenantPack, features: dict[str, float]) -> AnomalyResult | None:
        if not self.enabled or tenant.tenant_id not in self.models:
            return None
        import numpy as np

        model, mean, std = self.models[tenant.tenant_id]
        x = np.array([[features[f] for f in FEATURES]], dtype=float)
        s = float(model.decision_function(x)[0])
        z = (x[0] - mean) / std
        unusual = [f"{LABELS[f]} {round(features[f], 2):g}" for f, zi in sorted(zip(FEATURES, z), key=lambda t: -abs(t[1]))
                   if abs(zi) > 2][:3]
        return AnomalyResult(anomaly=s < 0, score=s, features=features, unusual=unusual)
