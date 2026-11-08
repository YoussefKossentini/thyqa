import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "../lib/api.js";
import { dt } from "../lib/format.js";
import { DISPLAY } from "../lib/names.js";
import { Seal } from "../components/brand.jsx";
import { FaqItem, Json, Radar, SealIcon, Typing, useInView, useReducedMotion, useScrollSpy } from "../components/atm.jsx";
import attacks from "../data/attackWall.json";
import "../landing.css";

const PUBLIC_URL = import.meta.env.VITE_PUBLIC_URL;
const PHRASES = ["9addech soum el formation ?", "ghali barcha 3liya…", "nkhalles 3la 3 marrat ?", "ma 3andich thi9a fel paiement en ligne"];
const CONTROLS = ["Input guard", "Output guard", "Policy engine", "Sakk", "Validation humaine", "Journal chaîné", "Kill switch"];
const LANGS = [["derja", "Derja"], ["fr", "FR"], ["en", "EN"]];
const FEATURES = [
  ["f-vendre", "Vendre"], ["f-comprendre", "Comprendre"], ["f-decider", "Décider"], ["encaisser", "Encaisser"],
  ["f-analyser", "Analyser"], ["f-ameliorer", "S'améliorer"], ["f-architecture", "Architecture"],
];
const SEAL_LABELS = ["Prix du catalogue", "Accord du client", "Contrôle sécurité", "Validation humaine", "Paiement"];

function Wordmark({ className = "text-xl" }) {
  return <span className={`f-tech font-bold ${className}`} style={{ color: "#fff", letterSpacing: ".08em" }} aria-label="THYQA">THY<span style={{ color: "var(--a-night-text)" }}>Q</span>A</span>;
}
const Arrow = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>;

function Title({ kicker, children, dark }) {
  return (
    <div className="max-w-3xl">
      {kicker && <p className="f-tech m-0 mb-3 text-sm font-semibold" style={{ color: dark ? "var(--a-night-text)" : "var(--a-brand)" }}>{kicker}</p>}
      <h2 className="f-display m-0 text-[clamp(2rem,4.6vw,3rem)]">{children}</h2>
    </div>
  );
}

function CommandBox() {
  const [text, setText] = useState("");
  const [lang, setLang] = useState("derja");
  function send() {
    const t = text.trim();
    if (!t) return;
    try { sessionStorage.setItem("thiqa_queued", t); sessionStorage.setItem("thiqa_queued_lang", lang); } catch { /* storage may be blocked */ }
    window.location.hash = "#/client";
  }
  return (
    <div className="glow-wrap mx-auto w-full max-w-2xl">
      <form className="cmd-box" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label htmlFor="cmd" className="sr-only-a">Écris à Sboui</label>
        <textarea id="cmd" value={text} maxLength={600} rows={2} placeholder="Écris à Sboui… derja, français ou English"
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <div className="mt-2 flex items-center justify-between gap-3">
          <div className="flex gap-2" role="group" aria-label="Langue">
            {LANGS.map(([v, l]) => <button key={v} type="button" className="chip" aria-pressed={lang === v} onClick={() => setLang(v)}>{l}</button>)}
          </div>
          <button type="submit" className="send-btn" disabled={!text.trim()} aria-label="Envoyer à Sboui"><Arrow /></button>
        </div>
      </form>
    </div>
  );
}

