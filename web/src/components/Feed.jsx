import { useState } from "react";
import { who } from "../lib/agents.js";
import { dt, hhmm, INTENT, OBJECTION, PERSONA, reasonText, reasonsText } from "../lib/format.js";
import { Avatar, DecisionMark, Empty } from "./ui.jsx";

const SIGNAL = { injection_attempt: "injection", unusual_amount: "montant élevé", velocity: "tentatives répétées",
  method_mismatch: "plusieurs moyens de paiement", failed_step_up: "vérification ratée", time_anomaly: "heure inhabituelle",
  processor_fraud_flag: "fraude signalée par la banque", isolation_forest: "Isolation Forest" };
const NOISE = new Set(["case.state_changed", "kpi.updated", "siem.status", "bouab.authorization_issued", "run.started"]);
const STATUS = { succeeded: "réussi", declined: "refusé", pending: "en attente" };
const RETRY = { retry_same: "réessayer", switch_to_installments: "passer en tranches", switch_to_bank_transfer: "virement",
  wait_and_refresh: "attendre la banque", no_retry_escalate: "pas de relance, l'équipe reprend" };

export function describe(ev) {
  const p = ev.payload || {};
  switch (ev.type) {
    case "case.opened": return { text: `Nouvelle conversation (${p.channel === "hack_us" ? "Hack Thiqa" : p.channel === "simulator" ? "simulée" : p.channel})` };
    case "turn.client": return { quote: p.text };
    case "turn.sahbi": return { text: p.text };
    case "guard.input_flagged": return { quote: p.text, struck: true, note: `Arrêté avant Sboui : ${reasonsText(p.reasons)}` };
    case "guard.output_rewritten": return { text: `Réponse de Sboui remplacée : ${reasonsText(p.reasons, 2)}`, note: p.original ? `Elle disait : « ${p.original} »` : null };
    case "fahem.analysis": {
      const obj = (p.objections || []).map((o) => OBJECTION[o]?.toLowerCase()).filter(Boolean);
      const what = p.intent === "objection" && obj.length ? `objection sur ${obj.join(" et ")}` : `${INTENT[p.intent] || p.intent}${obj.length ? `, objection sur ${obj.join(" et ")}` : ""}`;
      return { text: `${what}, persona ${PERSONA[p.persona] || p.persona}` };
    }
    case "offer.proposed":
      return { text: `Offre : ${p.product_name}, ${p.installments > 1 ? `${p.installments} tranches, ${dt(p.due_now_millimes)} aujourd'hui` : `${dt(p.total_millimes)} en une fois`}` };
    case "offer.accepted": return { text: `Le client confirme, moyen de test ${p.method}` };
    case "bouab.decision": {
      const amount = p.amount_millimes ? `${dt(p.amount_millimes)}, ` : "";
      const why = reasonsText(p.reasons, 3);
      return { text: `${amount}${why || "tous les contrôles passent"}`, note: `Risque ${p.risk_score ?? 0}${(p.signals || []).length ? ` : ${(p.signals || []).map((s) => `${SIGNAL[s.code] || s.code} +${s.weight}`).join(", ")}` : ""}` };
    }
    case "bouab.tool_denied": return { text: `${who(p.agent_id).name} a tenté « ${p.action} » : outil interdit` };
    case "approval.requested": return { text: `Validation humaine demandée : ${dt(p.amount_millimes)} pour ${p.product_name}` };
    case "approval.vote": return { text: `Valide via ${p.channel} (${(p.approvals || []).length}/${p.required})` };
    case "approval.granted": return { text: `Paiement validé par ${(p.approvers || []).join(", ")}` };
    case "approval.rejected": return { text: "Paiement refusé par l'équipe" };
    case "approval.refused": return { text: p.refusal === "self_approval" ? "Fouchika refuse : on ne valide pas sa propre demande" : `Fouchika refuse la validation : ${reasonText(`A_${(p.refusal || "").toUpperCase()}`)}` };
    case "payment.created":
    case "payment.updated":
      return { text: `Paiement simulé ${dt(p.amount_millimes)} (${p.method}) : ${STATUS[p.status] || p.status}${p.reason ? `, ${p.reason.replaceAll("_", " ")}` : ""}` };
    case "payment.engine_rejected": return { text: `Janet Pay rejette l'appel de ${who(p.agent_id).name} : ${reasonText(p.reason)}` };
    case "payment.retry_proposed": return { text: `Plan de relance : ${(p.options || []).map((o) => RETRY[o] || o).join(", ")}` };
    case "ledger.posted": return { text: `Écriture équilibrée : caisse sandbox au débit, ventes au crédit, ${dt(p.amount_millimes)}` };
    case "agent.quarantined": return { text: `${who(p.agent_id).name} en quarantaine : ${p.reason}` };
    case "policy.tampered": return { text: `${p.file} a changé sur le disque. Fouchika garde la politique signée chargée au démarrage.` };
    case "audit.verified": return { text: p.ok ? `Journal d'audit intact, ${p.checked} lignes vérifiées` : `Journal d'audit cassé à la ligne ${p.first_bad_seq} : ${p.reason}` };
    case "siem.alert": return { text: `Règle Wazuh ${p.rule_id}, niveau ${p.level} : ${p.summary}` };
    case "redteam.benchmark": return { text: `Béji Matrix : ${p.attacks_run} attaques, ${p.stopped} arrêtées, ${p.false_positives}/${p.benign_total} faux positifs` };
    case "run.finished": return { text: `Simulation terminée : conversion ${Math.round((p.summary?.conversion_rate || 0) * 100)} %, script v${p.script_version}` };
    default: return { text: ev.summary };
  }
}

function FeedItem({ ev }) {
  const src = who(ev.source);
  const tgt = ev.target ? who(ev.target) : null;
  const d = describe(ev);
  return (
    <li className="feed-enter grid grid-cols-[32px_1fr_auto] gap-3 border-b border-line/70 px-2 py-3 last:border-b-0">
      <Avatar agent={src} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
          <span className="font-semibold text-ink">{src.name}</span>
          {tgt && tgt.name !== src.name && <span>à {tgt.name}</span>}
          <span className="tabular">{hhmm(ev.ts)}</span>
          {ev.mode && <span className="rounded border border-line px-1 text-[0.75rem] text-ink-2">{ev.mode}</span>}
          {ev.payload?.fake && <span className="rounded border border-line px-1 text-[0.75rem]">factice</span>}
        </div>
        {d.quote !== undefined && (
          <p className={`mt-0.5 text-base [overflow-wrap:anywhere] ${d.struck ? "text-crit-ink line-through decoration-crit/60" : "text-ink"}`}>« {d.quote} »</p>
        )}
        {d.text && <p className="mt-0.5 text-base leading-snug text-ink [overflow-wrap:anywhere]">{d.text}</p>}
        {d.note && <p className="mt-0.5 text-xs text-ink-2 [overflow-wrap:anywhere]">{d.note}</p>}
      </div>
      <DecisionMark decision={ev.decision} />
    </li>
  );
}

export default function Feed({ events }) {
  const [quiet, setQuiet] = useState(true);
  const shown = events.filter((e) => !quiet || !NOISE.has(e.type)).slice(0, 140);
  return (
    <section className="card flex min-h-0 flex-1 flex-col p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Le Majlis</h2>
        <label className="flex items-center gap-2 text-xs text-ink-2">
          <input type="checkbox" checked={quiet} onChange={(e) => setQuiet(e.target.checked)} className="accent-[#7b8cff]" />
          Masquer les détails techniques
        </label>
      </div>
      {shown.length === 0 ? (
        <Empty>Personne ne parle encore. Ouvre l'app client et écris à Sboui, chaque échange entre agents s'affiche ici.</Empty>
      ) : (
        <ol className="scroll-quiet -mx-1 min-h-0 flex-1 overflow-y-auto">{shown.map((ev) => <FeedItem key={ev.event_id} ev={ev} />)}</ol>
      )}
    </section>
  );
}
