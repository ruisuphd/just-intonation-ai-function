export type SubscriptionTier = "starter" | "pro";
export type SubscriptionStatus = "trialing" | "active" | "past_due" | "canceled";
export type AccessSource = "starter" | "paid_subscription";
export type Tone = "professional" | "friendly" | "authoritative" | "casual";
export type Language = "en" | "zh" | "bilingual";
export type PlatformId =
  | "linkedin"
  | "x_twitter"
  | "instagram"
  | "google_business_profile"
  | "tiktok"
  | "xiaohongshu";

export interface TenantProfile {
  tenant_id: string;
  company_name: string;
  industry: string;
  description: string;
  target_audience: string;
  tone: Tone;
  language: Language;
  timezone: string;
  subscription_tier: SubscriptionTier;
  subscription_status: SubscriptionStatus;
  competitor_names: string[];
  industry_keywords: string[];
  platforms_enabled: string[];
  daily_digest_enabled: boolean;
  daily_digest_email: string;
  notification_time: string;
  starter_access_expires_at?: string | null;
  tone_formal_casual?: number;
  tone_technical_accessible?: number;
  website_url?: string;
  onboarding_completed?: boolean;
  legal_terms_version?: string | null;
  legal_terms_accepted_at?: string | null;
  legal_docs_current_version?: string;
}

/** GET /api/dashboard/bootstrap — parallel aggregate for dashboard shell */
export interface DashboardBootstrapResponse {
  settings: Partial<TenantProfile> & Record<string, unknown>;
  billing: BillingSummary;
  usage: {
    tier?: string;
    usage?: Record<string, { used?: number; limit?: number; percentage?: number }>;
    labels?: Record<string, string>;
  };
  pipeline_status: {
    last_run: {
      completed_at?: string;
      status?: string;
      drafts_generated?: number;
      signals_found?: number;
      leads_qualified?: number;
      date?: string;
    } | null;
    next_run?: string;
    next_run_local?: string;
    next_run_at?: string;
    has_run_before?: boolean;
    pipeline_days_per_week?: number[];
  };
  oauth_status: {
    linkedin: boolean;
    x_twitter: boolean;
    linkedin_expires_at?: string | null;
    x_twitter_expires_at?: string | null;
  };
}

export interface BillingSummary {
  tenant_id: string;
  subscription_tier: SubscriptionTier;
  subscription_status: SubscriptionStatus;
  effective_tier: SubscriptionTier;
  access_source: AccessSource;
  starter_access_expires_at: string | null;
  starter_access_active: boolean;
  has_paid_subscription: boolean;
  can_manage_billing: boolean;
  can_start_checkout: boolean;
  stripe_customer_linked: boolean;
  /** From Stripe Price (STRIPE_PRO_PRICE_ID), when configured */
  pro_unit_amount?: number | null;
  pro_currency?: string | null;
  pro_interval?: string | null;
}

export interface IntelligenceItem {
  id: string;
  tenant_id: string;
  source_url: string;
  source_name: string;
  title: string;
  summary: string;
  relevance_score: number;
  postability_score: number;
  suggested_angle: string;
  tags: string[];
  batch_date: string;
}

export interface DraftContent {
  id: string;
  platform: PlatformId;
  text: string;
  headline: string;
  hashtags: string[];
  feedback_thumbs?: "up" | "down";
  feedback_reason?: string | null;
  feedback_at?: string | null;
  status: "draft" | "scheduled" | "published" | "copied" | "dismissed";
  batch_date: string;
  company_name?: string;
  topic?: string;
  origin?: string;
  why_it_matters?: string;
  image_prompt?: string;
  image_url?: string;
  platforms_generated?: PlatformId[];
  content_by_platform?: Partial<Record<PlatformId, string>>;
  scheduled_for?: string;
  linkedin_post?: string;
  x_post?: string;
  instagram_caption?: string;
  google_business_profile_post?: string;
  tiktok_caption?: string;
  xiaohongshu_post?: string;
  created_at?: string;
  updated_at?: string;
}

export interface QualifiedLead {
  id: string;
  tenant_id: string;
  company_name: string;
  icp_fit: "high" | "medium" | "low";
  icp_fit_score: number;
  icp_reasoning?: string;
  suggested_outreach_angle: string;
  status: string;
  contact_email?: string;
  contact_linkedin_url?: string;
  enrichment_status?: string;
  draft_content?: string;
  draft_subject?: string;
  draft_type?: string;
  outreach_status?: string;
  last_contacted_at?: string;
}

export interface AnalyticsSeriesPoint {
  date: string;
  label: string;
  impressions: number;
  engagements: number;
  avg_open_rate: number;
}

export interface AnalyticsSummary {
  total_impressions: number;
  avg_open_rate: number;
  qualified_leads: number;
  published_posts: number;
  signals_detected: number;
  outreach_sent: number;
  reply_received: number;
}

export interface AnalyticsResponse {
  summary: AnalyticsSummary;
  series: AnalyticsSeriesPoint[];
  live_metrics_available: boolean;
}
