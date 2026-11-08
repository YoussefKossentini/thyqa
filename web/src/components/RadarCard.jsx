import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import { PERSONA } from "../lib/format.js";
import { Empty, SectionTitle } from "./ui.jsx";

const AXES = [["price_sensitivity", "Prix"], ["trust", "Confiance"], ["urgency", "Urgence"], ["comprehension", "Compréhension"], ["intent", "Intention"]];

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return <div className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-sm"><span className="text-ink-2">{d.axis}</span> <b>{d.value}</b>/100</div>;
}

export default function RadarCard({ events }) {
  const last = events.find((e) => e.type === "fahem.analysis" && e.payload?.radar);
  const radar = last?.payload?.radar;
  const data = radar ? AXES.map(([k, axis]) => ({ axis, value: radar[k] })) : [];
  return (
    <section>
      <SectionTitle aside={last ? `persona ${PERSONA[last.payload.persona] || last.payload.persona}` : null}>Radar d'hésitation</SectionTitle>
      {!radar ? (
        <Empty>Dr. Slimane dessine ici le dernier client : sensibilité au prix, confiance, urgence, compréhension, intention.</Empty>
      ) : (
        <>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data} outerRadius="70%" margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
                <PolarGrid stroke="var(--color-line)" />
                <PolarAngleAxis dataKey="axis" tick={{ fill: "var(--color-ink-2)", fontSize: 12 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                <Radar dataKey="value" stroke="var(--color-door)" strokeWidth={2} fill="var(--color-door)" fillOpacity={0.12} dot={{ r: 3, fill: "var(--color-door)" }} />
                <Tooltip content={<Tip />} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <dl className="mt-1 grid grid-cols-3 gap-x-1 gap-y-2 text-center">
            {data.map((d) => (
              <div key={d.axis}><dd className="text-sm font-semibold tabular">{d.value}</dd><dt className="text-[0.78rem] text-ink-2">{d.axis}</dt></div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}
