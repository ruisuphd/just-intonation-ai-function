"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { WS_URL } from "@/lib/constants";
import { getIdToken } from "@/lib/firebase";

type WsStatus = "disconnected" | "connecting" | "connected";

export function useWebSocket(path: string) {
  const [status, setStatus] = useState<WsStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<unknown>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setStatus("connecting");

    const token = await getIdToken();
    const url = `${WS_URL}${path}${token ? `?token=${token}` : ""}`;
    const ws = new WebSocket(url);

    ws.onopen = () => setStatus("connected");
    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("disconnected");
    ws.onmessage = (e) => {
      try {
        setLastMessage(JSON.parse(e.data));
      } catch {
        setLastMessage(e.data);
      }
    };

    wsRef.current = ws;
  }, [path]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  useEffect(() => () => disconnect(), [disconnect]);

  return { status, lastMessage, connect, send, sendBinary, disconnect };
}
