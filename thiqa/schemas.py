"""Thiqa shared contracts (frozen v1).

Every module and every teammate codes against these types. What the types
enforce on purpose:

* Money is an integer number of millimes (1 TND = 1000 millimes). Floats are
  rejected everywhere money appears (StrictInt).
* Agents exchange typed fields only. FahemAnalysis has no free-text field, so
  nothing the client typed can travel from Fahem to Le Renard: indirect prompt
  injection has no channel.
* Only the orchestrator writes CaseFile.state, and only along TRANSITIONS.
* Bouab decides with deterministic code; ToolDecision is its only output.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
try:
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        def __str__(self) -> str:
            return str(self.value)

        def __format__(self, spec: str) -> str:
            return format(str(self.value), spec)
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from .names import DISPLAY

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def canonical_json(obj: Any) -> str:
    """Stable JSON used for every hash and signature."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class Contract(BaseModel):
    """Base for agent-to-agent payloads: unknown fields are an error."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Identities and enums
# --------------------------------------------------------------------------- #


class AgentId(StrEnum):
    SAHBI = "sahbi"            # Voice Sales (LLM)
    FAHEM = "fahem"            # Customer Intelligence (LLM -> strict JSON)
    SANDOUK = "sandouk"        # Payment (code)
    SI_HSAB = "si_hsab"        # Financial Analyst (SQL)
    LE_RENARD = "le_renard"    # Strategy (LLM over aggregated stats)
    BOUAB = "bouab"            # Security & Fraud (code + rules)
    SARRAK = "sarrak"          # Red team (public door only)
    ORCHESTRATOR = "orchestrator"


AGENT_PROFILES: dict[str, dict[str, str]] = {
    "sahbi": {"name": DISPLAY["sahbi"], "role": "Voice Sales", "built_with": "LLM", "color": "#22c55e"},
    "fahem": {"name": DISPLAY["fahem"], "role": "Customer Intelligence", "built_with": "LLM -> strict JSON", "color": "#38bdf8"},
    "sandouk": {"name": DISPLAY["sandouk"], "role": "Payment", "built_with": "Code", "color": "#f59e0b"},
    "si_hsab": {"name": DISPLAY["si_hsab"], "role": "Financial Analyst", "built_with": "SQL views", "color": "#a78bfa"},
    "le_renard": {"name": DISPLAY["le_renard"], "role": "Strategy", "built_with": "LLM over stats", "color": "#fb7185"},
    "bouab": {"name": DISPLAY["bouab"], "role": "Security & Fraud", "built_with": "Code + rules", "color": "#ef4444"},
    "sarrak": {"name": DISPLAY["sarrak"], "role": "Red Team", "built_with": "Script + corpus", "color": "#64748b"},
    "orchestrator": {"name": DISPLAY["orchestrator"], "role": "Journey state machine", "built_with": "Code", "color": "#94a3b8"},
}


class Tool(StrEnum):
    TRANSCRIPT_READ = "transcript.read"
    OFFER_READ = "offer.read"
    CATALOG_READ = "catalog.read"
    TURN_APPEND = "turn.append"
    OFFER_PROPOSE = "offer.propose"
    INTELLIGENCE_WRITE = "intelligence.write"
    PAY_CREATE_INTENT = "pay.create_intent"
    PAY_GET_STATUS = "pay.get_status"
    PAY_PROPOSE_RETRY = "pay.propose_retry"
    KPI_READ = "kpi.read"
    KPI_SNAPSHOT_WRITE = "kpi.snapshot.write"
    OBJECTION_STATS_READ = "objection_stats.read"
    SCRIPT_PROPOSE = "script.propose"
    RISK_WRITE = "risk.write"
    AUDIT_WRITE = "audit.write"
    APPROVAL_REQUEST = "approval.request"
    CASE_BLOCK = "case.block"
    AGENT_QUARANTINE = "agent.quarantine"
    ALERT_RAISE = "alert.raise"
    # Never grantable to an agent (enforced in code, see bouab/policy.py)
    SCRIPT_ACTIVATE = "script.activate"
    CATALOG_WRITE = "catalog.write"
    POLICY_WRITE = "policy.write"
    APPROVAL_GRANT = "approval.grant"
    DB_QUERY = "db.query"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AIMode(StrEnum):
    """Badge on every AI output."""

    LIVE = "LIVE"
    REPLAY = "REPLAY"
    MOCK = "MOCK"


class Channel(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    SIMULATOR = "simulator"
    HACK_US = "hack_us"


class JourneyState(StrEnum):
    NEW = "new"
    CONVERSING = "conversing"
    OFFER_PROPOSED = "offer_proposed"        # offer card on the table, waiting for explicit confirmation
    OFFER_ACCEPTED = "offer_accepted"        # client confirmed (deterministic), money path starts
    AWAITING_APPROVAL = "awaiting_approval"  # Bouab said REQUIRE_APPROVAL
    PAYMENT_PENDING = "payment_pending"      # intent created, result not final (timeout, bank transfer)
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"        # declined; Sandouk proposes a retry plan
    BLOCKED = "blocked"                      # Bouab blocked the case; only a human reopens it
    CLOSED_LOST = "closed_lost"


S = JourneyState
TRANSITIONS: dict[JourneyState, set[JourneyState]] = {
    S.NEW: {S.CONVERSING, S.BLOCKED, S.CLOSED_LOST},
    S.CONVERSING: {S.OFFER_PROPOSED, S.BLOCKED, S.CLOSED_LOST},
    S.OFFER_PROPOSED: {S.OFFER_PROPOSED, S.OFFER_ACCEPTED, S.CONVERSING, S.BLOCKED, S.CLOSED_LOST},
    S.OFFER_ACCEPTED: {S.AWAITING_APPROVAL, S.PAYMENT_PENDING, S.PAID, S.PAYMENT_FAILED, S.BLOCKED},
    S.AWAITING_APPROVAL: {S.PAYMENT_PENDING, S.PAID, S.PAYMENT_FAILED, S.BLOCKED, S.CONVERSING},
    S.PAYMENT_PENDING: {S.PAID, S.PAYMENT_FAILED, S.BLOCKED},
    S.PAYMENT_FAILED: {S.OFFER_ACCEPTED, S.OFFER_PROPOSED, S.CONVERSING, S.CLOSED_LOST, S.BLOCKED},
    S.PAID: set(),
    S.BLOCKED: set(),
    S.CLOSED_LOST: {S.CONVERSING},
}
TERMINAL_STATES = {S.PAID, S.BLOCKED, S.CLOSED_LOST}
del S


class Intent(StrEnum):
    GREETING = "greeting"
    INFO_REQUEST = "info_request"
    PRICE_QUESTION = "price_question"
    OBJECTION = "objection"
    INTEREST = "interest"
    PURCHASE_INTENT = "purchase_intent"
    CONFIRM = "confirm"
    DECLINE = "decline"
    OFF_TOPIC = "off_topic"


class Objection(StrEnum):
    PRICE = "price"
    TRUST = "trust"
    TIME = "time"
    RELEVANCE = "relevance"
    COMPREHENSION = "comprehension"
    PAYMENT_METHOD = "payment_method"


class Persona(StrEnum):
    STUDENT = "student"
    BROKE_STUDENT = "broke_student"
    RUSHED_PRO = "rushed_pro"
    PARENT = "parent"
    UNKNOWN = "unknown"


class Lang(StrEnum):
    DERJA = "derja"
    FR = "fr"
    EN = "en"
    AR = "ar"


# --------------------------------------------------------------------------- #
# Agent outputs (typed intents)
# --------------------------------------------------------------------------- #


class Radar(Contract):
    """Hesitation Radar, every axis 0..100."""

    price_sensitivity: int = Field(ge=0, le=100)
    trust: int = Field(ge=0, le=100)
    urgency: int = Field(ge=0, le=100)
    comprehension: int = Field(ge=0, le=100)
    intent: int = Field(ge=0, le=100)


class FahemAnalysis(Contract):
    """Fahem's output. No free text on purpose: enums and scores only."""

    intent: Intent
    sentiment: int = Field(ge=-100, le=100)
    objections: list[Objection] = Field(default_factory=list, max_length=6)
    satisfaction: Literal["positive", "neutral", "negative"]
    radar: Radar
    persona: Persona
    lang: Lang


