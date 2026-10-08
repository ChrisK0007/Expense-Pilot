# Expense Pilot

## v0.7.0 — invitations, authenticator 2FA and receipt improvements

- Typed dates automatically become **DD/MM/YYYY** when you leave the field. Accepted examples: `8/10/2026`, `8-10-26`, `08.10.2026`, `081026`, `08102026` and `2026-10-08`. Two-digit years mean 2000–2099. Impossible dates and missing years are rejected; month/day order is never guessed.
- **Settings → Home base & receipt sorting:** search a suburb, city, area or postcode and select a suggestion. Nearby suburbs are recognised from the bundled Australian location list using an adjustable **50 km default local radius**. A preview shows the number of included suburbs and examples. Keep extra local names only for exceptions. Existing recognised bases such as Sunshine Coast work without re-entering every suburb. Coordinates are approximate suburb or area centres; choose a suburb for a more precise base. Unknown, ambiguous or unrecognised overseas locations stay in the inbox for manual review. Foreign currency alone does not prove a foreign location. All suggested overnight trips still require review and acceptance.
- **Settings → Account invitations:** save the URL people use to access Expense Pilot. Configure **Email delivery & templates** with SMTP. Then **People & access → Add person** sends an invitation with a generated temporary password, valid for **48 hours**. No manually entered initial password is required. The new person must replace it before accessing records. Failed or uncertain email delivery is shown against the person; **Resend invitation** generates a replacement and invalidates the old password. Existing accounts keep their passwords.
- **Settings → Two-factor authentication:** enter your current password, scan the QR code with a TOTP authenticator (for example Microsoft Authenticator, Google Authenticator or 1Password), then enter its six-digit code. Save the ten recovery codes shown once after setup. Every code works once. Future sign-ins require the password and an authenticator or recovery code. Each account enables 2FA individually, including read-only tax agents; the owner can see 2FA status under People & access.
- QR codes are generated locally. Authenticator secrets are encrypted using the persisted `session.key`; recovery codes are stored only as hashes. Enabling/disabling 2FA and changing passwords revoke other sessions. Reused authenticator codes are rejected and failed attempts are limited. Keep the server clock accurate and retain `session.key` in backups.
- Lost phone: use an unused recovery code to sign in. To replace your authenticator, disable 2FA with your password and a fresh recovery/authenticator code, then set it up again. If all recovery methods are lost, use the existing terminal recovery command (`python reset_password.py` inside the container); it now offers an explicit 2FA reset. It also clears a pending temporary-password requirement. Disabled accounts stay disabled.

Australian location data attribution and age are recorded in `datasets/README.md` and `datasets/LICENSE-au-suburbs.txt`. No external geocoding account, API key or receipt-location upload is needed. This lookup helps organise receipts; it does not decide overnight eligibility or tax deductibility.


A self-hosted expense workspace with a clean, Rounded-inspired interface. Separate employment, business and personal spending, attach receipts, track overnight meals and give your tax agent access to all financial records.

**Version: 0.7.0.** No live bank feeds: bank exports are imported as CSV using a column preview and mapping. AI receipt extraction requires a separately configured Ollama service. All financial records stay in your Unraid appdata folder; GitHub contains application code only.

## Features

- Client records, branded PDF invoices and quotes, payments and income exports.
- Your own SMTP email account, editable message templates and delivery history.
- Saved services, billable time and recurring invoice drafts.
- Separate Employment, Business and Personal expenses, percentage allocation and reimbursements.
- CommBank, Macquarie and American Express account labels; mapped CSV imports and duplicate detection.
- Receipt photos and PDFs; optional Ollama extraction into a draft you review before saving.
- Overnight trips, linked breakfast/lunch/dinner/incidentals and a separate allowance record.
- Owner, employee and tax-agent logins, with per-agent Read only / Read & write permissions.
- Automatic tax-agent access to all financial records, including personal expenses and unfiled receipts.
- Financial-year CSV exports, activity history, password changes and account disabling.
- Persistent SQLite database, Docker health check and backup helper.

The app records actual expenses, allocations and invoice payments. It calculates invoice GST when you enable GST registration; it does not determine tax deductibility, automatically apply ATO meal rates, calculate expense GST/BAS, lodge returns or reconcile bank balances. Imported purchases and transfers start Personal / To review until you categorise them. Credits in bank CSVs are skipped; record expense refunds manually as negative amounts.

