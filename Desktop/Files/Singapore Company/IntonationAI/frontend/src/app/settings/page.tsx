"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { signOut } from "@/lib/firebase";
import { api } from "@/lib/api";
import { getStoredMicId, setStoredMicId } from "@/lib/mic-preference";
import { RequireAuth } from "@/components/auth/RequireAuth";

export default function SettingsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [entitlements, setEntitlements] = useState<{
    plan: string;
    is_essential: boolean;
    is_pro: boolean;
    remaining_free_sessions: number;
  } | null>(null);

  useEffect(() => {
    navigator.mediaDevices
      .enumerateDevices()
      .then((list) => {
        const mics = list.filter((d) => d.kind === "audioinput");
        setDevices(mics);
        const stored = getStoredMicId();
        if (stored && mics.some((d) => d.deviceId === stored)) {
          setSelectedDeviceId(stored);
        } else if (mics.length && !selectedDeviceId) {
          setSelectedDeviceId(mics[0].deviceId);
        }
      })
      .catch(() => {});
  }, [selectedDeviceId]);

  const handleMicChange = (deviceId: string) => {
    setSelectedDeviceId(deviceId);
    setStoredMicId(deviceId);
  };

  useEffect(() => {
    api
      .getEntitlements()
      .then(setEntitlements)
      .catch(() => {});
  }, []);

  const handleSignOut = async () => {
    await signOut();
    router.push("/");
  };

  return (
    <RequireAuth>
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h1 className="text-2xl font-semibold text-[#1d1d1f]">Settings</h1>

      <section className="mt-8 rounded-xl border border-[#d2d2d7] bg-white p-6">
        <h2 className="text-lg font-medium text-[#1d1d1f]">Profile</h2>
        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-sm text-[#6e6e73]">Display name</label>
            <p className="mt-1 text-[#1d1d1f]">
              {user?.displayName || "—"}
            </p>
          </div>
          <div>
            <label className="block text-sm text-[#6e6e73]">Email</label>
            <p className="mt-1 text-[#1d1d1f]">{user?.email || "—"}</p>
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-xl border border-[#d2d2d7] bg-white p-6">
        <h2 className="text-lg font-medium text-[#1d1d1f]">Subscription</h2>
        <div className="mt-4 flex items-center justify-between">
          <span
            className={`rounded-full px-3 py-1 text-sm ${
              entitlements?.is_pro
                ? "bg-[#1d1d1f] text-white"
                : entitlements?.is_essential
                  ? "bg-[#0071e3] text-white"
                  : "bg-[#f5f5f7] text-[#6e6e73]"
            }`}
          >
            {entitlements?.is_pro ? "Pro" : entitlements?.is_essential ? "Essential" : "Free"}
          </span>
          {!entitlements?.is_essential && (
            <Link
              href="/pricing"
              className="rounded-xl bg-[#0071e3] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#0077ed]"
            >
              Upgrade to Pro
            </Link>
          )}
        </div>
        {!entitlements?.is_essential &&
          entitlements &&
          (entitlements.remaining_free_sessions ?? -1) >= 0 && (
            <p className="mt-2 text-sm text-[#6e6e73]">
              {entitlements.remaining_free_sessions} coaching sessions left this
              week
            </p>
          )}
      </section>

      <section className="mt-6 rounded-xl border border-[#d2d2d7] bg-white p-6">
        <h2 className="text-lg font-medium text-[#1d1d1f]">Audio</h2>
        <div className="mt-4">
          <label htmlFor="mic" className="block text-sm text-[#6e6e73]">
            Microphone
          </label>
          <select
            id="mic"
            value={selectedDeviceId}
            onChange={(e) => handleMicChange(e.target.value)}
            className="mt-2 w-full rounded-xl border border-[#d2d2d7] bg-white px-3 py-2 text-[#1d1d1f] outline-none focus:border-[#0071e3]"
          >
            {devices.length === 0 ? (
              <option value="">No microphones found</option>
            ) : (
              devices.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label || `Microphone ${d.deviceId.slice(0, 8)}`}
                </option>
              ))
            )}
          </select>
        </div>
      </section>

      <div className="mt-8">
        <button
          type="button"
          onClick={handleSignOut}
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-100"
        >
          Sign Out
        </button>
      </div>
    </div>
    </RequireAuth>
  );
}
