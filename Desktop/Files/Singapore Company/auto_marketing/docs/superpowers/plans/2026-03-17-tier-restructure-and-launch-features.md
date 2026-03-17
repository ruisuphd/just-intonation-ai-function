# Tier Restructure & International Launch Features — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the free tier, make Starter free for all users, add Pro at $29/month with usage limits, add password reset, email verification, legal pages, and cookie consent for international launch.

**Architecture:** Backend-first approach — restructure tiers and entitlements, then add usage limit enforcement via Redis counters, then layer on frontend changes. Each chunk is independently deployable.

**Tech Stack:** Python/FastAPI backend, Next.js/React frontend, Firebase Auth, Firestore, Redis, Stripe, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-17-tier-restructure-and-launch-features-design.md`

---

## Chunk 1: Backend Tier Restructure

### Task 1: Update entitlements module

**Files:**
- Modify: `functions/shared/entitlements.py` (lines 9-11, 32-37, 105-158)

- [ ] **Step 1: Update tier constants and normalize function**

Remove `FREE_TIER`, update `normalize_subscription_tier()` to map legacy values to `"starter"`:

```python
# Line 9-11: Replace tier constants
STARTER_TIER = "starter"
PRO_TIER = "pro"
STARTER_ACCESS_DAYS = 7  # Keep for backward compat but unused

# Lines 32-37: Update normalize function
def normalize_subscription_tier(raw: str | None) -> str:
    raw = (raw or "").strip().lower()
    if raw == "pro":
        return PRO_TIER
    return STARTER_TIER  # "free", "growth", "starter", empty, anything else → starter
```

- [ ] **Step 2: Simplify resolve_access()**

Remove trial logic from `resolve_access()`. The function should:
1. Internal accounts → Pro
2. Paid Stripe subscription with `subscription_id` → use subscription tier
3. Everything else → Starter

Remove all `starter_access_expires_at` checks and `starter_access_active` logic. The `AccessSnapshot` dataclass keeps `starter_access_active` field (set to `False` always) for API backward compatibility but the trial logic is gone.

Key changes in `resolve_access()` (lines 105-158):
- Remove the `_starter_access_active()` call and block (around lines 130-145)
- Change the final fallback from `FREE_TIER` to `STARTER_TIER`
- `can_start_checkout` is `True` when user is on Starter (to upgrade to Pro)

- [ ] **Step 3: Commit**

```bash
git add functions/shared/entitlements.py
git commit -m "refactor: remove free tier, make starter the default tier"
```

### Task 2: Update data models

**Files:**
- Modify: `functions/shared/models.py` (lines 52-86)

- [ ] **Step 1: Update TenantProfile Literals**

```python
# Line 65: Change subscription_tier
subscription_tier: Literal["starter", "pro"] = "starter"

# Line 72: Keep starter_access_expires_at but make it fully optional (backward compat)
starter_access_expires_at: datetime | None = None

# Lines 73-75: Change subscription_status - remove "free"
subscription_status: Literal["active", "trialing", "past_due", "canceled"] = "active"
```

Note: Keep `"trialing"` in the Literal for Stripe webhook compatibility (Stripe sends this status). The `model_config = {"extra": "allow"}` on `_Base` means legacy Firestore docs with `"free"` status won't crash on read — Pydantic will accept unknown values. But the `normalize_subscription_tier()` in entitlements handles the tier mapping.

- [ ] **Step 2: Commit**

```bash
git add functions/shared/models.py
git commit -m "refactor: update TenantProfile to starter/pro tiers only"
```

### Task 3: Update auth middleware

**Files:**
- Modify: `functions/api/middleware/auth.py` (lines 37-80)

- [ ] **Step 1: Update _build_default_tenant()**

In `_build_default_tenant()` (lines 37-52), change:
- `"subscription_tier": "free"` → `"subscription_tier": "starter"`
- `"subscription_status": "free"` → `"subscription_status": "active"`
- Remove the `"starter_access_expires_at": datetime.now(...)` line

- [ ] **Step 2: Remove trial conversion in _profile_updates()**

In `_profile_updates()` (lines 55-80), find the block that converts `"trialing"` to `"free"` when there's no Stripe subscription (approximately lines 69-78). Remove this entire block. Users without a Stripe subscription just stay on Starter.

- [ ] **Step 3: Commit**

```bash
git add functions/api/middleware/auth.py
git commit -m "refactor: default new users to starter tier, remove trial conversion"
```

### Task 4: Update billing routes

**Files:**
- Modify: `functions/api/routes/billing.py` (lines 63-270)

- [ ] **Step 1: Restrict checkout to Pro only**

Change `BillingCheckoutRequest` (around line 40):
```python
class BillingCheckoutRequest(BaseModel):
    tier: Literal["pro"]  # Only Pro is purchasable; Starter is free
