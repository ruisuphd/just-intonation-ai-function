"use client";

import { useState } from "react";
import { PitchMeter } from "@/components/audio/PitchMeter";
import { AudioVisualizer } from "@/components/audio/AudioVisualizer";
import { FeedbackCard } from "@/components/coach/FeedbackCard";
import { PianoVisualizer } from "@/components/coach/PianoVisualizer";
import { GuitarFretboard } from "@/components/coach/GuitarFretboard";
import type { AudioAnalysis } from "@/types";
import type { PitchData } from "@/types";
import type { CoachType } from "@/types";

interface InsightsPanelProps {
  pitch: PitchData | null;
  analyserNode: AnalyserNode | null;
  analysis: AudioAnalysis | null;
  suggestion: string;
  instrument?: CoachType;
}

export function InsightsPanel({
  pitch,
  analyserNode,
  analysis,
  suggestion,
  instrument = "vocal",
}: InsightsPanelProps) {
  const [open, setOpen] = useState(false);

  const visualizer =
    instrument === "piano" ? (
      <PianoVisualizer
        detectedNote={analysis?.noteName ?? null}
        targetNote={null}
        chord={analysis?.chordDetected ?? null}
        timingOffsetMs={analysis?.timingOffsetMs ?? 0}
        centsDev={analysis?.centsDev ?? 0}
      />
    ) : instrument === "guitar" ? (
      <GuitarFretboard
        detectedChord={analysis?.chordDetected ?? null}
        chordConfidence={analysis?.chordConfidence ?? 0}
        mutedStrings={analysis?.mutedStrings ?? []}
      />
    ) : (
      <PitchMeter pitch={pitch} />
    );

  return (
    <aside className="flex flex-col gap-4 lg:w-80 lg:shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex min-h-[44px] w-full items-center justify-between rounded-xl border border-[#d2d2d7] bg-white p-3 lg:hidden"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-[#1d1d1f]">
          {open ? "Hide" : "Show"} feedback
        </span>
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <div
        className={`overflow-hidden transition-all ${
          open ? "block max-h-[60vh] overflow-y-auto" : "hidden"
        } lg:block lg:max-h-none`}
      >
        <div className="flex flex-col gap-4 pt-4 pb-[var(--safe-bottom,0)] lg:pt-0">
          {visualizer}
          <AudioVisualizer analyserNode={analyserNode} />
          <FeedbackCard analysis={analysis} suggestion={suggestion} />
        </div>
      </div>
    </aside>
  );
}
