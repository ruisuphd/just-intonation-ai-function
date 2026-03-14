"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  signInWithGoogle,
  signInWithEmail,
  signUpWithEmail,
} from "@/lib/firebase";

export default function LoginPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [mode, setMode] = useState<"idle" | "email">("idle");
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [user, loading, router]);

  if (loading || user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-apple-bg">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-text border-t-transparent" />
      </div>
    );
  }

  async function handleGoogle() {
    setError("");
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch (e: any) {
      if (e?.code !== "auth/popup-closed-by-user") {
        setError(e?.message || "Sign-in failed");
      }
    }
    setBusy(false);
  }

  async function handleEmail(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (isSignUp) await signUpWithEmail(email, password);
      else await signInWithEmail(email, password);
    } catch (err: any) {
      const msg = err?.code?.replace("auth/", "").replace(/-/g, " ") || "Sign-in failed";
      setError(msg);
    }
    setBusy(false);
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-apple-bg px-6">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="mb-10 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-apple-text">
            <span className="text-xl font-bold text-white">A</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">AutoMark</h1>
          <p className="mt-2 text-[15px] text-apple-secondary">
            AI-powered marketing for your business.
          </p>
        </div>

        {/* OAuth buttons */}
        <div className="space-y-3">
          <button
            onClick={handleGoogle}
            disabled={busy}
            className="flex w-full items-center justify-center gap-3 rounded-apple bg-apple-card px-4 py-3 text-[15px] font-medium shadow-apple hover:shadow-apple-lg disabled:opacity-50"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Continue with Google
          </button>
        </div>
        <p className="mt-3 text-center text-xs text-apple-secondary">
          Every new account starts on Free and includes 7 days of Starter access.
        </p>

        {/* Divider */}
        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-apple-border" />
          <span className="text-xs text-apple-secondary">or</span>
          <div className="h-px flex-1 bg-apple-border" />
        </div>

        {/* Email */}
        {mode === "idle" ? (
          <button
            onClick={() => setMode("email")}
            className="w-full rounded-apple border border-apple-border bg-apple-card px-4 py-3 text-[15px] font-medium hover:shadow-apple"
          >
            Continue with Email
          </button>
        ) : (
          <form onSubmit={handleEmail} className="space-y-3">
            <input
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full"
              autoFocus
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full"
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-apple bg-apple-blue px-4 py-3 text-[15px] font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
            >
              {isSignUp ? "Create account" : "Sign in"}
            </button>
            <p className="text-center text-sm text-apple-secondary">
              {isSignUp ? "Already have an account?" : "Don\u2019t have an account?"}{" "}
              <button
                type="button"
                onClick={() => { setIsSignUp(!isSignUp); setError(""); }}
                className="font-medium text-apple-blue"
              >
                {isSignUp ? "Sign in" : "Create one"}
              </button>
            </p>
          </form>
        )}

        {error && (
          <p className="mt-4 text-center text-sm text-red-500">{error}</p>
        )}
      </div>
    </div>
  );
}
