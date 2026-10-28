# Beta changelog

Prerelease changes, newest first. Entries describe the version at the time; use the [stable changelog](CHANGELOG.md) and [release channels](releases.md) for current stable information.

## 1.0.6-beta.10 — Payslip columns and branded reports (2026-10-28)

- Read the supported Pay Slip Components layout locally, including wrapped employer names, payment/period dates and separate current-pay/YTD columns. Reconcile gross earnings, PAYG, net and super totals; subtract explicitly listed salary-sacrifice super from taxable pay. Unrecognised or inconsistent layouts retain the existing AI/manual review path.
- Stop mistaking the payroll SG (super guarantee) row for a Singapore-dollar marker. Real SGD and SG$ currency markers remain supported.
- Let successful rereads fill previously blank employment draft fields while retaining manual corrections, zero values and notes. Show the salary-sacrifice calculation during review. Extraction still never files income automatically.
- Add the Expense Pilot logo to every WFH and mileage PDF page, with the app’s purple headings/table headers and neutral text, rules and alternating rows. Keep report calculations, evidence and pagination unchanged.
- No database migration or iPhone build. Tests use synthetic payroll fixtures; private source documents are not distributed.

## 1.0.6-beta.9 — Faster payslip extraction with Ollama (2026-10-28)

- Read complete, explicitly labelled current-pay text payslips locally even when AI is enabled. Keep YTD and ambiguous amounts out of current-pay fields. All extracted figures still require review before saving income.
- Retain partial local fields with a visible review warning if AI is unavailable; keep manual drafts and original documents. Scanned or unsupported documents still report a clear failure when no local fields are available.
- Use a shorter employment-document prompt, disable Ollama thinking and cap generated output at 2,048 tokens. Reject truncated responses. Allow Ollama reads up to five minutes; cloud-provider and connection-test limits remain unchanged.
- No database migration, provider switch or iPhone build.

## 1.0.6-beta.8 — Reliable payslip reading behind a proxy (2026-10-27)

- Read uploaded documents in bounded background jobs and poll progress with short requests, so slow AI reads do not hold a browser request open across the proxy timeout. Apply this to capture, individual retries, bulk reprocessing and employment-document review.
- Reuse an active read for repeated clicks; preserve original documents and manual drafts after failures. Interrupted reads can be retried from Document inbox, including after a container restart. The standard single-worker deployment handles at most two reads at once.
- Replace raw JSON parsing errors from HTML gateway pages with useful messages and HTTP status. Retry temporary progress-check failures without repeating the upload or AI request. Report AI timeouts explicitly and recover the review button after a failed read.
- Recheck permissions and filed/deleted documents before saving extracted suggestions. Extraction still never writes employment income or expense records. No database migration or AI-provider change.

## 1.0.6-beta.7 — Document inbox, payslips and bank matching (2026-10-27)

- Make notes optional for manual WFH sessions and reviewed imports. Existing notes, original reports and history are retained.
- Rename Receipt inbox to **Document inbox**. Add payslip and annual income-statement review, with automatic gross/PAYG extraction using the configured AI provider. Explicitly labelled text payslips can be read locally without AI. Keep uncertain fields blank and YTD figures separate; require review before saving income.
- Link each employment original to its income record, prevent simultaneous expense/income filing, check duplicate and overlapping pay, and block annual statements that would overlap the same employer’s recorded pay. Deleting income returns its original to the inbox. Keep originals in full backups.
- File covered home-office bills directly from the inbox, choosing the cost type and confirming personal payment. New evidence is unallocated, with no extra percentage or separate bill deduction.
- Suggest bank matches from already-synced posted AUD purchases, using exact amounts, recognisable merchants and dates within three days. Link on filing; reuse a matching existing expense where possible. Ambiguity needs review, and explicit Cash / other choices remain excluded from later automatic matching.
- Add **Bank accounts → Match previous expenses**, with a preview, account filter and selected-match confirmation. Match only unique pairs and recheck all selected records under a write lock before applying any changes.
- Add migration m022 for employment document links, pay periods, record versions and explicit cash choices. Earlier migrations remain unchanged. Back up before updating; an older image requires its matching pre-update backup.

## 1.0.6-beta.6 — WFH import and document previews (2026-10-27)

- Import WFH Logbook Australia PDFs and Expense Pilot diary CSVs through a review screen. Choose Employment or Business, complete missing work descriptions, and check dates, breaks and session timezones before saving.
- Reject partial PDF extraction, invalid hours and overlapping sessions. Skip existing or previously removed imports, including retries after a lost response. Selected sessions save together or not at all.
- Preserve the original report in Documents and retain original logged/updated timestamps and source values in import history. Imported sessions link to their source; PDF logbooks distinguish source timestamps from Expense Pilot import timestamps. No monetary totals from a report are imported and claim settings are unchanged.
- View documents inside Expense Pilot: PDF page navigation and zoom, images, plain-text Word/TXT previews and cell-value Excel/CSV previews. Downloads retain original bytes. Password-protected or unsupported previews provide a download fallback.
- Keep each new success notification visible for its full duration when messages arrive close together.
- Process previews locally with bounded resources and authenticated owner/tax-agent access. No document content goes to an external viewer or AI service. No new schema migration.

