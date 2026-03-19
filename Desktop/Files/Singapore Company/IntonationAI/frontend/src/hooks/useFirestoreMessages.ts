"use client";
import { useState, useEffect } from "react";
import { collection, query, orderBy, onSnapshot } from "firebase/firestore";
import { getFirestoreDb } from "@/lib/firebase";
import type { ChatMessage } from "@/types";

export function useFirestoreMessages(sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    if (!sessionId) return;
    const db = getFirestoreDb();
    if (!db) return;

    const q = query(
      collection(db, "sessions", sessionId, "messages"),
      orderBy("created_at", "asc")
    );

    const unsub = onSnapshot(q, (snapshot) => {
      const msgs: ChatMessage[] = snapshot.docs.map((doc) => {
        const data = doc.data();
        return {
          id: doc.id,
          role: data.role ?? "system",
          content: data.content ?? "",
          audioUrl: data.audio_url ?? undefined,
          analysis: data.analysis ?? undefined,
          timestamp: data.created_at?.toMillis?.() ?? Date.now(),
        };
      });
      setMessages(msgs);
    });

    return unsub;
  }, [sessionId]);

  return messages;
}
