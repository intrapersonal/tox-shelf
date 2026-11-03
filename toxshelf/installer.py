import os
import shutil
import tempfile
import time
from pathlib import Path

from . import index
from .errors import ShelfError
from .fetch import fetch
from .manifest import td_ok
from .paths import cache_dir, write_json
from .semver import Range, Version
from .spec import parse

META = ".shelf.json"


class Plan:
    def __init__(self):
        self.order = []
        self.by_name = {}
        self.wanted = {}
        self.warnings = []

    def add(self, f, requested, parent):
        self.order.append(f)
        self.by_name[f.name] = f
        self.wanted[f.name] = {"requested": requested, "parent": parent}


def dep_spec(key, value):
    spec = parse(key)
    value = (value or "*").strip()
    if value.startswith("#"):
        spec.ref = value[1:]
    else:
        try:
            spec.range = Range(value)
        except ValueError:
            spec.ref = value
    return spec


def workdir():
    d = cache_dir() / "work"
    d.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="w", dir=d))


def resolve(specs, log=None, td_build="", work=None):
    work = work or workdir()
    data = None

    def lookup(name):
        nonlocal data
        if data is None:
            data = index.load()
        return index.lookup(name, data)

    plan = Plan()
    queue = [(s, None) for s in specs]
    while queue:
        spec, parent = queue.pop(0)
        if log:
            log(f"resolving {spec}")
        f = fetch(spec, work, lookup)
        have = plan.by_name.get(f.name)
        if have is not None:
            if parent and not spec.ref and not spec.range.is_any:
                v = Version.try_parse(have.version)
                if v is not None and not spec.range.matches(v, allow_pre=True):
                    raise ShelfError(
                        f"{parent} wants {f.name}@{spec.range} but {have.version} is already picked",
                    )
            continue
        plan.add(f, str(spec), parent)
        if f.touchdesigner and td_build and not td_ok(f.touchdesigner, td_build):
            plan.warnings.append(f"{f.name} wants touchdesigner {f.touchdesigner}, you have {td_build}")
        for key, value in f.dependencies.items():
            queue.append((dep_spec(key, value), f.name))
    return plan


def place(f, dest):
    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for rel in f.files:
        src = Path(f.root) / rel
        out = tmp / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    meta = dict(f.lock_entry(), name=f.name, files=f.files, tox=f.tox, installed=int(time.time()))
    if f.description:
        meta["description"] = f.description
    if f.touchdesigner:
        meta["touchdesigner"] = f.touchdesigner
    write_json(tmp / META, meta)
    if dest.exists():
        old = dest.with_name(dest.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        os.replace(dest, old)
        os.replace(tmp, dest)
        shutil.rmtree(old, ignore_errors=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, dest)
    return meta


def read_meta(pkgdir):
    from .paths import read_json

    return read_json(Path(pkgdir) / META)


def cleanup(work):
    shutil.rmtree(work, ignore_errors=True)
