# Feature Readiness Audit

Audit date: 2026-03-14

This matrix reflects current behavior after the latest stabilization pass. Status values are:

- `implemented`: usable end-to-end at a realistic production baseline
- `partially implemented`: real code paths exist, but important gaps remain
- `stubbed/mock`: visible flow exists but external behavior is simulated
- `missing`: no meaningful implementation

## F1 Direct Social Publishing

- Status: `stubbed/mock`
- What works:
  - `functions/api/routes/drafts.py` creates `publishing_records` and `calendar_events` when a draft is scheduled.
  - `frontend/src/components/sections/content-drafts.tsx` supports one-click approval and scheduling.
  - `frontend/src/components/sections/calendar.tsx` supports persisted rescheduling.
  - `functions/engines/publisher.py` processes due `publishing_records`.
- Commercial blockers:
  - Publisher still performs mock delivery and marks records published without real Buffer/LinkedIn/X API calls.
  - No OAuth token acquisition/refresh flow in the UI.

## F2 CRM-Lite Lead Tracker

- Status: `partially implemented`
- What works:
  - `frontend/src/components/sections/leads.tsx` is a real Kanban board with persisted stage changes.
  - `functions/api/routes/leads.py` reads/writes `qualified_leads` and now enriches lead cards with the latest outreach draft.
  - `Send Outreach` now uses real stored draft content when available.
- Commercial blockers:
  - Qualification/outreach generation is not yet fully wired into a user-facing intake flow.
  - There is no lead activity timeline UI for `CRMActivity`.

## F3 Brand Voice Customisation

- Status: `partially implemented`
- What works:
  - `frontend/src/app/settings/page.tsx` saves tone sliders and uploads brand guideline PDFs into the document workspace.
  - `functions/api/routes/settings.py` now persists the tone slider values.
  - `functions/engines/post_generate.py` consumes `brand_guidelines` when they exist.
- Commercial blockers:
  - Uploaded PDFs are stored, but automatic ingestion into tenant-scoped `brand_chunks` is not yet wired end-to-end.
  - There is still a mismatch between root-level brand chunk sync utilities and tenant-scoped retrieval.

## F4 Performance Analytics Dashboard

- Status: `partially implemented`
- What works:
  - `functions/api/routes/analytics.py` serves real aggregated dashboard data.
  - `frontend/src/components/sections/analytics.tsx` renders live metrics and exports CSV.
  - `functions/engines/analytics_gatherer.py` now writes tenant-scoped analytics snapshots correctly.
- Commercial blockers:
  - Engagement metrics are still placeholder-generated until real provider analytics APIs are integrated.

## F5 Onboarding Flow & Tenant Self-Setup

- Status: `partially implemented`
- What works:
  - `frontend/src/app/onboarding/page.tsx` is now a persisted 5-step flow.
  - `functions/api/routes/onboarding.py` stores company, audience, digest, platform, and tone configuration.
  - Final onboarding completion triggers the tenant pipeline.
- Commercial blockers:
  - No real website scraping or competitor discovery automation yet.
  - No real OAuth channel connection flow yet.

## F6 Content Calendar & Multi-Platform Scheduler

- Status: `partially implemented`
- What works:
  - Scheduled drafts are visible in the calendar.
  - Drag-and-drop date rescheduling persists and keeps scheduling records in sync.
  - `calendar_manager.py` exists for automated scheduling logic.
- Commercial blockers:
  - UI reads scheduled drafts rather than full `calendar_events`, so newsletter/outreach calendar events are not surfaced.
  - Suggested times are static heuristics, not platform-derived optimization.

## F7 White-Label Agency Mode

- Status: `stubbed/mock`
- What works:
  - Models and Firestore filtering scaffolding exist.
  - `/agency` exists as a preview page.
- Commercial blockers:
  - The page still uses sample data only.
  - No agency auth, tenant switching API, reporting backend, or persisted branding.

## F8 Competitor Monitoring & Alert System

- Status: `partially implemented`
- What works:
  - Competitor names feed into intelligence gathering and signal generation.
  - Existing intelligence/signals pipeline can surface competitor-related items.
- Commercial blockers:
  - No dedicated competitor monitoring UI or alert digest.
  - Website/pricing/job-page monitoring is not implemented at production quality.

## F9 LinkedIn Organic Lead Enrichment

- Status: `stubbed/mock`
- What works:
  - `functions/engines/linkedin_enrichment.py` now targets the correct `qualified_leads` collection.
- Commercial blockers:
  - Enrichment is still synthetic mock data.
  - No frontend trigger, no API route, and no real provider integration.

## F10 AI Newsletter & Blog Auto-Publishing

- Status: `stubbed/mock`
- What works:
  - Newsletter drafting exists via `functions/api/routes/newsletters.py`.
  - `newsletter_publisher.py` exists as a delivery worker.
- Commercial blockers:
  - Draft and publisher flows are still disconnected from a user-facing workflow.
  - Delivery remains mock-backed and not connected to Beehiiv/Substack/Ghost.

## Commercial Priority Order

1. Finish real social publishing integration for F1.
2. Complete tenant-scoped brand document ingestion for F3.
3. Replace placeholder analytics metrics with live platform metrics for F4.
4. Add real onboarding automation and OAuth connection flows for F5.
5. Convert Agency Mode from preview to live data for F7.
