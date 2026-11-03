import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, github, index, manifest, out, palette, project, store
from .errors import ShelfError
from .paths import DEFAULTS, home, load_config, packages_dir, save_config
from .spec import parse

JSON = False


def log(msg):
    if not JSON:
        out.note("  " + msg)


def show_warnings(warnings):
    for w in warnings:
        if not JSON:
            out.warn(w)


def label(version, ref=None, sha=None):
    if version in (None, "", "0.0.0") and ref:
        return f"{ref}@{sha[:7]}" if sha else ref
    return version or "?"


def _installed_lines(done):
    for d in done:
        ver = label(d["version"], d.get("ref"), d.get("sha"))
        prev = d.get("previous")
        if prev == "0.0.0" and d.get("previous_sha"):
            prev = d["previous_sha"][:7]
        change = f" {out.dim('was ' + prev)}" if prev and d.get("previous_sha") != d.get("sha") else ""
        dep = f" {out.dim('for ' + d['dependency_of'])}" if d.get("dependency_of") else ""
        out.say(out.green("+"), out.bold(d["name"]), ver + change + dep)


def cmd_install(a):
    if a.project:
        return cmd_add(a)
    done, warnings = store.install(a.packages, log=log, link=not a.no_palette, td_build=a.td)
    show_warnings(warnings)
    if JSON:
        return {"installed": done, "warnings": warnings}
    _installed_lines(done)
    if any(d["palette"] for d in done):
        out.say(out.dim("in td: palette > My Components > shelf (right click > Refresh Folder if it's not there yet)"))
    elif done and not a.no_palette:
        out.say(out.dim("couldn't find your td palette folder, run `shelf palette` to sort it out"))


def cmd_remove(a):
    root = project.find() if not a.globally else None
    if root and not a.globally and any(n in project.read_lock(root)["packages"] or n in manifest.load(root).dependencies for n in a.names):
        gone = project.drop(root, a.names)
        if JSON:
            return {"removed": gone, "project": str(root)}
        for n in gone:
            out.say(out.red("-"), n)
        return
    gone = store.remove(a.names, force=a.force)
    if JSON:
        return {"removed": gone}
    for n in gone:
        out.say(out.red("-"), n)


def cmd_list(a):
    root = None if a.globally else project.find()
    if root:
        rows = project.listing(root)
        if JSON:
            return {"project": str(root), "packages": rows}
        out.say(out.dim(f"project {root}"))
        if not rows:
            out.say("nothing yet, try `shelf add owner/repo`")
            return
        out.table([[r["name"], label(r["version"], r.get("ref"), r.get("sha")), r["from"], ("for " + r["dependency_of"]) if r["dependency_of"] else ""] for r in rows], ["name", "version", "from", ""])
        return
    pk = store.installed()
    rows = []
    for name, e in sorted(pk.items()):
        rows.append(
            {
                "name": name,
                "version": e.get("version"),
                "from": e.get("source"),
                "ref": e.get("ref"),
                "sha": e.get("sha"),
                "dependency_of": ", ".join(e.get("dependents", [])) or None,
                "requested": e.get("requested"),
                "tox": store.where(name),
                "palette": bool(e.get("palette")),
                "description": e.get("description", ""),
            }
        )
    if JSON:
        return {"packages": rows, "home": str(packages_dir())}
    if not rows:
        out.say("nothing installed yet, try `shelf install wintd` or `shelf search`")
        return
    out.table(
        [[r["name"], label(r["version"], r.get("ref"), r.get("sha")), r["from"], ("for " + r["dependency_of"]) if r["dependency_of"] and not r["requested"] else ""] for r in rows],
        ["name", "version", "from", ""],
    )


def cmd_update(a):
    root = None if a.globally else project.find()
    if root:
        done, gone, warnings = project.sync(root, update=True, log=log)
        show_warnings(warnings)
        if JSON:
            return {"updated": done, "removed": gone, "project": str(root), "warnings": warnings}
        _installed_lines(done)
        return
    done, warnings = store.update(a.names or None, log=log, td_build=a.td)
    show_warnings(warnings)
    if JSON:
        return {"updated": done, "warnings": warnings}
    changed = [d for d in done if d.get("previous") != d["version"] or d.get("previous_sha") != d.get("sha")]
    if not changed:
        out.say("everything's up to date")
    _installed_lines(changed)


