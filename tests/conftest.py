import asyncio
import shutil
from pathlib import Path

import pytest

from thiqa.container import build
from thiqa.settings import ROOT, Settings

SECRET_VARS = ["POLICY_SIGNING_KEY", "INTERNAL_API_SECRET", "AUTHZ_HMAC_SECRET", "AUDIT_ANCHOR_KEY", "GEMINI_API_KEY",
               "GROQ_API_KEY", "OLLAMA_URL", "TELEGRAM_BOT_TOKEN", "OPS_PIN"]


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(tmp_path, monkeypatch):
    for var in SECRET_VARS:
        monkeypatch.delenv(var, raising=False)
    config = tmp_path / "config"
    shutil.copytree(ROOT / "config", config)
    monkeypatch.setenv("THIQA_CONFIG_DIR", str(config))
    monkeypatch.setenv("THIQA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("THIQA_REPLAY_DIR", str(tmp_path / "replay"))
    monkeypatch.setenv("THIQA_LLM_MODE", "mock")
    monkeypatch.setenv("THIQA_TIME_ANOMALY", "0")
    monkeypatch.setenv("OPS_PIN", "2468")
    monkeypatch.setenv("INTERNAL_API_SECRET", "test-internal-secret")
    return tmp_path


@pytest.fixture
def app(env):
    return build(Settings.from_env(dotenv=False))


@pytest.fixture
def make_app(env):
    def _make(**overrides):
        return build(Settings.from_env(dotenv=False, **overrides))
    return _make


def config_dir(env: Path) -> Path:
    return env / "config"
