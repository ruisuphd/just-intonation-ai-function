import * as Sentry from "@sentry/react";
import { API_PREFIX, APP_RELEASE, BACKEND_URL } from "./constants";
import {
  mergeApiHeaders,
  parseApiErrorBody,
  readRequestIdFromResponse,
  ApiError,
} from "./api-error";
import { getAppCheckTokenForApi, getIdToken } from "./firebase";

export { ApiError } from "./api-error";

function withTelemetryContext(properties: Record<string, unknown>): Record<string, unknown> {
  const merged = { ...properties };
  if (APP_RELEASE) merged.app_release = APP_RELEASE;
  const pv =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_COACH_PROMPT_VERSION?.trim()
      ? process.env.NEXT_PUBLIC_COACH_PROMPT_VERSION.trim()
      : undefined;
  if (pv) merged.coach_prompt_version = pv;
  return merged;
}
import type {
  AudioAnalysis,
  CoachSessionRaw,
  CoachType,
  WarmupSessionRaw,
  UserProfile,
} from "@/types";
import { mapCoachSession, mapWarmupSession } from "@/types";

/** Bearer + optional ``X-Firebase-AppCheck`` for Cloud Run when App Check is configured. */
export async function backendAuthHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const ac = await getAppCheckTokenForApi();
  if (ac) headers["X-Firebase-AppCheck"] = ac;
  return headers;
}

function normalizeHeaderRecord(h: HeadersInit | undefined): Record<string, string> {
  if (!h) return {};
  if (typeof Headers !== "undefined" && h instanceof Headers) {
    const o: Record<string, string> = {};
    h.forEach((v, k) => {
      o[k] = v;
    });
    return o;
  }
  if (Array.isArray(h)) return Object.fromEntries(h);
  return { ...(h as Record<string, string>) };
}

function reportServerErrorIfNeeded(err: ApiError, path: string): void {
  if (err.status < 500) return;
  Sentry.captureException(err, {
    tags: {
      "api.path": path,
      "api.code": err.code,
      "http.status": String(err.status),
    },
    extra: { request_id: err.requestId },
  });
}

async function ensureOk(
  res: Response,
  path: string,
  sentRequestId: string
): Promise<void> {
  if (res.ok) return;
  const text = await res.text();
  const err = parseApiErrorBody(
    res.status,
    text,
    readRequestIdFromResponse(res) || sentRequestId
  );
  reportServerErrorIfNeeded(err, path);
  throw err;
}

function clientTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function mapUserProfile(raw: Record<string, unknown>): UserProfile {
  return {
    id: String(raw.id ?? ""),
    email: String(raw.email ?? ""),
    displayName: String(raw.display_name ?? raw.displayName ?? ""),
    preferredLocale:
      raw.preferred_locale != null && typeof raw.preferred_locale === "string"
        ? raw.preferred_locale
        : raw.preferredLocale != null && typeof raw.preferredLocale === "string"
          ? raw.preferredLocale
          : undefined,
    voiceProfile:
      raw.voice_profile && typeof raw.voice_profile === "object"
        ? (raw.voice_profile as Record<string, unknown>)
        : undefined,
    skillProfile:
      raw.skill_profile && typeof raw.skill_profile === "object"
        ? (raw.skill_profile as Record<string, unknown>)
        : undefined,
    badges: Array.isArray(raw.badges)
      ? (raw.badges as unknown[]).map(String)
      : undefined,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await backendAuthHeaders();
  const headers = mergeApiHeaders({
    "Content-Type": "application/json",
    ...auth,
    ...normalizeHeaderRecord(init?.headers),
  });
  const rid = headers["X-Request-ID"];
  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });
  await ensureOk(res, path, rid);
  return res.json() as Promise<T>;
}

async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  const auth = await backendAuthHeaders();
  const headers = mergeApiHeaders({
    "Content-Type": "application/json",
    ...auth,
    ...normalizeHeaderRecord(init?.headers),
  });
  const rid = headers["X-Request-ID"];
  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });
  await ensureOk(res, path, rid);
}

