"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as Sentry from "@sentry/nextjs";
import { onAuthStateChanged } from "firebase/auth";
import {
  readAnalyticsConsent,
  COOKIE_CONSENT_UPDATED_EVENT,
} from "@/lib/cookie-consent-storage";
import { auth, type User } from "./firebase";

interface AuthState {
  user: User | null;
  loading: boolean;
}

const AuthContext = createContext<AuthState>({ user: null, loading: true });

function applySentryUser(user: User | null) {
  if (user && readAnalyticsConsent()) {
    Sentry.setUser({ id: user.uid, email: user.email ?? undefined });
  } else {
    Sentry.setUser(null);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, loading: true });

  useEffect(() => {
    if (!auth) {
      setState({ user: null, loading: false });
      return;
    }
    const unsub = onAuthStateChanged(auth, (user) => {
      setState({ user, loading: false });
      applySentryUser(user);
    });
    return unsub;
  }, []);

  useEffect(() => {
    const onConsentUpdated = () => {
      applySentryUser(auth?.currentUser ?? null);
    };
    window.addEventListener(COOKIE_CONSENT_UPDATED_EVENT, onConsentUpdated);
    return () =>
      window.removeEventListener(COOKIE_CONSENT_UPDATED_EVENT, onConsentUpdated);
  }, []);

  return (
    <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
