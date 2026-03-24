import { onAuthStateChanged } from "firebase/auth";

import { auth } from "./firebase";

function normalizeApiBase(url: string): string {
  return url.replace(/\/+$/, "");
}

/**
 * Backend origin for API calls. Set NEXT_PUBLIC_API_URL in all deployed builds
 * (see .env.example). Production builds fail without it (see next.config.mjs).
 */
export function getApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (fromEnv) return normalizeApiBase(fromEnv);
  if (process.env.NODE_ENV !== "production") {
    return "http://localhost:8080";
  }
  if (typeof window !== "undefined") {
    console.error(
      "NEXT_PUBLIC_API_URL is missing; rebuild the frontend with this variable set.",
    );
  }
  return "";
}

let authReadyPromise: Promise<void> | null = null;

export type ApiErrorOptions = {
  code?: string;
  traceId?: string;
  retryAfterSec?: number;
  extras?: Record<string, unknown>;
};

export class ApiError extends Error {
  status: number;
  detail?: unknown;
  code?: string;
  traceId?: string;
  retryAfterSec?: number;
  extras?: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    detail?: unknown,
    opts?: ApiErrorOptions,
  ) {
    super(typeof message === "string" ? message : "API error");
    this.name = "ApiError";
    this.status = status;
    this.detail = detail ?? (typeof message === "object" ? message : undefined);
    if (opts) {
      this.code = opts.code;
      this.traceId = opts.traceId;
      this.retryAfterSec = opts.retryAfterSec;
      this.extras = opts.extras;
    }
  }
}

function newRequestId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeErrorDetail(body: unknown): unknown {
  if (body && typeof body === "object" && "detail" in body) {
    return (body as { detail: unknown }).detail;
  }
  return body;
}

function isLegalAcceptanceRequired(detail: unknown): boolean {
  return (
    typeof detail === "object" &&
    detail !== null &&
    "error" in detail &&
    (detail as { error: string }).error === "legal_acceptance_required"
  );
}

function parseApiError(
  status: number,
  body: Record<string, unknown>,
  res: Response,
): ApiError {
  const detail = normalizeErrorDetail(body);
  const code = typeof body.error === "string" ? body.error : undefined;
  const traceId =
    (typeof body.trace_id === "string" ? body.trace_id : undefined) ??
    res.headers.get("X-Request-ID") ??
    undefined;
  const known = new Set(["detail", "error", "trace_id", "fields"]);
  const extras: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(body)) {
    if (!known.has(k)) extras[k] = v;
  }
  let msg =
    typeof detail === "string"
      ? detail
      : typeof body.detail === "string"
        ? body.detail
        : `API error ${status}`;
  const retryRaw = res.headers.get("Retry-After");
  const retryParsed = retryRaw ? parseInt(retryRaw, 10) : NaN;
  const retryAfterSec = Number.isFinite(retryParsed) ? retryParsed : undefined;
  if (status === 429 && retryAfterSec !== undefined) {
    msg = `${msg} Try again in ${retryAfterSec}s.`;
  }

  return new ApiError(status, msg, detail, {
    code,
    traceId: traceId ?? undefined,
    retryAfterSec,
    extras: Object.keys(extras).length ? extras : undefined,
  });
}

async function waitForAuthReady() {
  const firebaseAuth = auth;
  if (!firebaseAuth || firebaseAuth.currentUser) return;
  if (!authReadyPromise) {
    authReadyPromise = new Promise((resolve) => {
      const unsubscribe = onAuthStateChanged(firebaseAuth, () => {
        unsubscribe();
        resolve();
      });
    });
  }
  await authReadyPromise;
}

