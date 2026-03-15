"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ALL_PLATFORMS, normalizePlatforms } from "@/lib/platforms";
import { COMPANY_DESCRIPTION_MAX_CHARS, TARGET_AUDIENCE_MAX_CHARS } from "@/lib/settings";
import Notice from "@/components/ui/notice";
import { formatStarterAccessDate } from "@/lib/billing";
import { apiFetch, apiFetchBlob } from "@/lib/api";
import type { BillingSummary, TenantProfile } from "@/types";

const TABS = [
  { id: "company", label: "Company" },
  { id: "brand_voice", label: "Brand Voice" },
  { id: "platforms", label: "Platforms" },
  { id: "notifications", label: "Notifications" },
  { id: "integrations", label: "Integrations" },
  { id: "billing", label: "Billing" },
  { id: "account", label: "Account & data" },
];

const COMMON_TIMEZONES = [
  "Pacific/Auckland",
  "Australia/Sydney",
  "Australia/Adelaide",
  "Australia/Perth",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Asia/Shanghai",
  "Asia/Hong_Kong",
  "Asia/Taipei",
  "Asia/Singapore",
  "Asia/Bangkok",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Europe/Moscow",
  "Europe/Istanbul",
  "Europe/Athens",
  "Europe/Helsinki",
  "Europe/Berlin",
  "Europe/Paris",
  "Europe/London",
  "Atlantic/Reykjavik",
  "America/Sao_Paulo",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
];

