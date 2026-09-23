# CLAUDE.md — HiTrendy Repository Guidance

Read `AGENTS.md` first. This repository is documentation-led, contract-first, and split into backend/frontend packages.

## Instruction order

1. Explicit user request
2. Applicable `AGENTS.md`
3. Accepted contracts and schemas
4. Relevant product and architecture documentation
5. This file
6. Existing implementation behavior

If applicable guidance conflicts, stop affected work and ask the main coordinator. Never silently choose.

## Repository map

- Product/UX/architecture: `docs/00-product/` through `docs/06-implementation/`, plus `docs/09-beta/`
- Contracts: `contracts/schemas/`
- Backend: `starter/backend/` (Python API, migrations, providers, tests)
- Web: `starter/web/` (Next.js app, components, API client, tests)
- Validation and bridges: `scripts/`
- Repository manifest: `project-manifest.yaml`

Read only relevant documentation. Preserve AGENTS.md token guards. Use repository-specific commands and package boundaries.

## Coordinator and delegation

- Main Claude session is sole coordinator and final reviewer.
- Main Claude owns product interpretation, contracts, architecture, file ownership, integration order, validation, and residual-risk reporting.
- Use at most one read-only Claude agent at a time: `hitrendy-explorer` for evidence or `hitrendy-reviewer` for actual-diff review.
- Codex is implementation writer. For code changes, use `codex-luna-implement` and invoke `rtk proxy ./scripts/agents/codex-luna-implement.sh` with a complete brief.
- Bridge enables up to three internal Codex submodels. Main worker and every submodel must use `gpt-5.6-luna` with `max` reasoning. Submodels implement bounded slices; they do not coordinate or delegate recursively.
- Default to one Luna worker. Parallel work requires frozen contracts, disjoint write ownership, no semantic overlap, and known integration order. Keep shared contracts, migrations, generated files, dependencies, and lockfiles ordered.
- After delegation, Claude reviews actual status, changed paths, full diff, tests, and validation. Worker summaries never prove correctness.
- Do not make substantive application fixes directly after delegation. Request another Luna pass; direct edits are limited to unambiguous mechanical corrections and must be disclosed.

## Contracts and ownership

Before medium/high-risk delegation, record objective, risk, current/target behavior, frozen inputs/outputs/errors/side effects/persistence, allowed paths, reserved paths, acceptance criteria, validation, and integration order.

Workers must preserve public contracts, provider boundaries, authorization, persistence semantics, and unrelated local changes. Stop and report a blocker when a contract or ownership decision is missing.

## Knowledge graph

When `graphify-out/GRAPH_REPORT.md` exists, inspect it before broad searches and confirm important findings in source. Use Graphify for relationship questions when repository size justifies it; raw search remains valid for small repositories. Source, accepted contracts, tests, and validated behavior remain authoritative.

## Product and architecture invariants

- HiTrendy provides personalized creation assistance, not generic chat. Generated behavior must use applicable profile, objective, channel, tone, request, product, and safety constraints.
- Dependency direction: UI -> application service -> domain -> provider interface -> external model/storage.
- Domain code must not depend on UI, transport, provider SDKs, storage SDKs, or database clients. Provider-specific data stops at provider boundaries.
- Keep providers replaceable, demo mode credential-free, generated artifacts editable, and user-visible text Spanish unless it is a technical identifier.
- Treat auth, user data, prompts, generated content, secrets, logging, exports, deletions, migrations, and provider payloads as high risk. Never log secrets, tokens, or unnecessary private content.

## Validation and completion

- Prefix shell commands with `rtk`; use `rtk proxy` when complete output is needed.
- Run focused checks plus applicable backend lint/tests, web typecheck/lint/tests/build, schema/contract validation, migrations, and E2E checks.
- Verify commands tested the changed package and behavior; do not trust silent or filtered output.
- Done means requested behavior exists, contracts and architecture hold, tests pass, docs stay synchronized, actual diff was reviewed, and residual risks are reported.

## Handoffs and Git

Compact handoffs must preserve:

`RESULT`, `CHANGED`, `BEHAVIOR`, `VALIDATION`, `CONTRACT DEVIATIONS`, `BLOCKERS`, `REVIEW HOTSPOTS`, and `UNRESOLVED ASSUMPTIONS`.

Never compress away failures, skipped validation, public interface/schema/migration/dependency changes, security/privacy/data-loss risks, or assumptions. Never treat handoff as diff review.

Preserve existing user changes. Do not use destructive Git commands. Do not commit, push, rebase, merge, or alter remote branches unless explicitly requested. Avoid broad staging such as `git add .`.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
rtk uv run <cmd>        # Compact uv project command output
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->
