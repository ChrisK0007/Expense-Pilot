## Public-release preparation

The next beta adds selectable receipt AI, email copies, portable Docker setup and data lifecycle controls. See [installation, AI modes, backup and restore](docs/public-release.md).

# Expense Pilot

*a clearer view of every dollar*

Self-hosted expense tracking for sole traders and people tracking employment expenses, with receipt capture, split deductions, invoicing and optional tax-agent access.

## Install and update

- [Installation, Unraid, HTTPS, backups and account recovery](docs/guide.md)
- [iPhone app and free Xcode installation](https://github.com/ChrisK0007/expense-pilot-ios)
- [PocketSmith bank feeds](docs/pocketsmith.md)
- [Stable and beta release channels](docs/releases.md)
- [Development and repository structure](docs/architecture.md)
- [Release history](docs/CHANGELOG.md)

Stable Docker image: `ghcr.io/chrisk0007/expense-pilot:latest` (or pin `:1.0.1`). Beta development image: `ghcr.io/chrisk0007/expense-pilot:beta`.

`main` is the stable release branch; `beta` is for ongoing development. Beta builds publish only the beta channel and their numbered prerelease tag. Run beta in a separate container with its own data directory; see the release-channel guide.

Existing Unraid installations can update the image normally. Container paths remain `/app` and `/data`; the database remains `/data/rounded.sqlite`. Keep your current appdata mount and environment settings.

For a new source installation, run these commands from the repository root:

```sh
bash prepare.sh
docker compose up -d --build
```

Read the installation guide before exposing the application outside your local network.

## Repository layout

| Path | Purpose |
| --- | --- |
| `server/` | Python backend, browser assets, suburb data and database migrations |
| `tests/server/` | Backend integration and migration tests |
| `tests/browser/` | Browser workflows and disposable test server |
| `tests/release/` | Stable/beta publishing checks |
| `deploy/unraid/` | Unraid container template |
| `scripts/` | Preparation and backup utilities |
| `docs/` | Installation guide, architecture and release history |

The root Dockerfile and Compose files stay as stable deployment entry points. Root `prepare.sh` and `backup.sh` forward to `scripts/` so existing commands continue to work. The iPhone app has its own source, version and build workflow in [expense-pilot-ios](https://github.com/ChrisK0007/expense-pilot-ios).

## Vehicle odometer log (1.0.2-beta.2)

Open **Tracking → Vehicles → Odometer log** to add an actual dashboard reading with its date/time. The estimated odometer adds the full distance of later uploaded journeys, including personal driving; allocation percentages do not reduce vehicle mileage. Editing/deleting journeys recalculates the estimate. Add another actual reading to reconcile GPS differences or unrecorded driving without overwriting previous readings. Actual readings can be edited or deleted, with protection against stale concurrent edits.

The iPhone app 0.4.0 adds address search, driving-route choices, optional via locations, manual trips, GPS route extensions/gap corrections and a native odometer screen. It includes local pending mileage in its estimate and deduplicates journeys already uploaded. Maps and route geometry stay on the iPhone. Address search/routing use Apple Maps and need internet access; the web journey form continues to accept entered kilometres or odometer readings.

Trips without a time on the baseline day, or trips spanning the reading time, are flagged and excluded rather than guessed. Add the reading after stopping the trip, or add a later reading to establish a clear baseline. The web estimate only includes server journeys. New iPhone uploads include timestamps and an idempotency reference; identical repeated uploads resolve to the original journey. Existing server/API clients remain compatible.

Update the **beta** container to `ghcr.io/chrisk0007/expense-pilot:beta` after backing up its appdata. The migration adds odometer history and journey metadata; the stable container is unchanged.

## Category budgets and vehicle comparison (1.0.2-beta.3)

Budgets are per category and allocation. Actuals include recorded expenses/refunds and exclude reimbursements. Split amounts use the same cent rounding as expense reports. Overlapping allocations and durations are not added into a combined total.

Under **Vehicles → Compare vehicle methods**, select a financial year. The cents/km estimate uses eligible recorded employment/business kilometres together, capped at 5,000 km per car. Rates are 78c (2022–23), 85c (2023–24), 88c (2024–25 and 2025–26), and 91c (2026–27). Future years are not assumed. The logbook estimate uses linked running costs, entered annual depreciation and representative logbook percentages. Cost settings exclude reimbursements, parking/tolls and purchase price, and allow GST credits and other exclusions. Receipts stay attached to their expenses and remain viewable/downloadable.

This is a comparison only: it does not choose a method or post another deduction to the tax forecast. Ordinary expense allocations remain as entered. Do not add cents/km to fuel and other costs already covered by that rate. Enter depreciation as annual decline in value, not purchase price; percentages need supporting logbook and odometer records.

Sources checked 12 October 2026: [2026 rate determination](https://www.legislation.gov.au/F2026L00785/asmade/text), [ATO car record requirements](https://www.ato.gov.au/api/public/content/bc562d4d-fcaf-4e15-b595-cca75e30f8bc_Taxtimetoolkit_Keepingrecordsforworkrelatedexpenses_pdf), [2024/2025 rate](https://softwaredevelopers.ato.gov.au/cents-kilometre-deduction-rate-car-expenses-2024-determination).

Personal journeys no longer require a purpose. Employment and business journeys still do. Distances display to one decimal place; stored metres are unchanged. iPhone 0.5.0 uses native screens for sign-in, expenses, receipt review, budgets and vehicle comparisons.

## Page URLs and budget durations (1.0.2-beta.4)

Each web page now has a URL, such as `/#/expenses`, `/#/invoices` or `/#/budgets`. Refresh keeps the selected page; browser Back/Forward and bookmarks work, including links opened before sign-in. Tax agent access has `/#/settings/tax-agent-access`. Unknown or hidden pages return to Dashboard, and permissions still apply. Hash routes need no reverse-proxy changes.

In **Budgets**, choose **Monthly**, **Quarterly** or **Yearly** and a **Starting month**. The amount applies to the whole 1, 3 or 12 month period. The page and budget editor show the exact date range. A yearly budget starting July covers 1 July through 30 June; a quarter can start in any month. Spending is totalled over that full range, including leap days. Edit a budget to change its duration, or use **Copy previous month/quarter/year** to carry budgets forward without replacing existing ones. Budgets do not renew automatically.

Migration m012 preserves existing budget IDs, amounts and versions as monthly budgets. The API adds `period=monthly|quarterly|yearly` to budget listing, creation, editing and copying; `month` remains the starting month. Requests omitting the period still list/create/copy monthly budgets, and edits omitting it retain the existing duration. Native iPhone 0.5.0 remains compatible and continues showing monthly budgets; the new duration selector is in the web app.

### Beta 1.0.2-beta.5 — native app and overnight ledger

Meals and linked overnight-trip expenses now appear in Overnight spending, separately from ordinary Expenses and their dashboard/report totals. Their receipts remain attached and accessible. The tax forecast excludes those records and exposes separate overnight allocation totals; it does not turn ATO reasonable amounts into deductions. Reports provides separate ordinary and overnight CSV exports (`ledger=ordinary` / `ledger=overnight`; the existing API default still exports all records).

Each overnight trip has a Spending & allowances comparison: actual spending, reimbursements, actual employer allowance received, salary/destination-based domestic reasonable amounts for 2025–26 and 2026–27, and explicit meal/day selections for partial travel days. Salary excludes allowances (full-time equivalent for part-time employees). Unselected, unclassified and reimbursed meals are not assumed claimable. The determination changes at 1 July, including salary bands. Unsupported years and overseas destinations require custom verified AUD amounts with a recorded source. Split trips when destination class changes. Accommodation is recorded but not part of the meal/incidental benchmark.

ATO reasonable amounts concern substantiation; they are neither an automatic claim nor a cap on expenses supported by evidence. Actual expenses must be eligible, incurred and unreimbursed. Employer allowance and income reporting conditions must be considered separately. Retain evidence and use the overnight export for assessment; these comparisons are not automatically added to tax estimates.

Rate references: ATO TD 2025/4 and TD 2026/4, domestic tables 1–3. The 2026–27 values were cross-checked against the published transcriptions at https://austax.tools/ato-travel-allowance-rates-2026-27-australia/ and https://pay-calculator-australia.com/travel-allowance/ because the ATO PDF returned HTTP 403 during development. Original determinations are linked in the interface; confirm the destination classification against table 4.

The native app's invoice creation uses user-scoped request keys. A retry returns the same invoice, changed payloads are rejected, and a deleted invoice cannot be recreated by a delayed retry. Draft creation does not send mail. Existing web clients keep their existing request behaviour.

## iPhone notifications (beta 1.0.2-beta.11)

The native app has opt-in driving, review and upload-failure alerts. This server adds
authenticated receipt, invoice, budget and bank-feed alert events. Without a push
relay these update when the app connects. Optional remote delivery uses a separate
[APNs relay](deploy/push-relay/README.md); Apple credentials never ship in this image.
Quiet hours, per-category switches and private previews are configured on each phone.

## Persistent iPhone sign-in (beta 1.0.2-beta.12)

With iPhone 0.8.5 (15), device logins renew on authenticated activity and expire after
30 days without use. Existing valid app sessions upgrade automatically. Browsers
retain a fixed 12-hour login. MFA still completes before a device login is issued.
Manage/revoke remembered devices in Settings → security or in the iPhone's Account
& privacy settings. Revocation and sign-out remove the push registration; password,
2FA and account access changes invalidate the login. Push workers never renew it.
