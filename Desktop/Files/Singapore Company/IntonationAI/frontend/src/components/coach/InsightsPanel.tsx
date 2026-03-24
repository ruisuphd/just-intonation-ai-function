"use client";

import { useState, type ReactNode } from "react";
import { PitchMeter } from "@/components/audio/PitchMeter";
import { AudioVisualizer } from "@/components/audio/AudioVisualizer";
import { FeedbackCard } from "@/components/coach/FeedbackCard";
import { PianoVisualizer } from "@/components/coach/PianoVisualizer";
import { GuitarFretboard } from "@/components/coach/GuitarFretboard";
import { PracticeDisclaimer } from "@/components/legal/PracticeDisclaimer";
import type { AudioAnalysis } from "@/types";
import type { PitchData } from "@/types";
import type { CoachType } from "@/types";

interface InsightsPanelProps {
  pitch: PitchData | null;
  analyserNode: AnalyserNode | null;
  analysis: AudioAnalysis | null;
  suggestion: string;
  instrument?: CoachType;
  techniqueSummary?: string | null;
  extras?: ReactNode;
}

export function InsightsPanel({
  pitch,
  analyserNode,
  analysis,
  suggestion,
  instrument = "vocal",
  techniqueSummary,
  extras,
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
    <aside className="flex flex-col gap-5 lg:w-80 lg:shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex min-h-[44px] w-full items-center justify-between rounded-2xl bg-white p-3 shadow-[var(--card-shadow)] lg:hidden"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-foreground">
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
        <div className="flex flex-col gap-5 pt-4 pb-[var(--safe-bottom,0)] lg:pt-0">
          {analysis?.analysisTier === "basic" && (
            <p
              className="rounded-xl border border-border-subtle bg-section px-3 py-2 text-center text-xs text-muted"
              role="status"
            >
              Basic live analysis. Upgrade to Pro for full dynamics, phrasing, and
              instrument depth.
            </p>
          )}
          {visualizer}
          <AudioVisualizer analyserNode={analyserNode} />
          {techniqueSummary && (
            <div className="rounded-2xl bg-white p-4 text-sm leading-relaxed text-foreground shadow-[var(--card-shadow)]">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Technique
              </p>
              <p className="mt-2">{techniqueSummary}</p>
            </div>
          )}
          <FeedbackCard analysis={analysis} suggestion={suggestion} />
          <PracticeDisclaimer variant="insights" className="px-1" />
          {extras}
        </div>
      </div>
    </aside>
  );
}
