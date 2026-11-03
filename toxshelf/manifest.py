import fnmatch
import json
import os
from pathlib import Path

from .errors import ShelfError
from .semver import Range, Version
from .spec import clean_name, valid_name

FILE = "shelf.json"
SKIP_DIRS = {"Backup", "backup", "node_modules", "shelf_modules", "__pycache__", "venv", ".venv"}


def find_tox(root):
    root = Path(root)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for f in sorted(filenames):
            if f.lower().endswith(".tox"):
                out.append(Path(dirpath, f).relative_to(root).as_posix())
    return out


def glob(root, pattern):
    root = Path(root)
    hits = []
    pattern = pattern.replace("\\", "/").lstrip("./")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
        for f in filenames:
            rel = Path(dirpath, f).relative_to(root).as_posix()
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, pattern.rstrip("/") + "/*"):
                hits.append(rel)
    return sorted(hits)


class Manifest:
    def __init__(self, data, root=None):
        self.data = data
        self.root = Path(root) if root else None

    @property
    def name(self):
        return self.data.get("name", "")

    @property
    def version(self):
        return self.data.get("version", "")

    @property
    def description(self):
        return self.data.get("description", "")

    @property
    def tox(self):
        t = self.data.get("tox", [])
        return [t] if isinstance(t, str) else list(t)

    @property
    def include(self):
        t = self.data.get("include", [])
        return [t] if isinstance(t, str) else list(t)

    @property
    def dependencies(self):
        return dict(self.data.get("dependencies", {}))

    @property
    def touchdesigner(self):
        return self.data.get("touchdesigner", "")

    @property
    def is_package(self):
        return bool(self.tox)

    def files(self):
        if self.root is None:
            return []
        out = []
        for t in self.tox:
            out.append(t.replace("\\", "/").lstrip("./"))
        for pat in self.include:
            out.extend(glob(self.root, pat))
        seen = set()
        uniq = []
        for f in out:
            if f not in seen:
                seen.add(f)
                uniq.append(f)
        return uniq

    def problems(self, strict=True):
        p = []
        d = self.data
        if not isinstance(d, dict):
            return ["shelf.json has to be an object"]
        if not valid_name(self.name):
            p.append(f"name {self.name!r} should be lowercase letters, numbers, - _ or .")
        if strict or self.is_package:
            if self.version and Version.try_parse(self.version) is None:
                p.append(f"version {self.version!r} isn't semver (like 1.0.0)")
            if not self.tox:
                p.append("no tox listed, add a \"tox\": [\"thing.tox\"]")
        if self.root is not None:
            for t in self.tox:
                rel = t.replace("\\", "/").lstrip("./")
                if not rel.lower().endswith(".tox"):
                    p.append(f"{t} isn't a .tox")
                elif not (self.root / rel).is_file():
                    p.append(f"{t} doesn't exist")
                elif ".." in Path(rel).parts:
                    p.append(f"{t} points outside the package")
            for pat in self.include:
                if ".." in Path(pat).parts:
                    p.append(f"include {pat} points outside the package")
        for k, v in self.dependencies.items():
            try:
                Range(v)
            except ValueError:
                if not str(v).startswith("#"):
                    p.append(f"dependency {k} has a bad range {v!r}")
        if self.touchdesigner and parse_td(self.touchdesigner.lstrip(">=")) is None:
            p.append(f"touchdesigner {self.touchdesigner!r} should look like 2023.11760")
        return p


def parse_td(text):
    text = str(text).strip()
    try:
        if "." in text:
            a, b = text.split(".", 1)
            return (int(a), int(b or 0))
        return (int(text), 0)
    except ValueError:
        return None


def td_ok(required, have):
    if not required or not have:
        return True
    r = parse_td(str(required).lstrip(">= "))
    h = parse_td(have)
    if r is None or h is None:
        return True
    return h >= r


def load(root, required=True):
    root = Path(root)
    f = root / FILE
    if not f.is_file():
        if required:
            raise ShelfError(f"no {FILE} in {root}")
        return None
    try:
        data = json.loads(f.read_text("utf-8-sig"))
    except ValueError as e:
        raise ShelfError(f"{f} isn't valid json ({e})")
    if not isinstance(data, dict):
        raise ShelfError(f"{f} has to be a json object")
    return Manifest(data, root)


def synthesize(root, name, version=None):
    tox = find_tox(root)
    if not tox:
        return None
    data = {"name": clean_name(name), "version": str(version or "0.0.0"), "tox": tox}
    return Manifest(data, root)


def save(root, data):
    from .paths import write_json

    write_json(Path(root) / FILE, data)