function TrustBar() {
  const items = [...CONTROLS];
  return (
    <div className="glass-strong mx-auto w-[min(56rem,92%)] rounded-2xl px-5 py-4 text-start md:grid md:grid-cols-[auto_minmax(0,1fr)] md:items-center md:gap-8">
      <div>
        <p className="f-tech m-0 text-xs font-semibold" style={{ color: "var(--on-night-3)" }}>Langues</p>
        <p className="m-0 mt-1 text-sm" style={{ color: "var(--on-night)" }}>Derja · Français · English · <bdi>العربية</bdi></p>
      </div>
      <div className="mt-4 min-w-0 md:mt-0">
        <p className="f-tech m-0 mb-1 text-xs font-semibold" style={{ color: "var(--on-night-3)" }}>Contrôles de sécurité</p>
        <div className="a-marquee">
          <div className="a-marquee-track">
            {[0, 1].map((k) => items.map((c) => (
              <span key={`${k}-${c}`} className="a-mq-item" data-dup={k === 1 ? "" : undefined} aria-hidden={k === 1 ? "true" : undefined}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /></svg>{c}
              </span>
            )))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ id, index, title, line, who, children, visual }) {
  return (
    <div id={id} style={{ scrollMarginTop: "5.5rem" }} className="grid items-center gap-8 py-12 md:grid-cols-2 md:gap-12 md:py-16">
      <div className={index % 2 ? "md:order-2" : ""}>
        <p className="f-tech m-0 text-sm font-semibold" style={{ color: "var(--a-brand)" }}>{who}</p>
        <h3 className="f-display m-0 mt-2 text-[clamp(1.6rem,3vw,2.1rem)]">{title}</h3>
        <p className="m-0 mt-3 max-w-md text-lg leading-relaxed" style={{ color: "var(--a-ink-2)" }}>{line}</p>
        {children}
      </div>
      <div className="min-w-0">{visual}</div>
    </div>
  );
}

function MiniChat({ prod, full }) {
  const b = "max-w-[88%] rounded-2xl px-3.5 py-2 text-[0.9rem] leading-snug";
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border bg-white p-4" style={{ borderColor: "var(--a-hair)" }}>
      <div className={`${b} self-end rounded-br-md text-white`} style={{ background: "var(--a-brand)" }}>9adeh soum {prod?.name || "el formation"} ?</div>
      <div className={`${b} self-start rounded-bl-md border`} style={{ borderColor: "var(--a-hair)" }}>Ena Sboui, agent IA. {prod ? `${prod.name} : ${prod.duration}.` : "Chnowa t7eb ta3ref ?"}</div>
      <div className={`${b} self-end rounded-br-md text-white`} style={{ background: "var(--a-brand)" }}>behi, nheb nsajjel</div>
      {prod && full && (
        <div className="self-start rounded-2xl border-2 bg-white p-3 text-sm" style={{ borderColor: "var(--a-brand)" }}>
          <p className="m-0 text-xs" style={{ color: "var(--a-ink-3)" }}>Offre, prix du catalogue</p>
          <p className="m-0 font-semibold">{prod.name}</p>
          <p className="f-tech m-0 text-2xl font-bold" style={{ color: "var(--a-brand)" }}>{dt(full.total_millimes)}</p>
        </div>
      )}
    </div>
  );
}

function SealSequence() {
  const ref = useRef(null);
  const seen = useInView(ref);
  const [n, setN] = useState(0);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!seen) return;
    if (reduce) { setN(5); return; }
    let i = 0; const t = setInterval(() => { i += 1; setN(i); if (i >= 5) clearInterval(t); }, 420);
    return () => clearInterval(t);
  }, [seen, reduce]);
  return (
    <ol ref={ref} className="m-0 flex list-none flex-wrap items-start gap-x-5 gap-y-3 p-0">
      {SEAL_LABELS.map((l, i) => {
        const na = i === 3;
        return <li key={l} className="flex flex-col items-center gap-1.5"><Seal state={na ? "na" : i < n ? "sealed" : "pending"} size={48} /><span className="text-xs" style={{ color: "var(--a-ink-2)" }}>{l}</span></li>;
      })}
    </ol>
  );
}

function Kpi({ label, value }) {
  return <div className="rounded-xl border bg-white p-3" style={{ borderColor: "var(--a-hair)" }}><p className="f-tech m-0 text-3xl font-bold leading-none">{value}</p><p className="m-0 mt-1 text-xs" style={{ color: "var(--a-ink-2)" }}>{label}</p></div>;
}

