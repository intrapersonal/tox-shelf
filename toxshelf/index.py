import json
import time
from pathlib import Path

from . import net
from .errors import ShelfError
from .paths import cache_dir, load_config, write_json

BUNDLED = Path(__file__).with_name("index.json")
MAX_AGE = 60 * 60 * 12


def _read(path):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("packages"), dict):
            return data
    except (OSError, ValueError):
        pass
    return None


def load(refresh=False, offline=False):
    cached = cache_dir() / "index.json"
    fresh = cached.is_file() and time.time() - cached.stat().st_mtime < MAX_AGE
    if not offline and (refresh or not fresh):
        try:
            data = net.get_json(load_config().get("index_url"), timeout=15, tries=1, what="the package index")
            if isinstance(data, dict) and isinstance(data.get("packages"), dict):
                write_json(cached, data)
                return data
        except ShelfError:
            pass
    return _read(cached) or _read(BUNDLED) or {"packages": {}}


def lookup(name, data=None):
    data = data or load()
    entry = data.get("packages", {}).get(name.lower())
    if not entry:
        return None
    return entry.get("source")


def search(query, data=None):
    data = data or load()
    q = (query or "").lower().split()
    out = []
    for name, e in sorted(data.get("packages", {}).items()):
        hay = " ".join([name, e.get("source", ""), e.get("description", ""), " ".join(e.get("tags", []))]).lower()
        if all(w in hay for w in q):
            out.append(dict(e, name=name))
    return out
