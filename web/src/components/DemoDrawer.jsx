import { useEffect, useState } from "react";
import { api, getPin, setPin } from "../lib/api.js";
import { useOps } from "../lib/useOps.js";
import { reasonText, reasonsText } from "../lib/format.js";
import { Button } from "./ui.jsx";

const GROUPS = [
  ["La Veto", [
    ["compromised-tool-call", "Sboui piraté appelle le paiement"],
    ["direct-engine-call", "Appel direct au moteur, sans jeton"],
    ["forged-token", "Appel avec un jeton forgé"],
  ]],
  ["Validation humaine", [
    ["amount-swap", "Réutiliser une validation avec un autre montant"],
    ["self-approval", "Valider sa propre commande"],
  ]],
  ["Paiements", [
    ["double-submit", "Double clic sur « confirmer »"],
    ["card-testing", "Six essais de carte d'affilée"],
  ]],
  ["Audit", [
    ["tamper-audit", "Falsifier une ligne du journal"],
  ]],
  ["Préparation", [
    ["fake-events", "Envoyer des événements factices"],
    ["reset", "Remettre la démo à zéro"],
  ]],
];

function sentence(name, r) {
  switch (name) {
    case "compromised-tool-call": return `Fouchika refuse : ${reasonsText(r.decision?.reasons)}.`;
    case "direct-engine-call":
    case "forged-token": return r.rejected ? `Janet Pay rejette l'appel : ${reasonText(r.reason)}.` : "L'appel est passé (inattendu).";
    case "amount-swap": return `Fouchika refuse : ${reasonsText(r.decision?.reasons)}. Empreinte validée ${r.approved_hash}, nouvelle ${r.new_hash}.`;
    case "self-approval": return r.refused ? `Refusé : on ne valide pas sa propre demande. ${r.next ? "Un autre validateur peut le faire." : ""}` : "Accepté (inattendu).";
    case "double-submit": return `Deux envois, ${r.payments_created} paiement créé.`;
    case "card-testing": {
      const last = r.steps?.[r.steps.length - 1];
      return `${r.steps?.length} essais. Dernier : ${last?.state === "blocked" ? "dossier bloqué par Fouchika" : last?.state}.`;
    }
    case "tamper-audit": return r.verify?.ok ? "Le journal est resté intact (aucune ligne à modifier)." : `Ligne ${r.tampered_seq} modifiée. La vérification casse à la ligne ${r.verify?.first_bad_seq}.`;
    case "fake-events": return "Événements factices envoyés dans le Majlis.";
    case "reset": return "Base de démo remise à zéro, nouvelle époque d'audit.";
    default: return "Fait.";
  }
}

export default function DemoDrawer({ open, onClose }) {
  const { tenants, tenant, setTenant, refresh, refreshStatus } = useOps();
  const [pin, setPinState] = useState(getPin());
  const [out, setOut] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function run(name) {
    setBusy(name);
    try {
      const r = await api(`/api/v1/demo/${name}`, { body: { tenant_id: tenant }, pin: true });
      setOut({ ok: true, text: sentence(name, r), raw: r });
    } catch (e) {
      setOut({ ok: false, text: e.message });
    }
    setBusy(null);
    refresh();
    refreshStatus();
  }
  async function verify() {
    const r = await api(`/api/v1/audit/verify?tenant_id=${tenant}`, { method: "POST" });
    setOut({ ok: r.ok, text: r.ok ? `Journal intact, ${r.checked} lignes vérifiées.` : `Journal cassé à la ligne ${r.first_bad_seq} : ${r.reason}.`, raw: r });
  }

  return (
    <div className={`fixed inset-0 z-40 ${open ? "" : "pointer-events-none"}`} aria-hidden={!open}>
      <div className={`absolute inset-0 bg-ink/20 transition-opacity ${open ? "opacity-100" : "opacity-0"}`} onClick={onClose} />
      <aside role="dialog" aria-label="Scénarios de démo"
        className={`absolute right-0 top-0 flex h-full w-[440px] max-w-full flex-col gap-4 overflow-y-auto border-l border-line bg-surface p-5 shadow-xl transition-transform ${open ? "translate-x-0" : "translate-x-full"}`}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Scénarios de démo</h2>
          <Button tone="quiet" onClick={onClose} aria-label="Fermer">Fermer</Button>
        </div>
        <label className="flex items-center gap-2 text-sm">Code PIN ops
          <input type="password" value={pin} onChange={(e) => { setPinState(e.target.value); setPin(e.target.value); }}
            className="w-24 rounded border border-line px-2 py-1" />
        </label>
        <label className="flex items-center gap-2 text-sm">Tenant
          <select value={tenant || ""} onChange={(e) => setTenant(e.target.value).catch((err) => setOut({ ok: false, text: err.message }))}
            className="rounded border border-line px-2 py-1">
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.display_name}</option>)}
          </select>
        </label>
        {GROUPS.map(([title, items]) => (
          <div key={title}>
            <h3 className="mb-1.5 text-sm font-semibold text-ink-2">{title}</h3>
            <div className="flex flex-col gap-1.5">
              {items.map(([name, label]) => (
                <Button key={name} tone={name === "reset" ? "danger" : "plain"} disabled={!!busy} onClick={() => run(name)} className="justify-start text-left">
                  {busy === name ? "…" : label}
                </Button>
              ))}
              {title === "Audit" && <Button onClick={verify} className="justify-start">Vérifier le journal</Button>}
            </div>
          </div>
        ))}
        {out && (
          <div className={`rounded-lg border p-3 text-sm ${out.ok ? "border-good/40 bg-good-wash text-good-ink" : "border-crit/40 bg-crit-wash text-crit-ink"}`}>
            <p>{out.text}</p>
            {out.raw && <details className="mt-1 text-xs text-ink-2"><summary className="cursor-pointer">Réponse brute</summary><pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap">{JSON.stringify(out.raw, null, 1)}</pre></details>}
          </div>
        )}
      </aside>
    </div>
  );
}
