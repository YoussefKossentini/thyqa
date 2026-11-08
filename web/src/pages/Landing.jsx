import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "../lib/api.js";
import { dt } from "../lib/format.js";
import { DISPLAY } from "../lib/names.js";
import { Badge, Bubble, Logo, PhoneFrame, PlanCard, SealRow, TrustNote } from "../components/brand.jsx";

const TEAM = [
  [DISPLAY.sahbi, "Discute avec le client en derja et propose une formation", "IA", "Ne touche jamais à l'argent."],
  [DISPLAY.fahem, "Repère ce que le client veut et ce qui le freine", "IA", "Ne fixe jamais un prix."],
  [DISPLAY.sandouk, "Prépare le paiement une fois le client d'accord", "Règles", "Ne peut pas payer sans le feu vert de la sécurité."],
  [DISPLAY.si_hsab, "Compte les ventes et les revenus", "Règles", "Ne fait que lire les chiffres."],
  [DISPLAY.le_renard, "Cherche pourquoi des clients partent et propose un meilleur script", "Règles", "Ne peut pas activer un script seul."],
  [DISPLAY.bouab, "Contrôle chaque paiement avant qu'il parte", "Règles + détection", "Ne se laisse pas convaincre par un message."],
  [DISPLAY.sarrak, "Attaque l'équipe pour vérifier qu'elle tient", "Règles", "Ne touche jamais aux vraies données."],
];
const STEPS = [
  ["Le client écrit", "Il pose ses questions en derja, en français ou en anglais. Sboui répond et propose une formation, au prix du catalogue."],
  ["Le paiement est contrôlé", "Avant chaque paiement, Fouchika vérifie le montant, l'accord du client et le risque. Au-dessus du seuil, un humain doit valider."],
  ["L'équipe apprend", "THYQA repère pourquoi des clients partent et propose un meilleur script. Un humain l'active, jamais l'IA."],
];
const TRUST = [
  "Un message piégé est arrêté avant d'atteindre l'agent.",
  "Le prix vient toujours du catalogue, jamais de l'IA.",
  "Un gros paiement attend la validation d'une personne.",
  "Chaque décision est notée dans un journal qu'on ne peut pas modifier en cachette.",
];
const PUBLIC_URL = import.meta.env.VITE_PUBLIC_URL;

function Section({ id, tint, dark, children }) {
  return (
    <section id={id} data-world={dark ? "ops" : undefined} className={`${dark ? "bg-wall text-ink" : tint ? "bg-wall" : "bg-surface"} px-5 py-16 md:py-28`}>
      <div className="mx-auto max-w-[1200px]">{children}</div>
    </section>
  );
}
const H2 = ({ children }) => <h2 className="max-w-3xl text-[1.9rem] font-bold leading-tight tracking-tight md:text-[2.5rem]">{children}</h2>;

