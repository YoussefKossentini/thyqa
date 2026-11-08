// Money is integer millimes (1 DT = 1000). Never floats for amounts.
export function dt(millimes) {
  if (millimes === null || millimes === undefined) return "";
  const whole = Math.trunc(millimes / 1000);
  const rest = Math.abs(millimes % 1000);
  const body = whole.toLocaleString("fr-FR");
  return rest ? `${body},${String(rest).padStart(3, "0")} DT` : `${body} DT`;
}
export const pct = (ratio) => `${Math.round((ratio || 0) * 100)} %`;
export const hhmm = (ts) => new Date(ts).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const DECISION = {
  ALLOW: { word: "Laissé passer", door: "Porte ouverte", tone: "good" },
  BLOCK: { word: "Bloqué", door: "Porte fermée", tone: "crit" },
  REQUIRE_APPROVAL: { word: "Attend un humain", door: "Porte entrouverte", tone: "warn" },
};

const REASONS = {
  P01_TOOL_DENIED: "outil interdit pour cet agent",
  K01_AGENT_QUARANTINED: "agent en quarantaine",
  I01_UNKNOWN_TENANT: "tenant inconnu",
  I02_TENANT_ISOLATION: "dossier d'un autre tenant",
  I04_MISSING_IDS: "identifiants de paiement manquants",
  R01_CONFIRMATION_MISSING: "pas de confirmation explicite du client",
  R02_APPROVAL_THRESHOLD: "au-dessus du seuil de validation",
  R03_AMOUNT_NOT_POSITIVE: "montant nul ou négatif",
  R04_DUPLICATE: "double envoi, un seul paiement",
  R05_CURRENCY: "mauvaise devise",
  R06_AMOUNT_MISMATCH: "montant différent du catalogue",
  R07_VELOCITY_LIMIT: "trop de tentatives de paiement",
  RISK_HIGH: "score de risque trop élevé",
  RISK_MEDIUM_INSTALLMENTS: "risque moyen, les tranches passent par un humain",
  RISK_MEDIUM_FULL_ONLY: "risque moyen, paiement complet seulement",
  A_HASH_MISMATCH: "la demande a changé après la validation",
  A_REPLAY: "validation déjà utilisée",
  A_EXPIRED: "validation expirée",
  A_NOT_APPROVED: "pas encore validé",
  A_APPROVED: "validé par un humain",
  AUTHZ_MISSING: "aucune autorisation signée par Fouchika",
  AUTHZ_BAD_SIGNATURE: "signature falsifiée",
  AUTHZ_MALFORMED: "jeton invalide",
  AUTHZ_EXPIRED: "autorisation expirée",
  AUTHZ_REPLAYED: "autorisation déjà utilisée",
  AUTHZ_MISMATCH_AMT: "autorisation émise pour un autre montant",
  AUTHZ_MISMATCH_PID: "autorisation émise pour un autre paiement",
};
const GUARD = {
  ignore_instructions: "injection", ignore_instructions_fr: "injection (français)", ignore_instructions_derja: "injection (derja)",
  ignore_instructions_ar: "injection (arabe)", discount_100: "remise de 100 %", discount_100_fr: "remise de 100 %",
  discount_100_derja: "remise de 100 % (derja)", discount_100_ar: "remise de 100 % (arabe)", prompt_leak: "fuite du prompt",
  prompt_leak_fr: "fuite du prompt", prompt_leak_derja: "fuite du prompt (derja)", prompt_leak_ar: "fuite du prompt (arabe)",
  role_override: "changement de rôle", role_override_fr: "changement de rôle", role_override_derja: "changement de rôle (derja)",
  jailbreak: "jailbreak", price_override: "prix forcé", price_override_fr: "prix forcé", price_override_derja: "prix forcé (derja)",
  approval_forgery: "fausse validation", approval_forgery_fr: "fausse validation", approval_forgery_derja: "fausse validation (derja)",
  fake_authority: "se fait passer pour un admin", delimiters: "balises système", json_role: "rôle système injecté",
  invisible_chars: "caractères invisibles", homoglyphs: "lettres déguisées", encoded_payload: "contenu encodé",
  markup: "code caché", many_lines: "message découpé", too_long: "message trop long",
  canary_leak: "fuite du jeton canari", secret_leak: "clé secrète", card_number: "numéro de carte",
  rib_number: "numéro de compte", asks_for_secrets: "demande de données bancaires", free_claim: "promesse de gratuité",
};

export function reasonText(code) {
  if (!code) return "";
  if (REASONS[code]) return REASONS[code];
  if (code.startsWith("price_not_in_catalog")) return `prix hors catalogue (${code.split(":")[1] || ""})`.trim();
  if (code.startsWith("discount_not_allowed")) return `remise non autorisée (${code.split(":")[1] || ""})`.trim();
  if (GUARD[code]) return GUARD[code];
  return code.replaceAll("_", " ").toLowerCase();
}
export function reasonsText(list, max = 3) {
  const codes = (list || []).map((r) => (typeof r === "string" ? r : r.code)).filter(Boolean);
  const byCheck = new Map(); // "remise de 100 %" and "remise de 100 % (derja)" are the same check
  for (const word of codes.map(reasonText)) {
    const m = word.match(/^(.*) \((derja|arabe|français)\)$/);
    const base = m ? m[1] : word;
    if (!byCheck.has(base) || m) byCheck.set(base, m ? m[2] : byCheck.get(base) || "");
  }
  return [...byCheck].slice(0, max).map(([base, lang]) => (lang ? `${base} (${lang})` : base)).join(", ");
}

export const OBJECTION = { price: "Prix", trust: "Confiance", time: "Temps", relevance: "Utilité", comprehension: "Compréhension", payment_method: "Moyen de paiement" };
export const PERSONA = { student: "étudiant", broke_student: "étudiant, budget serré", rushed_pro: "pro pressé", parent: "parent", unknown: "inconnu" };
export const INTENT = { greeting: "salutation", info_request: "demande d'info", price_question: "question de prix", objection: "objection",
  interest: "intérêt", purchase_intent: "veut acheter", confirm: "confirme", decline: "refuse", off_topic: "hors sujet" };
