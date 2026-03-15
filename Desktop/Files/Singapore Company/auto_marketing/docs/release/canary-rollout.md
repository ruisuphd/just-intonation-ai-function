# Canary Rollout Checklist

## Pre-Deploy Gate

- Backend tests pass.
- Frontend tests pass.
- Smoke matrix baseline passes.
- No new high/critical dependency advisories in runtime set.

## Traffic Plan

1. Deploy candidate revision with 0% traffic.
2. Route 10% traffic for 30 minutes.
3. If healthy, increase to 50% for 30 minutes.
4. Promote to 100% only if all SLO checks pass.

## SLO Checks During Canary

- API 5xx rate <= baseline.
- p95 latency <= baseline + 10%.
- DLQ publish count remains zero.
- No sustained increase in auth failures.

## Abort Criteria

- Error rate increase > 30% over baseline for 10+ minutes.
- p95 latency regression > 25% for 10+ minutes.
- repeated failures in golden-path smoke scenarios.

## Rollback

Follow `docs/runbooks/safe-rollback.md` immediately when abort criteria are met.
