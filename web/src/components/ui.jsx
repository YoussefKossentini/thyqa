import { DECISION } from "../lib/format.js";

export function Button({ children, tone = "plain", className = "", ...props }) {
  const tones = {
    plain: "border-line bg-surface text-ink hover:border-door",
    primary: "border-door bg-door text-white hover:bg-door-deep",
    danger: "border-crit/40 bg-surface text-crit-ink hover:border-crit",
    quiet: "border-transparent bg-transparent text-ink-2 hover:text-ink",
  };
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tones[tone]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Pill({ children, tone = "neutral", title, onDark = false }) {
  const light = {
    neutral: "border-line text-ink-2",
    good: "border-good/40 text-good-ink bg-good-wash",
    warn: "border-warn/60 text-warn-ink bg-warn-wash",
    crit: "border-crit/40 text-crit-ink bg-crit-wash",
    door: "border-door/30 text-door-deep bg-door-wash",
  };
  const dark = {
    neutral: "border-white/20 text-white/80 bg-white/5",
    good: "border-[#5be05b]/40 text-[#b8f5b8] bg-[#5be05b]/10",
    warn: "border-warn/50 text-[#ffe08a] bg-warn/10",
    crit: "border-[#ff8a8a]/50 text-[#ffc2c2] bg-crit/20",
    door: "border-white/30 text-white bg-white/10",
  };
  const tones = onDark ? dark : light;
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[0.8rem] ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** Door glyph + word: a decision is never shown by colour alone. */
export function DecisionMark({ decision, compact = false }) {
  const d = DECISION[decision];
  if (!d) return null;
  const fill = { good: "#0ca30c", warn: "#fab219", crit: "#d03b3b" }[d.tone];
  const text = { good: "text-good-ink", warn: "text-warn-ink", crit: "text-crit-ink" }[d.tone];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 text-xs font-medium ${text}`}>
      <svg width="12" height="16" viewBox="0 0 12 16" aria-hidden="true">
        <path d="M1 16V6a5 5 0 0 1 10 0v10z" fill={decision === "BLOCK" ? fill : "none"} stroke={fill} strokeWidth="1.6" />
        {decision === "ALLOW" && <path d="M1 16V6a5 5 0 0 1 3-4.6V16z" fill={fill} />}
        {decision === "REQUIRE_APPROVAL" && <path d="M1 16V6a5 5 0 0 1 6-4.9V16z" fill={fill} />}
      </svg>
      {!compact && d.word}
    </span>
  );
}

export function Avatar({ agent, size = 30 }) {
  const isClient = agent.color === "#ffffff";
  return (
    <span
      aria-hidden="true"
      className="inline-grid shrink-0 place-items-center rounded-full font-semibold"
      style={{ width: size, height: size, background: agent.color, color: isClient ? "#191919" : "#fff",
        border: isClient ? "1.5px solid #191919" : "none", fontSize: size * 0.4 }}
    >
      {agent.name.slice(0, 1)}
    </span>
  );
}

export function SectionTitle({ children, aside }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-lg font-semibold text-ink">{children}</h2>
      {aside && <div className="text-xs text-muted">{aside}</div>}
    </div>
  );
}

export function Empty({ children }) {
  return <p className="text-sm leading-relaxed text-muted">{children}</p>;
}
