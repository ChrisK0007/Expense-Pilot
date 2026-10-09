# Release history

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
