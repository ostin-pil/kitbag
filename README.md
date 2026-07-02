# kitbag

[![CI](https://github.com/ostin-pil/kitbag/actions/workflows/ci.yml/badge.svg)](https://github.com/ostin-pil/kitbag/actions/workflows/ci.yml)

One entry point to **explore, (un)install, batch, and evaluate** Claude Code
instruments — and to share curated **bundles** of them per workflow or curator.

It reads the local plugin catalog cache for instant, offline search/eval and shells
out to the `claude` CLI only for mutating actions. Curated bundles live in
[`kitbag/bundles.yaml`](kitbag/bundles.yaml) — that file *is* the shareable artifact:
fork it, edit it, pass it around.

> Origin: this repo started as a one-off plugin-install script
> ([`install-plugins.sh`](install-plugins.sh), [`PLAN.md`](PLAN.md)) and grew into the
> general `kitbag` CLI.

## Install

```bash
# from a checkout
pipx install .            # or: uv tool install .
# editable, for hacking on it
pip install -e .

# run without installing
python -m kitbag --help
```

Requires: Python 3.8+, PyYAML, and the `claude` CLI. No other dependencies.

Use a different manifest with `--manifest /path/to/file.yaml` or `$KITBAG_MANIFEST`.

## Usage

```bash
# explore
kitbag search lsp --sort installs        # search the 207-plugin catalog
kitbag search --category security
kitbag info playwright                   # detail + component inventory + token cost

# act (ad-hoc lists)
kitbag install frontend-design typescript-lsp playwright
kitbag remove figma
kitbag enable code-review  /  disable code-review
kitbag install <names...> --dry-run      # preview the exact commands

# evaluate
kitbag status                            # installed/enabled + always-on token budget
kitbag eval                              # per-plugin token cost of the enabled set
kitbag list --enabled

# standalone MCP servers (registry in bundles.yaml)
kitbag mcp list                          # registry + already-configured servers
kitbag mcp info sentry
kitbag mcp add sentry                    # -> claude mcp add ... (--scope user)
kitbag mcp remove sentry
kitbag mcp add <name> --dry-run

# bundles (curated, shareable sets of plugins AND mcp servers)
kitbag bundle list
kitbag bundle show observability
kitbag bundle diff web                   # installed vs bundle
kitbag bundle install web                # installs only what's missing (plugins + mcp)
kitbag bundle remove web

# maintenance
kitbag refresh                           # refresh the marketplace catalog cache
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

Point the tool at a different manifest with `KITBAG_MANIFEST=/path/to/file.yaml`.

## Generate a marketplace (single source)

`bundles.yaml` is the single source of truth; kitbag can derive a distributable
**Claude Code marketplace** from it so bundles install natively via `/plugin`:

```bash
kitbag generate marketplace --out dist/marketplace            # one plugin per bundle
kitbag generate marketplace --layout single                   # one plugin, command per bundle
kitbag generate marketplace --dry-run                         # list files only
```

Each bundle becomes a tiny plugin whose slash command runs `kitbag bundle install
<bundle>` (Claude Code plugins have no plugin→plugin dependency field, so members
are installed by the command rather than declared as deps). Output is validated by
`claude plugin validate`. Publish the generated directory as its own git repo:

```bash
cd dist/marketplace && git init && git add -A && git commit -m "kitbag marketplace"
claude plugin marketplace add <owner>/<repo>
claude plugin install web@kitbag-bundles
```

Re-run the generator whenever `bundles.yaml` changes — never hand-edit the output.

## Standalone MCP servers

MCP servers have no marketplace catalog, so the manifest carries an `mcp_servers:`
**registry** and bundles reference servers by name under an `mcp:` key:

```yaml
mcp_servers:
  sentry:                       # http/sse -> url (+ optional headers)
    transport: http
    url: https://mcp.sentry.dev/mcp
  my-server:                    # stdio (default) -> command (+ optional args/env)
    transport: stdio
    command: npx
    args: ["-y", "@scope/my-mcp"]
    env: ["API_KEY=replace-me"]

bundles:
  observability:
    plugins: [security-guidance]
    mcp: [sentry]               # pulled in by `bundle install observability`
```

`mcp add/remove` wrap `claude mcp add/remove` at `--scope user` by default
(`--scope local|project` to override). `bundle install/remove/diff/show` handle
plugins and MCP servers together. Plugin-provided MCP servers (the `plugin:…`
entries in `claude mcp list`) are managed via their plugin and ignored here.

## Architecture

| Concern        | Source                                              |
|----------------|-----------------------------------------------------|
| explore / eval | `~/.claude/plugins/plugin-catalog-cache.json` (offline) |
| plugin state   | `~/.claude/settings.json`, `installed_plugins.json` |
| mcp state      | `claude mcp list` (parsed; `plugin:`-prefixed excluded) |
| actions        | `claude plugin …`, `claude mcp add/remove`, `marketplace update` |

## Scope & roadmap

In Claude Code the **plugin** is the installable unit — it bundles skills, commands,
agents, hooks, MCP, and LSP servers — and standalone **MCP servers** are now wired in
too (registry + bundle `mcp:` keys). Remaining extension, not yet wired:

- local file-based **skills/commands/agents/rules** discovery & scaffolding

The manifest format leaves room for these; contributions welcome.
