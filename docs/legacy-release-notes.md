# Earlier release notes

Historical notes from development before v1.0, including the former iOS prototype. Some workflows were superseded; use the [current guide](guide.md) and [release history](CHANGELOG.md) for current behaviour.

## Receipt inbox and branding (v0.3.0)

- New Expense Pilot logo, blue navigation, cleaner cards, expense activity chart and mobile layout.
- Choose **Capture receipts** on Overview or Expenses, or open **Receipt inbox**. Upload several photos/PDFs or take a photo. Files are saved immediately without creating expenses or requiring a category.
- With Ollama configured, **Read with AI after upload** reads each uploaded receipt. Keep the capture window open until the queue finishes. Results are saved; failed scans retain the original and can be retried or entered manually. If interrupted, use Read with AI on the saved receipt.
- Review later: confirm merchant, date, AUD total, Employment/Business/Personal, category and use percentage. AI never chooses a use percentage. Tax agents automatically have access to all saved receipts. Unfiled receipts stay out of expense totals and exports.
- The review screen suggests a category/workspace from that person's latest reviewed expense at the same merchant. Matching date/amount transactions can be explicitly linked instead of creating another expense. Foreign/unknown currencies require an AUD amount entered by you.
- Exact duplicate uploaded files for the same person are reused. Different photographs of the same receipt still need your review. Tax agents see all receipts, including unfiled ones.
- Invoice/quote PDFs use a clean two-column layout inspired by the supplied example: business branding, client and invoice details, notes above the line items, totals and payment details. Invoice emails continue to carry a real PDF attachment. Your business logo in Settings stays separate from the application logo. Online card payments are not added by this update.
- Set `OLLAMA_URL` and a vision-capable `OLLAMA_MODEL` in the container to enable photo/scanned-PDF extraction. No new external AI provider or subscription is required. Text PDFs also work.

The app logo was generated with the built-in image generation tool using the direction: a cobalt blue paper aircraft integrated with a receipt/checkmark, a turquoise accent and a transparent background. It is included at `server/static/expense-pilot-logo.png`.


## Financial workspace (v0.4.0)

- **Tax agent access:** choose Read only or Read & write for each tax agent. All financial records are visible automatically. Read & write includes expenses, receipt filing, trips, clients, invoices, payments, employment income and forecast assumptions; it does not grant user administration or SMTP/email sending.
- **Trips & meals:** add a trip, then choose **Add meal** on its card. Ordinary expense forms and category lists no longer offer meals. Earlier unlinked meal records remain available under **Meals needing a trip**. Meals still count once in financial totals and reviewed tax allocations.
- **Receipt preview:** View receipt opens a viewer inside the app. Images and multi-page PDFs support zoom and page navigation. Download remains optional. PDF pages render individually; no external document viewer receives your receipts.
- **Employment income:** record gross taxable salary and PAYG withholding by payment date, using payslips or an annual total for the same income, not both. Employer super is excluded.
- **Tax forecast:** combines employment income, paid invoice receipts excluding GST and reviewed expense allocations. Choose FY 2024–25 through 2027–28. Enter expected annual totals or enable daily-rate projection; annual overrides replace recorded totals. Without either, it uses recorded totals only.

The forecast applies Australian resident individual brackets and LITO, with a clearly labelled 2% Medicare provision. Medicare low-income/family adjustments and exemptions require an override. HELP, Medicare levy surcharge and other special obligations require an Other tax provision. Set PAYG instalments, other income/deductions, expense GST credits and savings set aside in assumptions. Business losses are flagged for adviser review and do not automatically offset salary. It is a planning estimate for an individual/sole trader, not company/trust tax, BAS or a lodged assessment. Supported rates are recorded in `tax_core.py` with sources checked 8 October 2026.

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

- Create reusable expense categories in **Settings → Expense categories**, or while editing an expense. Owners and write-enabled tax agents can create workspace categories.
- **Vehicles** stores vehicles, registrations, journeys and running costs. Log either start/end odometer readings or a distance in kilometres, with the purpose, workspace and use percentage. Link an expense to a vehicle from either screen. Costs remain ordinary expenses and are counted once. Journey kilometres are not automatically turned into a tax deduction. Export journeys as CSV; expense CSV includes the linked vehicle.
- The receipt inbox now has **Draft receipts** and **All receipts**. **Save draft** persists partial details without creating an expense. **Save expense** files the reviewed values. All receipts displays the current linked expense’s AUD amount, date and merchant rather than the original AI reading.
- New receipt currency defaults to **AUD** when no other currency is specified; explicit foreign-currency evidence and manual currency confirmations take precedence. Conflicting currency markers still require review. Work/business use defaults to **100%**, preserving manual overrides; personal expenses remain excluded from allocated totals.
- **Reprocess all with AI** processes the current draft receipts sequentially, shows progress and errors, and can stop after the current receipt. Keep the tab open while the batch runs. Filed receipts are excluded. Saved manual drafts and confirmed currency survive rescanning.
- Configure **Home base & receipt sorting** in Settings or the inbox. Enter the city/suburb plus local aliases (for example Sunshine Coast with Maroochydore, Mooloolaba and Caloundra). Each account has its own home area and default receipt workspace.
- AI reads the seller’s city/address and meal type when printed. Consecutive meal receipt dates from the same place are grouped into **possible overnight trips**, separately for each person and workspace. Matching receipts can join an existing trip. Missing locations, local places and personal receipts are not suggested as new overnight trips. This uses locality-name matching, not geolocation or measured travel distance.
- Review suggested dates, purpose, meal types, amounts in AUD and use percentages, then **Accept trip & meals**. A single receipt can suggest a one-night draft, but cannot prove an overnight: confirm the actual dates yourself. Nothing is added to financial totals before acceptance. **Not an overnight** dismisses the suggestion while keeping the receipts.
- Three-dot action menus are available on expense rows, receipt cards, vehicles, trips and documents, with keyboard navigation and support for light/dark modes.

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
