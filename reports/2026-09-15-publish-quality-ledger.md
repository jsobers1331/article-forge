# Publish-quality ledger — 2026-09-15

Gate: `scripts/check_publish.py` (stdlib only, live HTTP GETs, no paid APIs). Every row below is a check the gate actually ran against the live page and the status it returned — PASS, WARN, or FAIL. `FAIL` means the gate calls it a hard failure (do not publish through the gate); `WARN` is a publishable-but-fix-it finding.

## 1. What was run

| Run | Command shape | Scope | Result |
|---|---|---|---|
| `shootmuse` sitemap | `check_publish.py --sitemap https://shootmuse.com/sitemap.xml --prefix /blog/` | 11 gated article page(s) | 11 of 11 with hard failures (25 hard / 48 warn) |
| `homeweal` sitemap | `check_publish.py --sitemap https://homeweal.com/sitemap.xml --prefix /articles/` | 16 gated article page(s) | 16 of 16 with hard failures (57 hard / 104 warn) |
| `jsobersphotography` sitemap | `check_publish.py --sitemap https://www.jsobersphotography.com/sitemap.xml --prefix /blog/` | 14 gated article page(s) | 0 of 14 with hard failures (0 hard / 63 warn) |
| `shootmuse` homepage | `check_publish.py --kind page` | https://shootmuse.com/ | 0 hard / 2 warn / 1 page |
| `shootmuse` hub | `check_publish.py --kind page` | https://shootmuse.com/blog | 1 hard / 3 warn / 1 page |
| `homeweal` homepage | `check_publish.py --kind page` | https://homeweal.com/ | 0 hard / 3 warn / 1 page |
| `homeweal` hub | `check_publish.py --kind page` | https://homeweal.com/articles | 0 hard / 4 warn / 1 page |
| `jsobersphotography` homepage | `check_publish.py --kind page` | https://www.jsobersphotography.com/ | 0 hard / 3 warn / 1 page |
| `jsobersphotography` hub | `check_publish.py --kind page` | https://www.jsobersphotography.com/blog | 1 hard / 4 warn / 1 page |
| Draft QA | `check_article.py` | 16 drafts | 12 pass, 4 hard FAIL |
| SERP scoring | `score_article.py` | 6 draft/snapshot pairs | all score, none hard-gate |

All raw artifacts are in `reports/`: `publish-gate.*.json` (one per run, full per-check results), `sitemap-run.*.txt` and `page-run.*.txt` (human-readable logs), `check-article/`, `score-article/`, and the two `*.summary.txt` rollups.

**Class totals across the three sitemap runs: 297 findings — 82 hard, 215 warn** (the hub/homepage runs are counted separately in section 3).

## 2.1 shootmuse.com — 11 gated `/blog/` articles

25 hard failure item(s) and 48 warning item(s) across 11 page(s); 11 page(s) carry at least one hard failure.

| Page | H | W | P | Evidence |
|---|---:|---:|---:|---|
| `/blog/photography-contract-checklist` | 3 | 6 | 18 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — 1 internal link(s) do not resolve: https://shootmuse.com/features/contracts -> HTTP 404<br>WARN — 75 chars (guidance 15–70) — 'Photography Contract Checklist: What to Incl…<br>WARN — 172 chars (guidance 50–160) — 'A practical photography contract checklist c…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Sep 13, 2026'<br>WARN — dateModified is not ISO-8601: 'Sep 13, 2026'<br>WARN — 896 words (below the 1000–2000 band for 'standard') |
| `/blog/how-to-get-photography-clients` | 3 | 6 | 18 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — 1 internal link(s) do not resolve: https://shootmuse.com/features/automation -> HTTP 404<br>WARN — 80 chars (guidance 15–70) — 'How to Get Photography Clients: A Practical…<br>WARN — 167 chars (guidance 50–160) — 'How to get photography clients without chasi…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Sep 13, 2026'<br>WARN — dateModified is not ISO-8601: 'Sep 13, 2026'<br>WARN — 879 words (below the 1000–2000 band for 'standard') |
| `/blog/what-is-a-photography-crm` | 3 | 5 | 19 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — 1 internal link(s) do not resolve: https://shootmuse.com/features/automation -> HTTP 404<br>WARN — 175 chars (guidance 50–160) — 'What is a photography CRM? ShootMuse is AI-p…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Aug 30, 2026'<br>WARN — dateModified is not ISO-8601: 'Aug 30, 2026'<br>WARN — 2183 words (above the 1000–2000 band for 'standard') |
| `/blog/photography-client-onboarding-workflow` | 2 | 5 | 20 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — 167 chars (guidance 50–160) — 'Build a photography client onboarding workfl…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Sep 9, 2026'<br>WARN — dateModified is not ISO-8601: 'Sep 9, 2026'<br>WARN — 2114 words (above the 1000–2000 band for 'standard') |
| `/blog/switch-from-honeybook` | 2 | 4 | 21 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — 181 chars (guidance 50–160) — "Thinking about leaving HoneyBook? Here's a c…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Apr 10, 2026'<br>WARN — dateModified is not ISO-8601: 'Apr 10, 2026' |
| `/blog/gallery-delivery-best-practices` | 2 | 4 | 21 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — 174 chars (guidance 50–160) — "Your gallery delivery is your biggest referr…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Mar 20, 2026'<br>WARN — dateModified is not ISO-8601: 'Mar 20, 2026' |
| `/blog/pricing-photography-packages` | 2 | 4 | 21 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Mar 13, 2026'<br>WARN — dateModified is not ISO-8601: 'Mar 13, 2026'<br>WARN — banned words present in the served copy: seamless |
| `/blog/photography-workflow-automation` | 2 | 4 | 21 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — 97 chars (guidance 15–70) — 'Photography Workflow Automation: What to Aut…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Sep 6, 2026'<br>WARN — dateModified is not ISO-8601: 'Sep 6, 2026' |
| `/blog/choose-photography-crm` | 2 | 4 | 21 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — 162 chars (guidance 50–160) — 'Learn how to choose a photography CRM by tes…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Sep 9, 2026'<br>WARN — dateModified is not ISO-8601: 'Sep 9, 2026' |
| `/blog/outgrown-photography-crm` | 2 | 3 | 22 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Apr 3, 2026'<br>WARN — dateModified is not ISO-8601: 'Apr 3, 2026' |
| `/blog/ai-for-photographers` | 2 | 3 | 22 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — datePublished is not ISO-8601: 'Mar 27, 2026'<br>WARN — dateModified is not ISO-8601: 'Mar 27, 2026' |

