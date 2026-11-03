import json
import os
import sys
from pathlib import Path


def home():
    env = os.environ.get("TOX_SHELF_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "tox-shelf"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "tox-shelf"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "tox-shelf"


def packages_dir():
    return home() / "packages"


def cache_dir():
    return home() / "cache"


def config_file():
    return home() / "config.json"


def installed_file():
    return home() / "installed.json"


def documents():
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path:
                    return Path(path)
        except Exception:
            pass
    return Path.home() / "Documents"


DEFAULTS = {
    "palette": "",
    "palette_link": True,
    "token": "",
    "index_url": "https://raw.githubusercontent.com/intrapersonal/tox-shelf/main/toxshelf/index.json",
    "td_build": "",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_file().read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in cfg.items() if k not in DEFAULTS or v != DEFAULTS[k]}
    write_json(path, clean)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except FileNotFoundError:
        return default
    except ValueError:
        return default
