#!/usr/bin/env bash
# Install the wishlist Claude Code plugins from the official marketplace.
# Idempotent: re-running for an already-installed plugin is a safe no-op.
set -uo pipefail

MARKET="claude-plugins-official"

# 12 plugins to install at user (global) scope.
# (frontend-design and code-simplifier are intentionally omitted — already installed.)
PLUGINS=(
  superpowers
  context7
  code-review
  skill-creator
  github
  playwright
  claude-md-management
  feature-dev
  typescript-lsp
  security-guidance
  ralph-loop
  claude-code-setup
)

failed=()
for p in "${PLUGINS[@]}"; do
  echo "==> installing ${p}@${MARKET}"
  if ! claude plugin install "${p}@${MARKET}" --scope user; then
    echo "!! failed: ${p}"
    failed+=("${p}")
  fi
done

echo
if [ ${#failed[@]} -eq 0 ]; then
  echo "All plugins installed. Verify with: claude plugin list"
else
  echo "Finished with failures: ${failed[*]}"
fi

cat <<'NOTE'

--- Post-install setup (MCP-backed plugins) ---
github     : export GITHUB_PERSONAL_ACCESS_TOKEN=<token>  (add to your shell profile)
playwright : run once -> npx playwright install           (downloads browsers)
context7   : needs Node/npx on PATH; works without a key (optional API key raises limits)

You may need to restart Claude Code or run /reload-plugins for new components to load.
NOTE
