export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export const WS_URL = BACKEND_URL.replace(/^http/, "ws");

export const SAMPLE_RATE = 44100;
export const FFT_SIZE = 2048;
export const PITCH_MIN_HZ = 60;
export const PITCH_MAX_HZ = 1500;

export const NOTE_NAMES = [
  "C",
  "C#",
  "D",
  "D#",
  "E",
  "F",
  "F#",
  "G",
  "G#",
  "A",
  "A#",
  "B",
] as const;

export const COACH_LABELS: Record<string, string> = {
  vocal: "Vocal Coach",
  piano: "Piano Coach",
  guitar: "Guitar Coach",
};
