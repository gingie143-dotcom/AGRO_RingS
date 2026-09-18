# AI Caller development rules

- Source of requirements: docs/requirements-original.md. Current implementation truth: docs/status.md.
- Do not claim all 15 stages passed. Mark tested/implemented/unverified/missing separately.
- Never replace real SIP/AI acceptance with a mock success. Simulation must remain visibly labeled.
- Keep real campaigns disabled until the single-call gate and failure tests pass.
- Never commit .env, credentials, phone lists, transcripts, audio recordings or database dumps.
- Backend does not process audio. Gateway does not own CRM persistence.
- Use migrations for schema changes. Test an existing migration before adding another.
- Test command: pytest -q. Lint: ruff check backend voice-gateway tests. Frontend: npm ci and npm run build.
- SQLite tests do not validate PostgreSQL locking. Docker, real provider and Windows results must come from actual runs.
- For API implementation use current official documentation. Source links are in docs/sip.md.
- Preserve user data; restore to a new database first. Never use compose down -v for upgrades.
- Publish only to the user's intended repository, with no force push.
