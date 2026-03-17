# Tier Restructure & International Launch Features

**Date:** 2026-03-17
**Status:** Approved
**Scope:** Pricing/tier overhaul, usage limits, auth improvements, legal pages, cookie consent

---

## 1. Pricing & Tier Restructure

### Current State

Three tiers: `free` (default), `starter` (paid or 7-day trial), `pro` (paid).
New signups get `free` tier with a 7-day `starter_access` trial. After trial expires, they drop to `free` which locks most features.

### Target State

Two tiers: `starter` (free for everyone, no expiry) and `pro` ($29/month).

- Remove `free` tier entirely from all code paths
- Remove `growth` tier alias
- Remove trial logic (`starter_access_expires_at`, `STARTER_ACCESS_DAYS`)
- All new signups get `starter` tier permanently
- Existing `free` users are migrated to `starter`
- Only Stripe checkout needed for `pro` upgrade

### Files to Change

| File | Change |
|---|---|
| `functions/shared/entitlements.py` | Remove `FREE_TIER`, remove trial logic, default to `starter`. `normalize_subscription_tier()` maps `"free"` and `"growth"` to `"starter"` (currently maps to `FREE_TIER`). |
| `functions/shared/models.py` | `TenantProfile.subscription_tier` Literal: remove `"free"` and `"growth"`, default `"starter"`. `subscription_status` Literal: remove `"free"`, default `"active"`. Remove `starter_access_expires_at` field. |
| `functions/api/middleware/auth.py` | `_build_default_tenant()`: set `subscription_tier="starter"`, `subscription_status="active"`, remove `starter_access_expires_at`. Remove the trialing-to-free conversion in `_profile_updates()` (lines 69-78). |
| `functions/api/routes/billing.py` | Change `BillingCheckoutRequest.tier` to `Literal["pro"]` (only pro purchasable). Update `_handle_subscription_deleted` to set tier to `"starter"` instead of `"free"`. Update `_handle_checkout_completed` to set status to `"active"` instead of `"trialing"`. |
| `frontend/src/app/settings/page.tsx` | Billing tab: show 2-column grid (Starter free, Pro $29). Remove trial messaging. Remove "Choose Starter" button. Only show "Upgrade to Pro" and "Manage Subscription" buttons. |
| `frontend/src/components/nav.tsx` | Plan badge: show "Starter" or "Pro" only. |
| `frontend/src/lib/billing.ts` | Update `TIER_ORDER` to remove `free: 0` and `growth: 1`. Remove `formatStarterAccessDate()`. Update `planBadgeLabel()` to remove "Starter trial" path. Map everything non-pro to "Starter". |
| `frontend/src/types` (if applicable) | Update `SubscriptionTier` type to `"starter" \| "pro"` only. |

### Migration Strategy

Existing tenants with `subscription_tier: "free"` or `subscription_status: "free"`:
- `normalize_subscription_tier()` maps `"free"` and `"growth"` to `"starter"` — this is the primary migration mechanism
- `resolve_access()` treats any tier that is not `"pro"` as `"starter"`
- No Firestore migration script needed; the code handles it gracefully at read time
- Model validators accept legacy values and normalize them

---

## 2. Usage Limits

### Limits Per Tier

| Resource | Starter (Free) | Pro ($29/mo) |
|---|---|---|
| Pipeline runs per week | 3 (Mon/Wed/Fri) | 7 (daily) |
| Intelligence items scored per run | 25 | 100 |
| Post generations per day | 1 | 5 |
| Leads qualified per run | 2 | 8 |
| Chat messages per day | 10 | 100 |
| Brand documents (total) | 3 | 50 |
| Newsletter generation | Blocked | Weekly |
| Platform connections | 1 | 10 |
| AI model | gemini-3.1-flash-lite-preview | gemini-3.1-pro-preview |

### AI Models Per Tier

- **Starter (free):** `publishers/google/models/gemini-3.1-flash-lite-preview` — fast, cheap, good enough for basic intelligence scoring and post generation
- **Pro ($29/mo):** `publishers/google/models/gemini-3.1-pro-preview` — higher quality for all tasks (post generation, lead qualification, outreach drafts, newsletters)

### Cost Basis

