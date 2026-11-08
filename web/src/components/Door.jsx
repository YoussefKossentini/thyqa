import { useEffect, useMemo, useState } from "react";
import { DECISION, dt, reasonsText } from "../lib/format.js";
import { who } from "../lib/agents.js";

const CX = 100, CY = 128, R = 66;

function arcStuds(radius, from, to, step) {
  const out = [];
  for (let a = from; a <= to + 0.01; a += step) {
    const rad = (a * Math.PI) / 180;
    out.push([CX + radius * Math.cos(rad), CY + radius * Math.sin(rad)]);
  }
  return out;
}
function column(x, y0, y1, step) {
  const out = [];
  for (let y = y0; y <= y1; y += step) out.push([x, y]);
  return out;
}
function diamond(cx, cy, r) {
  return [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy], [cx, cy - r / 2], [cx + r / 2, cy], [cx, cy + r / 2], [cx - r / 2, cy], [cx, cy]];
}

/** Fouchika's Tunisian door: open = ALLOW, shut and barred = BLOCK, ajar with a key = REQUIRE_APPROVAL. */
export function DoorArt({ state }) {
  const [knock, setKnock] = useState(false);
  const left = useMemo(() => [
    ...arcStuds(R - 9, 180, 268, 11), ...column(43, 142, 300, 16), ...column(93, 80, 300, 16),
    ...diamond(68, 206, 20), ...column(68, 150, 168, 9), ...column(68, 246, 290, 11),
  ], []);
  const right = useMemo(() => [
    ...arcStuds(R - 9, 272, 360, 11), ...column(157, 142, 300, 16), ...column(107, 80, 300, 16),
    ...diamond(132, 206, 20), ...column(132, 150, 168, 9), ...column(132, 246, 290, 11),
  ], []);
  useEffect(() => {
    if (state !== "block") return undefined;
    setKnock(true);
    const t = setTimeout(() => setKnock(false), 420);
    return () => clearTimeout(t);
  }, [state]);

  return (
    <svg className={`door w-full ${knock ? "knock" : ""}`} data-state={state} viewBox="0 0 200 330" role="img"
      aria-label={state === "idle" ? "Porte de Fouchika, fermée" : DECISION[{ allow: "ALLOW", block: "BLOCK", approval: "REQUIRE_APPROVAL" }[state]]?.door}>
      <defs>
        <radialGradient id="glowAllow" cx="50%" cy="60%" r="65%"><stop offset="0" stopColor="#2fae6b" /><stop offset="1" stopColor="#0f3d27" /></radialGradient>
        <radialGradient id="glowApproval" cx="70%" cy="60%" r="65%"><stop offset="0" stopColor="#f2b544" /><stop offset="1" stopColor="#4a3410" /></radialGradient>
        <clipPath id="doorOpening"><path d="M34 312V128a66 66 0 0 1 132 0v184z" /></clipPath>
      </defs>
      <text x="100" y="34" textAnchor="middle" fontFamily="var(--font-kufi)" fontSize="22" fill="var(--color-door-deep)">بوّاب</text>
      <path d="M34 312V128a66 66 0 0 1 132 0v184z" fill="#141b45" />
      <path className="door-glow allow" d="M34 312V128a66 66 0 0 1 132 0v184z" fill="url(#glowAllow)" />
      <path className="door-glow approval" d="M34 312V128a66 66 0 0 1 132 0v184z" fill="url(#glowApproval)" />
      <g clipPath="url(#doorOpening)">
      <g className="door-leaf left">
        <path d="M34 312V128a66 66 0 0 1 66-66v250z" fill="#3041a2" stroke="#1b2766" strokeWidth="1.5" />
        {left.map(([x, y], i) => <circle key={i} className="door-stud" cx={x} cy={y} r="2.3" fill="#23262e" />)}
        <circle cx="90" cy="206" r="5.5" fill="none" stroke="#23262e" strokeWidth="2" />
      </g>
      <g className="door-leaf right">
        <path d="M100 62a66 66 0 0 1 66 66v184H100z" fill="#3041a2" stroke="#1b2766" strokeWidth="1.5" />
        {right.map(([x, y], i) => <circle key={i} className="door-stud" cx={x} cy={y} r="2.3" fill="#23262e" />)}
        <circle cx="110" cy="206" r="5.5" fill="none" stroke="#23262e" strokeWidth="2" />
      </g>
      </g>
      <g className="door-bar"><rect x="26" y="196" width="148" height="11" rx="3" fill="#23262e" /><rect x="94" y="192" width="12" height="19" rx="2" fill="#d03b3b" /></g>
      <g className="door-key" transform="translate(150 200)">
        <circle cx="0" cy="0" r="7" fill="none" stroke="#7a4f00" strokeWidth="2.5" />
        <path d="M7 0h20M21 0v6M26 0v5" stroke="#7a4f00" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      </g>
      <path d="M28 318V126a72 72 0 0 1 144 0v192" fill="none" stroke="#1b2766" strokeWidth="5" />
      <path d="M18 318h164" stroke="#c9d3e3" strokeWidth="3" />
    </svg>
  );
}

