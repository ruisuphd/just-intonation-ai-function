"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { WS_URL } from "@/lib/constants";
import { getAppCheckTokenForApi, getIdToken } from "@/lib/firebase";

export type WsStatus = "disconnected" | "connecting" | "connected" | "reconnecting";

const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 800;

function jitter(ms: number): number {
  return ms + Math.floor(Math.random() * 400);
}

function isPermanentCloseCode(code: number): boolean {
  return code >= 4000 && code < 5000;
}

export function useWebSocket(path: string | null) {
  const [status, setStatus] = useState<WsStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<unknown>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const readyRef = useRef(false);
  const intentionalCloseRef = useRef(false);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const pathRef = useRef(path);
  const connectImplRef = useRef<
    ((fromBackoff?: boolean) => Promise<void>) | null
  >(null);

  useEffect(() => {
    pathRef.current = path;
  }, [path]);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    clearReconnectTimer();
    readyRef.current = false;
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("disconnected");
    backoffRef.current = INITIAL_BACKOFF_MS;
  }, [clearReconnectTimer]);

  const connect = useCallback(
    async (fromBackoff = false) => {
      const p = pathRef.current;
      if (!p) return;
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      intentionalCloseRef.current = false;
      clearReconnectTimer();
      if (!fromBackoff) {
        backoffRef.current = INITIAL_BACKOFF_MS;
      }
      setStatus(fromBackoff ? "reconnecting" : "connecting");
      readyRef.current = false;

      const url = `${WS_URL}${p}`;
      const ws = new WebSocket(url);

      ws.onopen = () => {
        void (async () => {
          const token = await getIdToken();
          if (!token) {
            ws.close();
            setStatus("disconnected");
            return;
          }
          const appCheckToken = await getAppCheckTokenForApi();
          ws.send(
            JSON.stringify({
              type: "auth",
              token,
              ...(appCheckToken ? { app_check_token: appCheckToken } : {}),
            })
          );
        })();
      };
      ws.onclose = (ev) => {
        readyRef.current = false;
        wsRef.current = null;
        if (intentionalCloseRef.current) {
          setStatus("disconnected");
          backoffRef.current = INITIAL_BACKOFF_MS;
          return;
        }
        if (!pathRef.current) {
          setStatus("disconnected");
          return;
        }
        if (isPermanentCloseCode(ev.code)) {
          setStatus("disconnected");
          backoffRef.current = INITIAL_BACKOFF_MS;
          return;
        }
        setStatus("reconnecting");
        const delay = jitter(Math.min(backoffRef.current, MAX_BACKOFF_MS));
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          void connectImplRef.current?.(true);
        }, delay);
      };
      ws.onerror = () => {
        readyRef.current = false;
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as { type?: string };
          setLastMessage(data);
          if (data?.type === "ready") {
            readyRef.current = true;
            backoffRef.current = INITIAL_BACKOFF_MS;
            setStatus("connected");
          }
        } catch {
          setLastMessage(e.data);
        }
      };

      wsRef.current = ws;
    },
    [clearReconnectTimer]
  );

  useEffect(() => {
    connectImplRef.current = connect;
  }, [connect]);

  const send = useCallback((data: unknown) => {
    if (
      wsRef.current?.readyState === WebSocket.OPEN &&
      readyRef.current
    ) {
      wsRef.current.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (
      wsRef.current?.readyState === WebSocket.OPEN &&
      readyRef.current
    ) {
      wsRef.current.send(data);
    }
  }, []);

  useEffect(
    () => () => {
      intentionalCloseRef.current = true;
      clearReconnectTimer();
      wsRef.current?.close();
      wsRef.current = null;
    },
    [clearReconnectTimer]
  );

  return { status, lastMessage, connect, send, sendBinary, disconnect };
}
