// Record the microphone, return mono 16 kHz WAV as base64. Works in any browser with MediaRecorder,
// no dependency on the browser's own speech service.

export const VOICE_ERRORS = {
  NotAllowedError: "Le micro est bloqué. Cliquez sur le cadenas à côté de l'adresse, autorisez le microphone, puis réessayez.",
  NotFoundError: "Aucun microphone détecté. Branchez-en un ou choisissez-le dans les réglages Windows.",
  NotReadableError: "Le micro est utilisé par une autre application. Fermez-la puis réessayez.",
  SecurityError: "Le micro ne marche que sur localhost ou en HTTPS. Sur un téléphone, écrivez votre message.",
};

export function voiceSupported() {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
}

/** Starts recording. Returns { stop(): Promise<string|null> } ; stop resolves with the WAV base64, or null if too short. */
export async function startRecording(maxMs = 9000, onAutoStop = () => {}) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  const done = new Promise((resolve) => { rec.onstop = resolve; });
  rec.start();
  const timer = setTimeout(() => { if (rec.state === "recording") { rec.stop(); onAutoStop(); } }, maxMs);
  return {
    async stop() {
      clearTimeout(timer);
      if (rec.state === "recording") rec.stop();
      await done;
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      if (blob.size < 1500) return null;
      return toWavBase64(blob);
    },
  };
}

async function toWavBase64(blob) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  await ctx.close();
  const rate = 16000;
  const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  const pcm = (await off.startRendering()).getChannelData(0);
  let peak = 0;
  for (let i = 0; i < pcm.length; i++) peak = Math.max(peak, Math.abs(pcm[i]));
  if (peak < 0.01) return null; // silence
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + pcm.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 0x7fff, true);
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