def cmd_search(a):
    q = " ".join(a.query)
    data = index.load(refresh=a.refresh)
    hits = index.search(q, data)
    found = []
    for h in hits:
        found.append({"name": h["name"], "repo": h.get("source"), "description": h.get("description", ""), "indexed": True})
    if not a.index_only:
        known = {h.get("source", "").lower() for h in hits}
        try:
            for r in github.search(q, limit=a.limit):
                if r["repo"].lower() in known:
                    continue
                found.append({"name": r["repo"], "repo": r["repo"], "description": r["description"], "stars": r["stars"], "indexed": False})
        except ShelfError as e:
            if not JSON:
                out.warn(f"github search didn't work ({e})")
    if JSON:
        return {"results": found}
    if not found:
        out.say("nothing found")
        return
    for f in found:
        tag = out.cyan(f["name"]) if f["indexed"] else f["name"]
        stars = out.dim(f"  ★{f['stars']}") if f.get("stars") else ""
        out.say(tag + stars)
        if f["description"]:
            out.say(out.dim("  " + f["description"][:100]))
    out.say("")
    out.say(out.dim("install with `shelf install <name>`. blue ones are in the shelf index"))


def cmd_info(a):
    root = project.find()
    name = a.package.lower()
    e = store.get(name)
    if e and not a.remote:
        res = dict(e, name=name, tox=store.where(name), installed=True)
        if JSON:
            return res
        out.say(out.bold(name), label(e.get("version"), e.get("ref"), e.get("sha")))
        if e.get("description"):
            out.say(e["description"])
        out.say(out.dim("from"), e.get("source"), out.dim(e.get("ref") or ""))
        for t in res["tox"] or []:
            out.say(out.dim("tox "), t)
        return
    if root:
        w = project.where(root, name)
        if w and not a.remote:
            res = {"name": name, "tox": w, "installed": True, "project": str(root)}
            if JSON:
                return res
            out.say(out.bold(name), out.dim("in this project"))
            for t in w:
                out.say(out.dim("tox "), t)
            return
    from .installer import workdir, cleanup
    from .fetch import fetch

    spec = parse(a.package)
    work = workdir()
    try:
        data = index.load()
        f = fetch(spec, work, lambda n: index.lookup(n, data))
        versions = []
        if f.kind == "github":
            o, r = f.source.split("/")[:2]
            from .semver import Version

            versions = sorted((Version.try_parse(t) for t in github.ls_remote(o, r).tags()), key=lambda v: (v is None, v))
            versions = [str(v) for v in versions if v is not None]
        res = {
            "name": f.name,
            "version": f.version,
            "from": f.source,
            "ref": f.ref,
            "description": f.description,
            "tox": f.tox,
            "files": f.files,
            "dependencies": f.dependencies,
            "touchdesigner": f.touchdesigner,
            "versions": versions,
            "installed": False,
        }
    finally:
        cleanup(work)
    if JSON:
        return res
    out.say(out.bold(res["name"]), res["version"], out.dim(res["ref"] or ""))
    if res["description"]:
        out.say(res["description"])
    out.say(out.dim("from"), res["from"])
    for t in res["tox"]:
        out.say(out.dim("tox "), t)
    if res["dependencies"]:
        out.say(out.dim("needs"), ", ".join(f"{k}@{v}" for k, v in res["dependencies"].items()))
    if res["touchdesigner"]:
        out.say(out.dim("td   "), res["touchdesigner"])
    if versions:
        out.say(out.dim("versions"), ", ".join(versions[-10:]))


def cmd_where(a):
    root = project.find() if not a.globally else None
    paths = (project.where(root, a.name) if root else None) or store.where(a.name)
    if not paths:
        raise ShelfError(f"{a.name} isn't installed")
    if JSON:
        return {"name": a.name, "tox": paths}
    for p in paths:
        print(p)


def cmd_init(a):
    pkg = True if a.package else (False if a.project else None)
    data, as_package = project.init(os.getcwd(), name=a.name, package=pkg)
    if JSON:
        return {"manifest": data, "package": as_package}
    if as_package:
        out.say(out.green("made shelf.json"), "for", out.bold(data["name"]), out.dim(f"({len(data['tox'])} tox)"))
        out.say(out.dim("tag a release like v0.1.0 and anyone can `shelf install` it"))
    else:
        out.say(out.green("made shelf.json"), out.dim("now `shelf add owner/repo` to pull stuff in"))


def cmd_add(a):
    root = project.require()
    done, warnings = project.add(root, a.packages, log=log)
    show_warnings(warnings)
    if JSON:
        return {"installed": done, "project": str(root), "warnings": warnings}
    _installed_lines(done)
    out.say(out.dim(f"in {project.MODULES}/, point a COMP's external tox at it or use `shelf where <name>`"))


def cmd_drop(a):
    root = project.require()
    gone = project.drop(root, a.names)
    if JSON:
        return {"removed": gone}
    for n in gone:
        out.say(out.red("-"), n)


def cmd_sync(a):
    root = project.require()
    done, gone, warnings = project.sync(root, update=a.update, frozen=a.frozen, log=log)
    show_warnings(warnings)
    if JSON:
        return {"installed": done, "removed": gone, "warnings": warnings}
    _installed_lines(done)
    for n in gone:
        out.say(out.red("-"), n)
    if not done and not gone:
        out.say("all synced")


