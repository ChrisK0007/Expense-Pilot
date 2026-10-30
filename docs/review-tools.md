# Review tools (beta)

Beta 1.0.6-beta.11 adds **Needs attention** and **Review tools** to the web app. Existing iPhone API version 1 remains supported; this release does not contain a new iPhone build. Use the web app for these new workflows.

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

Payslip checks report gaps between recorded pay periods, overlapping periods, and missing period dates. Gaps may represent leave or employment breaks. Explicit YTD figures are compared with payments through the same date. An annual statement entered here is a reference comparison, never an extra income payment. Employer matching ignores case and surrounding spaces; review employer name changes manually.

## Drives, equipment and adviser handover

Daily drive review supports bulk classification, merge, split and undo. Merges require matching vehicle, day, timezone, purpose and use, preserving recorded and estimated route sections separately. Distances are summed without inventing travel across gaps. Splits require an explicit location/distance, a timestamp for timed drives and a recorded-point boundary where available. Drives containing estimated sections must be split in the recording app or kept whole because the server cannot assign those sections reliably. Original records remain in change history; uploaded client IDs stay acknowledged to prevent repeat uploads.

Equipment records retain original cost, use, linked purchase, annual depreciation and disposal details. Annual depreciation amounts and their basis are entered explicitly; the app does not select a tax method or effective life. The linked purchase remains in spending but is excluded from ordinary forecast deductions. Confirmed annual depreciation enters the forecast once, without annualising it; existing annual overrides take precedence. Carrying values reflect entered depreciation, including drafts. Disposal proceeds and balancing tax adjustments require adviser review and are not automatically posted as income.

Adviser questions link to an expense, pay record, receipt, supporting document, drive, asset or invoice. Read-only tax agents may ask, answer and resolve questions, but cannot modify financial records.

The annual ZIP includes a branded PDF summary, CSV registers, outstanding items, adviser questions, linked receipt originals, supporting documents and SHA-256 manifest. Supporting documents with no year, unfiled inbox originals and older equipment evidence are included for review. The export snapshots and pins evidence before building the archive, and stops if an original is missing or fails its stored checksum. The original-file limit is 1 GB. It contains no session key or connection credentials.

Needs attention covers records already received by the server. Check the phone separately for unsent uploads.

## Email intake

In **Review tools → Mail & backup**, configure an IMAP TLS host, port, username, app password, dedicated folder and exact sender allow-list. Enable intake explicitly. The background service checks every five minutes, reading up to 20 unprocessed messages per pass, at most 12 MB per message and 10 MB per attachment. Supported originals are PDF, JPEG, PNG and WebP. Attachments are validated and deduplicated by content hash within the workspace; the original bytes are kept.

Messages are opened read-only using BODY.PEEK, never moved, deleted or marked read. Sender addresses are an intake filter, not proof of authenticity. Attachments become inbox drafts; email content cannot approve or post financial records. Failed messages remain visible in the intake history and can be uploaded manually. Credentials are encrypted using the installation secret. The host must be reachable from the server.

## Sign-in email alerts

Settings → Security shows active browser/app sessions and recent successful sign-ins. New-IP emails are enabled by default for each account and use existing Business & email SMTP settings. No email can be delivered until SMTP is configured. The owner and each tax agent receive only their own account alerts.

Only completed successful sign-ins enrol an address; failed passwords and unfinished two-factor challenges do not. Requests use the existing trusted-proxy address handling, never an arbitrary forwarded header. Addresses not seen for 180 days count as new. Alerts include UTC time, IP and device/browser, coalesced to at most one email per hour. Mobile networks and VPNs commonly change addresses. Uncertain deliveries are not automatically resent; failures remain in sign-in history. Pending alerts expire after 24 hours. Passwords, tokens and authentication codes are never put in the email.

## Encrypted copies and restore tests

Configure `OFFSITE_BACKUP_DIR` as an absolute container path outside `/data`, mounted from another machine or storage service. The destination must already exist and be writable by the container user. A local directory on the same server does not protect against loss of that server; Expense Pilot cannot verify the physical location of a mount.

For example, add this to your deployment's Compose service (replace the host path with your externally mounted destination):

```yaml
environment:
  OFFSITE_BACKUP_DIR: /external-backups
volumes:
  - /mnt/external-storage/expense-pilot:/external-backups
```

In Mail & backup, create/show the recovery key after re-entering your password and second factor where enabled. Save the key outside this server, then enable copies. Encryption uses a separate random AES-256-GCM key, an authenticated format header and a fresh nonce for every archive. The server stores the recovery key encrypted with its installation secret. Seven verified encrypted copies are retained; older copies are removed only after a new copy passes an actual isolated restore. The existing local backup schedule remains independent.

**Create copy now** and **Test latest restore** queue background work. Restore testing decrypts the stored copy, checks all checksums, restores into a temporary directory, verifies database links and confirms sessions are revoked. It never installs the test restore into the live workspace. Check the last-copy, last-test and error messages after the worker completes.

To recover on a compatible application image, decrypt to a private ZIP, supplying the saved key at the prompt, then run the existing restore command against an empty destination:

```sh
python server/offsite_backup.py /path/to/copy.epb /private/recovered.zip
python server/restore_backup.py /private/recovered.zip --data /empty/expense-pilot-data
```

Inside the Docker image the scripts are in `/app` rather than `server/`. Preserve your original data volume until recovery is checked. Keep the decrypted ZIP private and remove it when no longer needed. This beta adds migration m023; reverting to an older image requires restoring its pre-upgrade backup into a separate volume.
