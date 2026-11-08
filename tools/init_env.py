"""Create .env with fresh random secrets (if missing) and sign config/policy.yaml.

    python tools/init_env.py
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from thiqa.bouab.policy import sig_path_for, sign_bytes  # noqa: E402
from thiqa.settings import load_dotenv  # noqa: E402
import os  # noqa: E402

GENERATED = ("AUTHZ_HMAC_SECRET", "AUDIT_ANCHOR_KEY", "POLICY_SIGNING_KEY", "INTERNAL_API_SECRET")


def main() -> None:
    env = ROOT / ".env"
    if not env.exists():
        lines = []
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip()
            if key in GENERATED and line.strip().endswith("="):
                line = f"{key}={secrets.token_urlsafe(32)}"
            lines.append(line)
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("created .env with random secrets (keep it out of git)")
    else:
        print(".env already exists, kept as is")
    load_dotenv(env)
    key = os.environ.get("POLICY_SIGNING_KEY")
    if not key:
        print("POLICY_SIGNING_KEY is empty in .env: policy stays unsigned (dev mode)")
        return
    policy = ROOT / "config" / "policy.yaml"
    sig_path_for(policy).write_text(sign_bytes(policy.read_bytes(), key.encode()), encoding="utf-8")
    print(f"signed {policy.name} -> {sig_path_for(policy).name}")


if __name__ == "__main__":
    main()
