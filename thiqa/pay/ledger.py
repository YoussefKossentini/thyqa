"""Double-entry ledger lines for simulated payments. Every entry balances."""
from __future__ import annotations

from ..db import Repo
from ..schemas import PaymentIntent, new_id, utcnow


class Ledger:
    def __init__(self, repo: Repo):
        self.repo = repo

    def post_payment(self, p: PaymentIntent) -> str:
        entry_id = new_id("je")
        ts = utcnow().isoformat()
        with self.repo.tx() as c:
            c.execute("INSERT INTO ledger_lines (entry_id, tenant_id, run_id, payment_id, account, debit_millimes, credit_millimes, ts) "
                      "VALUES (?,?,?,?,?,?,?,?)", (entry_id, p.tenant_id, p.run_id, p.payment_id, "sandbox_cash", p.amount_millimes, 0, ts))
            c.execute("INSERT INTO ledger_lines (entry_id, tenant_id, run_id, payment_id, account, debit_millimes, credit_millimes, ts) "
                      "VALUES (?,?,?,?,?,?,?,?)", (entry_id, p.tenant_id, p.run_id, p.payment_id, "sales_revenue", 0, p.amount_millimes, ts))
        return entry_id

    def check(self, tenant_id: str) -> dict:
        rows = self.repo.q("SELECT entry_id, SUM(debit_millimes) AS d, SUM(credit_millimes) AS c FROM ledger_lines "
                           "WHERE tenant_id=? GROUP BY entry_id", (tenant_id,))
        unbalanced = [r["entry_id"] for r in rows if r["d"] != r["c"]]
        totals = self.repo.q("SELECT account, SUM(debit_millimes) AS d, SUM(credit_millimes) AS c FROM ledger_lines "
                             "WHERE tenant_id=? GROUP BY account", (tenant_id,))
        return {"ok": not unbalanced, "entries": len(rows), "unbalanced": unbalanced,
                "accounts": {r["account"]: {"debit_millimes": r["d"], "credit_millimes": r["c"]} for r in totals}}
