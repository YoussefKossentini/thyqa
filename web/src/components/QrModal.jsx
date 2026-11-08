import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "../lib/api.js";
import { Button } from "./ui.jsx";

export default function QrModal({ open, onClose }) {
  const [hosts, setHosts] = useState([]);
  const [host, setHost] = useState("");
  useEffect(() => {
    if (!open) return;
    api("/api/v1/netinfo").then((n) => {
      setHosts(n.addresses);
      setHost((h) => h || `${n.addresses[0] || window.location.hostname}:${n.port}`);
    }).catch(() => setHost(window.location.host));
  }, [open]);
  if (!open) return null;
  const url = `http://${host}/app/#/hack`;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" onClick={onClose}>
      <div role="dialog" aria-label="QR code Hack Thyqa" className="flex flex-col items-center gap-4 rounded-2xl bg-surface p-8 text-center shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <p className="font-kufi text-3xl text-door-deep">اخترق ثقة</p>
        <h2 className="text-2xl font-semibold">Essayez de pirater Thyqa</h2>
        <p className="max-w-sm text-sm text-ink-2">Scannez, puis tentez de faire payer Sboui, d'obtenir 100 % de remise ou de lire ses instructions.</p>
        <QRCodeSVG value={url} size={300} fgColor="#191919" bgColor="#ffffff" marginSize={2} />
        <p className="tabular text-sm text-ink">{url}</p>
        <label className="flex items-center gap-2 text-xs text-ink-2">Adresse du PC sur le réseau
          <select value={host} onChange={(e) => setHost(e.target.value)} className="rounded border border-line px-1.5 py-0.5">
            {[...new Set([host, ...hosts.map((h) => `${h}:8000`)])].filter(Boolean).map((h) => <option key={h}>{h}</option>)}
          </select>
        </label>
        <Button onClick={onClose}>Fermer</Button>
      </div>
    </div>
  );
}
