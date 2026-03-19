"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { api } from "@/lib/api";
import type { CoachType } from "@/types";

const INSTRUMENTS: { id: CoachType; label: string }[] = [
  { id: "vocal", label: "Voice" },
  { id: "piano", label: "Piano" },
  { id: "guitar", label: "Guitar" },
];

const LEVELS = [
  { id: "beginner", label: "Beginner" },
  { id: "intermediate", label: "Intermediate" },
  { id: "advanced", label: "Advanced" },
];

const GOALS = [
  "Improve technique",
  "Learn songs",
  "Sight-reading",
  "Performance prep",
  "General practice",
];

export default function AssessmentPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [instrument, setInstrument] = useState<CoachType | null>(null);
  const [level, setLevel] = useState<string | null>(null);
  const [goals, setGoals] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const toggleGoal = useCallback((g: string) => {
    setGoals((prev) =>
      prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]
    );
  }, []);

  const onComplete = useCallback(async () => {
    if (!instrument || !level) return;
    setSaving(true);
    try {
      await api.updateProfile({
        skill_profile: {
          primary_instrument: instrument,
          experience_level: level,
          goals,
        },
      });
      if (instrument === "vocal") router.push("/coach/vocal");
      else if (instrument === "piano") router.push("/coach/piano");
      else router.push("/coach/guitar");
    } catch {
      setSaving(false);
    }
  }, [instrument, level, goals, router]);

  return (
    <RequireAuth>
      <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-lg flex-col justify-center px-6 py-12">
        <h1 className="text-2xl font-bold text-[#1d1d1f]">
          Skill assessment
        </h1>
        <p className="mt-2 text-[#6e6e73]">
          Help us personalise your coaching.
        </p>

        {step === 1 && (
          <div className="mt-8">
            <p className="mb-4 text-sm font-medium text-[#1d1d1f]">
              Primary instrument
            </p>
            <div className="flex flex-col gap-3">
              {INSTRUMENTS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setInstrument(id)}
                  className={`rounded-xl border-2 px-4 py-3 text-left font-medium transition ${
                    instrument === id
                      ? "border-[#0071e3] bg-[#0071e3]/5 text-[#0071e3]"
                      : "border-[#d2d2d7] bg-white text-[#1d1d1f] hover:border-[#0071e3]/50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => instrument && setStep(2)}
              disabled={!instrument}
              className="mt-6 w-full rounded-xl bg-[#0071e3] py-3 font-medium text-white transition hover:bg-[#0077ed] disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="mt-8">
            <p className="mb-4 text-sm font-medium text-[#1d1d1f]">
              Experience level
            </p>
            <div className="flex flex-col gap-3">
              {LEVELS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setLevel(id)}
                  className={`rounded-xl border-2 px-4 py-3 text-left font-medium transition ${
                    level === id
                      ? "border-[#0071e3] bg-[#0071e3]/5 text-[#0071e3]"
                      : "border-[#d2d2d7] bg-white text-[#1d1d1f] hover:border-[#0071e3]/50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="flex-1 rounded-xl border border-[#d2d2d7] py-3 font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => level && setStep(3)}
                disabled={!level}
                className="flex-1 rounded-xl bg-[#0071e3] py-3 font-medium text-white transition hover:bg-[#0077ed] disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="mt-8">
            <p className="mb-4 text-sm font-medium text-[#1d1d1f]">
              Goals (optional)
            </p>
            <div className="flex flex-wrap gap-2">
              {GOALS.map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => toggleGoal(g)}
                  className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                    goals.includes(g)
                      ? "bg-[#0071e3] text-white"
                      : "bg-[#f5f5f7] text-[#1d1d1f] hover:bg-[#e5e5ea]"
                  }`}
                >
                  {g}
                </button>
              ))}
            </div>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="flex-1 rounded-xl border border-[#d2d2d7] py-3 font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
              >
                Back
              </button>
              <button
                type="button"
                onClick={onComplete}
                disabled={saving}
                className="flex-1 rounded-xl bg-[#0071e3] py-3 font-medium text-white transition hover:bg-[#0077ed] disabled:opacity-50"
              >
                {saving ? "Starting…" : "Start coaching"}
              </button>
            </div>
          </div>
        )}

        <Link
          href="/dashboard"
          className="mt-8 text-center text-sm text-[#0071e3] hover:underline"
        >
          Skip for now
        </Link>
      </div>
    </RequireAuth>
  );
}
