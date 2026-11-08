import time

import pytest

from thiqa.bouab.authz import AuthzError, verify_authorization
from thiqa.bouab.policy import Policy, sign_bytes, sig_path_for
from thiqa.pay.engine import EngineRejected
from thiqa.schemas import ActionRequest, ApprovalStatus, Decision, EventType, JourneyState

from .conftest import config_dir, run


def offer_case(app, product="intro_workshop", plan="full", method="tok_ok"):
    return run(app.orch.prepare_offer_case("9antra", product, plan, method))


def req(case, **kw):
    base = dict(agent_id="sandouk", action="pay.create_intent", tenant_id=case.tenant_id, case_id=case.case_id,
                payment_id="pay_x", amount_millimes=case.offer.due_now_millimes, currency="TND",
                customer_confirmation=True, idempotency_key="idem_x")
    base.update(kw)
    return ActionRequest(**base)


def test_sahbi_cannot_call_the_payment_tool(app):
    case = offer_case(app)
    d = app.bouab.call_tool(req(case, agent_id="sahbi"))
    assert d.decision == Decision.BLOCK and d.reasons[0].code == "P01_TOOL_DENIED"


def test_three_denials_quarantine_the_agent_until_a_human_releases_it(app):
    case = offer_case(app)
    for i in range(3):
        app.bouab.call_tool(req(case, agent_id="sahbi", action="db.query", idempotency_key=f"k{i}"))
    d = app.bouab.call_tool(ActionRequest(agent_id="sahbi", action="catalog.read", tenant_id="9antra", case_id=case.case_id))
    assert d.reasons[0].code == "K01_AGENT_QUARANTINED"
    assert app.bouab.release_agent("sahbi", case.case_id, "mouna", "9antra") == 1
    d = app.bouab.call_tool(ActionRequest(agent_id="sahbi", action="catalog.read", tenant_id="9antra", case_id=case.case_id))
    assert d.decision == Decision.ALLOW


def test_payment_without_confirmation_is_blocked_R01(app):
    case = offer_case(app)
    d = app.bouab.call_tool(req(case))
    assert d.decision == Decision.BLOCK and "R01_CONFIRMATION_MISSING" in [r.code for r in d.reasons]
    assert d.approval_id is None  # a BLOCK never becomes an approval


def confirmed(app, product="intro_workshop", plan="full"):
    case = offer_case(app, product, plan)
    case.confirmed_offer_hash = case.offer.offer_hash
    case.payment_attempt = 1
    app.repo.save_case(case)
    return case


@pytest.mark.parametrize("change,code", [
    ({"amount_millimes": 0}, "R03_AMOUNT_NOT_POSITIVE"),
    ({"currency": "EUR"}, "R05_CURRENCY"),
    ({"amount_millimes": 1000}, "R06_AMOUNT_MISMATCH"),
])
def test_hard_rules_block(app, change, code):
    case = confirmed(app)
    d = app.bouab.call_tool(req(case, **change))
    assert d.decision == Decision.BLOCK and code in [r.code for r in d.reasons]


def test_float_amounts_are_rejected_by_the_contract():
    with pytest.raises(Exception):
        ActionRequest(agent_id="sandouk", action="pay.create_intent", tenant_id="t", case_id="c", amount_millimes=25.0)


def test_above_threshold_requires_approval_R02(app):
    case = confirmed(app, "ai_bootcamp", "full")
    d = app.bouab.call_tool(req(case))
    assert d.decision == Decision.REQUIRE_APPROVAL and d.approval_id and d.authorization is None


def test_engine_rejects_missing_forged_wrong_and_replayed_tokens(app):
    case = confirmed(app)
    kw = dict(payment_id="pay_x", tenant_id="9antra", case_id=case.case_id, amount_millimes=25_000, currency="TND",
              method="tok_ok", idempotency_key="idem_x")
    with pytest.raises(EngineRejected) as e:
        app.engine.create_intent(authorization=None, **kw)
    assert e.value.code == "AUTHZ_MISSING"
    with pytest.raises(EngineRejected) as e:
        app.engine.create_intent(authorization="eyJ2IjoxfQ.Zm9yZ2Vk", **kw)
    assert e.value.code == "AUTHZ_BAD_SIGNATURE"
    d = app.bouab.call_tool(req(case))
    assert d.decision == Decision.ALLOW and d.authorization
    with pytest.raises(EngineRejected) as e:
        app.engine.create_intent(authorization=d.authorization, **{**kw, "amount_millimes": 999_000})
    assert e.value.code == "AUTHZ_MISMATCH_AMT"
    p = app.engine.create_intent(authorization=d.authorization, **kw)
    assert p.status.value == "succeeded"
    with pytest.raises(EngineRejected) as e:
        app.engine.create_intent(authorization=d.authorization, **{**kw, "idempotency_key": "other"})
    assert e.value.code == "AUTHZ_REPLAYED"


def test_expired_token():
    from thiqa.bouab.authz import Authorizer
    tok = Authorizer(b"k", ttl_s=1).issue(payment_id="p", tenant_id="t", amount_millimes=1, currency="TND",
                                          request_hash="h", now=time.time() - 10)
    with pytest.raises(AuthzError) as e:
        verify_authorization(tok, b"k", payment_id="p", tenant_id="t", amount_millimes=1, currency="TND")
    assert e.value.code == "AUTHZ_EXPIRED"


def test_tenant_isolation(app):
    case = confirmed(app)
    d = app.bouab.call_tool(req(case, tenant_id="nakhla"))
    assert d.reasons[0].code == "I02_TENANT_ISOLATION"


def approval_for(app, product="ai_bootcamp"):
    case = confirmed(app, product, "full")
    d = app.bouab.call_tool(req(case))
    return case, d