def cmd_check(a):
    root = Path(a.dir or os.getcwd())
    m = manifest.load(root)
    bad = m.problems(strict=True)
    files = m.files()
    if JSON:
        return {"ok": not bad, "problems": bad, "files": files, "name": m.name, "version": m.version}
    if bad:
        for b in bad:
            out.fail(b)
        return 1
    out.say(out.green("looks good"), out.bold(m.name), m.version)
    for f in files:
        out.say(out.dim("  " + f))


def cmd_palette(a):
    cfg = load_config()
    act = a.action or "status"
    if act == "set":
        if not a.value:
            raise ShelfError("give it a folder, like `shelf palette set \"D:\\td\\palette\"`")
        cfg["palette"] = str(Path(a.value).expanduser())
        save_config(cfg)
        act = "link"
    if act == "off":
        cfg["palette_link"] = False
        save_config(cfg)
        store.unlink_all()
        if JSON:
            return {"palette_link": False}
        out.say("palette linking off, removed shelf from the palette")
        return
    if act == "on":
        cfg["palette_link"] = True
        save_config(cfg)
        act = "link"
    if act == "link":
        res = store.relink()
        if JSON:
            return {"linked": res, "root": str(palette.root())}
        if not palette.enabled():
            out.warn(f"no palette folder at {palette.root()}")
            out.say(out.dim("open td once, or point it somewhere with `shelf palette set <folder>`"))
            return
        out.say(f"linked {len(res)} package(s) into", palette.root() / palette.FOLDER)
        return
    if act == "path":
        print(palette.root())
        return
    r = palette.root()
    res = {"root": str(r), "exists": r.is_dir(), "linking": bool(cfg.get("palette_link", True)), "linked": palette.linked()}
    if JSON:
        return res
    out.say(out.dim("palette "), r, "" if r.is_dir() else out.yellow("(doesn't exist)"))
    out.say(out.dim("linking "), "on" if res["linking"] else "off")
    out.say(out.dim("in there"), ", ".join(res["linked"]) or "nothing")


def cmd_config(a):
    cfg = load_config()
    if a.action in (None, "list"):
        shown = {k: ("•••" + v[-4:] if k == "token" and v else v) for k, v in cfg.items()}
        if JSON:
            return shown
        for k, v in shown.items():
            out.say(out.dim(k.ljust(13)), v)
        return
    if a.key not in DEFAULTS:
        raise ShelfError(f"no setting called {a.key}", "settings: " + ", ".join(DEFAULTS))
    if a.action == "get":
        v = cfg.get(a.key)
        if JSON:
            return {a.key: v}
        print(v)
        return
    if a.action == "unset":
        cfg[a.key] = DEFAULTS[a.key]
    elif a.action == "set":
        v = a.value
        if isinstance(DEFAULTS[a.key], bool):
            v = str(v).lower() in ("1", "true", "yes", "on")
        cfg[a.key] = v
    save_config(cfg)
    if JSON:
        return {a.key: cfg[a.key]}
    out.say("ok")


def cmd_doctor(a):
    from . import td

    cfg = load_config()
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": ok, "detail": str(detail)})

    check("shelf home", True, home())
    check("touchdesigner", bool(td.installs()), ", ".join(td.installs()) or "didn't find an install (that's ok on a custom path)")
    pr = palette.root(cfg)
    check("palette folder", pr.is_dir(), pr)
    check("git", bool(shutil.which("git")), shutil.which("git") or "not installed, only needed as a fallback")
    try:
        github.ls_remote("intrapersonal", "tox-shelf")
        check("github", True, "reachable")
    except ShelfError as e:
        check("github", False, e)
    check("token", True, "set" if (cfg.get("token") or os.environ.get("GITHUB_TOKEN")) else "not set (only needed if search hits the rate limit)")
    check("td build", True, cfg.get("td_build") or "unknown, the shelf COMP fills this in")
    if JSON:
        return {"checks": checks}
    for c in checks:
        mark = out.green("ok") if c["ok"] else out.yellow("--")
        out.say(mark, c["check"].ljust(15), out.dim(c["detail"]))


