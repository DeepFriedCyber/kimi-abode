# Security notice — credential exposure

## What happened

Earlier revisions of this repository contained real credentials in documentation
files:

| Credential | Location (pre-cleanup) |
|---|---|
| PostgreSQL password | `docs/REBUILD_DATABASE.md`, `docs/STATUS_REPORT.md` |
| `JWT_SECRET` | `FINAL_VERIFICATION_REPORT.md` |
| POI ingest key | `.env` (local only) |

These have been replaced with `<ROTATE-ME-…>` placeholders, but **git history
still contains the original values**. Deleting a string from the working tree is
not a remediation.

## Required actions

1. **Rotate the PostgreSQL password** and update `docker-compose`/deployment
   secrets. If the volume was initialised with the old password, changing it via
   `ALTER USER` is required (`POSTGRES_PASSWORD` is only applied on first init).
2. **Rotate `JWT_SECRET`.** Every token signed with the old secret must be
   considered forgeable. Rotating invalidates all sessions — which is the point.
3. **Rotate `POI_INGEST_API_KEY`** (the legacy `POI_INJECTION_SECRET` name is
   still accepted for compatibility; migrate and remove it).
4. Purge history if the repository is public (`git filter-repo`), or treat the
   history as public permanently and rotate.
5. Keep `gitleaks` enabled in CI (see `.github/workflows/ci.yml`).

## Preventative measures now in place

- Secrets are loaded from environment files that are git-ignored.
- `JWT_SECRET` has no literal fallback: production refuses to boot without a
  ≥32-character value; development generates an ephemeral secret.
- `CORS_ORIGIN="*"` is rejected in production and warns in development.
- POI ingest fails closed in production when no API key is configured and uses
  a constant-time comparison.
- Placeholder API keys (`sk-proj-XXX…`) are ignored rather than used.