- Gemini 3.1 Flash-Lite: very low cost per tenant/day
- Starter at 3 runs/week with 25 items: estimated ~$0.20/month per free user
- Pro at daily runs with 100 items using Gemini 3.1 Pro: estimated ~$3-7/month per pro user
- At $29/month Pro price, strong margin on AI costs

### Architecture

New module: `functions/shared/usage_limits.py`

This module coexists with the existing `functions/shared/settings_limits.py` which defines field validation limits (description length, competitor count, etc.). `usage_limits.py` handles tier-based runtime quotas.

```python
TIER_LIMITS = {
    "starter": {
        "intelligence_items_per_run": 25,
        "post_generations_per_day": 1,
        "leads_per_run": 2,
        "chat_messages_per_day": 10,
        "brand_documents_total": 3,
        "pipeline_days_per_week": [0, 2, 4],  # Mon, Wed, Fri
        "newsletter_enabled": False,
        "max_platform_connections": 1,
        "gemini_model": "publishers/google/models/gemini-3.1-flash-lite-preview",
    },
    "pro": {
        "intelligence_items_per_run": 100,
        "post_generations_per_day": 5,
        "leads_per_run": 8,
        "chat_messages_per_day": 100,
        "brand_documents_total": 50,
        "pipeline_days_per_week": [0, 1, 2, 3, 4, 5, 6],  # daily
        "newsletter_enabled": True,
        "max_platform_connections": 10,
        "gemini_model": "publishers/google/models/gemini-3.1-pro-preview",
    },
}
```

**Storage:** Redis counters with key `usage:{tenant_id}:{action}:{YYYY-MM-DD}`, TTL 48 hours.

**Redis counter primitives:** The existing `redis_client.py` only has cache get/set/delete and rate limiting. New counter functions needed:
- `counter_increment(key, ttl_seconds) -> int` — `INCR` + `EXPIRE` on first set
- `counter_get(key) -> int` — `GET` returning 0 if key absent

Add these to `shared/redis_client.py`. They follow the same pattern as existing functions: use the Redis client directly, with in-memory `dict[str, int]` fallback when Redis is unavailable.

**Model routing:** The `gemini_model` from tier limits is passed through `_run_pipeline()` to the GeminiClient. The pipeline resolves the tenant's tier, looks up the model from `TIER_LIMITS`, and passes it as a parameter to `generate_daily_post()`, `run_and_classify()`, `qualify_inline()`, and `generate_outreach_inline()`. The `GeminiClient.generate()` method already accepts a model parameter (or uses a default from env); we thread the tier-specific model through. Chat endpoint (`/api/chat`) similarly resolves the model from the tenant's tier.

**Fallback when Redis is unavailable:** Fail-open (allow the action, log a warning). Rationale: usage limits are a soft business constraint, not a security boundary. A brief Redis outage should not block users from using the product. The daily pipeline also has its own item count caps hardcoded, providing a secondary defense.

**Pipeline day-of-week check:** Uses the tenant's configured `timezone` field to determine the current weekday. The pipeline receives `tenant_id`, loads the tenant profile (which includes timezone), then checks if `datetime.now(ZoneInfo(tenant.timezone)).weekday()` is in `pipeline_days_per_week`. If not, the pipeline returns early with `email_status: "skipped_not_pipeline_day"`.

**Enforcement points:**
- `pipeline.py` `_run_pipeline()`: Check `pipeline_days_per_week` before running. Pass `intelligence_items_per_run` and `leads_per_run` limits to engines.
- `POST /api/drafts/quick-generate`: Check `post_generations_per_day`.
- `POST /api/chat`: Check `chat_messages_per_day`.
- `POST /api/documents`: Check `brand_documents_total` against current Firestore count.
- `POST /api/newsletters/generate` (file: `functions/api/routes/newsletters.py`): Check `newsletter_enabled`.
- `functions/api/routes/oauth.py`: Check `max_platform_connections` before initiating OAuth flow.

**New API endpoint:** `GET /api/usage` returns current usage counts and limits for the tenant. Register the router in `functions/api/app.py` alongside existing routers.

**Frontend usage display:** The `GET /api/usage` response includes `{action: {used: N, limit: M, percentage: float}}`. Frontend shows:
- Usage bars in Settings page (new section above billing)
- Toast notification via existing toast system when a limit check returns 429, with message from the API response body

### Files to Create/Change

