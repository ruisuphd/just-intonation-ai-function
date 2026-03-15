# Local QA Runbook

Professional QA checklist for verifying frontend and backend behavior before production release.

## Prerequisites

- Node 20+, Python 3.12+
- GCP project configured (for Firestore, Storage, Vertex AI)
- `.env` in project root; `frontend/.env.local` with `NEXT_PUBLIC_*` vars (copy from `frontend/.env.example`)

## 1. Backend QA

### 1.1 Lint and Tests

```bash
make qa-backend
```

- **Lint**: `ruff check . && ruff format --check`
- **Tests**: `python -m pytest tests/ -v`

**Expected**: All pass. No lint errors, no test failures.

### 1.2 API Contract (Headless)

The pytest suite includes contract tests that exercise the API in-process via FastAPI TestClient. No live server required.

Key contract files:
- `test_drafts_and_settings_contracts.py`
- `test_analytics_and_leads_contracts.py`
- `test_entitlements_and_billing.py`
- `test_publish_schedule_smoke.py`
- `test_firestore_client_auth.py`

### 1.3 API Health (Live)

Start the API locally:

```bash
make dev-api
```

Then:

```bash
curl -s http://localhost:8080/api/health | jq
```

**Expected**: `{"status": "ok"}`

---

## 2. Frontend QA

### 2.1 Build and Type Check

```bash
make qa-frontend
# or
cd frontend && npm run build && npx tsc --noEmit
```

**Expected**: Build succeeds, no TypeScript errors.

### 2.2 Dev Server

```bash
make dev-frontend
# or
cd frontend && npm run dev
```

Frontend at `http://localhost:3000`. API must be at `http://localhost:8080` (or set `NEXT_PUBLIC_API_URL`).

---

## 3. Full-Stack Browser QA

### 3.1 Start Both Services (Optional)

For manual testing, run in separate terminals:

```bash
make dev-api   # Terminal 1: API on http://localhost:8080
make dev-frontend   # Terminal 2: Frontend on http://localhost:3000
```

Playwright E2E (`make qa-e2e`) starts both automatically.

### 3.2 E2E Tests (Playwright)

```bash
make qa-e2e
# or
cd frontend && npm run test:e2e
```

Starts API (port 8080) and frontend (port 3000) via Playwright `webServer`, then runs browser tests. Tests cover: login page load, API health, onboarding redirect.

### 3.3 Manual Smoke Checklist

Open `http://localhost:3000` in a browser. Verify:

| # | Flow | Steps | Pass? |
|---|------|-------|-------|
| 1 | Login page loads | Visit `/` | AutoMark branding, Google/Email buttons visible |
| 2 | Sign in | Click "Continue with Google" (or use test email) | Redirects to dashboard or completes auth |
| 3 | Dashboard load | After login | Overview, Content, Analytics sections render |
| 4 | Settings > Platforms | Go to Settings → Platforms | Connect LinkedIn / Connect X buttons present |
| 5 | OAuth status | Check connection status | Shows connected or "Not connected" |
| 6 | Leads (Pro) | Go to Leads section (Pro tier) | Enrich button on lead cards with LinkedIn URL |
| 7 | Documents | Upload a PDF | Upload succeeds; document appears in list |
| 8 | Content drafts | Load Content section | Drafts list or empty state |

### 3.4 API Golden Paths (curl)

With API at `http://localhost:8080`, these require a valid Bearer token from Firebase auth:

| Endpoint | Expected |
|----------|----------|
| `GET /api/health` | `{"status": "ok"}` (no auth) |
| `GET /api/settings` | 401 without token; 200 with valid token |

---

## 4. Exit Gate (Pre-Release)

Before promoting to production:

- [ ] `make qa` passes (backend + frontend build)
- [ ] `make qa-e2e` passes (if Playwright configured)
- [ ] Manual smoke: login, dashboard, settings, OAuth buttons visible
- [ ] No high/critical `pip audit` / `npm audit` findings
- [ ] OAuth redirect URIs in LinkedIn/X apps include production URL

---

## 5. Troubleshooting

| Issue | Check |
|-------|-------|
| API 500 on startup | `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS` or ADC |
| Frontend "Failed to fetch" | `NEXT_PUBLIC_API_URL`, CORS `ALLOWED_ORIGINS` includes `http://localhost:3000` |
| OAuth callback fails | `API_URL` or `APP_URL` matches callback URL; redirect URI in LinkedIn/X app |
| Playwright timeout | Ensure API (8080) and frontend (3000) are running |
