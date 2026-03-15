# Auto Marketing — Full QA Audit Report

**Audit Date:** 2025-03-14  
**Scope:** All 10 features from the Comprehensive Integration Plan  
**Methodology:** Code review, API inspection, frontend/backend flow tracing, dependency audit

---

## Executive Summary

| Severity | Count | Status |
|----------|-------|--------|
| **Critical** (runtime failure) | 2 | Must fix before deploy |
| **High** (broken UX/data) | 5 | Fix in current sprint |
| **Medium** (partial/incomplete) | 6 | Plan for next sprint |
| **Low** (hardening) | 4 | Backlog |

---

## 1. Critical Issues (Must Fix)

### C1. `analytics_gatherer.py` — ImportError at runtime

**Location:** `functions/engines/analytics_gatherer.py:8`

**Problem:** Imports `write_doc` from `shared.firestore_client`, but that function does not exist. The Firestore client exposes `set_doc` and `add_doc` only.

**Evidence:**
```python
from shared.firestore_client import query_docs, write_doc  # write_doc does not exist
# ...
write_doc(f"tenants/{tenant_id}/analytics_snapshots", snapshot_id, snapshot_data)
```

**Impact:** Any invocation of `gather_daily_analytics()` (e.g., from a cron job) will raise `ImportError` and fail.

**Fix:** Replace `write_doc` with `set_doc` and correct the collection usage:
```python
from shared.firestore_client import query_docs, set_doc
# ...
set_doc("analytics_snapshots", snapshot_id, snapshot_data, tenant_id=tenant_id)
```

---

### C2. `analytics_gatherer.py` — Incorrect Firestore collection usage

**Location:** `functions/engines/analytics_gatherer.py:30, 49`

**Problem:** Calls `query_docs(f"tenants/{tenant_id}/published_posts")` and `query_docs(f"tenants/{tenant_id}/outreach_drafts")`. The `query_docs` API expects a collection name (e.g. `"published_posts"`) and optional `tenant_id`, not a full path. Passing a path causes Firestore to treat it as a root collection name, producing invalid queries.

**Evidence:** `firestore_client._resolve_collection(collection, tenant_id)` builds the path as `tenants/{tenant_id}/{collection}` when `tenant_id` is provided. Passing a path as `collection` bypasses this and breaks.

**Fix:**
```python
published_posts = query_docs("published_posts", tenant_id=tenant_id)
outreach_drafts = query_docs("outreach_drafts", tenant_id=tenant_id)
```

**Schema note:** The publisher engine uses `publishing_records` (not `published_posts`). Published content lives in `publishing_records` where `status == "published"`. Either (a) change analytics_gatherer to query `publishing_records` with that filter, or (b) ensure the publisher writes a summary to `published_posts` when publishing. The `outreach_drafts` collection exists and is used by the outreach API.

---

## 2. High Priority Issues (Fix This Sprint)

### H1. `linkedin_enrichment.py` — Wrong collection name

**Location:** `functions/engines/linkedin_enrichment.py:10, 18, 41`

**Problem:** Uses collection `"leads"` for `get_doc` and `update_doc`. The rest of the application uses `"qualified_leads"` (leads API, qualification engine, outreach engine).

**Impact:** Enrichment reads/writes a non-existent or different collection. Leads will never be enriched; if a `leads` collection exists separately, data will be split.

**Fix:** Change all `"leads"` to `"qualified_leads"`.

---

### H2. Calendar drag-and-drop reschedule does not work

**Location:**  
- Frontend: `frontend/src/components/sections/calendar.tsx:90-93`  
- Backend: `functions/api/routes/drafts.py:46-64`

**Problem:** The Calendar sends `PATCH /api/drafts/{id}/status` with `{ batch_date: date }`, but the `DraftStatusUpdate` model and handler only accept `status`. The `batch_date` field is ignored.

**Evidence:**
```python
class DraftStatusUpdate(BaseModel):
    status: str
# ... handler only updates status and updated_at
```

**Impact:** Users can drag drafts to different days, but the change is not persisted. The UI updates optimistically, then reverts on refresh.

