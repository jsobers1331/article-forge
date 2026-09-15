# Autonomous Operation

article-forge is built to run without a human in the loop — research, write, check, ship. That only works if everything the output asserts about the business is traceable to a source. This file is the contract for that.

1. **Every factual claim must exist in `claim_evidence` in the site config.** If a sentence asserts something about the business — a feature, a price, a statistic, a policy, a legal position — it must correspond to a `claim_evidence` entry. Anything asserted in the article body without an entry is a fabrication, even if it happens to be true.

2. **Claims are machine-verified by `scripts/verify_facts.py`.** The script reads each entry's source (`source_local` when present, otherwise `source_url`), strips it to text, snapshots it into `evidence/<slug>/`, asks the model for a strict-JSON judgment, and writes the result to `claim-verification.<slug>.json` next to the config. A claim is only `verified` when at least one returned quote appears verbatim in the source; a `verified` verdict with no matching quote is downgraded to `inconclusive`.

3. **Unsupported claims must never reach the article.** When `check_article.py` reports an unsupported claim, the article hard-fails. Replace the sentence with `<!-- PLACEHOLDER: claim <claim_id> not verifiable -->` or drop the claim entirely. Do not reword around it, and do not weaken `claim_evidence` to make the checker pass.

4. **Verification goes stale.** The ledger's `checked_at` timestamp is the freshness anchor. Entries older than 30 days are stale and must be re-verified before publishing (`--max-age-days` changes the window). Never hand-edit `checked_at` to fake freshness.

5. **The ledger and `evidence/` are generated artifacts.** `claim-verification.<slug>.json` and the `evidence/` snapshots are written by the verifier; they are never hand-authored or hand-edited. To change a verdict, change the source or the claim and re-run the verifier. Both are local-only artifacts and gitignored by design.

## Typical autonomous loop

```
python3 scripts/verify_facts.py --config site-config.<slug>.json
python3 scripts/check_article.py --config site-config.<slug>.json output/<article>.md
```

`check_article.py` hard-fails on an unsupported claim, warns when the ledger is missing, stale, or `inconclusive`, and can skip the ledger check entirely with `--no-ledger`.
