import { dt, pct } from "../lib/format.js";

export default function Kpis({ kpis }) {
  const k = kpis || { payments: {}, security: {} };
  const p = k.payments || {};
  const tiles = [
    ["Conversations", k.interactions ?? 0, `${k.interested ?? 0} intéressés`],
    ["Conversion", pct(k.conversion_rate), `${k.conversions ?? 0} ventes`],
    ["Revenu simulé", dt(k.revenue_collected_millimes ?? 0), `contrats ${dt(k.contract_value_millimes ?? 0)}`],
    ["Paiements", `${p.succeeded ?? 0} réussis`, `${p.declined ?? 0} refusés, ${(p.pending ?? 0) + (p.awaiting_approval ?? 0)} en attente`],
    ["Alertes sécurité", k.security?.alerts_total ?? 0, `${k.security?.injections_blocked ?? 0} injections bloquées`],
    ["Satisfaction", k.satisfaction?.score_0_100 !== undefined ? `${k.satisfaction.score_0_100}/100` : "–", "selon Dr. Slimane"],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-6">
      {tiles.map(([label, value, sub]) => (
        <div key={label} className="card relative min-w-0 overflow-hidden px-4 py-3 before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:bg-door/70">
          <dt className="text-[0.8rem] font-medium text-ink-2">{label}</dt>
          <dd className="mt-1 truncate text-2xl font-semibold leading-tight text-door-deep">{value}</dd>
          <dd className="truncate text-xs text-muted">{sub}</dd>
        </div>
      ))}
    </dl>
  );
}
