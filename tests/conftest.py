"""Shared fixtures for integration tests that exercise the command layer.

Builds a fake ~/.claude tree (catalog cache + settings + installed_plugins),
points the cli module's path globals at it, and stubs the two impure seams
(`claude mcp list` and any real subprocess) so commands run offline.
"""
import io
import json
from contextlib import redirect_stdout

import pytest

from kitbag import cli


def _catalog_cache():
    def entry(desc, cat, installs, ao, oi, comps, tags=None):
        return {
            "marketplace_entry": {
                "displayName": None, "description": desc, "category": cat,
                "tags": tags or [], "keywords": [],
                "author": {"name": "Anthropic"},
            },
            "unique_installs": installs,
            "tokens": {"claude-opus-4-8": {"always_on": ao, "on_invoke": oi}},
            "components": comps,
        }
    return {
        "fetchedAt": "2026-07-03T00:00:00.000Z",
        "catalog": {"plugins": {
            "superpowers@claude-plugins-official": entry(
                "Brainstorming and subagent-driven development", "workflow",
                5000, 723, 1200, {"skills": ["a", "b"], "commands": ["c"]},
                tags=["workflow"]),
            "code-review@claude-plugins-official": entry(
                "Automated PR review", "review", 3000, 130, 800,
                {"agents": ["r"], "commands": ["cr"]}, tags=["review"]),
            "typescript-lsp@claude-plugins-official": entry(
                "TypeScript language server", "lsp", 2000, 0, 400,
                {"lspServers": ["ts"]}, tags=["lsp"]),
            "figma@claude-plugins-official": entry(
                "Figma design integration", "design", 900, 50, 300,
                {"mcpServers": ["figma"]}),
        }},
    }


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """A fake ~/.claude with catalog + state. Returns the home Path.

    superpowers & code-review are installed+enabled; typescript-lsp is installed
    but disabled; figma is available (not installed).
    """
    claude = tmp_path / ".claude"
    (claude / "plugins").mkdir(parents=True)
    (claude / "plugins/plugin-catalog-cache.json").write_text(
        json.dumps(_catalog_cache()))
    (claude / "settings.json").write_text(json.dumps({"enabledPlugins": {
        "superpowers@claude-plugins-official": True,
        "code-review@claude-plugins-official": True,
        "typescript-lsp@claude-plugins-official": False,
    }}))
    (claude / "plugins/installed_plugins.json").write_text(json.dumps({"plugins": {
        "superpowers@claude-plugins-official": [{"scope": "user"}],
        "code-review@claude-plugins-official": [{"scope": "user"}],
        "typescript-lsp@claude-plugins-official": [{"scope": "user"}],
    }}))

    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "CATALOG", claude / "plugins/plugin-catalog-cache.json")
    monkeypatch.setattr(cli, "SETTINGS", claude / "settings.json")
    monkeypatch.setattr(cli, "INSTALLED", claude / "plugins/installed_plugins.json")
    # no MCP servers configured by default; never shell out to real `claude`
    monkeypatch.setattr(cli, "configured_mcp_names", lambda: set())
    cli._manifest_cache = None
    cli._mcp_cache = None
    return tmp_path


def run_cli(argv, *, manifest=None):
    """Parse argv, build the catalog (unless the command opts out), invoke the
    command, and return (exit_code, stdout). SystemExit is captured."""
    if manifest is not None:
        cli.BUNDLES = manifest
        cli._manifest_cache = None
    args = cli.build_parser().parse_args(argv)
    cat = cli.Catalog() if getattr(args, "needs_catalog", True) else None
    buf = io.StringIO()
    code = 0
    try:
        with redirect_stdout(buf):
            args.fn(cat, args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, buf.getvalue()
