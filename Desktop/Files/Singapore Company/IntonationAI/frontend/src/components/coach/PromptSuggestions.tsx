"use client";

import type { CoachType } from "@/types";

const BY_INSTRUMENT: Record<CoachType, string[]> = {
  vocal: [
    "Sing a sustained note and I'll check your pitch",
    "I just did my warm-up – can you give me feedback?",
    "Help me with breath support on high notes",
    "What should I focus on today?",
  ],
  piano: [
    "I played a C major scale — how was my evenness?",
    "Help me fix timing on this chord progression",
    "My left hand is weaker — what should I practice?",
    "What should I focus on in today's session?",
  ],
  guitar: [
    "Strum this chord and tell me if any strings are muted",
    "Help me clean up transitions between G and D",
    "My rhythm feels rushed — can you check my strumming?",
    "What should I work on first today?",
  ],
};

interface PromptSuggestionsProps {
  coachType?: CoachType;
  onSelect: (text: string) => void;
}

export function PromptSuggestions({
  coachType = "vocal",
  onSelect,
}: PromptSuggestionsProps) {
  const suggestions = BY_INSTRUMENT[coachType] ?? BY_INSTRUMENT.vocal;
  return (
    <div className="flex flex-wrap gap-2">
      {suggestions.map((text) => (
        <button
          key={text}
          type="button"
          onClick={() => onSelect(text)}
          className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-left text-sm text-[#1d1d1f] transition hover:border-[#0071e3]/50 hover:bg-[#f5f5f7]"
        >
          {text}
        </button>
      ))}
    </div>
  );
}
