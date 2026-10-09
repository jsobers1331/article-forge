# Evidence-led editorial workflow

Article Forge prepares reviewable drafts and decisions for any configured site.
It never treats a content score as a ranking probability or publishes from a
passing gate. Every project retains its own `site-config.<project>.json`.

## Claim verification and legacy migration

`verify_facts.py` writes `article-forge.claim-ledger.v2`. Every result contains:

- `claim_id`, `status` and the actual `checked_at` timestamp.
- `claim_fingerprint`: SHA-256 of canonical JSON containing the binding schema,
  exact claim text, verification scope, source URL and local source identity.
- `snapshot_path`, `snapshot_sha256`, `source_raw_sha256` and an evidence root.
- Exact evidence quotes, missing aspects, provider/model and limitations.

The raw-source hash records acquisition; the text-snapshot hash records what
was inspected. Local source bytes can be checked again without network access.
For remote sources, unchanged identity plus a fresh intact snapshot permits
reuse until the declared freshness window expires; reuse does **not** assert
that the remote page has remained unchanged. Use `--claim-id` to force a new
observation when a change is suspected. Snapshots use time/content suffixes so
new observations do not overwrite prior source evidence.

A legacy result without bindings or snapshot hashes cannot support a verified
pass or be carried forward as verified. Run the verifier against the actual
source. It records a new date only after a real verification attempt. Outside
an explicitly selected claim scope, invalid old results become inconclusive
without changing their original dates. No automatic owner-config migration,
source copying or secret handling occurs.

The model judge is advisory and sees no previous verdict. All returned quotes
must match exactly; every claimed structured-data dollar price must match.
A failed provider request is inconclusive and its exception text is withheld.
These checks cannot establish source authority or complete semantic entailment.

## Final-draft manifest

`article-forge.claim-manifest.v1` binds the **exact final draft** with
`draft_sha256`. `assertions` contains one record per material sentence/line:

| Field | Meaning |
| --- | --- |
| `sentence_id` | Stable occurrence ID from `claim_manifest.sentences` |
| `sentence` | Exact normalized visible sentence/line |
| `claim_ids` | Registry evidence records actually used |
| `evidence_binding` | Hash of ordered claim IDs, claim fingerprints and snapshot hashes |
| `semantic_review` | Required for paraphrases: reviewer, assertion hash, evidence binding and `supported_without_strengthening` verdict |

`human_review` must name `reviewer`, actual timezone-aware `reviewed_at`, the
same `draft_sha256`, `coverage: all_material_assertions` and `limitations`.
The reviewer reads **the whole draft**, maps missing assertions and inspects
source scope/authority. They must not merely sign the heuristic worklist.

The deterministic detector covers obvious prices, capabilities, tiers,
statistics, timelines, policies, first-hand experience, quotations and numeric
identifiers. It is incomplete: implication, negation, written-out quantities
and context still need human review. Numbers must appear in both the bound
claim and source snapshot; quotations and identifiers must appear in the
snapshot. Changed maps, reused IDs, duplicate occurrences and obvious universal
or first-hand strengthening fail. An unsupported unused registry entry does
not block unrelated content. A used claim omitted from the manifest blocks
coverage; an exact visible registry claim is also selected for ledger checking.

A manifest is a provenance map and review receipt, **not factual proof**.
No model performs semantic extraction in this implementation. If one is added,
its provider, model, output hash and limitations must be recorded and tested
with stubbed responses before it can participate in review.

## Evidence-led brief and page choice

`article-forge.editorial-brief.v1` requires `target_query`, `reader_problem`,
`intended_action`, `original_contribution`, `limitation` and supporting assets.
Each asset records its path, byte hash, source, rights, kind and role. An
inspectable evidentiary asset is required; a self-declared experience flag or
an AI-generated illustration cannot substitute for one.

`page_decision` records `action` (create/improve/consolidate/defer), `page_type`
(article/service/feature/comparison/documentation/interactive_example), reason,
reviewer, actual review time and existing URLs for improve/consolidate.
`existing_page_evidence` is an explicit list of URL + content snapshot path/hash.
An empty list is allowed for a new site. `query_page_observations` records
observations or an explicit unavailable reason. The planner also supplies a
review-only overlap signal from actual supplied page content and query-page
rows. Multiple URLs do not prove harmful cannibalization.

Screenshots and photographs carry captions, descriptive visible-content alt
text and `visible_content_reviewed_by`; interviews carry permission records.
Generated images are illustrations, never evidence of product behavior or
local first-hand experience. Optional `requires_ordered_steps: true` selects
procedural structure. Word bands are shared advisory planning ranges.

## SERP snapshots

`article-forge.serp-snapshot.v2` includes:

- `keyword`, timezone-aware `captured_at`, `locale.country`, `locale.language`
  and relevant location; collection `provenance.method` and `provenance.source`.
- At least five independent registrable domains, deduplicated using a bundled
  public suffix list, including private hosting suffixes. Sibling subdomains
  are not independent observations. This threshold is editorial policy.
- Competitors with URL, extracted `headings`, `subtopics`, `entities`, and
  `extraction.status: complete`, `extraction.complete: true`. `extraction.sha256`
  binds canonical JSON of those three arrays.
- Per-page `source_snapshot.text`, its SHA-256, exact source URL and actual
  capture time. Empty observed extraction arrays are allowed but provide no
  consensus score. Missing/failed extraction is invalid evidence.

A different target query requires `reviewed_query_cluster` with explicit
queries, reviewer, review time and rationale. Default freshness is 30 days.
`config.serp_policy` can set `max_age_days`, country, language and location;
otherwise locale follows `research.serper.gl/hl/location` (US/en defaults).

