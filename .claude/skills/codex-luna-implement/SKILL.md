---
name: codex-luna-implement
description: Delegate HiTrendy implementation work to Codex Luna at max reasoning, optionally using up to three bounded Luna submodels, then have Claude review the resulting diff. Use when code changes are requested in this repository.
---

# Codex Luna implementation bridge

Claude is the coordinator and reviewer for this repository. Do not edit application code directly when an implementation task is requested.

1. Inspect the relevant requirements and existing code enough to write a precise implementation brief.
2. Invoke the repository bridge with the complete task. The bridge enables Codex multi-agent mode with up to three internal submodels; all use gpt-5.6-luna with max reasoning:

   ```bash
   rtk proxy ./scripts/agents/codex-luna-implement.sh "Implement <task>. Follow AGENTS.md. Preserve unrelated worktree changes. Add/update tests and run proportionate validation. Return a concise summary of changes and checks."
   ```

3. Wait for Codex to finish writing the code.
4. Read Codex's compact `RESULT` / `CHANGED` / `VALIDATION` / `BLOCKERS` handoff, then inspect actual diff yourself.
5. Review contracts, authorization boundaries, provider interfaces, tests, error/loading/empty/success states, accessibility, and security.
6. Report concrete findings first. Do not silently repair the implementation; ask the user to delegate another Luna pass or explicitly authorize Claude to edit.

The bridge is restricted to this repository, uses Codex gpt-5.6-luna with max reasoning, enables up to three internal Luna submodels, and grants only workspace-write sandbox access. Codex may modify files in this workspace without an interactive approval prompt because this bridge is explicitly invoked for implementation. Internal submodels must stay bounded and must not create coordinators or recursively delegate.

RTK reduces terminal-output noise inside the writer. Caveman is used only for the inter-agent handoff summary; it does not hide the real diff or replace review.