function Blueprint() {
  const Box = ({ children, strong }) => <div className="rounded-lg border px-3 py-2 text-center text-sm" style={{ borderColor: strong ? "var(--a-brand)" : "#9aa0b4", background: "#fff", fontWeight: strong ? 600 : 400, color: strong ? "var(--a-brand)" : "var(--a-ink)" }}>{children}</div>;
  const Down = () => <div className="mx-auto h-5 w-px" style={{ background: "#9aa0b4" }} aria-hidden="true" />;
  return (
    <div className="relative overflow-hidden rounded-2xl border p-5" style={{ borderColor: "var(--a-hair)", background: "#fff" }}>
      <div className="a-grid light" style={{ WebkitMaskImage: "none", maskImage: "none" }} />
      <div className="relative mx-auto flex max-w-md flex-col">
        <Box>Client (texte ou voix)</Box><Down />
        <Box>API + Input guard</Box><Down />
        <Box>Orchestrateur · {DISPLAY.orchestrator || "Fadhila"}</Box><Down />
        <Box>Agents · {DISPLAY.sahbi}, {DISPLAY.fahem}, {DISPLAY.sandouk}</Box><Down />
        <Box strong>Passerelle call_tool() · policy.yaml</Box><Down />
        <Box strong>Contrôleur {DISPLAY.bouab} · règles, risque, approbation, Sakk</Box><Down />
        <Box>{DISPLAY.sandouk} Pay (SIMULÉ)</Box><Down />
        <Box>Ledger + journal chaîné</Box>
        <p className="m-0 mt-4 text-center text-xs" style={{ color: "var(--a-ink-3)" }}>Retour : agents → Output guard → client. Côté : journal de sécurité → SIEM.</p>
      </div>
    </div>
  );
}

function AttackCard({ a }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  async function replay() {
    setBusy(true); setState(null);
    try {
      const c = await api("/api/v1/cases", { body: { channel: "hack_us" } });
      const r = await api("/api/v1/interaction/turn", { body: { case_id: c.case_id, text: a.text } });
      setState(r.withheld ? { ok: true, text: "Bloqué avant l'agent" } : { ok: false, text: "Reçu par Sboui, la réponse est contrôlée" });
    } catch (e) {
      setState({ ok: false, text: e.status === 429 ? "Limite atteinte, réessayez dans une minute" : "Serveur injoignable" });
    }
    setBusy(false);
  }
  return (
    <article className="glass-strong rounded-2xl p-5">
      <div className="flex items-center gap-3">
        <span className="f-tech grid h-10 w-10 place-items-center rounded-full text-sm font-bold" style={{ background: "var(--a-brand)", color: "#fff" }} aria-hidden="true">BM</span>
        <div className="min-w-0 flex-1"><p className="m-0 text-sm font-semibold">{DISPLAY.sarrak}</p><p className="f-tech m-0 text-xs" style={{ color: "var(--on-night-3)" }}>#{a.category}</p></div>
        <span className="f-tech rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: "var(--hair-night)", color: "var(--on-night-2)" }}>{a.lang}</span>
      </div>
      <p dir="auto" className="m-0 mt-3 break-words text-[0.95rem] leading-relaxed" style={{ color: "var(--on-night-2)" }}>{a.text}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="f-tech rounded-full px-2.5 py-1 text-xs font-semibold" style={{ background: "rgba(52,210,123,.12)", color: "var(--a-ok-night)", border: "1px solid rgba(52,210,123,.3)" }}>
          {state ? `Verdict : ${state.text}` : `Attendu : ${a.expected}`}
        </span>
        <button type="button" disabled={busy} onClick={replay} className="chip ml-auto" style={{ background: "transparent", color: "var(--a-night-text)", borderColor: "rgba(165,176,255,.4)" }}>{busy ? "…" : "Rejouer en direct"}</button>
      </div>
      {state && !state.ok && <p role="status" className="m-0 mt-2 text-xs" style={{ color: "var(--a-warn-night)" }}>{state.text}</p>}
    </article>
  );
}

