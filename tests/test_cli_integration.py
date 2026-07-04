"""Integration tests for the command layer: Catalog parsing + command output +
the shell-out plan (asserted via --dry-run, so no real `claude` runs)."""
import json
import pytest

from kitbag import cli
from conftest import run_cli


# ---- Catalog parsing ---------------------------------------------------------
def test_catalog_parses_state(fake_home):
    cat = cli.Catalog()
    assert set(cat.by_name) == {"superpowers", "code-review", "typescript-lsp", "figma"}
    assert cat.is_installed("superpowers") and cat.is_enabled("superpowers")
    assert cat.is_installed("typescript-lsp") and not cat.is_enabled("typescript-lsp")
    assert not cat.is_installed("figma")
    ao, oi, model = cat.cost(cat.get("superpowers"))
    assert (ao, oi, model) == (723, 1200, "claude-opus-4-8")


def test_catalog_component_summary(fake_home):
    cat = cli.Catalog()
    # fixed emit order: commands, agents, skills, ...
    assert cat.comp_summary(cat.get("superpowers")) == "1 cmd, 2 skill"
    assert cat.comp_summary(cat.get("code-review")) == "1 cmd, 1 agent"


# ---- search ------------------------------------------------------------------
def test_search_text_and_json(fake_home):
    code, out = run_cli(["search", "review", "--json"])
    assert code == 0 and json.loads(out) == ["code-review"]


def test_search_filters_installed_and_sorts_by_cost(fake_home):
    code, out = run_cli(["search", "--installed", "--sort", "cost"])
    lines = [l for l in out.splitlines() if "tok" in l]
    # installed only (figma excluded); superpowers (723) before code-review (130)
    assert "figma" not in out
    assert lines[0].index("superpowers") and out.index("superpowers") < out.index("code-review")


def test_search_category_filter(fake_home):
    code, out = run_cli(["search", "--category", "lsp", "--json"])
    assert json.loads(out) == ["typescript-lsp"]


# ---- info / eval / status / list --------------------------------------------
def test_info_known_and_unknown(fake_home):
    code, out = run_cli(["info", "superpowers"])
    assert code == 0 and "always-on" in out and "723" in out
    code, _ = run_cli(["info", "does-not-exist"])
    assert code == 1


def test_status_sums_enabled_always_on(fake_home):
    code, out = run_cli(["status"])
    assert code == 0
    assert "installed: 3   enabled: 2" in out
    assert "always-on token budget (enabled): 853" in out  # 723 + 130


def test_eval_totals(fake_home):
    code, out = run_cli(["eval"])
    assert code == 0
    assert "TOTAL" in out and "853" in out


def test_list_installed(fake_home):
    code, out = run_cli(["list"])
    assert code == 0
    assert "3 installed" in out and "figma" not in out


# ---- mutating commands via --dry-run (assert the shell-out plan) ------------
def test_install_dry_run_emits_claude_command(fake_home):
    code, out = run_cli(["install", "figma", "--dry-run"])
    assert code == 0
    assert "claude plugin install figma@claude-plugins-official --scope user" in out


def test_enable_dry_run(fake_home):
    code, out = run_cli(["enable", "typescript-lsp", "--dry-run"])
    assert code == 0 and "claude plugin enable typescript-lsp" in out


def test_install_unknown_plugin_errors(fake_home):
    code, _ = run_cli(["install", "nope", "--dry-run"])
    assert code == 1


# ---- bundle install/diff with a temp manifest -------------------------------
@pytest.fixture
def manifest(tmp_path):
    p = tmp_path / "bundles.yaml"
    p.write_text(
        "schema: 1\n"
        "extends_defaults: false\n"           # isolate from packaged base
        "bundles:\n"
        "  demo:\n"
        "    description: demo\n"
        "    plugins: [figma, superpowers]\n"  # figma missing, superpowers present
    )
    return p


def test_bundle_diff_reports_missing(fake_home, manifest):
    code, out = run_cli(["bundle", "diff", "demo"], manifest=manifest)
    assert code == 0
    assert "figma" in out                       # missing
    assert "superpowers" in out                 # installed


def test_bundle_install_only_installs_missing(fake_home, manifest):
    code, out = run_cli(["bundle", "install", "demo", "--dry-run"], manifest=manifest)
    assert code == 0
    # figma is missing -> installed; superpowers already present -> skipped
    assert "claude plugin install figma@claude-plugins-official" in out
    assert "install superpowers@" not in out


def test_bundle_install_force_reinstalls_all(fake_home, manifest):
    code, out = run_cli(["bundle", "install", "demo", "--dry-run", "--force"],
                        manifest=manifest)
    assert "figma@claude-plugins-official" in out
    assert "superpowers@claude-plugins-official" in out


