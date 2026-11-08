import { DISPLAY } from "./names.js";

// Identity colours follow the reference categorical order (fixed, never cycled).
export const AGENTS = {
  sahbi: { name: DISPLAY.sahbi, role: "Vente en derja", color: "#3041a2" },
  sandouk: { name: DISPLAY.sandouk, role: "Paiement", color: "#92400e" },
  sandouk_pay: { name: `${DISPLAY.sandouk} Pay`, role: "Moteur de paiement simulé", color: "#92400e" },
  fahem: { name: DISPLAY.fahem, role: "Intelligence client", color: "#0e7490" },
  si_hsab: { name: DISPLAY.si_hsab, role: "Analyste financier", color: "#166534" },
  le_renard: { name: DISPLAY.le_renard, role: "Stratégie", color: "#c2410c" },
  bouab: { name: DISPLAY.bouab, role: "Sécurité et fraude", color: "#b91c1c" },
  sarrak: { name: DISPLAY.sarrak, role: "Red team", color: "#86198f" },
  zbayen: { name: DISPLAY.zbayen, role: "Clients simulés", color: "#8a93a8" },
  orchestrator: { name: DISPLAY.orchestrator, role: "Machine à états", color: "#8a93a8" },
  client: { name: "Client", role: "", color: "#ffffff" },
  human: { name: "Humain", role: "Validation", color: "#6250d6" },
  wazuh: { name: "Wazuh", role: "SIEM", color: "#0e7490" },
  system: { name: "Système", role: "", color: "#8a93a8" },
  dashboard: { name: "Console", role: "", color: "#8a93a8" },
  demo: { name: "Démo", role: "", color: "#8a93a8" },
};

export function who(source) {
  if (!source) return AGENTS.system;
  if (source.startsWith("human:")) {
    const n = source.slice(6);
    return { ...AGENTS.human, name: n.charAt(0).toUpperCase() + n.slice(1) };
  }
  return AGENTS[source] || { name: source, role: "", color: "#8a93a8" };
}
