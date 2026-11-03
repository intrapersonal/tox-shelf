import shutil
from pathlib import Path

from . import installer, palette
from .errors import ShelfError
from .paths import installed_file, load_config, packages_dir, read_json, write_json
from .spec import parse


def state():
    data = read_json(installed_file(), {}) or {}
    data.setdefault("packages", {})
    return data


def save(data):
    write_json(installed_file(), data)


def pkg_dir(name):
    return packages_dir() / name


def installed():
    return state()["packages"]


def get(name):
    return installed().get(name)


def install(raw_specs, log=None, link=True, td_build=None):
    cfg = load_config()
    td_build = td_build or cfg.get("td_build", "")
    specs = [parse(s) for s in raw_specs]
    work = installer.workdir()
    try:
        plan = installer.resolve(specs, log=log, td_build=td_build, work=work)
        data = state()
        done = []
        for f in plan.order:
            meta = installer.place(f, pkg_dir(f.name))
            w = plan.wanted[f.name]
            prev = data["packages"].get(f.name, {})
            entry = {k: v for k, v in meta.items() if k != "installed"}
            entry["installed"] = meta["installed"]
            if w["parent"] is None:
                entry["requested"] = w["requested"]
                entry["dependents"] = prev.get("dependents", [])
            else:
                entry["requested"] = prev.get("requested")
                deps = set(prev.get("dependents", []))
                deps.add(w["parent"])
                entry["dependents"] = sorted(deps)
            entry["palette"] = palette.link(f.name, pkg_dir(f.name), f.tox, cfg) if link else []
            data["packages"][f.name] = entry
            done.append({"name": f.name, "version": f.version, "from": f.source, "ref": f.ref, "sha": f.sha, "previous": prev.get("version"), "previous_sha": prev.get("sha"), "palette": entry["palette"], "path": str(pkg_dir(f.name)), "dependency_of": w["parent"]})
        save(data)
        return done, plan.warnings
    finally:
        installer.cleanup(work)


def remove(names, force=False):
    data = state()
    pk = data["packages"]
    removed = []
    for name in names:
        if name not in pk:
            raise ShelfError(f"{name} isn't installed")
        users = [n for n in pk[name].get("dependents", []) if n in pk and n not in names]
        if users and not force:
            raise ShelfError(f"{name} is needed by {', '.join(users)}", "remove those first or use --force")
    todo = list(names)
    while todo:
        for name in todo:
            pk.pop(name, None)
            shutil.rmtree(pkg_dir(name), ignore_errors=True)
            palette.unlink(name)
            removed.append(name)
            for other in pk.values():
                if name in other.get("dependents", []):
                    other["dependents"] = [d for d in other["dependents"] if d != name]
        todo = [n for n, e in pk.items() if not e.get("requested") and not e.get("dependents")]
    save(data)
    return removed


def update(names=None, log=None, td_build=None):
    pk = installed()
    targets = names or [n for n, e in pk.items() if e.get("requested")]
    specs = []
    for n in targets:
        e = pk.get(n)
        if not e:
            raise ShelfError(f"{n} isn't installed")
        req = e.get("requested") or e.get("source")
        specs.append(req)
    if not specs:
        return [], []
    return install(specs, log=log, td_build=td_build)


def where(name):
    e = get(name)
    if not e:
        return None
    base = pkg_dir(name)
    return [str(Path(base) / t) for t in e.get("tox", [])]


def relink():
    cfg = load_config()
    data = state()
    out = {}
    for name, e in data["packages"].items():
        e["palette"] = palette.link(name, pkg_dir(name), e.get("tox", []), cfg)
        out[name] = e["palette"]
    save(data)
    return out


def unlink_all():
    data = state()
    for name, e in data["packages"].items():
        palette.unlink(name)
        e["palette"] = []
    save(data)