## GitHub and Docker updates

The workflow in `.github/workflows/docker.yml` builds the image and runs integration tests and real-browser workflow checks before publishing. A passing push to `main` publishes:

```text
ghcr.io/chrisk0007/expense-pilot:latest
```

A `v0.1.0` Git tag also publishes the numbered `0.1.0` tag. Every build has a commit-derived image tag for rollback. Pull requests run checks without publishing. The workflow must succeed before the image exists. See the repository's **Actions** tab for its status.

The private repository does not make the application publicly accessible. GitHub Container Registry packages are private by default. To pull a private image, authenticate on Unraid with a GitHub personal access token (classic) that has `read:packages` access to this package:

```bash
docker login ghcr.io -u ChrisK0007
```

Paste the token at the password prompt. Never put it in this repository or a chat message. Check registry login again after an Unraid reboot if private-image pulls fail. The container image can optionally be made public separately for unauthenticated pulls, but that exposes the bundled application code and is not done by this project automatically.

## First install on Unraid

Download the repository ZIP, extract its contents to `/mnt/user/appdata/expense-pilot`, then open the Unraid terminal:

```bash
cd /mnt/user/appdata/expense-pilot
bash prepare.sh
```

This creates `.env` with a random first-run setup token and a `data` folder owned by UID 99/GID 100. Existing configuration is preserved.

### Unraid Docker page

A template is supplied in `unraid/expense-pilot.xml`. Copy it to `/boot/config/plugins/dockerMan/templates-user/my-expense-pilot.xml`, then go to **Docker → Add Container** and select the Expense Pilot template. Set:

| Setting | Value |
| --- | --- |
| Repository | `ghcr.io/chrisk0007/expense-pilot:latest` |
| Network | Bridge |
| Web port | Host 8788 → container 8788 |
| Appdata | `/mnt/user/appdata/expense-pilot/data` → `/data` |
| Setup token | `SETUP_TOKEN` value generated in `.env` |
| Ollama URL | Blank for manual entry, or your reachable Ollama address |
| Ollama model | Name of an installed model; photos/scans require vision support |
| Secure cookie | `false` for LAN HTTP setup; `true` when using HTTPS |

The template keeps the database and receipts outside the image. Replace `<server-ip>` below with your Unraid server’s LAN IP address. Open `http://<server-ip>:8788`, enter the setup token and create your owner login. No default password is provided. Enable **Autostart** for the container in Unraid.

When a tested image is published, use the normal Unraid Docker update controls to pull it. Keep the `/data` mapping unchanged. For private packages the server must remain authenticated to GHCR. Back up before updating.

### Docker Compose alternative

Do not run this at the same time as the Unraid template installation. Add this line to your generated `.env`:

```text
IMAGE=ghcr.io/chrisk0007/expense-pilot:latest
```

Then:

```bash
docker compose -f compose.registry.yaml pull
docker compose -f compose.registry.yaml up -d
```

To update, run the same two commands. To roll back, change `IMAGE` to a previously published version or commit tag and run them again. Preserve the database and keep data compatibility in mind when rolling back.

### Build locally instead

If no registry image is available yet:

```bash
docker compose up -d --build
```

`compose.yaml` builds the source; `compose.registry.yaml` pulls the published image. Use only one installation method.

## AI receipt reading

Set `OLLAMA_URL` to an address reachable from inside the app container, such as your Unraid host's LAN IP and Ollama port. `localhost` means the expense container itself. Set `OLLAMA_MODEL` to an installed model. Text PDFs send extracted text; scanned PDFs are rendered into images, as are receipt photos. PDFs are limited to eight pages and uploads to 12 MB.

Nothing is sent to Ollama until you select **Read with AI** or enable **Read with AI after upload** during capture. Check all suggested values before saving. Foreign amounts need manual AUD conversion. This version supports Ollama, not OpenAI API connections. If using the Unraid template, edit its environment-variable fields and Apply; if using Compose, edit `.env` and recreate the container.

## Access

| Role | Access |
| --- | --- |
| Owner | All records, invoicing, clients, SMTP settings, imports, people and reports |
| Employee | Only their own business expenses, receipts and trips |
| Tax agent | Read all financial records; optionally create/edit financial records with Read & write permission |

