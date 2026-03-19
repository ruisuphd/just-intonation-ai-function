"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ChatPanel } from "@/components/coach/ChatPanel";
import { InsightsPanel } from "@/components/coach/InsightsPanel";
import { useAudioCapture } from "@/hooks/useAudioCapture";
import { usePitchDetection } from "@/hooks/usePitchDetection";
import { useFirestoreMessages } from "@/hooks/useFirestoreMessages";
import { api } from "@/lib/api";
import { getStoredMicId } from "@/lib/mic-preference";
import { RequireAuth } from "@/components/auth/RequireAuth";
import type { ChatMessage, AudioAnalysis } from "@/types";

const INITIAL_MESSAGE: ChatMessage = {
  id: "init",
  role: "coach",
  content:
    "Hello! I'm your AI piano coach. Play into the mic and I'll analyse your notes, chords, timing, and technique.",
  timestamp: Date.now(),
};

export default function PianoCoachPage() {
  const router = useRouter();
  const { isCapturing, analyserNode, start, stop, getLastSeconds } =
    useAudioCapture();
  const pitch = usePitchDetection(analyserNode);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_MESSAGE]);
  const firestoreMessages = useFirestoreMessages(sessionId);
  const displayMessages =
    firestoreMessages.length > 0 ? firestoreMessages : messages;
  const [isLoading, setIsLoading] = useState(false);
  const [currentAnalysis, setCurrentAnalysis] = useState<AudioAnalysis | null>(null);
  const [recap, setRecap] = useState<{ recap: string; next_step: string } | null>(null);
  const [ending, setEnding] = useState(false);
  const [pendingRetry, setPendingRetry] = useState<{
    text: string;
    audioBlob: Blob | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .startCoachSession("piano")
      .then((session) => {
        if (!cancelled) {
          setSessionId(session.id);
          if (session.messages?.length) {
            setMessages(session.messages);
          }
        }
      })
      .catch((err) => {
        if (!cancelled && err?.message?.includes("403")) {
          router.push("/pricing");
        } else if (!cancelled) {
          setSessionId(crypto.randomUUID());
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const onEndSession = useCallback(async () => {
    if (!sessionId || ending) return;
    setEnding(true);
    try {
      const res = await api.endCoachSession(sessionId);
      setRecap(res);
    } catch {
      router.push("/dashboard");
    } finally {
      setEnding(false);
    }
  }, [sessionId, ending, router]);

  const onCloseRecap = useCallback(() => {
    setRecap(null);
    router.push("/dashboard");
  }, [router]);

  const onToggleVoice = useCallback(() => {
    if (isCapturing) {
      stop();
    } else {
      const deviceId = getStoredMicId();
      start({ deviceId: deviceId ?? undefined });
    }
  }, [isCapturing, start, stop]);

  const sendMessage = useCallback(
    async (text: string, audioBlob: Blob | null) => {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setPendingRetry(null);
      setIsLoading(true);
      try {
        const sid = sessionId ?? crypto.randomUUID();
        if (!sessionId) setSessionId(sid);
        const { reply, analysis } = await api.sendCoachMessage(
          sid,
          text,
          audioBlob
        );
        const coachMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "coach",
          content: reply,
          analysis,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, coachMsg]);
        if (analysis) setCurrentAnalysis(analysis);
      } catch {
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
        setPendingRetry({ text, audioBlob });
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId]
  );

  const onSendText = useCallback(
    (text: string) => {
      const audioBlob = isCapturing ? getLastSeconds(15) : null;
      sendMessage(text, audioBlob);
    },
    [isCapturing, getLastSeconds, sendMessage]
  );

  const onRetry = useCallback(() => {
    if (!pendingRetry) return;
    sendMessage(pendingRetry.text, pendingRetry.audioBlob);
  }, [pendingRetry, sendMessage]);

  return (
    <RequireAuth>
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-[#fbfbfd] supports-[height:100dvh]:h-[calc(100dvh-3.5rem)]">
      <div className="flex items-center justify-between border-b border-[#d2d2d7] bg-white px-4 py-3">
        <h1 className="text-lg font-semibold text-[#1d1d1f]">Piano Coach</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onEndSession}
            disabled={ending}
            className="rounded-xl border border-[#d2d2d7] px-3 py-1.5 text-sm text-[#1d1d1f] transition hover:bg-[#f5f5f7] disabled:opacity-50"
          >
            {ending ? "Ending…" : "End Session"}
          </button>
          <Link
            href="/dashboard"
            className="rounded-xl bg-[#0071e3] px-3 py-1.5 text-sm text-white transition hover:bg-[#0077ed]"
          >
            Dashboard
          </Link>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4 lg:flex-row lg:gap-4">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <ChatPanel
              messages={displayMessages}
              onSendText={onSendText}
              onToggleVoice={onToggleVoice}
              isRecording={isCapturing}
              isLoading={isLoading}
              pendingRetry={pendingRetry}
              onRetry={onRetry}
            />
          </div>
          <InsightsPanel
            pitch={pitch}
            analyserNode={analyserNode}
            analysis={currentAnalysis}
            suggestion="Play a note or chord to see feedback."
            instrument="piano"
          />
        </div>
      </div>

      {recap && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="max-w-md rounded-2xl border border-[#d2d2d7] bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-[#1d1d1f]">Session Recap</h2>
            <p className="mt-3 text-[#1d1d1f]">{recap.recap}</p>
            <p className="mt-2 text-sm font-medium text-[#6e6e73]">Next step:</p>
            <p className="mt-1 text-[#1d1d1f]">{recap.next_step}</p>
            <button
              type="button"
              onClick={onCloseRecap}
              className="mt-6 w-full rounded-xl bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ed]"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
    </RequireAuth>
  );
}
