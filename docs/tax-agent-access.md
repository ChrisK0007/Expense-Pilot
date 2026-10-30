# Tax-agent access

From 1.0.6-beta.13, agents use a dedicated tax-preparation workspace. Existing agent accounts start with no shared years after migration; owners must choose access under **Settings → Tax agent access → Sharing**. Both Read only and Read & write remain inside the same sharing boundary.

Select only required financial years. Relevant employment income, issued invoices and payments, employment/business expense allocations, equipment basis and earlier depreciation history, WFH evidence, work/business journeys and questions are included. Bills explicitly classified for WFH are supporting tax evidence even when their ordinary allocation is zero. Private journey distances are aggregated for apportionment; private locations and raw GPS routes are excluded.

Choose additional supporting documents individually. Dated documents require a matching shared year. Selected undated documents are available in every shared year. Linked receipts for shared expenses, income and equipment are included automatically; originals can contain personal details on a mixed-use receipt or household bill. Review these originals before sharing.

Agents cannot access unrelated personal spending, bank feeds/accounts, unfiled inbox originals, quotes/draft invoices, client contact management, budgets, SMTP credentials or owner administration. Direct old API/download links are denied. Removing a year or document applies on the next request, including exports. Files already downloaded cannot be recalled.

Read-only agents may ask, answer and resolve questions attached to shared records. Read & write additionally permits classification, use percentages, notes and review state on ordinary expenses, plus annual equipment overrides with reasons. Original amounts/dates, itemised receipts, meals, travel, vehicle and WFH treatments require owner correction. Edits are version checked and audited. No agent can send billing mail or move a record into wholly personal spending.

The agent Reports page exports the same filtered dataset, with PDF summary, CSV registers, JSON and original evidence, plus SHA-256 manifest. The evidence limit is 256 MB. The owner’s complete handover export remains separate.

Use **Disable** for temporary removal of access. Use **Remove account** and enter the agent’s email to permanently remove the login. Sessions and grants are revoked immediately; records, questions and revision history remain. Rare legacy ownership conflicts block deletion instead of dropping financial evidence; resolve those records before retrying.