class SahbiAction(StrEnum):
    NONE = "none"
    PROPOSE_OFFER = "propose_offer"
    CLOSE = "close"


class SahbiReply(Contract):
    """Sahbi's output. Prices are never computed here: code builds the Offer."""

    text: str = Field(min_length=1, max_length=480)
    action: SahbiAction = SahbiAction.NONE
    product_id: str | None = None
    plan_id: str | None = None
    discount_code: str | None = None


class Offer(Contract):
    """Built by code from the tenant catalog. The hash binds the confirmation."""

    offer_id: str
    tenant_id: str
    product_id: str
    product_name: str
    plan_id: str
    installments: int = Field(ge=1, le=12)
    discount_code: str | None = None
    discount_percent: int = Field(default=0, ge=0, le=100)
    total_millimes: StrictInt = Field(gt=0)
    due_now_millimes: StrictInt = Field(gt=0)
    schedule_millimes: list[StrictInt]
    currency: str
    offer_hash: str


# --------------------------------------------------------------------------- #
# Case File (one per interaction, single writer: the orchestrator)
# --------------------------------------------------------------------------- #


class Turn(Contract):
    turn_id: str
    role: Literal["client", "sahbi", "system"]
    text: str
    ts: datetime = Field(default_factory=utcnow)
    withheld: bool = False          # True: Bouab quarantined the client text, transcript keeps a placeholder
    mode: AIMode | None = None


