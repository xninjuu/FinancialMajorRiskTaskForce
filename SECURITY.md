# Security Posture

This prototype follows the OWASP Secure Coding Practices as a baseline. Key points:

- **Input validation:** All user-provided fields (login, filters, notes) are validated and sanitized before use or persistence. See `app/core/validation.py`.
- **Error handling:** User-facing UI surfaces generic messages; technical details go to logs/audit.
- **Secure defaults:** Logging and audit trails are always on, debug helpers are off in packaged builds, and password policy is enforced for every account.
- **Secrets:** No plaintext secrets are hard-coded. Use environment variables (e.g., `CODEX_ADMIN_PASSWORD`) or an OS secret store.
- **Authentication & RBAC:** Bcrypt hashing, lockout after repeated failures, inactivity lock, and role checks in UI _and_ code paths.
- **Data at rest:** SQLite is the default; for higher assurance use SQLCipher or field-level encryption and restrict NTFS permissions.
- **Updates:** Only install signed/verified executables from trusted sources; never auto-fetch code at runtime.

See `SECURITY_TODO.md` for the hardening backlog and `docs/legal_context.md` for privacy/regulatory context.
