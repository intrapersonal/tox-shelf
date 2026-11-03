import os
import shutil
from pathlib import Path

from . import installer, manifest
from .errors import ShelfError
from .fetch import fetch_locked
from .paths import load_config, read_json, write_json
from .semver import Version, caret
from .spec import clean_name, parse

LOCK = "shelf.lock"
MODULES = "shelf_modules"


def find(start=None):
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / manifest.FILE).is_file():
            return d
    return None


def require(start=None):
    root = find(start)
    if root is None:
        raise ShelfError("not in a shelf project", "run `shelf init` in your touchdesigner project folder first")
    return root


def init(root, name=None, package=None):
    root = Path(root)
    f = root / manifest.FILE
    if f.exists():
        raise ShelfError(f"{f} already exists")
    tox = manifest.pick_tox(manifest.find_tox(root))
    as_package = bool(tox) if package is None else package
    data = {"name": clean_name(name or root.name)}
    if as_package:
        if not tox:
            raise ShelfError("no .tox files in this folder to make a package from")
        data.update({"version": "0.1.0", "description": "", "tox": tox})
    data["dependencies"] = {}
    manifest.save(root, data)
    return data, as_package


def lock_path(root):
    return Path(root) / LOCK


def read_lock(root):
    data = read_json(lock_path(root), {}) or {}
    data.setdefault("lockVersion", 1)
    data.setdefault("packages", {})
    return data


def write_lock(root, data):
    data["packages"] = dict(sorted(data["packages"].items()))
    write_json(lock_path(root), data)


def modules(root):
    return Path(root) / MODULES


def _range_for(f, spec):
    if spec.ref:
        return f"#{spec.ref}"
    if not spec.range.is_any:
        return str(spec.range)
    v = Version.try_parse(f.version)
    if f.kind == "github" and f.ref and v is not None and f.ref.lstrip("v") == str(v):
        return caret(v)
    return "*"


def _apply(root, plan, lock, roots):
    mods = modules(root)
    out = []
    for f in plan.order:
        w = plan.wanted[f.name]
        installer.place(f, mods / f.name)
        prev = lock["packages"].get(f.name, {})
        entry = f.lock_entry()
        root_key = roots.get(f.name) or prev.get("root")
        if root_key:
            entry["root"] = root_key
        by = set(prev.get("by") or [])
        if w["parent"]:
            by.add(w["parent"])
        if by:
            entry["by"] = sorted(by)
        lock["packages"][f.name] = entry
        out.append({"name": f.name, "version": f.version, "from": f.source, "ref": f.ref, "sha": f.sha, "path": str(mods / f.name), "dependency_of": w["parent"]})
    return out


def _prune(root, lock, keep_roots):
    pk = lock["packages"]
    keep = set()
    stack = [n for n, e in pk.items() if e.get("root") in keep_roots]
    while stack:
        n = stack.pop()
        if n in keep or n not in pk:
            continue
        keep.add(n)
        for k, e in pk.items():
            if n in (e.get("by") or []):
                stack.append(k)
    gone = [n for n in list(pk) if n not in keep]
    for n in gone:
        pk.pop(n)
    for e in pk.values():
        if e.get("by"):
            e["by"] = [b for b in e["by"] if b in pk]
            if not e["by"]:
                e.pop("by")
        if e.get("root") and e["root"] not in keep_roots:
            e.pop("root")
    mods = modules(root)
    if mods.is_dir():
        for d in mods.iterdir():
            if d.is_dir() and d.name not in pk:
                shutil.rmtree(d, ignore_errors=True)
                gone.append(d.name)
    return sorted(set(gone))