class RiskSignal(Contract):
    code: Literal[
        "injection_attempt",
        "unusual_amount",
        "velocity",
        "method_mismatch",
        "failed_step_up",
        "time_anomaly",
        "processor_fraud_flag",
        "isolation_forest",
    ]
    weight: int
    detail: str                     # generated by code, never client text
    ts: datetime = Field(default_factory=utcnow)


class CaseFile(Contract):
    case_id: str
    tenant_id: str
    customer_ref: str               # synthetic id, never a real identity
    channel: Channel
    run_id: str | None = None       # set for simulated batch runs
    state: JourneyState = JourneyState.NEW
    script_version: int = 1
    turns: list[Turn] = Field(default_factory=list)
    intelligence: FahemAnalysis | None = None
    objections_seen: list[Objection] = Field(default_factory=list)
    objections_resolved: list[Objection] = Field(default_factory=list)
    product_interest: str | None = None     # product_id the client talks about (set by code)
    offer: Offer | None = None
    confirmed_offer_hash: str | None = None
    pending_approval_id: str | None = None
    payment_method: str = "tok_ok"  # sandbox test token chosen in the client app
    payment_attempt: int = 0
    payment_ids: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    lost_reason: Objection | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Bouab: action requests and decisions
# --------------------------------------------------------------------------- #


class ActionRequest(Contract):
    """Every tool call an agent makes goes through Bouab as one of these."""

    agent_id: str
    action: str                               # a Tool value; unknown names end as TOOL_DENIED
    tenant_id: str
    case_id: str
    payment_id: str | None = None
    amount_millimes: StrictInt | None = None  # integer millimes only
    currency: str | None = None
    customer_confirmation: StrictBool | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    approval_id: str | None = None            # set when resuming after a human approval
    params: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class Reason(Contract):
    code: str                       # e.g. R06_AMOUNT_MISMATCH, TOOL_DENIED
    rule_id: str | None = None      # R01..R07, K01 (kill switch), P01 (permissions)
    message: str                    # generated by code


