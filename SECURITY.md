# Security policy

## Report a vulnerability privately

If GitHub shows **Security → Advisories → Report a vulnerability** for this repository, use that private reporting form. Include the affected version, a minimal reproduction using synthetic data and the likely impact. Never attach live secrets or someone else's financial records.

If the button is unavailable, open an issue titled **Request a private security contact** containing only a request for a private channel. Do not include vulnerability details in that public issue. No separate security email address has been published yet.

## Supported versions

Security fixes target the current stable release. Beta builds are for testing and receive fixes through beta development; older numbered images are not promised separate backports. See [release channels](docs/releases.md) for current versions. Report a security issue even if you cannot safely upgrade immediately.

## Operating your server

- Complete first-owner setup on a trusted network. Current stable and beta releases allow token-free setup when `SETUP_TOKEN` is blank/unset. If a token is configured, it is enforced. Create the owner account before exposing a new installation remotely.
- Use HTTPS with `COOKIE_SECURE=true`, or a trusted VPN, for remote access. Do not expose the HTTP port directly to the internet.
- Keep `/data`, its `session.key`, deployment settings and backups private. Receipt originals and the database are not encrypted at rest by the application; stored integration credentials require both the database and key for recovery.
- Treat the owner and Docker host administrator as trusted. Tax agents can read the workspace's financial records, including personal records and unfiled receipts; read/write access is an additional permission, not per-record sharing.
- Review optional AI, SMTP and PocketSmith destinations and permissions. Self-hosting does not prevent data being sent to an integration you enable.
- Keep Docker, the host and the selected Expense Pilot release current. Retain a tested backup before upgrading.

Automated dependency, integration and browser checks are useful evidence, not a claim of an independent security audit. The [release checklist](docs/releases.md#release-checklist) describes the checks for each release.
