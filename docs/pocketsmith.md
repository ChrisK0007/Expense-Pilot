# PocketSmith bank feeds

Available in stable Expense Pilot **1.0.2** and the beta channel. First included in stable v1.0.1.

## Connect

1. Update within your chosen channel: beta uses `ghcr.io/chrisk0007/expense-pilot:beta` (or pin `:1.0.4-beta.2`); stable uses `:latest` (or `:1.0.4`). Keep that instance’s own `/data` directory and back it up first. Do not downgrade to an older database schema by changing only the image tag; restore a matching backup and image for rollback.
2. Connect your banks and check their transactions in [PocketSmith](https://my.pocketsmith.com/). Your PocketSmith account needs access to the feeds you want to use.
3. In PocketSmith, open **Settings → Security** and create a developer key for this installation.
4. Sign in as the Expense Pilot owner, open **Settings → Bank feeds → Configure PocketSmith**, enter the key and select **Connect PocketSmith**.
5. Select the accounts to import. For each, choose an existing Expense Pilot account label or create a new one. If you have already imported CSVs for that account, select that same label so existing expenses can be suggested. Saved account mappings are fixed to avoid moving historical records between accounts.
6. Choose the first transaction date and optionally enable hourly sync. Save, then open **Tracking → Bank accounts → Sync now**.

Only the owner can manage the connection and run a sync. Tax agents can see the bank review queue; those with read/write permission can match and categorise transactions.

The developer key is encrypted in the database using the installation's `session.key`. It is never returned to the browser after saving. Expense Pilot only makes GET requests to PocketSmith. Use HTTPS when accessing your instance remotely; do not paste keys into support messages. Each separate Expense Pilot instance should use its own connection key. Disconnect removes the saved key and stops syncing, while preserving imported history and expenses; revoke the developer key in PocketSmith as well if it is no longer needed.

## Review transactions

The bank queue is separate from expenses. Syncing does not automatically create expenses or affect deductions.

- **Match an existing expense:** review suggestions with the same AUD amount, within three days and in the same or an unassigned account. Open the expense to compare its receipt and details, then choose **Match this expense**. An unassigned expense receives the mapped account label; its amount and allocations stay intact.
- **Create expense:** posted purchases can open the regular expense form with date, payee, amount and bank account filled in. They start as Personal / To review with zero business or employment allocation. Add the receipt and set the relevant allocation before saving.
- **Record expense refund:** a posted credit requires explicit confirmation that it refunds an expense. It becomes a negative expense. Salary, invoice receipts and transfers should be ignored in this queue and recorded in their appropriate areas.
- **Pending:** wait for the posted transaction. PocketSmith can replace a pending transaction with a different transaction ID.
- **Transfers:** PocketSmith-marked transfers cannot be added as expenses. If a transaction is incorrectly marked, correct it in PocketSmith and sync again. Unmarked transfers require your review.
- **Foreign currency:** the original bank currency and amount are preserved. Enter the converted AUD expense amount yourself. Existing-expense suggestions currently support AUD accounts only.
- **Ignore / restore:** retain source history without creating an expense. Deleting a linked expense also leaves its bank transaction ignored, so a later sync does not recreate the expense. Restore it explicitly if needed.

PocketSmith categories are shown for reference. They do not determine expense categories, business purpose or deductible allocation. A bank feed is not a substitute for a receipt.

## Sync behaviour and troubleshooting

Hourly sync reads transactions already available through PocketSmith's API; it does not force PocketSmith to refresh its upstream bank feeds. Automatic sync runs only while the container is running and checks for due work every minute. The owner can also use **Sync now**, then **Refresh view** to see updated status.

Each sync fetches the selected accounts from the configured start date through today. Stable PocketSmith transaction IDs prevent duplicate ledger rows. Nothing is committed until all selected accounts and pages have been fetched and validated. If you change accounts or disconnect during a sync, that older sync cannot save its results.

A linked transaction whose date, payee, amount, account, currency, pending status or transfer classification changes is flagged **Source changed**. Your expense stays unchanged. Open the linked expense to compare it, edit it if appropriate, and acknowledge the change. A transaction omitted from a complete sync is marked **Not returned**; it may have been removed or replaced upstream. Linked expenses are retained.

- **Unsupported transaction status on beta.2/beta.3:** update within your channel to stable v1.0.2 or the current beta and run Sync now after any displayed retry time. Older versions incorrectly used this error for a null transfer marker, even on a posted transaction. Unset markers now use the category transfer flag when supplied, otherwise remain unmarked. Explicit true/false transaction markers take precedence. Pending transactions and transfers remain blocked from expense creation, and genuinely invalid statuses or transfer flags still stop the sync without changing previous imports. No reconnection or new developer key is needed.
- **Access denied:** replace the key in connection settings and refresh the account list.
- **Unavailable account:** refresh accounts in settings, check PocketSmith, and deselect accounts you no longer want synced.
- **Rate limit / connection error:** the previous successful import is retained. Settings show the error and retry time. Automatic sync retries after the delay; repeated manual requests respect the same delay.
- **Too much history / slow sync:** choose a later start date or fewer accounts. A sync is bounded to 50 pages per account, 50,000 transactions across accounts and roughly a minute of API requests.
- **Duplicate-looking expenses:** review suggestions before creating a new expense. Matching is explicit; two genuine purchases with different source IDs are not collapsed just because their amount and payee are identical.

This release is validated with simulated PocketSmith responses and browser workflows. A live bank connection still needs to be verified with your own account after setup.

API references: [authentication](https://developers.pocketsmith.com/docs/introduction), [API reference](https://developers.pocketsmith.com/reference), [official OpenAPI specification](https://github.com/pocketsmith/api/blob/master/openapi.json).