class ToolDecision(Contract):
    decision_id: str
    decision: Decision
    agent_id: str
    action: str
    tenant_id: str
    case_id: str
    risk_score: int = 0
    signals: list[RiskSignal] = Field(default_factory=list)
    reasons: list[Reason] = Field(default_factory=list)
    request_hash: str | None = None
    approval_id: str | None = None
    authorization: str | None = None   # signed token; stripped before any event is published
    restrictions: list[str] = Field(default_factory=list)
    existing_payment_id: str | None = None
    ts: datetime = Field(default_factory=utcnow)

    def public(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"authorization"})


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class Approval(Contract):
    approval_id: str
    tenant_id: str
    case_id: str
    payment_id: str
    decision_id: str
    request_hash: str               # sha256(payment_id, amount, currency, customer, idempotency_key)
    amount_millimes: StrictInt
    currency: str
    customer_ref: str
    product_name: str
    requested_by: str
    required_approvals: int = Field(ge=1, le=2)
    approvals: list[str] = Field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING
    reasons: list[Reason] = Field(default_factory=list)
    risk_score: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    consumed_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Payments
# --------------------------------------------------------------------------- #


class SandboxToken(StrEnum):
    OK = "tok_ok"
    INSUFFICIENT = "tok_insufficient"
    TIMEOUT = "tok_timeout"
    FRAUD = "tok_fraud"
    BANK_TRANSFER = "bank_transfer_sim"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    DECLINED = "declined"


class PaymentIntent(Contract):
    payment_id: str
    tenant_id: str
    case_id: str
    run_id: str | None = None
    amount_millimes: StrictInt = Field(gt=0)
    currency: str
    method: str                     # a SandboxToken value, never card data
    status: PaymentStatus
    reason: str | None = None       # insufficient_funds, processor_timeout, suspected_fraud, awaiting_transfer, invalid_token
    idempotency_key: str
    simulated: Literal[True] = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RetryOption(StrEnum):
    RETRY_SAME = "retry_same"
    SWITCH_TO_INSTALLMENTS = "switch_to_installments"
    SWITCH_TO_BANK_TRANSFER = "switch_to_bank_transfer"
    WAIT_AND_REFRESH = "wait_and_refresh"
    NO_RETRY_ESCALATE = "no_retry_escalate"


class RetryPlan(Contract):
    payment_id: str
    reason: str
    options: list[RetryOption]


class LedgerLine(Contract):
    entry_id: str
    tenant_id: str
    payment_id: str | None
    account: Literal["sandbox_cash", "sales_revenue"]
    debit_millimes: StrictInt = 0
    credit_millimes: StrictInt = 0


# --------------------------------------------------------------------------- #
# Scripts and strategy (Le Renard proposes, Bouab checks, a human activates)
# --------------------------------------------------------------------------- #


class ObjectionStrategy(StrEnum):
    VALUE_FIRST = "value_first"              # explain value before talking price
    INSTALLMENTS_FIRST = "installments_first"
    SHOW_PROGRAM = "show_program"            # offer the full program + a call with a trainer
    FLEXIBLE_SCHEDULE = "flexible_schedule"
    SIMPLIFY = "simplify"                    # explain with one concrete example
    STUDENT_DISCOUNT = "student_discount"    # mention the catalog student code, if the tenant has one


class ScriptVersion(Contract):
    tenant_id: str
    version: int = Field(ge=1)
    status: Literal["draft", "checked", "active", "rejected", "retired"] = "draft"
    opening: Literal["warm_short", "value_hook", "question_first"] = "warm_short"
    pitch_focus: list[Literal["outcomes", "projects", "certificate", "schedule", "price"]] = Field(
        default_factory=lambda: ["outcomes", "projects"], max_length=3
    )
    objection_strategies: dict[Objection, ObjectionStrategy]
    lead_with_monthly_price: bool = False
    max_discount_percent: int = Field(default=0, ge=0, le=100)
    disclosure_line: bool = True             # immutable: the AI + sandbox disclosure stays on
    proposed_by: str = "human"
    based_on_run: str | None = None
    rationale_ref: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Evidence(Contract):
    metric: str
    value: float | int | str
    scope: str


class Recommendation(Contract):
    rec_id: str
    tenant_id: str
    title: str = Field(max_length=140)
    rationale: str = Field(max_length=480)
    evidence: list[Evidence]
    priority: Literal["high", "medium", "low"] = "medium"
    proposed_change: dict[str, Any] | None = None
    mode: AIMode = AIMode.MOCK


# --------------------------------------------------------------------------- #
# KPIs (Si Hsab)
# --------------------------------------------------------------------------- #


