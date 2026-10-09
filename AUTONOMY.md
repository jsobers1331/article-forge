# Autonomous Operation

Article Forge prepares evidence and guarded drafts. A human reviews semantics, coverage, originality and the publication decision. Automation never grants publication approval. See [EVIDENCE_SYSTEM.md](EVIDENCE_SYSTEM.md) for the versioned contracts and legacy migration.

1. **Every factual claim must exist in `claim_evidence` in the site config.** If a sentence asserts something about the business — a feature, a price, a statistic, a policy, a legal position — it must correspond to a `claim_evidence` entry. An unmapped material assertion is unverified and blocks readiness; absence of a record alone does not establish that the assertion is false.

2. **Claims are machine-verified by `scripts/verify_facts.py`.** The script reads each entry's source (`source_local` when present, otherwise `source_url`), strips it to text, snapshots it into `evidence/<slug>/`, asks the judge model for a strict-JSON judgment, and writes the result to `claim-verification.<slug>.json` next to the config. Two programmatic keys are then applied, and neither can be argued away by the model: a `verified` verdict whose quotes do not appear verbatim in the source is downgraded to `inconclusive`, and when any of the claim's `$` amounts is absent from the source's JSON-LD `Offer`/`Product` prices, a `verified` verdict is downgraded to `inconclusive` (the numeric second key — inert whenever a source carries no numeric structured-data prices).

   The judge defaults to OpenAI `gpt-4o-mini`; `--provider`/`--model` change it. It is deliberately a different model family from the writer, which is normally DeepSeek — never let the model that wrote the draft judge it. The judge prompt is blind: claim, scope, source label and source text, nothing else. It never sees a prior verdict, `status`, or `verified_on`; do not add them to `build_prompt`.

3. **Unsupported claims must never reach the article.** When `check_article.py` reports an unsupported claim, the article hard-fails. Replace the sentence with `<!-- PLACEHOLDER: claim <claim_id> not verifiable -->` or drop the claim entirely. Do not reword around it, and do not weaken `claim_evidence` to make the checker pass.

4. **Verification goes stale.** The ledger's `checked_at` timestamp is the freshness anchor. The exact claim text, scope, source URL and local source identity are fingerprinted. Source snapshots carry hashes; changed bindings, changed local source bytes, missing snapshots and legacy results require re-verification. Entries older than 30 days are stale and must be re-verified before publishing (`--max-age-days` changes the window). Never hand-edit `checked_at` to fake freshness.

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

## Guarded local loop

```bash
python3 scripts/verify_facts.py --config site-config.<slug>.json
python3 scripts/generate_article.py --config site-config.<slug>.json --topic-index 0 \
  --provider deepseek --brief editorial-brief.<slug>.json --out-dir /tmp/forge-drafts
# Review the quarantined draft and unsigned manifest proposal against the sources.
python3 scripts/check_article.py --config site-config.<slug>.json \
  --draft /tmp/forge-drafts/.quarantine/<article>.md --type standard --query '<query>' \
  --manifest claim-manifest.<slug>.json --brief editorial-brief.<slug>.json
```

Only claims used in the final draft are ledger-gated. An unused unsupported
entry does not block unrelated content; omitting a used assertion from its
manifest blocks coverage. All non-PASS generation results stay quarantined.
Missing, stale, inconclusive and disabled verification cannot return a passing
checker/report exit code. `--no-ledger` is diagnostic only.

The model judge is advisory. A matching quote, hash or signed manifest does
not prove truth. Humans must inspect source authority, scope, meaning and
assertions the heuristic misses. `check_publish.py` is a separate transport,
rendering and metadata diagnostic; it does not establish final-draft coverage.
Publication still requires explicit owner authorization.
