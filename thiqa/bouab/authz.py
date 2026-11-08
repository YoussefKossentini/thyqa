"""Signed payment authorizations (HMAC-SHA256).

Bouab issues one per ALLOW; Sandouk Pay verifies it itself before moving
(simulated) money. No token, wrong amount, wrong payment, expired or replayed
token: rejected. Production path: Ed25519 so the engine only holds a public key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from ..schemas import canonical_json


class AuthzError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Authorizer:
    def __init__(self, secret: bytes, ttl_s: int = 120):
        self._secret = secret
        self.ttl_s = ttl_s

    def issue(self, *, payment_id: str, tenant_id: str, amount_millimes: int, currency: str,
              request_hash: str, now: float | None = None) -> str:
        now = time.time() if now is None else now
        claims = {"v": 1, "pid": payment_id, "tid": tenant_id, "amt": amount_millimes, "cur": currency,
                  "rh": request_hash, "exp": int(now) + self.ttl_s, "jti": uuid.uuid4().hex}
        body = _b64e(canonical_json(claims).encode())
        sig = _b64e(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"


def verify_authorization(token: str | None, secret: bytes, *, payment_id: str, tenant_id: str,
                         amount_millimes: int, currency: str, now: float | None = None) -> dict[str, Any]:
    if not token:
        raise AuthzError("AUTHZ_MISSING", "no signed authorization from Fouchika")
    try:
        body, sig = token.split(".")
        expected = hmac.new(secret, body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            raise AuthzError("AUTHZ_BAD_SIGNATURE", "signature does not match")
        claims = json.loads(_b64d(body))
    except AuthzError:
        raise
    except Exception as exc:
        raise AuthzError("AUTHZ_MALFORMED", "token is not a Fouchika authorization") from exc
    now = time.time() if now is None else now
    if claims.get("exp", 0) < now:
        raise AuthzError("AUTHZ_EXPIRED", "authorization expired")
    checks = {"pid": payment_id, "tid": tenant_id, "amt": amount_millimes, "cur": currency}
    for key, value in checks.items():
        if claims.get(key) != value:
            raise AuthzError(f"AUTHZ_MISMATCH_{key.upper()}", f"authorization was issued for another {key}")
    return claims
