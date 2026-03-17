"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  signInWithGoogle,
  signInWithEmail,
  signUpWithEmail,
  resetPassword,
  verifyEmail,
} from "@/lib/firebase";

export default function LoginPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [user, loading, router]);

  const handleGoogle = async () => {
    setBusy(true);
    setError("");
    try {
      await signInWithGoogle();
    } catch (e: any) {
      if (e?.code !== "auth/popup-closed-by-user") {
        setError(e.message || "Google sign-in failed.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await resetPassword(email);
      setResetSent(true);
    } catch (err: any) {
      if (err.code === "auth/user-not-found") {
        setError("No account found with this email.");
      } else {
        setError("Failed to send reset email. Try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "signup") {
        await signUpWithEmail(email, password);
        try { await verifyEmail(); } catch {} // Non-blocking
      } else {
        await signInWithEmail(email, password);
      }
    } catch (e: any) {
      setError(
        e.code === "auth/user-not-found" || e.code === "auth/wrong-password"
          ? "Invalid email or password."
          : e.code === "auth/email-already-in-use"
          ? "An account with this email already exists."
          : e.code === "auth/weak-password"
          ? "Password must be at least 6 characters."
          : e.message || "Authentication failed."
      );
    } finally {
      setBusy(false);
    }
  };

  if (loading || user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-apple-bg">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-blue border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-apple-bg">
      {/* Left panel — branding & value prop */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-[#0a0a0a] px-12 py-12 text-white">
        <div>
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="IntoMarketing" className="h-8 w-8 rounded-lg object-contain bg-white" />
            <span className="text-lg font-semibold">IntoMarketing</span>
          </div>
        </div>
        <div className="space-y-8">
          <div>
            <h1 className="text-4xl font-bold leading-tight">
              Your AI marketing team,<br />working while you sleep.
            </h1>
            <p className="mt-4 text-lg text-gray-400 leading-relaxed">
              IntoMarketing generates daily social posts, monitors market signals, qualifies leads, and sends your morning brief — fully automated.
            </p>
          </div>
          <div className="space-y-4">
            {[
              { icon: "✦", title: "Daily content across 6 platforms", desc: "LinkedIn, X, Instagram, TikTok, Google Business, Xiaohongshu" },
              { icon: "◉", title: "Market intelligence on autopilot", desc: "Monitors news, competitor signals, and buying intent 24/7" },
              { icon: "◈", title: "Lead detection & outreach drafts", desc: "Identifies warm prospects and generates personalised messages" },
            ].map((f) => (
              <div key={f.title} className="flex items-start gap-3">
                <span className="mt-0.5 text-apple-blue text-lg">{f.icon}</span>
                <div>
                  <p className="font-medium">{f.title}</p>
                  <p className="text-sm text-gray-400">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-gray-600">
          Every account includes our Starter plan — free forever.
        </p>
      </div>

      {/* Right panel — auth form */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <img src="/logo.png" alt="IntoMarketing" className="h-8 w-8 rounded-lg object-contain bg-white border border-apple-border" />
            <span className="text-lg font-semibold">IntoMarketing</span>
          </div>

          <h2 className="text-2xl font-semibold text-apple-text">
            {mode === "signin" ? "Welcome back" : "Create your account"}
          </h2>
          <p className="mt-1 text-sm text-apple-secondary">
            {mode === "signin"
              ? "Sign in to your workspace."
              : "Start your free account — no credit card required."}
          </p>

          {error && (
            <div className="mt-4 rounded-apple-sm bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            onClick={handleGoogle}
            disabled={busy}
            className="mt-6 flex w-full items-center justify-center gap-3 rounded-apple-sm border border-apple-border bg-white py-2.5 text-sm font-medium text-apple-text shadow-apple hover:bg-apple-bg disabled:opacity-50 transition-colors"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>

          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-apple-border" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-apple-bg px-3 text-xs text-apple-secondary">or continue with email</span>
            </div>
          </div>

          {forgotMode && resetSent ? (
            <div className="mt-6 text-center">
              <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-apple-sm px-4 py-3">
                Reset link sent! Check your inbox.
              </p>
              <button onClick={() => { setForgotMode(false); setResetSent(false); setError(""); }} className="mt-4 text-sm text-apple-blue hover:underline">
                Back to sign in
              </button>
            </div>
          ) : forgotMode && !resetSent ? (
            <form onSubmit={handleResetPassword} className="mt-6 space-y-3">
              <p className="text-sm text-apple-secondary">Enter your email to receive a password reset link.</p>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-apple-sm border border-apple-border bg-white px-3 py-2.5 text-sm text-apple-text placeholder:text-apple-secondary focus:border-apple-blue focus:outline-none focus:ring-1 focus:ring-apple-blue"
              />
              <button type="submit" disabled={busy} className="w-full rounded-apple-sm bg-apple-blue py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50 transition-colors">
                {busy ? "Sending…" : "Send reset link"}
              </button>
              <button type="button" onClick={() => { setForgotMode(false); setError(""); }} className="w-full text-sm text-apple-blue hover:underline">
                Back to sign in
              </button>
            </form>
          ) : (
            <form onSubmit={handleEmail} className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-apple-secondary">Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full rounded-apple-sm border border-apple-border bg-white px-3 py-2.5 text-sm text-apple-text placeholder:text-apple-secondary focus:border-apple-blue focus:outline-none focus:ring-1 focus:ring-apple-blue"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-apple-secondary">Password</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-apple-sm border border-apple-border bg-white px-3 py-2.5 text-sm text-apple-text placeholder:text-apple-secondary focus:border-apple-blue focus:outline-none focus:ring-1 focus:ring-apple-blue"
                />
              </div>
              {mode === "signin" && (
                <button
                  type="button"
                  onClick={() => { setForgotMode(true); setError(""); }}
                  className="text-xs text-apple-blue hover:underline"
                >
                  Forgot password?
                </button>
              )}
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-apple-sm bg-apple-blue py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50 transition-colors"
              >
                {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
              </button>
            </form>
          )}

          <p className="mt-5 text-center text-sm text-apple-secondary">
            {mode === "signin" ? (
              <>
                Don&apos;t have an account?{" "}
                <button onClick={() => { setMode("signup"); setError(""); }} className="font-medium text-apple-blue hover:underline">
                  Sign up free
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button onClick={() => { setMode("signin"); setError(""); }} className="font-medium text-apple-blue hover:underline">
                  Sign in
                </button>
              </>
            )}
          </p>

          <p className="mt-6 text-center text-xs text-apple-secondary">
            By continuing, you agree to IntoMarketing&apos;s{" "}
            <a href="/terms" className="underline hover:text-apple-text">Terms of Service</a>{" "}
            and{" "}
            <a href="/privacy" className="underline hover:text-apple-text">Privacy Policy</a>.
          </p>
        </div>
      </div>
    </div>
  );
}
