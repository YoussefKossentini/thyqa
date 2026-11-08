import { useEffect, useState } from "react";
import { OpsContext, useOpsState } from "./lib/useOps.js";
import DemoDrawer from "./components/DemoDrawer.jsx";
import QrModal from "./components/QrModal.jsx";
import { Button, Pill } from "./components/ui.jsx";
import Majlis from "./pages/Majlis.jsx";
import Learn from "./pages/Learn.jsx";
import Client from "./pages/Client.jsx";
import Landing from "./pages/Landing.jsx";
import { Logo } from "./components/brand.jsx";

function useRoute() {
  const read = () => window.location.hash.replace(/^#/, "") || "/";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onHash = () => setRoute(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

export default function App() {
  const route = useRoute();
  // Visitors see the landing page and the chat with Sboui. The team console lives under /ops and is not linked from there.
  if (route.startsWith("/ops")) return <Ops route={route.slice(4) || "/"} />;
  if (route.startsWith("/hack")) return <Client mode="hack" />;
  if (route.startsWith("/client")) return <Client mode="client" />;
  return <Landing />;
}

const NAV = [["/", "Majlis"], ["/learn", "L'équipe apprend"]];

function StatusPills({ status, connected }) {
  if (!status) return null;
  const llm = status.llm || {};
  const pol = status.policy || {};
  const live = llm.mode === "auto" && (llm.providers || []).length;
  return (
    <div className="flex items-center gap-1.5 sm:flex-wrap">
      <Pill onDark tone="door" title="Aucun argent réel ne bouge">Paiements simulés</Pill>
      <Pill onDark tone={live ? "good" : "warn"} title="Chaîne LLM : Gemini, Groq, Ollama, Replay, puis agents déterministes">
        {live ? `LLM ${llm.providers.join(", ")}` : llm.mode === "replay" ? "LLM en Replay" : "Agents en MOCK"}
      </Pill>
      <Pill onDark tone={pol.fail_closed ? "crit" : pol.signature === "valid" ? "good" : "warn"} title={`sha256 ${pol.sha256 || ""}`}>
        {pol.fail_closed ? "Politique refusée, tout est bloqué" : pol.signature === "valid" ? "Politique signée" : "Politique non signée (dev)"}
      </Pill>
      <Pill onDark tone={status.siem?.online ? "good" : "neutral"}>{status.siem?.online ? "Wazuh en ligne" : "Wazuh hors ligne"}</Pill>
      {status.ml_fraud?.enabled && <Pill onDark tone="neutral" title={status.ml_fraud.trained_on}>Isolation Forest actif</Pill>}
      <span className="ml-1 inline-flex items-center gap-1.5 text-xs text-white/85">
        <span className={`h-2 w-2 rounded-full ring-2 ${connected ? "bg-[#5be05b] ring-[#5be05b]/30" : "bg-crit ring-crit/30"}`} />{connected ? "En direct" : "Reconnexion"}
      </span>
    </div>
  );
}

function Ops({ route }) {
  const ops = useOpsState();
  const [demo, setDemo] = useState(false);
  const [qr, setQr] = useState(false);
  useEffect(() => {
    const onKey = (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
      if (e.key === "d") setDemo((v) => !v);
      if (e.key === "q") setQr((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.world = "ops";
    return () => { delete document.documentElement.dataset.world; };
  }, []);
  const tenantName = ops.tenants.find((t) => t.tenant_id === ops.tenant)?.display_name;
  const page = route.startsWith("/learn") ? <Learn /> : <Majlis />;

  return (
    <OpsContext.Provider value={ops}>
      <div data-world="ops" className="flex h-full min-h-0 flex-col bg-wall text-ink">
        <header className="topbar text-white shadow-[0_2px_12px_rgb(15_51_101/.25)]">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-2.5">
            <a href="#/ops" className="flex items-center gap-3 no-underline" aria-label="THYQA, console de l'équipe">
              <Logo dark className="h-9" />
              <span className="font-kufi text-xl text-white/80">ثقة</span>
              <span className="border-l border-white/20 pl-3 text-xs text-white/65">{tenantName}</span>
            </a>
            <nav className="scroll-quiet -mx-1 flex max-w-full gap-1 overflow-x-auto px-1 [&>a]:whitespace-nowrap" aria-label="Pages">
              {NAV.map(([href, label]) => {
                const active = href === "/" ? route === "/" : route.startsWith(href);
                return (
                  <a key={href} href={`#/ops${href === "/" ? "" : href}`} aria-current={active ? "page" : undefined}
                    className={`rounded-lg px-3.5 py-2 text-sm no-underline transition-colors ${active ? "bg-door/20 font-semibold text-white ring-1 ring-door/50" : "text-white/80 hover:bg-white/10 hover:text-white"}`}>
                    {label}
                  </a>
                );
              })}
            </nav>
            <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
              <button type="button" onClick={() => setQr(true)} title="Raccourci : q" className="rounded-lg border border-white/25 bg-white/10 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20">QR Hack Thyqa</button>
              <button type="button" onClick={() => setDemo(true)} title="Raccourci : d" className="rounded-lg bg-door px-3 py-1.5 text-sm font-semibold text-[#0e0f14] transition-colors hover:bg-door-deep">Scénarios</button>
              <a href="#/client" target="_blank" rel="noreferrer" className="rounded-lg px-2.5 py-1.5 text-sm text-white/85 no-underline hover:bg-white/10 hover:text-white">App client</a>
            </div>
          </div>
          <div className="scroll-quiet overflow-x-auto border-t border-white/10 bg-black/10 px-5 py-1.5"><StatusPills status={ops.status} connected={ops.connected} /></div>
        </header>
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{page}</main>
      </div>
      <DemoDrawer open={demo} onClose={() => setDemo(false)} />
      <QrModal open={qr} onClose={() => setQr(false)} />
    </OpsContext.Provider>
  );
}
