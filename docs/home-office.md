# Fixed-rate home office in the beta

Open **Tracking → Home office** and choose the financial year. Home office supports the fixed-rate method only.

1. **Log hours:** choose Employment or Business, describe the work, record start/finish times and subtract breaks. Times use your workspace timezone. Split work crossing midnight into two dates; `24:00` closes the first day. Overlapping sessions across either workspace are rejected.
2. **Bills & receipts:** use **Add bill evidence** to attach a bill or receipt and enter its supplier, date, amount and cost type. No work-use percentages are needed. Confirm you personally incurred the cost and it was not reimbursed. If the bill is already in Expenses, use **Link a bill** instead of adding it again. Confirm automatically identified Phone & internet bills before using them as evidence.
3. **Set up claim:** enable the fixed-rate claim, review the eligibility/hours/bills confirmations and select the running-cost types you personally incurred. Keep at least one bill or receipt for each selected type. Save now and finish missing checks later. **Pending** means no home-office deduction is included yet; **Included in tax forecast** means the record checks are complete.
4. **Allowances** is optional. Leave “Already included in gross pay” checked when your Employment income includes the allowance. Otherwise it is added once. An annual salary override replaces the complete recorded salary total.
5. **Download logbook PDF** creates a financial-year report with a summary, monthly employment/business totals, hours diary, breaks, work notes, logged/updated timestamps and bill checklist. **Export CSV** retains the detailed calculations, allowances and full relevant edit history. Full backups also retain receipt originals.

## Bill evidence and the deduction

The ATO fixed rate is 67c for FY 2022–23 and 2023–24, and 70c from 1 July 2024 under [PCG 2023/1](https://www.ato.gov.au/law/view/document?DocID=COG/PCG20231/NAT/ATO/00001). Reviewed rates are enabled through FY 2026–27; later years need a rule update.

The rate covers energy, phone usage, internet, stationery and computer consumables, including work phone use away from home. Your recorded hours determine the deduction, not a percentage of these bills. Classify covered bills already recorded in Expenses so they are excluded from separate forecast deductions.

**Add bill evidence** saves the full bill as a personal/unallocated expense (0% employment and 0% business), with a note that it supports fixed-rate hours. It still counts as evidence. Linking an existing expense does not change its amount or percentages. Ordinary spending reports retain those original allocations; the tax forecast applies the fixed-rate adjustment once.

Separate deductions outside the hourly rate, such as eligible equipment depreciation, still need their own evidence and use calculation. Their assessment fields appear only when a non-covered cost type is selected. Equipment/occupancy require an explicitly assessed annual amount and confirmation; purchase cost is not automatically the deduction. The beta does not calculate depreciation schedules, GST credits or BAS.

Log sessions as they occur. Creation/update timestamps remain in the diary and PDF; entering old hours later does not establish contemporaneous evidence. Figures are deduction estimates, not refunds or a lodged return.

## Existing records and updates

The fixed-rate-only calculation change keeps all hours, bills, allowances and history. This beta also adds migration m021 for the Documents repository; the twenty earlier migrations are unchanged. A year previously set to actual costs is held pending until you review and save the fixed-rate claim checks. Its stored old settings remain unchanged until then and are retained in edit history when replaced.

Turning off the fixed-rate claim restores ordinary expense treatment; review the forecast after doing so. New evidence-only bills remain unallocated. Back up before updating, keep the same data mount, and refresh the browser afterwards.

## Mileage reports

Open **Tracking → Vehicles → Download mileage PDF**. Choose one vehicle, start/end dates and the journey workspace (or all workspaces). The page's text search is not applied to the report. Leave the reimbursement rate blank for a distance-only report, or enter the agreed AUD rate per kilometre.

The PDF includes a summary by employment, business and personal use, then monthly journey details. Employment/business distances use the saved journey use percentage; the remainder is personal. Reimbursement estimates use those allocated kilometres and are rounded per journey. They do not set an ATO tax rate, apply annual kilometre limits or change the tax forecast.

Only recorded journey odometer readings are printed. Missing readings are labelled **Not recorded** rather than inferred from GPS. Only journeys already uploaded to the server are included. Existing journey CSV export remains available.


## Importing existing hours

Choose **Home office → Import hours**. Select a WFH Logbook Australia PDF or an Expense Pilot diary CSV and confirm the session timezone. PDF uploads support text-based reports up to 10 MB and 500 pages; CSV uploads support UTF-8 files up to 2 MB. Imports accept up to 1,000 sessions. Scanned PDFs and other PDF layouts are not supported. The parser checks the PDF's session total against its reported hours; money in the report is ignored.

Review the sessions, choose Employment or Business (individually or using Apply), and enter any missing work descriptions. Dates, times, breaks and timezones can be corrected before saving. Repeated daylight-saving times need an occurrence selection. Select only the correct sessions and tick the review confirmation. No hours or source document are stored during preview.

Existing sessions and previously deleted rows from the same import are skipped, including a retry after a lost response. Overlaps with saved or selected sessions reject the whole selected batch. Import does not overwrite existing sessions or restore deleted imports. Review and edit existing hours from the diary instead.

The original report is saved in Documents and linked from imported sessions. Its original dates, times, notes and logged/updated timestamps remain in import history and the full CSV history export. PDF logbooks include an imported-source section. Expense Pilot records the actual import date as the diary creation date; original report timestamps are evidence from that source, not independently verified dates. PDF source timestamp timezones are unspecified; Expense Pilot CSV source timestamps are UTC. Deleting the source document later removes its file but retains the import history.

The import does not enable the fixed-rate claim or tick any claim confirmations. Existing claim settings are unchanged; review them separately when your records change. Importing older records does not itself establish that they were kept contemporaneously.
