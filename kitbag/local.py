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
from urllib.parse import urlparse, parse_qs

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
    name = safe_name(name or (src.name if atype == "skill" else src.stem))
    base = Path(base)
    if atype == "skill":
        return base / "skills" / name, True
    sub = {"command": "commands", "agent": "agents",
           "output-style": "output-styles"}[atype]
    return base / sub / f"{name}.md", False


def safe_name(name):
    """Guard against path traversal in a derived artifact name."""
    if not name or "/" in name or "\\" in name or name.startswith(".") or ".." in name:
        raise ValueError(f"unsafe artifact name: {name!r}")
    return name


LOCAL_SPEC_KEYS = ("source", "type", "path", "ref", "name", "scope")

def normalize_local_entry(e):
    """Normalize a bundle `local:` entry (str shorthand or dict) to a spec dict.

    A bare string is treated as `source`. Dicts must carry a `source`; unknown
    keys are dropped. `type`/`scope` are validated when present.
    """
    if isinstance(e, str):
        e = {"source": e}
    if not isinstance(e, dict) or not e.get("source"):
        raise ValueError(f"local entry needs a 'source': {e!r}")
    spec = {k: e[k] for k in LOCAL_SPEC_KEYS if e.get(k) is not None}
    if spec.get("type") and spec["type"] not in COPYABLE:
        raise ValueError(f"local entry type must be one of {', '.join(COPYABLE)}")
    if spec.get("scope") and spec["scope"] not in ("user", "project"):
        raise ValueError("local entry scope must be 'user' or 'project'")
    return spec


# ---- remote sources (git URL / raw file) ------------------------------------
@dataclass
class Source:
    kind: str                 # local | git | raw
    path: str = ""            # local: filesystem path
    repo: str = ""            # git: clone URL
    ref: str | None = None    # git: branch/tag/sha
    subpath: str | None = None  # git: path within repo
    single_file: bool = False  # git blob / raw: a single .md
    url: str = ""             # raw: download URL


def _is_url(s):
    return s.startswith(("http://", "https://", "git@", "ssh://")) or s.endswith(".git")


def parse_source(source, *, exists=None):
    """Classify an `add` source into local / git / raw. Pure (network-free).

    Handles: local paths; github.com tree|blob URLs; raw.githubusercontent /
    gist raw / generic *.md URLs; plain git URLs (https, git@, ssh, *.git);
    `owner/repo[/tree|blob/ref/subpath]` shorthand; and a `#ref=..&path=..`
    fragment on any URL. `exists` overrides the local-path check (for tests).
    """
    raw = source.strip()
    s = raw
    is_local = exists if exists is not None else Path(s).expanduser().exists()
    if is_local and not _is_url(s):
        return Source("local", path=str(Path(s).expanduser()))

    # split off a #ref=..&path=.. fragment
    frag_ref = frag_path = None
    if "#" in s:
        s, frag = s.split("#", 1)
        q = parse_qs(frag)
        frag_ref = (q.get("ref") or [None])[0]
        frag_path = (q.get("path") or [None])[0]

    # github.com tree/blob (clone + copy subpath so type auto-detects)
    m = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?"
                 r"(?:/(tree|blob)/([^/]+)/(.+?))?/?$", s)
    if m:
        return Source("git", repo=f"https://github.com/{m.group(1)}.git",
                      ref=m.group(3) or frag_ref, subpath=m.group(4) or frag_path,
                      single_file=m.group(2) == "blob")

    # raw single-file download (raw.githubusercontent, gist raw, generic *.md)
    low = s.lower()
    if re.match(r"https?://", s) and (low.startswith("https://raw.")
                                      or "/raw/" in low or low.endswith(".md")):
        return Source("raw", url=s, single_file=True)

    # plain git URL
    if _is_url(s):
        return Source("git", repo=s, ref=frag_ref, subpath=frag_path)

    # owner/repo[/tree|blob/ref/subpath] shorthand
    m = re.match(r"^([\w.-]+/[\w.-]+)(?:/(tree|blob)/([^/]+)/(.+))?$", s)
    if m and not is_local:
        return Source("git", repo=f"https://github.com/{m.group(1)}.git",
                      ref=m.group(3) or frag_ref, subpath=m.group(4) or frag_path,
                      single_file=m.group(2) == "blob")

    return Source("local", path=str(Path(raw).expanduser()))


def _git_clone(repo, ref, dest):  # impure; monkeypatched in tests
    import subprocess
    argv = ["git", "clone", "--depth", "1"] + (["--branch", ref] if ref else []) \
        + [repo, str(dest)]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"git clone failed: {r.stderr.strip()[:200]}")


def _download(url, dest):  # impure; monkeypatched in tests
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "kitbag"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(5_000_000)  # 5 MB cap
    Path(dest).write_bytes(data)


def fetch_source(src: Source, workdir, *, clone=None, download=None):
    """Materialize a remote Source under workdir; return the local artifact path.
    `clone`/`download` are injectable so orchestration is testable without network."""
    clone = clone or _git_clone
    download = download or _download
    work = Path(workdir)
    if src.kind == "local":
        return Path(src.path)
    if src.kind == "raw":
        name = Path(urlparse(src.url).path).name or "artifact.md"
        dest = work / name
        download(src.url, dest)
        return dest
    if src.kind == "git":
        repo_dir = work / "repo"
        clone(src.repo, src.ref, repo_dir)
        target = repo_dir / src.subpath if src.subpath else repo_dir
        if not Path(target).exists():
            raise ValueError(f"path '{src.subpath}' not found in {src.repo}")
        return Path(target)
    raise ValueError(f"unknown source kind: {src.kind}")
