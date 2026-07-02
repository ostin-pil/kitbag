from kitbag.cli import resolve_local, resolve_bundle

BUNDLES = {
    "base": {"plugins": ["a"], "local": ["./skills/shared"]},
    "web": {
        "include": ["base"],
        "plugins": ["b"],
        "local": [
            "./skills/web",
            {"source": "o/r", "path": "agents/x.md", "type": "agent"},
            "./skills/shared",   # duplicate of base's -> deduped
        ],
    },
}


def test_resolve_local_flattens_includes_and_dedupes():
    specs = resolve_local(BUNDLES, "web")
    sources = [(s["source"], s.get("path")) for s in specs]
    # web's own + included base's, shared appearing once
    assert ("./skills/web", None) in sources
    assert ("o/r", "agents/x.md") in sources
    assert ("./skills/shared", None) in sources
    assert sources.count(("./skills/shared", None)) == 1


def test_resolve_local_normalizes_entries():
    specs = resolve_local(BUNDLES, "web")
    agent = next(s for s in specs if s["source"] == "o/r")
    assert agent["type"] == "agent" and agent["path"] == "agents/x.md"


def test_resolve_local_empty_when_no_local_key():
    assert resolve_local({"x": {"plugins": ["p"]}}, "x") == []


def test_resolve_bundle_still_ignores_local_key():
    # local: must not leak into the plugins/mcp resolution
    res = resolve_bundle(BUNDLES, "web")
    assert res["plugins"] == ["b", "a"] and res["mcp"] == []
