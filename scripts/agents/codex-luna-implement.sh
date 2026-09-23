#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "This bridge must run inside a Git repository." >&2
  exit 2
}

if [[ "$repo_root" != "/home/starryboyjosh/Dev/Projects/HiTrendy/hitrendy_foundation" ]]; then
  echo "Refusing to run outside the HiTrendy workspace: $repo_root" >&2
  exit 2
fi

if (($# == 0)); then
  echo "Usage: $0 \"implementation task\"" >&2
  exit 2
fi

task="$*"
worker_rules=$'\n\nCodex routing: main worker and every internal submodel must use gpt-5.6-luna with max reasoning. Use at most three internal submodels for bounded, disjoint work. Do not create another coordinator or delegate recursively.'
handoff_rules=$'\n\nHandoff protocol: use RTK for shell commands whenever possible. Keep the final response caveman-compressed and return only these sections: RESULT, CHANGED, BEHAVIOR, VALIDATION, CONTRACT DEVIATIONS, BLOCKERS, REVIEW HOTSPOTS, UNRESOLVED ASSUMPTIONS. Preserve failures, skipped checks, interface/schema/migration/dependency changes, security/privacy risks, and unresolved assumptions. Do not paste source code or long logs unless required to explain a failure.'

exec codex exec \
  --cd "$repo_root" \
  --model "gpt-5.6-luna" \
  --sandbox workspace-write \
  --enable multi_agent \
  --config 'agents.enabled=true' \
  --config 'agents.max_concurrent_threads_per_session=3' \
  --config 'agents.default_subagent_model="gpt-5.6-luna"' \
  --config 'agents.default_subagent_reasoning_effort="max"' \
  --config 'model_reasoning_effort="max"' \
  --config 'approval_policy="never"' \
  --color never \
  "${task}${worker_rules}${handoff_rules}"
