# Security notice — credential exposure

## What happened

Earlier revisions of this repository contained real credentials in documentation
files that were committed and pushed to a public GitHub repository:

| Credential | Location (pre-cleanup) | Was in git history |
|---|---|---|
| PostgreSQL password | `docs/REBUILD_DATABASE.md`, `docs/STATUS_REPORT.md` | yes |
| `JWT_SECRET` | `FINAL_VERIFICATION_REPORT.md` | yes |
| POI ingest key (`POI_INJECTION_SECRET`) | `FINAL_VERIFICATION_REPORT.md` | yes |

The OpenAI key in the local `.env` was checked and **never** appeared in history;
it does not need rotating for this incident.

Rotation is the remediation — a password that has been public is compromised even
after the history is purged, because clones, forks and caches of it exist.

## What was done (2026-10-23)

**1. Rotated** with `scripts/rotate_secrets.py`:

- `JWT_SECRET` — new 64-character hex value.
- `POI_INJECTION_SECRET` — new 64-character hex value.
- `POSTGRES_PASSWORD` — new 43-character value.

New values live only in the git-ignored `.env`. Verified with
`git log --all -S <value>` that none of them appear in any commit. Because
`JWT_SECRET` changed, every token signed with the old secret is invalid — all
sessions are logged out. That is intended.

**2. Rewrote history** with `git filter-repo --replace-text`, then force-pushed:

- All 12 commits have new SHAs. `main` is `600d904`.
- The old values were replaced with `REDACTED-POSTGRES-PASSWORD`,
  `REDACTED-JWT-SECRET` and `REDACTED-POI-SECRET`.
- Verified afterwards: `git log --all -S <old value>` returns nothing and the
  tracked tree contains no match, for all three credentials.
- The tree itself is unchanged — `HEAD^{tree}` before and after the rewrite is
  identical (`d2e33a5`), so the code that passed the test suite is byte-for-byte
  the code that was pushed.
- A pre-rewrite bundle is kept outside the repository at
  `../kimi-abode-prefilter-20261023.bundle`. **It contains the old secrets** —
  delete it once you are satisfied with the rewrite.

**3. Residual exposure on GitHub.** After the force-push, GitHub still served the
old commit and its raw files by SHA (`HTTP 200` on the old commit and on
`raw.githubusercontent.com/.../e439470/docs/REBUILD_DATABASE.md`). Unreachable
objects linger until GitHub garbage-collects them. Rotation is what makes this
harmless; if you want the bytes gone sooner, open a GitHub Support request to
purge the unreachable commits for the repository. Forks were zero at the time of
the rewrite, which limits further copies.

## Still outstanding (requires credentials this agent does not have)

1. **The PostgreSQL role password has not been changed on a live server.**
   Neither local instance (ports 5432 and 5433) has an `abode` role that accepts
   the old password, so the credential belongs to some other environment — a
   hosted database, or a machine that is no longer running. Rotate it where it
   actually lives:

   ```sql
   ALTER ROLE abode WITH PASSWORD '<new value from .env>';
   ```

   Then update the deployment's `DATABASE_URL`. Note that `POSTGRES_PASSWORD` in
   `docker-compose.yml` is only applied when the volume is first initialised; an
   existing volume keeps the old password until `ALTER ROLE` runs.
   `scripts/rotate_db_password.py --ports 5432,5433` does this for reachable
   local instances once the current password works. Once the database is
   rotated, delete `.env.bak` (it holds the old value).

2. **Check deployment and CI secrets** for the same values — `.env` on any host,
   GitHub Actions secrets, container orchestrator secrets — and replace them.

## Preventative measures now in place

- Secrets are loaded from environment files that are git-ignored; `.gitignore`
  covers `.env.*` (backups included) while keeping `.env.example` tracked.
- `scripts/secret_scan.py` scans tracked and untracked files for credential
  patterns; `gitleaks` runs in CI with full history (`.github/workflows/ci.yml`).
- `scripts/rotate_secrets.py` rotates the local secrets atomically, writes a
  git-ignored backup and keeps `DATABASE_URL` consistent.
- `JWT_SECRET` has no literal fallback: production refuses to boot without a
  ≥32-character value; development generates an ephemeral secret.
- `JWT_SECRET` has a single source of truth (repo-root `.env`); the gateway's
  `api/.env` no longer overrides it.
- `CORS_ORIGIN="*"` is rejected in production and warns in development.
- POI ingest fails closed in production when no API key is configured and uses a
  constant-time comparison.
- Photo uploads re-encode to strip EXIF/GPS, so agent photos cannot leak
  location metadata.
- Placeholder API keys (`sk-proj-XXX…`) are ignored rather than used.