**Fix options:**
1. Extend `DraftStatusUpdate` to include `batch_date: str | None = None` and update the PATCH handler to merge it into the draft document.
2. Add a separate `PATCH /api/drafts/{id}` endpoint that allows partial updates including `batch_date`.

---

### H3. Leads Kanban — No user feedback on PATCH failure

**Location:** `frontend/src/components/sections/leads.tsx:69-72`

**Problem:** On drag-and-drop, the UI optimistically updates. If the PATCH fails, only `console.error` is called. There is no toast, inline error, or rollback.

**Impact:** Users may believe the lead moved, but the backend did not persist the change. Data inconsistency and confusion.

**Fix:** On catch, revert the optimistic update (`setLeads` to previous state) and display an error message (e.g. `setError(...)` or a toast).

---

### H4. Analytics section — 100% mock, no real data

**Location:** `frontend/src/components/sections/analytics.tsx`

**Problem:** All metrics are hardcoded ("124.5K", "42.8%", "842"). No API calls. "Export to CSV" shows an alert. The bar chart uses static placeholder data.

**Impact:** Users see fake numbers. No ROI visibility. Feature appears complete but delivers no value.

**Fix:** Add an `/api/analytics` endpoint that aggregates from `analytics_snapshots` (once C1/C2 are fixed) or from `PostMetrics`/`OutreachMetrics`. Wire the Analytics section to fetch and render real data. Implement CSV export from that data.

---

### H5. Overview — API errors silently reset counts to 0

**Location:** `frontend/src/components/sections/overview.tsx:32-67`

**Problem:** `loadDraftCount`, `loadIntelCount`, `loadLeadCount` catch errors and set counts to 0 with no user feedback.

**Impact:** If the API is down or auth fails, users see "0 drafts, 0 intel, 0 leads" with no indication of an error. Looks like empty data instead of a failure.

**Fix:** Track an error state (e.g. `apiError: string | null`) and display a subtle banner or inline message when any fetch fails.

---

## 3. Medium Priority Issues (Plan for Next Sprint)

### M1. Content Drafts — "Approve & Schedule" only sets status

**Location:** `functions/api/routes/drafts.py`, `frontend/src/components/sections/content-drafts.tsx`

**Problem:** "Approve & Schedule" sets draft `status` to `"scheduled"` but does not create a `PublishingRecord` or `CalendarEvent`. The publisher engine looks for `publishing_records`; nothing creates them from approved drafts.

**Impact:** Approved drafts are never actually published. The publishing pipeline is disconnected from the UI approval flow.

**Fix:** When status becomes `"scheduled"`, either (a) create a `PublishingRecord` with `scheduled_for` and `post_id`, or (b) have the calendar_manager pick up drafts with `status == "scheduled"` and create calendar events / publishing records.

---

### M2. Publisher engine — No trigger path

**Location:** `functions/engines/publisher.py`, `functions/main.py` (or equivalent)

**Problem:** `run_publisher()` exists but may not be wired to any Cloud Scheduler, Pub/Sub, or HTTP endpoint.

**Fix:** Add a scheduled Cloud Function or cron job that invokes `run_publisher()` at the desired frequency (e.g. every 15 minutes).

---

### M3. Calendar manager — Firestore Timestamp handling

**Location:** `functions/engines/calendar_manager.py:57-60`

**Problem:** `events[-1].get("scheduled_for")` may return a Firestore `Timestamp` object. Arithmetic `last_event_time + timedelta(days=1)` can fail or behave incorrectly if the value is not a Python `datetime`.

**Fix:** Normalize Firestore Timestamps to `datetime` before arithmetic (e.g. `getattr(ts, "datetime", ts)` or use `firestore_convert` helpers).

---

### M4. Leads — "Send Outreach" uses suggested angle, not full draft

**Location:** `frontend/src/components/sections/leads.tsx:111-114`

**Problem:** `mailto:` body uses `lead.draft_content || lead.suggested_outreach_angle`. `QualifiedLead` has `suggested_outreach_angle` from qualification; the full email draft lives in `OutreachDraft` (linked by `lead_id`). `draft_content` is likely never set on the lead.

