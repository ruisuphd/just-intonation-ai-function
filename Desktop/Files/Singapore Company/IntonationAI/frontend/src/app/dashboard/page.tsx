"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import Link from "next/link";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { api } from "@/lib/api";

export default function DashboardPage() {
  const { user } = useAuth();
  const displayName = user?.displayName ?? user?.email?.split("@")[0] ?? "there";
  const [stats, setStats] = useState<{
    total_sessions: number;
    warmup_sessions: number;
    average_score: number | null;
    practice_streak_days: number;
  } | null>(null);
  const [sessions, setSessions] = useState<
    { id: string; coach_type: string; started_at: string }[]
  >([]);

  useEffect(() => {
    api.getDashboardStats().then(setStats).catch(() => {});
    api.getSessionHistory().then((list) => {
      const mapped = (list as { id: string; coach_type?: string; coachType?: string; started_at?: string; startedAt?: string }[]).map(
        (s) => ({
          id: s.id,
          coach_type: s.coach_type ?? s.coachType ?? "vocal",
          started_at: s.started_at ?? s.startedAt ?? "",
        })
      );
      setSessions(mapped);
    }).catch(() => {});
  }, []);

  return (
    <RequireAuth>
    <div className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-2xl font-semibold text-[#1d1d1f]">
        Welcome back, {displayName}
      </h1>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-[#d2d2d7] bg-white p-5">
          <p className="text-sm text-[#6e6e73]">Total Sessions</p>
          <p className="mt-1 text-2xl font-semibold text-[#1d1d1f]">
            {stats?.total_sessions ?? 0}
          </p>
        </div>
        <div className="rounded-xl border border-[#d2d2d7] bg-white p-5">
          <p className="text-sm text-[#6e6e73]">Average Score</p>
          <p className="mt-1 text-2xl font-semibold text-[#1d1d1f]">
            {stats?.average_score != null ? `${stats.average_score}%` : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-[#d2d2d7] bg-white p-5">
          <p className="text-sm text-[#6e6e73]">Practice Streak</p>
          <p className="mt-1 text-2xl font-semibold text-[#1d1d1f]">
            {stats?.practice_streak_days ?? 0} days
          </p>
        </div>
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-medium text-[#1d1d1f]">Quick Start</h2>
        <div className="mt-3 flex flex-wrap gap-3">
          <Link
            href="/coach/vocal"
            className="rounded-xl bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ed]"
          >
            Vocal Coach
          </Link>
          <Link
            href="/coach/piano"
            className="rounded-xl bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ed]"
          >
            Piano Coach
          </Link>
          <Link
            href="/coach/guitar"
            className="rounded-xl bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ed]"
          >
            Guitar Coach
          </Link>
          <Link
            href="/assessment"
            className="rounded-xl border border-[#d2d2d7] px-4 py-2.5 text-sm font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
          >
            Skill Assessment
          </Link>
          <Link
            href="/warmup"
            className="rounded-xl border border-[#d2d2d7] px-4 py-2.5 text-sm font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
          >
            Warm-Up
          </Link>
        </div>
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-medium text-[#1d1d1f]">Recent Sessions</h2>
        <div className="mt-3 rounded-xl border border-[#d2d2d7] bg-white p-6">
          {sessions.length === 0 ? (
            <div className="text-center">
              <p className="text-[#6e6e73]">
                No sessions yet. Start your first coaching session!
              </p>
              <Link
                href="/coach/vocal"
                className="mt-3 inline-block text-sm font-medium text-[#0071e3] hover:underline"
              >
                Go to Vocal Coach →
              </Link>
            </div>
          ) : (
            <ul className="space-y-2">
              {sessions.slice(0, 10).map((s) => (
                <li
                  key={s.id}
                  className="flex items-center justify-between rounded-lg border border-[#d2d2d7] px-4 py-2"
                >
                  <span className="font-medium text-[#1d1d1f] capitalize">
                    {s.coach_type}
                  </span>
                  <span className="text-sm text-[#6e6e73]">
                    {new Date(s.started_at).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
    </RequireAuth>
  );
}
