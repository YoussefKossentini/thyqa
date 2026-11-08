"""Wires every component from Settings. Tests build a fresh one per test."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from .agents.fahem import Fahem
from .agents.le_renard import LeRenard
from .agents.prompts import PROMPT_FRAGMENTS
from .agents.sahbi import Sahbi
from .agents.si_hsab import SiHsab
from .audit import AuditChain
from .bouab.anomaly import FraudModel
from .bouab.approvals import ApprovalManager
from .bouab.authz import Authorizer
from .bouab.core import Bouab
from .bouab.input_guard import InputGuard
from .bouab.killswitch import KillSwitch
from .bouab.output_guard import OutputGuard
from .bouab.policy import Policy
from .bus import EventBus
from .db import Repo
from .llm import LLMGateway
from .orchestrator import Orchestrator
from .pay.engine import SandoukPay
from .pay.ledger import Ledger
from .schemas import Decision, EventType, Severity
from .seclog import SecurityLog
from .settings import Settings
from .tenants import TenantRegistry


@dataclass
class Thiqa:
    settings: Settings
    repo: Repo
    audit: AuditChain
    seclog: SecurityLog
    bus: EventBus
    tenants: TenantRegistry
    policy: Policy
    bouab: Bouab
    ledger: Ledger
    engine: SandoukPay
    llm: LLMGateway
    sahbi: Sahbi
    fahem: Fahem
    si_hsab: SiHsab
    le_renard: LeRenard
    orch: Orchestrator
    canary: str
    siem: dict = field(default_factory=lambda: {"online": False, "last_seen": None})


def build(settings: Settings | None = None) -> Thiqa:
    s = settings or Settings.from_env()
    repo = Repo(s.db_path)
    audit = AuditChain(repo, s.audit_anchor_dir, s.audit_anchor_key)
    seclog = SecurityLog(s.security_log)
    bus = EventBus(repo, audit, seclog)
    tenants = TenantRegistry(s.tenants_dir)
    policy = Policy.load(s.policy_path, s.policy_signing_key)
    ks = policy.kill_switch
    killswitch = KillSwitch(repo, ks["denied_calls"], ks["window_seconds"], ks["burst_calls"], ks["burst_window_seconds"])
    canary = "THIQA-" + secrets.token_hex(4).upper()
    bouab = Bouab(repo=repo, bus=bus, tenants=tenants, policy=policy, authorizer=Authorizer(s.authz_secret),
                  approvals=ApprovalManager(repo), killswitch=killswitch, input_guard=InputGuard(),
                  output_guard=OutputGuard(canary, PROMPT_FRAGMENTS, max_sentences=3), settings=s,
                  fraud_model=FraudModel(list(tenants.packs.values())))
    ledger = Ledger(repo)
    engine = SandoukPay(repo, bus, ledger, s.authz_secret)
    llm = LLMGateway(s)
    sahbi, fahem, si_hsab, le_renard = Sahbi(llm, canary), Fahem(llm), SiHsab(repo, tenants), LeRenard(llm)
    orch = Orchestrator(repo=repo, bus=bus, tenants=tenants, bouab=bouab, engine=engine, sahbi=sahbi, fahem=fahem,
                        si_hsab=si_hsab, le_renard=le_renard, agent_timeout_s=s.llm_timeout_s + 4)
    for tenant_id in tenants.packs:
        orch.active_script(tenant_id)
    if policy.fail_closed or policy.problems:
        bus.emit(EventType.POLICY_TAMPERED, tenant_id="*", source="bouab", target="human",
                 decision=Decision.BLOCK, severity=Severity.CRITICAL if policy.fail_closed else Severity.HIGH,
                 summary=("Fouchika started in FAIL-CLOSED mode: policy signature " + policy.signature if policy.fail_closed
                          else "Fouchika dropped forbidden grants from policy.yaml: " + "; ".join(policy.problems)),
                 payload={"file": policy.path.name, "signature": policy.signature, "problems": policy.problems,
                          "reason": "POLICY_REJECTED_AT_STARTUP"})
    return Thiqa(settings=s, repo=repo, audit=audit, seclog=seclog, bus=bus, tenants=tenants, policy=policy,
                 bouab=bouab, ledger=ledger, engine=engine, llm=llm, sahbi=sahbi, fahem=fahem, si_hsab=si_hsab,
                 le_renard=le_renard, orch=orch, canary=canary)