All active tax-agent accounts see the whole financial workspace, including personal records and unfiled receipts. There are no per-record sharing checkboxes. Set each agent’s permission in People & access; existing agents default to Read only. Downgrades take effect on the next API request; reload the agent’s browser to update visible controls. Owner-only account administration, business configuration and SMTP/email sending are excluded from financial write access. Disabling an account revokes active sessions. Account creation sends an invitation through the configured SMTP account. The generated password expires after 48 hours and must be replaced on first sign-in. All people can manage their own password and authenticator 2FA in Settings.

For terminal-only recovery:

```bash
docker exec -it expense-pilot python /app/reset_password.py
```

## Backup

```bash
cd /mnt/user/appdata/expense-pilot
bash backup.sh /mnt/user/backups/expense-pilot
```

The script pauses the app by stopping its container, backs up the database, receipts, signing key and `.env`, then restarts it. SMTP passwords are encrypted using the backed-up session key; financial records and receipt files are not encrypted at rest; keep the appdata share and backups private. When using the Unraid template, its environment fields are stored in the Unraid template, so back up the boot-device configuration too. A generated `.env` does not automatically update those GUI fields.

## Billing and your own email (v0.2.0)

1. Open **Settings → Business profile & branding**. Enter your trading name, ABN, contact details, payment instructions and default terms. Enable GST only if your business is registered. A logo and brand colour are supported. Invoice and quote numbering have separate configurable prefixes.
2. Open **Settings → Email delivery & templates**. Enter your provider's SMTP hostname, port, username, password/app password, sender name/address and optional reply-to address. Choose STARTTLS (usually port 587) or SSL/TLS (usually port 465). Save, then use **Send test email** to send one message to your saved sender address.
3. Add billing contacts in **Clients**. Client payment terms are applied to new invoices.
4. Choose **Invoices → New invoice** or **Quotes → New quote**. Add line items, quantities, rates, discounts and GST treatment. Save a draft, inspect it and download the PDF.
5. **Issue & email** opens a recipient, subject and message preview. Nothing is sent until you click **Send email**. The PDF is attached. You can also **Issue without email** and send the downloaded file yourself.
6. Record deposits or partial/full payments when received. Overdue balances are highlighted. **Send reminder** opens an editable reminder; it does not automatically contact your client.
7. Mark an issued quote accepted, then **Convert to invoice**. Each quote can have one linked invoice; deleting the invoice draft releases the quote for another conversion.

### Email details

The app supports authenticated SMTP and TLS-enabled SMTP relays. It does not read your inbox and does not currently implement Gmail/Microsoft OAuth sign-in. An OAuth-only mailbox needs provider-supported SMTP access or a suitable relay. Use the sender address your provider permits. Provider-specific hostnames and app passwords come from your email provider; do not enter credentials into GitHub or chat.

SMTP passwords are encrypted in the database and never returned to the browser. A blank password field keeps the saved password; **Remove the saved SMTP password** clears it. Back up the whole data folder including `session.key`: this key is needed to decrypt the password after a restore. This protects the database value, not against someone with access to both the database and its key.

Email templates support `{kind}`, `{number}`, `{client}`, `{business}`, `{total}`, `{balance}` and `{due_date}`. Each outgoing document has a delivery history. **Sent / mail server accepted** means SMTP accepted the message, not proof that the recipient read or received it. A timeout during delivery is marked uncertain and blocks an accidental retry. Check your provider's logs, then use **Confirm delivery status** to reconcile it. A pending delivery can be reconciled after five minutes if a process restart interrupted it.

### Billing records and access

- Business and client details are copied into each draft. Editing and saving the draft refreshes those details. Issued documents are immutable, so changing a client address or business name does not rewrite old invoices.
- Employee accounts have no access to clients, invoices, time billing or email settings. Tax agents can read/download all invoices/quotes, payments and client records, including internal client notes. Read & write agents can maintain those records. SMTP settings and outgoing email remain owner-only.
- Invoices use AUD. Line amounts and GST are rounded to cents with decimal arithmetic. Prices may include GST, exclude GST or carry no GST; individual GST-free lines and percentage discounts are supported.
- Payments are records of money already received. They do not charge a card, transfer funds or issue refunds. A mistaken payment record can be reversed with a reason. An unpaid issued document can be voided; its history remains available. Credit notes and actual refund processing are not yet implemented.
- **Saved services & prices** keeps common line items ready to use.
- **Billable time** records client, date, work, hours and rate. Select unbilled entries for one client to create an invoice. Linked entries cannot be billed twice. Deleting a draft or voiding its invoice releases linked time.
- **Make recurring** creates weekly, fortnightly, monthly, quarterly or yearly schedules. The container checks once per minute and generates drafts only, never emails. Missed dates are caught up after a restart, at most 24 occurrences per schedule per pass. Month-end dates retain their original day where possible. Paused schedules require a current/future date when resumed. Changing the original invoice does not change the saved schedule; pause it and create a replacement to change its contents.
- **Income report** exports recorded invoice receipts for a chosen period, including proportional GST on partial payments. Reversed payment records are excluded. It is not a complete BAS or profit-and-loss statement; unrelated income, GST on expenses, bank reconciliation and tax estimates are not included.

