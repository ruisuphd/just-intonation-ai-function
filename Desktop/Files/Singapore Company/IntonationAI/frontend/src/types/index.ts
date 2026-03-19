export type CoachType = "vocal" | "piano" | "guitar";

export type MessageRole = "user" | "coach" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  audioUrl?: string;
  analysis?: AudioAnalysis;
  timestamp: number;
}

export interface AudioAnalysis {
  pitchHz?: number | null;
  noteName?: string | null;
  centsDev?: number;
  rmsDb?: number;
  onsetDetected?: boolean;
  tempo?: number;
  breathSupportScore?: number;
  vibratoPresent?: boolean;
  pitchStability?: number;
  rhythmScore?: number;
  chordDetected?: string | null;
  chordConfidence?: number;
  mutedStrings?: number[];
  timingOffsetMs?: number;
  velocityDb?: number;
  accuracyScore?: number;
  timingAccuracy?: number;
  strummingPattern?: string;
  barreDetected?: boolean;
}

export interface PitchData {
  frequency: number;
  note: string;
  cents: number;
  clarity: number;
}

export interface WarmupExercise {
  id: string;
  name: string;
  description: string;
  targetPitchRange: [number, number];
  durationSec: number;
  tempo: number;
  difficulty: number;
}

export interface WarmupScore {
  exerciseId: string;
  pitchAccuracy: number;
  rhythmAccuracy: number;
  overallScore: number;
}

export interface WarmupSession {
  id: string;
  exercises: WarmupExercise[];
  scores: WarmupScore[];
  startedAt: string;
  completedAt?: string | null;
}

export interface WarmupSessionRaw {
  id: string;
  exercises: {
    id: string;
    name: string;
    description: string;
    target_pitch_range: [number, number];
    duration_sec: number;
    tempo: number;
    difficulty: number;
  }[];
  scores: {
    exercise_id: string;
    pitch_accuracy: number;
    rhythm_accuracy: number;
    overall_score: number;
  }[];
  started_at: string;
  completed_at?: string | null;
}

export function mapWarmupSession(raw: WarmupSessionRaw): WarmupSession {
  return {
    id: raw.id,
    exercises: raw.exercises.map((e) => ({
      id: e.id,
      name: e.name,
      description: e.description,
      targetPitchRange: e.target_pitch_range,
      durationSec: e.duration_sec,
      tempo: e.tempo,
      difficulty: e.difficulty,
    })),
    scores: raw.scores.map((s) => ({
      exerciseId: s.exercise_id,
      pitchAccuracy: s.pitch_accuracy,
      rhythmAccuracy: s.rhythm_accuracy,
      overallScore: s.overall_score,
    })),
    startedAt: raw.started_at,
    completedAt: raw.completed_at ?? undefined,
  };
}

export interface CoachSession {
  id: string;
  coachType: CoachType;
  messages: ChatMessage[];
  startedAt: string;
  endedAt?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  displayName: string;
  voiceProfile?: Record<string, unknown>;
  skillProfile?: Record<string, unknown>;
}

export interface SubscriptionInfo {
  plan: "free" | "essential" | "pro";
  status: "active" | "cancelled" | "past_due";
  currentPeriodEnd?: string;
}
