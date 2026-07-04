# kitbag Handover

_Status: v0.1.0 · private · 87 tests · ~82% coverage · CI green (py 3.9/3.11/3.13)_
_Last updated at commit `ea15828`._

## What kitbag is

One CLI to **explore, install, batch, and evaluate** Claude Code instruments (marketplace plugins, standalone MCP servers, and your own local skills/commands/agents), plus curated, shareable **bundles** and a generator that turns the manifest into a distributable marketplace. It reads Claude Code's local caches for fast offline work and shells out to `claude` only for mutations.

## Current state: capability-complete

| Area | What works |
|------|------------|
| Plugins | `search / info / install / remove / enable / disable / list / eval / status` over the offline catalog cache |
| MCP | `mcp list/add/remove` from a manifest `mcp_servers:` registry |
| Local artifacts | `local list/eval/add/remove`: author your own skills/commands/agents/output-styles; `add` from a path **or git URL** (private repos via `gh` auth); warns when a copied skill belongs to a plugin |
| Bundles | compose plugins + MCP + local artifacts; `bundle list/show/diff/install/remove` |
| Git marketplaces | `market list/add/remove` plus `name@marketplace` refs install **whole plugins** from any git repo |
| Manifest layering | packaged base plus personal overlay (`~/.config/kitbag/bundles.yaml`, `$KITBAG_MANIFEST`, `--manifest`); `extends_defaults: false` to replace |
| Generate | `generate marketplace` derives a valid Claude Code marketplace from the manifest (validated by `claude plugin validate`) |

Proven on real data: `ostin-pil/claude-plugins` is registered as marketplace `ostin-pil-plugins`, and its `lifecycle-kit`, `knowledge-kit`, `prose-mint` plugins are installed and running live.

## Repo map

- `kitbag/cli.py`: all commands and argparse; `Catalog` (reads catalog cache/settings/installed); manifest loading and layering; plugin/MCP/market/bundle/local orchestration.
- `kitbag/local.py`: pure and testable. Local-artifact discovery and token estimation, frontmatter parsing, source parsing (`parse_source`), git clone (`clone_command`, which resets the inherited cred helper and routes github auth via `gh`), and `enclosing_plugin`.
- `kitbag/generate.py`: pure `build_marketplace()` returning `{path: contents}`, plus `write_tree()`.
- `kitbag/bundles.yaml`: the shipped base manifest (bundles plus `mcp_servers:` and `marketplaces:` docs).
- `tests/`: `test_local.py`, `test_bundles.py`, `test_generate.py`, `test_cli_integration.py`. `conftest.py` has the fake-`~/.claude` fixture and the `run_cli()` harness (mutations asserted via `--dry-run`).
- `.github/workflows/ci.yml`: pytest plus coverage gate (`--cov-fail-under=78`) plus a CLI smoke test on 3.9/3.11/3.13 via uv.

## Dev workflow

```bash
cd ~/kitbag
uv venv && uv pip install -e ".[dev]"     # setup
.venv/bin/pytest -q                         # tests
.venv/bin/pytest -q --cov=kitbag --cov-fail-under=78   # exact CI command
```

- Toolchain is **uv** (`~/.local/bin`). Python floor is **3.9** (the setuptools>=77 build backend needs it).
- Always verify the exact CI command in a clean venv before pushing. CI once went red on an untested change.

## Environment gotchas (WSL), see also memory `wsl-git-github-gotchas`

1. **git push hangs**: global config inherits the Windows credential-manager helper. The `~/kitbag` repo is already configured to use `gh auth git-credential`; push with `GIT_TERMINAL_PROMPT=0` and a timeout so auth fails fast instead of hanging.
2. **workflow scope**: pushing `.github/workflows/*` needs `gh auth refresh -h github.com -s workflow` (interactive).
3. **uv-tool refresh**: `uv tool install . --force` **skips the rebuild when the version is unchanged**. Use `uv tool install . --reinstall` to refresh the global `kitbag`, or bump the version. (This bit us mid-session; the global tool looked stale.)

## Live dogfood setup (durable, on this machine)

- Marketplace `ostin-pil-plugins` registered from `ostin-pil/claude-plugins`.
- Plugins installed (user scope): `lifecycle-kit`, `knowledge-kit`, `prose-mint` (the last also registers a connected MCP server).
- Personal manifest `~/.config/kitbag/bundles.yaml` holds the `my-sessions` bundle (now the **plugins**, not the old standalone skills) plus the `marketplaces:` entry. It is not in the repo.

## Next steps (chosen: pre-public polish, then keep dogfooding)

### Pre-public polish (actionable loose ends)

1. **Market-plugin lifecycle gap (highest value).** `install name@marketplace` works, but `remove / enable / disable` **fail** for git-marketplace plugins, because those verbs go through `_resolve()`, which requires the official catalog cache that market plugins aren't in (`kitbag remove lifecycle-kit` reports "unknown plugin"). Workaround today: `claude plugin uninstall lifecycle-kit`. Fix: make remove/enable/disable accept `@marketplace`/short names and shell `claude plugin <verb> <name>` without a catalog lookup. Add tests.
2. **`generate --base-only`.** `generate marketplace` currently merges the personal overlay, so run locally it can leak personal or private bundles into the output. Add a flag (and/or default) to generate from `PACKAGED` only.
3. **`kitbag market update`** passthrough for `claude plugin marketplace update` (git marketplaces don't refresh via `kitbag refresh`, which only touches the official catalog).
4. **Dev-install ergonomics.** A `Makefile`/`justfile` target that runs `uv tool install . --reinstall`, or version-bump discipline, so the global tool never looks stale.

### Keep dogfooding

- Run the now-live `lifecycle-kit`, `knowledge-kit`, and `prose-mint` on real work. Watch the `SessionStart` hook in projects without a `.claude/lifecycle-manifest.md` (it should no-op or warn), and whether `session-report`/`session-end` fit the rhythm.
- Manage plugins via kitbag day-to-day and let rough edges surface.

### Later milestone: ship it (deferred, not now)

- Flip the repo public; add a PyPI trusted-publishing release workflow (tag, build, publish) so `pipx install kitbag` and `uv tool install kitbag` work for anyone; write quickstart docs, set a real LICENSE holder, and record a demo (asciinema or GIF).

## Known limitations (quick list)

- Market plugins: install-only from kitbag (see polish item 1).
- Token cost for local artifacts is a rough estimate (~4 chars/token), not a real tokenizer.
- `configured_mcp_names()` parses the text output of `claude mcp list` (brittle if that format changes).
- `generate` local-overlay leak (see polish item 2).