def cmd_td(a):
    from .tdside import bootstrap

    path = bootstrap.write(home() / "td" / "shelf_bootstrap.py", exe=sys.executable if getattr(sys, "frozen", False) else "")
    line = f"exec(open(r'{path}').read())"
    copied = False
    if not a.no_copy:
        try:
            if os.name == "nt":
                subprocess.run(["clip"], input=line.encode("utf-16-le"), check=True, creationflags=0x08000000)
                copied = True
            elif shutil.which("pbcopy"):
                subprocess.run(["pbcopy"], input=line.encode(), check=True)
                copied = True
        except (OSError, subprocess.CalledProcessError):
            copied = False
    if JSON:
        return {"bootstrap": str(path), "line": line, "copied": copied}
    out.say("open td, hit alt+t for the textport and paste this" + (" (it's already copied)" if copied else "") + ":")
    out.say("")
    out.say("  " + out.cyan(line))
    out.say("")
    out.say(out.dim("it drops a shelf COMP into whatever network you're looking at and saves shelf.tox into your palette"))


def build_parser():
    p = argparse.ArgumentParser(prog="shelf", description="package manager for touchdesigner components")
    p.add_argument("--version", action="version", version=f"tox-shelf {__version__}")
    p.add_argument("--json", action="store_true", help="machine readable output")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    s = sub.add_parser("install", aliases=["i"], help="install packages globally (or into the project with -p)")
    s.add_argument("packages", nargs="+", metavar="package")
    s.add_argument("-p", "--project", action="store_true", help="same as shelf add")
    s.add_argument("--no-palette", action="store_true", help="don't copy into td's palette")
    s.add_argument("--td", default=None, help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("remove", aliases=["rm", "uninstall"], help="remove packages")
    s.add_argument("names", nargs="+", metavar="name")
    s.add_argument("-g", "--global", dest="globally", action="store_true", help="ignore the project you're in")
    s.add_argument("-f", "--force", action="store_true", help="remove even if something needs it")
    s.set_defaults(fn=cmd_remove)

    s = sub.add_parser("list", aliases=["ls"], help="what's installed")
    s.add_argument("-g", "--global", dest="globally", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("update", aliases=["up", "upgrade"], help="update packages to the newest matching version")
    s.add_argument("names", nargs="*", metavar="name")
    s.add_argument("-g", "--global", dest="globally", action="store_true")
    s.add_argument("--td", default=None, help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("search", aliases=["s", "find"], help="find components")
    s.add_argument("query", nargs="*")
    s.add_argument("--index-only", action="store_true", help="only the shelf index, skip github")
    s.add_argument("--refresh", action="store_true", help="redownload the index")
    s.add_argument("-n", "--limit", type=int, default=15)
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("info", aliases=["show"], help="look at a package before installing")
    s.add_argument("package")
    s.add_argument("--remote", action="store_true", help="always look it up online")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("where", help="print the path to an installed tox")
    s.add_argument("name")
    s.add_argument("-g", "--global", dest="globally", action="store_true")
    s.set_defaults(fn=cmd_where)

    s = sub.add_parser("init", help="make a shelf.json here")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--package", action="store_true", help="this folder is a component to share")
    g.add_argument("--project", action="store_true", help="this folder is a td project that uses packages")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("add", help="add packages to this project")
    s.add_argument("packages", nargs="+", metavar="package")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("drop", help="take packages out of this project")
    s.add_argument("names", nargs="+", metavar="name")
    s.set_defaults(fn=cmd_drop)

    s = sub.add_parser("sync", help="install exactly what shelf.lock says")
    s.add_argument("--update", action="store_true", help="re-resolve everything and rewrite the lock")
    s.add_argument("--frozen", action="store_true", help="fail if the lock doesn't cover shelf.json")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("check", help="check a package's shelf.json before you publish")
    s.add_argument("dir", nargs="?")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("palette", help="td palette linking")
    s.add_argument("action", nargs="?", choices=["status", "link", "path", "set", "on", "off"])
    s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_palette)

    s = sub.add_parser("config", help="settings")
    s.add_argument("action", nargs="?", choices=["list", "get", "set", "unset"])
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("doctor", help="check your setup")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("td", help="set up the shelf COMP inside touchdesigner")
    s.add_argument("--no-copy", action="store_true")
    s.set_defaults(fn=cmd_td)
    return p


def main(argv=None):
    global JSON
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--json" in argv:
        argv.remove("--json")
        JSON = True
    a = parser.parse_args(argv)
    if not getattr(a, "fn", None):
        parser.print_help()
        return 0
    if a.cmd == "config" and a.action in ("get", "set", "unset") and not a.key:
        parser.error("config needs a key")
    if a.cmd == "config" and a.action == "set" and a.value is None:
        parser.error("config set needs a value")
    try:
        res = a.fn(a)
    except ShelfError as e:
        if JSON:
            print(json.dumps({"ok": False, "error": str(e), "hint": e.hint}))
        else:
            out.fail(e, e.hint)
        return 1
    except KeyboardInterrupt:
        return 130
    if JSON:
        if isinstance(res, dict):
            print(json.dumps(dict({"ok": True}, **res), default=str))
        else:
            print(json.dumps({"ok": res != 1}))
    return res if isinstance(res, int) else 0
