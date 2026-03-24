# Runbook: DLQ Replay

For synchronous API failures and `trace_id` correlation, see [api-5xx-triage.md](./api-5xx-triage.md).

## Scope

Dead-letter topics:

- `content-generate-dlq`
- `batch-complete-dlq`

## Triage

1. Identify alert time and topic from Monitoring.
2. Inspect recent function logs for matching `batch_id` or `message_id`.
3. Confirm root cause category:
   - malformed payload
   - transient external API failure
   - missing permissions/config

## Replay Procedure

1. Pull affected message from DLQ subscription.
2. Validate payload shape against current schema.
3. Fix root cause before replay.
4. Republish payload to primary topic:
   - `content-generate` or `batch-complete`.
5. Monitor the corresponding function logs and package status.

## Rollback Criteria

Stop replay and escalate if:

- >10% replay attempts fail within 15 minutes.
- repeated failures have same stack trace after fix.
- downstream package statuses remain stuck in `generating`.
