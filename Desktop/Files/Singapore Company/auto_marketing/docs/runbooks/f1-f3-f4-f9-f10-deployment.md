# F1, F3, F4, F9, F10 — Deployment Runbook

## Pre-Deploy Checklist

- [ ] All tests pass: `make qa` or `make qa-backend` and `make qa-frontend`
- [ ] No high/critical `pip audit` or `npm audit` advisories
- [ ] Secrets created in GCP Secret Manager (see Secrets table below)
- [ ] LinkedIn and X developer apps created; redirect URIs configured
- [ ] Apollo API key obtained (for F9 lead enrichment)
- [ ] Ghost URL and Admin API key (for F10; optional)

## Secrets (GCP Secret Manager)

| Secret ID | Purpose |
|-----------|---------|
| `linkedin-client-id` | LinkedIn OAuth app client ID |
| `linkedin-client-secret` | LinkedIn OAuth app client secret |
| `x-client-id` | X (Twitter) OAuth app client ID |
| `x-client-secret` | X (Twitter) OAuth app client secret |
| `apollo-api-key` | Apollo.io API key for lead enrichment |

Optional: `ghost-default-url`, `ghost-default-key` (or use env vars).

## Environment Variables

Add to Cloud Run (API) and/or Cloud Functions:

- `API_URL` — Base URL of the deployed API (for OAuth redirect_uri)
- `APP_URL` — Frontend URL (for post-OAuth redirect to settings)
- `REAL_PUBLISHING_ENABLED` — Set to `true` for real LinkedIn/X publishing (default: true)
- `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` — Override secrets if using env
- `X_CLIENT_ID`, `X_CLIENT_SECRET` — Override secrets if using env
- `APOLLO_API_KEY` — Override for lead enrichment
- `GHOST_DEFAULT_URL`, `GHOST_DEFAULT_KEY` — For newsletter publishing

## Deployment Order

1. **Deploy backend (API + Functions)**
   - `make deploy-api` — Cloud Run API (OAuth callbacks, leads enrich, newsletter schedule)
   - `make deploy-pipeline` — fn-tenant-pipelines
   - `make deploy-publisher` — fn-scheduled-publisher (real LinkedIn/X when credentials exist)
   - `make deploy-analytics` — fn-analytics-sync
   - Capture function URLs and update `infra/terraform.tfvars`

2. **Infrastructure**
   - `make infra-apply` — Scheduler jobs point to new function URLs

3. **Frontend**
   - `make deploy-frontend` — Firebase App Hosting
   - Ensure OAuth redirect URIs in LinkedIn/X apps include production API URL

4. **Post-deploy**
   - Trigger publisher manually once (or wait for cron)
   - Trigger analytics sync once
   - Smoke test: connect LinkedIn/X in Settings, schedule a draft, verify `external_id`

## Rollback

- **Functions**: Redeploy from previous Git tag: `git checkout <previous-tag> && make deploy-*`
- **API (Cloud Run)**: `gcloud run services update-traffic automark-api --to-revisions=PREVIOUS=100`
- **Scheduler**: Revert `terraform.tfvars` and run `make infra-apply`
- **Frontend**: Redeploy previous build from Firebase
- **Feature flag**: Set `REAL_PUBLISHING_ENABLED=false` to revert to mock publishing without redeploy

## OAuth Redirect URI Format

- **LinkedIn callback**: `{API_URL}/api/oauth/linkedin/callback`
- **X callback**: `{API_URL}/api/oauth/x/callback`

Register these exact URLs in the respective developer app settings.
