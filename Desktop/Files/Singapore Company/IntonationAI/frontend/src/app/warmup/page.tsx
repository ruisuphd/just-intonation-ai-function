"use client";

import { useState, useEffect, useCallback } from "react";
import { ExerciseCard } from "@/components/warmup/ExerciseCard";
import { Timer } from "@/components/warmup/Timer";
import { ProgressRing } from "@/components/warmup/ProgressRing";
import { PitchMeter } from "@/components/audio/PitchMeter";
import { useAudioCapture } from "@/hooks/useAudioCapture";
import { usePitchDetection } from "@/hooks/usePitchDetection";
import { api } from "@/lib/api";
import { getStoredMicId } from "@/lib/mic-preference";
import { RequireAuth } from "@/components/auth/RequireAuth";
import type { WarmupExercise, WarmupScore } from "@/types";

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

export default function WarmupPage() {
  const { isCapturing, analyserNode, start, stop, getLastSeconds } =
    useAudioCapture();
  const pitch = usePitchDetection(analyserNode);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [exercises, setExercises] = useState<WarmupExercise[]>([]);
  const [scores, setScores] = useState<WarmupScore[]>([]);
  const [commentary, setCommentary] = useState<string | null>(null);
  const [currentExerciseIndex, setCurrentExerciseIndex] = useState(0);
  const [isExerciseActive, setIsExerciseActive] = useState(false);
  const [timerStarted, setTimerStarted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [timerDisplay, setTimerDisplay] = useState<{
    seconds: number;
    running: boolean;
  } | null>(null);
  const [pitchExpanded, setPitchExpanded] = useState(false);

  const currentExercise = exercises[currentExerciseIndex];
  const completedCount = scores.length;
  const totalCount = exercises.length;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  useEffect(() => {
    let cancelled = false;
    api
      .startWarmup()
      .then((session) => {
        if (!cancelled) {
          setSessionId(session.id);
          setExercises(session.exercises);
          setScores(session.scores);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to start warmup");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleExerciseComplete = useCallback(async () => {
    if (!sessionId || !currentExercise || !getLastSeconds) return;

    const audioBlob = getLastSeconds(currentExercise.durationSec);
    if (!audioBlob || audioBlob.size < 512) {
      setScores((prev) => [
        ...prev,
        {
          exerciseId: currentExercise.id,
          pitchAccuracy: 0.5,
          rhythmAccuracy: 0.8,
          overallScore: 0.6,
        },
      ]);
      setCommentary("No audio detected. Try again with your microphone on.");
      setIsExerciseActive(false);
      setTimerStarted(false);
      setCurrentExerciseIndex((prev) =>
        prev < exercises.length - 1 ? prev + 1 : prev
      );
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.submitWarmupScore(
        sessionId,
        currentExercise.id,
        audioBlob
      );
      const s = res.score;
      const newScore: WarmupScore = {
        exerciseId: s.exercise_id,
        pitchAccuracy: s.pitch_accuracy * 100,
        rhythmAccuracy: s.rhythm_accuracy * 100,
        overallScore: s.overall_score * 100,
      };
      setScores((prev) => [...prev, newScore]);
      setCommentary(res.commentary ?? null);
      setIsExerciseActive(false);
      setTimerStarted(false);
      setCurrentExerciseIndex((prev) =>
        prev < exercises.length - 1 ? prev + 1 : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit score");
    } finally {
      setSubmitting(false);
    }
  }, [
    sessionId,
    currentExercise,
    getLastSeconds,
    exercises.length,
  ]);

  useEffect(() => {
    const deviceId = getStoredMicId();
    if (!isCapturing) start({ deviceId: deviceId ?? undefined });
    return () => stop();
  }, [start, stop, isCapturing]);

  const handleStartExercise = () => {
    setCommentary(null);
    setIsExerciseActive(true);
    setTimerStarted(true);
    if (currentExercise) {
      setTimerDisplay({ seconds: currentExercise.durationSec, running: true });
    }
  };

  const handleTimerTick = useCallback((seconds: number, running: boolean) => {
    setTimerDisplay({ seconds, running });
  }, []);

  useEffect(() => {
    if (!isExerciseActive && !timerStarted) {
      setTimerDisplay(null);
    }
  }, [isExerciseActive, timerStarted]);

  if (loading) {
    return (
      <RequireAuth>
        <div className="mx-auto max-w-4xl px-6 py-8">
          <p className="text-[#6e6e73]">Loading warmup...</p>
        </div>
      </RequireAuth>
    );
  }

  if (error) {
    return (
      <RequireAuth>
        <div className="mx-auto max-w-4xl px-6 py-8">
          <p className="text-red-600">{error}</p>
        </div>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
    <div className="min-h-[100dvh] bg-[#fbfbfd] supports-[height:100dvh]:min-h-[100dvh]">
      {isExerciseActive && timerDisplay && (
        <div className="sticky top-14 z-10 flex items-center justify-center gap-4 border-b border-[#d2d2d7] bg-white px-4 py-3 md:hidden">
          <span
            className={`font-mono text-2xl tabular-nums text-[#1d1d1f] ${
              timerDisplay.running ? "animate-pulse" : ""
            }`}
            role="timer"
            aria-live="polite"
          >
            {pad(Math.floor(timerDisplay.seconds / 60))}:
            {pad(timerDisplay.seconds % 60)}
          </span>
          <span className="text-sm text-[#6e6e73]">
            {currentExercise?.name ?? "Exercise"}
          </span>
        </div>
      )}

      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start sm:justify-between">
          <h1 className="text-2xl font-semibold text-[#1d1d1f]">Vocal Warm-Up</h1>
          <ProgressRing value={progressPercent} size={80} label="Session" />
        </div>

        {commentary && (
          <div className="mt-6 rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] p-4">
            <p className="text-sm text-[#1d1d1f]">{commentary}</p>
          </div>
        )}

        <div className="mt-8 grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            {exercises.map((ex, i) => {
              const status =
                i < currentExerciseIndex
                  ? "completed"
                  : i === currentExerciseIndex
                    ? "active"
                    : "upcoming";
              const score = scores.find((s) => s.exerciseId === ex.id);
              return (
                <ExerciseCard
                  key={ex.id}
                  exercise={ex}
                  status={status}
                  score={score}
                  onStart={
                    status === "active" && !isExerciseActive && !submitting
                      ? handleStartExercise
                      : undefined
                  }
                />
              );
            })}
          </div>

          <div className="space-y-6">
            <div className="rounded-xl border border-[#d2d2d7] bg-white p-6">
              {isExerciseActive && currentExercise ? (
                <Timer
                  durationSec={currentExercise.durationSec}
                  onComplete={handleExerciseComplete}
                  autoStart={timerStarted}
                  onTick={handleTimerTick}
                />
              ) : (
                <div className="flex flex-col items-center gap-4 py-4">
                  <p className="text-[#6e6e73]">
                    {exercises.length > 0 && currentExerciseIndex < exercises.length
                      ? "Start an exercise to begin the timer"
                      : exercises.length > 0
                        ? "All exercises complete!"
                        : "No exercises in this session"}
                  </p>
                </div>
              )}
            </div>

            <div className="lg:block">
              <button
                type="button"
                onClick={() => setPitchExpanded((p) => !p)}
                className="mb-3 flex w-full items-center justify-between rounded-xl border border-[#d2d2d7] bg-white px-4 py-3 text-left text-sm font-medium text-[#1d1d1f] lg:hidden"
              >
                {pitchExpanded ? "Hide pitch" : "Show pitch"}
              </button>
              <div className={pitchExpanded ? "block" : "hidden lg:block"}>
                <div className="lg:hidden">
                  <PitchMeter pitch={pitch} compact />
                </div>
                <div className="hidden lg:block">
                  <PitchMeter pitch={pitch} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </RequireAuth>
  );
}
