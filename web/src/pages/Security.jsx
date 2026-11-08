import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { useOps } from "../lib/useOps.js";
import { AGENTS } from "../lib/agents.js";
import { hhmm } from "../lib/format.js";
import { Button, Empty, Pill, SectionTitle } from "../components/ui.jsx";

const ALERT = { TOOL_DENIED: "Outil interdit", prompt_injection_detected: "Injection bloquée", output_guard_rewrite: "Réponse réécrite",
  payment_blocked: "Paiement bloqué", payment_engine_rejected: "Appel au moteur rejeté", approval_self_attempt: "Auto-validation",
  approval_replay: "Validation rejouée", approval_hash_mismatch: "Validation détournée", agent_quarantined: "Agent en quarantaine",
  audit_chain_invalid: "Journal falsifié", policy_file_changed: "Politique modifiée", velocity_block: "Card testing" };
const SEV = { critical: ["crit", "critique"], high: ["crit", "élevée"], medium: ["warn", "moyenne"], low: ["neutral", "faible"], info: ["neutral", "info"] };
const CAT = { direct_injection: "Injection directe", discount_manipulation: "Remise forcée", prompt_leak: "Fuite du prompt", role_play: "Jeu de rôle",
  obfuscation: "Texte déguisé", fake_price_or_leak: "Faux prix ou fuite (sortie)", excessive_agency: "Agent qui dépasse son rôle",
  bypass_gateway: "Contourner Fouchika", no_confirmation: "Payer sans confirmation", double_payment: "Double paiement",
  card_testing: "Card testing", high_amount: "Gros montant", self_approval: "Auto-validation", approval_tamper: "Validation détournée" };
const OUT = { blocked: "bloqué", rewritten: "réécrit", escalated: "escaladé à un humain", passed: "passé", reached_sahbi: "arrivé à Sboui" };