def add(root, raw_specs, log=None):
    root = Path(root)
    m = manifest.load(root)
    specs = [parse(s, cwd=str(root)) for s in raw_specs]
    work = installer.workdir()
    try:
        plan = installer.resolve(specs, log=log, td_build=load_config().get("td_build", ""), work=work)
        lock = read_lock(root)
        deps = m.dependencies
        roots = {}
        for spec in specs:
            f = next((x for x in plan.order if plan.wanted[x.name]["requested"] == str(spec) and plan.wanted[x.name]["parent"] is None), None)
            if f is None:
                continue
            key = spec.source if spec.kind != "local" else os.path.relpath(spec.path, root).replace("\\", "/")
            if spec.kind == "local" and not key.startswith("."):
                key = "./" + key
            for k in list(deps):
                if lock["packages"].get(f.name, {}).get("root") == k and k != key:
                    deps.pop(k)
            deps[key] = _range_for(f, spec)
            roots[f.name] = key
        out = _apply(root, plan, lock, roots)
        m.data["dependencies"] = deps
        manifest.save(root, m.data)
        _prune(root, lock, set(deps))
        write_lock(root, lock)
        return out, plan.warnings
    finally:
        installer.cleanup(work)


def drop(root, names):
    root = Path(root)
    m = manifest.load(root)
    lock = read_lock(root)
    deps = m.dependencies
    hit = []
    for n in names:
        key = None
        if n in deps:
            key = n
        else:
            key = lock["packages"].get(n, {}).get("root")
        if not key or key not in deps:
            raise ShelfError(f"{n} isn't a dependency of this project")
        deps.pop(key)
        hit.append(n)
    m.data["dependencies"] = deps
    manifest.save(root, m.data)
    gone = _prune(root, lock, set(deps))
    write_lock(root, lock)
    return gone


def sync(root, update=False, frozen=False, log=None):
    root = Path(root)
    m = manifest.load(root)
    deps = m.dependencies
    lock = read_lock(root)
    if update:
        lock = {"lockVersion": 1, "packages": {}}
    locked_roots = {e.get("root"): n for n, e in lock["packages"].items() if e.get("root")}
    missing = [k for k in deps if k not in locked_roots]
    if frozen and missing:
        raise ShelfError(f"shelf.lock is out of date ({', '.join(missing)})", "run `shelf sync` without --frozen")
    done = []
    warnings = []
    mods = modules(root)
    gone = _prune(root, lock, set(deps))
    work = installer.workdir()
    try:
        for name, entry in list(lock["packages"].items()):
            meta = installer.read_meta(mods / name) or {}
            if meta.get("integrity") == entry.get("integrity") and all((mods / name / f).is_file() for f in meta.get("files", [])):
                continue
            if log:
                log(f"fetching {name}")
            f = fetch_locked(entry, work)
            installer.place(f, mods / name)
            done.append({"name": name, "version": f.version, "from": f.source, "ref": f.ref, "sha": f.sha, "path": str(mods / name)})
        if missing:
            specs = []
            for k in missing:
                specs.append(installer.dep_spec(k, deps[k]) if not k.startswith(".") else parse(k, cwd=str(root)))
            plan = installer.resolve(specs, log=log, td_build=load_config().get("td_build", ""), work=work)
            warnings += plan.warnings
            roots = {}
            for spec, k in zip(specs, missing):
                for f in plan.order:
                    w = plan.wanted[f.name]
                    if w["parent"] is None and w["requested"] == str(spec):
                        roots[f.name] = k
            done += _apply(root, plan, lock, roots)
        gone += _prune(root, lock, set(deps))
        write_lock(root, lock)
        return done, gone, warnings
    finally:
        installer.cleanup(work)


def listing(root):
    lock = read_lock(root)
    mods = modules(root)
    out = []
    for name, e in lock["packages"].items():
        meta = installer.read_meta(mods / name) or {}
        out.append(
            {
                "name": name,
                "version": e.get("version"),
                "from": e.get("source"),
                "ref": e.get("ref"),
                "sha": e.get("sha"),
                "dependency_of": ", ".join(e.get("by") or []) or None,
                "installed": bool(meta),
                "tox": [str(mods / name / t) for t in meta.get("tox", [])],
            }
        )
    return out


def where(root, name):
    meta = installer.read_meta(modules(root) / name)
    if not meta:
        return None
    return [str(modules(root) / name / t) for t in meta.get("tox", [])]
