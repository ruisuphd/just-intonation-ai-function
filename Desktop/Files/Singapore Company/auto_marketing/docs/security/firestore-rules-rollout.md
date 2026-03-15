# Firestore Rules Rollout

## Objective

Tighten access control without breaking the current single-admin workflow.

## Stages

1. **Legacy-compatible mode (default)**
   - `system_config/authz` document missing or `enforce != true`.
   - Behavior remains: authenticated users can read/write.

2. **Shadow allowlist mode**
   - Create `system_config/authz` with:
     - `enforce: false`
     - `allowed_uids: []`
     - `allowed_emails: []`
   - Populate target admin identities.
   - Validate reads/writes from intended account.

3. **Enforced allowlist mode**
   - Set `enforce: true`.
   - Monitor for denied requests and auth errors.
   - Keep rollback path: set `enforce: false`.

## Rollback

If access regressions appear:

- set `system_config/authz.enforce=false`
- keep allowlist data intact
- validate golden-path smoke tests