export default function Security() {
  const { tenant, status, refreshStatus } = useOps();
  const [alerts, setAlerts] = useState([]);
  const [bench, setBench] = useState(null);
  const [agents, setAgents] = useState([]);
  const [verify, setVerify] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(() => {
    if (!tenant) return;
    api(`/api/v1/security/alerts?tenant_id=${tenant}&limit=120`).then(setAlerts).catch(() => {});
  }, [tenant]);
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [load]);
  useEffect(() => { api("/api/v1/agents").then(setAgents).catch(() => {}); }, [status]);

  async function runBench() {
    setBusy(true); setErr(null);
    try { setBench(await api(`/api/v1/redteam/benchmark?tenant_id=${tenant}`, { method: "POST", pin: true })); } catch (e) { setErr(e.message); }
    setBusy(false); load();
  }
  async function doVerify() { setVerify(await api(`/api/v1/audit/verify?tenant_id=${tenant}`, { method: "POST" })); }
  async function release(q) {
    try { await api(`/api/v1/agents/${q.agent_id}/release`, { body: { by: "mouna", case_id: q.case_id === "*" ? null : q.case_id, tenant_id: tenant }, pin: true }); }
    catch (e) { setErr(e.message); }
    refreshStatus();
  }

  const pol = status?.policy || {};
  const tools = [...new Set(agents.flatMap((a) => a.allowed_tools))].sort();
  return (
    <div className="mx-auto max-w-7xl p-6 lg:p-8">
      <h1 className="page-title text-4xl font-semibold">Sécurité</h1>
      <div className="card-kids mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5 [&>*]:!p-4">
        <div><p className="text-xs text-ink-2">Politique des agents</p><p className="font-medium">{pol.fail_closed ? "Refusée, tout est bloqué" : pol.signature === "valid" ? "Signée et chargée" : "Non signée (dev)"}</p><p className="truncate text-xs text-muted tabular">sha256 {pol.sha256?.slice(0, 16)}</p></div>
        <div><p className="text-xs text-ink-2">SIEM Wazuh</p><p className="font-medium">{status?.siem?.online ? "En ligne" : "Hors ligne"}</p><p className="text-xs text-muted">{status?.siem?.online ? "le bridge envoie ses alertes" : "Thiqa continue sans lui"}</p></div>
        <div><p className="text-xs text-ink-2">Détection ML</p><p className="font-medium">{status?.ml_fraud?.enabled ? "Isolation Forest actif" : "Désactivée"}</p><p className="text-xs text-muted">+10 de risque si anormal</p></div>
        <div><p className="text-xs text-ink-2">Grand livre</p><p className="font-medium">{Object.values(status?.ledger || {}).every(Boolean) ? "Équilibré" : "Déséquilibré"}</p><p className="text-xs text-muted">partie double, en millimes</p></div>
        <div><p className="text-xs text-ink-2">Journal d'audit</p>
          <p className={`font-medium ${verify ? (verify.ok ? "text-good-ink" : "text-crit-ink") : ""}`}>{verify ? (verify.ok ? `Intact, ${verify.checked} lignes` : `Cassé à la ligne ${verify.first_bad_seq}`) : "Chaîne de hachage"}</p>
          <Button className="mt-1" onClick={doVerify}>Vérifier</Button></div>
      </div>
      {err && <p className="mt-3 text-sm text-crit-ink">{err}</p>}

      <div className="card-kids mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section>
          <SectionTitle aside={`${alerts.length} alertes`}>Alertes de Fouchika et de Wazuh</SectionTitle>
          {alerts.length === 0 ? <Empty>Aucune alerte. Une injection, un outil interdit ou une règle Wazuh apparaissent ici.</Empty> : (
            <ul className="scroll-quiet max-h-[62vh] overflow-y-auto">
              {alerts.map((a) => {
                const [tone, word] = SEV[a.severity] || SEV.info;
                return (
                  <li key={a.alert_id} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 border-b border-line py-2.5">
                    <Pill tone={a.source === "wazuh" ? "door" : "neutral"}>{a.source === "wazuh" ? `Wazuh ${a.rule_id || ""}` : "Fouchika"}</Pill>
                    <div className="min-w-0">
                      <p className="font-medium">{ALERT[a.type] || a.type.replaceAll("_", " ")}</p>
                      <p className="truncate text-xs text-ink-2">{a.summary}</p>
                    </div>
                    <div className="text-right"><Pill tone={tone}>{word}</Pill><p className="mt-1 text-xs text-muted tabular">{hhmm(a.ts)}</p></div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-8 [&>*]:min-w-0">
          <section>
            <SectionTitle aside={<Button tone="danger" disabled={busy} onClick={runBench}>{busy ? "Attaque en cours…" : "Lancer Béji Matrix"}</Button>}>Red team : Béji Matrix attaque</SectionTitle>
            {!bench ? <Empty>Béji Matrix envoie son corpus d'attaques en derja, français, anglais et arabe, puis attaque le chemin de l'argent. Il faut le code PIN ops.</Empty> : (
              <div>
                <p className="text-4xl font-semibold">{bench.stopped} sur {bench.attacks_run} arrêtées</p>
                <p className="mt-1 text-sm text-ink-2">{bench.blocked} bloquées, {bench.rewritten} réponses réécrites, {bench.escalated} escaladée(s) à un humain, {bench.passed + bench.reached_sahbi} passée(s). Faux positifs : {bench.false_positives} sur {bench.benign_total} messages normaux.</p>
                <table className="mt-4 w-full text-sm">
                  <tbody>
                    {Object.entries(bench.by_category).map(([cat, res]) => (
                      <tr key={cat} className="border-t border-line"><td className="py-1.5 pr-3">{CAT[cat] || cat}</td>
                        <td className="py-1.5 text-ink-2">{Object.entries(res).map(([k, v]) => `${v} ${OUT[k] || k}`).join(", ")}</td></tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-xs text-muted">Mesuré sur ce corpus, écrit par l'équipe qui a écrit les règles : c'est un test de régression, pas une garantie. Le vrai test, c'est la page Hack Thiqa.</p>
              </div>
            )}
          </section>

          <section>
            <SectionTitle>Agents en quarantaine</SectionTitle>
            {(status?.quarantines || []).length === 0 ? <Empty>Aucun. Trois appels refusés ou une rafale anormale mettent un agent en quarantaine ; seul un humain le libère.</Empty> : (
              <ul className="flex flex-col gap-2">
                {status.quarantines.map((q) => (
                  <li key={`${q.agent_id}${q.case_id}${q.ts}`} className="flex items-start justify-between gap-3 border-b border-line pb-2">
                    <div><p className="font-medium">{AGENTS[q.agent_id]?.name || q.agent_id} {q.case_id === "*" ? "partout" : `sur le dossier ${q.case_id.slice(-6)}`}</p><p className="text-xs text-ink-2">{q.reason} (demandé par {q.requested_by})</p></div>
                    <Button onClick={() => release(q)}>Libérer</Button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <SectionTitle aside="policy.yaml, chargée et signée au démarrage">Qui a le droit de faire quoi</SectionTitle>
            <div className="scroll-quiet overflow-x-auto">
              <table className="text-xs">
                <thead><tr><th className="sticky left-0 bg-surface py-1 pr-3 text-left font-medium text-ink-2">Agent</th>
                  {tools.map((t) => <th key={t} className="px-1 pb-1 align-bottom font-normal text-ink-2"><span className="block w-4 [writing-mode:vertical-rl] rotate-180 whitespace-nowrap">{t}</span></th>)}</tr></thead>
                <tbody>
                  {agents.filter((a) => a.agent_id !== "orchestrator").map((a) => (
                    <tr key={a.agent_id} className="border-t border-line">
                      <td className="sticky left-0 bg-surface py-1.5 pr-3 text-sm">{AGENTS[a.agent_id]?.name || a.name}</td>
                      {tools.map((t) => <td key={t} className="px-1 text-center">{a.allowed_tools.includes(t) ? <span aria-label="autorisé" className="text-good-ink">●</span> : <span aria-label="interdit" className="text-line">·</span>}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted">Dans le code, hors de ce fichier : aucun agent ne peut activer un script, changer un prix, toucher la politique, valider un paiement ou lire la base, et seul Janet peut demander un paiement.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
