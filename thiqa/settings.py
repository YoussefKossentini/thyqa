"""Settings from environment / .env. Secrets come only from the environment."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import timedelta, timezone, tzinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    """Tiny .env reader (no dependency). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("'", '"'):
            value = value[1:].split(value[0], 1)[0]
        else:
            value = value.split(" #", 1)[0].strip()   # inline comment
        os.environ.setdefault(key.strip(), value)


def local_tz(name: str = "Africa/Tunis") -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # Windows without tzdata: Tunisia is UTC+1, no DST
        return timezone(timedelta(hours=1))


def _parse_approvers(raw: str) -> dict[int, str]:
    """TELEGRAM_APPROVERS="123456:youssef,987654:mouna" -> {123456: "youssef", ...}"""
    out: dict[int, str] = {}
    for item in filter(None, (x.strip() for x in raw.split(","))):
        uid, _, name = item.partition(":")
        if uid.strip().lstrip("-").isdigit() and name.strip():
            out[int(uid)] = name.strip()
    return out


@dataclass
class Settings:
    root: Path
    config_dir: Path
    data_dir: Path
    replay_dir: Path
    authz_secret: bytes
    policy_signing_key: bytes | None
    internal_api_secret: bytes | None
    audit_anchor_key: bytes
    ops_pin: str
    llm_mode: str = "auto"                 # auto | mock | replay
    record_replay: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_url: str | None = None
    ollama_model: str = "qwen2.5:3b"
    llm_timeout_s: float = 8.0
    telegram_bot_token: str | None = None
    telegram_approvers: dict[int, str] = field(default_factory=dict)
    timezone_name: str = "Africa/Tunis"
    watch_interval_s: float = 3.0
    time_anomaly_enabled: bool = True
    ephemeral: list[str] = field(default_factory=list)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "thiqa.db"

    @property
    def security_log(self) -> Path:
        return self.data_dir / "security.jsonl"

    @property
    def audit_anchor_dir(self) -> Path:
        return self.data_dir / "audit_anchor"

    @property
    def tenants_dir(self) -> Path:
        return self.config_dir / "tenants"

    @property
    def policy_path(self) -> Path:
        return self.config_dir / "policy.yaml"

    @property
    def tz(self) -> tzinfo:
        return local_tz(self.timezone_name)

    @classmethod
    def from_env(cls, root: Path | None = None, dotenv: bool = True, **overrides) -> "Settings":
        root = root or ROOT
        if dotenv:
            load_dotenv(root / ".env")
        env = os.environ
        ephemeral: list[str] = []

        def secret(name: str, required_for_demo: bool = True) -> bytes | None:
            value = env.get(name)
            if value:
                return value.encode("utf-8")
            if required_for_demo:
                ephemeral.append(name)
                return secrets.token_bytes(32)
            return None

        data_dir = Path(env.get("THIQA_DATA_DIR", root / "data"))
        values = dict(
            root=root,
            config_dir=Path(env.get("THIQA_CONFIG_DIR", root / "config")),
            data_dir=data_dir,
            replay_dir=Path(env.get("THIQA_REPLAY_DIR", root / "replay")),
            authz_secret=secret("AUTHZ_HMAC_SECRET"),
            policy_signing_key=secret("POLICY_SIGNING_KEY", required_for_demo=False),
            internal_api_secret=secret("INTERNAL_API_SECRET", required_for_demo=False),
            audit_anchor_key=secret("AUDIT_ANCHOR_KEY"),
            ops_pin=env.get("OPS_PIN", "2468"),
            llm_mode=env.get("THIQA_LLM_MODE", "auto").lower(),
            record_replay=env.get("THIQA_RECORD_REPLAY", "0") == "1",
            gemini_api_key=env.get("GEMINI_API_KEY") or None,
            gemini_model=env.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
            groq_api_key=env.get("GROQ_API_KEY") or None,
            groq_model=env.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            ollama_url=env.get("OLLAMA_URL") or None,
            ollama_model=env.get("OLLAMA_MODEL", "qwen2.5:3b"),
            llm_timeout_s=float(env.get("LLM_TIMEOUT_S", "8")),
            telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_approvers=_parse_approvers(env.get("TELEGRAM_APPROVERS", "")),
            timezone_name=env.get("THIQA_TZ", "Africa/Tunis"),
            watch_interval_s=float(env.get("THIQA_WATCH_INTERVAL_S", "3")),
            time_anomaly_enabled=env.get("THIQA_TIME_ANOMALY", "1") == "1",
        )
        values.update(overrides)
        s = cls(**values, ephemeral=ephemeral)
        if "OPS_PIN" not in env and "ops_pin" not in overrides:
            s.ephemeral.append("OPS_PIN (default 2468)")
        s.data_dir.mkdir(parents=True, exist_ok=True)
        s.audit_anchor_dir.mkdir(parents=True, exist_ok=True)
        s.replay_dir.mkdir(parents=True, exist_ok=True)
        return s