## 1.0.6-beta.5 — Fixed-rate home office, printable logbooks and documents (2026-10-27)

- Simplify Home office to the fixed-rate method. Remove actual-cost selection, method comparisons and the optional employee standard-deduction comparison. Existing actual-cost settings and records are retained; the claim stays pending until fixed-rate confirmations are reviewed and saved.
- Add bill evidence directly without entering use percentages. Save the receipt, expense and classification safely with retry protection; new evidence has no separate allocated deduction. Existing expense allocations remain unchanged, while covered bills are excluded from duplicate forecast deductions. Separate assessed equipment and other costs outside the hourly rate retain their existing checks.
- Download a WFH logbook PDF with the financial-year summary, employment/business hours, monthly totals, session times, breaks, creation/update timestamps, work notes and evidence checklist. Clearly distinguish estimated deductions, pending claims and amounts included in the forecast.
- Download a mileage PDF for a vehicle, date range and workspace, with distance summaries and monthly journey details. Include routes, purposes, saved odometer readings, use percentages and an optional user-entered reimbursement rate. Never invent missing odometer readings or apply reimbursement amounts to the tax forecast.
- Add **Reports → Documents** for tax returns, private health statements and other supporting files, with titles, categories, optional financial years, notes, search, downloads and duplicate detection. Keep these files out of claims, income and receipt AI processing. Apply owner/tax-agent permissions and retain originals in manual and automatic backups.
- Keep vehicle actions disabled while records load, so an early click cannot be lost before the form is ready.
- Add migration m021 for document metadata without changing the twenty released migrations. Preserve CSV exports, allowances and audit history. No iPhone build. Take a full backup before updating; rollback needs its matching backup because older images do not recognise m021.

## 1.0.6-beta.4 — Clearer home office and verified automatic backups (2026-10-27)

- Replace the long Home office dashboard with a compact claim/hour summary and separate Hours, Bills & receipts, Claim and Allowances views. Remember the selected view on reload. Keep method comparisons and optional tax guidance expandable; only show the checks for the selected method in claim settings. Preserve calculations, records, permissions and existing migrations.
- Add nightly automatic backups at 02:30 workspace time, keeping seven (`BACKUP_TIME`, `BACKUP_KEEP`; zero disables). Verify the database snapshot and read every completed ZIP member back against its checksum before rotating older backups. Pin receipt originals before releasing the brief database reservation; compression runs without a write lock. Isolate archives by a local installation ID. Settings → Data & privacy shows the last result and offers **Back up now**.
- Add opt-in `TRUSTED_PROXIES` for per-visitor sign-in limits behind a verified reverse proxy. Default behaviour stays unchanged; trust exact proxy addresses and restrict direct access before enabling.
- Reuse Docker cache metadata carried in the published beta image, without creating an Actions cache or additional build artifacts. Refresh dependency layers on the first build each UTC day and pull the current base; stable builds remain uncached.
- Keep dependency source archives bundled with the application. No FUSE/storage warnings, repository-wide reformat or new database migration in this release.

## 1.0.6-beta.3 — Home office (2026-10-27)

- Add Home office under Tracking, with separate employment and sole-trader hours, breaks, workspace timezone and an edit history. Reject overlapping sessions, stale edits and accidental duplicate retries.
- Compare fixed-rate and actual-cost deductions by financial year. One annual method prevents covered running costs being claimed again through the ordinary expense forecast. Missing confirmations or evidence leave the selected deduction pending.
- Link original expense bills, preserve spending and use percentages, and require an assessed amount for equipment/depreciation and occupancy. Reimbursements are excluded.
- Record employer allowances, with an explicit choice about whether they are already included in gross pay. Annual salary overrides replace the recorded total.
- Export the diary, bills, calculations, allowances and relevant edit history to CSV. Tax agents can view/export; editing follows their existing permissions.
- Show an optional employee standard-deduction comparison separately from the forecast. This beta does not calculate a final tax return, depreciation schedules or GST/BAS.
- Add migration m020 without altering existing data or the 19 released migrations. Full backups retain home-office records and attachments. SQLite 3.54.1 and database health checks remain included.

See the [Home office guide](home-office.md). Take a full backup before updating. An older image cannot open a database after m020; rollback requires the matching pre-update backup.

## 1.0.6-beta.2 — SQLite reliability (2026-10-27)