| File | Change |
|---|---|
| `functions/shared/redis_client.py` | Add `counter_increment()` and `counter_get()` with in-memory fallback. |
| `functions/shared/usage_limits.py` | **New.** Tier limits config, `get_limits_for_tier()`, `check_limit()`, `increment_usage()`, `get_usage_summary()` functions. |
| `functions/api/routes/usage.py` | **New.** `GET /api/usage` endpoint. Register in `functions/api/app.py`. |
| `functions/api/app.py` | Register `usage.router`. |
| `functions/pipeline.py` | Import limits, check pipeline day using tenant timezone, cap intelligence items and leads per tier. |
| `functions/api/routes/chat.py` | Add `check_limit("chat_messages_per_day")` before processing. |
| `functions/api/routes/drafts.py` | Add `check_limit("post_generations_per_day")` before generating. |
| `functions/api/routes/documents.py` | Add total document count check before upload. |
| `functions/api/routes/newsletters.py` | Add `newsletter_enabled` check. (Note: file is plural `newsletters.py`.) |
| `functions/api/routes/oauth.py` | Add `max_platform_connections` check before OAuth authorize. |
| `frontend/src/app/settings/page.tsx` | Add usage summary section with progress bars. |

---

## 3. Auth Improvements

### 3a. Password Reset

Firebase Auth has built-in `sendPasswordResetEmail()`. No backend changes needed.

**Frontend changes to `frontend/src/app/page.tsx`:**
- Add "Forgot password?" link below password field
- When clicked, show email input + "Send reset link" button
- Call `sendPasswordResetEmail(auth, email)` from Firebase SDK
- Show success toast: "Reset link sent. Check your inbox."
- Show error for unknown email

**Add to `frontend/src/lib/firebase.ts`:**
- Export `resetPassword(email: string)` function wrapping `sendPasswordResetEmail`

### 3b. Email Verification

After email/password signup, send verification email automatically.

**Frontend changes:**
- `frontend/src/lib/firebase.ts`: Export `verifyEmail()` wrapping `sendEmailVerification(user)`
- `frontend/src/app/page.tsx`: After `signUpWithEmail()`, call `sendEmailVerification()`
- `frontend/src/app/dashboard/page.tsx`: Show dismissible banner if `user.emailVerified === false`
  - Banner text: "Please verify your email address. Check your inbox or [resend verification email]."
  - Resend calls `sendEmailVerification()` again
- Do NOT block app access -- just nudge. Blocking kills conversion for free tiers.

---

## 4. Legal Pages

### Content Authorship

The implementer drafts production-ready legal text based on standard SaaS practices (Notion, Buffer, Hootsuite, Jasper AI patterns). This text is a reasonable starting point but should be reviewed by a lawyer before a high-profile launch. It is sufficient for initial rollout.

### 4a. Terms of Service (`/terms`)

New page at `frontend/src/app/terms/page.tsx`.

Content covers:
- Service description (AI-powered marketing automation)
- Account responsibilities
- Acceptable use policy (no spam, no illegal content, no scraping abuse)
- AI-generated content disclaimer (no guarantee of accuracy, user responsible for review)
- Intellectual property (user owns their content, platform owns the service)
- Payment terms (Pro subscription at $29/month, cancellation, no refunds for partial months)
- Service availability and limitations
- Termination and account deletion
- Limitation of liability
- Governing law (Singapore)
- Contact information (support@intonationlabs.com)

Entity: Intonation Labs Pte. Ltd., Singapore

### 4b. Privacy Policy (`/privacy`)

New page at `frontend/src/app/privacy/page.tsx`.

Content covers (GDPR + CCPA compliant):
- Data controller identity (Intonation Labs Pte. Ltd.)
- Data collected: account data, company profile, AI-generated content, usage analytics
- Purpose of processing: service delivery, AI content generation, analytics
- Legal basis: contract performance, legitimate interest, consent
- Third-party processors: Google Cloud (Vertex AI, Firestore), Stripe (payments), Sentry (error tracking), Firebase (auth)
- AI data processing: inputs sent to Gemini API, not used for model training (paid tier)
- Data retention periods
- International data transfers (Singapore, US via Google Cloud/Stripe)
- User rights: access, rectification, erasure, portability, objection
- Cookie policy (references cookie consent)
- How to exercise rights (email contact)
- DPO/contact: privacy@intonationlabs.com