async function fetchForm(path: string, form: FormData, method = "POST"): Promise<Response> {
  const auth = await backendAuthHeaders();
  const headers = mergeApiHeaders({ ...auth });
  const rid = headers["X-Request-ID"];
  const res = await fetch(`${BACKEND_URL}${path}`, { method, headers, body: form });
  await ensureOk(res, path, rid);
  return res;
}

async function fetchText(path: string, init?: RequestInit): Promise<string> {
  const auth = await backendAuthHeaders();
  const headers = mergeApiHeaders({
    ...auth,
    ...normalizeHeaderRecord(init?.headers),
  });
  const rid = headers["X-Request-ID"];
  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });
  await ensureOk(res, path, rid);
  return res.text();
}

function mapCoachAnalysisFromApi(a: Record<string, unknown> | null | undefined): AudioAnalysis | undefined {
  if (!a || typeof a !== "object") return undefined;
  return {
    pitchHz: a.pitch_hz as number | undefined,
    noteName: a.note_name as string | undefined,
    centsDev: (a.cents_deviation as number) ?? 0,
    rmsDb: (a.rms_db as number) ?? 0,
    onsetDetected: (a.onset_detected as boolean) ?? false,
    tempo: a.tempo as number | undefined,
    breathSupportScore: a.breath_support_score as number | undefined,
    vibratoPresent: a.vibrato_present as boolean | undefined,
    pitchStability: a.pitch_stability as number | undefined,
    rhythmScore: a.rhythm_score as number | undefined,
    chordDetected: a.chord_detected as string | undefined,
    chordConfidence: a.chord_confidence as number | undefined,
    mutedStrings: (a.muted_strings as number[]) ?? [],
    timingOffsetMs: a.timing_offset_ms as number | undefined,
    velocityDb: a.velocity_db as number | undefined,
    accuracyScore: a.accuracy_score as number | undefined,
    timingAccuracy: a.timing_accuracy as number | undefined,
    strummingPattern: a.strumming_pattern as string | undefined,
    barreDetected: a.barre_detected as boolean | undefined,
    schemaVersion: a.schema_version as number | undefined,
    analysisTier: a.analysis_tier as string | undefined,
    dynamicRangeDb: a.dynamic_range_db as number | undefined,
    dynamicsFlatnessScore: a.dynamics_flatness_score as number | undefined,
    phraseCount: a.phrase_count as number | undefined,
    phrasingShapeScore: a.phrasing_shape_score as number | undefined,
    articulationHint: a.articulation_hint as string | undefined,
    noteDurationEvenness: a.note_duration_evenness as number | undefined,
    tempoStability: a.tempo_stability as number | undefined,
    tempoCurveBpm: a.tempo_curve_bpm as number[] | undefined,
    techniqueScore: a.technique_score as number | undefined,
  };
}

