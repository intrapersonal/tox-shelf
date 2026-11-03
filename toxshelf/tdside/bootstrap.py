from pathlib import Path

from .. import __version__

HERE = Path(__file__).parent

BUILDER = '''
import os


def _shelf_par(page, kind, name, label, **kw):
    fn = getattr(page, "append" + kind)
    fn(name, label=label)
    p = getattr(_shelf_comp.par, name)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _shelf_build():
    global _shelf_comp
    target = None
    pane = None
    try:
        pane = ui.panes.current
        if pane is not None and pane.type == PaneType.NETWORKEDITOR:
            target = pane.owner
    except Exception:
        pane = None
    if target is None:
        target = op("/project1") or op("/")
    old = target.op("shelf")
    if old is not None and old.isCOMP:
        x, y = old.nodeX, old.nodeY
        old.destroy()
    else:
        x = int(getattr(pane, "x", 0)) if pane is not None else 0
        y = int(getattr(pane, "y", 0)) if pane is not None else 0
    c = target.create(baseCOMP, "shelf")
    _shelf_comp = c
    c.nodeX, c.nodeY = x, y
    c.color = (0.42, 0.47, 0.72)
    c.comment = "tox-shelf " + VERSION

    ext = c.create(textDAT, "ShelfExt")
    ext.text = EXT
    ext.nodeX, ext.nodeY = 0, 0
    for i, (name, head) in enumerate((("packages", ["name", "version", "from", "tox"]), ("results", ["name", "repo", "description", "stars", "indexed"]))):
        t = c.create(tableDAT, name)
        t.clear()
        t.appendRow(head)
        t.nodeX, t.nodeY = 200, -150 * i

    page = c.appendCustomPage("Shelf")
    _shelf_par(page, "Str", "Package", "Package", help="owner/repo, a name from the index, a github url or a .tox url")
    _shelf_par(page, "Pulse", "Install", "Install")
    scope = _shelf_par(page, "Menu", "Scope", "Install To")
    scope.menuNames = ["global", "project"]
    scope.menuLabels = ["Everywhere (palette)", "This Project (shelf_modules)"]
    _shelf_par(page, "Toggle", "Placeafter", "Place After Install", default=True, val=True)
    _shelf_par(page, "Menu", "Installed", "Installed")
    _shelf_par(page, "Pulse", "Place", "Place In Network")
    _shelf_par(page, "Pulse", "Remove", "Remove")
    _shelf_par(page, "Pulse", "Update", "Update All")
    _shelf_par(page, "Pulse", "Refresh", "Refresh")
    _shelf_par(page, "Str", "Search", "Search")
    _shelf_par(page, "Pulse", "Searchgo", "Go")
    _shelf_par(page, "Menu", "Results", "Results")
    _shelf_par(page, "Str", "Status", "Status", readOnly=True, val="loading...")

    setup = c.appendCustomPage("Setup")
    _shelf_par(setup, "File", "Shelfexe", "Shelf Exe", val=EXE, default=EXE)
    _shelf_par(setup, "Pulse", "Openfolder", "Open Packages Folder")
    _shelf_par(setup, "Str", "About", "About", readOnly=True, val="tox-shelf " + VERSION + " - made by mason arcieri", default="tox-shelf " + VERSION + " - made by mason arcieri")

    expr = "op('./ShelfExt').module.ShelfExt(me)"
    if getattr(c.par, "ext0object", None) is not None:
        c.par.ext0object = expr
        if getattr(c.par, "ext0promote", None) is not None:
            c.par.ext0promote = True
    else:
        c.par.extension1 = expr
        c.par.promoteextension1 = True
    c.initializeExtensions()

    pe = c.create(parameterexecuteDAT, "parexec")
    pe.text = PAREXEC
    pe.nodeX, pe.nodeY = 0, -150
    pe.par.op = ".."
    for name, val in (("custom", True), ("builtin", False), ("valuechange", True), ("onpulse", True)):
        if hasattr(pe.par, name):
            setattr(pe.par, name, val)

    saved = []
    folder = getattr(app, "userPaletteFolder", "") or os.path.join(os.path.expanduser("~"), "Documents", "Derivative", "Palette")
    for path in (os.path.join(folder, "shelf", "shelf.tox"), os.path.join(SHELF_HOME, "td", "shelf.tox")):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            c.save(path)
            saved.append(path)
        except Exception as e:
            print("shelf: couldn't save", path, e)
    c.current = True
    print("shelf: ready at " + c.path)
    for s in saved:
        print("shelf: saved " + s)
    return c


_shelf_comp = None
_shelf_build()
'''


def source(exe="", shelf_home=""):
    ext = (HERE / "ext.py").read_text("utf-8")
    parexec = (HERE / "parexec.py").read_text("utf-8")
    head = "\n".join(
        [
            f"VERSION = {__version__!r}",
            f"EXE = {exe!r}",
            f"SHELF_HOME = {str(shelf_home)!r}",
            f"EXT = {ext!r}",
            f"PAREXEC = {parexec!r}",
        ]
    )
    return head + "\n" + BUILDER


def write(path, exe=""):
    from ..paths import home

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source(exe, home()), "utf-8")
    return path
