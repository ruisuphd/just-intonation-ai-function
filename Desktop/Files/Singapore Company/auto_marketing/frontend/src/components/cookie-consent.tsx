"use client";

import { useState, useEffect } from "react";

interface CookieConsent {
  essential: boolean;
  analytics: boolean;
  marketing: boolean;
  timestamp: string;
}

const STORAGE_KEY = "cookie_consent";

function getConsent(): CookieConsent | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveConsent(consent: CookieConsent) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
  document.cookie = "cc_consent=1; path=/; max-age=31536000; SameSite=Lax";
}

export function hasAnalyticsConsent(): boolean {
  return getConsent()?.analytics ?? false;
}

export default function CookieConsentBanner() {
  const [visible, setVisible] = useState(false);
  const [showPrefs, setShowPrefs] = useState(false);
  const [analytics, setAnalytics] = useState(true);
  const [marketing, setMarketing] = useState(false);

  useEffect(() => {
    if (!getConsent()) setVisible(true);
  }, []);

  if (!visible) return null;

  const accept = (consent: CookieConsent) => {
    saveConsent(consent);
    setVisible(false);
  };

  return (
    <div className="fixed bottom-0 inset-x-0 z-50 p-4">
      <div className="mx-auto max-w-2xl rounded-xl border border-gray-200 bg-white p-6 shadow-2xl">
        <p className="text-sm text-gray-700">
          We use cookies to ensure the app works properly and to improve your experience.{" "}
          <a href="/privacy" className="text-blue-600 underline">Privacy Policy</a>
        </p>

        {showPrefs && (
          <div className="mt-4 space-y-3 border-t pt-4">
            <label className="flex items-center gap-3 text-sm">
              <input type="checkbox" checked disabled className="rounded" />
              <span><strong>Essential</strong> — required for the app to function</span>
            </label>
            <label className="flex items-center gap-3 text-sm">
              <input type="checkbox" checked={analytics} onChange={e => setAnalytics(e.target.checked)} className="rounded" />
              <span><strong>Analytics</strong> — error tracking to improve reliability</span>
            </label>
            <label className="flex items-center gap-3 text-sm">
              <input type="checkbox" checked={marketing} onChange={e => setMarketing(e.target.checked)} className="rounded" />
              <span><strong>Marketing</strong> — currently none, reserved for future use</span>
            </label>
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-3">
          <button
            onClick={() => accept({ essential: true, analytics: true, marketing: true, timestamp: new Date().toISOString() })}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Accept All
          </button>
          {showPrefs ? (
            <button
              onClick={() => accept({ essential: true, analytics, marketing, timestamp: new Date().toISOString() })}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Save Preferences
            </button>
          ) : (
            <button
              onClick={() => setShowPrefs(true)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Manage Preferences
            </button>
          )}
          <button
            onClick={() => accept({ essential: true, analytics: false, marketing: false, timestamp: new Date().toISOString() })}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Reject Non-Essential
          </button>
        </div>
      </div>
    </div>
  );
}
