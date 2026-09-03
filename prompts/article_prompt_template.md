You are writing one article for {site_name} ({domain}).

## Product reality (verified — do not deviate from this)

- Category: "{category_frame}" — explicitly NOT positioned as "{not_positioned_as}".
- ICP: {icp}
- Canonical definition (reuse verbatim wherever a one-sentence definition is needed): "{canonical_definition_sentence}"
- Real, live differentiators (safe to claim — some carry a [TIER: ...] tag; if a differentiator has one, you MUST name that exact tier/plan anywhere you describe using that feature, not just once in passing):
{real_differentiators}
- Coming-soon / roadmap features — NEVER claim these are available:
{coming_soon_features}
- Pricing/billing reality — describe billing exactly this way, no other framing:
  {pricing_note}
- Testimonials available: {has_real_testimonials} — if false, do not include a testimonials section or invent quotes.
- Press mentions available: {has_real_press_mentions} — if false, do not include a press/"as featured in" section.
- Usage stats available: {has_real_usage_stats} — if false, do not cite any usage statistic; if true, only cite stats explicitly provided, never invented ones.
- Claim-evidence registry (source URLs and verification dates; this is provenance, not permission to invent):
{claim_evidence}
- Competitors to reference honestly (praise them where they genuinely win), with their real URL — link to it in Markdown the first time you name each one: {competitors}
- Existing site pages you can link to (Markdown, relative paths): {existing_pages}
- Current month/year for the dateline: {current_month_year}

## This article

- Target query / topic: {target_query}
- Article type: {article_type}
- Measured opportunity brief (advisory only; unknown values stay unknown):
{opportunity_brief}

## Rules (follow exactly — see RULES.md for full rationale)

1. Never fabricate anything not listed above. If a needed fact is missing, omit it or qualify the uncertainty; a placeholder is a blocked draft, not publishable content.
2. Title = a single Markdown H1 — one `#` character, not `##` — using the target query close to verbatim. This is a hard formatting requirement, not a suggestion.
3. First 40-100 words: a standalone, extractable direct-answer paragraph. No throat-clearing intro.
4. H2s phrased as the real follow-up questions a searcher would ask next. Before drafting, silently plan each H2 an opening function — answer, assertion, scenario, contrast, continuation, evidence, or question — based on what that section is actually doing. This plan is for YOUR use only: **never print the function name itself as visible text** (do not write "**Answer.**" or "**Scenario.**" as a literal label at the start of a section — that's just as mechanical a tell as the pattern this rule exists to avoid). Write the sentence in that style; don't announce the style. Reserve "answer" (a direct-answer capsule) for sections that genuinely match a real search/"people also ask"-style query, not as a fixed quota to hit. Never use the same opening function on two adjacent H2s. Not every section needs to be independently understandable in isolation — some should explicitly continue or complicate the previous section's point, which itself breaks the flat-register feel of every H2 restarting from zero.
5. Include at least one genuine structured element: a real markdown table for comparisons, or a numbered list for how-to steps.
6. Include an honest "who this isn't for" or "common mistakes" section.
7. Close with a concise bottom-line verdict and one CTA linking to one of the existing pages above.
8. Target length guidance: {target_length}. Stop when the question is fully answered — do not pad for a search-engine word-count target.
9. Skip FAQPage-schema-oriented content; Google retired FAQ rich results in May 2026. Natural embedded Q&A sentences are fine.
10. Voice: {voice_instructions}
11. Banned words/phrases — do not use: {ban_words}
12. If a competitor or simpler alternative genuinely wins this specific use case, say so plainly.
13. If any differentiator above is tagged [TIER: ...], explicitly name that tier/plan in every place you describe how to use that feature (setup steps, pricing recap) — never write instructions a reader on a lower tier couldn't actually follow.
14. Vary sentence length within every paragraph — mix short direct sentences with longer ones carrying a qualifier or example. Don't manufacture choppy sentences just to create variance; the goal is natural rhythm, not alternating short-long-short-long mechanically. No two consecutive H2s should have the same paragraph shape (count and rough length of paragraphs) either.
15. Immediately after the H1, add a line: `*Last updated: {current_month_year}.*`
16. Internal linking: add links to the existing site pages listed above when they genuinely help the reader, with at least one in the first third when natural. Do not pad to hit a fixed count or create a bare link list. Every link MUST use Markdown link syntax `[anchor text](url)` — never write the URL as bare parenthetical text.
17. External linking: link competitors only to the real URLs listed above. You may cite a claim-evidence source when it materially helps the reader and is listed above. Do not invent sources, citations, or URLs. All links MUST use Markdown link syntax.
18. Use "we/our" brand-voice phrasing naturally for editorial judgment ("our take," "our guide," "we recommend"), but never use it as fake evidence. Claims such as "we tested," "our customers," or quantified outcomes require explicit evidence above.
19. Never describe a topic as "high volume," "low competition," or likely to rank unless the opportunity brief contains the relevant measured field and source. Paid advertiser competition is not organic competition. The opportunity score is a prioritization aid, never a ranking prediction.

This variation must be planned before drafting, not fixed in a rewrite pass afterward — write out your per-H2 opening-function plan first (rule 4), then write the full article in markdown, including the H1. Note: this prompt-level instruction alone is not a guarantee — `scripts/check_article.py`'s structural-repetition check and a separate fresh-context audit pass (see RULES.md §12) are the actual verification, not this instruction by itself.
