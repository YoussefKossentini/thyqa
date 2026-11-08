import { dt } from "../lib/format.js";
import { DISPLAY } from "../lib/names.js";

const BASE = import.meta.env.BASE_URL || "/";

export function Logo({ dark = false, className = "h-8" }) {
  return <img src={`${BASE}brand/${dark ? "thyqa-logo-dark" : "thyqa-logo"}.png`} alt="THYQA" className={`${className} w-auto min-w-[96px] select-none`} draggable="false" />;
}

/** One seal of the Sakk: a circle with a stencil gap that closes when the step is sealed. */
export function Seal({ state = "pending", size = 44 }) {
  const r = 18, c = 2 * Math.PI * r, gap = 16;
  const sealed = state === "sealed", bad = state === "rejected", dim = state === "na";
  const color = bad ? "var(--color-crit)" : sealed ? "var(--color-door)" : "var(--color-muted)";
  return (
    <svg width={size} height={size} viewBox="0 0 44 44" aria-hidden="true" style={{ opacity: dim ? 0.35 : 1 }}>
      <circle cx="22" cy="22" r={r} fill={sealed ? "var(--color-door)" : bad ? "var(--color-crit-wash)" : "none"} stroke={color} strokeWidth="4"
        strokeLinecap="butt" strokeDasharray={sealed || bad ? `${c} 0` : `${c - gap} ${gap}`} className="seal-gap" transform="rotate(-70 22 22)" />
      {sealed && <path d="M14 22.5l5.5 5.5L30 16.5" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />}
      {bad && <path d="M16 16l12 12M28 16L16 28" stroke="var(--color-crit)" strokeWidth="3.2" strokeLinecap="round" />}
    </svg>
  );
}

const SEALS = ["Prix du catalogue", "Accord du client", "Contrôle sécurité", "Validation humaine", "Paiement"];
export function SealRow({ states, size = 44 }) {
  const st = states || ["sealed", "sealed", "sealed", "na", "sealed"];
  return (
    <ol className="flex flex-wrap items-start gap-x-5 gap-y-3">
      {SEALS.map((label, i) => (
        <li key={label} className="flex flex-col items-center gap-1.5">
          <Seal state={st[i]} size={size} />
          <span className="text-xs text-ink-2">{label}</span>
        </li>
      ))}
    </ol>
  );
}

export function Badge({ children, tone = "neutral", icon }) {
  const t = {
    neutral: "border-line text-ink-2 bg-surface",
    primary: "border-door/30 text-door-deep bg-door-wash",
    good: "border-good/40 text-good-ink bg-good-wash",
    warn: "border-warn/50 text-warn-ink bg-warn-wash",
    crit: "border-crit/40 text-crit-ink bg-crit-wash",
  }[tone];
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-[0.8rem] font-medium ${t}`}>{icon}{children}</span>;
}

export function PlanCard({ title, amount, line, benefit, footnote, selected = false, onSelect }) {
  return (
    <div role={onSelect ? "radio" : undefined} aria-checked={onSelect ? selected : undefined} tabIndex={onSelect ? 0 : undefined} onClick={onSelect}
      className={`card relative flex flex-col gap-2 p-6 ${selected ? "!border-2 !border-door" : ""}`}>
      <p className="text-sm font-medium text-ink-2">{title}</p>
      <p className="text-4xl font-bold leading-none tracking-tight tabular">{amount}</p>
      {line && <p className="text-base text-ink">{line}</p>}
      {benefit && <p className="text-sm text-ink-2">{benefit}{footnote && <sup className="ml-0.5 text-door">{footnote}</sup>}</p>}
    </div>
  );
}

export function TrustNote({ children }) {
  return (
    <p className="flex items-start gap-3 text-base text-ink">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--color-door)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0" aria-hidden="true">
        <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="M9 12l2 2 4-4" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

/** Pure CSS phone outline, no real device or brand. */
export function PhoneFrame({ children }) {
  return (
    <div className="mx-auto w-[300px] max-w-full rounded-[40px] border-[8px] border-ink bg-surface p-3 shadow-[0_24px_60px_-20px_rgb(11_27_51/.35)] sm:w-[320px]" style={{ aspectRatio: "9 / 19.5" }}>
      <div className="mx-auto mb-3 h-1.5 w-16 rounded-full bg-line" />
      <div className="flex h-[calc(100%-1.5rem)] flex-col gap-2.5 overflow-hidden">{children}</div>
    </div>
  );
}

export function Bubble({ mine, children }) {
  return (
    <div className={`max-w-[88%] rounded-2xl px-3.5 py-2 text-[0.88rem] leading-snug ${mine ? "self-end rounded-br-md bg-door text-white" : "self-start rounded-bl-md border border-line bg-surface text-ink"}`}>
      {children}
    </div>
  );
}

export const money = dt;