## 2.2 homeweal.com — 16 gated `/articles/` articles

57 hard failure item(s) and 104 warning item(s) across 16 page(s); 16 page(s) carry at least one hard failure.

| Page | H | W | P | Evidence |
|---|---:|---:|---:|---|
| `/articles/best-splitwise-alternative-for-recurring-household-bills` | 4 | 9 | 14 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 74 chars (guidance 15–70) — 'Best Splitwise Alternative for Recurring Hou…<br>WARN — 167 chars (guidance 50–160) — 'Splitwise is built for one-off shared expens…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://splitwise.com', 'https://ynab.com', 'https://monarchmoney.com']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fsplitwise-alt-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/what-is-a-household-bill-tracker` | 4 | 9 | 14 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 161 chars (guidance 50–160) — 'A household bill tracker logs, splits, and s…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://ynab.com', 'https://monarchmoney.com', 'https://copilot.money']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fhousehold-tracker-pillar-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k<br>WARN — 975 words (below the 1000–2000 band for 'standard') |
| `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet` | 4 | 8 | 15 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 170 chars (guidance 50–160) — 'Stop reconciling a shared spreadsheet. How a…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://splitwise.com', 'https://ynab.com', 'https://monarchmoney.com']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fsplit-bills-hero-v3.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/ynab-alternatives-without-bank-linking` | 4 | 8 | 15 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://ynab.com', 'https://monarchmoney.com', 'https://copilot.money']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fynab-alt-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k<br>WARN — 972 words (below the 1000–2000 band for 'standard') |
| `/articles/honeydue-alternative-without-bank-linking` | 4 | 8 | 15 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 177 chars (guidance 50–160) — 'Honeydue is free but requires linking your a…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-30)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 1 external/competitor link(s) in the body: ['https://www.honeydue.com']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fhoneydue-alt-hero.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/best-bill-tracker-without-bank-linking` | 4 | 7 | 16 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://ynab.com', 'https://monarchmoney.com', 'https://copilot.money']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fbest-tracker-hero-v3.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/multi-currency-budgeting-app-for-couples` | 4 | 7 | 16 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://ynab.com', 'https://monarchmoney.com', 'https://copilot.money']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fmulticurrency-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/monarch-alternative-without-bank-linking` | 4 | 7 | 16 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://monarchmoney.com', 'https://splitwise.com', 'https://ynab.com']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fmonarch-alt-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/copilot-alternative-without-bank-linking` | 4 | 7 | 16 | **FAIL** — og:image missing — social/link previews have no image<br>**FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — Article.image missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 4 external/competitor link(s) in the body: ['https://copilot.money', 'https://splitwise.com', 'https://ynab.com']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fcopilot-alt-hero-v4.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/how-to-make-a-monthly-budget` | 3 | 6 | 17 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 73 chars (guidance 15–70) — 'How to Make a Monthly Budget That Accounts f…<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-09-13)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fmonthly-bill-planner-hero.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k<br>WARN — 714 words (below the 1000–2000 band for 'standard') |
| `/articles/how-to-track-expenses` | 3 | 6 | 17 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 76 chars (guidance 15–70) — 'How to Track Expenses: A Simple System You W…<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-09-13)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fhousehold-tracker-pillar-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k<br>WARN — 666 words (below the 1000–2000 band for 'standard') |
| `/articles/uk-household-bills-checklist-moving-home` | 3 | 5 | 19 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 2 external/competitor link(s) in the body: ['https://www.gov.uk/guidance/your-property-and-council-tax', 'https://www.ofgem.gov.uk/get-energy-if-you-are-moving-home-or-business-premises']<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fuk-moving-bills-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/debt-snowball-vs-avalanche` | 3 | 5 | 18 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — 74 chars (guidance 15–70) — 'Debt Snowball vs Avalanche: Which Payoff Met…<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-08-30)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fdebt-snowball-avalanche-hero.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/what-is-a-good-monthly-planner-for-bills` | 3 | 4 | 19 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-09-04)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fmonthly-bill-planner-hero.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/how-to-split-bills-based-on-income` | 3 | 4 | 19 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fincome-split-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |
| `/articles/how-to-track-household-bills-in-multiple-currencies` | 3 | 4 | 19 | **FAIL** — twitter:title is identical to the homepage's — the card shows the wrong page name<br>**FAIL** — Article.author references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>**FAIL** — Article.publisher references @id 'https://homeweal.com#org' but no such node exists on this page (dangling reference)<br>WARN — og:type missing<br>WARN — dateModified == datePublished (2026-08-09)<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fmulti-currency-bills-hero-v2.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k |

## 2.3 www.jsobersphotography.com — 14 gated `/blog/` articles

0 hard failure item(s) and 63 warning item(s) across 14 page(s); 0 page(s) carry at least one hard failure.

| Page | H | W | P | Evidence |
|---|---:|---:|---:|---|
| `/blog/barbados-wedding-venues-how-to-choose` | 0 | 6 | 20 | WARN — 90 chars (guidance 15–70) — 'Barbados wedding venues: how to choose the r…<br>WARN — 181 chars (guidance 50–160) — 'A practical way to compare beach, garden, cl…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-09-13T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 959 words (below the 1000–2000 band for 'standard') |
| `/blog/best-time-to-get-married-in-barbados` | 0 | 6 | 20 | WARN — 97 chars (guidance 15–70) — 'Best time to get married in Barbados: weathe…<br>WARN — 170 chars (guidance 50–160) — 'How to choose a Barbados wedding date around…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-09-13T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 756 words (below the 1000–2000 band for 'standard') |
| `/blog/how-long-wedding-photos-barbados` | 0 | 5 | 21 | WARN — 73 chars (guidance 15–70) — 'How long until you get your Barbados wedding…<br>WARN — 169 chars (guidance 50–160) — "A 10–20 image sneak peek within 48–72 hours,…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-09T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog) |
| `/blog/plan-barbados-destination-wedding` | 0 | 5 | 21 | WARN — 81 chars (guidance 15–70) — 'How to plan a Barbados destination wedding f…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-02T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 662 words (below the 1000–2000 band for 'standard') |
| `/blog/outdoor-ceremony-barbados-what-to-expect` | 0 | 5 | 21 | WARN — 74 chars (guidance 15–70) — 'What to expect from your outdoor ceremony in…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-02T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 412 words (below the 1000–2000 band for 'standard') |
| `/blog/caribbean-engagement-portrait-style` | 0 | 5 | 21 | WARN — 73 chars (guidance 15–70) — 'What to wear for your Caribbean engagement p…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-02T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 347 words (below the 1000–2000 band for 'standard') |
| `/blog/how-to-book-a-barbados-wedding-photographer-from-abroad` | 0 | 5 | 21 | WARN — 76 chars (guidance 15–70) — 'How to book a Barbados wedding photographer…<br>WARN — 167 chars (guidance 50–160) — 'How to book a Barbados wedding photographer…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-09-04T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog) |
| `/blog/barbados-wedding-photographer-cost` | 0 | 4 | 22 | WARN — 72 chars (guidance 15–70) — 'How much does a Barbados wedding photographe…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-09T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog) |
| `/blog/engagement-photography-barbados-cost` | 0 | 4 | 22 | WARN — 90 chars (guidance 15–70) — "Engagement photography in Barbados: what it…<br>WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-09T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog) |
| `/blog/crane-beach-golden-hour` | 0 | 4 | 22 | WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-02T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 433 words (below the 1000–2000 band for 'standard') |
| `/blog/husband-wife-photography-team` | 0 | 4 | 22 | WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-02T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 327 words (below the 1000–2000 band for 'standard') |
| `/blog/wedding-album-printing-guide` | 0 | 4 | 22 | WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-02T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog)<br>WARN — 382 words (below the 1000–2000 band for 'standard') |
| `/blog/wedding-welcome-dinner-photography-barbados` | 0 | 3 | 23 | WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-08-09T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog) |
| `/blog/how-to-choose-a-barbados-wedding-photographer` | 0 | 3 | 23 | WARN — og:type is 'website', expected 'article'<br>WARN — dateModified == datePublished (2026-09-04T00:00:00.000Z)<br>WARN — no in-body link up to the hub (/blog) |

## 3. Hub and homepage (`--kind page`)

| Site | Page | H | W | P | Evidence |
|---|---|---:|---:|---:|---|
| `shootmuse` | `/` (homepage) | 0 | 2 | 19 | WARN — no in-body link up to the hub (/blog)<br>WARN — hero image has no width/height or aspect-ratio: /images/product-tour-frame.jpg |
| `shootmuse` | `/blog` (hub) | 1 | 3 | 17 | **FAIL** — og:image missing — social/link previews have no image<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — og:type missing<br>WARN — no in-body link up to the hub (/blog) |
| `homeweal` | `/` (homepage) | 0 | 3 | 19 | WARN — 192 chars (guidance 50–160) — 'Track recurring household bills, due dates,…<br>WARN — no in-body link up to the hub (/articles)<br>WARN — 1 external/competitor link(s) in the body: ['https://app.homeweal.com/signup'] |
| `homeweal` | `/articles` (hub) | 0 | 4 | 17 | WARN — no Organization/WebSite node (types present: ['BreadcrumbList', 'ListItem'])<br>WARN — no in-body link up to the hub (/articles)<br>WARN — hero image has no width/height or aspect-ratio: /_next/image?url=%2Fimages%2Farticles%2Fmonthly-bill-planner-hero.webp&w=3840&q=75&dpl=dpl_5Bj68X1CSpyfKt7WSkAT73uUHu5k<br>WARN — no visible publish or update date anywhere in the page text |
| `jsobersphotography` | `/` (homepage) | 0 | 3 | 18 | WARN — 166 chars (guidance 50–160) — 'Jason Sobers is a Barbados wedding photograp…<br>WARN — no in-body link up to the hub (/blog)<br>WARN — no visible publish or update date anywhere in the page text |
| `jsobersphotography` | `/blog` (hub) | 1 | 4 | 16 | **FAIL** — og:image missing — social/link previews have no image<br>WARN — 79 chars (guidance 15–70) — 'Journal — Field Notes from a Barbados Weddin…<br>WARN — twitter:image missing while twitter:card is 'summary_large_image' — the card claims a large image it cannot render<br>WARN — no in-body link up to the hub (/blog)<br>WARN — no visible publish or update date anywhere in the page text |

Both hubs carry one hard failure: their `og:image` is missing, so shared links to the hub render without a preview image. The three homepages are clean of hard failures.

## 4. Cross-site defect classes (ranked)

Every FAIL/WARN item from the three sitemap runs, grouped by the defect it represents. 297 findings in 19 classes, ranked by finding count. A page can contribute more than one finding to a class: `JSON-LD date not ISO-8601` fires 22 times across 11 page(s).

| # | Sev | Class | Findings | Pages | shootmuse | homeweal | jsobers |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | WARN | JSON-LD dateModified == datePublished (no update signal) | 30 | 30 | — | 16 | 14 |
| 2 | WARN | No in-body link up to the hub | 30 | 30 | — | 16 | 14 |
| 3 | **HARD** | Social preview — twitter:title duplicates the homepage title | 27 | 27 | 11 | 16 | — |
| 4 | WARN | JSON-LD date not ISO-8601 | 22 | 11 | 22 | — | — |
| 5 | **HARD** | Social preview — og:image missing | 20 | 20 | 11 | 9 | — |
| 6 | WARN | twitter:card says summary_large_image but twitter:image is missing | 20 | 20 | 11 | 9 | — |
| 7 | WARN | Title length outside 15-70 chars | 16 | 16 | 3 | 4 | 9 |
| 8 | WARN | og:type missing | 16 | 16 | — | 16 | — |
| 9 | **HARD** | JSON-LD dangling @id — Article.author | 16 | 16 | — | 16 | — |
| 10 | **HARD** | JSON-LD dangling @id — Article.publisher | 16 | 16 | — | 16 | — |
| 11 | WARN | Hero image lacks width/height (layout-shift risk) | 16 | 16 | — | 16 | — |
| 12 | WARN | Meta description length outside 50-160 chars | 15 | 15 | 7 | 4 | 4 |
| 13 | WARN | Word count below the band | 14 | 14 | 2 | 4 | 8 |
| 14 | WARN | og:type is 'website' on an article | 14 | 14 | — | — | 14 |
| 15 | WARN | External / competitor links in body | 10 | 10 | — | 10 | — |
| 16 | WARN | JSON-LD Article.image missing | 9 | 9 | — | 9 | — |
| 17 | **HARD** | Internal link returns non-200 | 3 | 3 | 3 | — | — |
| 18 | WARN | Word count above the band | 2 | 2 | 2 | — | — |
| 19 | WARN | Banned word in served copy | 1 | 1 | 1 | — | — |

Affected URLs by class (per-site counts are findings):

<details><summary><b>JSON-LD dateModified == datePublished (no update signal)</b> — 30 page(s)</summary>

- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`
- **jsobersphotography** (14 page(s)): `/blog/barbados-wedding-photographer-cost`, `/blog/engagement-photography-barbados-cost`, `/blog/wedding-welcome-dinner-photography-barbados`, `/blog/how-long-wedding-photos-barbados`, `/blog/plan-barbados-destination-wedding`, `/blog/crane-beach-golden-hour`, `/blog/outdoor-ceremony-barbados-what-to-expect`, `/blog/caribbean-engagement-portrait-style`, `/blog/husband-wife-photography-team`, `/blog/wedding-album-printing-guide`, `/blog/how-to-choose-a-barbados-wedding-photographer`, `/blog/how-to-book-a-barbados-wedding-photographer-from-abroad`, `/blog/barbados-wedding-venues-how-to-choose`, `/blog/best-time-to-get-married-in-barbados`