### Update an existing Unraid installation

Back up first:

```bash
cd /mnt/user/appdata/expense-pilot
bash backup.sh /mnt/user/backups/expense-pilot
```

Use **Docker → Check for Updates → Update** for `expense-pilot`. Keep the same repository, port and `/data` mapping. If the package is private and pulling is denied, sign in again with `docker login ghcr.io -u ChrisK0007`. Refresh your browser after the update and confirm **Settings → Version 0.7.0**.

New database tables are created automatically on startup. Existing users, expenses, trips, receipts, setup configuration and session key are preserved. No additional container variables are required for billing or email: configure them inside the app. Existing source copies on appdata do not need replacing for the registry-image installation; pull the image through Unraid.

### Feature comparison and current boundaries

The billing workflows were informed by [Rounded's feature list](https://rounded.com.au/features) and [invoicing overview](https://rounded.com.au/features/invoicing), with an original interface and implementation. This version adds the core client, quote, invoice, payment and email workflows, not every Rounded feature.

Not yet provided: live bank feeds, Stripe/PayPal card checkout and fee surcharges, automatic reminder emails, automatic recurring sending, multi-currency billing, client portals/online quote acceptance, credit notes, expense rebilling, client statements, a running time stopwatch, recurring expenses, BAS preparation or automatic HELP/Medicare surcharge calculations. Bank imports and AI receipt reading continue to work as in v0.1.0.

## Verification

The GitHub workflow builds the Docker image and gates publication on the original expense tests, billing/access/SMTP/upgrade regression tests, and real-browser desktop/mobile workflows. All SMTP calls in automated tests are mocked; browser tests never send mail. See the repository Actions tab for the build outcome for your installed image.

A clean test copy of the original database structure is upgraded in tests, checking that existing expenses, receipt bytes and session key survive. The browser workflow exercises setup, client and business forms, invoice GST, issue/partial payment, PDF download, agent permissions, employment income, tax forecasts, receipt preview, separate meals, income report, quote conversion, recurring draft setup, and SMTP password retention. Real delivery through your own provider still requires the in-app test after you enter your settings.

Local PDF generation is checked with a single-page and multiple-page invoice. Actual bank-export samples and real Ollama extraction still require deployment checks.

For manual integration testing after a local build:

```bash
docker build -t expense-pilot:test .
docker run --rm --entrypoint python -v "$PWD/tests:/app/tests:ro" expense-pilot:test -m unittest discover -s tests -v
```

Expense Pilot is an original implementation, not affiliated with Rounded.


## Receipt inbox and branding (v0.3.0)

- New Expense Pilot logo, blue navigation, cleaner cards, expense activity chart and mobile layout.
- Choose **Capture receipts** on Overview or Expenses, or open **Receipt inbox**. Upload several photos/PDFs or take a photo. Files are saved immediately without creating expenses or requiring a category.
- With Ollama configured, **Read with AI after upload** reads each uploaded receipt. Keep the capture window open until the queue finishes. Results are saved; failed scans retain the original and can be retried or entered manually. If interrupted, use Read with AI on the saved receipt.
- Review later: confirm merchant, date, AUD total, Employment/Business/Personal, category and use percentage. AI never chooses a use percentage. Tax agents automatically have access to all saved receipts. Unfiled receipts stay out of expense totals and exports.
- The review screen suggests a category/workspace from that person's latest reviewed expense at the same merchant. Matching date/amount transactions can be explicitly linked instead of creating another expense. Foreign/unknown currencies require an AUD amount entered by you.
- Exact duplicate uploaded files for the same person are reused. Different photographs of the same receipt still need your review. Employees see only their own receipts; tax agents see all receipts, including unfiled ones.
- Invoice/quote PDFs use a clean two-column layout inspired by the supplied example: business branding, client and invoice details, notes above the line items, totals and payment details. Invoice emails continue to carry a real PDF attachment. Your business logo in Settings stays separate from the application logo. Online card payments are not added by this update.
- Set `OLLAMA_URL` and a vision-capable `OLLAMA_MODEL` in the container to enable photo/scanned-PDF extraction. No new external AI provider or subscription is required. Text PDFs also work.

The app logo was generated with the built-in image generation tool using the direction: a cobalt blue paper aircraft integrated with a receipt/checkmark, a turquoise accent and a transparent background. It is included at `static/expense-pilot-logo.png`.


## Financial workspace (v0.4.0)

- **People & access:** choose Read only or Read & write for each tax agent. All financial records are visible automatically. Read & write includes expenses, receipt filing, trips, clients, invoices, payments, employment income and forecast assumptions; it does not grant user administration or SMTP/email sending.
- **Trips & meals:** add a trip, then choose **Add meal** on its card. Ordinary expense forms and category lists no longer offer meals. Earlier unlinked meal records remain available under **Meals needing a trip**. Meals still count once in financial totals and reviewed tax allocations.
- **Receipt preview:** View receipt opens a viewer inside the app. Images and multi-page PDFs support zoom and page navigation. Download remains optional. PDF pages render individually; no external document viewer receives your receipts.
- **Employment income:** record gross taxable salary and PAYG withholding by payment date, using payslips or an annual total for the same income, not both. Employer super is excluded.
- **Tax forecast:** combines employment income, paid invoice receipts excluding GST and reviewed expense allocations. Choose FY 2024–25 through 2027–28. Enter expected annual totals or enable daily-rate projection; annual overrides replace recorded totals. Without either, it uses recorded totals only.

The forecast applies Australian resident individual brackets and LITO, with a clearly labelled 2% Medicare provision. Medicare low-income/family adjustments and exemptions require an override. HELP, Medicare levy surcharge and other special obligations require an Other tax provision. Set PAYG instalments, other income/deductions, expense GST credits and savings set aside in assumptions. Business losses are flagged for adviser review and do not automatically offset salary. It is a planning estimate for an individual/sole trader, not company/trust tax, BAS or a lodged assessment. Supported rates are recorded in `tax_core.py` with sources checked 8 October 2026.

### Container memory and icon

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

## Receipt thumbnails and currency review (v0.4.2)

PDF inbox cards show the first page, with lazy loading and a small cached thumbnail. Open the full viewer for other pages. Previews remain subject to the receipt permissions.

Receipt AI now asks for visible currency evidence. Printed currency markers take priority; Australian ABN or GST plus an Australian website can suggest AUD. A dollar sign alone does not establish USD. From v0.6.0, receipts without another specified currency default to AUD; conflicting currency markers are left for review. Vision-model evidence is still an AI suggestion.

For previously scanned receipts, open **Review & categorise → This receipt is AUD**, or enter a three-letter code in **Receipt currency → Confirm currency**. Corrections persist without re-uploading and survive a new AI scan. Correcting a currency label does not perform an exchange-rate conversion or alter an existing expense. For foreign receipts, enter the actual AUD amount paid. Use **Read with AI** to re-scan an older receipt using the new rules.


## Accounting workspace redesign (v0.5.0)

- Compact navigation groups billing, money records and reporting. Line item templates now have their own page as well as the existing Settings shortcut.
- Choose Light, Dark or System in the sidebar, the mobile header or Settings → Appearance. The choice is remembered in this browser; System follows device changes. Invoice PDFs keep their print colours.
- The dashboard compares calendar-year business receipts (excluding GST) or allocated expenses, with line/bar views and accessible monthly figures. The separate financial-year selector controls breakdowns and the existing tax forecast summary. No sample financial records are added.
- Invoice and quote lists have client, status, financial-year and description search filters, sortable columns and final payment dates for fully paid invoices. Summary totals cover all dates.
- Expense reports show category, merchant or workspace breakdowns and an allocation chart. Refunds reduce totals; chart segments show positive net groups only. The CSV export includes all workspaces for the selected dates. Income reports show a client breakdown.
- This is a visual and workflow update: it retains the existing permissions, receipt processing, SMTP/PDF delivery and tax calculations. It does not add live bank feeds, automatic email sending or new tax rules.

Update the Docker image and refresh the browser. Existing appdata and financial records are retained.


## Readability and document wording (v0.5.1)

Small interface text is two pixels larger, with more room in the sidebar. The business/trading name from Settings → Business profile & branding appears beneath your name, and refreshes immediately when saved.

Open an issued invoice or quote and choose **Edit wording** to change line descriptions, reference, notes/terms and invoice payment instructions. Owners and tax agents with Read & write access can make these changes. Amounts, GST, dates and payment records are retained; void and converted documents cannot be amended. Earlier wording is retained in appdata history. A newly downloaded or resent PDF includes the updated wording; PDFs already emailed are unchanged. Drafts retain their full **Edit draft** editor.

## Receipt retries, Australian dates and wording defaults (v0.5.2)

- Use **Reprocess with AI** on an unfiled receipt card or inside Review receipt to run your configured Ollama model again. Review the new suggestions before saving. A currency you explicitly confirmed is retained; rescanning does not change a filed expense. Failed scans can be retried.
- Dates are displayed and entered as **DD/MM/YYYY** throughout the app, PDFs, email date tags and CSV exports. APIs and database dates remain ISO (YYYY-MM-DD).
- **Settings → Invoice & quote defaults** stores separate invoice and quote notes/terms and email subject/message templates, payment instructions and quote validity. Existing shared text is used until you configure these defaults. New drafts inherit the defaults; existing documents and recurring schedules keep their saved wording. Invoice due dates continue to use each client's payment terms.
- **Trips & meals** supports search by location, purpose, merchant and notes, plus workspace, meal type and date filters. Date ranges match overlapping trips; the matching-meals table shows only meals within the range. Trip cards retain the full trip totals.
- **Employer allowance (optional)** records an allowance paid by an employer for reference. Leave it blank when none was paid. It does not reduce meal costs or feed into the tax forecast.

## Draft receipt sorting and vehicles (v0.6.0)

**Expense Pilot — A clearer view of every dollar.**

- Create reusable expense categories in **Settings → Expense categories**, or while editing an expense. Owners and write-enabled tax agents can create workspace categories; employees can use them.
- **Vehicles** stores vehicles, registrations, journeys and running costs. Log either start/end odometer readings or a distance in kilometres, with the purpose, workspace and use percentage. Link an expense to a vehicle from either screen. Costs remain ordinary expenses and are counted once. Journey kilometres are not automatically turned into a tax deduction. Export journeys as CSV; expense CSV includes the linked vehicle.
- The receipt inbox now has **Draft receipts** and **All receipts**. **Save draft** persists partial details without creating an expense. **Save expense** files the reviewed values. All receipts displays the current linked expense’s AUD amount, date and merchant rather than the original AI reading.
- New receipt currency defaults to **AUD** when no other currency is specified; explicit foreign-currency evidence and manual currency confirmations take precedence. Conflicting currency markers still require review. Work/business use defaults to **100%**, preserving manual overrides; personal expenses remain excluded from allocated totals.
- **Reprocess all with AI** processes the current draft receipts sequentially, shows progress and errors, and can stop after the current receipt. Keep the tab open while the batch runs. Filed receipts are excluded. Saved manual drafts and confirmed currency survive rescanning.
- Configure **Home base & receipt sorting** in Settings or the inbox. Enter the city/suburb plus local aliases (for example Sunshine Coast with Maroochydore, Mooloolaba and Caloundra). Each account has its own home area and default receipt workspace.
- AI reads the seller’s city/address and meal type when printed. Consecutive meal receipt dates from the same place are grouped into **possible overnight trips**, separately for each person and workspace. Matching receipts can join an existing trip. Missing locations, local places and personal receipts are not suggested as new overnight trips. This uses locality-name matching, not geolocation or measured travel distance.
- Review suggested dates, purpose, meal types, amounts in AUD and use percentages, then **Accept trip & meals**. A single receipt can suggest a one-night draft, but cannot prove an overnight: confirm the actual dates yourself. Nothing is added to financial totals before acceptance. **Not an overnight** dismisses the suggestion while keeping the receipts.
- Three-dot action menus are available on expense rows, receipt cards, vehicles, trips and documents, with keyboard navigation and support for light/dark modes.
