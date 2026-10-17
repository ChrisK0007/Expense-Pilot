# Installation and operation

This branch documents **beta 1.0.2-beta.13**. For fresh beta installs and current setup/AI/backup controls, start with [beta installation and configuration](public-release.md). Stable 1.0.1 still needs its own main-branch guide and template.

For release changes, see [the changelog](CHANGELOG.md); for help, see [support](../SUPPORT.md).

## Security and supported accounts

Expense Pilot is for sole traders and people tracking employment expenses. Supported logins are the owner and invited tax agents (read-only by default, optional read/write). Employee invitations and sign-in are removed. Existing employee accounts are disabled and hidden from access management; historical financial records and attribution remain available to the owner and tax agent. Legacy role checks elsewhere in this repository support those historical records only.

Browser sessions have server-side revocation on logout and an absolute 12-hour expiry. Supported iPhone device sessions use a rolling 30-day inactivity expiry; explicit sign-out and security changes still revoke them. Pending 2FA sign-ins are also revoked on logout. Password attempts are limited per account and per source address, including concurrent requests. PDF parsing runs in a child process limited to 256 MiB, 8 CPU seconds and a 15-second wall timeout. Images are restricted to JPEG/PNG/WebP and 25 megapixels.

Use HTTPS and set `COOKIE_SECURE=true` for secure-only cookies and HSTS. The existing local HTTP mode remains compatible with LAN setup, but it is unencrypted; the sign-in screen now warns about it. Do not port-forward 8788 directly to the internet. A VPN or HTTPS reverse proxy is required for remote use. Source address limits deliberately ignore untrusted forwarding headers; users behind the same proxy may share its limit.

Back up your appdata before updating the container. Existing expenses, receipts, trips and invoices are preserved. An already installed iPhone app works with this server update; no Xcode reinstall is required for server security fixes.

---

## iPhone companion — testing

The native iPhone app is developed separately and remains in testing. It is optional; the Docker server and browser interface can be installed and used without it. Follow the companion repository's current signing/TestFlight instructions if you already have testing access. A Docker update does not install or update the phone app.

## Expense allocations and feature preferences

- Split one expense between employment and business, with personal use calculated as the remainder. For example, a $100 receipt at 30% employment and 20% business records $30 and $20, with 50% personal. Percentages must be whole numbers and cannot total more than 100%. Reviewed allocations feed each corresponding tax forecast total. Refunds and reimbursements keep the same treatment; rounding reconciles to the combined allocated amount.
- Existing expenses retain their previous allocations. CSV exports append separate employment/business/personal percentages and employment/business AUD allocations. Split records appear in both relevant report filters without duplicating the receipt.
- Receipt inbox sits directly below Dashboard. Business, Tracking, Income and Reports open compact popup menus with keyboard and mobile support.
- Settings → Features saves choices per login, across devices. The Employment expenses only preset hides business tools, vehicles, bank imports and the tax forecast; individual switches can restore them. Records, permissions and tax calculations are preserved. Existing data remains available in expense reports.
- Receipt currency is a compact editable field. AUD is the default unless extraction detects another currency. Edits save with the draft or expense; foreign amounts still require the actual AUD amount paid.
- Replaced the repeated “Private · AUD” labels with “Totals in AUD”. This is a display currency label, not a privacy setting or currency converter.

Update a beta Unraid container using `ghcr.io/chrisk0007/expense-pilot:beta`, keeping its own `/data` mount. Use `:latest` only for the existing stable channel. Refresh the browser after updating.

---

## Invitations, authenticator 2FA and receipt entry