</details>

<details><summary><b>No in-body link up to the hub</b> — 30 page(s)</summary>

- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`
- **jsobersphotography** (14 page(s)): `/blog/barbados-wedding-photographer-cost`, `/blog/engagement-photography-barbados-cost`, `/blog/wedding-welcome-dinner-photography-barbados`, `/blog/how-long-wedding-photos-barbados`, `/blog/plan-barbados-destination-wedding`, `/blog/crane-beach-golden-hour`, `/blog/outdoor-ceremony-barbados-what-to-expect`, `/blog/caribbean-engagement-portrait-style`, `/blog/husband-wife-photography-team`, `/blog/wedding-album-printing-guide`, `/blog/how-to-choose-a-barbados-wedding-photographer`, `/blog/how-to-book-a-barbados-wedding-photographer-from-abroad`, `/blog/barbados-wedding-venues-how-to-choose`, `/blog/best-time-to-get-married-in-barbados`

</details>

<details><summary><b>Social preview — twitter:title duplicates the homepage title</b> — 27 page(s)</summary>

- **shootmuse** (11 page(s)): `/blog/what-is-a-photography-crm`, `/blog/switch-from-honeybook`, `/blog/outgrown-photography-crm`, `/blog/ai-for-photographers`, `/blog/gallery-delivery-best-practices`, `/blog/pricing-photography-packages`, `/blog/photography-workflow-automation`, `/blog/photography-client-onboarding-workflow`, `/blog/choose-photography-crm`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`
- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`

</details>

<details><summary><b>JSON-LD date not ISO-8601</b> — 22 findings on 11 page(s)</summary>

- **shootmuse** (22 findings on 11 page(s)): `/blog/what-is-a-photography-crm`, `/blog/switch-from-honeybook`, `/blog/outgrown-photography-crm`, `/blog/ai-for-photographers`, `/blog/gallery-delivery-best-practices`, `/blog/pricing-photography-packages`, `/blog/photography-workflow-automation`, `/blog/photography-client-onboarding-workflow`, `/blog/choose-photography-crm`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`

