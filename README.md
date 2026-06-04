# claude-tools

One entry point to **explore, (un)install, batch, and evaluate** Claude Code
instruments — and to share curated **bundles** of them per workflow or curator.

It reads the local plugin catalog cache for instant, offline search/eval and shells
out to the `claude` CLI only for mutating actions. Curated bundles live in
[`bundles.yaml`](bundles.yaml) — that file *is* the shareable artifact: fork it,
edit it, pass it around.

> Origin: this repo started as a one-off plugin-install script
> ([`install-plugins.sh`](install-plugins.sh), [`PLAN.md`](PLAN.md)) and grew into the
> general `claude-tools` CLI.

## Install

```bash
chmod +x claude-tools
ln -s "$PWD/claude-tools" ~/.local/bin/claude-tools   # or put the repo on $PATH
```

Requires: Python 3.8+, PyYAML, and the `claude` CLI. No other dependencies.

## Usage

```bash
# explore
claude-tools search lsp --sort installs        # search the 207-plugin catalog
claude-tools search --category security
claude-tools info playwright                   # detail + component inventory + token cost

# act (ad-hoc lists)
claude-tools install frontend-design typescript-lsp playwright
claude-tools remove figma
claude-tools enable code-review  /  disable code-review
claude-tools install <names...> --dry-run      # preview the exact commands

# evaluate
claude-tools status                            # installed/enabled + always-on token budget
claude-tools eval                              # per-plugin token cost of the enabled set
claude-tools list --enabled

# bundles (curated, shareable sets)
claude-tools bundle list
claude-tools bundle show web
claude-tools bundle diff web                   # installed vs bundle
claude-tools bundle install web                # installs only what's missing
claude-tools bundle remove web

# maintenance
claude-tools refresh                           # refresh the marketplace catalog cache
```

Status glyphs: `●` enabled · `◐` installed-but-disabled · `○` available.
Token cost is shown as **always-on / on-invoke** — always-on is added to *every*
session; on-invoke is paid each time a skill/agent fires.

## Bundles

A bundle is a named set of plugins. `include:` composes bundles, so you can layer
`essentials` under `web`, `python`, etc. See [`bundles.yaml`](bundles.yaml):

```yaml
bundles:
  essentials:
    description: High-signal defaults useful in almost any repo
    plugins: [superpowers, context7, code-review, code-simplifier, github, security-guidance]
  web:
    description: Frontend & web app development
    include: [essentials]
    plugins: [frontend-design, typescript-lsp, playwright, chrome-devtools-mcp, figma]
```

Seeded bundles: `essentials`, `web`, `ios`, `android`, `mobile`, `typescript`,
`python`, `go`, `rust`, `data`, `security`, `testing`, `quality`,
`claude-authoring`, and an example curator bundle `karpathy`.

Point the tool at a different manifest with `CLAUDE_TOOLS_BUNDLES=/path/to/file.yaml`.

## Architecture

| Concern        | Source                                              |
|----------------|-----------------------------------------------------|
| explore / eval | `~/.claude/plugins/plugin-catalog-cache.json` (offline) |
| install state  | `~/.claude/settings.json`, `installed_plugins.json` |
| actions        | `claude plugin install/uninstall/enable/disable`, `marketplace update` |

## Scope & roadmap

In Claude Code the **plugin** is the installable unit — it bundles skills, commands,
agents, hooks, MCP, and LSP servers — so v1 manages plugins (covering all of those
transitively). Natural extensions, designed for but not yet wired:

- standalone **MCP servers** via `claude mcp add/remove` (add an `mcp:` key per bundle)
- local file-based **skills/commands/agents/rules** discovery & scaffolding

The bundle format already leaves room for these; contributions welcome.