### Frontend Changes

- `frontend/src/app/page.tsx`: Update ToS and Privacy Policy links from `#` to `/terms` and `/privacy`
- Both pages: centered content, max-width prose, back-to-app navigation link

---

## 5. Cookie Consent Banner

### Design

Floating bottom banner, shown on first visit (no cookie/localStorage flag set).

Three options:
- **Accept All** -- enables all cookie categories
- **Manage Preferences** -- expands to show category toggles
- **Reject Non-Essential** -- only essential cookies

Categories:
- **Essential** (always on, no toggle): Firebase auth session, CSRF protection
- **Analytics** (toggle): Sentry error tracking
- **Marketing** (toggle): None currently, placeholder for future

### Storage

- `localStorage` key: `cookie_consent` with value `{"essential":true,"analytics":true|false,"marketing":true|false,"timestamp":"ISO"}`
- Also set a cookie `cc_consent=1` for server-side awareness (if needed later)

### Implementation

- New component: `frontend/src/components/cookie-consent.tsx`
- Added to `frontend/src/app/layout.tsx` outside AuthProvider
- Sentry initialization: check `frontend/src/instrumentation.ts` (if it exists) and `frontend/src/app/layout.tsx` for where Sentry is initialized. Gate non-essential Sentry features (session replay, performance monitoring) on analytics consent. Core error reporting (essential for service reliability) can remain ungated.
- Banner hidden once any choice is made
- "Cookie Settings" link added to footer area of login page and settings page for re-opening

---

## 6. File Change Summary

### New Files

| File | Purpose |
|---|---|
| `functions/shared/usage_limits.py` | Tier limits config and Redis-backed usage tracking |
| `functions/api/routes/usage.py` | `GET /api/usage` endpoint |
| `frontend/src/app/terms/page.tsx` | Terms of Service page |
| `frontend/src/app/privacy/page.tsx` | Privacy Policy page |
| `frontend/src/components/cookie-consent.tsx` | Cookie consent banner component |

### Modified Files

| File | Changes |
|---|---|
| `functions/shared/entitlements.py` | Remove free tier, trial logic; default to starter |
| `functions/shared/models.py` | Update tier Literals, remove trial fields |
| `functions/shared/redis_client.py` | Add counter_increment, counter_get with fallback |
| `functions/api/middleware/auth.py` | Default new users to starter, remove trial conversion in _profile_updates |
| `functions/api/routes/billing.py` | Only pro purchasable, canceled -> starter, checkout -> active |
| `functions/api/app.py` | Register usage router |
| `functions/pipeline.py` | Usage limit checks, cap items per tier |
| `functions/api/routes/chat.py` | Add chat message limit check |
| `functions/api/routes/drafts.py` | Add post generation limit check |
| `functions/api/routes/documents.py` | Add document count limit check |
| `functions/api/routes/newsletters.py` | Add newsletter enabled check |
| `functions/api/routes/oauth.py` | Add platform connection limit check |
| `frontend/src/app/page.tsx` | Password reset, email verification, legal links |
| `frontend/src/lib/firebase.ts` | Export resetPassword, verifyEmail functions |
| `frontend/src/lib/billing.ts` | Remove free/growth/trial references, simplify to starter/pro |
| `frontend/src/types` (if applicable) | Update SubscriptionTier type |
| `frontend/src/app/dashboard/page.tsx` | Email verification banner |
| `frontend/src/app/settings/page.tsx` | 2-tier billing UI, usage summary with progress bars |
| `frontend/src/app/layout.tsx` | Add cookie consent, gate Sentry on consent |
| `frontend/src/components/nav.tsx` | Update plan badge labels |

---

## 7. Implementation Order

1. **Backend tier restructure** -- entitlements.py, models.py, auth middleware, billing routes, billing.ts
2. **Usage limits system** -- redis_client.py counter primitives, usage_limits.py, usage route, enforcement in pipeline + API routes
3. **Auth improvements** -- firebase.ts, login page (password reset), dashboard (email verification banner)
4. **Legal pages** -- terms page, privacy page, update login links
5. **Cookie consent** -- consent component, layout integration, Sentry gating
6. **Frontend billing UI** -- settings page 2-tier grid, usage display, nav badge

Each step can be deployed independently without breaking the others.
