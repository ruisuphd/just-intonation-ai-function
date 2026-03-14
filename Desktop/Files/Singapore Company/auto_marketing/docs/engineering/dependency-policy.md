# Dependency Policy

## Goals

- Keep runtime dependencies minimal and reproducible.
- Prefer permissive licenses only (MIT, Apache-2.0, BSD, ISC).
- Catch vulnerable dependencies before deployment.

## Python

- Runtime dependencies live in `functions/requirements.txt`.
- Dev-only dependencies live in `functions/requirements-dev.txt`.
- Reproducible runtime lock lives in `functions/requirements-lock.txt`.
- CI installs `requirements-dev.txt` so lint/tests run against the same runtime set.

## Update Cadence

- Weekly automated dependency update PRs via Dependabot.
- Monthly security review for unresolved advisories.

## Security Checks

- `pip-audit -r functions/requirements-lock.txt` for runtime Python advisories.

## Licensing

- New direct dependencies with copyleft licenses are not allowed.
- If a transitive package introduces a non-permissive license, document and replace if feasible.
