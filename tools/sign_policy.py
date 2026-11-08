"""Re-sign config/policy.yaml after a legitimate, reviewed change. Then restart the server.

    python tools/sign_policy.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from thiqa.bouab.policy import Policy, sig_path_for, sign_bytes  # noqa: E402
from thiqa.settings import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
key = os.environ.get("POLICY_SIGNING_KEY")
if not key:
    sys.exit("POLICY_SIGNING_KEY missing (run tools/init_env.py first)")
path = ROOT / "config" / "policy.yaml"
sig_path_for(path).write_text(sign_bytes(path.read_bytes(), key.encode()), encoding="utf-8")
policy = Policy.load(path, key.encode())
print(f"signed: signature={policy.signature} fail_closed={policy.fail_closed}")
for problem in policy.problems:
    print("  note:", problem)
