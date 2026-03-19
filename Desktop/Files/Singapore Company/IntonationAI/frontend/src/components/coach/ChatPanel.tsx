"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { TypingIndicator } from "./TypingIndicator";
import { PromptSuggestions } from "./PromptSuggestions";
import { InlineFeedbackScores } from "./InlineFeedbackScores";
import type { ChatMessage } from "@/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  onSendText: (text: string) => void;
  onToggleVoice: () => void;
  isRecording: boolean;
  isLoading: boolean;
  pendingRetry?: { text: string } | null;
  onRetry?: () => void;
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
  pendingRetry,
  onRetry,
}: ChatPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const userMessageCount = messages.filter((m) => m.role === "user").length;
  const showSuggestions = userMessageCount === 0 && !isLoading;

  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isLoading]);

  const handleCopy = useCallback(async (content: string, id: string) => {
    await navigator.clipboard.writeText(content);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
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
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="text-xs text-[#6e6e73]">
                      {formatRelativeTime(m.timestamp)}
                    </span>
                    {m.role === "coach" && (
                      <button
                        type="button"
                        onClick={() => handleCopy(m.content, m.id)}
                        className="rounded p-1 text-xs text-[#6e6e73] transition hover:bg-[#e5e5e7]"
                        aria-label="Copy"
                      >
                        {copiedId === m.id ? "Copied" : "Copy"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && <TypingIndicator />}
          </>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-2 border-t border-[#d2d2d7] p-3"
      >
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
          <PromptSuggestions onSelect={handleSuggestionSelect} />
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
