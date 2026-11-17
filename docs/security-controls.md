# Security controls and deployment requirements

This describes 1.0.7-beta.12. These controls reduce risk; they do not guarantee that software or a deployment is vulnerability-free.

## Accounts and mailbox proof

Settings → Security → Verify email address sends an eight-digit code after current-password verification and, when enabled, a second factor. The code expires after 15 minutes, allows at most five guesses and can be used once. Each new request invalidates the previous code; each account may request at most three messages per hour. Codes are stored as a keyed digest bound to the account, email and account version, never returned by the API or saved in browser storage.

A verified status means the code sent to that exact email was presented by its authenticated account. SMTP configuration alone is not verification. Existing addresses start unverified; changing an address invalidates its displayed proof. This is an additive self-service control: existing owner setup, logins, mobile sessions and terminal account recovery are not locked behind SMTP. A deployment that needs mandatory mailbox verification for every account needs a separate enrollment policy.

Tax-agent invitations already deliver a temporary password by email and require replacement before workspace access. Email verification does not grant roles, access to other accounts, or additional shared years. Passwords use Werkzeug's password-hash API; existing hashes remain readable. Password inputs are no longer silently truncated.

## Request and permission boundaries

The service uses SQLite. It does not have PostgreSQL-style row-level security. The application's owner checks, active/version/session checks, and tax-agent shared-year/document filters enforce its single-owner workspace model. Query values are bound with SQL placeholders; dynamic identifiers and clause selections must remain server-controlled.

CORS is deny-by-default: the API does not grant Access-Control-Allow-Origin. Browser API mutations carrying Sec-Fetch-Site: cross-site are rejected in addition to mandatory CSRF validation. This metadata is not full Origin validation or authentication. Native clients may omit the header. Mutating JSON requests require an object; multipart uploads remain supported.

Durable SQLite quotas apply to all API methods except OPTIONS, across processes: 1,200 requests per authenticated account per minute and 240 per anonymous source address per minute. API_USER_LIMIT and API_ANONYMOUS_LIMIT set positive limits at startup. A limit response is HTTP 429 with Retry-After; it does not revoke the session. Existing password-account/source and factor limits remain independently enforced. Configure TRUSTED_PROXIES only for real proxy addresses; arbitrary forwarded headers must not choose the source quota.

These application quotas do not replace edge connection limits, body/time limits or DDoS protection. Static pages and public quote routes have separate boundaries; review their exposure at the proxy.

## Data, uploads, browser rendering and logs

- Provider API credentials stay server-side. Bank-feed and SMTP stored secrets use server-side encryption rooted in the installation key. Protect session.key, environment configuration and backups together.
- Browser authentication remains in HttpOnly cookies, with server-side revocation/expiry. Browser localStorage is used for theme preference, not authentication. The iOS application is outside this release; its persistent embedded-browser cookie store remains a native follow-up.
- Receipt images are decoded, checked and re-encoded; file extension and MIME labels are not trusted as proof. PDFs are inspected in bounded workers. The 12 MB request limit, image pixel limit, receipt ownership checks and upload retry acknowledgements remain.
- CSP restricts scripts and connections to the same origin, with nosniff and frame denial. User-controlled HTML must still be escaped; CSP is not a substitute for output encoding. PDF rendering also escapes user content.
- Python logging masks quote bearer URLs, labelled credentials, authorization/cookie header lines and email addresses in messages, exceptions and stacks. It cannot guarantee removal of arbitrary unlabelled data, all encodings, structured logging extras or proxy/provider logs. Never log request bodies or secrets; configure proxy redaction and retention separately.
- Git, Docker context and downloadable-source exclusions cover environment files, mobile signing credentials and private data/export directories. Ignore rules do not remove a secret already tracked in history. No discovered leak or credential rotation is implied by these exclusions.

No inbound third-party webhook endpoint was identified in this release's server/relay review. The optional push relay authenticates callers with per-container bearer credentials; that is not webhook signature verification. A future webhook integration must verify its provider's signature, timestamp and replay rules before processing.

## Deployment and validation

Production uses Gunicorn and the application sets DEBUG=False. Serve public installations over HTTPS with COOKIE_SECURE=true. Keep setup tokens private, maintain backups and restrict network access to the database/data directory. Do not expose Flask's development debugger or treat a localhost/LAN configuration as a hardened public deployment.

Migration m038 adds request quota and mailbox-proof tables. It leaves account records, session cookies, existing session rows and stored password hashes intact and does not mark existing emails verified. Back up before upgrading; rollback requires the matching pre-upgrade backup and image.

CI audits both the server and optional push-relay dependency sets, builds the actual container, runs server/migration/upload/permission and browser regressions, and checks production startup before publishing. Beta.12 adds Chromium/WebKit coverage with US/Australian locales, workspace-zone date entry, invalid/leap dates, retained calendars and DST split-time resolution. Required test results and the exact image digest belong in the release PR/publishing run; no dependency or browser checks should be claimed from syntax validation alone.
