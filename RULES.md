# Article Rules

A site-agnostic editorial policy for useful, sourced content. These policies
are not validated ranking predictors or promises of AI citations. The evidence
contracts and migration rules are in [EVIDENCE_SYSTEM.md](EVIDENCE_SYSTEM.md).

Every rule below assumes you've filled out `site-config.<project>.json` first — that's
where the site-specific facts (product, ICP, differentiators, competitors,
what's real vs. not-yet-real) live. These rules never hardcode a product.

## 1. Non-negotiable integrity rules

1. **Never fabricate.** No invented press mentions, stats, testimonials,
   quotes, or contact info. If `site-config.<project>.json` doesn't supply a real value,
   leave a clearly-labeled placeholder (`<!-- PLACEHOLDER: needs real value -->`)
   instead of a plausible-sounding fake one. Fabricated content is
   structurally indistinguishable from real content once shipped — it gets
   past visual review and stays live.
2. **Claims must match verified reality.** Only state what's in
   `site-config.<project>.json`'s `verified_facts` block. Never describe a
   `coming_soon`/roadmap feature as available. Never state a pricing/billing
   term (trial, refund policy, price) that isn't explicitly listed there.
   `verified_facts` can drift out of date — a price change, a paused promo —
   between runs. `facts_last_verified` (YYYY-MM-DD) records when someone last
   re-read the live site's actual source of truth and confirmed the block
   still matches; `scripts/check_article.py` hard-WARNs once it's more than
   30 days old, so staleness surfaces every run instead of relying on someone
   remembering to check. Per-claim freshness is tracked separately in the
   claim-verification ledger (`claim-verification.<project>.json`, written by
   `scripts/verify_facts.py`) — see AUTONOMY.md for what it covers and when
   entries go stale. See DISCOVERY.md for the pre-topic-selection
   research pass that also depends on these facts being current.
   A live config should also carry a `claim_evidence` registry: each record
   names the claim, its first-party source URL, verification date, and
   `status: "verified"`. The generator blocks a missing or malformed registry;
   the registry is provenance metadata, not a substitute for reading the
   source and the final prose.
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
   a paywall mid-task. The automated pre-publish gate (§11) catches common
   unscoped and universal forms of this error, but it is still a facts-accuracy
   gap rather than a complete semantic proof — treat tier-gating as a
   mandatory manual cross-check on every draft too.
3. **Stay in the chosen category frame.** Use `category_frame` and
   `not_positioned_as` from the config on every article — don't let an
   article drift the product into an adjacent category the business has
   deliberately avoided.
4. **Comparison honesty.** When writing about competitors, if a competitor or
   a simpler/free alternative genuinely wins for a specific use case, say so.
   Hedged, non-absolute claims are both more trustworthy to readers and more
   likely to be surfaced by AI engines, which favor even-handed sourcing over
   marketing copy.

## 2. Structure follows the reader task

Select create, improve, consolidate or defer before choosing a page format.
The evidence-led brief must name the reader problem, intended action, original
contribution, inspectable supporting assets and a limitation. Service, feature,
comparison, documentation and interactive examples may fit better than articles.
Existing page content and query-to-page observations inform overlap review;
multiple ranking URLs are a signal to investigate, not proof of cannibalization.

Give the reader a clear answer and useful next action. Use headings, comparisons,
tables or steps when they help. No four-H2 requirement, question-heading quota,
introductory word band, mandatory exclusions section or universal closing verdict.
The brief can explicitly require ordered steps for a procedural task.

## 3. Length is advisory

The prompt and scripts share these planning ranges: pillar 1,500–2,200,
standard 1,000–2,000, supporting 700–1,400 words. They are editorial planning
ranges, not gates or search-engine targets. Stop when the reader's task is
answered; short service pages and narrow answers can be useful.

## 4. Structured data (schema.org / JSON-LD)

- `Article` + `BreadcrumbList` on every article page.
- Sitewide: `Organization` + `WebSite`, once, on the homepage.
- The site's main entity gets ONE schema type matched to what it actually is
  — `SoftwareApplication`, `Product`, `Service`, `LocalBusiness`, etc. Pick
  from `site-config.<project>.json`'s `schema_type` field; don't guess. If
  `SoftwareApplication`, use the most specific `applicationCategory` value
  that fits (e.g. `FinanceApplication`, not the generic `BusinessApplication`,
  if the product is finance-adjacent) — specificity helps categorization
  without contradicting the on-page positioning copy.
- `featureList` (if used) must name only features listed as real/live in
  `verified_facts` — never a `coming_soon` feature.
- Structured data must describe visible, accurate content. It does not create
  evidence for an assertion or guarantee a special search appearance.

## 5. Entity identity

Keep names, identifiers, categories and factual descriptions consistent.
The canonical definition is a reference, not mandatory identical copy in every
introduction, meta description and schema description. Tailor the description
to the page's actual purpose.

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
- Ban list (default — extend per-site in `site-config.<project>.json`): "delve",
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

## 8. Useful links

Use descriptive anchors and destinations that support the reader's next action
or evidence needs. Review internal paths and external source relevance. No link
count or placement quota. A draft with no links has unassessed link readiness.
Syntax checks alone do not establish usefulness.

## 9. Technical baseline and platform-specific claims

Make pages accessible to the intended crawler, keep meaningful dates honest,
and ensure structured data matches visible content. Record AI-search engine,
query, locale, observation date, cited URL and method separately from referrals
and conversions. Do not infer one outcome from another.

Google's generative-search guidance builds on ordinary SEO and useful original
content; no special AI markup, llms.txt, tiny chunks or writing style is required.
Other engines' behavior is platform-specific and needs its own dated evidence.

## 10. Review cadence

Choose production cadence by reader value and review capacity, not an invented
ranking benefit of a posting quota. Review published cohorts at declared 30/60/90
day windows. Diagnose accessibility, indexation, relevant impressions, clicks
and qualified actions in that order. Compare comparable periods and rates,
record seasonality and edits, and leave missing conversion data unknown.

## 11. Pre-publish gate

Before publishing anything generated with this framework, grep the draft
for placeholder/fabrication tells:

```
grep -inE "example\.com|lorem ipsum|TBD|FIXME|555-|Jane (S|Smith)|John (S|Smith)|Sample (Customer|Client)" draft.md
```

Any hit means a value that should have come from `site-config.<project>.json` was
left as a stand-in. Fix before publishing — don't ship placeholders.

**This grep only catches fabrication/placeholder tells.** The automated gate
also validates config shape, claim-evidence metadata, coming-soon mentions,
and nearby tier scope. These are conservative signals, not semantic proof
that the draft is true.

**Tested, not just theorized:** after adding `[TIER: ...]` tagging to
`verified_facts` and the matching prompt instruction (§2b), regenerating
the same article correctly named the gated tier in 2 of 3 places it
mattered — a real improvement over the untagged version, which named it
nowhere. The third mention still blurred two separate upgrade paths
("more bills" vs. "multiple members") into one muddled sentence. Tagging
reduces this error class; it does not eliminate it. Keep doing a manual
claim-and-tier read even on a fully tier-tagged config.

**Automated gate:** run `scripts/check_article.py --draft <file> --config
site-config.<project>.json --type <type> --query "<target query>" --manifest <reviewed.json> --brief <brief.json> --strict` before publishing.
Generation runs the same checks and writes non-PASS drafts only to
`output/.quarantine/` with a JSON receipt; it returns non-zero. The gate catches
config/evidence shape, placeholders, H1/query mismatch, coming-soon and
unscoped tier mentions, links, structure, and style signals. It still does NOT
prove that prose matches reality, intent, originality, or legal meaning: read
the final draft against the current source of truth every time.

## 11b. Opportunity evidence gate

Use `scripts/score_opportunities.py` with an
`article-forge.opportunity.v1` document before promoting a topic. Demand,
paid advertiser competition, organic competition, product fit, and content fit
are separate fields. Missing or stale demand/organic evidence returns
`needs-data`; organic consensus also requires at least five independent domains.
`scripts/collect_serper.py` may supply current SERP observations, but it must
not manufacture Google keyword difficulty or domain authority from result
counts. `organic_competition.editorial_difficulty` is optional evidence; it is
required only if a numeric prioritization score is requested, and it must carry
editorial semantics, rationale, evidence types, and evidence beyond a raw Serper
count. Counts and host totals alone are rejected. Content fit must also name an
unanswered question and at least one dated supporting source.

`intent_evidence` stores raw observed signals and may carry a reviewable
hypothesis. The hypothesis is never treated as ground truth; confidence over
90 requires at least three corroborating signals. `product_fit` must include a
first-party fact and a verified claim. `content_fit` must include an original
angle and a limitation. `freshness` records the refresh window and evidence,
while `evidence_confidence` is confidence in the evidence packet, not a
probability of ranking or citation. A score below 80 confidence can never
remain a `pursue` decision.

**For claim-level truth, run the automated verifier.** `scripts/verify_facts.py`
checks every entry in the config's `claim_evidence` against its source — a
live URL or a local file (`source_local`) — and records a verdict
(`verified` / `unsupported` / `inconclusive`) in
`claim-verification.<project>.json` next to the config. `check_article.py`
reads that ledger on every run and hard-fails the draft on any claim marked
`unsupported`; the fix is to replace the sentence with
`<!-- PLACEHOLDER: claim <id> not verifiable -->` or remove it. This covers
"does the source actually support this claim," not "is it scoped to the
right tier" — the tier question above is still a manual read. See
`AUTONOMY.md` for the full loop.

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

## Dated primary-source basis

Reviewed October 9, 2026 UTC (October 8 in Barbados):

- [Google people-first content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content): original value, clear sources, demonstrable experience, no preferred word count, no cosmetic date refreshing.
- [Google generative-search guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide): ordinary SEO and useful original material; no special AI markup or required writing style.
- [Google image guidance](https://developers.google.com/search/docs/appearance/google-images): visible content, contextual captions and descriptive alt text.

The numerical weights, length ranges, five-domain sampling and review cadence
are Forge editorial policy. They are not Google rules or calibrated predictors.
Refresh platform guidance against dated primary sources when it changes.
