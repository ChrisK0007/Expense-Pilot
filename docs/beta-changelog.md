# Beta development history

Historical prerelease notes, newest first. These changes were promoted into stable v1.0.1 and v1.0.2. Statements about the stable version describe the time of each entry. Use the [stable changelog](CHANGELOG.md), [current guide](guide.md) and [release channels](releases.md) for current instructions.

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
