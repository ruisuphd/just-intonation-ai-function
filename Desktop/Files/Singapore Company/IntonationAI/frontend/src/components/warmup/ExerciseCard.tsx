"use client";

import type { WarmupExercise, WarmupScore } from "@/types";
import { frequencyToNote } from "@/lib/audio-utils";

interface ExerciseCardProps {
  exercise: WarmupExercise;
  status: "upcoming" | "active" | "completed";
  score?: WarmupScore;
  onStart?: () => void;
}

export function ExerciseCard({
  exercise,
  status,
  score,
  onStart,
}: ExerciseCardProps) {
  const [lowHz, highHz] = exercise.targetPitchRange;
  const lowNote = frequencyToNote(lowHz).name;
  const highNote = frequencyToNote(highHz).name;

  return (
    <div
      className={`
        rounded-xl border-2 bg-white p-5 transition-colors
        ${status === "active" ? "border-[#0071e3] ring-2 ring-[#0071e3]/30" : "border-[#d2d2d7]"}
        ${status === "upcoming" ? "opacity-80" : ""}
      `}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-[#1d1d1f]">{exercise.name}</h3>
          <p className="mt-1 text-sm text-[#6e6e73]">{exercise.description}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[#6e6e73]">
            <span>
              Range: {lowNote} – {highNote}
            </span>
            <span>
              {Math.floor(exercise.durationSec / 60)}:
              {String(exercise.durationSec % 60).padStart(2, "0")} · {exercise.tempo} BPM
            </span>
          </div>
          <div className="mt-2 flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <span
                key={n}
                className={`h-1.5 w-1.5 rounded-full ${
                  n <= exercise.difficulty ? "bg-[#0071e3]" : "bg-[#d2d2d7]"
                }`}
              />
            ))}
          </div>
        </div>
        <div className="shrink-0">
          {status === "active" && onStart && (
            <button
              type="button"
              onClick={onStart}
              className="rounded-xl bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0077ed]"
            >
              Start
            </button>
          )}
          {status === "completed" && score && (
            <div className="rounded-xl bg-[#f5f5f7] px-3 py-2 text-right">
              <div className="text-lg font-semibold text-[#1d1d1f]">
                {Math.round(score.overallScore)}%
              </div>
              <div className="text-xs text-[#6e6e73]">
                pitch {Math.round(score.pitchAccuracy)} · rhythm{" "}
                {Math.round(score.rhythmAccuracy)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