**Impact:** Users get a short angle in the email body, not the full AI-drafted outreach. Manual editing required.

**Fix:** Fetch the OutreachDraft for the lead (or include `draft_content` in the lead API response when a draft exists) and use that for the mailto body.

---

### M5. NewsletterDraft vs newsletter collection schema

**Location:** `functions/engines/calendar_manager.py`, `functions/shared/models.py`

**Problem:** Calendar manager validates newsletter data with `NewsletterDraft.model_validate(newsletter_data)`. The `newsletters` collection may store different shapes (e.g. from `newsletter_generate`). Schema mismatch can cause validation errors.

**Fix:** Verify the newsletter documents written by the generate engine match `NewsletterDraft`. Align field names and required/optional fields.

---

### M6. Brand Voice — Settings save/load not verified

**Location:** `frontend/src/app/settings/page.tsx` (Brand Voice tab), backend settings API

**Problem:** The Brand Voice wizard (tone sliders, PDF upload) must persist to the backend. Unclear if `handleSave` and `fetchSettings` include brand voice fields and if the backend stores them in a format usable by `brand_synthesizer` and `post_generate`.

**Fix:** Trace the full flow: Settings PUT → Firestore → BrandGuidelines/brand_guidelines → engines. Add tests and verify round-trip.

---

## 4. Low Priority Issues (Backlog)

### L1. API routes — Limited structured error handling

**Location:** Multiple route files

**Problem:** Many routes lack explicit try/except. Firestore/network/LLM errors can surface as raw 500s. No retries for transient failures.

**Recommendation:** Add centralized exception handling middleware and retry logic for Firestore operations where appropriate.

---

### L2. Test coverage gaps

**Current coverage:** Pipeline, drafts/settings contracts, auth, entitlements, Gemini client.

**Missing:** API route handlers, engines (intelligence, signals, qualification, post_generate, etc.), Firestore CRUD helpers, frontend components, E2E tests.

**Recommendation:** Add contract tests for new API endpoints and engine entry points. Add at least smoke E2E for critical user flows (generate draft, approve, view leads).

---

### L3. Stripe in requirements vs lock file

**Location:** `functions/requirements.txt`, `functions/requirements-lock.txt`

**Problem:** Stripe may be in requirements but not in the lock file, risking version drift across installs.

**Fix:** Run `pip-compile` or equivalent to ensure lock file includes Stripe and all transitive deps.

---

### L4. Agency and Onboarding routes — Auth and integration

**Location:** `/onboarding`, `/agency` frontend routes

**Problem:** Onboarding creates tenants; needs to integrate with auth (who is the owner_uid?). Agency dashboard needs real tenant list from backend, not mocked data. Both require backend endpoints if not already present.

**Fix:** Verify onboarding API (`POST /onboarding/create-tenant`, etc.) is called and that agency dashboard fetches real tenants for the logged-in agency user.

---

## 5. Verification Checklist

Before marking QA complete, verify:

- [ ] `analytics_gatherer` imports run without error and `gather_daily_analytics()` executes
- [ ] `linkedin_enrichment` reads/writes `qualified_leads`
- [ ] Calendar drag-drop persists `batch_date` and survives refresh
- [ ] Leads Kanban shows error and rollback on PATCH failure
- [ ] Analytics section displays real aggregated metrics
- [ ] Overview shows an error state when API calls fail
- [ ] Approved drafts create publishing records and can be published
- [ ] Publisher cron/trigger is configured and runs

---

## 6. Recommended Fix Order

1. **C1, C2** — analytics_gatherer (unblocks analytics pipeline)
2. **H1** — linkedin_enrichment collection name
3. **H2** — Calendar batch_date support in drafts API
4. **H3** — Leads error handling and rollback
5. **H4** — Analytics API and real data integration
6. **H5** — Overview error state
7. **M1–M6** — In order of user impact

---

*Report generated from codebase exploration. No code changes made during this audit.*
