"use client";

import type { AudioAnalysis } from "@/types";

interface InlineFeedbackScoresProps {
  analysis: AudioAnalysis;
}

function getPitchScore(absCents: number): { score: number; color: string } {
  if (absCents <= 10) return { score: 100 - absCents, color: "text-emerald-500" };
  if (absCents <= 25) return { score: Math.max(60, 85 - absCents), color: "text-amber-500" };
  return { score: Math.max(0, 50 - absCents), color: "text-red-500" };
}

export function InlineFeedbackScores({ analysis }: InlineFeedbackScoresProps) {
  const absCents = Math.abs(analysis.centsDev ?? 0);
  const pitch = getPitchScore(absCents);
  const rhythmScore =
    analysis.rhythmScore != null
      ? Math.round(analysis.rhythmScore * 100)
      : analysis.pitchStability != null
        ? Math.round(analysis.pitchStability * 100)
        : 85;
  const overallScore = Math.round((pitch.score + rhythmScore) / 2);

  return (
    <div className="mt-2 flex gap-4 border-t border-[#d2d2d7]/50 pt-2">
      <span className={`text-xs font-medium ${pitch.color}`}>
        Pitch {Math.round(pitch.score)}%
      </span>
      <span className="text-xs font-medium text-[#6e6e73]">
        Rhythm {rhythmScore}%
      </span>
      <span className="text-xs font-medium text-[#1d1d1f]">
        Overall {overallScore}%
      </span>
    </div>
  );
}
