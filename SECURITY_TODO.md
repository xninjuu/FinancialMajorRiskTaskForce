# Security Hardening Backlog

1) **Code Security**
- Centralize input validation and sanitizing (done in `app/core/validation.py`; extend to new forms).
- Refine error handling to avoid stack traces in UI; keep technical details in logs.
- Move all secrets to `.env`/OS store; no hard-coded credentials.
- Route all UI inputs (filters, searches, case IDs) über `app/core/validation.py` whitelists.

2) **Auth & Session**
- Enforce password policy (min length 12), failure counters, and timed lockout (implemented); extend to password rotation.
- Inactivity lock with re-authentication (implemented); add configurable thresholds per role.

3) **Database**
- Decide on SQLCipher vs. field-level encryption for PII; wire optional AES-GCM helpers.
- Harden DB path with NTFS permissions guidance and encrypted backups.

4) **Privacy & Legal**
- Map data flows to DSGVO Art. 5/25 and GwG/BaFin/FATF guidance (see `docs/legal_context.md`).
- Add retention/archival controls for cases and audit logs.
- Publish and maintain `docs/threat_model_de.md` to keep the threat model current.
- Document backup/restore steps (see `docs/backup_strategy_de.md`) and verify monthly restores.

5) **Explainability & Audit**
- Keep score breakdowns in alert/case detail views.
- Expand audit action enums and filtering UI.

6) **Deployment/Hardening**
- Evaluate code-signing and publish SHA-256 hashes per release.
- Provide an operations guide for locked-down Windows desktops.