- Typed dates automatically become **DD/MM/YYYY** when you leave the field. Accepted examples: `8/10/2026`, `8-10-26`, `08.10.2026`, `081026`, `08102026` and `2026-10-08`. Two-digit years mean 2000–2099. Impossible dates and missing years are rejected; month/day order is never guessed.
- **Settings → Home base & receipt sorting:** search a suburb, city, area or postcode and select a suggestion. Nearby suburbs are recognised from the bundled Australian location list using an adjustable **50 km default local radius**. A preview shows the number of included suburbs and examples. Keep extra local names only for exceptions. Existing recognised bases such as Sunshine Coast work without re-entering every suburb. Coordinates are approximate suburb or area centres; choose a suburb for a more precise base. Unknown, ambiguous or unrecognised overseas locations stay in the inbox for manual review. Foreign currency alone does not prove a foreign location. All suggested overnight trips still require review and acceptance.
- **Settings → Account invitations:** save the URL people use to access Expense Pilot. Configure **Email delivery & templates** with SMTP. Then **Tax agent access → Invite tax agent** sends an invitation with a generated temporary password, valid for **48 hours**. No manually entered initial password is required. The new person must replace it before accessing records. Failed or uncertain email delivery is shown against the person; **Resend invitation** generates a replacement and invalidates the old password. Existing accounts keep their passwords.
- **Settings → Two-factor authentication:** enter your current password, scan the QR code with a TOTP authenticator (for example Microsoft Authenticator, Google Authenticator or 1Password), then enter its six-digit code. Save the ten recovery codes shown once after setup. Every code works once. Future sign-ins require the password and an authenticator or recovery code. Each account enables 2FA individually, including read-only tax agents; the owner can see 2FA status under Tax agent access.
- QR codes are generated locally. Authenticator secrets are encrypted using the persisted `session.key`; recovery codes are stored only as hashes. Enabling/disabling 2FA and changing passwords revoke other sessions. Reused authenticator codes are rejected and failed attempts are limited. Keep the server clock accurate and retain `session.key` in backups.
- Lost phone: use an unused recovery code to sign in. To replace your authenticator, disable 2FA with your password and a fresh recovery/authenticator code, then set it up again. If all recovery methods are lost, use the existing terminal recovery command (`python reset_password.py` inside the container); it now offers an explicit 2FA reset. It also clears a pending temporary-password requirement. Disabled accounts stay disabled.

Australian location data attribution and age are recorded in `server/datasets/README.md` and `server/datasets/LICENSE-au-suburbs.txt`. No external geocoding account, API key or receipt-location upload is needed. This lookup helps organise receipts; it does not decide overnight eligibility or tax deductibility.


A self-hosted expense workspace for Australian employment and sole-trader records. Separate employment, business and personal spending, attach receipts, track overnight meals and give your tax agent access to all financial records.

**This branch: 1.0.2-beta.13. Stable remains 1.0.1.** [PocketSmith bank feeds](pocketsmith.md) support transaction sync and expense matching. Bank exports can also be imported as CSV using a column preview and mapping. Receipt entry works with No AI, local/existing Ollama or an explicitly configured cloud provider; configure the mode in Settings. The database and receipt originals live in your Docker data volume. Optional services receive the data required for their configured functions; GitHub is not a backup of your workspace.

## Features

- Client records, branded PDF invoices and quotes, payments and income exports.
- Your own SMTP email account, editable message templates and delivery history.
- Saved services, billable time and recurring invoice drafts.
- Separate Employment, Business and Personal expenses, percentage allocation and reimbursements.
- CommBank, Macquarie and American Express account labels; mapped CSV imports and duplicate detection.
- Receipt photos and PDFs; optional configured AI extraction into a draft you review before saving.
- Separate overnight spending with linked breakfast/lunch/dinner/incidentals, allowance records and comparison estimates.
- Monthly, quarterly or yearly category budgets, vehicle odometer records and vehicle-method comparison estimates.
- Owner and tax-agent logins, with per-agent Read only / Read & write permissions.
- Automatic tax-agent access to all financial records, including personal expenses and unfiled receipts.
- Financial-year CSV exports, activity history, password changes and account disabling.
- Persistent SQLite database, Docker health check and backup helper.

The app records actual expenses, allocations and invoice payments. It calculates invoice GST when you enable GST registration; overnight and vehicle comparisons are estimates for review. It does not determine tax deductibility, calculate expense GST/BAS, lodge returns or reconcile bank balances. Allowance thresholds are not automatic deductions. Imported purchases and transfers start Personal / To review until you categorise them. Credits in bank CSVs are skipped; record expense refunds manually as negative amounts.

