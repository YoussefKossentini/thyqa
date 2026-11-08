import { useEffect, useRef, useState } from "react";

export function useReducedMotion() {
  const [r, setR] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const m = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!m) return;
    const f = () => setR(m.matches);
    m.addEventListener?.("change", f);
    return () => m.removeEventListener?.("change", f);
  }, []);
  return r;
}

/** Typing line: 40 ms per character, 1.5 s pause between phrases. Static first phrase when motion is reduced. */
export function Typing({ phrases }) {
  const reduce = useReducedMotion();
  const [out, setOut] = useState(reduce ? phrases[0] : "");
  useEffect(() => {
    if (reduce) { setOut(phrases[0]); return; }
    let i = 0, j = 0, t;
    const tick = () => {
      if (j < phrases[i].length) { j += 1; setOut(phrases[i].slice(0, j)); t = setTimeout(tick, 40); }
      else t = setTimeout(() => { i = (i + 1) % phrases.length; j = 0; setOut(""); tick(); }, 1500);
    };
    tick();
    return () => clearTimeout(t);
  }, [reduce]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <span aria-hidden="true"><bdi>{out}</bdi>{!reduce && <span className="a-caret" />}</span>
      <span className="sr-only-a">{phrases.join(". ")}</span>
    </>
  );
}

/** Stencil seal: a circle with a gap. On hover the gap closes. */
export function SealIcon({ size = 28, color = "currentColor", sealed = false }) {
  const r = 16, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <circle className="ring" cx="20" cy="20" r={r} fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={sealed ? `${c} 0` : `${c - 14} 14`} transform="rotate(-70 20 20)" style={{ transition: "stroke-dasharray .5s ease-in-out" }} />
    </svg>
  );
}

export function Json({ data }) {
  const text = JSON.stringify(data, null, 2);
  const parts = [];
  const re = /("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g;
  let last = 0, m, key = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1] && m[2]) { parts.push(<span key={key++} className="k">{m[1]}</span>); parts.push(m[2]); }
    else if (m[1]) parts.push(<span key={key++} className="s">{m[1]}</span>);
    else if (m[3]) parts.push(<span key={key++} className="b">{m[3]}</span>);
    else parts.push(<span key={key++} className="n">{m[4]}</span>);
    last = re.lastIndex;
  }
  parts.push(text.slice(last));
  return <pre dir="ltr" className="code-block f-mono m-0"><span className="ex-chip">Exemple</span><code>{parts}</code></pre>;
}

export function FaqItem({ q, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="faq-item" data-open={open}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{q}</span>
        <svg className="chev" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      <div className="faq-body"><div><p className="m-0 px-5 pb-5 text-base leading-relaxed" style={{ color: "var(--a-ink-2)" }}>{children}</p></div></div>
    </div>
  );
}

/** Scroll-spy: the section nearest the middle of the scroller becomes active. */
export function useScrollSpy(ids, rootRef) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const root = rootRef.current;
    if (!root || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((es) => { es.forEach((e) => { if (e.isIntersecting) setActive(e.target.id); }); }, { root, rootMargin: "-40% 0px -50% 0px" });
    ids.forEach((id) => { const el = root.querySelector(`#${id}`); if (el) io.observe(el); });
    return () => io.disconnect();
  }, [ids.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  return active;
}

export function useInView(ref) {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return seen;
}

export function Radar({ values, labels, size = 260 }) {
  const n = values.length, cx = size / 2, cy = size / 2, R = size / 2 - 44;
  const pt = (i, v) => { const a = (-90 + (360 / n) * i) * Math.PI / 180; return [cx + Math.cos(a) * R * v / 100, cy + Math.sin(a) * R * v / 100]; };
  const poly = values.map((v, i) => pt(i, v).join(",")).join(" ");
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={labels.map((l, i) => `${l} ${values[i]}`).join(", ")}>
      {[25, 50, 75, 100].map((g) => <polygon key={g} points={values.map((_, i) => pt(i, g).join(",")).join(" ")} fill="none" stroke="#3a4260" strokeWidth="1" />)}
      <polygon points={poly} fill="rgba(107,120,242,.35)" stroke="#A5B0FF" strokeWidth="2" />
      {labels.map((l, i) => { const [x, y] = pt(i, 120); return <text key={l} x={x} y={y} fontSize="10" fill="#A9B0CC" textAnchor="middle" dominantBaseline="middle">{l}</text>; })}
    </svg>
  );
}