- Build and pin SQLite 3.54.1, including the upstream WAL-reset corruption fix. Verify the downloaded source checksums and the library version/source ID actually loaded by Python.
- Preserve existing databases, receipts, credentials and all 19 migrations. This updates the database engine; it does not repair an already-corrupt file or replace user records.
- Check HTTP availability and database structure in the Docker health check. Missing or malformed databases report unhealthy without automatic repair. Checks have a bounded execution time and include active WAL data.
- Retain the matching SQLite source, build command, notices and version in the downloadable dependency bundles.
- Update Pillow to 13.0.0 and pypdf to 6.21.2 to resolve the existing dependency audit findings; receipt, image and invoice workflows remain covered by the release checks.
- Test the upgrade from Debian SQLite, retained records, backup integrity and a deliberately damaged session table. Reduce temporary browser evidence retention to 3 days.

Take a full backup before updating. Keep any recovery snapshot until a fresh backup has been verified and the repaired application's records and receipt attachments have been checked. Stable remains v1.0.5; WFH development is not included in this reliability release.

## 1.0.6-beta.1 — Stable source packaging sync (2026-10-18)

- Bring the v1.0.5 dependency source packaging, publication checks and documentation into beta.
- Keep beta images separate from latest and use a distinct Unraid name, port and data folder.
- No application database migration or iPhone release.

Publication verification: [run 39089596737](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39089596737) passed after correcting the browser test to wait for the invoice view before closing its dialog. Application behavior is unchanged by that test correction.

## 1.0.4-beta.2

- Add source and licence links at login, in the sidebar and in Settings, with version-matched application source downloadable directly from the container.
- Package build scripts, checksums, dependency versions and available third-party licence notices without workspace data or Git history.
- Make installation/help links follow the installed build revision or release channel.
- Refresh the release checklist and document pending GitHub history/image cleanup, repository settings and dependency-source distribution checks. Stable remains 1.0.3.

## 1.0.4-beta.1

- Use the maintainer’s GitHub username in project and container copyright notices.
- Replace the local Ollama test address with a generic private network example. No application behaviour or database schema changes are included.

## 1.0.3-beta.1

- Bring the website session fix from stable v1.0.3 into beta: authenticated activity renews the browser cookie and server session for 30 days of inactivity instead of forcing sign-in after 12 hours.
- Preserve expiry, logout, password/2FA revocation and account permissions; no database migration is added.
- Include the approved AGPL licence/copyright and licence image metadata.

## 1.0.2-beta.13

- Show split expense allocations as separate purple Employment and green Business badges, with capitalised labels, in expense tables and recent expenses.

## 1.0.2-beta.12

- Add revocable persistent iPhone sessions with a rolling 30-day inactivity deadline. Browser sessions retain their existing lifetime.
- Preserve explicit sign-out, password/2FA revocation and account/server isolation.

## 1.0.2-beta.11

- Add per-device notification preferences and server event/review support for the iPhone test app.
- Current iPhone builds read server alerts directly while connected; a shared push relay is not part of the standard self-hosted setup.

## 1.0.2-beta.10

- Sync saved drive addresses between iPhones signed in to the same server account.
- Version each address, retain deletion tombstones and acknowledge repeated changes safely; concurrent edits require an explicit choice.
- Keep address collections private to each login, including tax agents, and preserve them in server backups.

## 1.0.2-beta.9

- Simplify Settings into fixed topic groups with clear email, receipt AI, security and data controls, consistent spacing and mobile navigation.
- Remove Ollama fields from the beta Unraid template; configure AI in the app while retaining existing environment compatibility.
- Make SETUP_TOKEN optional. A configured token remains enforced, and first-owner creation still closes after setup. Hide the token field when not required.
- Remove backups from the workspace setup checklist. Optional downloads remain under Data & privacy.

## 1.0.2-beta.8

- Add an owner-managed workspace timezone in setup and Settings; suggest the browser's timezone on new installs and retain Brisbane on upgrades.
- Apply regional dates and daylight saving to invoices, reminders, recurring drafts, budgets, bank-sync date windows, tax-period progress and vehicle logs.
- Share the timezone with native iOS and retain each recorded trip's timezone for safe offline upload after a setting change.
- Use workspace time for odometer entry and bank-feed timestamps; reject daylight-saving gaps and explicitly resolve repeated clock times.
- Preserve saved calendar dates and UTC timestamps. AUD, Australian financial years and tax rules are unchanged.

## 1.0.2-beta.7

- Add No AI, local Ollama, existing/remote Ollama and cloud API modes with encrypted keys, connection testing and explicit cloud consent. Preserve legacy Ollama configuration.
- Add client-email BCC copies and consistent dashboard invoice status labels.
- Add portable Docker deployment, setup checklist, public server discovery/API compatibility and privacy/account controls.
- Add authenticated full backup download and verified restore into an empty volume.
- Make mobile expense/receipt uploads idempotent with deletion tombstones.

