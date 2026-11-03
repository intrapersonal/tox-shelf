import shutil
from pathlib import Path

from .paths import documents, load_config

FOLDER = "shelf"


def root(cfg=None):
    cfg = cfg or load_config()
    if cfg.get("palette"):
        return Path(cfg["palette"])
    return documents() / "Derivative" / "Palette"


def enabled(cfg=None):
    cfg = cfg or load_config()
    if not cfg.get("palette_link", True):
        return False
    r = root(cfg)
    return bool(cfg.get("palette")) or r.is_dir()


def target(name, cfg=None):
    return root(cfg) / FOLDER / name


def link(name, pkgdir, tox, cfg=None):
    cfg = cfg or load_config()
    if not enabled(cfg):
        return []
    dest = target(name, cfg)
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    made = []
    used = set()
    for rel in tox:
        src = Path(pkgdir) / rel
        base = src.name
        if base.lower() in used:
            base = rel.replace("/", "_")
        used.add(base.lower())
        shutil.copy2(src, dest / base)
        made.append(str(dest / base))
    return made


def unlink(name, cfg=None):
    dest = target(name, cfg)
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
        return True
    return False


def linked(cfg=None):
    base = root(cfg) / FOLDER
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
