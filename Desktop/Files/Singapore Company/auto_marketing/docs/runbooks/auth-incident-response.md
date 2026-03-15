# Runbook: Auth Incident Response

## Trigger Conditions

- sudden spike in `401` or `403` responses
- admin user loses access
- unauthorized access attempt detected

## Immediate Actions

1. Inspect `system_config/authz` in Firestore.
2. Verify:
   - `enforce`
   - `allowed_emails`
   - `allowed_uids`
3. Validate Firebase token claims for the affected user.

## Containment

- If legitimate admin is blocked, temporarily disable enforcement:
  - set `system_config/authz.enforce=false`
  - redeploy Firestore rules if needed
- If unauthorized actor is detected:
  - keep enforcement enabled
  - remove compromised identity from allowlist
  - rotate credentials/secrets if exposure is suspected

## Recovery

1. Correct allowlist entries.
2. Re-enable enforcement.
3. Re-run the authenticated Firestore access smoke flow.
4. Capture timeline and root cause in postmortem.
