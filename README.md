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
# straight from GitHub, no checkout needed
uv tool install git+https://github.com/ostin-pil/kitbag
# or: pipx install git+https://github.com/ostin-pil/kitbag

kitbag --help
```

Working on kitbag itself, from a checkout:

```bash
pipx install .            # or: uv tool install .
pip install -e .          # editable, for hacking on it
python -m kitbag --help   # run without installing
```

Requires: Python 3.8+, PyYAML, and the `claude` CLI. No other dependencies.

> Not on PyPI: the name there belongs to an unrelated project, so install from git as
> above. The `kitbag` command is the same either way.

Add your own bundles in `~/.config/kitbag/bundles.yaml` (auto-layered on the
built-ins) — see [Personal bundles](#personal-bundles-manifest-layering).

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

A bundle can also carry **`local:`** — your own skills/commands/agents/output-styles
(local path or git URL), installed alongside plugins & MCP by one `bundle install`:

```yaml
  my-workflow:
    include: [essentials]
    plugins: [typescript-lsp]
    mcp: [sentry]
    local:
      - ./my-skills/pr-review                 # local skill dir (type auto-detected)
      - source: owner/agents-repo             # a git repo…
        path: agents/reviewer.md              # …file within it
        type: agent
        ref: main                             # optional branch/tag/sha
```

`bundle install` installs missing local artifacts (idempotent; remote ones prompt
unless `--yes`); `bundle show`/`diff` mark each present ●, missing ○, or remote ?;
`bundle remove` deletes the ones it can resolve. This makes `bundles.yaml` a single
shareable manifest for a whole workflow — marketplace plugins **and** your own tools.

### Personal bundles (manifest layering)

Keep your own bundles out of the shipped manifest: put them in
**`~/.config/kitbag/bundles.yaml`** and kitbag auto-layers them on top of the
built-ins — you get the defaults **and** your bundles. A bundle/MCP server whose
name matches a built-in overrides it.

```yaml
# ~/.config/kitbag/bundles.yaml
schema: 1
bundles:
  my-sessions:
    description: My own skills, pulled over git
    local:
      - source: me/my-skills-repo
        path: skills/session-start
```

Overlay precedence: `--manifest <file>` › `$KITBAG_MANIFEST` › `~/.config/kitbag/bundles.yaml`.
`kitbag bundle list` shows which layers are active. To ignore the built-ins entirely,
put `extends_defaults: false` at the top of your manifest.

## Git marketplaces (install whole plugins from any repo)

The catalog only knows the official marketplace. To install a **whole plugin**
(skills + commands + hooks + templates — full fidelity) from any git repo, kitbag
drives Claude Code's own marketplace machinery:

```bash
kitbag market add ostin-pil/claude-plugins          # owner/repo, URL, or path
kitbag market list                                  # registered + manifest-declared
kitbag install lifecycle-kit@ostin-pil-plugins      # plugin@marketplace
kitbag market remove ostin-pil-plugins
```

Declare marketplaces in the manifest so bundles can pull plugins from them — kitbag
adds the marketplace (if missing) before installing:

```yaml
marketplaces:
  ostin-pil-plugins:
    source: ostin-pil/claude-plugins        # owner/repo, URL, or path
    # sparse: [.claude-plugin, lifecycle-kit]   # optional monorepo checkout
bundles:
  my-lifecycle:
    plugins: [lifecycle-kit@ostin-pil-plugins, knowledge-kit@ostin-pil-plugins]
```

The `@marketplace` name must match the `name` in the repo's `marketplace.json`.
Standalone `local:` skills (above) vs. `@marketplace` plugins are the two ways to
get someone's work: a single skill copied in, or the whole plugin managed by
Claude Code. `kitbag local add` warns when you copy a skill that's part of a plugin.

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

## Local artifacts (your own skills/commands/agents)

Beyond marketplace plugins, kitbag inventories the instruments you author yourself
under `~/.claude/` (user scope) and `./.claude/` (project scope), and **estimates
their token cost** (there's no catalog for these, so it's a ~4-chars/token estimate):

```bash
kitbag local list                 # everything, with always-on / on-invoke cost
kitbag local list --type skill    # filter by type or --scope user|project
kitbag local eval                 # local token budget, heaviest always-on
kitbag local add ./my-skill/      # copy-install a skill dir (auto-detects type)
kitbag local add ./review.md --type agent --scope project
kitbag local remove skill my-skill
```

`add` also installs from **git**: pass a repo URL, a github `tree`/`blob` URL, an
`owner/repo` shorthand, or a raw `.md` URL. kitbag shallow-clones (or downloads),
copy-installs the artifact, and cleans up. Remote installs ask for confirmation
(`--yes` to skip):

```bash
kitbag local add owner/skills-repo --path skills/pr-review        # subdir of a repo
kitbag local add https://github.com/owner/repo/blob/main/agents/x.md --yes
kitbag local add https://example.com/style.md --type output-style  # raw url needs --type
kitbag local add owner/repo --ref v2 --path commands/deploy.md
```

`kitbag status` now reports the **true** always-on budget = plugins + local.

| Type           | Always-on cost                    | `add` |
|----------------|-----------------------------------|:-----:|
| skill          | `name` + `description` frontmatter | ✅ dir |
| agent          | `name` + `description` frontmatter | ✅ .md |
| command        | 0 (body loads on invoke)           | ✅ .md |
| output-style   | full body, only when it's active   | ✅ .md |
| memory (CLAUDE.md) | full body (loads every session) | read-only |
| hook           | 0 (behavioural, not context)       | read-only |

`add` auto-detects type from the source (a directory with `SKILL.md` → skill; a
`.md` under `agents/`, `commands/`, `output-styles/` → that type; else pass `--type`).
`memory` and `hooks` are inventoried but not mutated by kitbag in v1.

## Architecture

| Concern        | Source                                              |
|----------------|-----------------------------------------------------|
| explore / eval | `~/.claude/plugins/plugin-catalog-cache.json` (offline) |
| plugin state   | `~/.claude/settings.json`, `installed_plugins.json` |
| mcp state      | `claude mcp list` (parsed; `plugin:`-prefixed excluded) |
| local artifacts| filesystem scan of `~/.claude` & `./.claude` (+ CLAUDE.md) |
| actions        | `claude plugin …`, `claude mcp add/remove`; local = file copy |

## Scope & roadmap

In Claude Code the **plugin** is the installable unit — it bundles skills, commands,
agents, hooks, MCP, and LSP servers — standalone **MCP servers** are wired in (registry
+ bundle `mcp:` keys), and your own **local artifacts** are now discoverable, costed,
and copy-installable (`kitbag local`). Still open:

- `local add` from a **git URL** (v1 is local-path copy only)
- managing **memory/hooks** mutations (v1 lists them read-only)
- a community **bundle registry** (`kitbag registry add` / `bundle pull <url>`)

The manifest format leaves room for these; contributions welcome.