```

- [ ] **Step 2: Update webhook handlers**

In `_handle_subscription_deleted()` (lines 180-194):
- Change `"subscription_tier": "free"` → `"subscription_tier": "starter"`
- Keep `"subscription_status": "canceled"` as-is (a deleted subscription IS canceled; the user reverts to Starter but the status correctly reflects that their paid sub was canceled)

In `_handle_checkout_completed()` (lines 149-177):
- Keep `"subscription_status": "trialing"` as-is — Stripe often creates subscriptions in trialing state initially, then sends a `subscription.updated` event to set `"active"`. Changing this prematurely could conflict with subsequent webhooks.

Also clean up `_price_id_for_tier()` and `_tier_from_price_id()` helper functions (lines 47-60) — remove starter price entries since only Pro is purchasable.

- [ ] **Step 3: Update checkout session creation**

In `create_checkout_session()` (lines 222-270):
- Remove the `if tier == "starter"` branch and the `STRIPE_STARTER_PRICE_ID` lookup
- Only `STRIPE_PRO_PRICE_ID` is needed
- Update success/cancel URLs if needed

- [ ] **Step 4: Commit**

```bash
git add functions/api/routes/billing.py
git commit -m "refactor: billing only handles Pro checkout, canceled users revert to starter"
```

---

## Chunk 2: Usage Limits System

### Task 5: Add Redis counter primitives

**Files:**
- Modify: `functions/shared/redis_client.py` (insert after line 121, before rate limiting section)

- [ ] **Step 1: Add counter_increment and counter_get**

Insert after the `cache_delete_pattern()` function (line 121):

```python
# ── Usage counters ────────────────────────────────────────────────────────────

_in_memory_counters: dict[str, int] = {}


def counter_increment(key: str, ttl_seconds: int = 172800) -> int:
    """Atomically increment a Redis counter. Returns new value.

    Falls back to in-memory dict when Redis is unavailable.
    TTL defaults to 48 hours.
    """
    client = _get_redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_seconds)
            results = pipe.execute()
            return int(results[0])
        except Exception as exc:
            logger.warning("redis.counter_increment_failed", extra={"key": key, "error": str(exc)})
    # In-memory fallback (resets on deploy — fail-open is acceptable)
    _in_memory_counters[key] = _in_memory_counters.get(key, 0) + 1
    return _in_memory_counters[key]


def counter_get(key: str) -> int:
    """Get current value of a Redis counter. Returns 0 if absent."""
    client = _get_redis()
    if client is not None:
        try:
            val = client.get(key)
            return int(val) if val is not None else 0
        except Exception as exc:
            logger.warning("redis.counter_get_failed", extra={"key": key, "error": str(exc)})
    return _in_memory_counters.get(key, 0)
