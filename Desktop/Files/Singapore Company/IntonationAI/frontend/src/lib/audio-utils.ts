import { NOTE_NAMES } from "./constants";

export function frequencyToNote(hz: number): { name: string; cents: number } {
  const semitone = 12 * Math.log2(hz / 440);
  const rounded = Math.round(semitone);
  const cents = Math.round((semitone - rounded) * 100);
  const noteIndex = ((rounded % 12) + 12) % 12;
  const octave = Math.floor((rounded + 69) / 12);
  return { name: `${NOTE_NAMES[noteIndex]}${octave}`, cents };
}

export function rmsToDb(rms: number): number {
  return 20 * Math.log10(Math.max(rms, 1e-10));
}

export function computeRms(buffer: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    sum += buffer[i] * buffer[i];
  }
  return Math.sqrt(sum / buffer.length);
}

export function floatTo16BitPCM(float32: Float32Array): ArrayBuffer {
  const buf = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}