## 1.0.2-beta.6

- Retain reviewed iPhone route maps on the server and acknowledge exact retry-safe uploads before phone cleanup.
- Preserve deletion receipts so delayed retries cannot recreate deleted journeys; alphabetise expense categories.

## 1.0.2-beta.5

- Support native invoice creation and separate overnight spending/allowance comparisons for the iPhone test app.
- Keep overnight spending separate from the ordinary expense forecast.

## 1.0.2-beta.4

- Give web pages bookmarkable URLs; preserve the page through refresh/sign-in and support browser Back/Forward, including shared billing pages and tax agent settings.
- Add monthly, quarterly and yearly category budgets with a selectable starting month, full-period spending totals, date ranges, duration editing and copying of the previous period.
- Preserve existing monthly budgets and API compatibility with iPhone 0.5.0. Add migration, financial-period and desktop/mobile navigation regressions.

## 1.0.2-beta.3

- Add category budgets and comparison estimates for vehicle cents-per-kilometre and logbook methods.
- Retain vehicle cost receipts and representative logbook inputs for review.

## 1.0.2-beta.2

- Add dated vehicle odometer readings and estimates based on recorded journey distances, with account and retry protection.

## 1.0.2-beta.1

- Edit saved service descriptions, prices and GST treatment from Services & prices. Existing invoice and quote line items keep their saved values.
- Reuse the most recently permanently deleted invoice number for the next automatically numbered invoice, then any other available deleted numbers. Voiding keeps the number reserved. Add a custom number when creating an invoice or change a saved invoice number, with duplicate and concurrent-edit protection.
- Customise automatic reminder dates and due-date, overdue and manual reminder email wording per invoice. Preview messages using the invoice's details, inherit shared settings when overrides are off, and carry preferences into duplicates and recurring drafts. The shared automatic sending switch remains the master control.
- Standardise service labels and shared business navigation, including Billable time. Improve settings spacing, dialog layout, mobile buttons, theme colours and keyboard focus.
- Migration m009 preserves existing records and reminder delivery claims when numbers change. Number reuse applies to invoices deleted after this upgrade. Back up beta data before updating; rollback requires its matching pre-upgrade backup. Stable remains v1.0.1.

## 1.0.1-beta.4

- Add Clients to the shared business page navigation and retain that menu on the Clients page. Shorten All invoices and All quotes to Invoices and Quotes.
- Fix PocketSmith sync rejecting null transfer markers as an unsupported transaction status. Treat unset markers consistently, retaining category transfer protection, while preserving explicit transaction flags and pending-transaction checks. Give invalid status and transfer fields separate errors; failed syncs still leave prior imports intact.
- Cover nullable feed data and client navigation in backend and desktop/mobile browser regressions. Beta only; stable remains v1.0.0.

## 1.0.1-beta.3

- Keep the billing navigation on invoices, quotes, recurring invoices and line item templates, with direct routes back to both document lists. Replace the Wording defaults tab with an Email settings menu for templates, signature, SMTP delivery and reminders.
- Add reminder switches when creating or viewing any invoice, including drafts and invoices generated by recurring schedules. Preserve each preference through draft edits and duplication, and let a new recurring schedule choose the preference for its generated invoices. Global sending settings still apply.
- Make automatic reminder settings clearer with separate before-due, due-date and overdue controls, individual follow-up day fields, a live schedule summary, sender details and links to reminder wording and delivery settings.
- Permanently delete an expense’s attached receipt, draft, extraction details, original file and cached previews. Deleted receipts no longer return to the inbox, and in-flight AI or PDF rendering cannot recreate them. Update the deletion confirmation to describe the removal.
- Add backend and browser regression coverage. Beta only; stable remains v1.0.0.

## 1.0.1-beta.2

- Add an owner-configured PocketSmith bank feed with an encrypted developer key, account discovery and mapping, manual sync and optional hourly syncing. Bank authorisation remains in PocketSmith.
- Add a bank transaction review queue with receipt/CSV expense suggestions, explicit matching, new expenses and expense refunds, ignore/restore controls and links to accepted expenses. New expenses default to Personal / To review.
- Preserve source transaction identities across repeated syncs, block pending transactions and transfers from becoming expenses, and flag changed or missing source transactions without overwriting linked expenses. Failed syncs leave the ledger unchanged.
- Add migration m008, bank-feed integration tests and desktop/mobile browser coverage. Beta only; stable remains v1.0.0.

## 1.0.1-beta.1

- Start the beta development channel from the v1.0.0 feature set, with a prerelease version and isolated `beta` Docker tag.
