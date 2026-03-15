# Smoke Test Matrix

This matrix is the non-regression baseline for conservative refinements.
Run it before and after every phase.

## Golden Paths

| ID | Flow | Steps | Expected Result |
|---|---|---|---|
| GP-01 | Login and session | Sign in with Google, load dashboard, refresh browser | User remains authenticated, dashboard loads |
| GP-02 | Intelligence list | Load Intelligence page | `GET /api/intelligence` returns items array |
| GP-03 | Topic generation | Click "Write a post now" on Content page | `POST /api/drafts/quick-generate` returns draft without error |
| GP-04 | Draft lifecycle | Load Content page, copy a draft | `GET /api/drafts` returns drafts; `PATCH /api/drafts/{id}/status` persists |
| GP-04A | Schedule and publish | Approve a draft, confirm `publishing_records`, run publisher worker, then analytics sync | Draft becomes `scheduled`, publisher flips due records to `published`, analytics snapshot is written |
| GP-05 | Lead list | Load Leads page (Growth/Pro tier) | `GET /api/leads` returns leads array; starter tier sees 403 |
| GP-06 | Lead delete | Delete a lead (Growth/Pro tier) | `DELETE /api/leads/{id}` removes record |
| GP-07 | Documents lifecycle | Upload file, delete file | `POST /api/documents` uploads; `DELETE /api/documents/{id}` removes |
| GP-08 | Settings lifecycle | Save company info, platforms, notifications | `PUT /api/settings` persists; `GET /api/settings` returns updated values |
| GP-09 | Billing portal | Click "Manage billing" on Settings > Billing | `GET /billing/portal` returns Stripe portal URL |
| GP-10 | Health endpoint | Request `/api/health` | Returns `{"status": "ok"}` |
| GP-11 | Onboarding flow | Create tenant, upload document, complete | `POST /onboarding/create-tenant`, `POST /onboarding/upload-document`, `POST /onboarding/complete` |

## Contract Baseline

Validate these response-shape guarantees:

- `GET /api/settings` includes `tenant_id`, `company_name`, `subscription_tier`, `subscription_status`, `platforms_enabled`.
- `GET /api/intelligence` returns `{"items": [...]}`.
- `GET /api/drafts` returns `{"drafts": [...]}`.
- `GET /api/analytics` returns `{"summary": {...}, "series": [...]}`.
- `GET /api/leads` returns `{"leads": [...]}` (Growth/Pro only; 403 for Starter).
- `GET /api/outreach` returns `{"drafts": [...]}` (Growth/Pro only).
- `GET /api/newsletters` returns `{"newsletters": [...]}` (Growth/Pro only).
- `GET /api/documents` returns `{"documents": [...]}`.
- `GET /billing/subscription` returns `tenant_id`, `subscription_tier`, `subscription_status`.
- `GET /api/health` returns `{"status": "ok"}`.

### Not yet implemented (future)

These endpoints are referenced in earlier documentation but do not exist yet:

- `/api/suppress-list`
- `/api/signals/{id}/dismiss`
- `/api/intelligence/gather`
- `/api/leads/{id}/export-pii`

## Exit Gate

No phase can be promoted unless:

- All golden paths pass.
- Backend and frontend test suites pass in CI.
- No new lint/type errors are introduced.