# ---- MCP registry + add plan -------------------------------------------------
@pytest.fixture
def mcp_manifest(tmp_path):
    p = tmp_path / "mcp.yaml"
    p.write_text(
        "schema: 1\n"
        "extends_defaults: false\n"
        "mcp_servers:\n"
        "  sentry:\n"
        "    transport: http\n"
        "    url: https://mcp.sentry.dev/mcp\n"
        "  local-tool:\n"
        "    transport: stdio\n"
        "    command: npx\n"
        "    args: ['-y', '@scope/tool']\n"
        "bundles:\n"
        "  obs:\n"
        "    description: observability\n"
        "    mcp: [sentry]\n"
    )
    return p


def test_mcp_list(fake_home, mcp_manifest):
    code, out = run_cli(["mcp", "list"], manifest=mcp_manifest)
    assert code == 0 and "sentry" in out and "local-tool" in out


def test_mcp_add_http_dry_run(fake_home, mcp_manifest):
    code, out = run_cli(["mcp", "add", "sentry", "--dry-run"], manifest=mcp_manifest)
    assert code == 0
    assert "claude mcp add -s user --transport http sentry https://mcp.sentry.dev/mcp" in out


def test_mcp_add_stdio_dry_run(fake_home, mcp_manifest):
    code, out = run_cli(["mcp", "add", "local-tool", "--dry-run"], manifest=mcp_manifest)
    assert "claude mcp add -s user local-tool -- npx -y @scope/tool" in out


def test_mcp_add_unknown_errors(fake_home, mcp_manifest):
    code, _ = run_cli(["mcp", "add", "ghost", "--dry-run"], manifest=mcp_manifest)
    assert code == 1


def test_bundle_install_emits_mcp_add(fake_home, mcp_manifest):
    code, out = run_cli(["bundle", "install", "obs", "--dry-run"], manifest=mcp_manifest)
    assert "claude mcp add -s user --transport http sentry" in out


# ---- local add through the CLI ----------------------------------------------
def test_local_add_skill_dry_run(fake_home, tmp_path):
    src = tmp_path / "greet"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: greet\ndescription: hi\n---\nbody")
    code, out = run_cli(["local", "add", str(src), "--dry-run"])
    assert code == 0
    assert "install skill" in out and "skills/greet" in out


def test_local_add_missing_source_errors(fake_home):
    code, _ = run_cli(["local", "add", "/no/such/path", "--dry-run"])
    assert code == 1


def test_local_add_remote_dry_run_no_network(fake_home):
    code, out = run_cli(
        ["local", "add", "owner/repo", "--path", "agents/x.md", "--dry-run"])
    assert code == 0 and "would fetch" in out and "github.com/owner/repo" in out


# ---- bundle show / list smoke (exercise the display/formatting paths) --------
def test_bundle_show_and_list_run(fake_home, manifest):
    code, out = run_cli(["bundle", "show", "demo"], manifest=manifest)
    assert code == 0 and "demo" in out and "superpowers" in out
    code, out = run_cli(["bundle", "list"], manifest=manifest)
    assert code == 0 and "demo" in out


def test_bundle_remove_uninstalls_present_plugins(fake_home, manifest):
    code, out = run_cli(["bundle", "remove", "demo", "--dry-run"], manifest=manifest)
    assert code == 0
    # superpowers is installed -> uninstall planned; figma not installed -> skipped
    assert "claude plugin uninstall superpowers" in out
    assert "uninstall figma" not in out


# ---- local list / eval / remove + status-with-local -------------------------
@pytest.fixture
def local_skill(fake_home):
    d = fake_home / ".claude/skills/mine"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: mine\ndescription: a local skill\n---\n" + "body " * 50)
    return fake_home


def test_local_list_and_eval(local_skill):
    code, out = run_cli(["local", "list"])
    assert code == 0 and "mine" in out and "skill" in out
    code, out = run_cli(["local", "eval"])
    assert code == 0 and "always-on total" in out and "mine" in out


def test_status_includes_local_always_on(local_skill):
    code, out = run_cli(["status"])
    assert code == 0
    assert "local artifacts always-on" in out
    assert "true always-on (plugins+local)" in out


def test_local_remove_deletes(local_skill):
    target = local_skill / ".claude/skills/mine"
    assert target.exists()
    code, out = run_cli(["local", "remove", "skill", "mine"])
    assert code == 0 and not target.exists()


def test_local_remove_unknown_errors(fake_home):
    code, _ = run_cli(["local", "remove", "skill", "ghost"])
    assert code == 1


# ---- manifest layering (personal overlay on the packaged base) --------------
def test_overlay_merges_onto_packaged_base(fake_home, tmp_path):
    # a personal overlay adds a bundle; built-in bundles remain visible
    p = tmp_path / "personal.yaml"
    p.write_text("schema: 1\nbundles:\n  mine:\n    description: my own\n"
                 "    plugins: [figma]\n")
    code, out = run_cli(["bundle", "list"], manifest=p)
    assert code == 0
    assert "mine" in out          # personal bundle
    assert "essentials" in out    # built-in from packaged base still present


