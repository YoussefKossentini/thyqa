import { useEffect, useState } from "react";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api.js";
import { useOps } from "../lib/useOps.js";
import { dt, pct } from "../lib/format.js";
import { Button, Empty } from "../components/ui.jsx";

const OUTCOME = [
  ["paid", "Payé"], ["lost_price_shock", "Parti en voyant le prix"], ["lost", "Parti après une objection"],
  ["awaiting_approval", "Attend un humain"], ["payment_pending", "Paiement en attente"], ["payment_failed", "Paiement refusé"],
  ["blocked", "Bloqué par Fouchika"], ["lost_no_offer", "Parti sans offre"],
];
const RUN_COLORS = { a: "#7b8cff", b: "#f2b544" };
const FIELD = { lead_with_monthly_price: "Annoncer le prix mensuel d'abord", objection_strategies: "Réponse aux objections",
  pitch_focus: "Ce que le pitch met en avant", opening: "Première phrase" };
const STRAT = { value_first: "valeur d'abord", installments_first: "tranches d'abord", show_program: "programme + formateur",
  flexible_schedule: "horaires", simplify: "simplifier", student_discount: "code étudiant" };

const FOCUS = { outcomes: "résultats", projects: "projets", certificate: "certificat", schedule: "horaires", price: "prix" };
const OBJ = { price: "prix", trust: "confiance", time: "temps", relevance: "utilité", comprehension: "compréhension", payment_method: "moyen de paiement" };
const METRIC = { price_objection_share: "objections prix", trust_objection_share: "objections confiance", time_objection_share: "objections temps",
  revenue_lost_price_millimes: "perdu sur le prix", revenue_lost_trust_millimes: "perdu sur la confiance", conversion_rate: "conversion",
  payments_declined: "paiements refusés" };

function evidence(e) {
  const label = METRIC[e.metric] || e.metric.replaceAll("_", " ");
  if (typeof e.value !== "number") return `${label} : ${e.value}`;
  if (e.metric.endsWith("_millimes")) return `${label} : ${dt(e.value)}`;
  if (e.metric.endsWith("_share") || e.metric === "conversion_rate") return `${label} : ${Math.round(e.value * 100)} %`;
  return `${label} : ${e.value}`;
}

/** Only the entries that changed, in French. */
function diffRows(field, from, to) {
  if (field === "objection_strategies") {
    return Object.keys({ ...from, ...to }).filter((k) => from?.[k] !== to?.[k])
      .map((k) => [`Objection ${OBJ[k] || k}`, STRAT[from?.[k]] || from?.[k] || "", STRAT[to?.[k]] || to?.[k] || ""]);
  }
  const show = (v) => (v === true ? "oui" : v === false ? "non" : Array.isArray(v) ? v.map((x) => FOCUS[x] || x).join(", ") : String(v ?? ""));
  return [[FIELD[field] || field, show(from), show(to)]];
}

function StatPair({ label, a, b, format, better = "up" }) {
  if (a === undefined) return null;
  const delta = b === undefined ? null : b - a;
  const good = delta === null ? null : (better === "up" ? delta > 0 : delta < 0);
  return (
    <div>
      <p className="text-sm text-ink-2">{label}</p>
      <p className="mt-1 flex items-baseline gap-3 text-4xl font-semibold leading-none">
        <span className={b === undefined ? "" : "text-ink-2"}>{format(a)}</span>
        {b !== undefined && <><span className="text-2xl text-muted" aria-hidden="true">›</span><span>{format(b)}</span></>}
      </p>
      {delta !== null && delta !== 0 && (
        <p className={`mt-1 text-sm font-medium ${good ? "text-good-ink" : "text-crit-ink"}`}>
          {delta > 0 ? "+" : "−"}{format === pct ? `${Math.abs(Math.round(delta * 100))} points` : format(Math.abs(delta))}
        </p>
      )}
    </div>
  );
}

