import { useOps } from "../lib/useOps.js";
import Door from "../components/Door.jsx";
import Feed from "../components/Feed.jsx";
import Kpis from "../components/Kpis.jsx";
import RadarCard from "../components/RadarCard.jsx";
import LostRevenue from "../components/LostRevenue.jsx";
import Approvals from "../components/Approvals.jsx";

export default function Majlis() {
  const { events, kpis, lastDecision } = useOps();
  return (
    <div className="grid min-h-full grid-cols-1 xl:h-full xl:min-h-0 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)_400px]">
      <aside className="scroll-quiet hero-wall border-b border-line p-5 xl:overflow-y-auto lg:border-b-0 lg:border-r">
        <Door lastDecision={lastDecision} kpis={kpis} />
      </aside>
      <section className="flex min-h-[70vh] flex-col gap-4 p-5 xl:min-h-0">
        <Kpis kpis={kpis} />
        <Feed events={events} />
      </section>
      <aside className="scroll-quiet flex flex-col gap-4 border-t border-line p-5 lg:col-span-2 xl:col-span-1 xl:overflow-y-auto xl:border-l xl:border-t-0">
        <div className="card p-4"><Approvals /></div>
        <div className="card p-4"><RadarCard events={events} /></div>
        <div className="card p-4"><LostRevenue rows={kpis?.revenue_lost_by_objection} /></div>
      </aside>
    </div>
  );
}
