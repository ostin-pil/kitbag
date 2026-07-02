"""Local artifacts — discover, token-cost, and (for file-based types) copy-install
the user's own Claude Code instruments living under `.claude/` (and CLAUDE.md).

Unlike marketplace plugins, local artifacts have no catalog, so kitbag scans the
filesystem and *estimates* token cost with a ~4-chars/token heuristic:

  - skill / agent : always-on ≈ name + description (what's injected so Claude can
                    decide to trigger it); on-invoke ≈ the full body.
  - command       : on-invoke only (body loads when the command runs).
  - output-style  : full body, but only counted always-on when it's the *active* style.
  - memory        : CLAUDE.md loads in full every session -> all always-on.
  - hook          : behavioural, not context tokens -> listed, costed at 0.

Everything here is pure and takes base paths as arguments so it is unit-testable
against temp directories.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

# file/dir-based types kitbag can copy-install; the rest are read-only in v1.
COPYABLE = ("skill", "command", "agent", "output-style")
ALL_TYPES = COPYABLE + ("memory", "hook")


def estimate_tokens(text) -> int:
    """Rough token estimate (~4 chars/token). Approximate, not a real tokenizer."""
    text = text or ""
    return (len(text) + 3) // 4


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)

def parse_frontmatter(md: str):
    """Return (frontmatter_dict, body). Empty dict if no YAML frontmatter."""
    m = _FM_RE.match(md or "")
    if not m:
        return {}, md or ""
    try:
        import yaml
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, m.group(2)


@dataclass
class Artifact:
    type: str            # skill|command|agent|output-style|memory|hook
    name: str
    scope: str           # user|project
    path: str
    description: str = ""
    always_on: int = 0
    on_invoke: int = 0
    active: bool | None = None   # output-style: is it the active one?

    def as_dict(self):
        return {k: getattr(self, k) for k in
                ("type", "name", "scope", "path", "description",
                 "always_on", "on_invoke", "active")}


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _skills(base: Path, scope: str):
    d = base / "skills"
    if not d.is_dir():
        return
    for sub in sorted(p for p in d.iterdir() if p.is_dir()):
        f = sub / "SKILL.md"
        if not f.is_file():
            continue
        fm, body = parse_frontmatter(_read(f))
        name = fm.get("name") or sub.name
        desc = fm.get("description", "")
        yield Artifact("skill", name, scope, str(f), desc,
                       estimate_tokens(f"{name}: {desc}"), estimate_tokens(body))


def _md_files(base: Path, kind: str):
    d = base / kind
    if not d.is_dir():
        return
    for f in sorted(d.rglob("*.md")):
        if f.is_file():
            yield f


def _commands(base: Path, scope: str):
    d = base / "commands"
    for f in _md_files(base, "commands"):
        fm, body = parse_frontmatter(_read(f))
        name = f.relative_to(d).with_suffix("").as_posix()
        yield Artifact("command", name, scope, str(f), fm.get("description", ""),
                       0, estimate_tokens(body))


def _agents(base: Path, scope: str):
    d = base / "agents"
    for f in _md_files(base, "agents"):
        fm, body = parse_frontmatter(_read(f))
        name = fm.get("name") or f.relative_to(d).with_suffix("").as_posix()
        desc = fm.get("description", "")
        yield Artifact("agent", name, scope, str(f), desc,
                       estimate_tokens(f"{name}: {desc}"), estimate_tokens(body))


def _output_styles(base: Path, scope: str, active_style):
    d = base / "output-styles"
    for f in _md_files(base, "output-styles"):
        fm, body = parse_frontmatter(_read(f))
        name = fm.get("name") or f.stem
        is_active = active_style is not None and name == active_style
        yield Artifact("output-style", name, scope, str(f),
                       fm.get("description", ""),
                       estimate_tokens(body) if is_active else 0,
                       0, active=is_active)


def discover(bases, *, active_style=None):
    """Discover file/dir-based artifacts. `bases` = iterable of (Path, scope)."""
    out = []
    for base, scope in bases:
        base = Path(base)
        out += list(_skills(base, scope))
        out += list(_commands(base, scope))
        out += list(_agents(base, scope))
        out += list(_output_styles(base, scope, active_style))
    return out


def memory_artifacts(entries):
    """`entries` = iterable of (path, scope) for CLAUDE.md files."""
    out = []
    for path, scope in entries:
        p = Path(path)
        if not p.is_file():
            continue
        text = _read(p)
        first = next((ln.strip("# ").strip() for ln in text.splitlines()
                      if ln.strip()), "")
        out.append(Artifact("memory", p.name, scope, str(p), first[:80],
                            estimate_tokens(text), 0))
    return out


def hook_artifacts(settings: dict, scope: str):
    """Flatten settings.json `hooks` into read-only artifacts (0 context tokens)."""
    out = []
    for event, matchers in (settings.get("hooks") or {}).items():
        for m in matchers if isinstance(matchers, list) else []:
            pat = m.get("matcher", "*")
            cmds = [h.get("command", "") for h in (m.get("hooks") or [])]
            out.append(Artifact("hook", f"{event}:{pat}", scope, "settings.json",
                                "; ".join(c[:40] for c in cmds), 0, 0))
    return out


# ---- install (copy) ----------------------------------------------------------
def detect_type(src: Path, explicit=None):
    """Infer artifact type from a source path. Returns one of COPYABLE or raises."""
    src = Path(src)
    if explicit:
        if explicit not in COPYABLE:
            raise ValueError(f"--type must be one of {', '.join(COPYABLE)}")
        return explicit
    if src.is_dir():
        if (src / "SKILL.md").is_file():
            return "skill"
        raise ValueError(f"directory {src} has no SKILL.md; not a skill")
    parent = src.parent.name
    hint = {"agents": "agent", "commands": "command",
            "output-styles": "output-style"}.get(parent)
    if hint:
        return hint
    raise ValueError("cannot infer type from path; pass --type "
                     f"({'/'.join(COPYABLE)})")


def install_plan(src: Path, base: Path, atype, name=None):
    """Return (dest_path, is_dir) where the artifact should be copied. Pure."""
    src = Path(src)
    name = name or (src.name if atype == "skill" else src.stem)
    base = Path(base)
    if atype == "skill":
        return base / "skills" / name, True
    sub = {"command": "commands", "agent": "agents",
           "output-style": "output-styles"}[atype]
    return base / sub / f"{name}.md", False
