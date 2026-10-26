// Microphone capture that hands Saaras a clean 16 kHz mono WAV (its preferred input),
// whatever container the browser's MediaRecorder produces (webm/opus, mp4/aac, ...).

export const MAX_SECONDS = 28;

export class VoiceRecorder {
  constructor({ onLevel, onTick, onAutoStop } = {}) {
    this.onLevel = onLevel || (() => {});
    this.onTick = onTick || (() => {});
    this.onAutoStop = onAutoStop || (() => {});
    this.recording = false;
  }

  static supported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream);
    this.recorder.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.recorder.start(250);
    this.recording = true;
    this.startedAt = performance.now();

    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;
    source.connect(this.analyser);
    const buf = new Uint8Array(this.analyser.fftSize);
    const loop = () => {
      if (!this.recording) return;
      this.analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      this.onLevel(Math.min(1, peak / 64));
      const secs = (performance.now() - this.startedAt) / 1000;
      this.onTick(secs);
      if (secs >= MAX_SECONDS) {
        this.onAutoStop();
        return;
      }
      this.raf = requestAnimationFrame(loop);
    };
    loop();
  }

  async stop() {
    if (!this.recorder) return null;
    this.recording = false;
    cancelAnimationFrame(this.raf);
    const done = new Promise((resolve) => (this.recorder.onstop = resolve));
    if (this.recorder.state !== "inactive") this.recorder.stop();
    await done;
    this.stream.getTracks().forEach((t) => t.stop());
    try { await this.ctx.close(); } catch { /* already closed */ }
    const type = this.recorder.mimeType || "audio/webm";
    const raw = new Blob(this.chunks, { type });
    this.recorder = null;
    try {
      return { blob: await toWav16k(raw), filename: "speech.wav" };
    } catch {
      const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      return { blob: raw, filename: `speech.${ext}` };
    }
  }

  cancel() {
    if (!this.recorder) return;
    this.recording = false;
    cancelAnimationFrame(this.raf);
    try { this.recorder.stop(); } catch { /* ignore */ }
    this.stream.getTracks().forEach((t) => t.stop());
    try { this.ctx.close(); } catch { /* ignore */ }
    this.recorder = null;
  }
}

async function toWav16k(blob) {
  const rate = 16000;
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  ctx.close();
  const frames = Math.max(1, Math.ceil(decoded.duration * rate));
  const offline = new OfflineAudioContext(1, frames, rate);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0), rate);
}

function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (off, s) => [...s].forEach((c, i) => view.setUint8(off + i, c.charCodeAt(0)));
  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (const s of samples) {
    const v = Math.max(-1, Math.min(1, s));
    view.setInt16(off, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    off += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}
