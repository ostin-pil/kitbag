#!/usr/bin/env python3
"""kitbag — one entry point to explore, (un)install, batch, and evaluate
Claude Code instruments (plugins today; MCP/skills are an extension point).

Reads the local plugin catalog cache for fast, offline explore/eval and shells
out to the `claude` CLI only for mutating actions. Curated, shareable bundles
live in bundles.yaml next to this script (override with $KITBAG_MANIFEST).
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

from . import local as _local

HOME = Path.home()
CATALOG = HOME / ".claude/plugins/plugin-catalog-cache.json"
SETTINGS = HOME / ".claude/settings.json"
INSTALLED = HOME / ".claude/plugins/installed_plugins.json"
DEFAULT_MARKET = "claude-plugins-official"
BUNDLES = Path(os.environ.get("KITBAG_MANIFEST",
                              Path(__file__).resolve().parent / "bundles.yaml"))
# token-cost model preference (catalog may not carry the very newest model)
MODEL_PREF = ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6"]
SCHEMA = 1  # manifest schema version this CLI understands

try:
    from importlib.metadata import version as _pkgver
    VERSION = _pkgver("kitbag")
except Exception:
    VERSION = "0.0.0+src"

# ---- styling -----------------------------------------------------------------
def _c(code): return "" if not sys.stdout.isatty() else code
BOLD, DIM, GRN, YEL, CYN, RED, RST = (_c("\033[1m"), _c("\033[2m"), _c("\033[32m"),
    _c("\033[33m"), _c("\033[36m"), _c("\033[31m"), _c("\033[0m"))

def die(msg): print(f"{RED}error:{RST} {msg}", file=sys.stderr); sys.exit(1)

def load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except FileNotFoundError:
        if default is not None: return default
        die(f"missing {p} — is Claude Code installed? Try: kitbag refresh")
    except json.JSONDecodeError as e:
        die(f"corrupt JSON in {p}: {e}")

# ---- catalog model -----------------------------------------------------------
class Catalog:
    def __init__(self):
        raw = load_json(CATALOG)
        self.fetched_at = raw.get("fetchedAt") or raw.get("catalog", {}).get("generated_at")
        plugins = raw.get("catalog", {}).get("plugins", {})
        self.by_name = {}      # short name -> record
        for key, e in plugins.items():
            short = key.split("@")[0]
            market = key.split("@")[1] if "@" in key else DEFAULT_MARKET
            me = e.get("marketplace_entry") or {}
            self.by_name[short] = {
                "name": short, "key": key, "market": market,
                "display": me.get("displayName") or short,
                "desc": me.get("description") or "",
                "category": me.get("category") or "",
                "tags": me.get("tags") or [],
                "keywords": me.get("keywords") or [],
                "author": (me.get("author") or {}).get("name") if isinstance(me.get("author"), dict) else me.get("author"),
                "installs": e.get("unique_installs") or 0,
                "tokens": e.get("tokens") or {},
                "components": e.get("components") or {},
            }
        # state
        self.enabled = {k.split("@")[0]: v for k, v in
                        load_json(SETTINGS, {}).get("enabledPlugins", {}).items()}
        inst = load_json(INSTALLED, {}).get("plugins", {})
        self.installed = {k.split("@")[0] for k in inst}

    def get(self, name): return self.by_name.get(name)
    def is_installed(self, name): return name in self.installed
    def is_enabled(self, name): return self.enabled.get(name) is True

    def model_for(self, rec):
        tk = rec["tokens"]
        for m in MODEL_PREF:
            if m in tk: return m
        return next(iter(tk), None)

    def cost(self, rec):
        m = self.model_for(rec)
        d = rec["tokens"].get(m, {}) if m else {}
        return d.get("always_on", 0), d.get("on_invoke", 0), m

    def comp_summary(self, rec):
        c = rec["components"]
        parts = []
        for kind, label in [("commands", "cmd"), ("agents", "agent"),
                            ("skills", "skill"), ("hooks", "hook"),
                            ("mcpServers", "mcp"), ("lspServers", "lsp")]:
            items = c.get(kind) or []
            if items: parts.append(f"{len(items)} {label}")
        return ", ".join(parts) or "—"

# ---- formatting --------------------------------------------------------------
def status_tag(cat, name):
    if cat.is_enabled(name): return f"{GRN}●{RST}"      # enabled
    if cat.is_installed(name): return f"{YEL}◐{RST}"    # installed, disabled
    return f"{DIM}○{RST}"                                # available

def fmt_k(n):
    return f"{n/1000:.0f}k" if n >= 1000 else str(n)

def print_rows(cat, recs, show_cost=True):
    if not recs: print(f"{DIM}(nothing matched){RST}"); return
    for r in recs:
        ao, oi, _ = cat.cost(r)
        cost = f"{DIM}{ao:>4}/{fmt_k(oi):>4} tok{RST}" if show_cost else ""
        inst = f"{fmt_k(r['installs']):>6}"
        print(f" {status_tag(cat, r['name'])} {BOLD}{r['name']:<26}{RST} "
              f"{DIM}{inst}{RST}  {cost}  {r['desc'][:58]}")

LEGEND = f"{DIM}legend: {GRN}● enabled{DIM}  {YEL}◐ installed{DIM}  ○ available   cost = always-on/on-invoke tokens{RST}"

# ---- commands ----------------------------------------------------------------
def cmd_search(cat, a):
    q = (a.query or "").lower()
    recs = list(cat.by_name.values())
    def hay(r): return " ".join([r["name"], r["display"], r["desc"], r["category"],
                                 " ".join(r["tags"]), " ".join(r["keywords"])]).lower()
    if q: recs = [r for r in recs if all(t in hay(r) for t in q.split())]
    if a.category: recs = [r for r in recs if r["category"] == a.category]
    if a.tag: recs = [r for r in recs if a.tag in r["tags"]]
    if a.installed: recs = [r for r in recs if cat.is_installed(r["name"])]
    keyf = {"installs": lambda r: -r["installs"],
            "cost": lambda r: -cat.cost(r)[0],
            "name": lambda r: r["name"]}[a.sort]
    recs.sort(key=keyf)
    recs = recs[:a.limit]
    if a.json: print(json.dumps([r["name"] for r in recs])); return
    print(f"{BOLD}{len(recs)} result(s){RST}  {DIM}sorted by {a.sort}{RST}")
    print_rows(cat, recs); print(); print(LEGEND)

def cmd_info(cat, a):
    r = cat.get(a.name) or die(f"unknown plugin '{a.name}' (try: kitbag search {a.name})")
    ao, oi, model = cat.cost(r)
    state = ("enabled" if cat.is_enabled(a.name) else
             "installed (disabled)" if cat.is_installed(a.name) else "available")
    print(f"{BOLD}{r['name']}{RST}  {DIM}({r['display']}){RST}")
    print(f"  {r['desc']}")
    print(f"  {DIM}source:{RST} {r['key']}   {DIM}category:{RST} {r['category'] or '—'}"
          f"   {DIM}installs:{RST} {fmt_k(r['installs'])}")
    if r["tags"]: print(f"  {DIM}tags:{RST} {', '.join(r['tags'])}")
    print(f"  {DIM}status:{RST} {state}")
    print(f"  {DIM}components:{RST} {cat.comp_summary(r)}")
    print(f"  {DIM}token cost ({model}):{RST} {ao} always-on, {oi} on-invoke")
    print(f"\n{DIM}full inventory:{RST} claude plugin details {r['name']}")

def _resolve(cat, names):
    out = []
    for n in names:
        r = cat.get(n) or die(f"unknown plugin '{n}' (try: kitbag search {n})")
        out.append(r)
    return out

def _run(argv, dry):
    print(f"{CYN}$ {' '.join(argv)}{RST}")
    if dry: return 0
    return subprocess.call(argv)

def _act(cat, names, verb, dry, note=True):
    recs = _resolve(cat, names)
    rc = 0
    for r in recs:
        if verb == "install":
            argv = ["claude", "plugin", "install", r["key"], "--scope", "user"]
        elif verb == "uninstall":
            argv = ["claude", "plugin", "uninstall", r["name"]]
        else:  # enable / disable
            argv = ["claude", "plugin", verb, r["name"]]
        rc |= _run(argv, dry)
    if note and not dry:
        print(f"\n{DIM}you may need /reload-plugins (or restart) for changes to load.{RST}")
    return rc

def cmd_install(cat, a): sys.exit(_act(cat, a.names, "install", a.dry_run))
def cmd_remove(cat, a):  sys.exit(_act(cat, a.names, "uninstall", a.dry_run))
def cmd_enable(cat, a):  sys.exit(_act(cat, a.names, "enable", a.dry_run))
def cmd_disable(cat, a): sys.exit(_act(cat, a.names, "disable", a.dry_run))

def cmd_list(cat, a):
    recs = [r for r in cat.by_name.values() if cat.is_installed(r["name"])]
    if a.enabled: recs = [r for r in recs if cat.is_enabled(r["name"])]
    recs.sort(key=lambda r: r["name"])
    print(f"{BOLD}{len(recs)} installed{RST}")
    print_rows(cat, recs); print(); print(LEGEND)

def cmd_eval(cat, a):
    if a.names:
        recs = _resolve(cat, a.names)
    else:
        recs = [r for r in cat.by_name.values() if cat.is_enabled(r["name"])]
    recs.sort(key=lambda r: -cat.cost(r)[0])
    total_ao = total_oi = 0
    model = cat.model_for(recs[0]) if recs else MODEL_PREF[0]
    print(f"{BOLD}token budget{RST}  {DIM}({len(recs)} plugins, model {model}){RST}\n")
    print(f"  {'plugin':<26}{'always-on':>11}{'on-invoke':>11}")
    for r in recs:
        ao, oi, _ = cat.cost(r)
        total_ao += ao; total_oi += oi
        flag = f" {YEL}heavy{RST}" if ao >= 200 else ""
        print(f"  {r['name']:<26}{ao:>11}{fmt_k(oi):>11}{flag}")
    print(f"  {'-'*48}")
    print(f"  {BOLD}{'TOTAL':<26}{total_ao:>11}{fmt_k(total_oi):>11}{RST}")
    print(f"\n  {DIM}always-on is added to EVERY session; on-invoke is paid per fire.{RST}")

# ---- manifest (bundles + standalone MCP registry) ---------------------------
_manifest_cache = None
def load_manifest():
    global _manifest_cache
    if _manifest_cache is not None: return _manifest_cache
    if not BUNDLES.exists():
        die(f"no manifest at {BUNDLES} (set $KITBAG_MANIFEST or use --manifest)")
    try:
        import yaml
    except ImportError:
        die("PyYAML not available; install it (pip install pyyaml)")
    data = yaml.safe_load(BUNDLES.read_text()) or {}
    sv = data.get("schema")
    if sv is not None and sv > SCHEMA:
        print(f"{YEL}warning:{RST} manifest schema v{sv} is newer than kitbag "
              f"(v{SCHEMA}); some fields may be ignored. Upgrade: pip install -U kitbag",
              file=sys.stderr)
    _manifest_cache = data
    return data

def load_bundles(): return load_manifest().get("bundles", {})
def mcp_registry(): return load_manifest().get("mcp_servers", {})

def resolve_bundle(bundles, name, seen=None):
    """Flatten a bundle to {'plugins': [...], 'mcp': [...]}, following `include:`."""
    seen = seen or set()
    if name in seen: return {"plugins": [], "mcp": []}
    seen.add(name)
    b = bundles.get(name) or die(f"unknown bundle '{name}' (try: kitbag bundle list)")
    plugins, mcp = list(b.get("plugins", [])), list(b.get("mcp", []))
    for inc in b.get("include", []):
        sub = resolve_bundle(bundles, inc, seen)
        plugins += sub["plugins"]; mcp += sub["mcp"]
    dedupe = lambda xs: list(dict.fromkeys(xs))
    return {"plugins": dedupe(plugins), "mcp": dedupe(mcp)}

# ---- standalone MCP servers --------------------------------------------------
_mcp_cache = None
def configured_mcp_names():
    """Names of MCP servers already configured (any scope). Plugin-provided
    servers are 'plugin:'-prefixed and excluded — those are managed via plugins."""
    global _mcp_cache
    if _mcp_cache is not None: return _mcp_cache
    names = set()
    try:
        out = subprocess.run(["claude", "mcp", "list"], capture_output=True,
                             text=True, timeout=60).stdout
        for line in out.splitlines():
            line = line.strip()
            if not line or ": " not in line or line.startswith("plugin:"):
                continue
            if line.lower().startswith(("checking", "no mcp")):
                continue
            names.add(line.split(": ", 1)[0].strip())
    except Exception:
        pass
    _mcp_cache = names
    return names

def mcp_add_argv(name, defn, scope="user"):
    t = (defn.get("transport") or "stdio").lower()
    argv = ["claude", "mcp", "add", "-s", scope]
    if t in ("http", "sse"):
        argv += ["--transport", t]
        for h in defn.get("headers", []): argv += ["-H", h]
        url = defn.get("url") or die(f"mcp '{name}': {t} transport needs a 'url'")
        argv += [name, url]
    else:
        for e in defn.get("env", []): argv += ["-e", e]
        cmd = defn.get("command") or die(f"mcp '{name}': stdio transport needs a 'command'")
        argv += [name, "--", cmd] + list(defn.get("args", []))
    return argv

def _mcp_act(names, verb, dry, reg, scope="user"):
    rc = 0
    for n in names:
        if verb == "add":
            d = reg.get(n) or die(f"unknown mcp server '{n}' — define it under "
                                  f"mcp_servers in {BUNDLES}")
            argv = mcp_add_argv(n, d, scope)
        else:
            argv = ["claude", "mcp", "remove", "-s", scope, n]
        rc |= _run(argv, dry)
    return rc

def _mcp_tag(name, configured): return f"{GRN}●{RST}" if name in configured else f"{DIM}○{RST}"

def cmd_mcp_list(cat, a):
    reg, configured = mcp_registry(), configured_mcp_names()
    print(f"{BOLD}MCP registry{RST}  {DIM}({len(reg)} defined in {BUNDLES.name}){RST}\n")
    for name, d in reg.items():
        t = (d.get("transport") or "stdio")
        target = d.get("url") or " ".join([d.get("command", "")] + list(d.get("args", [])))
        print(f" {_mcp_tag(name, configured)} {BOLD}{name:<20}{RST} {DIM}{t:<5}{RST} {target[:48]}")
    extra = [n for n in sorted(configured) if n not in reg]
    if extra:
        print(f"\n {DIM}also configured (not in registry): {', '.join(extra)}{RST}")
    print(f"\n{DIM}● configured  ○ not yet   add: kitbag mcp add <name>{RST}")

def cmd_mcp_add(cat, a): sys.exit(_mcp_act(a.names, "add", a.dry_run, mcp_registry(), a.scope))
def cmd_mcp_remove(cat, a): sys.exit(_mcp_act(a.names, "remove", a.dry_run, mcp_registry(), a.scope))

def cmd_mcp_info(cat, a):
    d = mcp_registry().get(a.name) or die(f"unknown mcp server '{a.name}'")
    state = "configured" if a.name in configured_mcp_names() else "not configured"
    print(f"{BOLD}{a.name}{RST}  {DIM}({state}){RST}")
    for k, v in d.items(): print(f"  {DIM}{k}:{RST} {v}")
    print(f"\n{DIM}would run:{RST} {' '.join(mcp_add_argv(a.name, d, a.scope if hasattr(a,'scope') else 'user'))}")

# ---- bundles -----------------------------------------------------------------
def cmd_bundle_list(cat, a):
    bundles = load_bundles()
    configured = None
    print(f"{BOLD}{len(bundles)} bundle(s){RST}  {DIM}from {BUNDLES}{RST}\n")
    for name, b in bundles.items():
        res = resolve_bundle(bundles, name)
        np, nm = len(res["plugins"]), len(res["mcp"])
        if nm and configured is None: configured = configured_mcp_names()
        active = sum(1 for p in res["plugins"] if cat.is_enabled(p))
        active += sum(1 for m in res["mcp"] if m in (configured or set()))
        mcp_s = f"+{nm}m" if nm else ""
        print(f"  {BOLD}{name:<16}{RST} {DIM}{np}p{mcp_s:<3} {active} active{RST}  "
              f"{b.get('description','')[:48]}")
    print(f"\n{DIM}see one: kitbag bundle show <name>{RST}")

def cmd_bundle_show(cat, a):
    bundles = load_bundles()
    res = resolve_bundle(bundles, a.name)
    b = bundles[a.name]
    print(f"{BOLD}{a.name}{RST}  {DIM}{b.get('description','')}{RST}")
    if b.get("include"): print(f"  {DIM}includes:{RST} {', '.join(b['include'])}")
    print()
    recs = [cat.get(p) for p in res["plugins"]]
    missing = [p for p, r in zip(res["plugins"], recs) if r is None]
    print_rows(cat, [r for r in recs if r])
    if missing: print(f" {RED}not in catalog:{RST} {', '.join(missing)}")
    if res["mcp"]:
        reg, configured = mcp_registry(), configured_mcp_names()
        print(f"\n {DIM}MCP servers:{RST}")
        for m in res["mcp"]:
            d = reg.get(m, {})
            t = d.get("transport") or "stdio"
            print(f" {_mcp_tag(m, configured)} {BOLD}{m:<20}{RST} {DIM}{t}{RST}"
                  + ("" if m in reg else f"  {RED}(not in registry){RST}"))
    print(); print(LEGEND)

def cmd_bundle_diff(cat, a):
    bundles = load_bundles()
    res = resolve_bundle(bundles, a.name)
    miss_p = [p for p in res["plugins"] if not cat.is_installed(p)]
    have_p = [p for p in res["plugins"] if cat.is_installed(p)]
    print(f"{BOLD}bundle {a.name}{RST} vs current state:")
    print(f"  {GRN}plugins installed:{RST} {', '.join(have_p) or '—'}")
    print(f"  {YEL}plugins missing:{RST}   {', '.join(miss_p) or '— (all installed)'}")
    miss_m = []
    if res["mcp"]:
        configured = configured_mcp_names()
        have_m = [m for m in res["mcp"] if m in configured]
        miss_m = [m for m in res["mcp"] if m not in configured]
        print(f"  {GRN}mcp configured:{RST}    {', '.join(have_m) or '—'}")
        print(f"  {YEL}mcp missing:{RST}       {', '.join(miss_m) or '— (all configured)'}")
    if miss_p or miss_m:
        print(f"\n{DIM}apply: kitbag bundle install {a.name}{RST}")

def cmd_bundle_install(cat, a):
    bundles = load_bundles()
    res = resolve_bundle(bundles, a.name)
    reg, configured = mcp_registry(), configured_mcp_names()
    todo_p = res["plugins"] if a.force else [p for p in res["plugins"] if not cat.is_installed(p)]
    todo_m = res["mcp"] if a.force else [m for m in res["mcp"] if m not in configured]
    if not todo_p and not todo_m:
        print(f"{GRN}bundle '{a.name}' already fully applied.{RST}"); return
    print(f"{BOLD}installing bundle '{a.name}'{RST}")
    if todo_p: print(f"  plugins: {', '.join(todo_p)}")
    if todo_m: print(f"  mcp:     {', '.join(todo_m)}")
    print()
    rc = 0
    if todo_p: rc |= _act(cat, todo_p, "install", a.dry_run, note=not todo_m)
    if todo_m: rc |= _mcp_act(todo_m, "add", a.dry_run, reg)
    sys.exit(rc)

def cmd_bundle_remove(cat, a):
    bundles = load_bundles()
    res = resolve_bundle(bundles, a.name)
    reg, configured = mcp_registry(), configured_mcp_names()
    rm_p = [p for p in res["plugins"] if cat.is_installed(p)]
    rm_m = [m for m in res["mcp"] if m in configured]
    if not rm_p and not rm_m:
        print(f"{DIM}nothing from bundle '{a.name}' is installed.{RST}"); return
    print(f"{BOLD}removing bundle '{a.name}'{RST}")
    if rm_p: print(f"  plugins: {', '.join(rm_p)}")
    if rm_m: print(f"  mcp:     {', '.join(rm_m)}")
    print()
    rc = 0
    if rm_p: rc |= _act(cat, rm_p, "uninstall", a.dry_run, note=not rm_m)
    if rm_m: rc |= _mcp_act(rm_m, "remove", a.dry_run, reg)
    sys.exit(rc)

def cmd_refresh(cat, a):
    sys.exit(_run(["claude", "plugin", "marketplace", "update"], a.dry_run))

def cmd_status(cat, a):
    inst = [r for r in cat.by_name.values() if cat.is_installed(r["name"])]
    en = [r for r in inst if cat.is_enabled(r["name"])]
    total_ao = sum(cat.cost(r)[0] for r in en)
    print(f"{BOLD}kitbag status{RST}")
    print(f"  catalog: {len(cat.by_name)} plugins  {DIM}(fetched {cat.fetched_at}){RST}")
    print(f"  installed: {len(inst)}   enabled: {len(en)}")
    print(f"  always-on token budget (enabled): {BOLD}{total_ao}{RST} tok/session")
    heavy = sorted(en, key=lambda r: -cat.cost(r)[0])[:3]
    if heavy:
        print(f"  heaviest: " + ", ".join(f"{r['name']}({cat.cost(r)[0]})" for r in heavy))
    local_ao = sum(x.always_on for x in _collect_local())
    if local_ao:
        print(f"  local artifacts always-on: {local_ao} tok/session")
        print(f"  {BOLD}true always-on (plugins+local): {total_ao + local_ao}{RST} tok/session")
    print(f"\n{DIM}explore: kitbag search <q>   bundles: kitbag bundle list   local: kitbag local list{RST}")

# ---- local artifacts (your own skills/commands/agents/output-styles) --------
def _local_bases():
    return [(HOME / ".claude", "user"), (Path.cwd() / ".claude", "project")]

def _active_style():
    s = load_json(SETTINGS, {})
    return s.get("outputStyle") or s.get("output_style")

def _collect_local():
    arts = _local.discover(_local_bases(), active_style=_active_style())
    arts += _local.memory_artifacts([
        (HOME / ".claude/CLAUDE.md", "user"),
        (Path.cwd() / "CLAUDE.md", "project"),
        (Path.cwd() / ".claude/CLAUDE.md", "project"),
    ])
    arts += _local.hook_artifacts(load_json(SETTINGS, {}), "user")
    ps = Path.cwd() / ".claude/settings.json"
    if ps.exists():
        arts += _local.hook_artifacts(load_json(ps, {}), "project")
    return arts

_TYPE_ORDER = {t: i for i, t in enumerate(_local.ALL_TYPES)}

def _print_local(arts):
    if not arts:
        print(f"{DIM}(no local artifacts found under ~/.claude or ./.claude){RST}"); return
    arts = sorted(arts, key=lambda x: (_TYPE_ORDER.get(x.type, 9), x.scope, x.name))
    print(f"  {DIM}{'type':<13}{'name':<26}{'scope':<8}{'always':>7}{'invoke':>8}  desc{RST}")
    for x in arts:
        act = f" {GRN}(active){RST}" if x.active else ""
        print(f"  {x.type:<13}{BOLD}{x.name[:24]:<24}{RST}  {x.scope:<8}"
              f"{x.always_on:>7}{fmt_k(x.on_invoke):>8}  {DIM}{x.description[:38]}{RST}{act}")

def cmd_local_list(cat, a):
    arts = _collect_local()
    if a.type: arts = [x for x in arts if x.type == a.type]
    if a.scope: arts = [x for x in arts if x.scope == a.scope]
    print(f"{BOLD}{len(arts)} local artifact(s){RST}  {DIM}(token cost is estimated){RST}\n")
    _print_local(arts)
    print(f"\n{DIM}always-on loads every session; invoke is paid when fired. "
          f"copy-install: kitbag local add <path>{RST}")

def cmd_local_eval(cat, a):
    arts = _collect_local()
    ao = sum(x.always_on for x in arts)
    oi = sum(x.on_invoke for x in arts)
    top = sorted((x for x in arts if x.always_on), key=lambda x: -x.always_on)[:5]
    print(f"{BOLD}local token budget{RST}  {DIM}({len(arts)} artifacts, estimated){RST}\n")
    print(f"  always-on total: {BOLD}{ao}{RST} tok/session")
    print(f"  on-invoke total: {fmt_k(oi)} tok (paid per fire)")
    if top:
        print(f"\n  {DIM}heaviest always-on:{RST}")
        for x in top:
            print(f"    {x.always_on:>5}  {x.type}/{x.name}")
    print(f"\n  {DIM}combine with plugins: kitbag status{RST}")

def cmd_local_add(cat, a):
    src = Path(a.source).expanduser()
    if not src.exists(): die(f"source not found: {src}")
    try:
        atype = _local.detect_type(src, a.type)
    except ValueError as e:
        die(str(e))
    if atype == "skill" and not src.is_dir():
        die("skill source must be a directory containing SKILL.md")
    base = HOME / ".claude" if a.scope == "user" else Path.cwd() / ".claude"
    dest, is_dir = _local.install_plan(src, base, atype, a.name)
    if dest.exists() and not a.force:
        die(f"{atype} already exists at {dest} (use --force to overwrite)")
    print(f"{BOLD}install {atype}{RST} {DIM}({a.scope}){RST}: {src} {CYN}->{RST} {dest}")
    if a.dry_run: return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_dir:
        if dest.exists(): shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    print(f"{GRN}installed.{RST} {DIM}run /reload-plugins (or restart) to load it.{RST}")

def cmd_local_remove(cat, a):
    matches = [x for x in _collect_local() if x.type == a.type and x.name == a.name
               and (a.scope is None or x.scope == a.scope)]
    if not matches:
        die(f"no local {a.type} named '{a.name}'" + (f" in {a.scope}" if a.scope else ""))
    if len(matches) > 1:
        die(f"'{a.name}' matches {a.type} in multiple scopes; pass --scope user|project")
    art = matches[0]
    if art.type not in _local.COPYABLE:
        die(f"{art.type} is read-only in kitbag; edit {art.path} yourself")
    p = Path(art.path)
    target = p.parent if art.type == "skill" else p
    print(f"{BOLD}remove {art.type}{RST} {DIM}({art.scope}){RST}: {target}")
    if a.dry_run: return
    if art.type == "skill": shutil.rmtree(target)
    else: p.unlink()
    print(f"{GRN}removed.{RST}")

# ---- argparse ----------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="kitbag", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"kitbag {VERSION}")
    p.add_argument("--manifest", metavar="PATH",
                   help="manifest file to use (overrides $KITBAG_MANIFEST / packaged default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search the catalog")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--category"); s.add_argument("--tag")
    s.add_argument("--installed", action="store_true")
    s.add_argument("--sort", choices=["installs", "cost", "name"], default="installs")
    s.add_argument("--limit", type=int, default=25); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("info", help="show plugin detail + token cost")
    s.add_argument("name"); s.set_defaults(fn=cmd_info)

    for verb, fn, help in [("install", cmd_install, "install plugin(s)"),
                           ("remove", cmd_remove, "uninstall plugin(s)"),
                           ("enable", cmd_enable, "enable plugin(s)"),
                           ("disable", cmd_disable, "disable plugin(s)")]:
        s = sub.add_parser(verb, help=help)
        s.add_argument("names", nargs="+")
        s.add_argument("--dry-run", action="store_true", help="print commands, don't run")
        s.set_defaults(fn=fn)

    s = sub.add_parser("list", help="list installed plugins")
    s.add_argument("--enabled", action="store_true"); s.set_defaults(fn=cmd_list)

    s = sub.add_parser("eval", help="token-cost report (enabled set, or given names)")
    s.add_argument("names", nargs="*"); s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("status", help="summary of installed/enabled + token budget")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("refresh", help="refresh the marketplace catalog")
    s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_refresh)

    m = sub.add_parser("mcp", help="standalone MCP servers (registry in bundles.yaml)").add_subparsers(dest="mcmd", required=True)
    m.add_parser("list", help="list registry + configured MCP servers").set_defaults(fn=cmd_mcp_list)
    x = m.add_parser("info", help="show a registry MCP server"); x.add_argument("name")
    x.add_argument("--scope", default="user"); x.set_defaults(fn=cmd_mcp_info)
    x = m.add_parser("add", help="configure MCP server(s) from the registry"); x.add_argument("names", nargs="+")
    x.add_argument("--scope", choices=["local", "user", "project"], default="user")
    x.add_argument("--dry-run", action="store_true"); x.set_defaults(fn=cmd_mcp_add)
    x = m.add_parser("remove", help="remove configured MCP server(s)"); x.add_argument("names", nargs="+")
    x.add_argument("--scope", choices=["local", "user", "project"], default="user")
    x.add_argument("--dry-run", action="store_true"); x.set_defaults(fn=cmd_mcp_remove)

    b = sub.add_parser("bundle", help="curated workflow bundles").add_subparsers(dest="bcmd", required=True)
    b.add_parser("list", help="list bundles").set_defaults(fn=cmd_bundle_list)
    x = b.add_parser("show", help="show a bundle's plugins"); x.add_argument("name"); x.set_defaults(fn=cmd_bundle_show)
    x = b.add_parser("diff", help="installed vs bundle"); x.add_argument("name"); x.set_defaults(fn=cmd_bundle_diff)
    x = b.add_parser("install", help="install a bundle"); x.add_argument("name")
    x.add_argument("--force", action="store_true"); x.add_argument("--dry-run", action="store_true"); x.set_defaults(fn=cmd_bundle_install)
    x = b.add_parser("remove", help="remove a bundle's plugins"); x.add_argument("name")
    x.add_argument("--dry-run", action="store_true"); x.set_defaults(fn=cmd_bundle_remove)

    l = sub.add_parser("local", help="your own skills/commands/agents/output-styles (+ memory/hooks)").add_subparsers(dest="lcmd", required=True)
    x = l.add_parser("list", help="list local artifacts with estimated token cost")
    x.add_argument("--type", choices=_local.ALL_TYPES)
    x.add_argument("--scope", choices=["user", "project"])
    x.set_defaults(fn=cmd_local_list, needs_catalog=False)
    x = l.add_parser("eval", help="token budget for local artifacts")
    x.set_defaults(fn=cmd_local_eval, needs_catalog=False)
    x = l.add_parser("add", help="copy-install a skill dir / command|agent|output-style .md")
    x.add_argument("source", help="path to a skill directory or a .md file")
    x.add_argument("--type", choices=list(_local.COPYABLE), help="override auto-detected type")
    x.add_argument("--scope", choices=["user", "project"], default="user")
    x.add_argument("--name", help="install under a different name")
    x.add_argument("--force", action="store_true", help="overwrite if it exists")
    x.add_argument("--dry-run", action="store_true")
    x.set_defaults(fn=cmd_local_add, needs_catalog=False)
    x = l.add_parser("remove", help="remove a local artifact")
    x.add_argument("type", choices=list(_local.COPYABLE))
    x.add_argument("name")
    x.add_argument("--scope", choices=["user", "project"])
    x.add_argument("--dry-run", action="store_true")
    x.set_defaults(fn=cmd_local_remove, needs_catalog=False)

    g = sub.add_parser("generate", help="generate distributable artifacts from the manifest").add_subparsers(dest="gcmd", required=True)
    x = g.add_parser("marketplace", help="emit a Claude Code marketplace repo from bundles")
    x.add_argument("--out", default="dist/marketplace", help="output directory")
    x.add_argument("--layout", choices=["per-bundle", "single"], default="per-bundle")
    x.add_argument("--name", default="kitbag-bundles", help="marketplace name")
    x.add_argument("--author", default="kitbag authors")
    x.add_argument("--dry-run", action="store_true", help="list files, don't write")
    x.set_defaults(fn=cmd_generate_marketplace, needs_catalog=False)
    return p

def cmd_generate_marketplace(cat, a):
    from . import generate as gen
    files = gen.build_marketplace(load_manifest(), name=a.name, author=a.author,
                                  layout=a.layout)
    if a.dry_run:
        print(f"{BOLD}{len(files)} file(s){RST} would be written to {a.out}/ "
              f"{DIM}(layout: {a.layout}){RST}")
        for rel in sorted(files): print(f"  {rel}")
        return
    written = gen.write_tree(a.out, files)
    print(f"{BOLD}generated marketplace{RST} -> {a.out}/  "
          f"{DIM}({len(written)} files, layout: {a.layout}){RST}")
    print(f"\n{DIM}next:{RST}")
    print(f"  cd {a.out} && git init -q && git add -A && git commit -qm 'kitbag marketplace'")
    print(f"  claude plugin marketplace add <owner>/<repo>")
    print(f"  claude plugin install <bundle>@{a.name}")

def main():
    global BUNDLES
    args = build_parser().parse_args()
    if getattr(args, "manifest", None):
        BUNDLES = Path(args.manifest).expanduser()
    try:
        cat = Catalog() if getattr(args, "needs_catalog", True) else None
        args.fn(cat, args)
    except KeyboardInterrupt:
        sys.exit(130)

if __name__ == "__main__":
    main()
