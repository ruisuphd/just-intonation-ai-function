"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ALL_PLATFORMS, normalizePlatforms } from "@/lib/platforms";
import { COMPANY_DESCRIPTION_MAX_CHARS, TARGET_AUDIENCE_MAX_CHARS } from "@/lib/settings";
import Notice from "@/components/ui/notice";
import { apiFetch, apiFetchBlob } from "@/lib/api";
import { formatProListPrice } from "@/lib/billing";
import { openCookiePreferences } from "@/lib/cookie-consent-storage";
import type { BillingSummary, TenantProfile } from "@/types";

const STRIPE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "";
const STRIPE_PRICING_TABLE_ID = process.env.NEXT_PUBLIC_STRIPE_PRICING_TABLE_ID ?? "";
const stripePricingTableConfigured =
  Boolean(STRIPE_PUBLISHABLE_KEY && STRIPE_PRICING_TABLE_ID);

const TABS = [
  { id: "company", label: "Company" },
  { id: "brand_voice", label: "Brand Voice" },
  { id: "platforms", label: "Platforms" },
  { id: "notifications", label: "Notifications" },
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

const STARTER_FEATURES = [
  "Core AI engine",
  "Content generation (3x/week)",
  "25 intelligence items per run",
  "1 post generation per day",
  "10 chat messages per day",
  "3 brand documents",
  "1 platform connection",
  "Daily email digest",
];

const PRO_FEATURES = [
  "Everything in Starter, plus:",
  "Daily content (7x/week)",
  "100 intelligence items per run",
  "5 post generations per day",
  "100 chat messages per day",
  "50 brand documents",
  "10 platform connections",
  "Newsletter generation",
  "Gemini 3.1 Pro model",
  "Priority support",
];

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
  const [billingBusy, setBillingBusy] = useState<"portal" | null>(null);
  const pricingTableAnchorRef = useRef<HTMLDivElement>(null);
  const [usage, setUsage] = useState<any>(null);
  const [exporting, setExporting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteAcknowledged, setDeleteAcknowledged] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordChanging, setPasswordChanging] = useState(false);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

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
  const [brandVoiceUploadError, setBrandVoiceUploadError] = useState("");
  const [brandVoiceMessage, setBrandVoiceMessage] = useState("");
  const [oauthStatus, setOauthStatus] = useState<{
    linkedin: boolean;
    x_twitter: boolean;
    linkedin_expires_at?: string;
    x_twitter_expires_at?: string;
  } | null>(null);
  const [invoices, setInvoices] = useState<{ id: string; number: string | null; amount_paid: number; currency: string; created: number; invoice_pdf: string | null }[]>([]);
  const [invoicesHasMore, setInvoicesHasMore] = useState(false);
  const [shouldPollAfterCheckout, setShouldPollAfterCheckout] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const fetchOauthStatus = useCallback(async () => {
    if (!user) return;
    try {
      const status = await apiFetch<{
        linkedin: boolean;
        x_twitter: boolean;
        linkedin_expires_at?: string;
        x_twitter_expires_at?: string;
      }>("/api/oauth/status");
      setOauthStatus(status);
    } catch {
      setOauthStatus(null);
    }
  }, [user]);

  const isTokenExpiringSoon = (expiresAt?: string) =>
    expiresAt && new Date(expiresAt).getTime() - Date.now() < 7 * 24 * 60 * 60 * 1000;

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
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const hash = window.location.hash.replace("#", "");
    const tabFromHash = ["company", "brand_voice", "platforms", "notifications", "billing", "account"].includes(hash) ? hash : null;
    setTab(tabFromHash || params.get("tab") || "company");
    const checkoutState = params.get("checkout");
    if (checkoutState === "success") {
      setShouldPollAfterCheckout(true);
      setBillingMessage({
        tone: "success",
        text: "Payment successful. Pro access usually appears within a few seconds while we confirm with Stripe.",
      });
      params.delete("checkout");
      const qs = params.toString();
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${qs ? `?${qs}` : ""}${window.location.hash}`,
      );
    } else if (checkoutState === "canceled") {
      setBillingMessage({
        tone: "warning",
        text: "Checkout was canceled. You were not charged and your plan is unchanged.",
      });
      params.delete("checkout");
      const qs = params.toString();
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${qs ? `?${qs}` : ""}${window.location.hash}`,
      );
    }
  }, []);

  useEffect(() => {
    if (!shouldPollAfterCheckout || !user || authLoading) return;
    let cancelled = false;

    async function poll() {
      for (let attempt = 0; attempt < 5; attempt++) {
        if (cancelled) return;
        if (attempt > 0) {
          await new Promise((r) => setTimeout(r, 2000));
        }
        if (cancelled) return;
        try {
          const next = await apiFetch<BillingSummary>("/billing/subscription");
          if (cancelled) return;
          setBilling(next);
          if (next.effective_tier === "pro" || next.has_paid_subscription) {
            setShouldPollAfterCheckout(false);
            setBillingMessage({
              tone: "success",
              text: "You are on Pro. Thank you for subscribing.",
            });
            return;
          }
        } catch {
          /* continue polling */
        }
      }
      if (!cancelled) {
        setShouldPollAfterCheckout(false);
        setBillingMessage({
          tone: "success",
          text: "Payment successful. If your plan still shows Starter, wait a moment and refresh the page.",
        });
      }
    }

    void poll();
    return () => {
      cancelled = true;
    };
  }, [shouldPollAfterCheckout, user, authLoading]);

  useEffect(() => {
    if (!authLoading && user) {
      fetchSettings();
      setDisplayName(user.displayName || "");
    }
  }, [authLoading, user, fetchSettings]);

  useEffect(() => {
    if (!authLoading && user) {
      apiFetch("/api/usage").then(setUsage).catch(() => {});
    }
  }, [authLoading, user]);

  useEffect(() => {
    if (!authLoading && user && tab === "billing") {
      apiFetch<{ invoices?: { id: string; number: string | null; amount_paid: number; currency: string; created: number; invoice_pdf: string | null }[]; has_more?: boolean }>("/billing/invoices")
        .then((d) => {
          setInvoices(d.invoices || []);
          setInvoicesHasMore(d.has_more ?? false);
        })
        .catch(() => setInvoices([]));
    }
  }, [authLoading, user, tab]);

  async function loadMoreInvoices() {
    const lastId = invoices[invoices.length - 1]?.id;
    if (!lastId) return;
    try {
      const d = await apiFetch<{ invoices?: typeof invoices; has_more?: boolean }>(
        `/billing/invoices?starting_after=${encodeURIComponent(lastId)}`
      );
      setInvoices((prev) => [...prev, ...(d.invoices || [])]);
      setInvoicesHasMore(d.has_more ?? false);
    } catch {}
  }

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
    setBrandVoiceUploadError("");
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

  function scrollToPricingTable() {
    pricingTableAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function billingSummaryText() {
    if (!billing) return "Loading billing details.";
    if (billing.subscription_status === "past_due") {
      return "Your last payment did not go through. Update your payment method in Manage billing to restore Pro features.";
    }
    if (billing.has_paid_subscription) {
      const st = billing.subscription_status;
      if (st === "trialing") return "You are trialing Pro. Billing begins when the trial ends unless you cancel.";
      if (st === "active") return "Your Pro subscription is active.";
      return `Subscription status: ${st}.`;
    }
    return "You are on the free Starter plan. Upgrade to unlock Pro limits and features.";
  }

  function currentAccessLabel() {
    if (!billing) return "Loading";
    if (billing.has_paid_subscription) {
      return `${billing.subscription_tier[0].toUpperCase()}${billing.subscription_tier.slice(1)} plan`;
    }
    return "Starter plan";
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
        {saved && !pageError && (
          <div className="mb-4"><Notice tone="success">Settings saved.</Notice></div>
        )}

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
                <label className="mb-2 block text-sm font-medium">Brand Guidelines (PDF, DOCX, MD — max 10MB)</label>
                <div className="relative flex flex-col items-center justify-center rounded-apple-sm border-2 border-dashed border-apple-border bg-apple-bg p-8 text-center transition-colors hover:bg-apple-border/10">
                  <input
                    type="file"
                    accept=".pdf,.docx,.doc,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown"
                    onChange={(e) => {
                      setBrandVoiceUploadError("");
                      const file = e.target.files?.[0];
                      if (!file) {
                        setBrandGuidelinesFile(null);
                        return;
                      }
                      const ext = file.name.toLowerCase().split(".").pop();
                      const allowed = ["pdf", "docx", "md"];
                      if (!ext || !allowed.includes(ext)) {
                        setBrandVoiceUploadError("Only .pdf, .docx, and .md files are allowed.");
                        setBrandGuidelinesFile(null);
                        e.target.value = "";
                        return;
                      }
                      if (file.size > 10 * 1024 * 1024) {
                        setBrandVoiceUploadError("File exceeds 10MB limit. Please compress or trim the document.");
                        setBrandGuidelinesFile(null);
                        e.target.value = "";
                        return;
                      }
                      setBrandGuidelinesFile(file);
                    }}
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
                {brandVoiceUploadError && (
                  <p className="mt-2 text-sm text-red-500">{brandVoiceUploadError}</p>
                )}
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
                    <>
                      <span className="text-xs text-apple-secondary">Connected</span>
                      {isTokenExpiringSoon(oauthStatus.linkedin_expires_at) && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">Token expiring soon — Reconnect</span>
                      )}
                    </>
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
                  {oauthStatus?.linkedin && (
                    <button
                      onClick={async () => {
                        try {
                          await apiFetch("/api/oauth/disconnect", { method: "POST", body: JSON.stringify({ platform: "linkedin" }) });
                          void fetchOauthStatus();
                        } catch (err: any) {
                          setPageError(err.message || "Unable to disconnect.");
                        }
                      }}
                      className="rounded-apple-sm border border-apple-border px-3 py-1.5 text-sm font-medium text-apple-secondary hover:bg-apple-bg"
                    >
                      Disconnect
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-3 rounded-apple-sm border border-apple-border bg-apple-bg px-4 py-3">
                  <span className="text-sm font-medium">X</span>
                  {oauthStatus?.x_twitter ? (
                    <>
                      <span className="text-xs text-apple-secondary">Connected</span>
                      {isTokenExpiringSoon(oauthStatus.x_twitter_expires_at) && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">Token expiring soon — Reconnect</span>
                      )}
                    </>
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
                  {oauthStatus?.x_twitter && (
                    <button
                      onClick={async () => {
                        try {
                          await apiFetch("/api/oauth/disconnect", { method: "POST", body: JSON.stringify({ platform: "x_twitter" }) });
                          void fetchOauthStatus();
                        } catch (err: any) {
                          setPageError(err.message || "Unable to disconnect.");
                        }
                      }}
                      className="rounded-apple-sm border border-apple-border px-3 py-1.5 text-sm font-medium text-apple-secondary hover:bg-apple-bg"
                    >
                      Disconnect
                    </button>
                  )}
                </div>
              </div>
            </div>
            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-apple-secondary">
                Select which platforms IntoMarketing generates content for. Your saved choices
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
                {billing.can_manage_billing && (
                  <button
                    onClick={handleBillingPortal}
                    disabled={billingBusy !== null}
                    className={`rounded-apple-sm px-4 py-2 text-sm font-medium disabled:opacity-50 ${
                      billing.subscription_status === "past_due"
                        ? "bg-apple-blue text-white hover:bg-apple-blue-hover"
                        : "border border-apple-border hover:bg-apple-bg"
                    }`}
                  >
                    {billingBusy === "portal" ? "Opening portal\u2026" : "Manage billing"}
                  </button>
                )}
              </div>
            </div>

            {billingMessage && (
              <Notice tone={billingMessage.tone}>{billingMessage.text}</Notice>
            )}

            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
              {usage && (
                <div className="mb-6 space-y-3">
                  <h3 className="text-sm font-semibold text-gray-700">Today&apos;s Usage</h3>
                  {Object.entries(usage.usage || {})
                    .filter(([, data]) => {
                      const d = data as { limit?: number; used?: number } | undefined;
                      return d && typeof d.limit === "number" && d.limit > 0 && typeof d.used === "number";
                    })
                    .map(([action, data]) => {
                    const d = data as { used: number; limit: number };
                    const pct = Math.min((d.used / d.limit) * 100, 100);
                    const label = (usage as { labels?: Record<string, string> }).labels?.[action]
                      ?? action.replace(/_/g, " ");
                    return (
                      <div key={action} className="flex items-center gap-3">
                        <span className="w-40 truncate text-xs text-gray-600">{label}</span>
                        <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-400" : "bg-blue-500"}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500 w-16 text-right">{d.used}/{d.limit}</span>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                {/* Starter card */}
                <div
                  className={`rounded-apple border p-6 ${
                    billing.effective_tier === "starter"
                      ? "border-apple-blue bg-blue-50/30"
                      : "border-apple-border bg-apple-bg"
                  } shadow-apple`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-lg font-semibold">Starter</h3>
                      <p className="text-2xl font-bold mt-1">Free</p>
                      <p className="text-sm text-apple-secondary mt-0.5">For individuals getting started</p>
                    </div>
                    {billing.effective_tier === "starter" && (
                      <span className="rounded-full bg-apple-blue/10 px-2.5 py-1 text-xs font-medium text-apple-blue">
                        Current plan
                      </span>
                    )}
                  </div>
                  <ul className="mt-4 space-y-2">
                    {STARTER_FEATURES.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-apple-text">
                        <span className="mt-0.5 text-green-500">✓</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Pro card */}
                <div
                  className={`rounded-apple border p-6 ${
                    billing.effective_tier === "pro"
                      ? "border-blue-500 bg-blue-50/30"
                      : "border-blue-500 bg-apple-bg"
                  } shadow-apple`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-lg font-semibold">Pro</h3>
                      <p className="text-2xl font-bold mt-1">{formatProListPrice(billing)}</p>
                      <p className="text-sm text-apple-secondary mt-0.5">For teams that want more</p>
                    </div>
                    {billing.effective_tier === "pro" && (
                      <span className="rounded-full bg-apple-blue/10 px-2.5 py-1 text-xs font-medium text-apple-blue">
                        Current plan
                      </span>
                    )}
                  </div>
                  <ul className="mt-4 space-y-2">
                    {PRO_FEATURES.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-apple-text">
                        <span className={`mt-0.5 ${i === 0 ? "text-apple-secondary" : "text-green-500"}`}>
                          {i === 0 ? "" : "✓"}
                        </span>
                        {f}
                      </li>
                    ))}
                  </ul>

                  <div className="mt-5">
                    {billing.effective_tier === "pro" ? (
                      <button
                        onClick={handleBillingPortal}
                        disabled={billingBusy !== null}
                        className="w-full rounded-apple-sm border border-apple-border px-4 py-2.5 text-sm font-medium hover:bg-apple-bg disabled:opacity-50"
                      >
                        {billingBusy === "portal" ? "Opening portal\u2026" : "Manage billing"}
                      </button>
                    ) : billing.can_start_checkout ? (
                      stripePricingTableConfigured ? (
                        <button
                          type="button"
                          onClick={scrollToPricingTable}
                          className="w-full rounded-apple-sm bg-apple-blue px-4 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover"
                        >
                          Upgrade to Pro
                        </button>
                      ) : (
                        <p className="text-sm text-amber-800">
                          Online checkout is not configured (missing Stripe pricing table env). Add
                          NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY and NEXT_PUBLIC_STRIPE_PRICING_TABLE_ID.
                        </p>
                      )
                    ) : null}
                  </div>
                </div>
              </div>

              {billing.can_start_checkout && stripePricingTableConfigured && (
                <>
                  <Script
                    src="https://js.stripe.com/v3/pricing-table.js"
                    strategy="lazyOnload"
                  />
                  <div
                    ref={pricingTableAnchorRef}
                    id="stripe-pricing-table"
                    className="mt-6 rounded-apple border border-apple-border bg-apple-card p-5 shadow-apple sm:p-6"
                  >
                    <h3 className="mb-1 text-lg font-semibold">Complete upgrade</h3>
                    <p className="mb-4 text-sm text-apple-secondary">
                      Select a plan below to subscribe securely via Stripe Checkout.
                    </p>
                    <stripe-pricing-table
                      pricing-table-id={STRIPE_PRICING_TABLE_ID}
                      publishable-key={STRIPE_PUBLISHABLE_KEY}
                      client-reference-id={billing.tenant_id}
                      {...(user?.email ? { "customer-email": user.email } : {})}
                    />
                  </div>
                </>
              )}

              {billing.has_paid_subscription && (
                <div className="mt-6 border-t border-apple-border pt-6">
                  <h3 className="mb-3 text-sm font-semibold text-gray-700">Invoice history</h3>
                  {invoices.length === 0 ? (
                    <p className="text-sm text-apple-secondary">
                      No invoices yet. They will appear here after your first successful payment.
                    </p>
                  ) : (
                    <>
                      <div className="overflow-x-auto rounded-apple-sm border border-apple-border">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-apple-border bg-apple-bg">
                              <th className="px-3 py-2 text-left font-medium">Date</th>
                              <th className="px-3 py-2 text-left font-medium">Invoice</th>
                              <th className="px-3 py-2 text-right font-medium">Amount</th>
                              <th className="px-3 py-2 text-left font-medium" />
                            </tr>
                          </thead>
                          <tbody>
                            {invoices.map((inv) => (
                              <tr key={inv.id} className="border-b border-apple-border last:border-0">
                                <td className="px-3 py-2 text-apple-secondary">
                                  {new Date(inv.created * 1000).toLocaleDateString()}
                                </td>
                                <td className="px-3 py-2">{inv.number || inv.id}</td>
                                <td className="px-3 py-2 text-right">
                                  {(inv.amount_paid / 100).toFixed(2)} {inv.currency.toUpperCase()}
                                </td>
                                <td className="px-3 py-2">
                                  {inv.invoice_pdf && (
                                    <a
                                      href={inv.invoice_pdf}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-apple-blue hover:underline"
                                    >
                                      PDF
                                    </a>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {invoicesHasMore && (
                        <button
                          type="button"
                          onClick={() => void loadMoreInvoices()}
                          className="mt-3 w-full rounded-apple-sm border border-apple-border py-2 text-sm font-medium text-apple-secondary hover:bg-apple-bg"
                        >
                          Load more
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Account & data Tab */}
        {tab === "account" && (
          <div className="space-y-6">
            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
              <h2 className="mb-4 text-lg font-semibold">Profile</h2>
              <div className="mb-4">
                <label className="mb-1 block text-sm font-medium">Display name</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  className="w-full max-w-xs rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
                />
                <button
                  onClick={async () => {
                    try {
                      const { updateProfile } = await import("@/lib/firebase");
                      await updateProfile({ displayName: displayName.trim() || undefined });
                      setPageError("");
                    } catch (e: any) {
                      setPageError(e.message || "Could not update name");
                    }
                  }}
                  className="mt-2 rounded-apple-sm bg-apple-blue px-4 py-1.5 text-sm font-medium text-white hover:bg-apple-blue-hover"
                >
                  Save name
                </button>
              </div>
              {user?.providerData?.[0]?.providerId === "password" && (
                <div className="mt-6">
                  <h3 className="mb-2 text-sm font-medium">Change password</h3>
                  <p className="mb-2 text-xs text-apple-secondary">Enter your current password and a new one.</p>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Current password"
                    className="mb-2 block w-full max-w-xs rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
                  />
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="New password"
                    className="mb-2 block w-full max-w-xs rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
                  />
                  {passwordSuccess && (
                    <div className="mb-2">
                      <Notice tone="success">Password updated successfully</Notice>
                    </div>
                  )}
                  <button
                    onClick={async () => {
                      if (!currentPassword || !newPassword || newPassword.length < 6) {
                        setPageError("New password must be at least 6 characters");
                        return;
                      }
                      setPasswordChanging(true);
                      setPageError("");
                      setPasswordSuccess(false);
                      try {
                        const { changePasswordWithReauth } = await import("@/lib/firebase");
                        await changePasswordWithReauth(currentPassword, newPassword);
                        setCurrentPassword("");
                        setNewPassword("");
                        setPasswordSuccess(true);
                      } catch (e: any) {
                        const code = e?.code || e?.message || "";
                        let msg = "Password change failed. Please try again.";
                        if (code.includes("wrong-password") || code.includes("invalid-credential")) {
                          msg = "Your current password is incorrect.";
                        } else if (code.includes("weak-password")) {
                          msg = "New password must be at least 6 characters.";
                        } else if (code.includes("requires-recent-login")) {
                          msg = "For security, please sign out and sign in again before changing your password.";
                        }
                        setPageError(msg);
                      } finally {
                        setPasswordChanging(false);
                      }
                    }}
                    disabled={passwordChanging || !currentPassword || !newPassword}
                    className="rounded-apple-sm bg-apple-blue px-4 py-1.5 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
                  >
                    {passwordChanging ? "Updating…" : "Change password"}
                  </button>
                </div>
              )}
            </div>

            <div className="rounded-apple bg-apple-card p-5 shadow-apple sm:p-6">
              <h2 className="mb-2 text-lg font-semibold">Cookie preferences</h2>
              <p className="mb-4 text-sm text-apple-secondary">
                Choose whether we may use analytics cookies for error tracking (Sentry). Essential cookies
                required for sign-in always stay on. See the Privacy Policy for details.
              </p>
              <button
                type="button"
                onClick={() => openCookiePreferences()}
                className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium hover:bg-apple-bg"
              >
                Manage cookie preferences
              </button>
            </div>

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
                    a.download = `intomarketing-export-${new Date().toISOString().slice(0, 10)}.zip`;
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

