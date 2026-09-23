# RTK - Rust Token Killer (Codex CLI)

**Usage**: Token-optimized CLI proxy for shell commands.

## Rule

Always prefix shell commands with `rtk`.

Examples:

```bash
rtk git status
rtk cargo test
rtk npm run build
rtk pytest -q
```

## Meta Commands

```bash
rtk gain            # Token savings analytics
rtk gain --history  # Recent command savings history
rtk proxy <cmd>     # Run raw command without filtering
```

## Verification

```bash
rtk --version
rtk gain
which rtk

## Agent handoff

When Codex is working through the Claude bridge, use RTK for shell commands and return a concise handoff with only `CHANGED`, `CHECKS`, and `BLOCKERS`. Do not paste long logs or source code into the parent agent context.
```