const PLAN_FEATURES: Record<string, string[]> = {
  free: [
    "Workspace access",
    "Company profile settings",
    "Billing and plan management",
    "7 days of Starter access on first login",
  ],
  starter: [
    "Core AI engine for daily content tasks",
    "Daily content for your selected platforms",
    "Market intelligence",
    "1 image/day",
    "Email digest",
  ],
  pro: [
    "Everything in Starter",
    "Advanced AI engine for premium workflows",
    "Lead detection & qualification",
    "Outreach drafts",
    "Email newsletter",
    "Bilingual content",
    "Advanced image generation",
    "Priority support",
  ],
};

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState("company");
  const [settings, setSettings] = useState<Partial<TenantProfile> | null>(null);
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [billingMessage, setBillingMessage] = useState<{
    tone: "success" | "warning" | "danger" | "neutral";
    text: string;
  } | null>(null);
  const [billingBusy, setBillingBusy] = useState<"starter" | "pro" | "portal" | null>(null);
  const [exporting, setExporting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteAcknowledged, setDeleteAcknowledged] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [companyName, setCompanyName] = useState("");
  const [description, setDescription] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [competitors, setCompetitors] = useState<string[]>([]);
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [digestEnabled, setDigestEnabled] = useState(true);
  const [digestEmail, setDigestEmail] = useState("");
  const [notificationTime, setNotificationTime] = useState("07:00");
  const [digestTimezone, setDigestTimezone] = useState("Asia/Singapore");
  const [toneFormalCasual, setToneFormalCasual] = useState(50);
  const [toneTechnicalAccessible, setToneTechnicalAccessible] = useState(50);
  const [brandGuidelinesFile, setBrandGuidelinesFile] = useState<File | null>(null);
  const [brandVoiceMessage, setBrandVoiceMessage] = useState("");
  const [oauthStatus, setOauthStatus] = useState<{ linkedin: boolean; x_twitter: boolean } | null>(null);

  // Integrations state
  const [integrationsLoading, setIntegrationsLoading] = useState(false);
  const [integrationsSaved, setIntegrationsSaved] = useState(false);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState(587);
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpFromEmail, setSmtpFromEmail] = useState("");
  const [smtpUseTls, setSmtpUseTls] = useState(true);
  const [smtpConfigured, setSmtpConfigured] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/");
  }, [user, authLoading, router]);

  const fetchOauthStatus = useCallback(async () => {
    if (!user) return;
    try {
      const status = await apiFetch<{ linkedin: boolean; x_twitter: boolean }>("/api/oauth/status");
      setOauthStatus(status);
    } catch {
      setOauthStatus(null);
    }
  }, [user]);

  const fetchSettings = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setPageError("");
    try {
      const [data, billingState] = await Promise.all([
        apiFetch<Partial<TenantProfile>>("/api/settings"),
        apiFetch<BillingSummary>("/billing/subscription"),
      ]);
      setSettings(data);
      setBilling(billingState);
      setCompanyName(data.company_name || "");
      setDescription(data.description || "");
      setTargetAudience(data.target_audience || "");
      setCompetitors(data.competitor_names || []);
      setPlatforms(normalizePlatforms(data.platforms_enabled || []));
      setDigestEnabled(data.daily_digest_enabled ?? true);
      setDigestEmail(data.daily_digest_email || "");
      setNotificationTime(data.notification_time || "07:00");
      setDigestTimezone(data.timezone || "Asia/Singapore");
      setToneFormalCasual((data as any).tone_formal_casual ?? 50);
      setToneTechnicalAccessible((data as any).tone_technical_accessible ?? 50);
    } catch (err: any) {
      setPageError(err.message || "Unable to load settings.");
    } finally {
      setLoading(false);
    }
    void fetchOauthStatus();
  }, [user, fetchOauthStatus]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setTab(params.get("tab") || "company");
    const checkoutState = params.get("checkout");
    if (checkoutState === "success") {
      setBillingMessage({
        tone: "success",
        text: "Checkout completed. Your billing status will refresh in a moment.",
      });
    } else if (checkoutState === "canceled") {
      setBillingMessage({
        tone: "warning",
        text: "Checkout was canceled. Your plan has not changed.",
      });
    }
  }, []);

  useEffect(() => {
    if (!authLoading && user) {
      fetchSettings();
    }
  }, [authLoading, user, fetchSettings]);

  async function handleSave(updates: Record<string, any>) {
    setSaving(true);
    setSaved(false);
    setPageError("");
    try {
      await apiFetch("/api/settings", { method: "PUT", body: JSON.stringify(updates) });
      setSettings((prev) => ({ ...(prev || {}), ...updates }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      return true;
    } catch (err: any) {
      setPageError(err.message || "Unable to save settings.");
      return false;
    }
    finally {
      setSaving(false);
    }
  }

  async function handleBrandVoiceSave() {
    setBrandVoiceMessage("");
    const savedSettings = await handleSave({
      tone_formal_casual: toneFormalCasual,
      tone_technical_accessible: toneTechnicalAccessible,
    });
    if (!savedSettings || !brandGuidelinesFile) {
      return;
    }

    const formData = new FormData();
    formData.append("file", brandGuidelinesFile);
    formData.append("doc_type", "brand_voice");

    try {
      await apiFetch("/api/documents", {
        method: "POST",
        body: formData,
      });
      setBrandVoiceMessage("Brand guidelines uploaded to your document workspace.");
      setBrandGuidelinesFile(null);
    } catch (err: any) {
      setBrandVoiceMessage("");
      setPageError(err.message || "Brand guidelines could not be uploaded.");
    }
  }

  function selectTab(nextTab: string) {
    setTab(nextTab);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", nextTab);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }

  async function handleBillingPortal() {
    setBillingBusy("portal");
    setBillingMessage(null);
    try {
      const data = await apiFetch("/billing/portal");
      if (data.url) window.location.href = data.url;
    } catch (err: any) {
      setBillingMessage({
        tone: "danger",
        text: err.message || "Unable to open the billing portal.",
      });
    }
    setBillingBusy(null);
  }

  async function handleCheckout(tier: "starter" | "pro") {
    setBillingBusy(tier);
    setBillingMessage(null);
    try {
      const data = await apiFetch("/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ tier }),
      });
      if (data.url) window.location.href = data.url;
    } catch (err: any) {
      setBillingMessage({
        tone: "danger",
        text: err.message || "Unable to start checkout.",
      });
    }
    setBillingBusy(null);
  }

  function billingSummaryText() {
    if (!billing) return "Loading billing details.";
    if (billing.is_internal) return "Internal test account with full access.";
    if (billing.access_source === "starter_access") {
      return `Starter trial access is included until ${formatStarterAccessDate(billing) || "the current access window ends"}.`;
    }
    if (billing.subscription_status === "past_due") {
      return "Your paid subscription needs attention before paid features are restored.";
    }
    if (billing.has_paid_subscription) {
      return `Paid subscription status: ${billing.subscription_status}.`;
    }
    return "You are currently on the Free plan.";
  }

  function currentAccessLabel() {
    if (!billing) return "Loading";
    if (billing.is_internal) return "Internal access";
    if (billing.access_source === "starter_access") return "Starter trial";
    if (billing.has_paid_subscription) {
      return `${billing.subscription_tier[0].toUpperCase()}${billing.subscription_tier.slice(1)} plan`;
    }
    return "Free plan";
  }

  function renderPlanAction(tier: "free" | "starter" | "pro") {
    if (!billing) return null;
    if (tier === "free") {
      return billing.effective_tier === "free" ? (
        <button
          disabled
          className="mt-5 w-full rounded-apple-sm border border-apple-border px-4 py-2.5 text-sm font-medium text-apple-secondary"
        >
          Current plan
        </button>
      ) : null;
    }

    if (billing.is_internal) {
      return (
        <button
          disabled
          className="mt-5 w-full rounded-apple-sm border border-apple-border px-4 py-2.5 text-sm font-medium text-apple-secondary"
        >
          Included with internal access
        </button>
      );
    }

    if (billing.effective_tier === tier) {
      const label =
        billing.access_source === "starter_access"
          ? "Included trial access"
          : billing.has_paid_subscription
            ? "Current plan"
            : "Current access";
      return (
        <button
          disabled
          className="mt-5 w-full rounded-apple-sm border border-apple-border px-4 py-2.5 text-sm font-medium text-apple-secondary"
        >
          {label}
        </button>
      );
    }

    if (billing.can_manage_billing && billing.has_paid_subscription) {
      return (
        <button
          onClick={handleBillingPortal}
          disabled={billingBusy !== null}
          className="mt-5 w-full rounded-apple-sm border border-apple-border px-4 py-2.5 text-sm font-medium hover:bg-apple-bg disabled:opacity-50"
        >
          {billingBusy === "portal" ? "Opening portal\u2026" : "Manage in portal"}
        </button>
      );
    }

    if (!billing.can_start_checkout) {
      return null;
    }

    return (
      <button
        onClick={() => handleCheckout(tier)}
        disabled={billingBusy !== null}
        className="mt-5 w-full rounded-apple-sm bg-apple-blue px-4 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
      >
        {billingBusy === tier
          ? "Redirecting\u2026"
          : tier === "starter" && billing.access_source === "starter_access"
            ? "Keep Starter after access ends"
            : tier === "pro"
              ? "Choose Pro"
              : "Choose Starter"}
      </button>
    );
  }

  if (authLoading || loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-apple-bg">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-text border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-apple-bg">
      {/* Top bar */}
      <header className="sticky top-0 z-50 border-b border-apple-border bg-apple-card/80 backdrop-blur-xl">
        <div className="mx-auto flex min-h-12 max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:h-12 sm:py-0">
          <Link href="/dashboard" className="text-sm font-medium text-apple-blue">
            &larr; Dashboard
          </Link>
          <h1 className="text-[15px] font-semibold">Settings</h1>
          <div className="w-20" />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-5 sm:py-6">
        {/* Tabs */}
        <div className="mb-6 overflow-x-auto rounded-apple-sm bg-apple-card p-1 shadow-apple [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          <div className="flex min-w-max gap-1 sm:min-w-0">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => selectTab(t.id)}
                className={`flex-none whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors sm:flex-1 ${
                  tab === t.id
                    ? "bg-apple-text text-white"
                    : "text-apple-secondary hover:bg-apple-bg"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {pageError && <Notice tone="danger">{pageError}</Notice>}

        {/* Company Tab */}
        {tab === "company" && (
          <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Company name</label>
                <input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="w-full" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Description</label>
                <textarea
                  value={description}
                  onChange={(e) =>
                    setDescription(e.target.value.slice(0, COMPANY_DESCRIPTION_MAX_CHARS))
                  }
                  rows={5}
                  className="w-full"
                />
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-apple-secondary">
                  <p>More detail here gives the AI better grounding for tone, positioning, and services.</p>
                  <p>
                    {description.length}/{COMPANY_DESCRIPTION_MAX_CHARS}
                  </p>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Target audience</label>
                <textarea
                  value={targetAudience}
                  onChange={(e) =>
                    setTargetAudience(e.target.value.slice(0, TARGET_AUDIENCE_MAX_CHARS))
                  }
                  rows={3}
                  className="w-full"
                />
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-apple-secondary">
                  <p>Describe who you want to reach, what they care about, and how they buy.</p>
                  <p>
                    {targetAudience.length}/{TARGET_AUDIENCE_MAX_CHARS}
                  </p>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Competitors (up to 5)</label>
                <div className="space-y-2">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <input
                      key={i}
                      type="text"
                      value={competitors[i] || ""}
                      onChange={(e) => {
                        const next = [...competitors];
                        next[i] = e.target.value;
                        setCompetitors(next.filter(Boolean));
                      }}
                      placeholder={`Competitor ${i + 1}`}
                      className="w-full"
                    />
                  ))}
                </div>
              </div>
            </div>
            <button
              onClick={() => handleSave({ company_name: companyName, description, target_audience: targetAudience, competitor_names: competitors.filter(Boolean) })}
              disabled={saving}
              className="mt-6 rounded-apple-sm bg-apple-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
            >
              {saved ? "Saved" : saving ? "Saving\u2026" : "Save changes"}
            </button>
          </div>
        )}

        {/* Brand Voice Tab */}
        {tab === "brand_voice" && (
          <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
            <h2 className="mb-4 text-lg font-semibold">Brand Voice Wizard</h2>
            <div className="space-y-6">
              <div>
                <label className="mb-2 block text-sm font-medium">Tone: Formal vs Casual</label>
                <div className="flex items-center gap-4">
                  <span className="w-16 text-right text-xs text-apple-secondary">Formal</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={toneFormalCasual}
                    onChange={(e) => setToneFormalCasual(Number(e.target.value))}
                    className="flex-1 accent-apple-blue"
                  />
                  <span className="w-16 text-xs text-apple-secondary">Casual</span>
                </div>
              </div>
              
              <div>
                <label className="mb-2 block text-sm font-medium">Tone: Technical vs Accessible</label>
                <div className="flex items-center gap-4">
                  <span className="w-16 text-right text-xs text-apple-secondary">Technical</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={toneTechnicalAccessible}
                    onChange={(e) => setToneTechnicalAccessible(Number(e.target.value))}
                    className="flex-1 accent-apple-blue"
                  />
                  <span className="w-16 text-xs text-apple-secondary">Accessible</span>
                </div>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium">Brand Guidelines (PDF)</label>
                <div className="relative flex flex-col items-center justify-center rounded-apple-sm border-2 border-dashed border-apple-border bg-apple-bg p-8 text-center transition-colors hover:bg-apple-border/10">
                  <input
                    type="file"
                    accept="application/pdf"
                    onChange={(e) => setBrandGuidelinesFile(e.target.files?.[0] || null)}
                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  />
                  <div className="text-apple-secondary">
                    {brandGuidelinesFile ? (
                      <p className="font-medium text-apple-text">{brandGuidelinesFile.name}</p>
                    ) : (
                      <>
                        <p className="font-medium">Click or drag PDF to upload</p>
                        <p className="mt-1 text-xs">Max size 10MB</p>
                      </>
                    )}
                  </div>
                </div>
                <p className="mt-2 text-xs text-apple-secondary">
                  Upload stores the file in your workspace document library. Retrieval sync can
                  process it in the next brand-context ingestion run.
                </p>
              </div>
            </div>
            {brandVoiceMessage && (
              <div className="mt-4">
                <Notice tone="success">{brandVoiceMessage}</Notice>
              </div>
            )}
            <button
              onClick={() => void handleBrandVoiceSave()}
              disabled={saving}
              className="mt-6 rounded-apple-sm bg-apple-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
            >
              {saved ? "Saved" : saving ? "Saving\u2026" : "Save Brand Voice"}
            </button>
          </div>
        )}

        {/* Platforms Tab */}
        {tab === "platforms" && (
          <div className="space-y-6">
            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
              <h2 className="mb-4 text-lg font-semibold">Direct Publishing</h2>
              <p className="mb-4 text-sm text-apple-secondary">
                Connect accounts for one-click publishing to LinkedIn and X. Scheduled posts
                will post directly to your connected accounts.
              </p>
              <div className="flex flex-wrap gap-3">
                <div className="flex items-center gap-3 rounded-apple-sm border border-apple-border bg-apple-bg px-4 py-3">
                  <span className="text-sm font-medium">LinkedIn</span>
                  {oauthStatus?.linkedin ? (
                    <span className="text-xs text-apple-secondary">Connected</span>
                  ) : null}
                  <button
                    onClick={async () => {
                      try {
                        const { redirect_url } = await apiFetch<{ redirect_url: string }>("/api/oauth/linkedin/authorize");
                        window.location.href = redirect_url;
                      } catch (err: any) {
                        setPageError(err.message || "Unable to start LinkedIn connection. Please check that OAuth credentials are configured.");
                      }
                    }}
                    className="rounded-apple-sm bg-apple-blue px-3 py-1.5 text-sm font-medium text-white hover:bg-apple-blue-hover"
                  >
                    {oauthStatus?.linkedin ? "Reconnect" : "Connect"}
                  </button>
                </div>
                <div className="flex items-center gap-3 rounded-apple-sm border border-apple-border bg-apple-bg px-4 py-3">
                  <span className="text-sm font-medium">X</span>
                  {oauthStatus?.x_twitter ? (
                    <span className="text-xs text-apple-secondary">Connected</span>
                  ) : null}
                  <button
                    onClick={async () => {
                      try {
                        const { redirect_url } = await apiFetch<{ redirect_url: string }>("/api/oauth/x/authorize");
                        window.location.href = redirect_url;
                      } catch (err: any) {
                        setPageError(err.message || "Unable to start X connection. Please check that OAuth credentials are configured.");
                      }
                    }}
                    className="rounded-apple-sm bg-apple-blue px-3 py-1.5 text-sm font-medium text-white hover:bg-apple-blue-hover"
                  >
                    {oauthStatus?.x_twitter ? "Reconnect" : "Connect"}
                  </button>
                </div>
              </div>
            </div>
            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-apple-secondary">
                Select which platforms AutoMark generates content for. Your saved choices
                drive the dashboard tabs, drafts, and calendar.
              </p>
              <p className="text-sm font-medium text-apple-secondary">
                {platforms.length} selected
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {ALL_PLATFORMS.map((p) => (
                <label
                  key={p.id}
                  className="flex items-center gap-3 rounded-apple-sm border border-apple-border px-3 py-3"
                >
                  <input
                    type="checkbox"
                    checked={platforms.includes(p.id)}
                    onChange={(e) => {
                      if (e.target.checked) setPlatforms(normalizePlatforms([...platforms, p.id]));
                      else setPlatforms(platforms.filter((x) => x !== p.id));
                    }}
                    className="h-4 w-4 rounded border-apple-border accent-apple-blue"
                  />
                  <span className="text-sm">{p.label}</span>
                </label>
              ))}
            </div>
            <button
              onClick={() => handleSave({ platforms_enabled: platforms })}
              disabled={saving || platforms.length === 0}
              className="mt-6 rounded-apple-sm bg-apple-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
            >
              {saved ? "Saved" : "Save platforms"}
            </button>
          </div>
          </div>
        )}

        {/* Notifications Tab */}
        {tab === "notifications" && (
          <div className="rounded-apple bg-apple-card p-6 shadow-apple">
            <div className="space-y-4">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={digestEnabled}
                  onChange={(e) => setDigestEnabled(e.target.checked)}
                  className="h-4 w-4 rounded border-apple-border accent-apple-blue"
                />
                <span className="text-sm font-medium">Daily email digest</span>
              </label>
              <div>
                <label className="mb-1 block text-sm font-medium">Digest email</label>
                <input type="email" value={digestEmail} onChange={(e) => setDigestEmail(e.target.value)} placeholder="you@company.com" className="w-full" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Notification time</label>
                <input type="time" value={notificationTime} onChange={(e) => setNotificationTime(e.target.value)} className="w-48" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Timezone</label>
                <select
                  value={digestTimezone}
                  onChange={(e) => setDigestTimezone(e.target.value)}
                  className="w-full rounded-apple-sm border border-apple-border bg-white px-3 py-2 text-sm"
                >
                  {COMMON_TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-apple-secondary">
                  Your daily digest email will be sent at the notification time in this timezone.
                </p>
              </div>
            </div>
            <button
              onClick={() =>
                handleSave({
                  daily_digest_enabled: digestEnabled,
                  daily_digest_email: digestEmail,
                  notification_time: notificationTime,
                  timezone: digestTimezone,
                })
              }
              disabled={saving}
              className="mt-6 rounded-apple-sm bg-apple-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
            >
              {saved ? "Saved" : "Save notifications"}
            </button>
          </div>
        )}

        {/* Integrations Tab */}
        {tab === "integrations" && (
          <IntegrationsTab
            loading={integrationsLoading}
            saved={integrationsSaved}
            smtpHost={smtpHost}
            setSmtpHost={setSmtpHost}
            smtpPort={smtpPort}
            setSmtpPort={setSmtpPort}
            smtpUser={smtpUser}
            setSmtpUser={setSmtpUser}
            smtpPassword={smtpPassword}
            setSmtpPassword={setSmtpPassword}
            smtpFromEmail={smtpFromEmail}
            setSmtpFromEmail={setSmtpFromEmail}
            smtpUseTls={smtpUseTls}
            setSmtpUseTls={setSmtpUseTls}
            smtpConfigured={smtpConfigured}
            onLoadConfig={async () => {
              setIntegrationsLoading(true);
              try {
                const smtpData = await apiFetch<any>("/api/admin/smtp-config");
                setSmtpHost(smtpData.smtp_host || "");
                setSmtpPort(smtpData.smtp_port || 587);
                setSmtpUser(smtpData.smtp_user || "");
                setSmtpPassword(smtpData.smtp_password || "");
                setSmtpFromEmail(smtpData.smtp_from_email || "");
                setSmtpUseTls(smtpData.smtp_use_tls ?? true);
                setSmtpConfigured(smtpData.configured || false);
              } catch (err: any) {
                setPageError(err.message || "Failed to load integration settings.");
              } finally {
                setIntegrationsLoading(false);
              }
            }}
            onSaveSMTP={async () => {
              setIntegrationsSaved(false);
              setPageError("");
              try {
                const updates: Record<string, any> = {};
                if (smtpHost) updates.smtp_host = smtpHost;
                if (smtpPort) updates.smtp_port = smtpPort;
                if (smtpUser) updates.smtp_user = smtpUser;
                if (smtpPassword && !smtpPassword.includes("*"))
                  updates.smtp_password = smtpPassword;
                if (smtpFromEmail) updates.smtp_from_email = smtpFromEmail;
                updates.smtp_use_tls = smtpUseTls;
                updates.smtp_use_ssl = !smtpUseTls;
                if (Object.keys(updates).length === 0) {
                  setPageError("Enter at least one SMTP field to save.");
                  return;
                }
                await apiFetch("/api/admin/smtp-config", {
                  method: "PUT",
                  body: JSON.stringify(updates),
                });
                setIntegrationsSaved(true);
                setSmtpConfigured(true);
                setTimeout(() => setIntegrationsSaved(false), 2000);
              } catch (err: any) {
                setPageError(err.message || "Failed to save SMTP configuration.");
              }
            }}
          />
        )}

        {/* Billing Tab */}
        {tab === "billing" && billing && (
          <div className="space-y-4">
            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-apple-secondary">Current access</p>
                  <p className="text-2xl font-semibold">{currentAccessLabel()}</p>
                  <p className="mt-1 text-xs text-apple-secondary">
                    {billingSummaryText()}
                  </p>
                </div>
                {billing.can_manage_billing && !billing.is_internal && (
                  <button
                    onClick={handleBillingPortal}
                    disabled={billingBusy !== null}
                    className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium hover:bg-apple-bg disabled:opacity-50"
                  >
                    {billingBusy === "portal" ? "Opening portal\u2026" : "Manage billing"}
                  </button>
                )}
              </div>
            </div>

            {billingMessage && (
              <Notice tone={billingMessage.tone}>{billingMessage.text}</Notice>
            )}

            <div className="grid gap-4 md:grid-cols-3">
              {(["free", "starter", "pro"] as const).map((tier) => (
                <div
                  key={tier}
                  className={`rounded-apple border p-6 ${
                    tier === billing.effective_tier
                      ? "border-apple-blue bg-blue-50/30"
                      : "border-apple-border bg-apple-card"
                  } shadow-apple`}
                >
                  <h3 className="text-lg font-semibold capitalize">{tier}</h3>
                  <ul className="mt-4 space-y-2">
                    {(PLAN_FEATURES[tier] || []).map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-apple-text">
                        <span className="mt-0.5 text-green-500">&#10003;</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  {renderPlanAction(tier)}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Account & data Tab */}
        {tab === "account" && (
          <div className="space-y-6">
            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
              <h2 className="mb-4 text-lg font-semibold">Data export</h2>
              <p className="mb-4 text-sm text-apple-secondary">
                Download a copy of all your account data (company profile, drafts, leads,
                intelligence, etc.) as a JSON ZIP file. Useful for backups and GDPR compliance.
              </p>
              <button
                onClick={async () => {
                  setExporting(true);
                  setPageError("");
                  try {
                    const blob = await apiFetchBlob("/api/account/export");
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = `automark-export-${new Date().toISOString().slice(0, 10)}.zip`;
                    a.click();
                    URL.revokeObjectURL(a.href);
                  } catch (e: any) {
                    setPageError(e.message || "Export failed");
                  } finally {
                    setExporting(false);
                  }
                }}
                disabled={exporting}
                className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium hover:bg-apple-bg disabled:opacity-50"
              >
                {exporting ? "Preparing\u2026" : "Export my data"}
              </button>
            </div>

            <div className="rounded-apple border border-red-200 bg-red-50/30 p-5 shadow-apple sm:p-6">
              <h2 className="mb-2 text-lg font-semibold text-red-700">Delete account</h2>
              <p className="mb-4 text-sm text-apple-secondary">
                Permanently delete your account and all associated data. This cannot be undone.
              </p>
              <div className="mb-4 space-y-2">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={deleteAcknowledged}
                    onChange={(e) => setDeleteAcknowledged(e.target.checked)}
                    className="h-4 w-4 rounded border-apple-border"
                  />
                  <span className="text-sm">I understand this action is irreversible</span>
                </label>
                <input
                  type="text"
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  placeholder='Type DELETE to confirm'
                  className="w-full max-w-xs rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
                />
              </div>
              <button
                onClick={async () => {
                  if (deleteConfirm !== "DELETE" || !deleteAcknowledged) return;
                  setDeleting(true);
                  setPageError("");
                  try {
                    await apiFetch(
                      `/api/account?confirm=${encodeURIComponent(deleteConfirm)}`,
                      { method: "DELETE" }
                    );
                    const { signOut } = await import("@/lib/firebase");
                    await signOut();
                    router.replace("/");
                  } catch (e: any) {
                    setPageError(e.message || "Deletion failed");
                  } finally {
                    setDeleting(false);
                  }
                }}
                disabled={deleteConfirm !== "DELETE" || !deleteAcknowledged || deleting}
                className="rounded-apple-sm bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? "Deleting\u2026" : "Delete account"}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}


/* ── Integrations Tab Component ──────────────────────────────────────────────── */

function IntegrationsTab({
  loading,
  saved,
  smtpHost,
  setSmtpHost,
  smtpPort,
  setSmtpPort,
  smtpUser,
  setSmtpUser,
  smtpPassword,
  setSmtpPassword,
  smtpFromEmail,
  setSmtpFromEmail,
  smtpUseTls,
  setSmtpUseTls,
  smtpConfigured,
  onLoadConfig,
  onSaveSMTP,
}: {
  loading: boolean;
  saved: boolean;
  smtpHost: string;
  setSmtpHost: (v: string) => void;
  smtpPort: number;
  setSmtpPort: (v: number) => void;
  smtpUser: string;
  setSmtpUser: (v: string) => void;
  smtpPassword: string;
  setSmtpPassword: (v: string) => void;
  smtpFromEmail: string;
  setSmtpFromEmail: (v: string) => void;
  smtpUseTls: boolean;
  setSmtpUseTls: (v: boolean) => void;
  smtpConfigured: boolean;
  onLoadConfig: () => void;
  onSaveSMTP: () => void;
}) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!loaded) {
      setLoaded(true);
      onLoadConfig();
    }
  }, [loaded, onLoadConfig]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-text border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* SMTP Configuration */}
      <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Email (SMTP)</h2>
          {smtpConfigured && (
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
              Configured
            </span>
          )}
        </div>
        <p className="mb-4 text-sm text-apple-secondary">
          Configure SMTP to enable daily digest emails. Works with any provider (Gmail, SendGrid,
          Mailgun, Amazon SES, etc.).
        </p>

        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-apple-secondary">
                SMTP Host
              </label>
              <input
                type="text"
                value={smtpHost}
                onChange={(e) => setSmtpHost(e.target.value)}
                placeholder="smtp.gmail.com"
                className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-apple-secondary">Port</label>
              <input
                type="number"
                value={smtpPort}
                onChange={(e) => setSmtpPort(Number(e.target.value))}
                placeholder="587"
                className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-apple-secondary">
                Username
              </label>
              <input
                type="text"
                value={smtpUser}
                onChange={(e) => setSmtpUser(e.target.value)}
                placeholder="your@email.com"
                className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-apple-secondary">
                Password
              </label>
              <input
                type="password"
                value={smtpPassword}
                onChange={(e) => setSmtpPassword(e.target.value)}
                placeholder="App password or API key"
                className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-apple-secondary">
              From Email
            </label>
            <input
              type="email"
              value={smtpFromEmail}
              onChange={(e) => setSmtpFromEmail(e.target.value)}
              placeholder="noreply@yourcompany.com"
              className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
            />
          </div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={smtpUseTls}
              onChange={(e) => setSmtpUseTls(e.target.checked)}
              className="h-4 w-4 rounded border-apple-border accent-apple-blue"
            />
            <span className="text-sm">Use TLS (recommended for port 587)</span>
          </label>
        </div>

        <button
          onClick={onSaveSMTP}
          className="mt-4 rounded-apple-sm bg-apple-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
        >
          {saved ? "Saved" : "Save SMTP configuration"}
        </button>
      </div>
    </div>
  );
}
