import { onAuthStateChanged } from "firebase/auth";

import { auth } from "./firebase";

const PRODUCTION_API = "https://automark-api-qglnjkfpjq-as.a.run.app";

function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (
    typeof window !== "undefined" &&
    window.location?.hostname?.includes("hosted.app")
  ) {
    return PRODUCTION_API;
  }
  return "http://localhost:8080";
}
let authReadyPromise: Promise<void> | null = null;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
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

async function getAuthHeaders(): Promise<Record<string, string>> {
  await waitForAuthReady();
  const user = auth?.currentUser;
  if (!user) return {};
  const token = await user.getIdToken();
  return { Authorization: `Bearer ${token}` };
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const base = getApiBase();
  const authHeaders = await getAuthHeaders();
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...authHeaders,
    ...options.headers,
  };
  const res = await fetch(`${base}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || `API error ${res.status}`);
  }
  return res.json();
}

export async function apiFetchBlob(
  path: string,
  options: RequestInit = {},
): Promise<Blob> {
  const authHeaders = await getAuthHeaders();
  const headers = { ...authHeaders, ...options.headers };
  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || `API error ${res.status}`);
  }
  return res.blob();
}