export const api = {
  postTelemetryEvent: (name: string, properties: Record<string, unknown> = {}) =>
    requestNoContent(`${API_PREFIX}/telemetry/events`, {
      method: "POST",
      body: JSON.stringify({ name, properties: withTelemetryContext(properties) }),
    }),

  postCoachFeedback: (body: {
    session_id: string;
    message_id: string;
    vote: "up" | "down";
    coach_type?: CoachType;
    prompt_version?: string;
  }) =>
    requestNoContent(`${API_PREFIX}/telemetry/coach-feedback`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getProfile: () =>
    request<Record<string, unknown>>(`${API_PREFIX}/users/me`).then(mapUserProfile),

  updateProfile: (data: {
    skill_profile?: Record<string, unknown>;
    preferred_locale?: string | null;
  }) =>
    request<Record<string, unknown>>(`${API_PREFIX}/users/me`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(mapUserProfile),

  sendCoachMessage: async (
    sessionId: string,
    content: string,
    audioBlob?: Blob | null,
    opts?: { techniqueJson?: string; tts?: boolean; audioFilename?: string }
  ) => {
    const form = new FormData();
    form.append("content", content);
    if (audioBlob) {
      const name =
        opts?.audioFilename ||
        (audioBlob.type.includes("mp4") || audioBlob.type.includes("aac")
          ? "recording.m4a"
          : "recording.webm");
      form.append("audio", audioBlob, name);
    }
    if (opts?.tts === true) {
      form.append("tts", "true");
    }
    if (opts?.techniqueJson) {
      form.append("technique_json", opts.techniqueJson);
    }
    const res = await fetchForm(
      `${API_PREFIX}/coach/${sessionId}/message`,
      form,
      "POST"
    );
    const data = (await res.json()) as Record<string, unknown>;
    const analysis = mapCoachAnalysisFromApi(
      data.analysis as Record<string, unknown> | undefined
    );
    return {
      reply: String(data.reply ?? ""),
      audioUrl: data.audio_url as string | undefined,
      analysis,
    };
  },

  sendCoachMessageStream: async (
    sessionId: string,
    content: string,
    audioBlob?: Blob | null,
    opts?: {
      techniqueJson?: string;
      tts?: boolean;
      audioFilename?: string;
      onToken?: (text: string) => void;
    }
  ) => {
    const form = new FormData();
    form.append("content", content);
    if (audioBlob) {
      const name =
        opts?.audioFilename ||
        (audioBlob.type.includes("mp4") || audioBlob.type.includes("aac")
          ? "recording.m4a"
          : "recording.webm");
      form.append("audio", audioBlob, name);
    }
    if (opts?.tts === true) {
      form.append("tts", "true");
    }
    if (opts?.techniqueJson) {
      form.append("technique_json", opts.techniqueJson);
    }
    const res = await fetchForm(
      `${API_PREFIX}/coach/${sessionId}/message/stream`,
      form,
      "POST"
    );
    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error("No response body");
    }
    const dec = new TextDecoder();
    let buffer = "";
    let reply = "";
    let analysis: AudioAnalysis | undefined;
    let audioUrl: string | undefined;
    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += dec.decode(value, { stream: true });
      }
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const block of parts) {
        const line = block.trim();
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        try {
          const ev = JSON.parse(raw) as Record<string, unknown>;
          if (ev.type === "token" && typeof ev.text === "string") {
            opts?.onToken?.(ev.text);
          } else if (ev.type === "done") {
            reply = typeof ev.reply === "string" ? ev.reply : "";
            analysis = mapCoachAnalysisFromApi(
              ev.analysis as Record<string, unknown> | undefined
            );
            if (typeof ev.audio_url === "string") audioUrl = ev.audio_url;
          }
        } catch {
          /* ignore malformed SSE frame */
        }
      }
      if (done) break;
    }
    return { reply, analysis, audioUrl };
  },

  endCoachSession: (sessionId: string) =>
    request<{ recap: string; next_step: string }>(
      `${API_PREFIX}/coach/${sessionId}/end`,
      { method: "POST" }
    ),

  /** Best-effort end when the tab is closing (Authorization + keepalive). */
  endCoachSessionKeepalive: async (sessionId: string) => {
    const auth = await backendAuthHeaders();
    if (!auth.Authorization) return;
    const headers = mergeApiHeaders({ ...auth });
    try {
      await fetch(`${BACKEND_URL}${API_PREFIX}/coach/${sessionId}/end`, {
        method: "POST",
        headers,
        keepalive: true,
      });
    } catch {
      /* tab may be torn down */
    }
  },

  startCoachSession: async (
    coachType: string,
    opts?: { practice_mode?: boolean; locale?: string }
  ) => {
    const body: Record<string, unknown> = {
      coach_type: coachType,
      timezone: clientTimeZone(),
    };
    if (opts?.practice_mode === false) body.practice_mode = false;
    else if (opts?.practice_mode === true) body.practice_mode = true;
    if (opts?.locale) body.locale = opts.locale;
    const raw = await request<CoachSessionRaw>(`${API_PREFIX}/coach/sessions`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    return mapCoachSession(raw);
  },

  getSessionHistory: async () => {
    const list = await request<CoachSessionRaw[]>(`${API_PREFIX}/sessions`);
    return list.map(mapCoachSession);
  },

  getDashboardStats: () => {
    let tz = "UTC";
    if (typeof Intl !== "undefined") {
      try {
        tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      } catch {
        /* ignore */
      }
    }
    const q = encodeURIComponent(tz);
    return request<{
      total_sessions: number;
      warmup_sessions: number;
      average_score: number | null;
      practice_streak_days: number;
      weekly_practice_minutes_goal: number;
      weekly_practice_minutes_estimate: number;
    }>(`${API_PREFIX}/dashboard/stats?timezone=${q}`);
  },

  exportSessionRecap: (sessionId: string) =>
    fetchText(`${API_PREFIX}/coach/${sessionId}/export-recap`, { method: "GET" }),

  getCurriculumNodes: (instrument: string) =>
    request<{
      nodes: {
        id: string;
        slug: string;
        title: string;
        tier: string;
        locked_by_plan: boolean;
      }[];
    }>(`${API_PREFIX}/curriculum/nodes?instrument=${encodeURIComponent(instrument)}`),

  getCurriculumProgress: (instrument?: string) => {
    const q = instrument
      ? `?instrument=${encodeURIComponent(instrument)}`
      : "";
    return request<{
      progress: {
        node_id: string;
        slug: string | null;
        title?: string | null;
        mastery_score: number;
        decayed_mastery?: number;
        status: string;
        attempts: number;
        last_attempted: string | null;
      }[];
      active_slugs: string[];
      needs_review: {
        slug: string;
        title: string;
        decayed_mastery: number;
        mastery_score: number;
      }[];
    }>(`${API_PREFIX}/curriculum/progress${q}`);
  },

  listSongs: (instrument?: string) => {
    const q = instrument
      ? `?instrument=${encodeURIComponent(instrument)}`
      : "";
    return request<{
      songs: {
        id: string;
        slug: string;
        title: string;
        artist: string;
        instrument: string;
        difficulty: string;
      }[];
    }>(`${API_PREFIX}/songs${q}`);
  },

  getSong: (slug: string) =>
    request<{
      id: string;
      slug: string;
      title: string;
      artist: string;
      instrument: string;
      difficulty: string;
      chord_chart: Record<string, unknown> | null;
    }>(`${API_PREFIX}/songs/${encodeURIComponent(slug)}`),

  exportTeacherReport: () =>
    fetchText(`${API_PREFIX}/coach/teacher-report`, { method: "GET" }),

  postCurriculumPlacement: (body: {
    instrument: string;
    pitch_score?: number;
    rhythm_score?: number;
  }) =>
    request<{ placed: { slug: string; status: string; mastery_score: number }[] }>(
      `${API_PREFIX}/curriculum/placement`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  subscribePush: (body: {
    endpoint: string;
    keys: { p256dh: string; auth: string };
  }) =>
    request<{ ok: boolean }>(`${API_PREFIX}/notifications/push-subscribe`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  analyseAudio: async (audioBlob: Blob) => {
    const form = new FormData();
    form.append("audio", audioBlob);
    const res = await fetchForm(`${API_PREFIX}/audio/analyse`, form, "POST");
    return res.json() as Promise<AudioAnalysis>;
  },

  startWarmup: async () => {
    const raw = await request<WarmupSessionRaw>(`${API_PREFIX}/warmup/start`, {
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
    const res = await fetchForm(
      `${API_PREFIX}/warmup/${sessionId}/score`,
      form,
      "POST"
    );
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
    interval?: "monthly" | "yearly";
    price_id?: string;
    trial_days?: number;
    success_path?: string;
    cancel_path?: string;
  }) =>
    request<{ url: string }>(`${API_PREFIX}/billing/checkout`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getEntitlements: () => {
    const q = encodeURIComponent(clientTimeZone());
    return request<{
      plan: string;
      is_pro: boolean;
      remaining_free_sessions: number;
      current_period_end: string | null;
    }>(`${API_PREFIX}/billing/entitlements?timezone=${q}`);
  },

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
      `${API_PREFIX}/coach/backing-track${q ? `?${q}` : ""}`
    );
  },
};
