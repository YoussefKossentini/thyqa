import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, wsUrl } from "./api.js";

export const OpsContext = createContext(null);
export const useOps = () => useContext(OpsContext);

const MAX_EVENTS = 400;

/** Live state for the ops screens: tenant, event stream, KPIs, security status. */
export function useOpsState() {
  const [tenants, setTenants] = useState([]);
  const [tenant, setTenantState] = useState(null);
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [kpis, setKpis] = useState(null);
  const [status, setStatus] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [lastDecision, setLastDecision] = useState(null);
  const wsRef = useRef(null);
  const seen = useRef(new Set());
  const timer = useRef(null);

  const refresh = useCallback(async (tid) => {
    const t = tid || tenant;
    if (!t) return;
    const [k, a] = await Promise.all([
      api(`/api/v1/kpis?tenant_id=${t}`).catch(() => null),
      api(`/api/v1/approvals?tenant_id=${t}&status=pending`).catch(() => []),
    ]);
    if (k) setKpis(k);
    setApprovals(a);
  }, [tenant]);

  const refreshStatus = useCallback(async () => {
    setStatus(await api("/api/v1/security/status").catch(() => null));
  }, []);

  useEffect(() => {
    api("/api/v1/tenants").then((t) => { setTenants(t.tenants); setTenantState(t.active); }).catch(() => {});
    refreshStatus();
    const id = setInterval(refreshStatus, 15000);
    return () => clearInterval(id);
  }, [refreshStatus]);

  useEffect(() => {
    if (!tenant) return undefined;
    let stop = false;
    let retry = 800;
    seen.current = new Set();
    setEvents([]);
    refresh(tenant);
    const connect = () => {
      const ws = new WebSocket(wsUrl(`/ws/events?tenant_id=${tenant}`));
      wsRef.current = ws;
      ws.onopen = () => { setConnected(true); retry = 800; };
      ws.onmessage = (m) => {
        const ev = JSON.parse(m.data);
        if (seen.current.has(ev.event_id)) return;
        seen.current.add(ev.event_id);
        setEvents((prev) => [ev, ...prev].slice(0, MAX_EVENTS));
        if (ev.decision && ["bouab.decision", "bouab.tool_denied", "guard.input_flagged", "guard.output_rewritten",
          "payment.engine_rejected", "approval.refused", "approval.granted"].includes(ev.type)) {
          setLastDecision(ev);
        }
        if (["payment.created", "payment.updated", "case.state_changed", "kpi.updated", "approval.requested",
          "approval.granted", "approval.rejected", "guard.input_flagged", "bouab.tool_denied", "run.finished"].includes(ev.type)) {
          clearTimeout(timer.current);
          timer.current = setTimeout(() => refresh(tenant), 350);
        }
        if (["siem.status", "policy.tampered", "agent.quarantined", "agent.released"].includes(ev.type)) refreshStatus();
      };
      ws.onclose = () => {
        setConnected(false);
        if (!stop) setTimeout(connect, (retry = Math.min(retry * 1.6, 6000)));
      };
    };
    connect();
    return () => { stop = true; wsRef.current?.close(); clearTimeout(timer.current); };
  }, [tenant]); // eslint-disable-line react-hooks/exhaustive-deps

  const setTenant = useCallback(async (tid) => {
    await api("/api/v1/tenants/active", { body: { tenant_id: tid }, pin: true });
    setTenantState(tid);
    setLastDecision(null);
  }, []);

  return { tenants, tenant, setTenant, events, connected, kpis, status, approvals, lastDecision, refresh, refreshStatus };
}
