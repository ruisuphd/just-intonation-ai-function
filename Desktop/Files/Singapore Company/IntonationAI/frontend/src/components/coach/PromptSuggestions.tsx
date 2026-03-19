"use client";

const SUGGESTIONS = [
  "Sing a sustained note and I'll check your pitch",
  "I just did my warm-up – can you give me feedback?",
  "Help me with breath support on high notes",
  "What should I focus on today?",
];

interface PromptSuggestionsProps {
  onSelect: (text: string) => void;
}

export function PromptSuggestions({ onSelect }: PromptSuggestionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {SUGGESTIONS.map((text) => (
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
