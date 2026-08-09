# Article Rules

A model-agnostic, site-agnostic ruleset for writing articles that rank in
traditional search (Google/Bing SERPs) **and** get cited by AI answer engines
(ChatGPT, Perplexity, Google AI Overviews, Claude). Distilled from cross-model
research (independent answers from Claude and DeepSeek, cross-checked against
live web research) plus hard lessons from real sites that shipped inaccurate
content.

Every rule below assumes you've filled out `site-config.json` first — that's
where the site-specific facts (product, ICP, differentiators, competitors,
what's real vs. not-yet-real) live. These rules never hardcode a product.

## 1. Non-negotiable integrity rules

1. **Never fabricate.** No invented press mentions, stats, testimonials,
   quotes, or contact info. If `site-config.json` doesn't supply a real value,
   leave a clearly-labeled placeholder (`<!-- PLACEHOLDER: needs real value -->`)
   instead of a plausible-sounding fake one. Fabricated content is
   structurally indistinguishable from real content once shipped — it gets
   past visual review and stays live.
2. **Claims must match verified reality.** Only state what's in
   `site-config.json`'s `verified_facts` block. Never describe a
   `coming_soon`/roadmap feature as available. Never state a pricing/billing
   term (trial, refund policy, price) that isn't explicitly listed there.
3. **Stay in the chosen category frame.** Use `category_frame` and
   `not_positioned_as` from the config on every article — don't let an
   article drift the product into an adjacent category the business has
   deliberately avoided.
4. **Comparison honesty.** When writing about competitors, if a competitor or
   a simpler/free alternative genuinely wins for a specific use case, say so.
   Hedged, non-absolute claims are both more trustworthy to readers and more
   likely to be surfaced by AI engines, which favor even-handed sourcing over
   marketing copy.

## 2. Structure — same template for every article

- **H1** = the target query, close to verbatim.
- **First 40–100 words**: a standalone, extractable direct-answer
  "capsule" — plain declarative prose, no throat-clearing intro
  ("In today's fast-paced world…"). This is the paragraph AI answer engines
  lift verbatim, so it must make sense with zero surrounding context.
- **H2s phrased as the real follow-up questions** a searcher would ask next.
  Each H2 opens with its own 2–3 sentence direct answer, then supporting
  detail.
- **At least one real structured element**: a genuine `<table>` (never a div
  grid) for comparisons, or a numbered step list for how-tos. Structured
  elements get extracted and cited by AI engines disproportionately more
  than prose paragraphs saying the same thing.
- **An honest "who this isn't for" / "common mistakes" section.** Builds
  trust; also reads as a non-absolute claim, which AI engines weight
  favorably.
- **Close with a ~150-word bottom-line/verdict** restating the direct answer,
  plus a single CTA appropriate to the article's funnel stage.

## 3. Word count

Let the query's intent set the length — don't pad to hit a number.

| Article type | Target length |
|---|---|
| Standard how-to / comparison | 1,200–1,800 words |
| The one definitional/pillar article | up to 2,000 words |
| Supporting/narrow-question posts | 800–1,200 words |

Signal you're off: consistently landing under ~1,000 words means the topic is
too narrow to stand alone (fold it into a bigger piece). Consistently pushing
past ~2,000 on a non-pillar piece means split it into two articles.

## 4. Structured data (schema.org / JSON-LD)

- `Article` + `BreadcrumbList` on every article page.
- Sitewide: `Organization` + `WebSite`, once, on the homepage.
- The site's main entity gets ONE schema type matched to what it actually is
  — `SoftwareApplication`, `Product`, `Service`, `LocalBusiness`, etc. Pick
  from `site-config.json`'s `schema_type` field; don't guess. If
  `SoftwareApplication`, use the most specific `applicationCategory` value
  that fits (e.g. `FinanceApplication`, not the generic `BusinessApplication`,
  if the product is finance-adjacent) — specificity helps categorization
  without contradicting the on-page positioning copy.
- `featureList` (if used) must name only features listed as real/live in
  `verified_facts` — never a `coming_soon` feature.
- **Do not add `FAQPage` schema for a Google rich-result benefit** — Google
  retired FAQ rich results entirely in May 2026 (confirmed, for every site
  including government/health, which had been the last carve-out). FAQPage
  markup itself still validates and may still help some AI engines parse
  Q&A structure, but don't build content strategy around the schema for
  SERP purposes. Natural Q&A sentences embedded in body prose work just as
  well for AI parseability without a dedicated schema block.

## 5. Entity consistency (cheapest, strongest AEO signal)

Write **one canonical definition sentence** for the product/business and
reuse it **verbatim** in: the meta description, the schema `description`
field, and the homepage/article's first paragraph. Consistency across
surfaces — not more content — is what lets AI engines resolve "what is this
entity" with confidence and start citing it.

## 6. Earn AI citations with original data

Include one genuinely original, self-generated statistic per article when
you have one (aggregate/anonymized product usage data, a real calculation,
a real survey) — stated as a standalone sentence. Never invent a number.
Original numbers are what other content can't copy, which is what gets
cited. If you don't have a real stat for this topic, skip this — don't
force a fake one in.

## 7. Voice — avoid generic AI-sounding copy

- Draft from your own outline/bullet points; use an LLM to critique and
  tighten, not to generate full paragraphs from a blank prompt.
- Ban list (default — extend per-site in `site-config.json`): "delve",
  "landscape", "robust", "seamless", "elevate", "game-changer", "in today's
  fast-paced world", rhetorical-question openers, rule-of-three padding.
- If the site has a real first-person founder voice (`voice.first_person:
  true` in config), include one true, specific anecdote per article — never
  a fabricated one. If the site writes in brand/third-person voice, skip
  this rule entirely rather than fake a founder story.
- State a real, specific opinion per section rather than hedging everything
  into mush — readers and AI engines both discount content that says
  nothing.

## 8. Internal linking — hub and spoke

Pick one pillar/definitional page as the hub for the site's core topic.
Every comparison and how-to article links **up** to the hub with a
descriptive (not "click here") anchor, **sideways** to sibling comparison
pages, and **down** to the primary conversion surface (signup, pricing, a
free tool) — placed in the first third of the article, not just the
footer.

## 9. Technical / AEO baseline

- Article pages must be server-rendered or statically generated — many AI
  crawlers don't execute client-side JS, so client-only rendering makes
  content invisible to them even though it looks fine in a browser.
- Show a visible last-updated / `dateModified` date.
- Consider adding a `llms.txt` file at the site root — cheap, emerging
  convention, no known downside.

## 10. Cadence

Depth over volume. For a solo writer: roughly 3–4 articles/month, each done
to the full standard above, beats a higher volume of thinner posts — both
traditional SEO and AI-citation patterns reward depth-per-query. Revisit
each article at ~90 days: check what queries it's actually getting found
for, tighten the answer capsule, refresh the date.

## 11. Pre-publish gate

Before publishing anything generated with this framework, grep the draft
for placeholder/fabrication tells:

```
grep -inE "example\.com|lorem ipsum|TBD|FIXME|555-|Jane (S|Smith)|John (S|Smith)|Sample (Customer|Client)" draft.md
```

Any hit means a value that should have come from `site-config.json` was
left as a stand-in. Fix before publishing — don't ship placeholders.
