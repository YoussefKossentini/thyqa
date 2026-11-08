import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

const TITLES = [["simulated", "Ce qui est simulé"], ["human_supervision", "Où un humain décide"], ["known_failure_modes", "Ce qui peut échouer"]];

export default function Limits() {
  const [limits, setLimits] = useState(null);
  useEffect(() => { api("/api/v1/limits?lang=fr").then(setLimits).catch(() => {}); }, []);
  return (
    <div className="mx-auto max-w-6xl p-8">
      <h1 className="page-title text-4xl font-semibold">Les limites, dites franchement</h1>
      <p className="mt-2 max-w-2xl text-ink-2">Un prototype de 14 heures. Voici ce qu'il ne fait pas pour de vrai, où un humain garde la main, et ce qui peut casser.</p>
      <div className="card-kids mt-8 grid gap-4 md:grid-cols-3">
        {TITLES.map(([key, title]) => (
          <section key={key}>
            <h2 className="border-b-2 border-door/20 pb-2 text-lg font-semibold text-door-deep">{title}</h2>
            <ul className="mt-3 flex flex-col gap-3">
              {(limits?.[key] || []).map((t) => <li key={t} className="text-base leading-relaxed text-ink">{t}</li>)}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
