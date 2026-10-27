# Home office in the beta

Open **Tracking → Home office** and choose the financial year.

1. Use **Log hours** for actual home-working sessions. Choose Employment or Business, record the activity and start/finish times, and subtract breaks. Times use your workspace timezone. Split work crossing midnight into two dates; `24:00` closes the first day. The diary rejects overlaps across both workspaces.
2. Keep bills and receipts in **Expenses**, with the correct employment/business percentages and reimbursement status. Use **Link a bill** to confirm each cost type and explain the work/private calculation. Automatic Phone & internet detection prevents double counting, but you must confirm the bill type before it counts as evidence.
3. Open **Annual method & records** to choose fixed rate or actual costs and review the evidence confirmations. The choice covers both workspaces for that year. The comparison shows estimates; only a complete selected method enters the recorded tax forecast.
4. Record any **Employer allowances**. Leave “Already included in gross pay” checked when your Employment income total already includes the allowance. Otherwise the allowance is added once. An annual salary override replaces the complete recorded salary total.
5. Download **Home-office CSV** for your tax agent. It includes the diary, original bills, assessed amounts, forecast treatment, allowances and edit history. A full application backup also retains the records and receipt files.

## Calculation and evidence

The ATO fixed rate is 67c for FY 2022–23 and 2023–24, and 70c from 1 July 2024 under [PCG 2023/1](https://www.ato.gov.au/law/view/document?DocID=COG/PCG20231/NAT/ATO/00001). This beta enables reviewed rates through FY 2026–27. Later years need a rule update.

The fixed rate covers energy, phone usage, internet, stationery and computer consumables, including work phone use away from home. Keep actual hours and a bill for each cost type incurred. The application retains when diary entries were created/changed; entering old hours now does not itself establish contemporaneous records.

Actual costs need evidence and reasonable apportionment. Equipment/depreciation and occupancy require an explicitly assessed annual amount; purchase cost is not automatically the deduction. Occupancy eligibility, personal services income and potential CGT effects need review. Reimbursements are excluded. Keep separately evidenced portions for partly reimbursed bills.

The optional [employee standard-deduction comparison](https://www.ato.gov.au/individuals-and-families/income-deductions-offsets-and-records/deductions-you-can-claim/work-related-deductions/standard-deduction-for-work-related-expenses) is indicative and stays outside the forecast. Relevant deductions already claimed reduce the remaining amount; eligibility and income limits still need checking. It is not added to itemised deductions automatically.

These are deduction estimates, not refunds or a lodged return. The beta does not calculate depreciation schedules, GST credits or BAS. Original spending reports retain the original allocations; use the home-office export to review the adjustments. Changing the annual method to “Not selected” restores ordinary expense treatment, so review the forecast after changing it.

## Updating and restoring

Back up before installing this beta. Migration m020 adds five tables and retains existing records. Keep the pre-update backup: an older application image rejects the new migration and requires restoration of its matching backup to roll back.

## Finding your records

The overview shows hours recorded and the deduction actually included in the forecast. **Not set up** means no method is selected; **Pending** means the selected method still needs checks or evidence. Potential comparison figures are kept under **Claim → Compare fixed rate and actual costs**.

- **Hours:** log and edit actual sessions, separately for employment and business.
- **Bills & receipts:** link existing expenses, confirm automatically identified phone/internet bills and record their use.
- **Claim:** see outstanding checks, compare methods and open detailed tax guidance. **Set up claim / Review claim settings** shows only confirmations relevant to the selected method.
- **Allowances:** optional employer payments, with an explicit gross-pay inclusion choice.

Your last view is remembered in the current browser tab. Financial-year selection, CSV export and edit history remain available above the records. Tax forecast also shows a short method/status note, with the calculation explanation expandable underneath. Calculations and evidence requirements are unchanged.
