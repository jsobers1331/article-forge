# Autonomous Operation

article-forge is built to run without a human in the loop — research, write, check, ship. That only works if everything the output asserts about the business is traceable to a source. This file is the contract for that.

1. **Every factual claim must exist in `claim_evidence` in the site config.** If a sentence asserts something about the business — a feature, a price, a statistic, a policy, a legal position — it must correspond to a `claim_evidence` entry. Anything asserted in the article body without an entry is a fabrication, even if it happens to be true.

2. **Claims are machine-verified by `scripts/verify_facts.py`.** The script reads each entry's source (`source_local` when present, otherwise `source_url`), strips it to text, snapshots it into `evidence/<slug>/`, asks the judge model for a strict-JSON judgment, and writes the result to `claim-verification.<slug>.json` next to the config. Two programmatic keys are then applied, and neither can be argued away by the model: a `verified` verdict whose quotes do not appear verbatim in the source is downgraded to `inconclusive`, and when the claim's `$` amounts and the source's JSON-LD `Offer`/`Product` prices share no value, a `verified` verdict is downgraded to `inconclusive` (the numeric second key — inert whenever a source carries no numeric structured-data prices).

   The judge defaults to OpenAI `gpt-4o-mini`; `--provider`/`--model` change it. It is deliberately a different model family from the writer, which is normally DeepSeek — never let the model that wrote the draft judge it. The judge prompt is blind: claim, scope, source label and source text, nothing else. It never sees a prior verdict, `status`, or `verified_on`; do not add them to `build_prompt`.

3. **Unsupported claims must never reach the article.** When `check_article.py` reports an unsupported claim, the article hard-fails. Replace the sentence with `<!-- PLACEHOLDER: claim <claim_id> not verifiable -->` or drop the claim entirely. Do not reword around it, and do not weaken `claim_evidence` to make the checker pass.

4. **Verification goes stale.** The ledger's `checked_at` timestamp is the freshness anchor. Entries older than 30 days are stale and must be re-verified before publishing (`--max-age-days` changes the window). Never hand-edit `checked_at` to fake freshness.

5. **The ledger and `evidence/` are generated artifacts.** `claim-verification.<slug>.json` and the `evidence/` snapshots are written by the verifier; they are never hand-authored or hand-edited. To change a verdict, change the source or the claim and re-run the verifier. Both are local-only artifacts and gitignored by design.

6. **Research red lines.** These are never negotiable:
   - Facts about a competitor come only from that competitor's own page — never from third-party summaries, listicles, or reviews.
   - No claim may rest on the model's internal knowledge. A fact the model "knows" but the source snapshot does not show is not a fact.
   - A regulatory or legal figure without the primary official document (the regulator's own page, the statute, the government guidance) is **deleted, not hedged**. A hedge is still an assertion.
   - First-hand experience claims (counts, timelines, what "we" do) with no `claim_evidence` entry are **deleted, never softened**.
   - No superlatives: no "best", "number one", "leading", "cheaper than".
   - No negative-existence claims about competitors ("X doesn't offer Y").
   - Never use a Wayback/archive snapshot as support for present-tense pricing. Pricing must come from the live page.

7. **`inconclusive` is a to-do, not a pass.** Work the fallback ladder in order, stopping at the first rung that lands: (1) restate the claim as the weaker statement the source actually supports; (2) replace the assertion with a pointer to the source ("see their pricing page"); (3) delete the sentence; (4) if the fact matters, set `"needs_evidence": true` on the `claim_evidence` entry — a parked marker the loop must not publish around — and re-run the verifier once a source exists.

## Typical autonomous loop

```
python3 scripts/verify_facts.py --config site-config.<slug>.json
python3 scripts/check_article.py --config site-config.<slug>.json output/<article>.md
python3 scripts/check_publish.py --config site-config.<slug>.json --url <live-url> --type standard
```

`check_article.py` hard-fails on an unsupported claim, warns when the ledger is missing, stale, or `inconclusive`, and can skip the ledger check entirely with `--no-ledger`. `check_publish.py` reads the same ledger for the live page, so an `unsupported` claim blocks the published URL too; it takes `--no-ledger` as well.
