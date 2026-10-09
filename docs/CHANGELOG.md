# Release history

## 1.0.0

- Establish the stable release channel on `main`, publishing `latest` and `1.0.0`, with ongoing development on `beta` and separate prerelease image tags.
- Gate both channels with the same backend and browser checks. Reject versions assigned to the wrong channel and prevent beta, pull-request and topic-branch builds from replacing `latest`.
- Move the iPhone app 0.1.1, Xcode project, icon, tests and simulator workflow into [expense-pilot-ios](https://github.com/ChrisK0007/expense-pilot-ios). Preserve its bundle identifier and independent app version; earlier history remains in this repository.
- Carry forward all v0.8.6 features with the same server paths and data format.

## 0.8.6

- Add the supplied invoice, quote, due/overdue/manual reminder, partial/full payment receipt and statement email defaults. Provide separate template tabs, insertable fields, sample previews and a formatted signature with links and embedded images. Preserve custom wording and offer a reset to the reference defaults.
- Add payment receipt PDFs and emails, client statements with opening/running balances or outstanding invoices, and statement PDF/email delivery history.
- Add owner-controlled automatic reminders with before-due, due-date and overdue dates, per-invoice pause controls, and durable duplicate protection. Automatic sending is off by default; failed or uncertain deliveries require review instead of automatic retries.
- Add Delete invoice alongside Void, including issued, paid and voided invoices, with a permanent-deletion confirmation. Remove associated payment and document history, update income totals, release linked time entries and restore the original quote to Accepted. Keep recurring schedules and invoice numbering intact, and block deletion while email delivery is pending or uncertain.

## 0.8.5

- Combine receipt city/suburb and address/state inputs into one Location field. Use detected suburb, state and postcode where available, preserve the full extracted address, and let reviewed locations override AI evidence when matching trips.
- Move Tax agent access from the side menu into Settings, retaining owner-only invitation and permission controls.

## 0.8.4

- Remove the redundant Workspace selector from adding and editing expenses and meals; employment and business percentages determine the allocation.
- Remove Trip workspace from receipt trip review. The proposed trip inherits the receipt allocation, and each meal percentage is labelled Employment or Business.

## 0.8.3

- Keep Receipt inbox for unfiled drafts only. Accepted receipts are available through Expenses, including trip meals.
- Remove the redundant receipt Workspace selector; the entered allocation percentages determine the expense workspace.
- Open possible matching expenses in a separate detail view, preserving unsaved receipt edits. Already-attached receipts show a status instead of a disabled button with a waiting cursor.
- Remove the tax-agent-assessment footer from Expenses.
- Review and create a new overnight trip directly from a meal receipt. Saving a meal without a selected trip now opens trip review instead of a dead-end error.
- Carry edited receipt values into the review and group matching consecutive-day meal receipts. Reuse matching trips in the same person's workspace and date range.
- Permit explicit trip review when a home base is missing or a suburb is ambiguous, while leaving automatic away-from-home suggestions evidence-based. The trip and expenses are created only after the user accepts the overnight dates, location, purpose and meal details.
- Show the receipt address/state for correction and use location evidence to distinguish identically named suburbs.

## 0.8.2

- Organise the backend under `server/`, test suites under `tests/server/` and `tests/browser/`, deployment templates under `deploy/`, and documentation under `docs/`.
- Extract receipt, finance and billing-document routes into focused modules.
- Introduce numbered transactional database migrations and an applied-migration ledger.
- Read the server/API and Docker release version from `server/VERSION`.
- Exclude iOS, documentation and test files from Docker build context; skip Docker builds for iOS-only and documentation-only changes.
- Back up the actual configured container data mount and preserve whether the container was running.
- Preserve container paths, database name, host appdata mounts and root deployment commands. Keep iOS in the same repository.

## 0.8.1

- Retire employee account access while retaining historical financial records.
- Add server-side session revocation and strengthen login rate limits.
- Bound PDF inspection resources and restrict receipt image types and size.
- Update dependencies and verify dependency, backend and browser checks.

## iOS 0.1.0

- Initial SwiftUI app with a server-connected web workspace and native receipt scanning.
- Support installation through Xcode using a free Personal Team.

See [earlier release notes](legacy-release-notes.md) for the original 0.3–0.6 feature history.