```

- [ ] **Step 2: Commit**

```bash
git add functions/shared/redis_client.py
git commit -m "feat: add Redis counter primitives for usage tracking"
```

### Task 6: Create usage limits module

**Files:**
- Create: `functions/shared/usage_limits.py`

- [ ] **Step 1: Create the module**

```python
"""Tier-based usage limits and Redis-backed daily counters."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.logger import get_logger
from shared.redis_client import counter_get, counter_increment

logger = get_logger("usage_limits")

TIER_LIMITS: dict[str, dict] = {
    "starter": {
        "intelligence_items_per_run": 25,
        "post_generations_per_day": 1,
        "leads_per_run": 2,
        "chat_messages_per_day": 10,
        "brand_documents_total": 3,
        "pipeline_days_per_week": [0, 2, 4],  # Mon, Wed, Fri
        "newsletter_enabled": False,
        "max_platform_connections": 1,
    },
    "pro": {
        "intelligence_items_per_run": 100,
        "post_generations_per_day": 5,
        "leads_per_run": 8,
        "chat_messages_per_day": 100,
        "brand_documents_total": 50,
        "pipeline_days_per_week": [0, 1, 2, 3, 4, 5, 6],
        "newsletter_enabled": True,
        "max_platform_connections": 10,
    },
}


def get_limits_for_tier(tier: str) -> dict:
    """Return limits dict for a tier. Unknown tiers get starter limits."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["starter"])


def _usage_key(tenant_id: str, action: str, date_str: str) -> str:
    return f"usage:{tenant_id}:{action}:{date_str}"


def _today_str(timezone_name: str = "UTC") -> str:
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).strftime("%Y-%m-%d")


def check_limit(
    tenant_id: str,
    tier: str,
    action: str,
    timezone_name: str = "UTC",
) -> tuple[bool, int, int]:
    """Check if a daily action is within limits.

    Returns (allowed, current_count, limit).
    """
    limits = get_limits_for_tier(tier)
    limit = limits.get(action)
    if limit is None:
        return (True, 0, 0)

    date_str = _today_str(timezone_name)
    key = _usage_key(tenant_id, action, date_str)
    current = counter_get(key)
    return (current < limit, current, limit)


def increment_usage(
    tenant_id: str,
    action: str,
    timezone_name: str = "UTC",
) -> int:
    """Increment a daily usage counter. Returns new count."""
    date_str = _today_str(timezone_name)
    key = _usage_key(tenant_id, action, date_str)
    return counter_increment(key, ttl_seconds=172800)  # 48h


def is_pipeline_day(tier: str, timezone_name: str = "UTC") -> bool:
    """Check if today is a pipeline day for this tier."""
    limits = get_limits_for_tier(tier)
    allowed_days = limits.get("pipeline_days_per_week", [])
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
    today_weekday = datetime.now(tz).weekday()
    return today_weekday in allowed_days


def get_usage_summary(
    tenant_id: str,
    tier: str,
    timezone_name: str = "UTC",
) -> dict[str, dict]:
    """Return usage summary for all daily-tracked actions."""
    limits = get_limits_for_tier(tier)
    date_str = _today_str(timezone_name)
    daily_actions = ["post_generations_per_day", "chat_messages_per_day"]

    summary: dict[str, dict] = {}
    for action in daily_actions:
        limit = limits.get(action, 0)
        key = _usage_key(tenant_id, action, date_str)
        used = counter_get(key)
        summary[action] = {
            "used": used,
            "limit": limit,
            "percentage": round(used / limit * 100, 1) if limit > 0 else 0,
        }

    # Add non-daily limits for display
    summary["intelligence_items_per_run"] = {"limit": limits["intelligence_items_per_run"]}
    summary["leads_per_run"] = {"limit": limits["leads_per_run"]}
    summary["brand_documents_total"] = {"limit": limits["brand_documents_total"]}
    summary["newsletter_enabled"] = {"enabled": limits["newsletter_enabled"]}
    summary["max_platform_connections"] = {"limit": limits["max_platform_connections"]}
    summary["pipeline_days_per_week"] = {"days": limits["pipeline_days_per_week"]}

    return summary