</details>

<details><summary><b>Social preview — og:image missing</b> — 20 page(s)</summary>

- **shootmuse** (11 page(s)): `/blog/what-is-a-photography-crm`, `/blog/switch-from-honeybook`, `/blog/outgrown-photography-crm`, `/blog/ai-for-photographers`, `/blog/gallery-delivery-best-practices`, `/blog/pricing-photography-packages`, `/blog/photography-workflow-automation`, `/blog/photography-client-onboarding-workflow`, `/blog/choose-photography-crm`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`
- **homeweal** (9 page(s)): `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`

</details>

<details><summary><b>twitter:card says summary_large_image but twitter:image is missing</b> — 20 page(s)</summary>

- **shootmuse** (11 page(s)): `/blog/what-is-a-photography-crm`, `/blog/switch-from-honeybook`, `/blog/outgrown-photography-crm`, `/blog/ai-for-photographers`, `/blog/gallery-delivery-best-practices`, `/blog/pricing-photography-packages`, `/blog/photography-workflow-automation`, `/blog/photography-client-onboarding-workflow`, `/blog/choose-photography-crm`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`
- **homeweal** (9 page(s)): `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`

</details>

<details><summary><b>Title length outside 15-70 chars</b> — 16 page(s)</summary>

- **shootmuse** (3 page(s)): `/blog/photography-workflow-automation`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`
- **homeweal** (4 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/debt-snowball-vs-avalanche`
- **jsobersphotography** (9 page(s)): `/blog/barbados-wedding-photographer-cost`, `/blog/engagement-photography-barbados-cost`, `/blog/how-long-wedding-photos-barbados`, `/blog/plan-barbados-destination-wedding`, `/blog/outdoor-ceremony-barbados-what-to-expect`, `/blog/caribbean-engagement-portrait-style`, `/blog/how-to-book-a-barbados-wedding-photographer-from-abroad`, `/blog/barbados-wedding-venues-how-to-choose`, `/blog/best-time-to-get-married-in-barbados`