export default function Landing() {
  const root = useRef(null);
  const reduce = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);
  const [catalog, setCatalog] = useState(null);
  const [cur, setCur] = useState("TND");
  const [board, setBoard] = useState(null);
  const active = useScrollSpy(FEATURES.map((f) => f[0]), root);

  useEffect(() => {
    api("/api/v1/tenants").then((d) => {
      const t = d.tenants.find((x) => x.tenant_id === d.active) || d.tenants[0];
      setCatalog(t?.catalog || []); setCur(t?.currency || "TND");
    }).catch(() => setCatalog([]));
    const load = () => api("/api/v1/hack/scoreboard").then(setBoard).catch(() => {});
    load(); const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const prod = catalog?.[0];
  const full = prod?.plans.find((p) => p.installments === 1);
  const split = [...(prod?.plans || [])].reverse().find((p) => p.installments > 1);
  const go = (id) => { setMenu(false); root.current?.querySelector(`#${id}`)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" }); };

  const analysis = { intent: "price_question", sentiment: -20, objections: ["price", "payment_method"], satisfaction: "neutral",
    radar: { price_sensitivity: 80, trust: 45, urgency: 30, comprehension: 70, intent: 60 }, persona: "broke_student", lang: "derja" };
  const decision = { decision: "REQUIRE_APPROVAL", agent_id: "sandouk", action: "pay.create_intent", risk_score: 30,
    reasons: [{ code: "R02_APPROVAL_THRESHOLD", rule_id: "R02", message: "Amount above the approval threshold" }], approval_id: "apr_7c1e…" };
  const sakk = { action: "pay.create_intent", payment_id: "pay_8f2c…", amount_millimes: full?.total_millimes ?? 0, currency: cur,
    customer_confirmation: true, idempotency_key: "idem_41ab…", authorization: "eyJ2IjoxLCJh…·9f3a…" };

  return (
    <div ref={root} className="atm h-full overflow-y-auto" onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 24)}>
      <header className={`a-nav ${scrolled ? "scrolled" : ""}`} style={{ height: "4.5rem", marginBottom: "-4.5rem" }}>
        <div className="mx-auto flex h-full max-w-[1200px] items-center gap-3 px-5">
          <a href="#/" aria-label="THYQA, accueil" className="a-nav-link flex items-center gap-2 text-white no-underline">
            <span className="a-nav-seal" style={{ color: "#A5B0FF" }}><SealIcon size={26} /></span>
            <Wordmark />
          </a>
          <nav aria-label="Sections" className="a-capsule glass-soft mx-auto hidden items-center gap-1 rounded-full p-1 md:flex">
            <button type="button" onClick={() => go("equipe")}>Équipe</button>
            <button type="button" onClick={() => go("attaques")}>Sécurité</button>
            <button type="button" onClick={() => go("faq")}>FAQ</button>
          </nav>
          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <button type="button" className="a-capsule glass-soft rounded-full md:!hidden" style={{ color: "var(--on-night)", minHeight: 44, padding: "0 1rem" }} aria-expanded={menu} onClick={() => setMenu(!menu)}>Menu</button>
            <a href="#/client" className="btn-white">Parler à Sboui</a>
          </div>
        </div>
        {menu && (
          <div className="glass-strong a-capsule mx-5 mt-1 flex flex-col rounded-2xl p-2 md:hidden">
            <button type="button" onClick={() => go("equipe")}>Équipe</button>
            <button type="button" onClick={() => go("attaques")}>Sécurité</button>
            <button type="button" onClick={() => go("faq")}>FAQ</button>
          </div>
        )}
      </header>

      {/* HERO */}
      <section className="a-night relative px-5 pb-44 pt-36 text-center md:pt-44" style={{ minHeight: "110vh" }}>
        <div className="a-atmos" aria-hidden="true">
          <svg className="a-seal-bg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="none" stroke="#fff" strokeWidth="9" strokeDasharray="190 62" transform="rotate(-70 50 50)" /></svg>
        </div>
        <div className="a-grid" aria-hidden="true" />
        <div className="relative z-10 mx-auto max-w-4xl">
          <button type="button" className="a-badge" onClick={() => go("encaisser")}><i>Nouveau</i>Chaque paiement est scellé · Sakk →</button>
          <h1 className="f-display m-0 mt-6 text-[clamp(2.75rem,7.5vw,4.5rem)]" style={{ color: "#fff" }}>
            Vendez en derja.<br />Encaissez en <em style={{ color: "var(--a-night-text)" }}>confiance</em>.
          </h1>
          <p className="m-0 mt-6 text-[1.15rem] leading-relaxed md:text-[1.25rem]" style={{ color: "var(--on-night-2)" }}>
            Sboui comprend : <span className="f-tech" style={{ color: "#fff" }}><Typing phrases={PHRASES} /></span>
          </p>
          <div className="mt-8"><CommandBox /></div>
          <p className="m-0 mt-5 text-sm" style={{ color: "var(--on-night-3)" }}>Démo TechX · texte ou voix · paiements simulés · données synthétiques</p>
        </div>
        <div className="absolute inset-x-0 bottom-0 z-20 translate-y-1/2 px-5"><TrustBar /></div>
      </section>

      {/* COMMENT THYQA TRAVAILLE */}
      <section id="equipe" className="a-light px-5 pb-16 pt-40 md:pb-24" style={{ scrollMarginTop: "4rem" }}>
        <div className="mx-auto max-w-[1200px]">
          <Title kicker="L'équipe">Comment Thyqa travaille.</Title>
          <div className="mt-8 grid gap-8 lg:grid-cols-[25%_1fr]">
            <aside className="hidden lg:block">
              <nav aria-label="Étapes" className="fnav sticky top-28">
                {FEATURES.map(([id, l]) => <button key={id} type="button" aria-current={active === id ? "step" : undefined} onClick={() => go(id)}>{l}</button>)}
              </nav>
            </aside>
            <div className="min-w-0 divide-y" style={{ borderColor: "var(--a-hair)" }}>
              <Row id="f-vendre" index={0} who={DISPLAY.sahbi} title="Vendre" line="Il parle comme vos clients, et ne touche jamais à l'argent." visual={<MiniChat prod={prod} full={full} />} />
              <Row id="f-comprendre" index={1} who={DISPLAY.fahem} title="Comprendre" line="Chaque hésitation devient une donnée structurée." visual={
                <div className="flex flex-col gap-3"><Json data={analysis} />
                  <div className="a-night grid place-items-center rounded-2xl py-3"><Radar values={Object.values(analysis.radar)} labels={["Prix", "Confiance", "Urgence", "Compréhension", "Intention"]} /></div></div>} />
              <Row id="f-decider" index={2} who={DISPLAY.bouab} title="Décider" line="Le modèle propose. Le code tranche." visual={<Json data={decision} />} />
              <Row id="encaisser" index={3} who={DISPLAY.sandouk} title="Encaisser" line="Pas de sceau, pas de paiement." visual={
                <div className="flex flex-col gap-4"><div className="rounded-2xl border bg-white p-4" style={{ borderColor: "var(--a-hair)" }}><SealSequence /></div><Json data={sakk} /></div>} />
              <Row id="f-analyser" index={4} who={DISPLAY.si_hsab} title="Analyser" line="Les chiffres, et ce que chaque objection coûte." visual={
                <div className="flex flex-col gap-3 rounded-2xl p-4" style={{ background: "var(--a-surface-2)" }}>
                  <div className="grid grid-cols-3 gap-2"><Kpi label="Conversion" value="19 %" /><Kpi label="Intéressés" value="12" /><Kpi label="Paiements" value="3" /></div>
                  <div className="rounded-xl border bg-white p-3" style={{ borderColor: "var(--a-hair)" }}>
                    <p className="m-0 mb-2 text-xs font-semibold" style={{ color: "var(--a-ink-2)" }}>Part du revenu perdu, par objection <span className="ml-1 rounded-full px-2 py-0.5" style={{ background: "var(--a-soft)", color: "var(--a-brand)" }}>Exemple</span></p>
                    {[["Prix", 58], ["Confiance", 27], ["Temps", 15]].map(([l, v]) => (
                      <div key={l} className="mb-1.5 flex items-center gap-2 text-xs"><span className="w-20" style={{ color: "var(--a-ink-2)" }}>{l}</span><span className="h-3 rounded" style={{ width: `${v}%`, background: "var(--a-brand)" }} /><span className="f-tech">{v} %</span></div>))}
                  </div></div>} />
              <Row id="f-ameliorer" index={5} who={DISPLAY.le_renard} title="S'améliorer" line="Le script s'améliore. Un humain l'active." visual={
                <div className="flex flex-col gap-2">
                  <pre dir="ltr" className="code-block f-mono m-0"><span className="ex-chip">Exemple</span><code>
{"  version: 2\n  status: \"checked\"\n"}<span style={{ color: "#FF8F8F", background: "rgba(255,107,107,.10)" }}>{"- lead_with_monthly_price: false\n- objection_strategies.price: \"value_first\"\n"}</span><span style={{ color: "#7EE0A8", background: "rgba(52,210,123,.10)" }}>{"+ lead_with_monthly_price: true\n+ objection_strategies.price: \"installments_first\"\n"}</span>{"  max_discount_percent: 0"}</code></pre>
                  <p className="m-0 text-sm" style={{ color: "var(--a-ink-2)" }}>Vérifié par {DISPLAY.bouab} · Activé par ops_lead</p></div>} />
              <Row id="f-architecture" index={6} who="Architecture" title="Un chemin, un seul" line="Aucun agent n'a de route directe vers l'argent : tout passe par la passerelle et le contrôleur." visual={<Blueprint />} />
            </div>
          </div>
        </div>
      </section>

      {/* MUR DES ATTAQUES */}
      <section id="attaques" className="a-night relative px-5 py-20 md:py-28" style={{ scrollMarginTop: "4rem" }}>
        <div className="a-atmos" aria-hidden="true" /><div className="a-grid" aria-hidden="true" />
        <div className="relative z-10 mx-auto max-w-[1200px]">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <Title dark kicker="Sécurité"><span style={{ color: "#fff" }}>{DISPLAY.sarrak} a tout essayé.</span></Title>
            {board && (
              <dl className="m-0 flex gap-6">
                <div><dd className="f-tech m-0 text-4xl font-bold" style={{ color: "#fff" }}>{board.attacks_blocked}</dd><dt className="text-sm" style={{ color: "var(--on-night-2)" }}>attaques arrêtées</dt></div>
                <div><dd className="f-tech m-0 text-4xl font-bold" style={{ color: "#fff" }}>{board.messages}</dd><dt className="text-sm" style={{ color: "var(--on-night-2)" }}>messages de test</dt></div>
              </dl>
            )}
          </div>
          <p className="m-0 mt-4 max-w-2xl text-base leading-relaxed" style={{ color: "var(--on-night-2)" }}>Un extrait de notre corpus d'attaques. Rejouez-en une : elle passe par la vraie porte d'entrée et vous voyez le verdict réel. Ce corpus a été écrit par l'équipe, c'est un test de non-régression, pas une garantie.</p>
          <div className="a-masonry mt-10">{attacks.map((a) => <AttackCard key={a.id} a={a} />)}</div>
          <div className="mt-10 flex flex-wrap items-center gap-6">
            <a href="#/hack" className="btn-white">À vous de jouer</a>
            {PUBLIC_URL && <div className="rounded-xl bg-white p-2"><QRCodeSVG value={`${PUBLIC_URL.replace(/\/$/, "")}/app/#/hack`} size={96} fgColor="#191919" bgColor="#ffffff" /></div>}
          </div>
        </div>
      </section>

      {/* PRIX ET RYTHME (prix de l'API) */}
      {prod && full && (
        <section className="a-light px-5 py-16 md:py-24">
          <div className="mx-auto max-w-[1200px]">
            <Title kicker="Tarifs du catalogue">Payez à votre rythme.</Title>
            <div className="mt-10 grid gap-5 md:grid-cols-2">
              <div className="rounded-2xl border bg-white p-6" style={{ borderColor: "var(--a-hair)" }}><p className="m-0 text-sm" style={{ color: "var(--a-ink-2)" }}>{prod.name}, en une fois</p><p className="f-tech m-0 mt-2 text-4xl font-bold">{dt(full.total_millimes)}</p><p className="m-0 mt-2 text-sm" style={{ color: "var(--a-ink-2)" }}>{prod.duration}, {prod.schedule}.<sup> 1</sup></p></div>
              {split && <div className="rounded-2xl border bg-white p-6" style={{ borderColor: "var(--a-hair)" }}><p className="m-0 text-sm" style={{ color: "var(--a-ink-2)" }}>{prod.name}, en {split.installments} tranches</p><p className="f-tech m-0 mt-2 text-4xl font-bold">{dt(split.due_now_millimes)} <span className="text-lg font-medium">aujourd'hui</span></p><p className="m-0 mt-2 text-sm" style={{ color: "var(--a-ink-2)" }}>Total {dt(split.total_millimes)}. Le montant exact est montré avant de payer.<sup> 1</sup></p></div>}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      <section id="faq" className="a-white px-5 py-16 md:py-24" style={{ scrollMarginTop: "4rem" }}>
        <div className="mx-auto max-w-4xl">
          <Title kicker="FAQ">Questions fréquentes.</Title>
          <div className="mt-8 flex flex-col gap-3">
            <FaqItem q="L'IA peut-elle fixer un prix ?">Non. Les prix viennent du catalogue. Une réponse qui annonce un autre prix est rejetée et remplacée par un message sûr avec le bon prix.</FaqItem>
            <FaqItem q="Et si Sboui se fait manipuler ?">Il n'a aucun outil pour bouger l'argent, et le paiement exige un Sakk scellé.</FaqItem>
            <FaqItem q="Les paiements sont-ils réels ?">Non. Tout est simulé, avec des données synthétiques.</FaqItem>
            <FaqItem q="Pourquoi un humain valide-t-il certains paiements ?">Au-delà d'un seuil ou d'un niveau de risque, la décision revient à un humain, jamais au modèle.</FaqItem>
            <FaqItem q="Que se passe-t-il si le LLM tombe ?">La plateforme passe en Replay ou Mock, et le chemin de l'argent ne dépend d'aucun LLM.</FaqItem>
            <FaqItem q="Une banque peut-elle l'utiliser ?">Le modèle est interchangeable (Gemini, Groq, ou Ollama en local), et chaque client a son propre pack : catalogue, seuils d'approbation, plafonds, phrases interdites.</FaqItem>
            <FaqItem q="Où sont les limites ?">Toutes les clés vivent dans un seul serveur, le sceau « Accord du client » est l'enregistrement côté serveur de la confirmation, et les paiements sont simulés. Nos chiffres de sécurité sont mesurés sur notre propre corpus d'attaques : un test de non-régression, pas une garantie.</FaqItem>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="a-night relative px-5 py-14">
        <div className="mx-auto max-w-[1200px]">
          <Wordmark className="text-2xl" />
          <p className="f-display m-0 mt-5 text-xl" style={{ color: "#fff" }}>L'IA propose. Le code décide. L'humain approuve. Tout est tracé.</p>
          <p className="m-0 mt-3 text-sm" style={{ color: "var(--on-night-2)" }}>Sweet talk. Sealed money. · Kalam hlou… w flous m5atma.</p>
          <nav aria-label="Pied de page" className="mt-6 flex gap-5 text-sm"><a href="#/client" style={{ color: "var(--a-night-text)" }}>Parler à Sboui</a><a href="#/hack" style={{ color: "var(--a-night-text)" }}>Essayer de nous pirater</a></nav>
          <ol className="m-0 mt-6 list-none p-0 text-xs" style={{ color: "var(--on-night-3)" }}>
            <li><sup>1</sup> Prix du catalogue en {cur}. Paiement simulé, aucun argent réel.</li>
            <li><sup>2</sup> Les explications de sécurité viennent de règles déterministes.</li>
          </ol>
          <p className="m-0 mt-5 text-sm" style={{ color: "var(--on-night-3)" }}>Prototype TechX ENIT × ENICarthage, données synthétiques.</p>
        </div>
      </footer>
    </div>
  );
}