class ObjectionStat(Contract):
    objection: Objection
    count: int
    share: float                    # 0..1, not money


class RevenueLost(Contract):
    objection: Objection
    lost_cases: int
    revenue_lost_millimes: StrictInt
    formula: str


class KpiSnapshot(Contract):
    tenant_id: str
    scope: str                      # "live" or a run_id
    ts: datetime = Field(default_factory=utcnow)
    interactions: int = 0
    interested: int = 0
    offers_proposed: int = 0
    conversions: int = 0
    conversion_rate: float = 0.0
    payments: dict[str, int] = Field(default_factory=dict)  # succeeded / declined / pending / blocked / awaiting_approval
    revenue_collected_millimes: StrictInt = 0
    contract_value_millimes: StrictInt = 0
    top_objections: list[ObjectionStat] = Field(default_factory=list)
    revenue_lost_by_objection: list[RevenueLost] = Field(default_factory=list)
    satisfaction: dict[str, int] = Field(default_factory=dict)  # positive / neutral / negative / score_0_100
    security: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Events (one envelope for Majlis feed, audit, replay)
# --------------------------------------------------------------------------- #


class EventType(StrEnum):
    CASE_OPENED = "case.opened"
    STATE_CHANGED = "case.state_changed"
    TURN_CLIENT = "turn.client"
    TURN_SAHBI = "turn.sahbi"
    INPUT_FLAGGED = "guard.input_flagged"
    OUTPUT_REWRITTEN = "guard.output_rewritten"
    FAHEM_ANALYSIS = "fahem.analysis"
    OFFER_PROPOSED = "offer.proposed"
    OFFER_ACCEPTED = "offer.accepted"
    TOOL_DENIED = "bouab.tool_denied"
    BOUAB_DECISION = "bouab.decision"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_VOTE = "approval.vote"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_REFUSED = "approval.refused"     # self-approval, replay, hash mismatch, expired
    AUTHORIZATION_ISSUED = "bouab.authorization_issued"
    PAYMENT_CREATED = "payment.created"
    PAYMENT_UPDATED = "payment.updated"
    PAYMENT_ENGINE_REJECTED = "payment.engine_rejected"
    RETRY_PROPOSED = "payment.retry_proposed"
    LEDGER_POSTED = "ledger.posted"
    KPI_UPDATED = "kpi.updated"
    ALERT = "security.alert"
    AGENT_QUARANTINED = "agent.quarantined"
    AGENT_RELEASED = "agent.released"
    POLICY_TAMPERED = "policy.tampered"
    SCRIPT_PROPOSED = "script.proposed"
    SCRIPT_CHECKED = "script.checked"
    SCRIPT_ACTIVATED = "script.activated"
    RECOMMENDATIONS = "strategy.recommendations"
    AUDIT_VERIFIED = "audit.verified"
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    BENCHMARK_FINISHED = "redteam.benchmark"
    TENANT_SWITCHED = "tenant.switched"
    SIEM_ALERT = "siem.alert"
    SIEM_STATUS = "siem.status"


class EventEnvelope(Contract):
    event_id: str = Field(default_factory=lambda: new_id("ev"))
    seq: int | None = None          # filled when stored
    ts: datetime = Field(default_factory=utcnow)
    tenant_id: str
    case_id: str | None = None
    run_id: str | None = None
    correlation_id: str
    type: EventType
    source: str                     # agent id, "client", "human:<name>", "system", "wazuh"
    target: str | None = None       # for the arrows in the Majlis feed
    decision: Decision | None = None
    severity: Severity = Severity.INFO
    mode: AIMode | None = None      # LIVE / REPLAY / MOCK badge on AI outputs
    simulated: bool = True          # every payment is a SIMULATED one
    summary: str                    # one line for the feed, generated by code
    payload: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# API responses
# --------------------------------------------------------------------------- #


class TurnResult(Contract):
    case_id: str
    reply: str
    mode: AIMode
    state: JourneyState
    withheld: bool = False
    offer: Offer | None = None
    radar: Radar | None = None
    payment: PaymentIntent | None = None
    decision: Decision | None = None
    notice: str | None = None