</details>

<details><summary><b>og:type missing</b> — 16 page(s)</summary>

- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`

</details>

<details><summary><b>JSON-LD dangling @id — Article.author</b> — 16 page(s)</summary>

- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`

</details>

<details><summary><b>JSON-LD dangling @id — Article.publisher</b> — 16 page(s)</summary>

- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`

</details>

<details><summary><b>Hero image lacks width/height (layout-shift risk)</b> — 16 page(s)</summary>

- **homeweal** (16 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/what-is-a-good-monthly-planner-for-bills`, `/articles/how-to-split-bills-based-on-income`, `/articles/how-to-track-household-bills-in-multiple-currencies`, `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`, `/articles/debt-snowball-vs-avalanche`

</details>

<details><summary><b>Meta description length outside 50-160 chars</b> — 15 page(s)</summary>

- **shootmuse** (7 page(s)): `/blog/what-is-a-photography-crm`, `/blog/switch-from-honeybook`, `/blog/gallery-delivery-best-practices`, `/blog/photography-client-onboarding-workflow`, `/blog/choose-photography-crm`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`
- **homeweal** (4 page(s)): `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/what-is-a-household-bill-tracker`, `/articles/honeydue-alternative-without-bank-linking`
- **jsobersphotography** (4 page(s)): `/blog/how-long-wedding-photos-barbados`, `/blog/how-to-book-a-barbados-wedding-photographer-from-abroad`, `/blog/barbados-wedding-venues-how-to-choose`, `/blog/best-time-to-get-married-in-barbados`

</details>

<details><summary><b>Word count below the band</b> — 14 page(s)</summary>

- **shootmuse** (2 page(s)): `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`
- **homeweal** (4 page(s)): `/articles/how-to-make-a-monthly-budget`, `/articles/how-to-track-expenses`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`
- **jsobersphotography** (8 page(s)): `/blog/plan-barbados-destination-wedding`, `/blog/crane-beach-golden-hour`, `/blog/outdoor-ceremony-barbados-what-to-expect`, `/blog/caribbean-engagement-portrait-style`, `/blog/husband-wife-photography-team`, `/blog/wedding-album-printing-guide`, `/blog/barbados-wedding-venues-how-to-choose`, `/blog/best-time-to-get-married-in-barbados`

