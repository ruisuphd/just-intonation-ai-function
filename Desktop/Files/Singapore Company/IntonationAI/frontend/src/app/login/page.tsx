"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { signInEmail, signUpEmail, signInGoogle } from "@/lib/firebase";

type Mode = "signin" | "signup";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTo = searchParams.get("redirect") || "/dashboard";
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "signin") {
        await signInEmail(email, password);
      } else {
        await signUpEmail(email, password);
      }
      router.push(redirectTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setLoading(true);
    try {
      await signInGoogle();
      router.push(redirectTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fbfbfd] px-4">
      <div className="w-full max-w-sm rounded-2xl border border-[#d2d2d7] bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-[#1d1d1f]">
          {mode === "signin" ? "Sign In" : "Sign Up"}
        </h1>

        <div className="mt-4 flex rounded-xl border border-[#d2d2d7] bg-[#f5f5f7] p-1">
          <button
            type="button"
            onClick={() => setMode("signin")}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              mode === "signin"
                ? "bg-white text-[#1d1d1f] shadow-sm"
                : "text-[#6e6e73] hover:text-[#1d1d1f]"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setMode("signup")}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              mode === "signup"
                ? "bg-white text-[#1d1d1f] shadow-sm"
                : "text-[#6e6e73] hover:text-[#1d1d1f]"
            }`}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm text-[#6e6e73]">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="mt-1 w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[#1d1d1f] placeholder-[#6e6e73] outline-none focus:border-[#0071e3]"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm text-[#6e6e73]">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              className="mt-1 w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[#1d1d1f] placeholder-[#6e6e73] outline-none focus:border-[#0071e3]"
            />
          </div>
          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-[#0071e3] py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ed] disabled:opacity-50"
          >
            {loading ? "Please wait…" : mode === "signin" ? "Sign In" : "Sign Up"}
          </button>
        </form>

        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-[#d2d2d7]" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="bg-white px-2 text-[#6e6e73]">
                or continue with
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleGoogle}
            disabled={loading}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-[#d2d2d7] bg-white py-2.5 text-sm text-[#1d1d1f] transition hover:bg-[#f5f5f7] disabled:opacity-50"
          >
            <span className="text-lg">G</span>
            Google
          </button>
        </div>

        <p className="mt-6 text-center text-sm text-[#6e6e73]">
          <Link href="/" className="text-[#0071e3] hover:underline">
            ← Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-[#6e6e73]">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