async function getAuthHeaders(forceRefresh = false): Promise<Record<string, string>> {
  await waitForAuthReady();
  const user = auth?.currentUser;
  if (!user) return {};
  const token = await user.getIdToken(forceRefresh);
  return { Authorization: `Bearer ${token}` };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function buildFetchHeaders(
  options: RequestInit,
  forceRefresh: boolean,
  requestId: string,
): Promise<Record<string, string>> {
  const authHeaders = await getAuthHeaders(forceRefresh);
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  return {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    "X-Request-ID": requestId,
    ...authHeaders,
    ...(options.headers as Record<string, string> | undefined),
  };
}

const GET_RETRY_STATUSES = new Set([502, 503, 504]);
const GET_MAX_RETRIES = 2;

async function fetchWithAuthRetry(
  url: string,
  options: RequestInit,
  requestId: string,
): Promise<Response> {
  let headers = await buildFetchHeaders(options, false, requestId);
  let res = await fetch(url, { ...options, headers });
  if (res.status === 401 && auth?.currentUser) {
    headers = await buildFetchHeaders(options, true, requestId);
    res = await fetch(url, { ...options, headers });
  }
  return res;
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const base = getApiBase();
  const method = options.method || "GET";
  const target = `${base}${path}`;
  const requestId = newRequestId();

  let res = await fetchWithAuthRetry(target, options, requestId);

  if (method === "GET" && GET_RETRY_STATUSES.has(res.status)) {
    for (let attempt = 0; attempt < GET_MAX_RETRIES; attempt++) {
      await sleep(300 * (attempt + 1) + Math.random() * 200);
      res = await fetchWithAuthRetry(target, options, requestId);
      if (!GET_RETRY_STATUSES.has(res.status)) break;
    }
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const err = parseApiError(res.status, body, res);

    if (
      res.status === 403 &&
      isLegalAcceptanceRequired(err.detail) &&
      typeof window !== "undefined" &&
      !path.includes("/api/legal/accept")
    ) {
      const safePath = `${window.location.pathname}${window.location.search}`;
      window.location.assign(`/legal/accept?redirect=${encodeURIComponent(safePath)}`);
    }

    throw err;
  }
  return res.json();
}

export interface ChatStreamResult {
  reply: string;
  settings_updated: Record<string, unknown>;
  suggested_questions: string[];
}

/** POST /api/chat/stream — SSE with { delta } chunks then { done, reply, ... } */
const CHAT_STREAM_TIMEOUT_MS = 120_000;

export async function apiChatStream(
  messages: { role: string; content: string }[],
  onDelta: (chunk: string) => void,
): Promise<ChatStreamResult> {
  const base = getApiBase();
  const target = `${base}/api/chat/stream`;
  const requestId = newRequestId();
  const abort = new AbortController();
  const deadline = setTimeout(() => abort.abort(), CHAT_STREAM_TIMEOUT_MS);
  const postInit: RequestInit = {
    method: "POST",
    body: JSON.stringify({ messages }),
    signal: abort.signal,
  };
  let res: Response;
  try {
    res = await fetchWithAuthRetry(target, postInit, requestId);
  } catch (e) {
    clearTimeout(deadline);
    if (e instanceof Error && e.name === "AbortError") {
      throw new ApiError(504, "The assistant took too long to respond. Try a shorter question.", undefined, {
        code: "CHAT_TIMEOUT",
      });
    }
    throw e;
  }
  clearTimeout(deadline);

  if (res.status === 429) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    throw parseApiError(429, body, res);
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const err = parseApiError(res.status, body, res);

    if (
      res.status === 403 &&
      isLegalAcceptanceRequired(err.detail) &&
      typeof window !== "undefined"
    ) {
      const safePath = `${window.location.pathname}${window.location.search}`;
      window.location.assign(`/legal/accept?redirect=${encodeURIComponent(safePath)}`);
    }

    throw err;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new ApiError(500, "No response body", undefined, {
      traceId: res.headers.get("X-Request-ID") ?? undefined,
    });
  }

  const dec = new TextDecoder();
  let carry = "";
  let result: ChatStreamResult | null = null;
  const streamStarted = Date.now();

  while (true) {
    if (Date.now() - streamStarted > CHAT_STREAM_TIMEOUT_MS) {
      await reader.cancel().catch(() => {});
      throw new ApiError(504, "The assistant took too long to respond. Try a shorter question.", undefined, {
        code: "CHAT_TIMEOUT",
      });
    }
    const { done, value } = await reader.read();
    if (done) break;
    carry += dec.decode(value, { stream: true });
    const blocks = carry.split("\n\n");
    carry = blocks.pop() ?? "";
    for (const block of blocks) {
      const line = block.trim();
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6);
      let obj: Record<string, unknown>;
      try {
        obj = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        continue;
      }
      if (typeof obj.delta === "string" && obj.delta.length) {
        onDelta(obj.delta);
      }
      if (obj.done === true) {
        result = {
          reply: typeof obj.reply === "string" ? obj.reply : "",
          settings_updated:
            obj.settings_updated && typeof obj.settings_updated === "object"
              ? (obj.settings_updated as Record<string, unknown>)
              : {},
          suggested_questions: Array.isArray(obj.suggested_questions)
            ? (obj.suggested_questions as string[])
            : [],
        };
      }
    }
  }

  if (!result) {
    throw new ApiError(500, "Stream ended without completion", undefined);
  }
  return result;
}

export async function apiFetchBlob(
  path: string,
  options: RequestInit = {},
): Promise<Blob> {
  const requestId = newRequestId();
  const url = `${getApiBase()}${path}`;
  let res = await fetchWithAuthRetry(url, options, requestId);
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    throw parseApiError(res.status, body, res);
  }
  return res.blob();
}
