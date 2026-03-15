"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import Notice from "@/components/ui/notice";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { ALL_PLATFORMS, normalizePlatforms } from "@/lib/platforms";

const STEP_COUNT = 5;

export default function Onboarding() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [formData, setFormData] = useState({
    companyName: "",
    website: "",
    industry: "",
    competitors: ["", "", ""],
    brandVoice: "",
    toneFormalCasual: 50,
    toneTechnicalAccessible: 50,
    targetAudience: "",
    keywords: ["", "", ""],
    digestEnabled: true,
    digestEmail: "",
    notificationTime: "07:00",
    platformsEnabled: ["linkedin", "x_twitter"],
    linkedInConnected: false,
    xConnected: false,
  });

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/");
    }
  }, [authLoading, user, router]);

  useEffect(() => {
    if (user?.email) {
      setFormData((prev) => ({
        ...prev,
        digestEmail: prev.digestEmail || user.email || "",
      }));
    }
  }, [user]);

  const progressWidth = useMemo(() => `${((step - 1) / (STEP_COUNT - 1)) * 100}%`, [step]);

  function updateArrayField(
    field: "competitors" | "keywords",
    index: number,
    value: string,
  ) {
    setFormData((prev) => {
      const next = [...prev[field]];
      next[index] = value;
      return { ...prev, [field]: next };
    });
  }

  function togglePlatform(platformId: string) {
    setFormData((prev) => ({
      ...prev,
      platformsEnabled: prev.platformsEnabled.includes(platformId)
        ? prev.platformsEnabled.filter((item) => item !== platformId)
        : normalizePlatforms([...prev.platformsEnabled, platformId]),
    }));
  }

  async function handleSubmit() {
    setSaving(true);
    setError("");
    try {
      const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      await apiFetch("/onboarding/create-tenant", {
        method: "POST",
        body: JSON.stringify({
          company_name: formData.companyName,
          website_url: formData.website,
          industry: formData.industry || "Other",
          description: formData.brandVoice,
          target_audience: formData.targetAudience,
          tone: formData.toneFormalCasual >= 55 ? "casual" : "professional",
          language: "en",
          timezone: browserTimezone,
          competitor_names: formData.competitors.filter((item) => item.trim()),
          industry_keywords: formData.keywords.filter((item) => item.trim()),
          platforms_enabled: formData.platformsEnabled,
          daily_digest_enabled: formData.digestEnabled,
          daily_digest_email: formData.digestEmail,
          notification_time: formData.notificationTime,
          tone_formal_casual: formData.toneFormalCasual,
          tone_technical_accessible: formData.toneTechnicalAccessible,
        }),
      });
      await apiFetch("/onboarding/complete", { method: "POST" });
      router.push("/dashboard");
    } catch (err: any) {
      setError(err?.message || "Unable to complete onboarding.");
    } finally {
      setSaving(false);
    }
  }

  const handleNext = () => {
    if (step < STEP_COUNT) {
      setStep((current) => current + 1);
      return;
    }
    void handleSubmit();
  };

  const handleSkip = () => {
    if (step < STEP_COUNT) {
      setStep((current) => current + 1);
    }
  };

  const handleBack = () => {
    if (step > 1) setStep((current) => current - 1);
  };

  if (authLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-apple-bg">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-text border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center bg-apple-bg px-4 py-20">
      <div className="w-full max-w-xl rounded-apple bg-apple-card p-10 shadow-apple">
        <div className="mb-8 text-center">
          <h1 className="mb-2 text-3xl font-semibold tracking-tight text-apple-text">
            Welcome to AutoMark
          </h1>
          <p className="text-apple-secondary">Let&apos;s set up your workspace.</p>
        </div>

        <div className="relative mb-10 flex items-center justify-between">
          <div className="absolute left-0 top-1/2 -z-10 h-1 w-full -translate-y-1/2 rounded-full bg-apple-border" />
          <div
            className="absolute left-0 top-1/2 -z-10 h-1 -translate-y-1/2 rounded-full bg-apple-blue transition-all duration-300"
            style={{ width: progressWidth }}
          />
          {Array.from({ length: STEP_COUNT }, (_, index) => index + 1).map((value) => (
            <div
              key={value}
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                step >= value
                  ? "bg-apple-blue text-white"
                  : "border-2 border-apple-border bg-apple-card text-apple-secondary"
              }`}
            >
              {value}
            </div>
          ))}
        </div>

        {error && (
          <div className="mb-6">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-6">
            <h2 className="text-xl font-medium text-apple-text">Company Details</h2>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Company Name
                </label>
                <input
                  type="text"
                  className="w-full"
                  placeholder="Acme Corp"
                  value={formData.companyName}
                  onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Website URL
                </label>
                <input
                  type="url"
                  className="w-full"
                  placeholder="https://acme.com"
                  value={formData.website}
                  onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Industry
                </label>
                <input
                  type="text"
                  className="w-full"
                  placeholder="AI consulting"
                  value={formData.industry}
                  onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Main Competitor <span className="text-apple-secondary/60 font-normal">(optional)</span>
                </label>
                <input
                  key="competitor-0"
                  type="text"
                  className="w-full"
                  placeholder="Competitor name"
                  value={formData.competitors[0]}
                  onChange={(e) => updateArrayField("competitors", 0, e.target.value)}
                />
                <p className="mt-1 text-xs text-apple-secondary/60">We&apos;ll set up competitor tracking later in Settings.</p>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <div className="flex items-start justify-between">
              <h2 className="text-xl font-medium text-apple-text">Brand Voice <span className="text-sm font-normal text-apple-secondary">(optional)</span></h2>
              <button type="button" onClick={handleSkip} className="text-sm text-apple-blue hover:underline">Skip for now</button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Describe your positioning, tone, and key messages
                </label>
                <textarea
                  className="h-32 w-full resize-none"
                  placeholder="Professional, innovative, yet approachable..."
                  value={formData.brandVoice}
                  onChange={(e) => setFormData({ ...formData, brandVoice: e.target.value })}
                />
                <p className="mt-1 text-xs text-apple-secondary/60">We&apos;ll set this up later if you prefer.</p>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-apple-secondary">
                  Formal vs Casual
                </label>
                <div className="flex items-center gap-4">
                  <span className="w-16 text-right text-xs text-apple-secondary">Formal</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={formData.toneFormalCasual}
                    onChange={(e) =>
                      setFormData({ ...formData, toneFormalCasual: Number(e.target.value) })
                    }
                    className="flex-1 accent-apple-blue"
                  />
                  <span className="w-16 text-xs text-apple-secondary">Casual</span>
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-apple-secondary">
                  Technical vs Accessible
                </label>
                <div className="flex items-center gap-4">
                  <span className="w-16 text-right text-xs text-apple-secondary">Technical</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={formData.toneTechnicalAccessible}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        toneTechnicalAccessible: Number(e.target.value),
                      })
                    }
                    className="flex-1 accent-apple-blue"
                  />
                  <span className="w-16 text-xs text-apple-secondary">Accessible</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6">
            <div className="flex items-start justify-between">
              <h2 className="text-xl font-medium text-apple-text">Target Audience <span className="text-sm font-normal text-apple-secondary">(optional)</span></h2>
              <button type="button" onClick={handleSkip} className="text-sm text-apple-blue hover:underline">Skip for now</button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Who are your ideal customers?
                </label>
                <textarea
                  className="h-28 w-full resize-none"
                  placeholder="CTOs at fintech companies in Singapore..."
                  value={formData.targetAudience}
                  onChange={(e) => setFormData({ ...formData, targetAudience: e.target.value })}
                />
                <p className="mt-1 text-xs text-apple-secondary/60">We&apos;ll set this up later if you prefer.</p>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-apple-secondary">
                  Keywords <span className="font-normal text-apple-secondary/60">(optional)</span>
                </label>
                <div className="space-y-2">
                  {formData.keywords.map((value, index) => (
                    <input
                      key={`keyword-${index}`}
                      type="text"
                      className="w-full"
                      placeholder={`Keyword ${index + 1}`}
                      value={value}
                      onChange={(e) => updateArrayField("keywords", index, e.target.value)}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-6">
            <div className="flex items-start justify-between">
              <h2 className="text-xl font-medium text-apple-text">Digest Settings <span className="text-sm font-normal text-apple-secondary">(optional)</span></h2>
              <button type="button" onClick={handleSkip} className="text-sm text-apple-blue hover:underline">Skip for now</button>
            </div>
            <div className="space-y-4">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={formData.digestEnabled}
                  onChange={(e) => setFormData({ ...formData, digestEnabled: e.target.checked })}
                  className="h-4 w-4 rounded border-apple-border accent-apple-blue"
                />
                <span className="text-sm font-medium">Daily email digest</span>
              </label>
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Delivery email
                </label>
                <input
                  type="email"
                  className="w-full"
                  value={formData.digestEmail}
                  onChange={(e) => setFormData({ ...formData, digestEmail: e.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-apple-secondary">
                  Delivery time
                </label>
                <input
                  type="time"
                  className="w-48"
                  value={formData.notificationTime}
                  onChange={(e) => setFormData({ ...formData, notificationTime: e.target.value })}
                />
              </div>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-6">
            <h2 className="text-xl font-medium text-apple-text">Platforms</h2>
            <p className="text-sm text-apple-secondary">
              Choose the platforms AutoMark should prepare content for. Direct OAuth publishing
              will remain disabled until platform credentials are connected.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {ALL_PLATFORMS.map((platform) => (
                <label
                  key={platform.id}
                  className="flex items-center gap-3 rounded-apple-sm border border-apple-border px-3 py-3"
                >
                  <input
                    type="checkbox"
                    checked={formData.platformsEnabled.includes(platform.id)}
                    onChange={() => togglePlatform(platform.id)}
                    className="h-4 w-4 rounded border-apple-border accent-apple-blue"
                  />
                  <span className="text-sm">{platform.label}</span>
                </label>
              ))}
            </div>
            <div className="rounded-apple-sm border border-apple-border bg-apple-bg p-4">
              <p className="text-sm text-apple-secondary">
                You can connect your LinkedIn and X accounts after setup in{" "}
                <span className="font-medium text-apple-text">Settings &gt; Platforms</span>.
                This enables direct publishing from AutoMark to your social profiles.
              </p>
            </div>
          </div>
        )}

        <div className="mt-10 flex items-center justify-between border-t border-apple-border/50 pt-6">
          <button
            onClick={handleBack}
            disabled={step === 1 || saving}
            className={`rounded-full px-6 py-2.5 text-[15px] font-medium transition-colors ${
              step === 1 || saving
                ? "cursor-not-allowed text-apple-secondary/50"
                : "text-apple-text hover:bg-apple-border/30"
            }`}
          >
            Back
          </button>
          <button
            onClick={handleNext}
            disabled={saving || !formData.companyName.trim()}
            className="rounded-full bg-apple-blue px-6 py-2.5 text-[15px] font-medium text-white shadow-sm hover:bg-apple-blue-hover disabled:opacity-50"
          >
            {saving ? "Saving…" : step === STEP_COUNT ? "Complete Setup" : "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
