<!-- PERSONAL CODEMAP GUARD -->
## Code map and targeted grounding

Read `CODEMAP.md` before scanning this repository. It is the generated orientation map and its
commit marker must match the commit under review or its first parent (the pre-commit generator
runs before Git creates the new commit). Use exact `git grep`/file reads as authority for
implementation details; the local retrieval index is only for ranking likely analogs.

For substantive work, refresh the local index lazily when available:
`node "$HOME/Personal/personal-agentic-engineering/scripts/codemap.mjs" --repo "$PWD" --ensure`

Before substantive work, confirm the agent is in the intended checkout:
`python3 "$HOME/Personal/ceobrain/scripts/check_worktree.py" --path "$PWD" --json`
Codex, Kimi, Claude, and other agents use this same runtime-neutral check. When a task has a
known branch/worktree contract, add `--expect-branch`, `--expect-path`, and `--expect-base`; use
`--require-up-to-date-base` before integration or rebasing.

Keep the final `CODEMAP.md` change with the source commit. The pre-commit hook generates it, the
pre-push hook validates the exact commit being pushed, and CI validates pushes to the main branch.
<!-- END PERSONAL CODEMAP GUARD -->

