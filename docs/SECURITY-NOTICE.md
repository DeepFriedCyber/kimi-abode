# Security notice — credential exposure

## What happened

Earlier revisions of this repository contained real credentials in documentation
files that were committed and pushed to a public GitHub repository:

| Credential | Location (pre-cleanup) | In git history |
|---|---|---|
| PostgreSQL password | `docs/REBUILD_DATABASE.md`, `docs/STATUS_REPORT.md` | yes — 2 commits |
| `JWT_SECRET` | `FINAL_VERIFICATION_REPORT.md` | yes — 2 commits |
| POI ingest key (`POI_INJECTION_SECRET`) | `FINAL_VERIFICATION_REPORT.md` | yes — 2 commits |

The working tree has been cleaned and history will be rewritten, but **rotation
is the remediation** — a password that has been public is compromised even after
the history is purged, because clones, forks and caches of it exist.

The OpenAI key in the local `.env` was checked and **never** appeared in history;
it does not need rotating for this incident.

## Status

**Rotated on 2026-10-23** with `scripts/rotate_secrets.py`:

- `JWT_SECRET` — new 64-character hex value.
- `POI_INJECTION_SECRET` — new 64-character hex value.
- `POSTGRES_PASSWORD` — new 43-character value.

New values live only in the git-ignored `.env`. Verified with
`git log --all -S <value>` that none of them appear in any commit.

Because `JWT_SECRET` changed, every token signed with the old secret is now
invalid — all sessions are logged out. That is intended.

## Still outstanding (requires credentials this agent does not have)

1. **The PostgreSQL role password has not been changed on a live server.**
   Neither local instance (ports 5432 and 5433) has an `abode` role that accepts
   the old password, so the credential belongs to some other environment — a
   hosted database or a machine that is no longer running. Rotate it where it
   actually lives:

   ```sql
   ALTER ROLE abode WITH PASSWORD '<new value from .env>';
   ```

   Then update the deployment's `DATABASE_URL`. Note that
   `POSTGRES_PASSWORD` in `docker-compose.yml` is only applied when the volume is
   first initialised; an existing volume keeps the old password until
   `ALTER ROLE` runs. `scripts/rotate_db_password.py --ports 5432,5433` does this
   for reachable local instances once the current password works.

2. **Purge the history** (do this *after* step 1):

   ```bash
   # replacements.txt lines look like: <old-value>==>REDACTED
   # Build it from .env.bak; never commit it (gitignore covers *.txt.secret).
   git filter-repo --replace-text replacements.txt
   git push --force --all
   git push --force --tags
   ```

   This document intentionally does **not** repeat the exposed values — doing so
   would recreate the exposure in a new commit.

   GitHub keeps unreferenced objects reachable for a while and forks keep their
   own history; ask GitHub Support to purge cached views if the repository was
   public for long. Anyone with a clone must re-clone.

3. **Check deployment and CI secrets** for the same values (`.env` on any host,
   GitHub Actions secrets, container orchestrator secrets) and replace them.

## Preventative measures now in place

- Secrets are loaded from environment files that are git-ignored; `.gitignore`
  now covers `.env.*` (backups included) while keeping `.env.example` tracked.
- `scripts/secret_scan.py` scans tracked and untracked files for credential
  patterns; `gitleaks` runs in CI (`.github/workflows/ci.yml`).
- `scripts/rotate_secrets.py` rotates the local secrets atomically, writes a
  git-ignored backup and keeps `DATABASE_URL` consistent.
- `JWT_SECRET` has no literal fallback: production refuses to boot without a
  ≥32-character value; development generates an ephemeral secret.
- `JWT_SECRET` now has a single source of truth (repo-root `.env`); the gateway's
  `api/.env` no longer overrides it.
- `CORS_ORIGIN="*"` is rejected in production and warns in development.
- POI ingest fails closed in production when no API key is configured and uses
  a constant-time comparison.
- Photo uploads re-encode to strip EXIF/GPS, so agent photos cannot leak
  location metadata.
- Placeholder API keys (`sk-proj-XXX…`) are ignored rather than used.
