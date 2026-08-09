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
2b. **Tier-gated features must name their tier.** A feature being real and
   live is not the same as it being universally available. If a
   differentiator in `verified_facts.real_differentiators` carries a `tier`
   annotation (e.g. `{"feature": "household bill splitting", "tier": "family
   only"}`), any article describing how to use that feature must name the
   tier/plan explicitly — never let the surrounding prose imply it's
   available on a lower tier. This is a real bug caught in article-forge's
   first live deployment (2026-08-09): a generated how-to article walked a
   reader through "create a household, invite your roommate, split bills"
   without noting that splitting/invite/settle-up was gated to a specific
   paid plan — a reader following the free-tier instructions would have hit
   a paywall mid-task. The automated pre-publish gate (§11) does NOT catch
   this class of error — it's a facts-accuracy gap, not a fabrication or
   placeholder — so treat tier-gating as a mandatory manual cross-check on
   every draft, not just an automated one.
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
- **Vary how each section opens — do not open every H2 the same way.** A
  flat register (every section starts with a plain declarative sentence
  stating a general truth, then elaborates) is itself an AI-sounding tell,
  independent of word choice. Rotate: a blunt one-line statement, a direct
  question, a short scenario, an answer-first capsule (reserve this
  specifically for sections that match a real search/PAA-style query — not
  every section is one). Pick per-section based on what that section is
  actually doing (explaining a trade-off vs. answering a direct question
  vs. transitioning topics), not decoratively.
- **Vary sentence length within a paragraph.** Mix short, direct sentences
  with longer ones that carry a qualifier or example. Uniform
  medium-length sentences throughout a section are a second AI-sounding
  tell independent of vocabulary.
- These two rules are generation-time rules, not just a rewrite-time fix —
  apply them in the first draft (see the prompt template), not as a
  polish pass afterward. A prompt that only says "sound human" without
  these two concrete instructions reliably produces the flat-register
  default.

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

**This grep only catches fabrication/placeholder tells. It does not catch
facts-accuracy errors** — a claim that's real but wrongly scoped (see §2b).
Before publishing, also manually cross-check: for every feature the draft
describes someone using, does `verified_facts.real_differentiators` gate
that feature to a specific tier? If so, does the draft name that tier
wherever it matters (setup instructions, pricing recap), not just once in
passing? This check has no automatable pattern — it requires actually
reading the draft against the config, which is why it's separate from the
grep above rather than folded into it.

**Tested, not just theorized:** after adding `[TIER: ...]` tagging to
`verified_facts` and the matching prompt instruction (§2b), regenerating
the same article correctly named the gated tier in 2 of 3 places it
mattered — a real improvement over the untagged version, which named it
nowhere. The third mention still blurred two separate upgrade paths
("more bills" vs. "multiple members") into one muddled sentence. Tagging
reduces this error class; it does not eliminate it. Keep doing the manual
cross-check above even on a fully tier-tagged config.

**Automated gate:** run `scripts/check_article.py --draft <file> --config
site-config.json --type <type> --query "<target query>"` before publishing.
It automates what CAN be automated — the fabrication grep, word count range,
banned words, presence of a structured element, H1/query match, and a
word-overlap heuristic for tier-gating gaps — and exits non-zero on a hard
fabrication failure. It does NOT replace the manual read above: automated
checks catch shape (is there a table? is the word count right?), not
meaning (does this sentence actually match `verified_facts`?). Tested
against a deliberately bad draft ("invite your roommate to split bills...
all for free" — no tier named) and it correctly flagged the gap; tested
against both real shipped articles and both passed clean.

## 12. Rewriting an already-published article

Before rewriting anything for voice, tone, or structure, **verify your
diagnosis against the actual current source, not against what you assume
is there.** A rewrite plan proposed "every H2 opens with a bolded 2-3
sentence capsule" as the problem to fix — a plausible-sounding pattern that,
on inspection of the live article, wasn't actually present; only 2 of 7
H2s had anything resembling that shape. Rewriting against a wrong diagnosis
either fixes nothing or breaks something that wasn't broken. Read the
current live source first; state the actual pattern found, not the assumed
one.

Once the real issue is identified, treat any prose rewrite as a risk
surface for reintroducing inaccuracy, not just a style pass:

- Re-run the automated gate (§11) AND the manual fabrication/tier-gating
  checks after every rewrite, not just on first generation.
- Vary structure by what the section is actually doing, not decoratively:
  a direct-answer capsule where the section matches a real "people also
  ask"-style query, a scenario or blunt statement where it's explaining a
  trade-off, a question where it's transitioning topics. Vary sentence
  length within a section too — a rewrite that's just "different words,
  same rhythm throughout" doesn't read any more human than the original.
- Every fact carried over from the original draft (pricing, tier-gating,
  billing framing, what's real vs. `coming_soon`) must be checked against
  `verified_facts` again, not assumed correct because it was correct
  before the rewrite touched that sentence.

**Prompt-level voice rules are not self-verifying.** Cross-model review
(DeepSeek + direct Codex CLI, 2026-08-09) on exactly this question agreed:
an LLM given "vary how each section opens" cannot reliably audit its own
output for whether it actually did — long-generation self-monitoring is
weak, and a self-critique appended to the same generation tends to
rubber-stamp itself rather than catch real repetition. Two things fix
this, not one:

1. `scripts/check_article.py`'s structural-repetition check — flags
   adjacent H2s sharing an opening word and sections with near-uniform
   sentence length. Coarse and gameable by design (a variance threshold
   alone rewards mechanically-alternating short/long sentences, not real
   rhythm) — treat it as a WARN worth a human skim, never a hard gate.
2. For anything ship-grade, run a genuine audit pass in a **separate,
   fresh model context** — a new `agent()`/API call handed only the
   finished draft, asked specifically to find repeated rhetorical
   patterns across H2s. A fresh context has no stake in the text it
   didn't write, which is why it catches what a same-context self-critique
   misses.
