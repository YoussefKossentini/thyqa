import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from thiqa import api as api_module, strategy
from thiqa.schemas import Objection, ObjectionStrategy
from thiqa.simulator import compare_runs, run_batch

from .conftest import run


def test_run1_vs_run2_same_seed_improves(app):
    r1 = run(run_batch(app, "9antra", 40, 7))
    prop = run(strategy.propose(app, "9antra", r1["run_id"]))
    assert prop["check"]["ok"]
    assert prop["draft"]["lead_with_monthly_price"] is True
    ok, _, _ = strategy.activate(app, "9antra", prop["draft"]["version"], "mouna")
    assert ok
    r2 = run(run_batch(app, "9antra", 40, 7))
    c = compare_runs(app, r1["run_id"], r2["run_id"])
    assert c["same_seed"] and c["delta"]["conversion_points"] > 0
    assert app.si_hsab.snapshot("9antra").interactions == 0  # simulated runs never touch live KPIs


def test_same_seed_same_result(app):
    a = run(run_batch(app, "9antra", 25, 3))
    b = run(run_batch(app, "9antra", 25, 3))
    assert a["summary"]["conversions"] == b["summary"]["conversions"] and a["outcomes"] == b["outcomes"]


def test_script_guard_refuses_locked_changes(app):
    current = app.orch.active_script("9antra")
    bad = current.model_copy(update={"version": 2, "status": "draft", "disclosure_line": False, "max_discount_percent": 50})
    reasons, _ = app.bouab.check_script(bad, current, 2)
    assert {"S03_DISCLOSURE", "S04_DISCOUNT_CAP"} <= {r.code for r in reasons}


def test_activation_needs_a_human_and_a_checked_draft(app):
    current = app.orch.active_script("9antra")
    draft = current.model_copy(update={"version": 2, "status": "draft",
                                       "objection_strategies": {**current.objection_strategies, Objection.PRICE: ObjectionStrategy.INSTALLMENTS_FIRST}})
    app.repo.save_script(draft)
    assert not strategy.activate(app, "9antra", 2, "mouna")[0]          # not checked yet
    draft.status = "checked"
    app.repo.save_script(draft)
    assert not strategy.activate(app, "9antra", 2, "le_renard")[0]      # an agent is not a human approver
    assert strategy.activate(app, "9antra", 2, "mouna")[0]


def client_for(app):
    api_module.STATE["app"] = app
    return TestClient(api_module.app)


def test_api_public_door_and_pin(app):
    with client_for(app) as c:
        case = c.post("/api/v1/cases", json={"channel": "text"}).json()
        r = c.post("/api/v1/interaction/turn", json={"case_id": case["case_id"], "text": "nheb nchri el genai weekend"}).json()
        assert r["state"] == "offer_proposed"
        r = c.post("/api/v1/interaction/confirm", json={"case_id": case["case_id"], "offer_hash": r["offer"]["offer_hash"],
                                                         "payment_method": "tok_ok"}).json()
        assert r["state"] == "paid" and r["payment"]["simulated"] is True
        assert c.post("/api/v1/demo/compromised-tool-call", json={}).status_code == 401
        d = c.post("/api/v1/demo/compromised-tool-call", json={}, headers={"X-Ops-Pin": "2468"}).json()
        assert d["decision"]["reasons"][0]["code"] == "P01_TOOL_DENIED"
        assert c.get("/api/v1/kpis").json()["conversions"] == 1
        assert c.post("/api/v1/audit/verify").json()["ok"]


def test_api_rejects_oversized_and_unsigned_internal_calls(app):
    with client_for(app) as c:
        assert c.post("/api/v1/interaction/turn", content=b"x" * 5000,
                      headers={"content-type": "application/json"}).status_code == 413
        assert c.post("/internal/siem/alerts", json={"rule_id": "100001"}).status_code == 401
        body = json.dumps({"alert_id": "a1", "rule_id": "100006", "level": 14, "description": "FIM policy.yaml"}).encode()
        ts = str(int(time.time()))
        sig = "sha256=" + hmac.new(b"test-internal-secret", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        r = c.post("/internal/siem/alerts", content=body, headers={"x-thiqa-timestamp": ts, "x-thiqa-signature": sig,
                                                                    "content-type": "application/json"})
        assert r.status_code == 200
        assert any(a["source"] == "wazuh" for a in app.repo.list_alerts("9antra"))


def test_websocket_streams_events(app):
    with client_for(app) as c:
        with c.websocket_connect("/ws/events?tenant_id=9antra") as ws:
            c.post("/api/v1/cases", json={"channel": "text"})
            types = set()
            for _ in range(10):
                types.add(ws.receive_json()["type"])
                if "turn.sahbi" in types:
                    break
            assert {"case.opened", "turn.sahbi"} <= types


def test_quarantine_request_from_wazuh_is_decided_by_bouab(app):
    with client_for(app) as c:
        def signed(payload):
            body = json.dumps(payload).encode()
            ts = str(int(time.time()))
            sig = "sha256=" + hmac.new(b"test-internal-secret", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
            return c.post("/internal/bouab/quarantine-request", content=body,
                          headers={"x-thiqa-timestamp": ts, "x-thiqa-signature": sig, "content-type": "application/json"}).json()
        assert signed({"agent_id": "bouab", "rule_id": "100002"})["accepted"] is False
        assert signed({"agent_id": "sahbi", "rule_id": "100001"})["accepted"] is False
        assert signed({"agent_id": "sahbi", "rule_id": "100002", "alert_id": "x"})["accepted"] is True


def test_voice_route_takes_a_short_wav_but_other_public_routes_stay_capped(app):
    big_wav = "QUJD" * 30000  # about 120 kB of base64, far over the 4 kB cap of the other public routes
    with client_for(app) as c:
        assert c.post("/api/v1/voice/transcribe", json={"audio_b64": big_wav, "mime": "audio/wav"}).status_code == 503  # past the size gate, no Gemini key in tests
        assert c.post("/api/v1/interaction/turn", json={"case_id": "x", "text": "a" * 5000}).status_code == 413


def test_llm_test_route_needs_the_pin_and_reports_providers_without_keys(app):
    with client_for(app) as c:
        assert c.post("/api/v1/llm/test").status_code == 401
        r = c.post("/api/v1/llm/test", headers={"X-Ops-Pin": app.settings.ops_pin})
        assert r.status_code == 200 and r.json() == {"providers": [], "voice": False}  # no keys in tests
