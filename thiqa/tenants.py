"""Tenant packs: catalog, prices, plans, thresholds, approvers. One YAML per tenant."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from .money import apply_discount, split_installments
from .schemas import Offer, Persona, canonical_json, new_id, sha256_hex


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    label: str
    installments: int = Field(ge=1, le=12)


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    name: str
    price_millimes: StrictInt = Field(gt=0)
    plans: list[str]
    duration: str = ""
    schedule: str = ""
    highlights: list[str] = Field(default_factory=list)
    mentionable_amounts_millimes: list[StrictInt] = Field(default_factory=list)


class DiscountCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    percent: int = Field(ge=1, le=100)
    label: str
    applies_to: list[str]
    personas: list[Persona] = Field(default_factory=list)


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_threshold_millimes: StrictInt = Field(gt=0)
    two_approver_multiplier: int = Field(default=2, ge=1)
    risk_allow_below: int = 40
    risk_block_above: int = 70
    velocity_window_seconds: int = 300
    velocity_free_attempts: int = 2
    velocity_max_attempts: int = 5
    approval_ttl_seconds: int = 900
    time_anomaly_hours: list[int] = Field(default_factory=lambda: [1, 5])


class TenantPack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    display_name: str
    kind: str
    currency: str = "TND"
    default_product: str
    disclosure: dict[str, str]
    plans: list[Plan]
    catalog: list[Product]
    discount_codes: list[DiscountCode] = Field(default_factory=list)
    max_discount_percent: int = Field(default=0, ge=0, le=100)
    thresholds: Thresholds
    approvers: list[str]
    file_sha256: str = ""

    @model_validator(mode="after")
    def _check(self) -> "TenantPack":
        plan_ids = {p.plan_id for p in self.plans}
        product_ids = {p.product_id for p in self.catalog}
        for prod in self.catalog:
            missing = set(prod.plans) - plan_ids
            if missing:
                raise ValueError(f"{prod.product_id}: unknown plans {missing}")
        for dc in self.discount_codes:
            if dc.percent > self.max_discount_percent:
                raise ValueError(f"discount {dc.code} above max_discount_percent")
            if set(dc.applies_to) - product_ids:
                raise ValueError(f"discount {dc.code} applies to unknown products")
        if self.default_product not in product_ids:
            raise ValueError("default_product not in catalog")
        return self

    # -- lookups -------------------------------------------------------------
    def product(self, product_id: str) -> Product | None:
        return next((p for p in self.catalog if p.product_id == product_id), None)

    def plan(self, plan_id: str) -> Plan | None:
        return next((p for p in self.plans if p.plan_id == plan_id), None)

    def discount(self, code: str | None) -> DiscountCode | None:
        if not code:
            return None
        return next((d for d in self.discount_codes if d.code == code.upper()), None)

    def installment_plans(self, product_id: str) -> list[Plan]:
        prod = self.product(product_id)
        if not prod:
            return []
        return [p for p in (self.plan(pid) for pid in prod.plans) if p and p.installments > 1]

    # -- money, computed by code only -------------------------------------------
    def price_for(self, product_id: str, plan_id: str, discount_code: str | None = None) -> tuple[int, list[int], int]:
        """Return (total, schedule, discount_percent). Raises ValueError on anything off-catalog."""
        prod = self.product(product_id)
        if prod is None:
            raise ValueError(f"unknown product {product_id}")
        if plan_id not in prod.plans:
            raise ValueError(f"plan {plan_id} not offered for {product_id}")
        plan = self.plan(plan_id)
        if plan is None:
            raise ValueError(f"unknown plan {plan_id}")
        percent = 0
        if discount_code:
            dc = self.discount(discount_code)
            if dc is None or product_id not in dc.applies_to:
                raise ValueError(f"discount code {discount_code} not valid for {product_id}")
            percent = dc.percent
        total = apply_discount(prod.price_millimes, percent) if percent else prod.price_millimes
        return total, split_installments(total, plan.installments), percent

    def build_offer(self, product_id: str, plan_id: str, discount_code: str | None = None) -> Offer:
        total, schedule, percent = self.price_for(product_id, plan_id, discount_code)
        prod = self.product(product_id)
        plan = self.plan(plan_id)
        if prod is None or plan is None:
            raise ValueError("offer outside the catalog")
        core = {
            "tenant_id": self.tenant_id,
            "product_id": product_id,
            "plan_id": plan_id,
            "discount_code": discount_code.upper() if discount_code else None,
            "total_millimes": total,
            "due_now_millimes": schedule[0],
            "currency": self.currency,
        }
        return Offer(
            offer_id=new_id("off"),
            product_name=prod.name,
            installments=plan.installments,
            discount_percent=percent,
            schedule_millimes=schedule,
            offer_hash=sha256_hex(canonical_json(core)),
            **core,
        )

    # -- what the output guard accepts in a reply --------------------------------
    def allowed_amounts(self) -> set[int]:
        amounts: set[int] = set()
        for prod in self.catalog:
            amounts.update(prod.mentionable_amounts_millimes)
            codes: list[str | None] = [None] + [d.code for d in self.discount_codes if prod.product_id in d.applies_to]
            for code in codes:
                for plan_id in prod.plans:
                    total, schedule, _ = self.price_for(prod.product_id, plan_id, code)
                    amounts.add(total)
                    amounts.update(schedule)
                if code:  # the saving itself may be quoted ("150 DT de remise")
                    amounts.add(prod.price_millimes - self.price_for(prod.product_id, prod.plans[0], code)[0])
        amounts.add(self.thresholds.approval_threshold_millimes)
        return amounts

    def allowed_discount_percents(self) -> set[int]:
        return {d.percent for d in self.discount_codes}

    def catalog_for_prompt(self) -> list[dict]:
        out = []
        for prod in self.catalog:
            plans = []
            for pid in prod.plans:
                total, schedule, _ = self.price_for(prod.product_id, pid)
                plans.append({"plan_id": pid, "installments": len(schedule), "due_now_millimes": schedule[0], "total_millimes": total})
            out.append(
                {
                    "product_id": prod.product_id,
                    "name": prod.name,
                    "price_millimes": prod.price_millimes,
                    "plans": plans,
                    "duration": prod.duration,
                    "schedule": prod.schedule,
                    "highlights": prod.highlights,
                }
            )
        return out


class TenantRegistry:
    def __init__(self, tenants_dir: Path):
        self.dir = tenants_dir
        self.packs: dict[str, TenantPack] = {}
        self.loaded_files: dict[Path, str] = {}
        for path in sorted(tenants_dir.glob("*.yaml")):
            raw = path.read_bytes()
            data = yaml.safe_load(raw)
            pack = TenantPack(**data, file_sha256=sha256_hex(raw))
            self.packs[pack.tenant_id] = pack
            self.loaded_files[path] = pack.file_sha256
        if not self.packs:
            raise RuntimeError(f"no tenant pack in {tenants_dir}")
        self.active_tenant_id = "9antra" if "9antra" in self.packs else next(iter(self.packs))

    def get(self, tenant_id: str) -> TenantPack:
        try:
            return self.packs[tenant_id]
        except KeyError as exc:
            raise KeyError(f"unknown tenant {tenant_id}") from exc

    def has(self, tenant_id: str) -> bool:
        return tenant_id in self.packs

    @property
    def active(self) -> TenantPack:
        return self.packs[self.active_tenant_id]

    def files(self) -> dict[Path, str]:
        """Loaded file -> sha256 at load time, for the tamper watcher."""
        return dict(self.loaded_files)