The shared validator is used by generation, scoring, reports and discovery
reports. Generation rejects an invalid supplied snapshot before a writer call.
An invalid snapshot yields unassessed SERP pillars and explicit reasons in
reports. A complete sample without observed consensus has the distinct
`serp_sample_valid_no_consensus` status. Raw `article-forge.serp.v1` Serper
observations are discovery inputs, not extracted-page consensus snapshots.
Never wrap them in v2 with invented dates, source text or extraction status.

Reports use `article-forge.report.v2`. Unknown pillars and aggregate totals are
`null`; Markdown displays “unassessed.” E-E-A-T is unassessed rather than inferred
from booleans or brand phrases. Intent cues are an explicitly limited content
heuristic, independent of article length/type. Gate results are separate from
editorial scores. Disabled/missing checks never establish readiness.

## Complete local draft/review commands

Use a writable output folder outside the repository; no credentials are needed
for local review. Provider calls, when requested, use the owner's direct account.

```bash
python scripts/generate_article.py --config site-config.<project>.json \
  --topic-index 0 --provider deepseek --brief editorial-brief.<project>.json \
  --snapshot serp-snapshot.<project>.json --out-dir /tmp/forge-drafts
```

The first draft normally goes to quarantine with reports and an **unsigned**
`.manifest-proposal.json`. For a supplied draft, prepare the worklist explicitly:

```bash
python scripts/claim_manifest.py --config site-config.<project>.json \
  --draft /tmp/forge-drafts/.quarantine/<article>.md \
  --out claim-manifest.<project>.json
```

After inspecting source evidence and recording real human review:

```bash
python scripts/generate_article.py --config site-config.<project>.json \
  --topic-index 0 --provider deepseek --brief editorial-brief.<project>.json \
  --manifest claim-manifest.<project>.json \
  --review-draft /tmp/forge-drafts/.quarantine/<article>.md \
  --snapshot serp-snapshot.<project>.json --out-dir /tmp/forge-reviewed
```

This performs no writer call. The provider flag remains a CLI compatibility
argument in review mode; attribution comes from a matching original report,
or stays unknown for an owner-supplied draft. The original draft/report must
have matching hashes. Every non-PASS result exits 1 and stays in quarantine.
Passing drafts retain prompt/config/draft/evidence hashes, reviewer, candidate,
provider/model and Forge commit in reports/receipts. Reports identify that a
local tree may contain uncommitted changes; commit before a production handoff.

The same inputs work with `check_article.py` and `score_article.py` via explicit
`--draft --config --query --manifest --brief --snapshot`. Both return nonzero
when blocked. `--no-ledger` produces diagnostic blocked results. `--force`
replaces a passing output; it does not bypass evidence gates.

## Publication registry and measured review

`publication_registry.py` writes only a named local registry. The owner supplies
actual publication time, canonical URL, content version, locale, declared
`[30, 60, 90]` review windows and conversion definition in a receipt. Bind that
receipt to a passing draft report using `--report`; no article is published.

```bash
python scripts/publication_registry.py --registry publication-registry.<project>.json \
  --identity <site-identity.json> --publication <owner-publication-receipt.json> \
  --report /tmp/forge-reviewed/<article>.report.json
python scripts/publication_registry.py --registry publication-registry.<project>.json \
  --publication-id <record-id> --gsc <existing-gsc-export.json> \
  --indexing <existing-indexing-export.json> --access <dated-access.json> \
  --actions <exact-period-attributed-actions.json> --review-out outcome-review.<project>.json
```

The versioned registry joins candidate, evidence packet, final draft, reviewer,
provider/model, Forge commit, canonical URL, publish date and immutable content
version. Site identity lists a canonical host and explicitly equivalent hosts;
original URLs remain in observations. Path case, trailing slashes and queries
are not silently merged. Writes are locked and atomic.

The export adapter accepts existing GSC/indexation collector schemas. Page rows
are observed site performance, not market demand. Anonymous/truncated query
omissions and absent rows remain unknown. Export locale granularity is recorded
separately from the publication cohort. Qualified actions and conversions need
a matching period, URL, source hash and owner-defined attribution. Absence of
conversion evidence is not zero conversions.

The review engine emits one approval-held recommendation per URL: keep, improve,
consolidate, refresh or defer. It diagnoses accessibility → indexing → relevant
impressions → clicks → qualified actions. It holds stale/short/absent observations
and future cohort windows. Consolidation requires a human overlap decision.
Comparisons use rates, never raw 28-day vs 90-day totals, and refuse changed
scope, overlapping periods, content edits or unconfirmed seasonality.

AI-search records name engine, query, locale, time, method and cited URL, with
availability, observed citation, referrals and conversions as separate fields.
The implementation creates no schedules and changes no provider settings.

## Workflow evaluation

`evaluate_workflows.py --input <receipts.json> --out <scorecard.json>` accepts
`article-forge.workflow-evaluation.v1`: a fixed query set across at least two
businesses and current/evidence-led runs with reviewer, evidence hash, commit,
provider/model and measured editorial metrics. It reports factual accuracy,
useful original contribution, page choice, evidence validity, human review
minutes, cost USD and elapsed seconds. Unknown observations stay unknown.
At least five paired queries are required for a descriptive comparison;
holdouts are excluded from training summaries and counted separately. Published
cohorts carry actual 30/60/90-day receipts. Weights are not automatically changed.

Synthetic regressions verify mechanics, not ranking impact, causal improvement
or a production benchmark. Real effectiveness needs owner-approved published
cohorts, comparable outcome observations and enough independent samples.