const STATE_OF = { ALLOW: "allow", BLOCK: "block", REQUIRE_APPROVAL: "approval" };

export function doorSentence(ev) {
  if (!ev) return { title: "Fouchika garde la porte", body: "Chaque action d'un agent passe par lui avant d'arriver à l'argent ou au client." };
  const p = ev.payload || {};
  const d = DECISION[ev.decision] || DECISION.BLOCK;
  switch (ev.type) {
    case "guard.input_flagged":
      return { title: d.door, body: `Message arrêté avant Sboui : ${reasonsText(p.reasons)}.`, quote: p.text };
    case "guard.output_rewritten":
      return { title: d.door, body: `Réponse de Sboui remplacée avant le client : ${reasonsText(p.reasons, 2)}.`, quote: p.original };
    case "bouab.tool_denied":
      return { title: d.door, body: `${who(p.agent_id).name} a tenté « ${p.action} ». Outil interdit.` };
    case "payment.engine_rejected":
      return { title: d.door, body: `Janet Pay a refusé l'appel de ${who(p.agent_id).name} : ${reasonsText([p.reason])}.` };
    case "approval.refused":
      return { title: d.door, body: `Validation refusée : ${p.refusal === "self_approval" ? "on ne valide pas sa propre demande" : reasonsText([`A_${(p.refusal || "").toUpperCase()}`]) || p.refusal}.` };
    case "approval.granted":
      return { title: "Porte ouverte", body: `Validé par ${(p.approvers || []).join(", ")}.` };
    default: {
      const amount = p.amount_millimes ? `${dt(p.amount_millimes)} : ` : "";
      if (ev.decision === "ALLOW") return { title: d.door, body: `${amount}autorisé, risque ${p.risk_score ?? 0}. Autorisation signée, valable une fois.` };
      if (ev.decision === "REQUIRE_APPROVAL") return { title: d.door, body: `${amount}attend un humain (${reasonsText(p.reasons, 2)}).` };
      return { title: d.door, body: `${amount}${reasonsText(p.reasons, 2) || "bloqué"}.` };
    }
  }
}

export default function Door({ lastDecision, kpis }) {
  const state = lastDecision ? STATE_OF[lastDecision.decision] || "idle" : "idle";
  const s = doorSentence(lastDecision);
  const sec = kpis?.security || {};
  const pay = kpis?.payments || {};
  const blocked = (sec.injections_blocked || 0) + (sec.tool_denied || 0) + (sec.payments_blocked || 0) + (sec.engine_rejections || 0);
  const counters = [
    ["ALLOW", "Laissés passer", (pay.succeeded || 0) + (pay.pending || 0)],
    ["BLOCK", "Bloqués", blocked],
    ["REQUIRE_APPROVAL", "Chez un humain", sec.approvals_pending || 0],
  ];
  const tone = { allow: "text-good-ink", block: "text-crit-ink", approval: "text-warn-ink", idle: "text-ink" }[state];
  return (
    <section aria-live="polite" className="flex flex-col gap-4">
      <div className="mx-auto w-full max-w-[250px] drop-shadow-[0_18px_28px_rgba(18,62,120,.25)]"><DoorArt state={state} /></div>
      <div className="card p-4">
        <p className={`text-lg font-semibold ${tone}`}>{s.title}</p>
        <p className="mt-1 text-sm leading-relaxed text-ink-2">{s.body}</p>
        {s.quote && <p className="mt-2 border-l-2 border-crit/50 pl-3 text-sm italic text-ink-2 [overflow-wrap:anywhere]">« {s.quote} »</p>}
      </div>
      <dl className="grid grid-cols-3 gap-2">
        {counters.map(([dec, label, n]) => (
          <div key={dec} className="card px-3 py-2.5">
            <dd className="text-2xl font-semibold text-door-deep">{n}</dd>
            <dt className="text-xs text-ink-2">{label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
}