## GitHub and Docker updates

The workflow in `.github/workflows/docker.yml` builds the image and runs integration tests and real-browser workflow checks before publishing. A passing push to `main` publishes:

```text
ghcr.io/chrisk0007/expense-pilot:latest
```

The numbered image tag comes from `server/VERSION`; a Git release tag must match it (for example `v1.0.0`). A passing push to `beta` publishes `ghcr.io/chrisk0007/expense-pilot:beta` plus a prerelease tag such as `1.0.1-beta.1`, and never changes `latest`. Both channels have commit-derived image tags. Pull requests run checks without publishing. See [release channels](releases.md) for separate beta-container setup and the repository’s **Actions** tab for build status.

The private repository does not make the application publicly accessible. GitHub Container Registry packages are private by default. To pull a private image, authenticate on Unraid with a GitHub personal access token (classic) that has `read:packages` access to this package:

```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME
```

Use your own GitHub username with package access and paste your token at the password prompt. Never put it in this repository or a chat message. Check registry login again after an Unraid reboot if private-image pulls fail. The container image can optionally be made public separately for unauthenticated pulls, but that exposes the bundled application code and is not done by this project automatically.

## First install on Unraid

Download the repository ZIP, extract its contents to `/mnt/user/appdata/expense-pilot`, then open the Unraid terminal:

```bash
cd /mnt/user/appdata/expense-pilot
bash prepare.sh
```

This creates `.env` with an optional random first-run setup token and a `data` folder owned by UID 99/GID 100. Existing configuration is preserved. On beta.9 or later, keep the token for protected setup or clear it for token-free setup.

### Unraid Docker page

The beta template is supplied in `deploy/unraid/expense-pilot.xml`. For stable v1.0.1, use the template from the main branch; its original setup and AI requirements still apply. Copy it to `/boot/config/plugins/dockerMan/templates-user/my-expense-pilot.xml`, then go to **Docker → Add Container** and select the Expense Pilot template. Set:

| Setting | Value |
| --- | --- |
| Repository | `ghcr.io/chrisk0007/expense-pilot:beta` |
| Network | Bridge |
| Web port | Host 8788 → container 8788 |
| Appdata | `/mnt/user/appdata/expense-pilot/data` → `/data` |
| Setup token | Optional; blank, or a random value of at least 24 characters |
| Secure cookie | `false` for LAN HTTP setup; `true` when using HTTPS |

The template keeps the database and receipts outside the image. Replace `<server-ip>` below with your Unraid server’s LAN IP address. Open `http://<server-ip>:8788`, create your owner login (enter a setup token only if configured). Complete owner setup before exposing the server remotely. No default password is provided. Enable **Autostart** for the container in Unraid.

When a tested image is published, use the normal Unraid Docker update controls to pull it. Keep the `/data` mapping unchanged. For private packages the server must remain authenticated to GHCR. Back up before updating.

### Docker Compose alternative

Do not run this at the same time as the Unraid template installation. Add this line to your generated `.env`:

```text
IMAGE=ghcr.io/chrisk0007/expense-pilot:1.0.2-beta.13
```

Then:

```bash
docker compose -f compose.registry.yaml pull
docker compose -f compose.registry.yaml up -d
```

