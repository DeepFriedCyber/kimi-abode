# Archived documents (pre-rebuild)

These files describe an earlier iteration of the codebase — the one that did not
build or run (see `docs/SECURITY-NOTICE.md` and the root `README.md`). They are
kept only for historical context and **must not be treated as documentation of
current behaviour**.

Several of them made claims ("FINAL", "VERIFIED", "PRODUCTION READY") about code
that never passed a test suite. They are archived rather than deleted so the
record of that period stays inspectable.

For current documentation see:

- `README.md` — architecture, quick start, test commands, API surface
- `docs/SECURITY-NOTICE.md` — credential exposure and rotation
- `docs/REBUILD_DATABASE.md` — Postgres setup

Secrets that appeared in these files were redacted in place; the originals
remain in git history until the history is purged, so rotate anything that was
ever exposed.
