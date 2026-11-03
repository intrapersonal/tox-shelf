import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def shelf_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    pal = tmp_path / "palette"
    pal.mkdir()
    monkeypatch.setenv("TOX_SHELF_HOME", str(home))
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"palette": str(pal), "index_url": "http://127.0.0.1:9/none.json"}))
    cache = home / "cache"
    cache.mkdir()
    (cache / "index.json").write_text(json.dumps({"packages": {}}))
    os.utime(cache / "index.json")
    return home, pal


def make_pkg(root, name, version="1.0.0", tox=("thing.tox",), deps=None, extra=None, manifest=True):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for t in tox:
        p = root / t
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"TOX:" + name.encode() + b":" + t.encode())
    for rel, data in (extra or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    if manifest:
        m = {"name": name, "version": version, "tox": list(tox)}
        if deps:
            m["dependencies"] = deps
        (root / "shelf.json").write_text(json.dumps(m))
    return root
