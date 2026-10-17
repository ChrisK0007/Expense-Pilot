# Changelog

Stable Docker release history starts at **v1.0**, listed in release order. The current stable image is **v1.0.3**. The iPhone app is versioned separately and remains in testing.

Detailed beta changes are retained in the [beta development history](beta-changelog.md). Earlier internal development notes are archived separately and are not part of this stable release history.

## v1.0 — Initial stable release

Published version and image tag: `1.0.0`.

- Establish the stable Docker channel on `main` with `latest` and numbered images, plus a separate `beta` channel for testing.
- Track Employment, Business and Personal expenses, split allocations, receipt originals and reviewed receipt drafts.
- Manage clients, quotes, invoices, payments, recurring drafts, saved services, email templates and automatic reminders.
- Organise overnight trips and meals, import bank CSVs and export records for review.
- Provide owner and tax-agent access, authenticator 2FA, account recovery and host backup tools.
- Gate published images with server and browser checks; preserve the existing data directory and database format.
- Maintain the optional iPhone companion in its own repository with independent versions.

## v1.0.1

- Promote all changes tested through v1.0.1-beta.4 to the stable channel. Publish `1.0.1` and update `latest`.
- Add PocketSmith bank feeds with encrypted credentials, manual/hourly sync, transaction review, expense matching and duplicate protection, including the nullable transfer flag fix.
- Keep shared navigation across Invoices, Quotes, Clients, Recurring invoices and Line item templates; provide Email settings and clearer automatic reminder controls, including a switch on each invoice.
- Permanently remove accepted expenses and their attached receipts together so deleted records cannot return to the draft inbox.
- Upgrade existing v1.0.0 databases with migration m008 while preserving existing records and settings. PocketSmith stays disconnected until configured. Back up the existing `/data` directory before upgrading; returning to v1.0.0 requires its matching backup.

## v1.0.2 — Stable Docker release (2026-10-17)

Promotes the tested 1.0.2-beta.1–beta.13 server changes to stable. The iPhone app remains independently versioned and in testing.

- Editable saved services and invoice numbers, reuse of permanently deleted invoice numbers, per-invoice reminder wording and email copies.
- Monthly, quarterly and yearly budgets; vehicle logbook and cents-per-kilometre comparison; separate overnight spending.
- Browser page URLs, clearer settings, consistent allocation labels and colours.
- Optional setup token, in-app AI modes, workspace timezone, full backups, restore and account privacy controls.
- Saved-address sync, drive timing/route support, longer-lived mobile sessions and server notification polling support.
- Docker-first documentation, support forms and installation defaults now target stable.

Back up the complete data directory before upgrading from 1.0.1. Startup applies migrations m009–m019. Keep the existing `/data` mount; legacy AI environment settings remain supported. Rollback requires the matching old backup and image. No iOS build is released by this update.

## v1.0.3 — Website sign-in persistence (2026-10-18)

- Replace the website’s fixed 12-hour sign-in expiry with a rolling 30-day inactivity period, matching the iPhone session policy. Authenticated activity renews both the server deadline and browser cookie.
- Preserve immediate sign-out, password/2FA revocation, account disabling, tax-agent permissions and the five-minute 2FA challenge. Expired or revoked sessions cannot be renewed.
- Include the AGPL licence and copyright notice in the container and label the image licence.

No database migration is added. If your old website session has already expired, sign in once after updating. Private browsing, cleared cookies and external sign-in gateways can still end a browser session.
