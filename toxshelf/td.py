import os
import sys
from pathlib import Path


def installs():
    found = []
    if os.name == "nt":
        roots = {os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files")}
        for r in roots:
            base = Path(r) / "Derivative"
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                exe = d / "bin" / "TouchDesigner.exe"
                if exe.is_file():
                    found.append(str(exe))
    elif sys.platform == "darwin":
        apps = Path("/Applications")
        if apps.is_dir():
            for d in sorted(apps.glob("TouchDesigner*.app")):
                found.append(str(d))
    return sorted(set(found))
