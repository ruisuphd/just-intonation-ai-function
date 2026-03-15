# Runbook: Safe Rollback

## Preconditions

- Current deploy is unhealthy or introduces regressions.
- Previous known-good artifact/tag is available.

## Rollback Steps

1. Freeze further deploys.
2. Roll back the daily pipeline:
   - redeploy the previous known-good `fn-daily-pipeline` revision/source.
3. If a scheduler change caused the regression:
   - disable or pause the `daily-pipeline` Cloud Scheduler job until the rollback is complete.
4. If infra caused regression:
   - apply last known-good Terraform state/config.

## Verification

Run smoke matrix `docs/qa/smoke-test-matrix.md`:

- manual invocation of `fn-daily-pipeline`
- Firestore writes for `intelligence_items` and `prospect_signals`
- daily brief email delivery
- image generation and RAG retrieval if enabled

## Post-Rollback

1. Keep canary traffic at 0% for failed revision.
2. Open incident with root cause and prevention tasks.
3. Add regression test before reattempting deployment.
