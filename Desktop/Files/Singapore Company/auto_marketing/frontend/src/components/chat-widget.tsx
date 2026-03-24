"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiChatStream, ApiError } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  settingsUpdated?: Record<string, unknown>;
  upgradeUrl?: string;
  streaming?: boolean;
}

const FIELD_LABELS: Record<string, string> = {
  company_name: "Company name",
  industry: "Industry",
  description: "Description",
  target_audience: "Target audience",
  competitor_names: "Competitors",
  industry_keywords: "Keywords",
  tone: "Tone",
  tone_formal_casual: "Formal/Casual",
  tone_technical_accessible: "Technical/Accessible",
  language: "Language",
  daily_digest_enabled: "Daily digest",
  daily_digest_email: "Digest email",
  notification_time: "Notification time",
  timezone: "Timezone",
};

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hi! I'm your Marketing Assistant 👋 I can help you refine your company profile, brand voice, target audience, and preferences. What would you like to update?",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([
    "Update my company description",
    "Change my target audience",
    "Add competitor names",
  ]);
  const [unread, setUnread] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setUnread(0);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading) return;

      const userMsg: Message = { role: "user", content: trimmed };
      const newMessages: Message[] = [
        ...messages,
        userMsg,
        { role: "assistant", content: "", streaming: true },
      ];
      setMessages(newMessages);
      setInput("");
      setSuggestions([]);
      setLoading(true);

      try {
        const streamPayload = newMessages
          .slice(0, -1)
          .map((m) => ({ role: m.role, content: m.content }));
        const res = await apiChatStream(streamPayload, (delta) => {
          setMessages((prev) => {
            if (prev.length === 0) return prev;
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last?.role !== "assistant") return prev;
            copy[copy.length - 1] = {
              role: "assistant",
              content: last.content + delta,
              streaming: false,
            };
            return copy;
          });
        });

        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last?.role !== "assistant") return prev;
          copy[copy.length - 1] = {
            role: "assistant",
            content: res.reply,
            streaming: false,
            settingsUpdated:
              res.settings_updated && Object.keys(res.settings_updated).length > 0
                ? res.settings_updated
                : undefined,
          };
          return copy;
        });
        if (res.suggested_questions?.length) {
          setSuggestions(res.suggested_questions.slice(0, 3));
        }
        if (!open) setUnread((n) => n + 1);
      } catch (err) {
        const is429 = err instanceof ApiError && err.status === 429;
        const ex = err instanceof ApiError ? err.extras : undefined;
        const detail = err instanceof ApiError ? err.detail : null;
        const limit = Number(
          ex?.limit ??
            (typeof detail === "object" && detail && "limit" in detail
              ? (detail as { limit?: number }).limit
              : 10),
        );
        const tier = String(
          ex?.tier ??
            (typeof detail === "object" && detail && "tier" in detail
              ? (detail as { tier?: string }).tier
              : "starter"),
        );
        const upgradeUrl = String(
          ex?.upgrade_url ??
            (typeof detail === "object" && detail && "upgrade_url" in detail
              ? (detail as { upgrade_url?: string }).upgrade_url
              : "/billing"),
        );
        const devTrace =
          process.env.NODE_ENV === "development" &&
          err instanceof ApiError &&
          err.traceId
            ? ` [trace ${err.traceId}]`
            : "";
        const isTimeout =
          err instanceof ApiError &&
          (err.status === 504 || err.code === "CHAT_TIMEOUT");
        const content = is429
          ? `You've used all ${limit} chat messages for today (${tier} plan). Upgrade to Pro for 100 messages/day.${devTrace}`
          : isTimeout
            ? `${err instanceof ApiError ? err.message : "Request timed out."}${devTrace}`
            : `Sorry, I'm having trouble connecting. Please try again.${devTrace}`;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          const base =
            last?.role === "assistant" && !last.content
              ? prev.slice(0, -1)
              : prev;
          return [
            ...base,
            {
              role: "assistant",
              content,
              upgradeUrl: is429 ? upgradeUrl : undefined,
            },
          ];
        });
      } finally {
        setLoading(false);
      }
    },
    [messages, loading, open]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-apple-blue shadow-lg transition-transform hover:scale-105 hover:bg-apple-blue-hover focus:outline-none"
        aria-label="Open Marketing Assistant"
      >
        {open ? (
          <svg className="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        )}
        {!open && unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white">
            {unread}
          </span>
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 flex w-[360px] max-w-[calc(100vw-3rem)] flex-col rounded-apple bg-white shadow-2xl ring-1 ring-apple-border"
          style={{ height: "520px" }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 rounded-t-apple border-b border-apple-border bg-apple-card px-4 py-3">
            <img src="/logo.png" alt="IntoMarketing" className="h-8 w-8 rounded-full object-contain border border-apple-border bg-white" />
            <div>
              <p className="text-sm font-semibold">IntoMarketing Assistant</p>
              <p className="text-xs text-apple-secondary">Powered by Gemini</p>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.map((msg, i) => (
              <div key={i} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-apple-blue text-white"
                      : "bg-apple-bg text-apple-text"
                  }`}
                >
                  {msg.streaming && !msg.content ? (
                    <span className="inline-flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-apple-secondary [animation-delay:-0.3s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-apple-secondary [animation-delay:-0.15s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-apple-secondary" />
                    </span>
                  ) : (
                    msg.content
                  )}
                  {msg.upgradeUrl && (
                    <span className="mt-2 block">
                      <Link
                        href={msg.upgradeUrl}
                        className="font-medium text-apple-blue hover:underline"
                      >
                        Upgrade to Pro →
                      </Link>
                    </span>
                  )}
                </div>
                {msg.settingsUpdated && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.keys(msg.settingsUpdated).map((field) => (
                      <span
                        key={field}
                        className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-green-200"
                      >
                        <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                        {FIELD_LABELS[field] ?? field} updated
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {loading && messages[messages.length - 1]?.role === "user" && (
              <div className="flex items-start">
                <div className="flex gap-1 rounded-2xl bg-apple-bg px-3.5 py-3">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-apple-secondary [animation-delay:-0.3s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-apple-secondary [animation-delay:-0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-apple-secondary" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Suggestion chips */}
          {suggestions.length > 0 && !loading && (
            <div className="flex flex-wrap gap-1.5 px-4 pb-2">
              {suggestions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q)}
                  className="rounded-full border border-apple-border bg-apple-card px-3 py-1 text-xs text-apple-text hover:bg-apple-bg transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="border-t border-apple-border px-3 py-2.5">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask me anything about your marketing profile…"
                rows={1}
                className="flex-1 resize-none rounded-apple-sm border border-apple-border bg-apple-bg px-3 py-2 text-sm text-apple-text placeholder:text-apple-secondary focus:border-apple-blue focus:outline-none"
                style={{ maxHeight: "96px" }}
                disabled={loading}
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || loading}
                className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-apple-blue text-white transition-colors hover:bg-apple-blue-hover disabled:opacity-40"
                aria-label="Send"
              >
                <svg className="h-4 w-4 rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
            <p className="mt-1 text-center text-[10px] text-apple-secondary">
              Changes are saved automatically · Press Enter to send
            </p>
          </div>
        </div>
      )}
    </>
  );
}