To update, run the same two commands. To roll back after a migration, stop the container and restore the backup made with the matching older image into a separate data directory. Changing only `IMAGE` does not undo migrations. Keep the current data intact until the restored installation is verified; see [backup architecture](architecture.md#backups).

### Build locally instead

To build the checked-out beta source locally:

```bash
docker compose up -d --build
```

`compose.yaml` builds the source; `compose.registry.yaml` pulls the published image. Use only one installation method.

## AI receipt reading

Open **Settings → Receipts & AI → Configure receipt AI**. No AI keeps manual receipt entry available. Local Ollama uses an optional companion service; Existing / remote Ollama connects to an installed vision model on your own endpoint; Cloud AI uses your own OpenAI or Anthropic API key with explicit consent to provider processing and charges. There is no automatic fallback between providers. See [AI modes](public-release.md#receipt-ai-modes) for setup and model download commands.

The Ollama address must be reachable from inside the app container; `localhost` means that container itself. Legacy `OLLAMA_URL` / `OLLAMA_MODEL` values remain supported until you save in-app AI settings. New beta templates do not require these fields. Selecting a model does not download it.

Extraction runs when you choose **Read with AI** or enable **Read with AI after upload** during capture. Text PDFs can supply extracted text; scanned PDFs and photos supply images. PDF processing is limited to eight pages and uploads to 12 MB. Review suggested amounts, currency, dates, allocation and any trip match before acceptance. Foreign amounts require the actual AUD amount paid. Read the server's **Privacy & data** page for the configured services' data handling.

## Access

| Role | Access |
| --- | --- |
| Owner | All records, invoicing, clients, SMTP settings, imports, people and reports |
| Tax agent | Read all financial records; optionally create/edit financial records with Read & write permission |

All active tax-agent accounts see the whole financial workspace, including personal records and unfiled receipts. There are no per-record sharing checkboxes. Set each agent’s permission in Tax agent access; existing agents default to Read only. Downgrades take effect on the next API request; reload the agent’s browser to update visible controls. Owner-only account administration, business configuration and SMTP/email sending are excluded from financial write access. Disabling an account revokes active sessions. Account creation sends an invitation through the configured SMTP account. The generated password expires after 48 hours and must be replaced on first sign-in. All people can manage their own password and authenticator 2FA in Settings.

For terminal-only recovery:

```bash
docker exec -it expense-pilot python /app/reset_password.py
```

## Backup

```bash
cd /mnt/user/appdata/expense-pilot
bash backup.sh /mnt/user/backups/expense-pilot
```

Beta also provides an owner-only full backup download under **Settings → Data & privacy** and a [verified restore guide](public-release.md#backup-and-restore). A download is optional and does not schedule backups.

The host script discovers the container’s actual `/data` mount, stops it if running, backs up the database, receipts, signing key and `.env` (when present), then restores its previous running state. SMTP passwords are encrypted using the backed-up session key; financial records and receipt files are not encrypted at rest; keep the appdata share and backups private. When using the Unraid template, its environment fields are stored in the Unraid template, so back up the boot-device configuration too. A generated `.env` does not automatically update those GUI fields.

## Billing and your own email

1. Open **Settings → Business profile & branding**. Enter your trading name, ABN, contact details, payment instructions and default terms. Enable GST only if your business is registered. A logo and brand colour are supported. Invoice and quote numbering have separate configurable prefixes.
2. Open **Settings → Email delivery (SMTP)**. Enter your provider's SMTP hostname, port, username, password/app password, sender name/address and optional reply-to address. Choose STARTTLS (usually port 587) or SSL/TLS (usually port 465). Save, then use **Send test email** to send one message to your saved sender address.
3. Add billing contacts in **Clients**. Client payment terms are applied to new invoices.
4. Choose **Invoices → New invoice** or **Quotes → New quote**. Add line items, quantities, rates, discounts and GST treatment. Save a draft, inspect it and download the PDF.
5. **Issue & email** opens a recipient, subject and message preview. Nothing is sent until you click **Send email**. The PDF is attached. You can also **Issue without email** and send the downloaded file yourself.
6. Record deposits or partial/full payments when received. Overdue balances are highlighted. **Send reminder** opens an editable manual reminder. **Email payment receipt** uses the partial-payment or paid-in-full template and attaches the recorded payments and remaining balance. The payment form can also open a receipt preview after saving; cancelling the email keeps the payment.
7. Mark an issued quote accepted, then **Convert to invoice**. Each quote can have one linked invoice; deleting the invoice releases the quote for another conversion.

### Email details

The app supports authenticated SMTP and TLS-enabled SMTP relays. It does not read your inbox and does not currently implement Gmail/Microsoft OAuth sign-in. An OAuth-only mailbox needs provider-supported SMTP access or a suitable relay. Use the sender address your provider permits. Provider-specific hostnames and app passwords come from your email provider; do not enter credentials into GitHub or chat.

SMTP passwords are encrypted in the database and never returned to the browser. A blank password field keeps the saved password; **Remove the saved SMTP password** clears it. Back up the whole data folder including `session.key`: this key is needed to decrypt the password after a restore. This protects the database value, not against someone with access to both the database and its key.

**Settings → Email templates** has Invoices, Quotes, Reminders, Receipts, Statements and Signature tabs. Each message has separate subject/body text, insertable fields and a sample preview. Templates start with the supplied reference wording; **Use default wording** restores a tab's defaults before saving. Existing custom invoice/quote wording is preserved. Invoice and quote notes/payment terms stay under **Invoice & quote defaults**.

Fields include `{kind}`, `{number}`, `{client}`, `{business}`, `{total}`, `{balance}`, `{due_date}`, `{full_name}`, `{latest_payment}` and `{date_range}` where relevant. Client contact name falls back to the client business name; full name uses the owner's profile; latest payment excludes reversed records. The default manual reminder avoids saying overdue before the due date has passed.

The signature supports bold, italic, underline, text size, colour, highlighting, links and up to three embedded images (no wider than 300 px, no taller than 600 px and under 100 KB). Images are included in the email rather than fetched from a remote server. A plain-text alternative is included. Signatures apply to client billing emails, not invitations or SMTP test messages. You can omit the signature in an individual send preview.

**Settings → Automatic reminders** is off by default. The owner can enable reminders for a chosen number of days before due, on the due date, and up to six overdue dates. Only issued, unpaid invoices with a client email are eligible. **Reminder options** on an invoice allows an individual pause. Dates use the workspace timezone; the container checks once per minute. Each scheduled date is claimed once across workers/restarts; missed days are not sent as a batch after downtime. Failed/uncertain sends are not automatically retried. Pause the schedule before changing templates if you do not want scheduled sends during editing.

**Clients → Statement** offers all invoices and payments for a date range or all outstanding invoices as at today. The dated ledger includes opening balance, period invoices/payments, running balance and closing balance. Draft/void invoices and reversed payment records are excluded. Statements use the currently recorded information, so correcting/deleting past records can change a historical statement. Both forms can be downloaded as PDFs; the owner can preview and email them, with separate statement delivery history. Changes to statement data after the email preview require reloading before sending.

Each outgoing document has a delivery history. **Sent / mail server accepted** means SMTP accepted the message, not proof that the recipient read or received it. A timeout during delivery is marked uncertain and blocks an accidental retry. Check your provider's logs, then use **Confirm delivery status** to reconcile it. A pending delivery can be reconciled after five minutes if a process restart interrupted it.

### Billing records and access

- Business and client details are copied into each draft. Editing and saving the draft refreshes those details. Issued line items and business/client details are locked, so changing a client address or business name does not rewrite old invoices. Beta v1.0.2-beta.1 allows the invoice number to be amended separately.
- Tax agents can read/download all invoices/quotes, payments and client records, including internal client notes. Read & write agents can maintain those records. SMTP settings and outgoing email remain owner-only.
- Invoices use AUD. Line amounts and GST are rounded to cents with decimal arithmetic. Prices may include GST, exclude GST or carry no GST; individual GST-free lines and percentage discounts are supported.
- Payments are records of money already received. They do not charge a card, transfer funds or issue refunds. A mistaken payment record can be reversed with a reason. An unpaid issued document can be voided; its history remains available. **Delete invoice** permanently removes the invoice and its payment, wording and email history after confirmation. Payment totals and income reports update, linked time is released, the original quote returns to Accepted, and recurring schedules continue. Stable v1.0.1 does not reuse invoice numbers. In beta v1.0.2-beta.1, permanent deletion makes that number available for the next automatically numbered invoice; when several are available the most recently deleted is used first. Voiding does not release the number. This applies to deletions made after the beta upgrade. Pending or uncertain email delivery must be resolved first. Credit notes and actual refund processing are not yet implemented.
- **Services & prices** keeps common line items ready to use. In beta v1.0.2-beta.1, choose **Edit** to update a saved description, unit price or GST treatment. Changes apply when the service is next added to an invoice or quote; existing lines retain their saved values.
- **Billable time** records client, date, work, hours and rate. Select unbilled entries for one client to create an invoice. Linked entries cannot be billed twice. Deleting or voiding an invoice releases linked time.
- **Make recurring** creates weekly, fortnightly, monthly, quarterly or yearly schedules. The container checks once per minute and generates drafts only, never emails. Missed dates are caught up after a restart, at most 24 occurrences per schedule per pass. Month-end dates retain their original day where possible. Paused schedules require a current/future date when resumed. Changing the original invoice does not change the saved schedule; pause it and create a replacement to change its contents.
- **Income report** exports recorded invoice receipts for a chosen period, including proportional GST on partial payments. Reversed payment records are excluded. It is not a complete BAS or profit-and-loss statement; unrelated income, GST on expenses, bank reconciliation and tax estimates are not included.

### Update an existing Unraid installation

Back up first:

```bash
cd /mnt/user/appdata/expense-pilot
bash backup.sh /mnt/user/backups/expense-pilot
```

Use **Docker → Check for Updates → Update** for `expense-pilot`. Keep the same repository, port and `/data` mapping. If the package is private and pulling is denied, sign in again with `docker login ghcr.io -u YOUR_GITHUB_USERNAME`. Refresh your browser after the update and confirm the version in Settings matches the selected beta image (currently **1.0.2-beta.13**).

New database tables are created automatically on startup. Existing users, expenses, trips, receipts, setup configuration and session key are preserved. No additional container variables are required for billing or email: configure them inside the app. Existing source copies on appdata do not need replacing for the registry-image installation; pull the image through Unraid.

### Feature comparison and current boundaries

The billing workflows were informed by [Rounded's feature list](https://rounded.com.au/features) and [invoicing overview](https://rounded.com.au/features/invoicing), with an original interface and implementation. This version adds the core client, quote, invoice, payment and email workflows, not every Rounded feature.

Not yet provided: Stripe/PayPal card checkout and fee surcharges, automatic recurring sending, multi-currency billing, client portals/online quote acceptance, credit notes, expense rebilling, a running time stopwatch, recurring expenses, BAS preparation or automatic HELP/Medicare surcharge calculations. Bank imports and AI receipt reading continue to work as in v0.1.0.

## Verification

The GitHub workflow builds the Docker image and gates publication on the original expense tests, billing/access/SMTP/upgrade regression tests, and real-browser desktop/mobile workflows. All SMTP calls in automated tests are mocked; browser tests never send mail. See the repository Actions tab for the build outcome for your installed image.

A clean test copy of the original database structure is upgraded in tests, checking that existing expenses, receipt bytes and session key survive. The browser workflow exercises setup, client and business forms, invoice GST, issue/partial payment, PDF download, agent permissions, employment income, tax forecasts, receipt preview, separate meals, income report, quote conversion, recurring draft setup, and SMTP password retention. Real delivery through your own provider still requires the in-app test after you enter your settings.

Local PDF generation is checked with a single-page and multiple-page invoice. Actual bank-export samples and real Ollama extraction still require deployment checks.

For manual integration testing after a local build:

```bash
docker build -t expense-pilot:test .
docker run --rm --entrypoint python -v "$PWD/tests/server:/app/tests/server:ro" -v "$PWD/scripts:/app/scripts:ro" expense-pilot:test -m unittest discover -s tests/server -v
```

Expense Pilot is an original implementation, not affiliated with Rounded.


## Container memory and icon

The supplied 1 GB memory cap is a starting guardrail for the application. Ollama is a separate service and needs its own model-dependent resources. A hard cap does not reserve 1 GB; it bounds how much this container may consume. Keep the cap unless observed out-of-memory events or large concurrent PDF workloads justify raising it. Browser CI runs with `--memory 1g --memory-swap 1g` and captures peak memory as evidence, not a production capacity guarantee.

The logo is stored in appdata. `prepare.sh` copies it during setup, and container startup creates it automatically if it is missing. With the standard `/data` mount, the host file is:

```text
/mnt/user/appdata/expense-pilot/data/expense-pilot-logo.png
```

The Unraid template now points **Icon URL** at that local file:

```text
file:///mnt/user/appdata/expense-pilot/data/expense-pilot-logo.png
```

No server IP, web port or internet connection is needed for the icon. Keep all three slashes after `file:`. If you change the host Appdata location, change the Icon URL path to match. The icon remains available while the app is stopped. An existing logo file is preserved, so you may replace it with your own image.

For an existing installation, update and start the container, then open **Docker → expense-pilot → Edit → Advanced View**, paste the local file URL into **Icon URL**, and Apply. Existing saved Unraid templates do not change when the image updates. If installing without `prepare.sh`, let the container start once to create the file before applying the icon setting.

To copy the logo immediately from an older running image without waiting for an update, run this in the Unraid terminal with the standard appdata path:

```bash
docker cp expense-pilot:/app/static/expense-pilot-logo.png /mnt/user/appdata/expense-pilot/data/expense-pilot-logo.png
chmod 644 /mnt/user/appdata/expense-pilot/data/expense-pilot-logo.png
```

This is the container-list icon. Your invoice business logo is separately set in **Settings → Business profile & branding**. The current template's `--memory 1g` extra parameter controls memory; change it to `--memory 2g` only if your workload needs it.


## Development and backup options

See [architecture and backups](architecture.md) for development commands, numbered migrations, custom backup mounts and restore guidance. Run installation commands from the repository root.

## Billing navigation, reminders and deleting expenses

Invoices, Quotes, Clients and Recurring invoices share a top navigation bar. Beta v1.0.2-beta.1 also standardises Services & prices and includes Billable time in that menu. Choose Invoices or Quotes to return to a document list. Email settings opens the message templates/signature, SMTP delivery and reminder settings. Document notes and payment instructions remain under Invoice & quote defaults.

The owner can switch automatic reminders on or off while creating an invoice or directly in any invoice’s details. The preference is saved for drafts, issued invoices and recurring-generated invoices. Editing or duplicating a draft preserves it. When making a recurring schedule, select whether its generated invoices allow reminders; each generated invoice can then be changed individually.

Settings → Automatic invoice reminders controls the shared sending switch and dates. Choose a reminder before the due date, on the due date, and up to six separate days after it. The summary shows the schedule. Switching global sending off keeps the schedule saved. An invoice must also allow reminders, be issued, and have an unpaid balance and client email address. Dates use the workspace timezone. Changing the schedule can make an existing invoice eligible to send today; drafts, paid invoices and voided invoices are skipped.

Deleting a saved expense now also deletes its attached receipt, saved draft, extraction data and cached previews. It is removed from Expenses, Receipt inbox and the reports that use those records. The confirmation describes this permanent removal. Existing backup archives are not rewritten. A linked PocketSmith source transaction remains ignored in the bank history so syncing does not recreate the deleted expense.


## Beta invoice numbers and custom reminders

In v1.0.2-beta.1, leave **Invoice number (optional)** blank when creating an invoice to assign it automatically, or enter a unique number. For an existing invoice, use **Edit invoice number** in its details; draft editing also includes the number. Use up to 50 letters, numbers, spaces, full stops, underscores or hyphens. Numbers cannot duplicate an existing invoice or quote, even with different capitalisation. Payments and line items stay linked. Already sent emails and downloaded PDFs retain their old number; new previews and downloads use the new one. Resolve any pending or uncertain email before renumbering.

Open an invoice's **Reminder options** to set a custom schedule and individual subject/message templates for before/on-due, overdue and manual reminders. Insert fields and preview the message using that invoice's values. Turn an override off to follow the latest shared settings. The shared signature remains included and automatic sending must still be enabled in Settings. Duplicates and newly created recurring schedules copy the invoice's reminder choices; each resulting invoice can be customised independently. Renumbering does not resend a reminder already attempted for the same due date and day.
