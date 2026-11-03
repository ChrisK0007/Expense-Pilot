# Equipment calculations

Open **Expenses → Equipment**. Link an existing standalone purchase to retain its receipt and avoid double deductions. Original spending remains visible; the capital purchase is excluded from ordinary forecast deductions. Existing manual records are unchanged on upgrade.

Choose **Add equipment**, select an existing purchase if available, and check the name, date, original cost and employment/business percentages. Choose **Suggest a deduction**, **Already fully claimed**, or **Let my accountant finish**. Suggestions reuse the purchase details and annual tax settings; supported tablets/laptops get a two-year useful-life suggestion which can be changed. Other assets need a useful life where relevant. The app never treats a low business-use percentage as reducing an asset’s cost below an immediate-deduction threshold.

Cards show this year's allocated deduction and remaining value. Methods, rates, history, disposal and calculation controls are under **Advanced details**. First use defaults to acquisition, income use defaults to first use, and GST credit defaults to zero; change the relevant details if these defaults do not fit the purchase. Estimates remain labelled for accountant review. **Let my accountant finish** saves the asset without including an equipment deduction in the forecast until an annual amount or calculation is saved.

**Already fully claimed** records a completed claim in the chosen financial year, leaving zero remaining and no future depreciation. For an asset acquired in that year, the original tax cost supplies the amount. For an older asset, enter its remaining value before that year's write-off; the app does not recreate earlier claims. Use this to record an established treatment, not to decide eligibility for a new claim.

| Method | Supported treatment |
| --- | --- |
| Prime cost | GST-adjusted original cost × days ÷ 365 ÷ effective life, capped at remaining value |
| Diminishing value | Opening value × days ÷ 365 × 200% ÷ effective life; acquisition from 10 May 2006 |
| Employee immediate deduction | Cost ≤ $300, mainly non-business income use, eligible asset and set/identical-item restrictions confirmed |
| Small-business instant write-off | Cost < $20,000 in FY 2024–25 onward; permanent from 1 July 2026 under current law; eligibility and election to simplified depreciation confirmed |
| Manual | Reviewed annual amounts with calculation notes |

Days include leap days while the statutory denominator remains 365. Calculations use decimal arithmetic and annual rounding to cents. GST credit entitlement reduces the cost basis. Decline before income use consumes carrying value but is excluded from the deductible portion. Employment and business percentages apportion only the income-use amount; the remainder is personal.

Automatic estimates enter the forecast once and are labelled separately from recorded/confirmed deductions. Annual forecast overrides still take precedence. Save a reasoned annual override to confirm or correct a figure. Draft annual amounts reserve carrying value but do not enter the forecast. Confirmed years retain their use percentages even when later usage changes. New percentages carry forward from the chosen year. Confirmed history locks automatic setup; annual overrides remain available. Enabling automatic calculation over existing history requires acknowledgement and rejects inconsistent carrying values.

Disposal stops the schedule and flags the disposal year for review. Balancing adjustments and proceeds are not posted as income automatically. Pooling, capital works, pre-10 May 2006 diminishing value, unusual assets, changed use after an immediate deduction and unsupported immediate-deduction years require manual tax treatment. Registration does not itself establish deductibility. No automatic tax return is lodged.

Rules reviewed 31 October 2026; new calculation records store ruleset `AU-equipment-2026-10-31` (existing saved setups retain their recorded ruleset). Sources:

