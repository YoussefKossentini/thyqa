import { useState } from "react";
import { api, getPin, setPin } from "../lib/api.js";
import { useOps } from "../lib/useOps.js";
import { dt, reasonsText } from "../lib/format.js";
import { Button, Empty, SectionTitle } from "./ui.jsx";

export default function Approvals() {
  const { approvals, tenants, tenant, refresh } = useOps();
  const approvers = tenants.find((t) => t.tenant_id === tenant)?.approvers || ["mouna", "youssef", "ops_lead"];
  const [approver, setApprover] = useState(approvers[0]);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(null);
  const [pin, setPinState] = useState(getPin());

  async function act(id, action) {
    if (!pin) { setMsg({ ok: false, text: "Saisis d'abord le code PIN ops (champ ci-dessus)." }); return; }
    setBusy(id + action);
    setMsg(null);
    try {
      const r = await api(`/api/v1/approvals/${id}/${action}`, { body: { approver_id: approver }, pin: true });
      setMsg({ ok: true, text: action === "approve" ? (r.outcome ? `Validé par ${approver}, paiement ${r.outcome.state === "paid" ? "réussi" : r.outcome.state}.` : `Vote de ${approver} enregistré : ${r.message}.`) : `Refusé par ${approver}.` });
    } catch (e) {
      const why = { self_approval: "on ne valide pas sa propre demande", duplicate_vote: "il faut un deuxième validateur différent",
        not_an_approver: "cette personne n'est pas validatrice", replay: "validation déjà utilisée", expired: "validation expirée" }[e.detail?.refusal];
      setMsg({ ok: false, text: `Fouchika refuse : ${(why || e.message).replace(/\.$/, "")}.` });
    }
    setBusy(null);
    refresh();
  }

  return (
    <section>
      <SectionTitle aside={
        <label className="flex items-center gap-1.5 whitespace-nowrap">Je suis
          <select value={approver} onChange={(e) => setApprover(e.target.value)} className="rounded border border-line bg-surface px-1.5 py-0.5 text-xs text-ink">
            {approvers.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>}>
        Humains dans la boucle
      </SectionTitle>
      <label className="mb-3 flex items-center justify-between gap-2 text-xs text-ink-2">Code PIN ops
        <input type="password" inputMode="numeric" autoComplete="off" value={pin} placeholder="PIN"
          onChange={(e) => { setPinState(e.target.value); setPin(e.target.value); }}
          className="w-24 rounded border border-line bg-surface px-2 py-1 text-sm text-ink placeholder:text-muted" />
      </label>
      {approvals.length === 0 ? (
        <Empty>Rien à valider. Un paiement au-dessus du seuil arrive ici et sur Telegram.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {approvals.map((a) => (
            <li key={a.approval_id} className="rounded-xl border border-warn/60 bg-warn-wash/60 p-3">
              <p className="text-2xl font-semibold">{dt(a.amount_millimes)}</p>
              <p className="text-sm text-ink">{a.product_name}</p>
              <p className="mt-1 text-xs text-ink-2">{reasonsText(a.reasons)}. Risque {a.risk_score}. {a.required_approvals > 1 ? `Deux validateurs différents (${a.approvals.length}/2).` : "Une validation suffit."}</p>
              <p className="text-xs text-muted">Demandé par {a.requested_by.replace("agent:", "")}, client {a.customer_ref}</p>
              <div className="mt-2 flex gap-2">
                <Button tone="primary" disabled={!!busy} onClick={() => act(a.approval_id, "approve")}>Valider</Button>
                <Button tone="danger" disabled={!!busy} onClick={() => act(a.approval_id, "reject")}>Refuser</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {msg && <p className={`mt-2 text-sm ${msg.ok ? "text-good-ink" : "text-crit-ink"}`}>{msg.text}</p>}
    </section>
  );
}
