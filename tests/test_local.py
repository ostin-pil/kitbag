import pytest
from pathlib import Path
from kitbag import local


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_estimate_tokens():
    assert local.estimate_tokens("") == 0
    assert local.estimate_tokens("abcd") == 1
    assert local.estimate_tokens("a" * 400) == 100


def test_parse_frontmatter():
    fm, body = local.parse_frontmatter("---\nname: x\ndescription: hi\n---\nBODY\n")
    assert fm == {"name": "x", "description": "hi"}
    assert body.strip() == "BODY"
    fm2, body2 = local.parse_frontmatter("no frontmatter here")
    assert fm2 == {} and body2 == "no frontmatter here"


@pytest.fixture
def tree(tmp_path):
    base = tmp_path / ".claude"
    _write(base / "skills/greet/SKILL.md",
           "---\nname: greet\ndescription: say hello nicely\n---\nlong body " + "x" * 200)
    _write(base / "commands/deploy.md",
           "---\ndescription: deploy the app\n---\nrun the deploy steps " + "y" * 100)
    _write(base / "agents/reviewer.md",
           "---\nname: reviewer\ndescription: reviews code\n---\nagent body")
    _write(base / "output-styles/terse.md",
           "---\nname: terse\ndescription: short answers\n---\nBe terse.")
    return base


def test_discover_finds_all_types(tree):
    arts = local.discover([(tree, "user")])
    by_type = {a.type: a for a in arts}
    assert set(by_type) == {"skill", "command", "agent", "output-style"}
    assert by_type["skill"].name == "greet"
    assert by_type["command"].name == "deploy"


def test_skill_and_agent_have_always_on_command_does_not(tree):
    arts = {a.type: a for a in local.discover([(tree, "user")])}
    assert arts["skill"].always_on > 0 and arts["skill"].on_invoke > 0
    assert arts["agent"].always_on > 0
    assert arts["command"].always_on == 0 and arts["command"].on_invoke > 0


def test_output_style_only_costs_when_active(tree):
    inactive = {a.type: a for a in local.discover([(tree, "user")])}["output-style"]
    assert inactive.always_on == 0 and inactive.active is False
    active = {a.type: a for a in
              local.discover([(tree, "user")], active_style="terse")}["output-style"]
    assert active.always_on > 0 and active.active is True


def test_nested_command_name_uses_relative_path(tmp_path):
    base = tmp_path / ".claude"
    _write(base / "commands/git/commit.md", "---\ndescription: commit\n---\nbody")
    arts = local.discover([(base, "user")])
    assert arts[0].name == "git/commit"


def test_memory_artifacts(tmp_path):
    cl = tmp_path / "CLAUDE.md"
    cl.write_text("# Project rules\nAlways run tests.")
    arts = local.memory_artifacts([(cl, "project")])
    assert len(arts) == 1
    assert arts[0].type == "memory" and arts[0].always_on > 0
    assert arts[0].description == "Project rules"


def test_hook_artifacts():
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"command": "echo hi"}]}]}}
    arts = local.hook_artifacts(settings, "user")
    assert len(arts) == 1
    assert arts[0].type == "hook" and arts[0].name == "PreToolUse:Bash"
    assert arts[0].always_on == 0


def test_detect_type(tmp_path):
    skill = tmp_path / "myskill"
    (skill).mkdir()
    (skill / "SKILL.md").write_text("---\nname: s\n---\nx")
    assert local.detect_type(skill) == "skill"
    _write(tmp_path / "agents/a.md", "x")
    assert local.detect_type(tmp_path / "agents/a.md") == "agent"
    _write(tmp_path / "commands/c.md", "x")
    assert local.detect_type(tmp_path / "commands/c.md") == "command"
    # explicit override
    assert local.detect_type(tmp_path / "whatever.md", explicit="command") == "command"


def test_detect_type_errors(tmp_path):
    (tmp_path / "loose.md").write_text("x")
    with pytest.raises(ValueError):
        local.detect_type(tmp_path / "loose.md")       # ambiguous, no hint
    with pytest.raises(ValueError):
        local.detect_type(tmp_path / "x.md", explicit="bogus")


def test_install_plan_destinations(tmp_path):
    base = tmp_path / ".claude"
    dest, is_dir = local.install_plan(Path("/src/greet"), base, "skill")
    assert dest == base / "skills/greet" and is_dir is True
    dest, is_dir = local.install_plan(Path("/src/deploy.md"), base, "command")
    assert dest == base / "commands/deploy.md" and is_dir is False
    dest, _ = local.install_plan(Path("/src/x.md"), base, "agent", name="custom")
    assert dest == base / "agents/custom.md"
