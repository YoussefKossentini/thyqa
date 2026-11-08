// Thin client for the Thiqa API (docs/API.md). Same origin when served by FastAPI at /app.
const BASE = import.meta.env.VITE_API_BASE || "";
let PIN = "";
try { PIN = sessionStorage.getItem("thiqa_pin") || ""; } catch { /* storage may be blocked */ }

export function getPin() { return PIN; }
export function setPin(pin) {
  PIN = pin;
  try { sessionStorage.setItem("thiqa_pin", pin); } catch { /* ignore */ }
}

export async function api(path, { method, body, pin = false, headers = {} } = {}) {
  const h = { "content-type": "application/json", ...headers };
  if (pin) h["X-Ops-Pin"] = PIN;
  const res = await fetch(BASE + path, {
    method: method || (body !== undefined ? "POST" : "GET"),
    headers: h,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === "string" ? d : d?.message || d?.refusal || res.statusText;
    const err = new Error(res.status === 401 ? "Code PIN ops manquant ou faux." : msg);
    err.status = res.status;
    err.detail = d;
    throw err;
  }
  return data;
}

export function wsUrl(path) {
  const base = BASE || window.location.origin;
  return base.replace(/^http/, "ws") + path;
}