</details>

<details><summary><b>og:type is 'website' on an article</b> — 14 page(s)</summary>

- **jsobersphotography** (14 page(s)): `/blog/barbados-wedding-photographer-cost`, `/blog/engagement-photography-barbados-cost`, `/blog/wedding-welcome-dinner-photography-barbados`, `/blog/how-long-wedding-photos-barbados`, `/blog/plan-barbados-destination-wedding`, `/blog/crane-beach-golden-hour`, `/blog/outdoor-ceremony-barbados-what-to-expect`, `/blog/caribbean-engagement-portrait-style`, `/blog/husband-wife-photography-team`, `/blog/wedding-album-printing-guide`, `/blog/how-to-choose-a-barbados-wedding-photographer`, `/blog/how-to-book-a-barbados-wedding-photographer-from-abroad`, `/blog/barbados-wedding-venues-how-to-choose`, `/blog/best-time-to-get-married-in-barbados`

</details>

<details><summary><b>External / competitor links in body</b> — 10 page(s)</summary>

- **homeweal** (10 page(s)): `/articles/uk-household-bills-checklist-moving-home`, `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`

</details>

<details><summary><b>JSON-LD Article.image missing</b> — 9 page(s)</summary>

- **homeweal** (9 page(s)): `/articles/best-bill-tracker-without-bank-linking`, `/articles/how-to-split-bills-with-a-roommate-without-a-spreadsheet`, `/articles/best-splitwise-alternative-for-recurring-household-bills`, `/articles/multi-currency-budgeting-app-for-couples`, `/articles/ynab-alternatives-without-bank-linking`, `/articles/what-is-a-household-bill-tracker`, `/articles/monarch-alternative-without-bank-linking`, `/articles/copilot-alternative-without-bank-linking`, `/articles/honeydue-alternative-without-bank-linking`

</details>

<details><summary><b>Internal link returns non-200</b> — 3 page(s)</summary>

- **shootmuse** (3 page(s)): `/blog/what-is-a-photography-crm`, `/blog/photography-contract-checklist`, `/blog/how-to-get-photography-clients`

</details>

<details><summary><b>Word count above the band</b> — 2 page(s)</summary>

- **shootmuse** (2 page(s)): `/blog/what-is-a-photography-crm`, `/blog/photography-client-onboarding-workflow`

</details>

<details><summary><b>Banned word in served copy</b> — 1 page(s)</summary>

- **shootmuse** (1 page(s)): `/blog/pricing-photography-packages`

</details>

## 5. Clean list (no hard failures)

- **jsobersphotography**: all 14 gated `/blog/` articles — 0 hard failures (63 warnings).
- **Homepages**: shootmuse `/`, homeweal `/`, jsobersphotography `/` — 0 hard failures each.
- Note: no *article* on shootmuse or homeweal is clean — every gated article on both sites carries at least one hard failure. jsobersphotography is the only site that is article-clean.

## 6. Search Console overlay — where a defect costs traffic

Window **2026-06-16 → 2026-09-13**, `sc-domain:` property per site, page dimension. Gated pages matched to a GSC row: shootmuse 0, homeweal 9, jsobersphotography 8.