def test_overlay_extends_defaults_false_replaces(fake_home, tmp_path):
    p = tmp_path / "only.yaml"
    p.write_text("schema: 1\nextends_defaults: false\nbundles:\n"
                 "  mine:\n    description: solo\n    plugins: [figma]\n")
    code, out = run_cli(["bundle", "list"], manifest=p)
    assert code == 0 and "mine" in out
    assert "essentials" not in out   # base replaced


def test_overlay_bundle_overrides_base_by_name(fake_home, tmp_path):
    p = tmp_path / "override.yaml"
    p.write_text("schema: 1\nbundles:\n  essentials:\n"
                 "    description: MY OVERRIDDEN ESSENTIALS\n    plugins: [figma]\n")
    code, out = run_cli(["bundle", "show", "essentials"], manifest=p)
    assert code == 0 and "MY OVERRIDDEN ESSENTIALS" in out


# ---- git marketplaces (install whole plugins from any repo) -----------------
def test_split_market():
    assert cli.split_market("lifecycle-kit@ostin-pil-plugins") == \
        ("lifecycle-kit", "ostin-pil-plugins")
    assert cli.split_market("code-review") == ("code-review", None)


def test_market_add_argv():
    argv = cli.market_add_argv("mp", {"source": "o/r", "sparse": [".claude-plugin", "p"]})
    assert argv == ["claude", "plugin", "marketplace", "add", "o/r",
                    "--sparse", ".claude-plugin", "p"]
    argv2 = cli.market_add_argv("mp", {"source": "o/r", "scope": "project"})
    assert "--scope" in argv2 and "project" in argv2


@pytest.fixture
def market_manifest(tmp_path):
    p = tmp_path / "mk.yaml"
    p.write_text(
        "schema: 1\n"
        "extends_defaults: false\n"
        "marketplaces:\n"
        "  mine:\n"
        "    source: me/plugins-repo\n"
        "bundles:\n"
        "  kit:\n"
        "    description: my git-marketplace plugins\n"
        "    plugins: [lifecycle-kit@mine, code-review]\n"  # one market, one catalog
    )
    return p


def test_market_list_shows_registered_and_manifest(fake_home, market_manifest):
    code, out = run_cli(["market", "list"], manifest=market_manifest)
    assert code == 0
    assert "claude-plugins-official" in out   # registered (from fake_home)
    assert "mine" in out                       # manifest registry, not yet added


def test_market_add_from_manifest_registry_name(fake_home, market_manifest):
    code, out = run_cli(["market", "add", "mine", "--dry-run"], manifest=market_manifest)
    assert code == 0
    assert "claude plugin marketplace add me/plugins-repo" in out


def test_market_add_direct_source(fake_home):
    code, out = run_cli(["market", "add", "owner/repo", "--dry-run"])
    assert "claude plugin marketplace add owner/repo" in out


def test_install_market_ref_adds_marketplace_then_installs(fake_home, market_manifest):
    code, out = run_cli(["install", "lifecycle-kit@mine", "--dry-run"],
                        manifest=market_manifest)
    assert code == 0
    assert "claude plugin marketplace add me/plugins-repo" in out   # auto-add
    assert "claude plugin install lifecycle-kit@mine --scope user" in out


def test_install_market_ref_unknown_marketplace_errors(fake_home):
    code, _ = run_cli(["install", "x@ghostmarket", "--dry-run"])
    assert code == 1   # not registered, not in manifest registry


def test_bundle_install_routes_market_and_catalog(fake_home, market_manifest):
    code, out = run_cli(["bundle", "install", "kit", "--dry-run"],
                        manifest=market_manifest)
    assert code == 0
    # market plugin -> add marketplace + install @mine
    assert "marketplace add me/plugins-repo" in out
    assert "install lifecycle-kit@mine" in out
    # catalog plugin code-review is already installed in fake_home -> skipped
    assert "install code-review@" not in out


def test_bundle_show_lists_market_plugins(fake_home, market_manifest):
    code, out = run_cli(["bundle", "show", "kit"], manifest=market_manifest)
    assert code == 0
    assert "lifecycle-kit" in out and "@mine" in out
    assert "marketplace plugins" in out


def test_merge_manifests_unit():
    base = {"schema": 1, "bundles": {"a": {"x": 1}, "b": {"x": 2}},
            "mcp_servers": {"s1": {}}}
    overlay = {"schema": 1, "bundles": {"b": {"x": 99}, "c": {"x": 3}},
               "mcp_servers": {"s2": {}}}
    merged = cli._merge_manifests(base, overlay)
    assert set(merged["bundles"]) == {"a", "b", "c"}
    assert merged["bundles"]["b"]["x"] == 99          # overlay wins
    assert set(merged["mcp_servers"]) == {"s1", "s2"}
