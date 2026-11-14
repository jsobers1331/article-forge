# Household Bill Spreadsheet Template: Due, Paid, and Shared

Last updated: November 13, 2026

A household bill spreadsheet template is a plain, editable starting file for tracking recurring bills by hand. The downloadable file provided here is a UTF-8 CSV containing only column headers—no formulas, macros, automatic reminders, or sample data. You open it in your preferred spreadsheet app, copy the header row into a workbook, and add one row per bill occurrence as it happens. This approach works best for households with a modest number of bills and a preference for reviewing each charge manually. 

Download the template here: [household-bill-spreadsheet-template.csv](/downloads/household-bill-spreadsheet-template.csv)

## What the File Actually Contains

The downloadable file is a CSV with one header row and no data rows. The columns are:

| Column                  | Purpose                                                                 |
|-------------------------|------------------------------------------------------------------------|
| `bill`                  | Name of the recurring bill, such as rent or electricity                 |
| `due_date`              | Date the bill is due                                                    |
| `expected_amount`       | Amount you expect before the bill arrives                               |
| `actual_amount`         | Amount on the final bill                                                |
| `currency`              | Currency code for that row, such as USD or EUR                          |
| `payer`                 | Person or account responsible for paying                                |
| `status`                | Where the bill stands, such as pending or paid                          |
| `paid_date`             | Date the payment was confirmed                                          |
| `confirmation_reference`| Reference number or note from the payment confirmation                  |
| `shared_split_note`     | Optional note about how the bill is split, if it is shared              |

The file contains only these headers. It does not include sample rows, formulas, conditional formatting, or reminder logic. You add your own records. The downloadable file is already UTF-8 encoded, so it should open correctly in Excel, Google Sheets, LibreOffice, Apple Numbers, or any text editor. If your spreadsheet app asks about encoding, choose UTF-8.


## Setting Up Your Bill Spreadsheet

This template is a starting point for your own records. Here is a straightforward process to set up your household bill spreadsheet:

1. **Download the CSV** and open it in your preferred spreadsheet app.
2. **Create a new sheet** for your master recurring schedule. Copy the header row into that sheet.
3. **List each recurring bill once** in the master schedule. Use the `bill`, `due_date`, `expected_amount`, `currency`, and `payer` columns. Leave `actual_amount`, `status`, `paid_date`, and `confirmation_reference` blank on the master schedule.
4. **Create a second sheet** for actual occurrences. Copy the header row again.
5. **Each month, copy the master rows forward** into the occurrence sheet. Do not copy the `status`, `paid_date`, or `confirmation_reference` values from a previous month. Those are per-occurrence fields and should start blank each cycle.
6. **Update each row as the bill moves** from expected to pending to paid. Enter the actual amount when the bill arrives, mark the status, and record the paid date and confirmation reference once the payment is confirmed.

This separation matters: the master schedule is a reference of what recurs, while the occurrence sheet is a record of what actually happened in a given period. If you copy paid statuses forward, you lose the distinction between a bill you have already handled and one you still need to handle.

## A Qualitative Example: Rent Workflow

Suppose a household tracks rent. The master schedule row might read:

- `bill`: Rent
- `due_date`: first of the month
- `expected_amount`: the amount stated in the lease
- `currency`: the household's local currency
- `payer`: the person who has agreed to make the payment
- `status`: blank on the master schedule

When the month begins, the household copies that row into the occurrence sheet and sets `status` to `pending`. The `expected_amount` remains the lease amount. When the payment is initiated, the household might note `pending transfer` in the status or confirmation field. When the landlord or bank confirms receipt, the household changes `status` to `paid`, enters the `paid_date`, and adds the confirmation reference.

This example is qualitative and illustrative, with no specific amounts or deadlines. The point is the workflow: expected, pending, paid. The same pattern applies to a variable utility bill, where `expected_amount` is an estimate and `actual_amount` is the billed figure. For more on estimating variable bills, see our guide on [how to estimate variable utility bills](/articles/how-to-estimate-variable-utility-bills).

## Where a Spreadsheet Is Most Useful

A manual spreadsheet has real advantages in specific situations. If you have a manageable recurring schedule and want to review each one before paying, a spreadsheet gives you full visibility without handing over bank credentials. You control the columns, the status values, and the history. Nothing updates automatically, which is a feature if you prefer to confirm payments yourself.

A spreadsheet does not enforce or automate currency conversion; you manage this manually. You can record a bill in one currency and a different bill in another, and simply not sum across unlike currencies. Keep the original currency visible even if you later add a separate converted planning total. Our guide to [multi-currency budgeting for couples](/articles/multi-currency-budgeting-app-for-couples) covers that scenario in more depth.

The supplied CSV does not include reminders, validation, or error checks. Add a review schedule and any checks you need in your spreadsheet app, including a check for missing payment confirmations and carried-forward paid statuses. These are process disciplines you maintain yourself.

## Common Mistakes to Avoid

- **Treating a pending transfer as a confirmed payment.** A bank transfer can be initiated before the recipient has accepted or processed it. For this tracker, keep the status pending until you have the confirmation required by your payment method. Keep `pending transfer` and `paid` as separate statuses.
- **Recording a reimbursement as a second expense.** If one person pays a shared bill and another person pays them back, the household's total expense is the bill itself, not the bill plus the reimbursement. Record the bill once. Use the `shared_split_note` column to note the split arrangement, and track reimbursements separately if you need to.
- **Summing amounts in different currencies.** A total that adds USD and EUR rows is not meaningful unless you apply an explicit conversion rate and record the rate and date. If you need a combined view, convert deliberately and document the rate. Otherwise, keep currency totals separate.
- **Copying paid statuses forward.** The master schedule should stay clean. When you copy rows into a new month, reset `status`, `paid_date`, and `confirmation_reference` to blank. Otherwise, a new bill may appear to have been settled already.


## When a Manual-First Bill Tracker May Be Better

A spreadsheet is a reasonable choice when the household is small, the bill count is low, and someone is willing to maintain the file. It becomes less comfortable when bills are numerous, split unevenly across people, or due on many different dates. At that point, a purpose-built manual tracker can handle the same workflow with less upkeep.

HomeWeal is a manual-entry household bill tracker and does not connect to a bank. You enter bills yourself and confirm payments yourself. The Solo plan includes up to 10 bills, a bill calendar, web push bill reminders, variable-amount tracking, and CSV and Excel export. These features and limits apply to the Solo plan as described. The Family plan adds equal, percentage, or fixed-amount bill splitting; income-based percentages are calculated by the household, not by the app. See the [features](/features) page for the full breakdown, or [pricing](/pricing) for current plan details.

If you are deciding between a spreadsheet and a tracker, our guide to [what a household bill tracker is](/articles/what-is-a-household-bill-tracker) explains the category plainly. For a broader look at tracking without bank linking, see [the best bill tracker without bank linking](/articles/best-bill-tracker-without-bank-linking).

## Next Step: Try the Template With One Bill

Download the CSV, open it, and copy the header row into a new sheet. Add one real recurring bill from your own records—rent, electricity, internet, or anything you already pay on a schedule. You do not need to add a full year of history. Run one bill through the expected-pending-paid flow and see whether the columns capture what you need. If they do, add the rest of your recurring schedule. If they do not, adjust the columns before you build further.

For guidance on handling bills that arrive once a year rather than monthly, see [how to budget for annual household bills](/articles/how-to-budget-for-annual-household-bills).

Find related guides in the [HomeWeal article library](/articles).
