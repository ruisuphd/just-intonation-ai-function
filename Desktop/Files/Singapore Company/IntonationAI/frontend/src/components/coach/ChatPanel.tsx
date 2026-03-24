"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { TypingIndicator } from "./TypingIndicator";
import { PromptSuggestions } from "./PromptSuggestions";
import { InlineFeedbackScores } from "./InlineFeedbackScores";
import type { ChatMessage, CoachType } from "@/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  onSendText: (text: string) => void;
  onToggleVoice: () => void;
  isRecording: boolean;
  isLoading: boolean;
  /** Partial coach reply while SSE stream is in progress */
  streamingCoachContent?: string;
  pendingRetry?: { text: string } | null;
  onRetry?: () => void;
  coachType?: CoachType;
  coachVoiceEnabled?: boolean;
  onCoachVoiceChange?: (enabled: boolean) => void;
  onCoachFeedback?: (messageId: string, vote: "up" | "down") => void;
}

function formatRelativeTime(ts: number): string {
  const sec = (Date.now() - ts) / 1000;
  if (sec < 60) return "Just now";
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} hr ago`;
  return new Date(ts).toLocaleDateString();
}

export function ChatPanel({
  messages,
  onSendText,
  onToggleVoice,
  isRecording,
  isLoading,
  streamingCoachContent = "",
  pendingRetry,
  onRetry,
  coachType = "vocal",
  coachVoiceEnabled = false,
  onCoachVoiceChange,
  onCoachFeedback,
}: ChatPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, "up" | "down">>({});
  const [, setTick] = useState(0);

  const userMessageCount = messages.filter((m) => m.role === "user").length;
  const showSuggestions = userMessageCount === 0 && !isLoading;

  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isLoading, streamingCoachContent]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const submitFeedback = useCallback(
    (messageId: string, vote: "up" | "down") => {
      if (feedbackGiven[messageId] || !onCoachFeedback) return;
      setFeedbackGiven((prev) => ({ ...prev, [messageId]: vote }));
      onCoachFeedback(messageId, vote);
    },
    [feedbackGiven, onCoachFeedback]
  );

  const handleCopy = useCallback(async (content: string, id: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      /* clipboard unavailable (non-HTTPS, denied, etc.) */
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = textareaRef.current?.value.trim();
    if (text && !isLoading) {
      onSendText(text);
      textareaRef.current!.value = "";
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  };

  const handleSuggestionSelect = (text: string) => {
    if (textareaRef.current) {
      textareaRef.current.value = text;
      textareaRef.current.focus();
    }
  };

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    const resize = () => {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
    };
    ta.addEventListener("input", resize);
    return () => ta.removeEventListener("input", resize);
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-[#d2d2d7] bg-white">
      <div
        ref={listRef}
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4"
      >
        {messages.length === 0 ? (
          <p className="py-8 text-center text-sm text-[#6e6e73]">
            Start the conversation
          </p>
        ) : (
          <>
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex flex-col ${
                  m.role === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`group relative max-w-[85%] rounded-xl px-3 py-2 ${
                    m.role === "user"
                      ? "bg-[#0071e3] text-white"
                      : "bg-[#f5f5f7] text-[#1d1d1f]"
                  }`}
                >
                  <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                  {m.role === "coach" && m.analysis && (
                    <InlineFeedbackScores analysis={m.analysis} />
                  )}
                  <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs text-[#6e6e73]">
                      {formatRelativeTime(m.timestamp)}
                    </span>
                    {m.role === "coach" && (
                      <div className="flex items-center gap-1">
                        {onCoachFeedback && (
                          <>
                            <button
                              type="button"
                              onClick={() => submitFeedback(m.id, "up")}
                              disabled={!!feedbackGiven[m.id]}
                              className={`rounded px-2 py-0.5 text-xs font-medium transition ${
                                feedbackGiven[m.id] === "up"
                                  ? "bg-[#34c759]/20 text-[#1d1d1f]"
                                  : "text-[#6e6e73] hover:bg-[#e5e5e7]"
                              } disabled:opacity-40`}
                              aria-label="Helpful"
                            >
                              Helpful
                            </button>
                            <button
                              type="button"
                              onClick={() => submitFeedback(m.id, "down")}
                              disabled={!!feedbackGiven[m.id]}
                              className={`rounded px-2 py-0.5 text-xs font-medium transition ${
                                feedbackGiven[m.id] === "down"
                                  ? "bg-[#ff3b30]/15 text-[#1d1d1f]"
                                  : "text-[#6e6e73] hover:bg-[#e5e5e7]"
                              } disabled:opacity-40`}
                              aria-label="Not helpful"
                            >
                              Not helpful
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          onClick={() => handleCopy(m.content, m.id)}
                          className="rounded p-1 text-xs text-[#6e6e73] transition hover:bg-[#e5e5e7]"
                          aria-label="Copy"
                        >
                          {copiedId === m.id ? "Copied" : "Copy"}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && streamingCoachContent ? (
              <div className="flex flex-col items-start">
                <div className="max-w-[85%] rounded-xl bg-[#f5f5f7] px-3 py-2 text-[#1d1d1f]">
                  <p className="whitespace-pre-wrap text-sm">{streamingCoachContent}</p>
                  <span className="mt-1 inline-block h-2 w-2 animate-pulse rounded-full bg-[#0071e3]" />
                </div>
              </div>
            ) : null}
            {isLoading && !streamingCoachContent ? <TypingIndicator /> : null}
          </>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-2 border-t border-[#d2d2d7] p-3"
      >
        <p className="text-[11px] leading-snug text-[#6e6e73]">
          AI-generated responses — may be inaccurate; use your judgment.
        </p>
        {pendingRetry && onRetry && (
          <div className="flex items-center justify-between gap-2 rounded-lg bg-[#f5f5f7] px-3 py-2 text-sm text-[#1d1d1f]">
            <span>Something went wrong. Try again?</span>
            <button
              type="button"
              onClick={onRetry}
              className="min-h-[36px] shrink-0 rounded-lg bg-[#0071e3] px-3 py-1.5 font-medium text-white transition hover:bg-[#0077ed]"
            >
              Retry
            </button>
          </div>
        )}
        {showSuggestions && (
          <PromptSuggestions coachType={coachType} onSelect={handleSuggestionSelect} />
        )}
        {onCoachVoiceChange && (
          <label className="flex cursor-pointer items-center gap-2 text-xs text-[#6e6e73]">
            <input
              type="checkbox"
              checked={coachVoiceEnabled}
              onChange={(e) => onCoachVoiceChange(e.target.checked)}
              className="h-4 w-4 rounded border-[#d2d2d7]"
            />
            Spoken coach replies (slower, uses cloud TTS)
          </label>
        )}
        <div className="flex gap-2" style={{ paddingBottom: "var(--safe-bottom, 0)" }}>
          <textarea
            ref={textareaRef}
            placeholder={
              isRecording
                ? "Last 15s of singing will be included. Type a message..."
                : "Sing into your mic, then type a message and send for feedback."
            }
            disabled={isLoading}
            rows={2}
            onKeyDown={handleTextareaKeyDown}
            className="min-h-[44px] max-h-36 flex-1 resize-none rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] px-3 py-2.5 text-sm text-[#1d1d1f] placeholder-[#6e6e73] outline-none transition focus:border-[#0071e3] disabled:opacity-50"
          />
          <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={onToggleVoice}
              className={`min-h-[44px] min-w-[44px] rounded-xl px-3 py-2 text-sm font-medium transition ${
                isRecording
                  ? "bg-red-500 text-white"
                  : "border border-[#d2d2d7] text-[#1d1d1f] hover:bg-[#f5f5f7]"
              }`}
              aria-label={isRecording ? "Stop recording" : "Start voice input"}
            >
              {isRecording ? "Stop" : "Voice"}
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="min-h-[44px] min-w-[44px] rounded-xl bg-[#0071e3] px-3 py-2 text-sm font-medium text-white transition hover:bg-[#0077ed] disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
