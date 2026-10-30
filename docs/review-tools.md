# Review workflows (beta)

Beta 1.0.6-beta.12 places **Needs attention** immediately below Dashboard and moves optional tools into their existing sections. There is no separate Review tools menu. The iPhone API remains version 1; no new iPhone build is required.

| Section | Optional tools |
| --- | --- |
| Bank accounts → Matching options | Suggested matches and payment reconciliation |
| Expenses → Expense tools | Categorisation rules, receipt items, equipment |
| Employment income → Optional payslip checks | Pay-period and YTD comparisons |
| Vehicles → Drive tools | Bulk classification, split, merge and undo |
| Reports → Adviser tools | Adviser questions and annual handover |

Needs attention contains failed document reads, expenses awaiting review, ambiguous bank matches, changed/missing linked bank records, work/business drives missing a purpose, annual evidence checks, open adviser questions and failed sign-in alerts. Normal inbox drafts, ordinary unmatched transactions, valid classified drives and optional payslip comparisons stay in their own sections.

Clear one-to-one expense/bank matches link automatically when a receipt is filed or a bank sync completes. Amounts must match, merchants must agree and dates must be within three days. Ambiguous, ignored, pending, transfer, foreign-currency and explicit cash choices are not automatically linked. More than 2,000 unmatched expenses requires using the account-filtered suggested matching tool. No financial amounts or allocations are changed by linking. The bank page still supports creating an expense when no invoice is available.

## Bank reconciliation

Choose a posted AUD transaction, its match type and allocation amounts. **Preview match** shows the exact changes; **Apply changes** rechecks the bank transaction and every target record in one transaction. Previews expire after 15 minutes. No bank provider records are changed.

- Invoice deposits can be split over multiple issued invoices, including partial payments. Each allocation becomes one invoice payment; unpaid balances cannot be exceeded.
- Payslip deposits link to an existing payment with explicitly recorded net pay. Enter the actual printed net amount in **Payslip checks → Net & YTD** first. No additional income record is created.
- Purchases can be matched in parts against an existing expense. Existing bank links and explicit cash choices are respected.
- Refunds link back to an ordinary purchase and create a negative expense awaiting review. Itemised, vehicle, overnight and equipment refunds need their existing specialist review paths.
- Undo reverses invoice payment records with a reason. For refunds, choose whether to keep an unlinked expense; an edited or reviewed refund is never silently deleted.

Changed or missing source transactions appear in Needs attention. The match screen shows the latest 500 bank transactions/invoices/payments and 1,000 purchases. Existing Bank accounts tools remain available for the full ledger.

## Rules and receipt items

Rules use an exact merchant name, ignoring case and surrounding spaces. Repeated reviewed allocations appear as suggestions; no rule is created or applied automatically. Preview the affected expenses before applying. Applying marks them for review. Undo is available while the affected records still match the saved result, preventing later edits from being overwritten.

Itemisation keeps one expense, one payment and one original. Each line has an amount, category and employment/business percentages. Lines must total the payment exactly. Budgets, category reports, exports and allocation calculations use the individual lines. Clear the breakdown before changing its parent amount or allocation through an older client. Trip, vehicle, explicitly classified home-office and registered equipment purchases use their specialist treatment rather than itemisation.

## Document evidence and payslip checks

**Check extracted evidence** highlights literal text matches in PDF originals. A match is not a confidence score: check its label and whether it is current pay or YTD. Repeated amounts may have multiple matches. The bounded text preview examines up to 20 pages and 20,000 words. Image-only documents retain the original preview without invented coordinates.

Import checks the extracted figures for one document. Optional payslip checks compare records: they report gaps between recorded pay periods, overlapping periods, and missing period dates. Gaps may represent leave or employment breaks. Explicit YTD figures are compared with payments through the same date. An annual statement entered here is a reference comparison, never an extra income payment. Employer matching ignores case and surrounding spaces; review employer name changes manually.

## Drives, equipment and adviser handover

Daily drive review supports bulk classification, merge, split and undo. Merges require matching vehicle, day, timezone, purpose and use, preserving recorded and estimated route sections separately. Distances are summed without inventing travel across gaps. Splits require an explicit location/distance, a timestamp for timed drives and a recorded-point boundary where available. Drives containing estimated sections must be split in the recording app or kept whole because the server cannot assign those sections reliably. Original records remain in change history; uploaded client IDs stay acknowledged to prevent repeat uploads.

Equipment records retain original cost, use, linked purchase, annual depreciation and disposal details. Annual depreciation amounts and their basis are entered explicitly; the app does not select a tax method or effective life. The linked purchase remains in spending but is excluded from ordinary forecast deductions. Confirmed annual depreciation enters the forecast once, without annualising it; existing annual overrides take precedence. Carrying values reflect entered depreciation, including drafts. Disposal proceeds and balancing tax adjustments require adviser review and are not automatically posted as income.

Adviser questions link to an expense, pay record, receipt, supporting document, drive, asset or invoice. Read-only tax agents may ask, answer and resolve questions, but cannot modify financial records.

The annual ZIP includes a branded PDF summary, CSV registers, outstanding items, adviser questions, linked receipt originals, supporting documents and SHA-256 manifest. Supporting documents with no year, unfiled inbox originals and older equipment evidence are included for review. The export snapshots and pins evidence before building the archive, and stops if an original is missing or fails its stored checksum. The original-file limit is 1 GB. It contains no session key or connection credentials.

Needs attention covers records already received by the server. Check the phone separately for unsent uploads.

## Sign-in email alerts

Settings → Security shows active browser/app sessions and recent successful sign-ins. New-IP emails are enabled by default for each account and use existing Business & email SMTP settings. No email can be delivered until SMTP is configured. The owner and each tax agent receive only their own account alerts.

Only completed successful sign-ins enrol an address; failed passwords and unfinished two-factor challenges do not. Requests use the existing trusted-proxy address handling, never an arbitrary forwarded header. Addresses not seen for 180 days count as new. Alerts include UTC time, IP and device/browser, coalesced to at most one email per hour. Mobile networks and VPNs commonly change addresses. Uncertain deliveries are not automatically resent; failures remain in sign-in history. Pending alerts expire after 24 hours. Passwords, tokens and authentication codes are never put in the email.

## Backups and retired email intake

Beta.12 removes IMAP document intake and the encrypted external backup service, settings and API. Uploaded originals and adviser questions remain available. Configure external appdata backups on the Unraid host; Expense Pilot's existing local verified backups and owner backup downloads remain available. No background job accesses the retired mailbox or external mount. Existing migration tables are retained for upgrade compatibility.

Previously generated beta.11 encrypted archives can still be recovered offline using the saved recovery key:

```sh
python server/offsite_backup.py /path/to/copy.epb /private/recovered.zip
python server/restore_backup.py /private/recovered.zip --data /empty/expense-pilot-data
```

Inside Docker these scripts are in `/app`. Decryption refuses to overwrite an existing file and removes incomplete output on authentication failure. Preserve your data volume and saved recovery key until recovery is verified. Downgrading the app requires restoring the older version's backup into a separate volume.
