"use client";

import type { AudioAnalysis } from "@/types";

interface FeedbackCardProps {
  analysis: AudioAnalysis | null;
  suggestion: string;
}

function getPitchScore(absCents: number): {
  score: number;
  label: string;
  color: string;
} {
  if (absCents <= 10) return { score: 100 - absCents, label: "Good", color: "text-emerald-400" };
  if (absCents <= 25) return { score: Math.max(60, 85 - absCents), label: "OK", color: "text-amber-400" };
  return { score: Math.max(0, 50 - absCents), label: "Poor", color: "text-red-400" };
}

export function FeedbackCard({ analysis, suggestion }: FeedbackCardProps) {
  if (!analysis) {
    return (
      <div className="rounded-xl border border-[#d2d2d7] bg-white p-6">
        <p className="text-center text-[#6e6e73]">No analysis yet</p>
        {suggestion && (
          <p className="mt-3 text-sm text-[#6e6e73]">{suggestion}</p>
        )}
      </div>
    );
  }

  const absCents = Math.abs(analysis.centsDev ?? 0);
  const pitch = getPitchScore(absCents);
  const rhythmScore =
    analysis.rhythmScore != null
      ? Math.round(analysis.rhythmScore * 100)
      : analysis.timingAccuracy != null
        ? Math.round(analysis.timingAccuracy * 100)
        : (analysis.pitchStability != null ? Math.round(analysis.pitchStability * 100) : null);
  const rhythmDisplay = rhythmScore ?? (analysis.accuracyScore != null ? Math.round(analysis.accuracyScore * 100) : 85);
  const overallScore = analysis.accuracyScore != null
    ? Math.round(analysis.accuracyScore * 100)
    : Math.round((pitch.score + rhythmDisplay) / 2);

  return (
    <div className="rounded-xl border border-[#d2d2d7] bg-white p-6">
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-[#6e6e73]">Pitch</p>
          <p className={`text-xl font-semibold ${pitch.color}`}>
            {pitch.score}%
          </p>
          <p className={`text-xs ${pitch.color}`}>{pitch.label}</p>
        </div>
        <div>
          <p className="text-xs text-[#6e6e73]">Rhythm</p>
          <p className="text-xl font-semibold text-[#1d1d1f]">{rhythmDisplay}%</p>
        </div>
        <div>
          <p className="text-xs text-[#6e6e73]">Overall</p>
          <p className="text-xl font-semibold text-[#1d1d1f]">{overallScore}%</p>
        </div>
      </div>

      {suggestion && (
        <div className="mt-4 rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] p-3">
          <p className="text-xs font-medium text-[#6e6e73]">Suggestion</p>
          <p className="mt-1 text-sm text-[#1d1d1f]">{suggestion}</p>
        </div>
      )}
    </div>
  );
}
