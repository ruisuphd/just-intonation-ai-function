function getBackendUrl(): string {
  const url = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (url && (url.startsWith("http://") || url.startsWith("https://")))
    return url;
  if (process.env.NODE_ENV === "development") return "http://localhost:8000";
  throw new Error("NEXT_PUBLIC_BACKEND_URL is required for production. Set it at build time.");
}

export const BACKEND_URL = getBackendUrl();

/** Same value as backend `APP_RELEASE` when set (e.g. git SHA); used in Sentry and telemetry. */
export const APP_RELEASE: string | undefined =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_APP_RELEASE?.trim()
    ? process.env.NEXT_PUBLIC_APP_RELEASE.trim()
    : undefined;

/** Must match backend versioned mount (`/api/v1/*`). */
export const API_PREFIX = "/api/v1";

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