- [ATO: employee assets costing $300 or less](https://www.ato.gov.au/api/public/content/0-29b19571-b460-44af-8299-781b30ff7fb7)
- [ATO: small-business instant asset write-off](https://community.ato.gov.au/s/article/a07Mo00002BaUJ6IAN/can-my-small-business-claim-the-20000-instant-asset-writeoff)
- [ATO: assets used for non-business income](https://smallbusiness.taxsuperandyou.gov.au/depreciation/assets-used-to-earn-non-business-income)
- [ATO: GST and depreciation](https://smallbusiness.taxsuperandyou.gov.au/depreciation/gst)
- [ATO: cost of an asset](https://smallbusiness.taxsuperandyou.gov.au/depreciation/cost-of-an-asset)
- [Income Tax Assessment Act 1997, Division 40](https://www.legislation.gov.au/C2004A05138/2026-04-01/2026-04-01/text/original/epub/OEBPS/document_2/document_2.html)
- [Income Tax Assessment (Effective Life of Depreciating Assets) Determination 2025, Table B](https://www.legislation.gov.au/F2025L01097/asmade/2025-09-15/text/original/epub/OEBPS/document_1/document_1.html)

## Suggestions while reviewing a purchase

In **Add/Edit expense** or **Document inbox → Review receipt**, use **Tax treatment → Check deduction**. Receipt reading retains actual item names in the notes; item keywords and the Equipment category flag possible equipment. AI does not determine eligibility, tax rules or effective life. Enter the actual item and check the suggested treatment. The standard purchase choice describes ordinary equipment owned and used to earn income; prior private use and unusual assets can be selected under Advanced details. The description “hearing protection” alone does not establish deductibility or approved PPE.

**Annual tax settings** saves the owner’s general/simplified depreciation choice per financial year. The simplified option explains sole-trader ownership, carrying on a business, aggregated turnover under $10 million and application of the whole regime to eligible assets; saving that choice records the election without four separate checkboxes. This can include employment assets. Settings are not inferred from one receipt, copied into another year or used to rewrite existing asset setups. A changed election may require review of existing records.

The full cost is tested before applying use percentages. A $500 asset used 50% for employment and 25% for business fails the employee $300 test. Under the general rules it needs depreciation or another reviewed treatment; under eligible simplified depreciation its combined taxable portion may qualify for a $375 immediate deduction (assuming no GST credit). Exactly $20,000 fails the business threshold. Exactly 50% employment use is not mainly non-business income use. Pools, prior private use, special assets and uncertain eligibility stay for review. Effective life is confirmed by the owner; only tablets/laptops get the documented two-year suggestion.

After opening Check deduction, **Use this deduction when saving** is selected; clear it to save without applying the suggestion. The backend recalculates the decision, checks the current annual settings and matched payment, and creates the linked asset in the same transaction. Failure rolls back both records. The purchase stays in spending, but its equipment treatment replaces ordinary deductions so it is counted once. Existing phone API clients continue working unchanged.

## Importing an accountant’s schedule

Use **Expenses → Equipment → Import schedule**. PDF, PNG, JPG, WebP and the provided CSV template are supported, up to 10 MB, 6 PDF pages and 60 assets. CSV is read locally; PDF/image extraction uses the configured AI provider and existing consent settings. Reading runs in the background. The original is saved in Documents before reading starts; failed or interrupted jobs can be retried from Saved imports. No assets are created by extraction alone.

Review the financial year and each asset's deduction/remaining-value summary. Source figures are under Advanced details, opened automatically when balances need attention. Saving the selected rows confirms their AUD figures; there are no separate general confirmation checkboxes. Amounts must be tax balances net of applicable GST credits, before use apportionment. Opening minus decline must equal closing. Rounded accountant figures that do not reconcile need corrected balances. D5 work-related expenses are Employment, even with a generic “Business use” heading. An amount pooled is not proof of a completed write-off. Explicitly choose **Fully claimed this year** for an established completed write-off; a new purchase uses its cost, while an older asset needs its known opening value.

On confirmation, all selected rows import atomically. A single eligible matching purchase is selected automatically and displayed for review; it must have the same date, cost and use percentages to prevent an ordinary expense claim as well as depreciation. If leaving a matching purchase separate, explicitly confirm that it is a different purchase. Original costs remain intact, the report year is a confirmed annual override, and PC/DV future estimates use its closing value and reviewed printed rate. Earlier years are not invented or deducted. Zero-balance written-off assets remain recorded without future claims. Manual/pool rows require annual review. Imported setup and report-year figures are fixed; future annual overrides and usage changes are supported. To correct a source row, remove that asset (and any later annual overrides), read the saved schedule again, and select only the corrected assets. Exact file duplicates reuse the original; existing matching name/date/cost assets are rejected instead of duplicated. Match equivalent assets with different names manually before import.

Import originals supporting existing assets are retained as evidence. Failed or abandoned imports, or imports whose asset records have all been removed, can be deleted through Documents. An in-progress reader discards its result if its original was removed. Tax agents see relevant imported balances only for shared years from the import year onward. Share the source schedule explicitly under Settings → Tax agent access if they need the original; it may contain unrelated assets.

## Adding a receipt later

On an existing equipment card, choose **Link receipt** to select a saved original or upload a PDF/image. One purchase receipt can be attached, alongside an imported schedule if present. The receipt does not change the asset's cost, annual amounts or history and is removed from the unfiled inbox. Under **Link an existing expense**, choose a matching purchase to replace its ordinary deduction with the equipment treatment. Itemised, reimbursed, specialist or already-linked purchases are not eligible.

**Manage receipt → Unlink receipt** returns the original to Document inbox; the deduction and any linked purchase remain intact. Receipt links are owner-only. Tax agents can view relevant originals only for the financial years shared with them, and annual handovers include the supporting original. A failed upload-link leaves the saved original available in Document inbox.

Additional sources:

- [ATO: applying the entire simplified depreciation regime](https://smallbusiness.taxsuperandyou.gov.au/depreciation/using-simplified-depreciation-rules)
- [Treasury Laws Amendment (Tax Reform No. 2) Act 2026, Schedule 2](https://www.legislation.gov.au/C2026A00071/asmade/2026-08-26/text/original/pdf)
- [ATO: records of depreciating assets](https://smallbusiness.taxsuperandyou.gov.au/record-keeping/records-of-depreciating-assets)


## Automatic purchase suggestions (beta 19)

A new equipment purchase can be saved with one suggested treatment. The purchase date is the first-use default, and the expense's employment/business percentages are reused. The default method is diminishing value. Useful-life defaults are planning estimates: portable computers 2 years, phones and headsets 3, computers/monitors 4, and other equipment 5. Except for the previously documented portable-computer preset, these labels do not assert an ATO-determined effective life. The calculation stores its assumptions and `needs_accountant_review` metadata. **Adjust deduction** exposes life, dates, GST credit, method and set/identical-item considerations.

Unknown annual tax elections use general depreciation as a conservative planning fallback. The app never infers eligibility for the small-business simplified regime from price or business-use percentage. An owner can choose the eligible regime once per year. Full asset cost is assessed before use percentages, so a $500 asset does not become an employee immediate deduction because its employment portion is $250. Labels such as “hearing protection” do not establish deductibility or protective-equipment certification.

Previously private assets, special assets and unsupported pooling are saved for accountant review without an automatic claim. Ordinary repairs, subscriptions and rent are not treated as equipment merely because their descriptions mention a device. Linked capital purchases are excluded from ordinary expense deductions; the generated estimate supplies the forecast once. Historical imported and manually saved years retain their existing values.
