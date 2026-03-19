import { BACKEND_URL } from "./constants";
import { getIdToken } from "./firebase";
import type {
  AudioAnalysis,
  CoachSession,
  WarmupSessionRaw,
  UserProfile,
} from "@/types";
import { mapWarmupSession } from "@/types";

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
    ...init?.headers,
  };
  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  getProfile: () => request<UserProfile>("/api/users/me"),

  updateProfile: (data: { skill_profile?: Record<string, unknown> }) =>
    request<UserProfile>("/api/users/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  sendCoachMessage: async (
    sessionId: string,
    content: string,
    audioBlob?: Blob | null
  ) => {
    const form = new FormData();
    form.append("content", content);
    if (audioBlob) {
      form.append("audio", audioBlob, "recording.webm");
    }
    const headers = await authHeaders();
    const res = await fetch(`${BACKEND_URL}/api/coach/${sessionId}/message`, {
      method: "POST",
      headers: { ...headers },
      body: form,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API ${res.status}: ${body}`);
    }
    const data = await res.json();
    const a = data.analysis;
    const analysis = a
      ? {
          pitchHz: a.pitch_hz,
          noteName: a.note_name,
          centsDev: a.cents_deviation ?? 0,
          rmsDb: a.rms_db ?? 0,
          onsetDetected: a.onset_detected ?? false,
          tempo: a.tempo,
          breathSupportScore: a.breath_support_score,
          vibratoPresent: a.vibrato_present,
          pitchStability: a.pitch_stability,
          rhythmScore: a.rhythm_score,
          chordDetected: a.chord_detected,
          chordConfidence: a.chord_confidence,
          mutedStrings: a.muted_strings ?? [],
          timingOffsetMs: a.timing_offset_ms,
          velocityDb: a.velocity_db,
          accuracyScore: a.accuracy_score,
          timingAccuracy: a.timing_accuracy,
          strummingPattern: a.strumming_pattern,
          barreDetected: a.barre_detected,
        }
      : undefined;
    return {
      reply: data.reply,
      audioUrl: data.audio_url,
      analysis,
    };
  },

  endCoachSession: (sessionId: string) =>
    request<{ recap: string; next_step: string }>(
      `/api/coach/${sessionId}/end`,
      { method: "POST" }
    ),

  startCoachSession: (coachType: string) =>
    request<CoachSession>("/api/coach/sessions", {
      method: "POST",
      body: JSON.stringify({ coach_type: coachType }),
    }),

  getSessionHistory: () => request<CoachSession[]>("/api/sessions"),

  getDashboardStats: () =>
    request<{
      total_sessions: number;
      warmup_sessions: number;
      average_score: number | null;
      practice_streak_days: number;
    }>("/api/dashboard/stats"),

  analyseAudio: async (audioBlob: Blob) => {
    const form = new FormData();
    form.append("audio", audioBlob);
    const token = await getIdToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${BACKEND_URL}/api/audio/analyse`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!res.ok) throw new Error(`Audio analyse failed: ${res.status}`);
    return res.json() as Promise<AudioAnalysis>;
  },

  startWarmup: async () => {
    const raw = await request<WarmupSessionRaw>("/api/warmup/start", {
      method: "POST",
    });
    return mapWarmupSession(raw);
  },

  submitWarmupScore: async (
    sessionId: string,
    exerciseId: string,
    audioBlob: Blob
  ) => {
    const form = new FormData();
    form.append("audio", audioBlob);
    form.append("exercise_id", exerciseId);
    const headers = await authHeaders();
    const res = await fetch(
      `${BACKEND_URL}/api/warmup/${sessionId}/score`,
      {
        method: "POST",
        headers: { ...headers },
        body: form,
      }
    );
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API ${res.status}: ${body}`);
    }
    return res.json() as Promise<{
      score: {
        exercise_id: string;
        pitch_accuracy: number;
        rhythm_accuracy: number;
        overall_score: number;
      };
      commentary: string;
      next_exercise: Record<string, unknown> | null;
    }>;
  },

  createCheckoutSession: (body: {
    plan?: "essential" | "pro" | "monthly" | "yearly";
    interval?: "monthly" | "yearly";
    price_id?: string;
  }) =>
    request<{ url: string }>("/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getEntitlements: () =>
    request<{
      plan: string;
      is_essential: boolean;
      is_pro: boolean;
      remaining_free_sessions: number;
      current_period_end: string | null;
    }>("/api/billing/entitlements"),

  getBackingTrack: (params?: {
    tempo_bpm?: number;
    key?: string;
    style?: string;
    duration_seconds?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.tempo_bpm) sp.set("tempo_bpm", String(params.tempo_bpm));
    if (params?.key) sp.set("key", params.key);
    if (params?.style) sp.set("style", params.style || "metronome");
    if (params?.duration_seconds) sp.set("duration_seconds", String(params.duration_seconds));
    const q = sp.toString();
    return request<{ url: string | null }>(
      `/api/coach/backing-track${q ? `?${q}` : ""}`
    );
  },
};
