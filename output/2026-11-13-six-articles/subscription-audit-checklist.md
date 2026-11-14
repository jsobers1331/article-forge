# Subscription Audit Checklist: Keep, Cancel, or Review

Last updated: November 13, 2026

A subscription audit is a manual review of your recurring charges using records you check yourself—such as email receipts, app store lists, vendor account pages, and statements. You do not upload credentials or let a tool discover charges for you. This checklist is a planning outline to help you decide which subscriptions to keep, cancel, or review, and to plan your next actions. Confirm the renewal and cancellation terms in each vendor account.

If you want a manual-entry tool to track recurring bills after the audit, see [HomeWeal's features](/features) or try the [free audit tool](/tools/subscription-audit). The method below works with any spreadsheet or paper list, keeping you in control of every record. For more on how HomeWeal works, visit [our pricing page](/pricing) or read [what is a household bill tracker](/articles/what-is-a-household-bill-tracker).

## Download the Subscription Audit Checklist

The main resource for this article is a plain CSV file with these headers:

`vendor,payer,billing_cycle,amount,currency,next_renewal_date,notice_deadline,decision,action_owner,cancellation_confirmation,access_end_date`

[Download the subscription audit checklist CSV](/downloads/subscription-audit-checklist.csv)

This CSV is an editable checklist with headers only—no example data, formulas, reminders, macros, or automated imports. You fill in each row from records you review directly. This limitation is intentional: the audit is only as reliable as the source records you actually check.

## What a Subscription Audit Is—and What It Is Not

A subscription audit helps you answer: which recurring charges do I still want, and which should I stop before the next renewal?

It is not a payment history. A bank statement shows money already spent. The audit looks forward to the next renewal date and any required notice deadline.

It is also not an automatic cancellation service. HomeWeal does not connect to your bank, discover unentered charges, or cancel vendors for you. The audit produces a list of decisions and action owners. You still need to contact the vendor, use their cancellation process, or follow the terms in your account.

Key distinctions throughout the audit:

- **Cancel auto-renew**: Check the vendor confirmation for the effective date; a refund request is a separate action.
- **Uninstalling an app**: Removes software from your device, but does not cancel a subscription if billing happens through an app store or vendor account.
- **Subscription inventory**: Lists active recurring commitments. It is not the same as a transaction export from a bank.

## Step 1: Gather Source Records Without Uploading Credentials

Work from records you can open and read yourself. Common sources include:

1. **Email receipts**: Search your inbox for terms like "receipt," "invoice," "renewal," or vendor names you remember.
2. **App store subscription lists**: Use the subscription guidance for [Apple-billed subscriptions](https://support.apple.com/en-us/118428) or [Google Play subscriptions](https://support.google.com/googleplay/answer/7018481) to find the relevant account records.
3. **Vendor account pages**: Log in to each service and check the billing or subscription area for renewal dates and terms.
4. **Bank and card statements**: Review a statement window long enough to include annual renewals as well as monthly charges. Use these to find vendors you forgot, then verify terms in the vendor account or receipt.

Do not upload bank credentials to any tool during this step. The audit works because you compare records yourself. A manual-first household bill tracker like [HomeWeal](/articles/what-is-a-household-bill-tracker) fits this workflow because it does not ask for bank access.

## Step 2: Build the Inventory

Create one row per subscription. Use the CSV headers as your minimum fields:

- **Vendor**: Name of the service or provider.
- **Payer**: Who in the household pays, if you share costs.
- **Billing cycle**: Monthly, quarterly, annual, or another interval.
- **Amount and currency**: The amount shown on the receipt or account page.
- **Next renewal date**: When the next charge is scheduled.
- **Notice deadline**: The date by which you must cancel to avoid the next charge, if the vendor states one.

Check vendor terms directly. Do not assume a universal cancellation rule. Some vendors require notice days before renewal; others let you cancel anytime and keep access until the period ends. The notice deadline column is only as accurate as the terms you read for that specific vendor. Record the cancellation conditions shown for your actual subscription.

### Comparing Annual and Monthly Plans

You may want to compare an annual plan against a monthly plan. A monthly-equivalent figure is useful for comparison only. In a hypothetical example, a subscription billed at 120 once a year has a monthly equivalent of 10: divide 120 by 12. This does not mean 10 leaves your account each month, and it does not change the actual due cash on the renewal date.

If you add a monthly-equivalent column, label it clearly as a comparison figure. The supplied CSV does not include this column to keep the audit focused on actual amounts and cycles.

## Step 3: Decide Keep, Cancel, or Review

For each row, assign one decision:

| Decision | Meaning | Next action |
| --- | --- | --- |
| Keep | You use it and accept the next renewal. | Note the next renewal date; no cancellation needed. |
| Cancel | You no longer want the service. | Cancel auto-renew before the notice deadline, then record confirmation. |
| Review | You are unsure or the cost changed. | Set a date to check usage, then decide before the notice deadline. |

A "review" decision is not a final state. It needs a date and an owner. If auto-renew is enabled, missing the review date can leave an unwanted renewal in place. That is not a failure of the audit; it is a reminder that the audit only helps when the review date is real.

## Step 4: Take One Action and Record Confirmation

Assign one action owner to each cancel or review row. In a shared household, that might be the person whose account holds the subscription.

When you cancel, record the confirmation. That could be:

- A cancellation confirmation email.
- A note in your records showing the access end date as provided by the vendor.

The CSV includes `cancellation_confirmation` and `access_end_date` columns for this reason. A cancellation without confirmation is easy to forget, especially when access continues for weeks after you turn off auto-renew.

## Step 5: Make the Audit a Routine

The audit reflects your subscriptions at the time of review. Subscriptions change when people sign up for trials, switch plans, or share costs with a partner or roommate. Update your checklist as changes occur.

You can keep the CSV as a reference and update it manually. If you want an ongoing view, HomeWeal's Solo plan includes up to 10 bills, a bill calendar, web push bill reminders, variable-amount tracking, and CSV and Excel export ([see features](/features)). For households that split costs, [HomeWeal Family](/pricing) supports equal, percentage, or fixed-amount bill splitting. Income-based percentages are calculated by the household, not by the app.

For annual bills that do not fit a monthly rhythm, see our guide on [how to budget for annual household bills](/articles/how-to-budget-for-annual-household-bills). If you want an AI-assisted way to think through the audit without bank linking, see [the AI bill tracker](/articles/ai-bill-tracker).

## Common Mistakes in a Subscription Audit

- **Mistaking uninstall for cancellation**: Deleting an app does not stop a subscription billed through an app store or vendor account. Always check the subscription list or vendor billing page.
- **Mistaking a refund request for a cancellation**: You can cancel auto-renew and still ask about a refund, but they are separate actions. Check the cancellation confirmation for future billing and access dates. Read the vendor refund terms separately from its cancellation instructions.
- **Mixing inventory and payment history**: A bank statement shows past charges. It may include one-time purchases that look recurring, or miss annual charges that have not hit recently. Use statements to find candidates, then verify each one in the vendor account or receipt.
- **Assuming a monthly-equivalent is actual cash due**: An annual plan compared at a monthly rate is a planning number, not a monthly bill. The renewal date and the full amount are what matter for cash flow.
- **Skipping the notice deadline**: Some vendors require action before a specific date. If you only check the renewal date, you may cancel too late for the next cycle.

## Who This Method Is Not For

This audit is not for someone who wants a bank-linked app to automatically detect subscriptions and cancel them. HomeWeal does not do that, and this checklist does not pretend to. If you want automatic detection, a bank-linked budgeting service may fit better, while this method keeps discovery and record checking manual.

The audit also does not replace reading vendor terms. It gives you a place to record deadlines and confirmations, but the deadlines themselves come from the vendor, not from this template.

## Next Action: Run the Audit This Week

Start with the source you can check fastest—usually your app store subscription list or email receipts. [Download the CSV checklist](/downloads/subscription-audit-checklist.csv), fill in one row per subscription, and assign a decision before the next notice deadline. Then move the results into a routine you will actually update, whether that is the CSV or a manual-first tracker like [HomeWeal](/pricing).

Find related guides in the [HomeWeal article library](/articles).
