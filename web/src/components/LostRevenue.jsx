import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dt, OBJECTION } from "../lib/format.js";
import { Empty, SectionTitle } from "./ui.jsx";

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="max-w-[260px] rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-sm">
      <p className="font-semibold">{d.label} : {dt(d.value)}</p>
      <p className="text-ink-2">{d.cases} ventes perdues. Somme des prix catalogue des produits discutés, quand cette objection est restée sans réponse.</p>
    </div>
  );
}

/** One series, one colour: bar length is the money, labels carry every value. */
export default function LostRevenue({ rows, title = "Ce que coûtent les objections", compact = false }) {
  const data = (rows || []).map((r) => ({ label: OBJECTION[r.objection] || r.objection, value: r.revenue_lost_millimes,
    cases: r.lost_cases, valueLabel: dt(r.revenue_lost_millimes) }));
  return (
    <section>
      {title && <SectionTitle aside="ventes perdues, simulé">{title}</SectionTitle>}
      {data.length === 0 ? (
        <Empty>Aucune vente perdue pour l'instant. Quand un client part, l'objection restée sans réponse apparaît ici avec son coût.</Empty>
      ) : (
        <div style={{ height: data.length * (compact ? 30 : 36) + 12 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 2, right: 72, bottom: 2, left: 0 }} barCategoryGap={8}>
              <XAxis type="number" hide domain={[0, "dataMax"]} />
              <YAxis type="category" dataKey="label" width={118} tick={{ fill: "var(--color-ink-2)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip content={<Tip />} cursor={{ fill: "var(--color-door-wash)" }} />
              <Bar dataKey="value" fill="var(--color-door)" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="valueLabel" position="right" fill="var(--color-ink)" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