function OutcomeChart({ a, b }) {
  const keys = OUTCOME.filter(([k]) => (a?.outcomes?.[k] || 0) + (b?.outcomes?.[k] || 0) > 0);
  const data = keys.map(([k, label]) => ({ label, a: a?.outcomes?.[k] || 0, b: b?.outcomes?.[k] || 0 }));
  if (!data.length) return null;
  return (
    <div>
      <div className="mb-2 flex gap-4 text-sm text-ink-2">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: RUN_COLORS.a }} />Run 1, script v{a.script_version}</span>
        {b && <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: RUN_COLORS.b }} />Run 2, script v{b.script_version}</span>}
      </div>
      <div style={{ height: data.length * (b ? 52 : 32) + 16 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }} barGap={2} barCategoryGap={10}>
            <XAxis type="number" hide allowDecimals={false} />
            <YAxis type="category" dataKey="label" width={190} tick={{ fill: "var(--color-ink-2)", fontSize: 13 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "var(--color-door-wash)" }} formatter={(v, name) => [`${v} clients`, name === "a" ? "Run 1" : "Run 2"]} />
            <Bar dataKey="a" name="a" fill={RUN_COLORS.a} barSize={16} radius={[0, 4, 4, 0]} minPointSize={(v) => (v === 0 ? 2 : 0)} isAnimationActive={false}>
              <LabelList dataKey="a" position="right" fill="var(--color-ink)" fontSize={12} />
            </Bar>
            {b && (
              <Bar dataKey="b" name="b" fill={RUN_COLORS.b} barSize={16} radius={[0, 4, 4, 0]} minPointSize={(v) => (v === 0 ? 2 : 0)} isAnimationActive={false}>
                <LabelList dataKey="b" position="right" fill="var(--color-ink)" fontSize={12} />
              </Bar>
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function Learn() {
  const { tenant, tenants } = useOps();
  const approvers = tenants.find((t) => t.tenant_id === tenant)?.approvers || ["mouna"];
  const [n, setN] = useState(50);
  const [seed, setSeed] = useState(42);
  const [runA, setRunA] = useState(null);
  const [runB, setRunB] = useState(null);
  const [prop, setProp] = useState(null);
  const [activated, setActivated] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!tenant) return;
    setRunA(null); setRunB(null); setProp(null); setActivated(null);
    api(`/api/v1/runs?tenant_id=${tenant}`).then((runs) => {
      if (runs.length >= 2 && runs[runs.length - 1].seed === runs[runs.length - 2].seed && runs[runs.length - 1].script_version !== runs[runs.length - 2].script_version) {
        setRunA(runs[runs.length - 2]); setRunB(runs[runs.length - 1]);
      } else if (runs.length) setRunA(runs[runs.length - 1]);
    }).catch(() => {});
  }, [tenant]);

  async function step(name, fn) {
    setBusy(name); setErr(null);
    try { await fn(); } catch (e) { setErr(e.message); }
    setBusy(null);
  }
  const run1 = () => step("run1", async () => { setRunB(null); setProp(null); setActivated(null); setRunA(await api("/api/v1/runs", { body: { tenant_id: tenant, n, seed }, pin: true })); });
  const propose = () => step("propose", async () => setProp(await api("/api/v1/strategy/propose", { body: { tenant_id: tenant, run_id: runA?.run_id }, pin: true })));
  const activate = () => step("activate", async () => setActivated(await api(`/api/v1/scripts/${prop.draft.version}/activate`, { body: { tenant_id: tenant, approver_id: approvers[0] }, pin: true })));
  const run2 = () => step("run2", async () => setRunB(await api("/api/v1/runs", { body: { tenant_id: tenant, n: runA.n, seed: runA.seed }, pin: true })));

  const sa = runA?.summary, sb = runB?.summary;
  const steps = [
    { title: `Simuler ${n} clients avec le script actuel`, done: !!runA, result: sa && `${pct(sa.conversion_rate)} de conversion, ${dt(sa.revenue_collected_millimes)} encaissés`,
      action: <Button tone="primary" disabled={!!busy} onClick={run1}>{busy === "run1" ? "Simulation…" : runA ? "Relancer" : "Lancer"}</Button> },
    { title: "Zeineb lit les chiffres et propose une v2", done: !!prop, result: prop && `${prop.recommendations.length} recommandation(s), fondées sur les objections et le revenu perdu`,
      action: <Button tone="primary" disabled={!runA || !!busy} onClick={propose}>{busy === "propose" ? "Analyse…" : "Proposer"}</Button> },
    { title: "Fouchika vérifie le changement, un humain l'active", done: !!activated,
      result: prop?.check && (prop.check.ok ? `Fouchika : seuls des champs modifiables changent. ${activated ? `Activée par ${approvers[0]}.` : ""}` : `Fouchika refuse : ${prop.check.reasons.map((r) => r.message).join(", ")}`),
      action: <Button tone="primary" disabled={!prop?.check?.ok || !!activated || !!busy} onClick={activate}>{busy === "activate" ? "…" : `Activer la v${prop?.draft?.version ?? 2}`}</Button> },
    { title: "Rejouer exactement les mêmes clients", done: !!runB, result: sb && `${pct(sb.conversion_rate)} de conversion, ${dt(sb.revenue_collected_millimes)} encaissés`,
      action: <Button tone="primary" disabled={!runA || !activated || !!busy} onClick={run2}>{busy === "run2" ? "Simulation…" : "Rejouer"}</Button> },
  ];

  return (
    <div className="mx-auto max-w-6xl p-6 lg:p-8">
      <h1 className="page-title text-4xl font-semibold">L'équipe apprend</h1>
      <p className="mt-2 max-w-3xl text-ink-2">Si Zahi simule des clients avec une graine fixe. Les mêmes personnes passent dans les deux runs : seul le script de Sboui change. Les résultats sont simulés, c'est la méthode qu'on montre.</p>
      <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-ink-2">
        <label className="flex items-center gap-2">Clients <input type="number" min={5} max={200} value={n} onChange={(e) => setN(+e.target.value)} className="w-20 rounded border border-line bg-surface px-2 py-1" /></label>
        <label className="flex items-center gap-2">Graine <input type="number" value={seed} onChange={(e) => setSeed(+e.target.value)} className="w-20 rounded border border-line bg-surface px-2 py-1" /></label>
      </div>

      <ol className="mt-6 grid gap-3 md:grid-cols-4">
        {steps.map((s, i) => (
          <li key={s.title} className={`card relative flex flex-col gap-2 p-4 ${s.done ? "!border-door/40 !bg-door-wash/60" : ""} ${i < 3 ? "md:after:absolute md:after:-right-[11px] md:after:top-9 md:after:z-10 md:after:h-2.5 md:after:w-2.5 md:after:rotate-45 md:after:border-r-2 md:after:border-t-2 md:after:border-door/50" : ""}`}>
            <span className={`grid h-7 w-7 place-items-center rounded-full text-sm font-semibold ${s.done ? "bg-door text-white" : "border border-line text-ink-2"}`}>{i + 1}</span>
            <p className="font-medium leading-snug">{s.title}</p>
            {s.result && <p className="text-sm text-ink-2">{s.result}</p>}
            <div className="mt-auto pt-1">{s.action}</div>
          </li>
        ))}
      </ol>
      {err && <p className="mt-3 text-sm text-crit-ink">{err}</p>}

      {!runA ? (
        <div className="mt-8"><Empty>Lance la première simulation (étape 1). Il faut le code PIN ops, à saisir dans « Scénarios ».</Empty></div>
      ) : (
        <div className="card-kids mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section className="flex flex-col gap-6">
            <StatPair label="Conversion" a={sa.conversion_rate} b={sb?.conversion_rate} format={pct} />
            <StatPair label="Revenu simulé encaissé" a={sa.revenue_collected_millimes} b={sb?.revenue_collected_millimes} format={dt} />
            <StatPair label="Ventes perdues, en valeur catalogue" a={sa.revenue_lost_millimes} b={sb?.revenue_lost_millimes} format={dt} better="down" />
          </section>
          <section>
            <h2 className="mb-3 text-base font-semibold">Ce que sont devenus les {runA.n} clients</h2>
            <OutcomeChart a={runA} b={runB} />
          </section>
        </div>
      )}

      {prop && (
        <div className="card-kids mt-4 grid gap-4 lg:grid-cols-2">
          <section>
            <h2 className="mb-3 text-base font-semibold">Ce que propose Zeineb</h2>
            <ul className="flex flex-col gap-4">
              {prop.recommendations.map((r) => (
                <li key={r.rec_id} className="border-l-2 border-door pl-4">
                  <p className="font-medium">{r.title}</p>
                  <p className="mt-1 text-sm text-ink-2">{r.rationale}</p>
                  <p className="mt-1 text-xs text-muted">Preuves : {r.evidence.map(evidence).join(", ")}</p>
                </li>
              ))}
            </ul>
          </section>
          {prop.check && (
            <section>
              <h2 className="mb-3 text-base font-semibold">Ce qui change dans le script (vérifié par Fouchika)</h2>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-ink-2"><th className="py-1.5 pr-3 font-medium">Champ</th><th className="py-1.5 pr-3 font-medium">Avant</th><th className="py-1.5 font-medium">Après</th></tr></thead>
                <tbody>
                  {Object.entries(prop.check.diff).flatMap(([k, v]) => diffRows(k, v.from, v.to)).map(([label, from, to]) => (
                    <tr key={label} className="border-t border-line align-top">
                      <td className="py-2 pr-3">{label}</td><td className="py-2 pr-3 text-ink-2">{from}</td><td className="py-2 font-medium">{to}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-muted">Prix, remises, sécurité et paiements ne font pas partie des champs qu'un script peut changer.</p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