def test_approval_rules(app):
    case, d = approval_for(app)
    t = app.tenants.get("9antra")
    assert app.bouab.approvals.vote(d.approval_id, "stranger", t).refusal == "not_an_approver"
    assert app.bouab.approvals.vote(d.approval_id, "agent:sandouk", t).refusal == "not_an_approver"
    assert app.bouab.approvals.vote(d.approval_id, "mouna", t).ok
    # changed amount after approval -> hash mismatch, then the real request works once, then replay
    bad = app.bouab.call_tool(req(case, amount_millimes=2_500_000, approval_id=d.approval_id))
    assert bad.decision == Decision.BLOCK and bad.reasons[0].code == "A_HASH_MISMATCH"
    good = app.bouab.call_tool(req(case, approval_id=d.approval_id))
    assert good.decision == Decision.ALLOW and good.authorization
    again = app.bouab.call_tool(req(case, approval_id=d.approval_id))
    assert again.reasons[0].code == "A_REPLAY"


def test_self_approval_is_refused(app):
    r = run(app.orch.manual_order("9antra", "ai_bootcamp", "full", requested_by="youssef"))
    case = app.repo.get_case(r.case_id)
    res, _ = run(app.orch.vote(case.pending_approval_id, "youssef"))
    assert not res.ok and res.refusal == "self_approval"
    res, out = run(app.orch.vote(case.pending_approval_id, "mouna"))
    assert res.ok and out.state == JourneyState.PAID


def test_two_approvers_above_twice_the_threshold(app):
    t = app.tenants.get("9antra")
    t.thresholds.approval_threshold_millimes = 700_000   # 1,500 TND > 2 x 700 TND
    case, d = approval_for(app)
    a = app.repo.get_approval(d.approval_id)
    assert a.required_approvals == 2
    assert app.bouab.approvals.vote(d.approval_id, "mouna", t).approval.status == ApprovalStatus.PENDING
    assert app.bouab.approvals.vote(d.approval_id, "mouna", t).refusal == "duplicate_vote"
    assert app.bouab.approvals.vote(d.approval_id, "ops_lead", t).approval.status == ApprovalStatus.APPROVED


def test_unsigned_or_tampered_policy_fails_closed(env):
    cfg = config_dir(env)
    path = cfg / "policy.yaml"
    sig_path_for(path).write_text(sign_bytes(path.read_bytes(), b"key"))
    assert Policy.load(path, b"key").signature == "valid"
    path.write_text(path.read_text().replace("sahbi:            # Voice Sales (LLM)", "sahbi:\n    - pay.create_intent\n  sahbi_old:"))
    p = Policy.load(path, b"key")
    assert p.signature == "invalid" and p.fail_closed and not p.allowed("sandouk", "pay.create_intent")


def test_forbidden_grants_are_dropped_even_without_signature(env):
    path = config_dir(env) / "policy.yaml"
    text = path.read_text().replace("    - offer.propose\n", "    - offer.propose\n    - pay.create_intent\n    - approval.grant\n", 1)
    path.write_text(text)
    p = Policy.load(path, None)
    assert not p.allowed("sahbi", "pay.create_intent") and not p.allowed("sahbi", "approval.grant")
    assert len(p.problems) == 2


def test_insider_edit_at_runtime_is_detected_and_ignored(app):
    path = app.policy.path
    path.write_text(path.read_text().replace("    - offer.propose\n", "    - offer.propose\n    - pay.create_intent\n", 1))
    assert "policy.yaml" in app.bouab.check_protected_files()
    case = confirmed(app)
    d = app.bouab.call_tool(req(case, agent_id="sahbi"))
    assert d.reasons[0].code == "P01_TOOL_DENIED"
    types = [e.type for e in app.repo.list_events("*", 0, 500)]
    assert EventType.POLICY_TAMPERED in types


def test_isolation_forest_flags_card_testing_not_a_normal_sale(app):
    m, t = app.bouab.fraud_model, app.tenants.get("9antra")
    if not m.enabled:
        pytest.skip("scikit-learn not installed")
    normal = dict(amount_ratio=500 / 675, attempts_window=1, distinct_methods=1, night=0, injections=0, client_turns=3, minutes_open=1.0)
    testing = dict(amount_ratio=25 / 675, attempts_window=5, distinct_methods=2, night=0, injections=0, client_turns=0, minutes_open=0.3)
    assert not m.score(t, normal).anomaly
    r = m.score(t, testing)
    assert r.anomaly and "attempts 5" in r.detail()
    assert m.score(t, testing).score == r.score  # fixed seed: same input, same score


def test_ml_signal_shows_up_in_card_testing_decisions(app):
    if not app.bouab.fraud_model.enabled:
        pytest.skip("scikit-learn not installed")
    case = offer_case(app)
    for tok in ["tok_insufficient", "tok_fraud", "tok_insufficient", "tok_insufficient", "tok_fraud"]:
        c = app.repo.get_case(case.case_id)
        if c.state == JourneyState.BLOCKED:
            break
        run(app.orch.confirm(case.case_id, c.offer.offer_hash, tok))
    decisions = [e.payload for e in app.repo.list_events("9antra", case_id=case.case_id, limit=500)
                 if e.type == EventType.BOUAB_DECISION]
    assert any(s["code"] == "isolation_forest" for d in decisions for s in d.get("signals", []))


def test_ml_signal_is_optional(app, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_sklearn(name, *a, **k):
        if name.startswith("sklearn"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_sklearn)
    from thiqa.bouab.anomaly import FraudModel
    assert FraudModel(list(app.tenants.packs.values())).enabled is False
