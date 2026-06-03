# Plan: Review & Automate Claude Code Plugin Installation

## Context
A wishlist of 14 Claude Code plugins needs reviewing and its installation automated.
Investigation found **all 14 exist in the official marketplace** (`claude-plugins-official`,
already registered on this machine), **none require interactive `userConfig`**, so installs
run fully non-interactively via the CLI. Two are already installed. Goal: a reusable script
(`install-plugins.sh`) that installs the remaining twelve at user (global) scope, plus
documented post-install setup for the three MCP-backed plugins.

## Review: wishlist → marketplace mapping
All map to `claude-plugins-official`.

| Wishlist name        | Plugin id              | Status              | Notes |
|----------------------|------------------------|---------------------|-------|
| Frontend Design      | `frontend-design`      | already installed   | — |
| Code Simplifier      | `code-simplifier`      | already installed   | — |
| Superpowers          | `superpowers`          | to install          | brainstorming + subagent-driven dev |
| Context7             | `context7`             | to install (MCP)    | needs Node/`npx`; optional API key |
| Code Review          | `code-review`          | to install          | multi-agent PR review |
| Skill Creator        | `skill-creator`        | to install          | — |
| GitHub               | `github`               | to install (MCP)    | needs `GITHUB_PERSONAL_ACCESS_TOKEN` |
| Playwright           | `playwright`           | to install (MCP)    | needs `npx` + `npx playwright install` |
| CLAUDE.md Management  | `claude-md-management` | to install          | — |
| Feature Dev          | `feature-dev`          | to install          | — |
| TypeScript LSP       | `typescript-lsp`       | to install          | language-server intelligence |
| Security Guidance    | `security-guidance`    | to install          | — |
| Ralph Loop           | `ralph-loop`           | to install          | iterative self-referential loops |
| Claude Code Setup    | `claude-code-setup`    | to install          | recommends hooks/skills/MCP |

→ **12 to install.**

## Decisions (confirmed with user)
- **Scope:** user / global (`--scope user`).
- **MCP plugins:** install all three; document external setup, don't block on it.
- **Delivery:** reusable script (`install-plugins.sh`), then run it.

## Implementation
1. `install-plugins.sh` — idempotent loop over the 12 ids, `claude plugin install <id>@claude-plugins-official --scope user`, with failure tracking and a post-install setup note. (Already in this repo.)
2. Run it: `bash install-plugins.sh`.
3. Verify: `claude plugin list` shows all 14 plugins enabled.

## Post-install setup (documented, not blocking)
- **github** — `export GITHUB_PERSONAL_ACCESS_TOKEN=...` so the MCP server authenticates.
- **playwright** — `npx playwright install` once to download browsers.
- **context7** — needs Node/`npx`; optional API key raises rate limits.

## Verification (end-to-end)
1. `bash install-plugins.sh` finishes with no failures.
2. `claude plugin list` shows 14 plugins, all enabled.
3. Restart Claude Code / `/reload-plugins`; confirm new commands/skills appear
   (`/code-review`, `/feature-dev`, superpowers, etc.) and MCP servers register.
4. GitHub MCP connects only after the PAT env var is set — expected.

## Notes / risks
- `claude plugin install` is non-interactive; no `userConfig` required for any of the 14.
- New components may need a restart / `/reload-plugins` to load.