export default function Landing() {
  const [catalog, setCatalog] = useState(null);
  const [cur, setCur] = useState("TND");
  const [threshold, setThreshold] = useState("");
  useEffect(() => {
    api("/api/v1/tenants").then((d) => {
      const t = d.tenants.find((x) => x.tenant_id === d.active) || d.tenants[0];
      setCatalog(t?.catalog || []); setCur(t?.currency || "TND"); setThreshold((t?.approval_threshold || "").replace(/,/g, "\u202f").replace("TND", "DT"));
    }).catch(() => setCatalog([]));
  }, []);
  const prod = catalog?.[0];
  const full = prod?.plans.find((p) => p.installments === 1);
  const split = [...(prod?.plans || [])].reverse().find((p) => p.installments > 1);

  return (
    <div className="h-full overflow-y-auto bg-surface">
      <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-line bg-surface/95 px-5 py-3 backdrop-blur">
        <a href="#/" aria-label="THYQA, accueil" className="flex items-center gap-2 no-underline"><Logo className="h-8" /><span className="font-kufi text-xl text-door">ثقة</span></a>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden sm:inline-flex"><Badge tone="primary">Paiement SIMULÉ</Badge></span>
          <a href="#/client" className="pill-btn primary">Parler à Sboui</a>
        </div>
      </header>

      <Section>
        <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rise">
            <h1 className="display">Vendez en derja.<br />Encaissez en confiance.</h1>
            <p className="accent-line mt-4 text-2xl md:text-3xl">kalam hlou, flous m5atma.</p>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2 md:text-xl">THYQA est une équipe d'agents IA pour les centres de formation. Elle répond à vos clients en derja, leur propose la bonne formation et encaisse le paiement, avec un contrôle de sécurité à chaque étape.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#/client" className="pill-btn primary lg">Parler à Sboui</a>
              <a href="#/hack" className="pill-btn secondary lg">Essayer de nous pirater</a>
            </div>
            <div className="mt-8 flex flex-wrap gap-2">
              <Badge>Démonstration : aucun argent réel</Badge>
            </div>
          </div>
          <PhoneFrame>
            <Bubble mine>9adeh soum {prod?.name || "el formation"}?</Bubble>
            <Bubble>Ena Sboui, agent IA mta3 9antra. {prod ? `${prod.name} : ${prod.duration}, ${(prod.highlights || []).slice(0, 2).join(" w ")}.` : "Chnowa t7eb ta3ref?"}</Bubble>
            <Bubble mine>behi, nheb nsajjel</Bubble>
            {prod && full && (
              <div className="self-start rounded-2xl border-2 border-door bg-surface p-3 text-sm">
                <p className="text-xs text-ink-2">Offre, prix du catalogue</p>
                <p className="font-semibold">{prod.name}</p>
                <p className="text-2xl font-bold text-door-deep">{dt(full.total_millimes)}</p>
                <p className="mt-1 rounded-full bg-door px-3 py-1.5 text-center text-xs font-semibold text-white">Confirmer (test)</p>
              </div>
            )}
          </PhoneFrame>
        </div>
      </Section>

      <Section tint>
        <H2>Comment ça marche.</H2>
        <ol className="mt-10 grid gap-5 md:grid-cols-3">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="card flex flex-col gap-3 p-6">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-door text-base font-bold text-white">{i + 1}</span>
              <p className="text-xl font-bold">{title}</p>
              <p className="text-base leading-relaxed text-ink-2">{i === 1 && threshold ? `${body} Le seuil actuel est de ${threshold}.` : body}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section>
        <H2>Payez à votre rythme.</H2>
        <p className="accent-line mt-3 text-xl">flous 3la 9ad ra7tek.</p>
        {prod && full ? (
          <div className="mt-10 grid gap-5 md:grid-cols-2">
            <PlanCard title={`${prod.name}, en une fois`} amount={dt(full.total_millimes)} line="Un seul paiement" benefit={`${prod.duration}, ${prod.schedule}.`} footnote="1" />
            {split && <PlanCard title={`${prod.name}, en ${split.installments} tranches`} amount={`${dt(split.due_now_millimes)} aujourd'hui`} line={`Total ${dt(split.total_millimes)}`} benefit="Le montant exact est montré avant de payer." footnote="1" />}
          </div>
        ) : <p className="mt-10 text-ink-2">Chargement du catalogue…</p>}
        <a href="#/client" className="pill-btn primary lg mt-10">Choisir ma formation</a>
      </Section>

      <Section tint>
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <H2>Chaque paiement passe 5 contrôles.</H2>
            <ul className="mt-6 space-y-3 text-lg text-ink">
              <li>Le prix vient du catalogue, jamais de l'IA.</li>
              <li>Vous confirmez le montant exact.</li>
              <li>Fouchika vérifie, et un humain valide si le montant est élevé.</li>
            </ul>
            <p className="accent-line mt-6 text-xl">Un agent peut se tromper. Un paiement contrôlé, non.</p>
          </div>
          <div className="card p-8">
            <SealRow size={64} />
            <p className="mt-5 text-sm text-ink-2">Chaque rond doit se fermer avant que le paiement parte. Un rond rouge arrête tout.</p>
          </div>
        </div>
      </Section>

      <Section tint>
        <H2>Qui fait quoi.</H2>
        <p className="mt-3 max-w-2xl text-base text-ink-2">Sept agents, chacun avec un rôle précis. « IA » veut dire qu'un modèle de langage écrit ou analyse. « Règles » veut dire du code classique, sans IA.</p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TEAM.map(([name, role, kind, never]) => (
            <div key={name} className="card flex flex-col gap-2 p-5">
              <div className="flex items-center justify-between gap-2"><p className="text-xl font-bold">{name}</p><Badge tone="primary">{kind}</Badge></div>
              <p className="text-base text-ink">{role}</p>
              <p className="text-sm text-ink-2">{never}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <H2>La sécurité, en clair.</H2>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">{TRUST.map((t) => <TrustNote key={t}>{t}</TrustNote>)}</div>
        <a href="#/hack" className="pill-btn secondary lg mt-10">Tester la sécurité</a>
      </Section>

      <Section dark>
        <div className="grid items-center gap-10 md:grid-cols-[1fr_auto]">
          <div>
            <h2 className="display !text-[2.4rem] md:!text-[3.2rem]">Essayez de nous pirater.</h2>
            <p className="accent-line mt-3 text-xl">Béji Matrix a essayé. Fouchika a dit non.</p>
            <p className="mt-4 max-w-xl text-base text-ink-2">Écrivez un message pour tromper l'agent : une remise de 100 %, un paiement sans accord, ses instructions secrètes. La sécurité regarde et bloque.</p>
            <a href="#/hack" className="pill-btn primary lg mt-8">Lancer une attaque</a>
          </div>
          {PUBLIC_URL && <div className="rounded-2xl bg-white p-3"><QRCodeSVG value={`${PUBLIC_URL.replace(/\/$/, "")}/app/#/hack`} size={160} fgColor="#191919" bgColor="#ffffff" /></div>}
        </div>
      </Section>

      <footer className="bg-surface px-5 py-12">
        <div className="mx-auto max-w-[1200px]">
          <p className="text-lg font-semibold">L'IA propose. Le code décide. L'humain approuve. Tout est tracé.</p>
          <ol className="mt-6 text-xs text-muted"><li><sup>1</sup> Prix illustratifs en {cur}. Paiement simulé, aucun argent réel.</li></ol>
          <p className="mt-6 text-sm text-ink-2">Prototype TechX ENIT × ENICarthage, données synthétiques.</p>
        </div>
      </footer>
    </div>
  );
}
