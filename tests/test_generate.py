import json
import pytest
from kitbag import generate as gen

MANIFEST = {
    "schema": 1,
    "bundles": {
        "essentials": {"description": "defaults", "plugins": ["a", "b"]},
        "web": {"description": "frontend", "include": ["essentials"],
                "plugins": ["c"], "mcp": ["sentry"]},
    },
    "mcp_servers": {"sentry": {"transport": "http", "url": "https://x"}},
}


def test_per_bundle_layout_structure():
    files = gen.build_marketplace(MANIFEST, name="m", layout="per-bundle")
    # marketplace.json is valid and lists every bundle
    mkt = json.loads(files[".claude-plugin/marketplace.json"])
    assert mkt["name"] == "m"
    names = {p["name"] for p in mkt["plugins"]}
    assert names == {"essentials", "web"}
    assert all(p["source"] == f"./plugins/{p['name']}" for p in mkt["plugins"])
    # each bundle yields a plugin.json + install command
    for b in ("essentials", "web"):
        pj = json.loads(files[f"plugins/{b}/.claude-plugin/plugin.json"])
        assert pj["name"] == b
        cmd = files[f"plugins/{b}/commands/install.md"]
        assert f"kitbag bundle install {b}" in cmd


def test_web_command_lists_resolved_members_and_mcp():
    files = gen.build_marketplace(MANIFEST, layout="per-bundle")
    cmd = files["plugins/web/commands/install.md"]
    # include: essentials -> a, b should be flattened in alongside c
    for plugin in ("a", "b", "c"):
        assert plugin in cmd
    assert "sentry" in cmd  # mcp member surfaced


def test_single_layout_is_one_plugin_with_per_bundle_commands():
    files = gen.build_marketplace(MANIFEST, layout="single")
    mkt = json.loads(files[".claude-plugin/marketplace.json"])
    assert [p["name"] for p in mkt["plugins"]] == ["kitbag"]
    assert "plugins/kitbag/commands/essentials.md" in files
    assert "plugins/kitbag/commands/web.md" in files


def test_all_json_outputs_are_valid_json():
    for layout in ("per-bundle", "single"):
        files = gen.build_marketplace(MANIFEST, layout=layout)
        for rel, content in files.items():
            if rel.endswith(".json"):
                json.loads(content)  # raises on invalid


def test_empty_manifest_raises():
    with pytest.raises(ValueError):
        gen.build_marketplace({"bundles": {}})


def test_unknown_layout_raises():
    with pytest.raises(ValueError):
        gen.build_marketplace(MANIFEST, layout="nope")


def test_write_tree_roundtrips(tmp_path):
    files = gen.build_marketplace(MANIFEST, layout="per-bundle")
    written = gen.write_tree(tmp_path, files)
    assert len(written) == len(files)
    mkt = (tmp_path / ".claude-plugin/marketplace.json")
    assert mkt.exists() and json.loads(mkt.read_text())["plugins"]