| Priority | Site | Page | Impressions | Clicks | Avg pos | H | W |
|---|---|---|---:|---:|---:|---:|---:|
| **fix first** | `jsobersphotography` | `/blog/barbados-wedding-photographer-cost` | 56 | 1 | 8.1 | 0 | 4 |
| **fix first** | `homeweal` | `/articles/monarch-alternative-without-bank-linking` | 36 | 0 | 12.4 | 4 | 7 |
| **fix first** | `jsobersphotography` | `/blog/plan-barbados-destination-wedding` | 31 | 0 | 29.2 | 0 | 5 |
| **fix first** | `homeweal` | `/articles/multi-currency-budgeting-app-for-couples` | 15 | 0 | 44.6 | 4 | 7 |
| **fix first** | `homeweal` | `/articles/best-bill-tracker-without-bank-linking` | 14 | 0 | 24.5 | 4 | 7 |
| **fix first** | `homeweal` | `/articles/what-is-a-household-bill-tracker` | 13 | 0 | 19.2 | 4 | 9 |
| **fix first** | `jsobersphotography` | `/blog/engagement-photography-barbados-cost` | 12 | 2 | 8.6 | 0 | 4 |

Reading:

- The threshold is impressions > 10 **and** at least one defect — below that the page has no traffic to lose, so the fix can wait; above it a defect is actively suppressing a page people see.
- `jsobersphotography/blog/barbados-wedding-photographer-cost` is the single highest-value fix on the board: 56 impressions at average position 8.1 (page one) with 0 hard failures and 4 warnings — the warnings (social card, hub link, date signal) are the cheap wins here.
- shootmuse has **zero** gated article pages in Search Console — the gate's 25 hard failures there are all on pages that currently earn no impressions. Its traffic sits on `/features/invoicing` (111 impressions), `/features/crm` (51) and `/compare/pixieset` (23), which are not `--prefix /blog/` gated.
- homeweal's `monarch-alternative-without-bank-linking` (36 impressions, 4 hard / 7 warn) is its worst combination of traffic and defects.

Top pages per site regardless of gating:

- **shootmuse**: `/features/invoicing` 111 imp / pos 77.2, `/features/crm` 51 imp / pos 80.5, `/compare/pixieset` 23 imp / pos 43.7, `/features` 8 imp / pos 3.4, `/` 6 imp / pos 3.8, `/compare/honeybook` 6 imp / pos 16.7
- **homeweal**: `/articles/monarch-alternative-without-bank-linking` 36 imp / pos 12.4, `/vs/monarch` 36 imp / pos 35.1, `/articles/multi-currency-budgeting-app-for-couples` 15 imp / pos 44.6, `/articles/best-bill-tracker-without-bank-linking` 14 imp / pos 24.5, `/articles/what-is-a-household-bill-tracker` 13 imp / pos 19.2, `/tools/subscription-audit` 10 imp / pos 67.6
- **jsobersphotography**: `/` 588 imp / pos 28.9, `/` 383 imp / pos 16.9, `/wedding` 276 imp / pos 34.1, `/wedding` 175 imp / pos 21.0, `/wedding-packages` 128 imp / pos 63.0, `/blog` 63 imp / pos 11.2

## 7. `check_article.py` — all 16 drafts

| Draft | Config | Type | PASS | WARN | FAIL |
|---|---|---|---:|---:|---:|
| `what-is-a-photography-crm` | `site-config.shootmuse.json` | pillar | 10 | 0 | 0 |
| `how-to-split-bills-based-on-income` | `site-config.homeweal.json` | standard | 7 | 3 | 0 |
| `how-to-track-household-bills-in-multiple-currencies` | `site-config.homeweal.json` | standard | 7 | 3 | 0 |
| `uk-household-bills-checklist-moving-home` | `site-config.homeweal.json` | standard | 8 | 2 | 0 |
| `best-bill-tracker-without-bank-linking-2026` | `site-config.homeweal.json` | standard | 8 | 2 | 0 |
| `best-splitwise-alternative-for-recurring-household-bills-2026` | `site-config.homeweal.json` | standard | 7 | 2 | 1 |
| `copilot-alternative-without-bank-linking-2026` | `site-config.homeweal.json` | standard | 5 | 4 | 1 |
| `how-to-split-bills-with-a-roommate-without-a-spreadsheet` | `site-config.homeweal.json` | standard | 8 | 2 | 0 |
| `monarch-alternative-without-bank-linking-2026` | `site-config.homeweal.json` | standard | 6 | 3 | 1 |
| `multi-currency-budgeting-app-for-couples-2026` | `site-config.homeweal.json` | standard | 8 | 2 | 0 |
| `what-is-a-household-bill-tracker` | `site-config.homeweal.json` | standard | 7 | 3 | 0 |
| `ynab-alternatives-without-bank-linking-2026` | `site-config.homeweal.json` | standard | 5 | 4 | 1 |
| `engagement-photography-barbados-cost` | `site-config.jsobersphotography.json` | standard | 9 | 1 | 0 |
| `how-long-to-get-wedding-photos-back-barbados` | `site-config.jsobersphotography.json` | supporting | 9 | 1 | 0 |
| `how-much-does-a-barbados-wedding-photographer-cost` | `site-config.jsobersphotography.json` | pillar | 9 | 1 | 0 |
| `wedding-welcome-dinner-photographer-barbados` | `site-config.jsobersphotography.json` | supporting | 8 | 2 | 0 |