```

- [ ] **Step 2: Commit**

```bash
git add functions/shared/usage_limits.py
git commit -m "feat: add tier-based usage limits module"
```

### Task 7: Create usage API endpoint

**Files:**
- Create: `functions/api/routes/usage.py`
- Modify: `functions/api/app.py` (router registration, around line 179-194)

- [ ] **Step 1: Create the endpoint**

```python
"""Usage tracking API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.middleware.auth import require_tenant
from shared.models import TenantProfile
from shared.usage_limits import get_usage_summary

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_usage(
    request: Request,
    tenant: TenantProfile = Depends(require_tenant),
):
    tier = getattr(request.state, "tenant_tier", "starter")
    summary = get_usage_summary(
        tenant_id=tenant.tenant_id,
        tier=tier,
        timezone_name=tenant.timezone,
    )
    return {"tier": tier, "usage": summary}
```

- [ ] **Step 2: Register router in app.py**

In `functions/api/app.py`, add import and registration alongside existing routers (lines 179-194):

```python
from api.routes.usage import router as usage_router
# ... in the router registration block:
app.include_router(usage_router)
```

- [ ] **Step 3: Commit**

```bash
git add functions/api/routes/usage.py functions/api/app.py
git commit -m "feat: add GET /api/usage endpoint"
```

### Task 8: Enforce limits in pipeline

**Files:**
- Modify: `functions/pipeline.py` (lines 493-540 for step 1, lines 640-740 for step 3)

- [ ] **Step 1: Add pipeline day check and item caps**

At the start of `_run_pipeline()` (after tenant is resolved, around line 520), add:

```python
from shared.usage_limits import get_limits_for_tier, is_pipeline_day
from shared.entitlements import resolve_access

# After tenant is resolved and digest_config is loaded:
effective_tier = "starter"
if tenant_id:
    tenant_doc_for_tier = get_tenant(tenant_id)
    if tenant_doc_for_tier:
        profile_for_tier = TenantProfile.model_validate(tenant_doc_for_tier)
        from shared.entitlements import resolve_access
        access = resolve_access(profile_for_tier)
        effective_tier = access.effective_tier

tier_limits = get_limits_for_tier(effective_tier)

# Check if today is a pipeline day
if tenant_id and not is_pipeline_day(effective_tier, digest_config.timezone_name):
    logger.info("pipeline.skipped_not_pipeline_day", extra={
        "tenant_id": tenant_id, "tier": effective_tier,
    })
    return {
        "tenant_id": tenant_id,
        "date": local_today,
        "timezone": digest_config.timezone_name,
        "email_status": "skipped_not_pipeline_day",
        "intel_items": 0, "post_generated": False,
        "image_generated": False, "leads_found": 0,
        "prospects_found": 0, "force_send": force_send,
    }
```

- [ ] **Step 2: Cap intelligence items and leads**

In Step 1 (intelligence), after `intel_items` are returned (line 533):
```python
# Cap intelligence items per tier
max_intel = tier_limits.get("intelligence_items_per_run", 100)
intel_items = intel_items[:max_intel]
```

In Step 3 (leads), change the hardcoded `3` limits (lines 655, 679, 700) to use tier limits:
```python
max_leads = tier_limits.get("leads_per_run", 8)
# Replace: if len(lead_items) >= 3 and len(prospect_items) >= 3:
# With:    if len(lead_items) >= max_leads and len(prospect_items) >= max_leads:
```

- [ ] **Step 3: Pass tier to Gemini calls via existing architecture**

The codebase already has a model routing system: `gemini_client.py` has `TASK_MODEL_MAP` (lines 23-38) that maps task names to per-tier models, and `GeminiClient.generate()` already accepts a `tier` parameter (line 98). The `_resolve_model()` function (line 45) resolves the correct model per task and tier.

**Update `TASK_MODEL_MAP` in `gemini_client.py`** to use the correct Gemini 3.1 models:
- Starter tier tasks → `publishers/google/models/gemini-3.1-flash-lite-preview`
- Pro tier tasks → `publishers/google/models/gemini-3.1-pro-preview`

**Pass `effective_tier` through the pipeline** to engine functions. Add `tier=effective_tier` parameter to `generate_daily_post()`, `run_and_classify()`, `qualify_inline()`, and `generate_outreach_inline()`. Each engine function forwards this as `tier=tier` to `GeminiClient().generate()`.

Do NOT add a `gemini_model` key to `TIER_LIMITS` — the model routing is handled by `TASK_MODEL_MAP` in `gemini_client.py`. Remove `"gemini_model"` from the `TIER_LIMITS` dict in `usage_limits.py` if present.

- [ ] **Step 4: Commit**

```bash
git add functions/pipeline.py functions/shared/gemini_client.py functions/engines/post_generate.py functions/engines/signals.py functions/engines/qualification.py functions/engines/outreach_generate.py
git commit -m "feat: enforce per-tier pipeline limits and model routing"
```

### Task 9: Enforce limits in API routes

**Files:**
- Modify: `functions/api/routes/chat.py`
- Modify: `functions/api/routes/drafts.py`
- Modify: `functions/api/routes/documents.py`
- Modify: `functions/api/routes/newsletters.py`
- Modify: `functions/api/routes/oauth.py`

- [ ] **Step 1: Add limit check helper**

Create a reusable helper (can go in `usage_limits.py` or as a FastAPI dependency):

```python
# Add to functions/shared/usage_limits.py:

from fastapi import HTTPException

def require_usage_limit(
    tenant_id: str,
    tier: str,
    action: str,
    timezone_name: str = "UTC",
) -> None:
    """Raise 429 if limit is exceeded. Call before the action."""
    allowed, current, limit = check_limit(tenant_id, tier, action, timezone_name)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached: {current}/{limit} {action.replace('_', ' ')}. "
                   f"Upgrade to Pro for higher limits.",
        )
```

- [ ] **Step 2: Add to chat route**

In `functions/api/routes/chat.py`, at the start of the chat handler:
```python
from shared.usage_limits import require_usage_limit, increment_usage

# Inside the handler, before processing:
require_usage_limit(tenant.tenant_id, request.state.tenant_tier, "chat_messages_per_day", tenant.timezone)
# After successful processing:
increment_usage(tenant.tenant_id, "chat_messages_per_day", tenant.timezone)
```

- [ ] **Step 3: Add to drafts quick-generate route**

In `functions/api/routes/drafts.py`, at the start of the quick-generate handler:
```python
require_usage_limit(tenant.tenant_id, request.state.tenant_tier, "post_generations_per_day", tenant.timezone)
# After successful generation:
increment_usage(tenant.tenant_id, "post_generations_per_day", tenant.timezone)
```

- [ ] **Step 4: Add document count check**

In `functions/api/routes/documents.py`, before upload:
```python
from shared.usage_limits import get_limits_for_tier
from shared.firestore_client import query_docs

limits = get_limits_for_tier(request.state.tenant_tier)
max_docs = limits["brand_documents_total"]
current_docs = query_docs("brand_documents", tenant_id=tenant.tenant_id, limit=max_docs + 1)
if len(current_docs) >= max_docs:
    raise HTTPException(status_code=429, detail=f"Document limit reached ({max_docs}). Upgrade to Pro for more.")
```

- [ ] **Step 5: Add newsletter check**

In `functions/api/routes/newsletters.py`, before generate:
```python
from shared.usage_limits import get_limits_for_tier

limits = get_limits_for_tier(request.state.tenant_tier)
if not limits["newsletter_enabled"]:
    raise HTTPException(status_code=403, detail="Newsletter generation requires Pro plan.")
```

- [ ] **Step 6: Add platform connection check**

In `functions/api/routes/oauth.py`, before authorize:
```python
from shared.usage_limits import get_limits_for_tier

limits = get_limits_for_tier(request.state.tenant_tier)
max_connections = limits["max_platform_connections"]
# Count existing connected platforms from tenant.platform_credentials
connected = len(tenant.platform_credentials)
if connected >= max_connections:
    raise HTTPException(status_code=429, detail=f"Platform connection limit reached ({max_connections}). Upgrade to Pro.")
```

- [ ] **Step 7: Commit**

```bash
git add functions/shared/usage_limits.py functions/api/routes/chat.py functions/api/routes/drafts.py functions/api/routes/documents.py functions/api/routes/newsletters.py functions/api/routes/oauth.py
git commit -m "feat: enforce usage limits across all API routes"
```

---

## Chunk 3: Auth Improvements

### Task 10: Add Firebase auth helpers

**Files:**
- Modify: `frontend/src/lib/firebase.ts` (lines 39-57)

- [ ] **Step 1: Add resetPassword and verifyEmail exports**

Add after the existing auth functions (after line 57):

```typescript
export async function resetPassword(email: string): Promise<void> {
  const { sendPasswordResetEmail } = await import("firebase/auth");
  if (!auth) throw new Error("Firebase not initialized");
  await sendPasswordResetEmail(auth, email);
}

export async function verifyEmail(): Promise<void> {
  const { sendEmailVerification } = await import("firebase/auth");
  if (!auth?.currentUser) throw new Error("No user signed in");
  await sendEmailVerification(auth.currentUser);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/firebase.ts
git commit -m "feat: add password reset and email verification helpers"
```

### Task 11: Add password reset to login page

**Files:**
- Modify: `frontend/src/app/page.tsx` (lines 25-62 area)

- [ ] **Step 1: Add forgot password state and UI**

Add state: `const [forgotMode, setForgotMode] = useState(false);`
Add state: `const [resetSent, setResetSent] = useState(false);`

Add a "Forgot password?" link below the password field that sets `forgotMode = true`.

When `forgotMode` is true, show only the email field + "Send reset link" button. On submit:
```typescript
import { resetPassword } from "@/lib/firebase";

const handleResetPassword = async () => {
  try {
    await resetPassword(email);
    setResetSent(true);
    // Show success message
  } catch (err: any) {
    if (err.code === "auth/user-not-found") {
      setError("No account found with this email.");
    } else {
      setError("Failed to send reset email. Try again.");
    }
  }
};
```

Show success message: "Reset link sent! Check your inbox." with a "Back to login" link.

- [ ] **Step 2: Send email verification on signup**

In the existing `signUpWithEmail` handler (around line 50-62), after successful signup:
```typescript
import { verifyEmail } from "@/lib/firebase";

// After successful signup:
try {
  await verifyEmail();
} catch {
  // Non-blocking — verification is a nudge, not a gate
}
```

- [ ] **Step 3: Update legal links**

Change the ToS and Privacy Policy links (currently `href="#"`) to:
```html
<a href="/terms">Terms of Service</a>
<a href="/privacy">Privacy Policy</a>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat: add password reset flow and email verification on signup"
```

### Task 12: Add email verification banner to dashboard

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx` (near top of render, around line 80-100)

- [ ] **Step 1: Add verification banner**

At the top of the dashboard content (after nav, before sections), add:

```tsx
{user && !user.emailVerified && user.providerData?.[0]?.providerId === "password" && (
  <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
    <span>
      Please verify your email address. Check your inbox or{" "}
      <button
        className="underline font-medium hover:text-amber-900"
        onClick={async () => {
          try {
            const { verifyEmail } = await import("@/lib/firebase");
            await verifyEmail();
            // Show toast
          } catch {
            // Show error toast
          }
        }}
      >
        resend verification email
      </button>.
    </span>
    <button
      className="ml-4 text-amber-500 hover:text-amber-700"
      onClick={() => {/* dismiss with local state */}}
    >
      ✕
    </button>
  </div>
)}
```

Only show for email/password users (not Google OAuth — those are already verified).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/dashboard/page.tsx
git commit -m "feat: add email verification nudge banner on dashboard"
```

---

## Chunk 4: Legal Pages

### Task 13: Create Terms of Service page

**Files:**
- Create: `frontend/src/app/terms/page.tsx`

- [ ] **Step 1: Create the page**

Create a full Terms of Service page with proper legal content. Use a clean, centered prose layout with Tailwind's `prose` class. Content based on standard SaaS ToS patterns covering:

1. Acceptance of Terms
2. Service Description — AI-powered marketing automation platform
3. Account Registration — email/OAuth, one account per person, accurate info
4. Starter & Pro Plans — Starter is free, Pro is $29/month via Stripe
5. Acceptable Use — no spam, no illegal content, no scraping abuse, no automated account creation
6. AI-Generated Content — disclaimer that AI output is not guaranteed accurate, user must review before publishing, user is responsible for compliance with platform ToS
7. Intellectual Property — user owns their content, Intonation Labs owns the platform
8. Payment Terms — Pro billed monthly, cancel anytime, no refunds for partial months
9. Data & Privacy — reference to Privacy Policy at `/privacy`
10. Service Availability — best-effort uptime, no SLA for Starter
11. Termination — either party can terminate, account deletion available in Settings
12. Limitation of Liability — standard limitation, no consequential damages
13. Governing Law — Singapore law, Singapore courts
14. Contact — support@intonationlabs.com

Entity: Intonation Labs Pte. Ltd.
Effective date: 2026-03-17

Page layout:
```tsx
export default function TermsPage() {
  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <a href="/" className="text-sm text-blue-600 hover:underline">← Back to IntoMarketing</a>
        <h1 className="mt-8 text-3xl font-bold">Terms of Service</h1>
        <p className="mt-2 text-sm text-gray-500">Effective: March 17, 2026</p>
        <div className="prose prose-gray mt-8 max-w-none">
          {/* All sections as semantic HTML */}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/terms/page.tsx
git commit -m "feat: add Terms of Service page"
```

### Task 14: Create Privacy Policy page

**Files:**
- Create: `frontend/src/app/privacy/page.tsx`

- [ ] **Step 1: Create the page**

Create a full GDPR + CCPA compliant Privacy Policy. Same layout as Terms. Content covering:

1. Data Controller — Intonation Labs Pte. Ltd., Singapore
2. Data We Collect — account data (email, name), company profile, AI-generated content, usage analytics, payment info (via Stripe)
3. How We Use Your Data — service delivery, AI content generation, analytics, billing
4. Legal Basis (GDPR) — contract performance, legitimate interest, consent
5. AI Processing — inputs sent to Google Gemini API for content generation; Google does not use paid-tier API data for training; we do not train our own models on user data
6. Third-Party Processors — Google Cloud (Vertex AI, Firestore, Firebase Auth), Stripe (payments), Sentry (error tracking)
7. Data Retention — account data kept while account active, deleted within 30 days of account deletion, usage logs kept 90 days
8. International Transfers — data processed in Google Cloud (Singapore region primary, US for some services), Stripe (US), Sentry (US); Standard Contractual Clauses apply
9. Your Rights — access, rectification, erasure (Settings > Delete Account), portability (Settings > Export Data), objection, restrict processing
10. Cookies — reference to cookie consent banner, categories (essential, analytics)
11. Children — service not intended for under 16
12. Changes — we'll notify via email for material changes
13. Contact — privacy@intonationlabs.com
14. CCPA Addendum — California residents: we don't sell personal info, right to know/delete/opt-out

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/privacy/page.tsx
git commit -m "feat: add Privacy Policy page (GDPR + CCPA)"
```

---

## Chunk 5: Cookie Consent

### Task 15: Create cookie consent component

**Files:**
- Create: `frontend/src/components/cookie-consent.tsx`
- Modify: `frontend/src/app/layout.tsx` (lines 37-39)

- [ ] **Step 1: Create the component**

```tsx
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
```

- [ ] **Step 2: Add to layout**

In `frontend/src/app/layout.tsx`, add the banner inside the body, after `{children}`:

```tsx
import CookieConsentBanner from "@/components/cookie-consent";

// In the body:
<AuthProvider>
  <ToastProvider>
    {children}
  </ToastProvider>
</AuthProvider>
<CookieConsentBanner />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/cookie-consent.tsx frontend/src/app/layout.tsx
git commit -m "feat: add GDPR-compliant cookie consent banner"
```

---

## Chunk 6: Frontend Billing UI & Cleanup

### Task 16: Update billing utilities

**Files:**
- Modify: `frontend/src/lib/billing.ts` (lines 1-44)

- [ ] **Step 1: Simplify to starter/pro only**

Rewrite `billing.ts`:

```typescript
import type { BillingSummary } from "@/types";

const TIER_ORDER: Record<string, number> = {
  starter: 0,
  pro: 1,
};

export function hasTierAccess(
  billing: BillingSummary | null | undefined,
  requiredTier: string,
): boolean {
  if (!billing) return false;
  const current = TIER_ORDER[billing.effective_tier] ?? 0;
  const required = TIER_ORDER[requiredTier] ?? 0;
  return current >= required;
}

export function planBadgeLabel(billing: BillingSummary | null | undefined): string {
  if (!billing) return "Starter";
  if (billing.effective_tier === "pro") return "Pro";
  return "Starter";
}
```

Remove `formatStarterAccessDate()` — it's no longer needed.

- [ ] **Step 2: Update types if needed**

Check `frontend/src/types` for `SubscriptionTier` type. If it includes `"free"` or `"growth"`, update to:
```typescript
export type SubscriptionTier = "starter" | "pro";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/billing.ts frontend/src/types
git commit -m "refactor: simplify billing utilities to starter/pro only"
```

### Task 17: Update settings billing tab

**Files:**
- Modify: `frontend/src/app/settings/page.tsx` (lines 706-758)

- [ ] **Step 1: Rewrite billing section**

Replace the 3-column plan grid with a 2-column grid:

**Starter (Free) card:**
- Badge: "Current plan" (always, unless Pro)
- Features: Core AI engine, Daily content (3x/week), Market intelligence (25 items), 1 post/day, 10 chat messages/day, 3 brand documents, 1 platform connection, Email digest
- No action button (it's free)

**Pro ($29/mo) card:**
- Badge: "Current plan" or "Upgrade"
- Features: Everything in Starter +, Daily content (7x/week), 100 intelligence items, 5 posts/day, 100 chat messages/day, 50 brand documents, 10 platform connections, Newsletter generation, Gemini 3.1 Pro model, Priority support
- Button: "Upgrade to Pro" (checkout) or "Manage Subscription" (portal)

Remove all trial-related messaging (trial expiry, "Keep Starter", etc.)

- [ ] **Step 2: Add usage summary section**

Above the billing grid, add a usage summary that calls `GET /api/usage`:

```tsx
// Fetch usage data
const [usage, setUsage] = useState<any>(null);
useEffect(() => {
  apiFetch("/api/usage").then(setUsage).catch(() => {});
}, []);

// Render usage bars
{usage && (
  <div className="mb-6 space-y-3">
    <h3 className="text-sm font-semibold text-gray-700">Today's Usage</h3>
    {["post_generations_per_day", "chat_messages_per_day"].map(action => {
      const data = usage.usage[action];
      if (!data) return null;
      const pct = Math.min(data.percentage, 100);
      return (
        <div key={action} className="flex items-center gap-3">
          <span className="w-40 text-xs text-gray-600 truncate">{action.replace(/_/g, " ")}</span>
          <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-400" : "bg-blue-500"}`} style={{ width: `${pct}%` }} />
          </div>
          <span className="text-xs text-gray-500 w-16 text-right">{data.used}/{data.limit}</span>
        </div>
      );
    })}
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/settings/page.tsx
git commit -m "feat: update billing UI to 2-tier starter/pro with usage display"
```

### Task 18: Update nav badge

**Files:**
- Modify: `frontend/src/components/nav.tsx` (lines 63-67)

- [ ] **Step 1: Ensure badge uses updated planBadgeLabel**

The nav already calls `planBadgeLabel(billing)`. Since we updated `billing.ts` in Task 16, this should now show "Starter" or "Pro" automatically. Verify no hardcoded "Free" or "Trial" strings remain in `nav.tsx`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/nav.tsx
git commit -m "chore: verify nav badge shows starter/pro labels"
```

---

## Final Verification

### Task 19: End-to-end verification

- [ ] **Step 1: Verify backend starts without errors**

```bash
cd functions && python -c "from shared.entitlements import resolve_access; from shared.usage_limits import TIER_LIMITS; print('Backend OK')"
```

- [ ] **Step 2: Verify frontend builds**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Verify no remaining references to free tier**

Search for remaining `"free"` tier references that should have been updated:
```bash
grep -rn '"free"' functions/shared/entitlements.py functions/api/middleware/auth.py functions/api/routes/billing.py frontend/src/lib/billing.ts
```

Expected: No results (or only in comments/migration handling).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final verification of tier restructure and launch features"
```