Four drafts hard-fail, all on the same defect: a bare URL in parentheses instead of a Markdown link — `(https://splitwise.com)`, `(https://copilot.money)`, `(https://monarchmoney.com)`, and four in `ynab-alternatives-without-bank-linking-2026`. These are one-line fixes in the draft source.

## 8. `score_article.py` — the 6 paired snapshots

| Draft | Score | Hard gate | Entity coverage | Entity gaps | Linking notes |
|---|---:|---|---:|---|---:|
| `best-bill-tracker-without-bank-linking-2026` | 77.2 | pass | 40.0% | 3: `plaid`, `venmo`, `goodbudget` | 1 |
| `copilot-alternative-without-bank-linking-2026` | 85.9 | pass | 37.5% | 5: `plaid`, `rocket money`, `empower`, `quicken simplifi` +1 more | 1 |
| `how-to-split-bills-with-a-roommate-without-a-spreadsheet` | 87.3 | pass | 57.1% | 3: `splittr`, `ourgroceries`, `zelle` | 1 |
| `monarch-alternative-without-bank-linking-2026` | 84.3 | pass | 27.3% | 8: `mint`, `plaid`, `empower`, `goodbudget` +4 more | 1 |
| `what-is-a-household-bill-tracker` | 84.8 | pass | 40.0% | 3: `everydollar`, `empower`, `plaid` | 2 |
| `ynab-alternatives-without-bank-linking-2026` | 82.9 | pass | 44.4% | 5: `mint`, `goodbudget`, `google sheets`, `everydollar` +1 more | 2 |

Scoring only ran where a `serp/` snapshot pairs with the draft (six `serp/*.json` snapshots); the other 10 drafts have no snapshot and are unscored rather than scored on a weaker basis. No draft trips the scorer's hard gate. Entity coverage is the consistent weakness (27.3%–57.1%), most-repeated gaps: `plaid` (4), `goodbudget` (3), `empower` (3), `mint` (3), `everydollar` (2), `venmo` (1). Every scored draft also carries at least one linking note (internal links above the 3–5 target, or external links risking a spam signal).

## 9. www vs apex

`www.jsobersphotography.com` serves the site directly; the apex `jsobersphotography.com` 307-redirects to it. Verified with two HEAD requests:

```
$ curl -sSI https://www.jsobersphotography.com/
HTTP/2 200
server: Vercel
(no location header — served directly)

$ curl -sSI https://jsobersphotography.com/
HTTP/2 307
location: https://www.jsobersphotography.com/
server: Vercel
```

**Verdict: correct — one canonical host, one hop.** No redirect loop, no duplicate-content split, and the sitemap (`https://www.jsobersphotography.com/sitemap.xml`) is consistent with the canonical host.

One wrinkle worth knowing: Search Console still reports the *apex* host for some `/blog/` rows even though the redirect resolves to `www`, and 13 paths appear under both hosts in the same window. That is stale reporting data, not a live serving problem — the redirect is a single 307 and the pages themselves only resolve on `www`. The gate scopes jsobersphotography to the `www` host, so all its findings above are `www` URLs.

## 10. Caveats and follow-ups

- **Two gate fixes landed during this run, and they raised the hard-failure count.** The JSON-LD `@id` resolver had a false negative that hid dangling `Article.author` / `Article.publisher` references, and the content-region extractor had an `in_main` depth bug. After the fixes, those 32 homeweal dangling-`@id` items became visible. Earlier counts taken before the fix are lower and should not be compared to this ledger.
- **The word-count band is type-aware and the pillar runs are separate.** A page published as `pillar` is judged against a wider band, so the standalone `--type pillar` runs of `shootmuse/blog/what-is-a-photography-crm` (2183 words — passes its own band) and `homeweal/articles/what-is-a-household-bill-tracker` (975 words — below even the standard band) differ slightly from the same pages inside their sitemap runs, where they were judged as `standard`.
- **8 homeweal drafts declare no article type** and so default to `standard`, which makes their word-count warnings stricter than a declared type would be. Treat homeweal word-count warnings as type-configuration noise until the drafts declare a type.
- **Region extraction is heuristic.** Word counts come from a text-density heuristic, not a hand count; the long ones were eyeballed (`inline` readings match), but the short ones should be confirmed against the source before rewriting.
- **Gitignore boundary**: `reports/` (this ledger and every artifact above) and `site-config.example.json` are committable; the populated `site-config.<site>.json` and the pulled `gsc-90d-*.json` are gitignored and stay local.
- **Pre-existing lint debt left alone**: `score_article.py` has 5 ruff findings (E741 ×2, F541 ×3) that predate this work. `check_publish.py` and its tests are clean.

