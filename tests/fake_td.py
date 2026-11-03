import os
import time
import types
from pathlib import Path


class Par:
    def __init__(self, owner, name, val="", style="Str"):
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "val", val)
        object.__setattr__(self, "style", style)
        object.__setattr__(self, "menuNames", [])
        object.__setattr__(self, "menuLabels", [])
        object.__setattr__(self, "readOnly", False)
        object.__setattr__(self, "default", None)
        object.__setattr__(self, "help", "")

    def eval(self):
        return self.val

    def __setattr__(self, k, v):
        if k == "menuNames" and v and self.style == "Menu" and self.val not in v:
            object.__setattr__(self, "val", v[0])
        object.__setattr__(self, k, v)


class Pars:
    def __init__(self, owner, builtin=()):
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_pars", {})
        for b in builtin:
            self._pars[b] = Par(owner, b)

    def __getattr__(self, k):
        try:
            return self._pars[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        if k not in self._pars:
            raise AttributeError(k)
        old = self._pars[k].val
        object.__setattr__(self._pars[k], "val", v)
        owner = self._owner
        if old != v and owner.td is not None:
            owner.td.par_changed(self._pars[k])

    def add(self, name, style):
        p = Par(self._owner, name, False if style == "Toggle" else "", style)
        self._pars[name] = p
        return p


class Page:
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name

    def __getattr__(self, k):
        if k.startswith("append"):
            style = k[len("append"):]

            def fn(name, label=None):
                return (self.owner.par.add(name, style),)

            return fn
        raise AttributeError(k)


BUILTIN = {
    "baseCOMP": ("ext0object", "ext0promote", "externaltox", "enableexternaltox"),
    "parameterexecuteDAT": ("op", "custom", "builtin", "valuechange", "onpulse"),
    "textDAT": (),
    "tableDAT": (),
}


class Node:
    def __init__(self, td, kind, name, parent):
        self.td = None
        self.kind = kind
        self.name = name
        self._parent = parent
        self.children = {}
        self.par = Pars(self, BUILTIN.get(kind, ()))
        self.td = td
        self.nodeX = 0
        self.nodeY = 0
        self.color = None
        self.comment = ""
        self.text = ""
        self.rows = []
        self.ext = types.SimpleNamespace()
        self.current = False
        self.pages = []
        self._module = None

    @property
    def isCOMP(self):
        return self.kind.endswith("COMP")

    @property
    def path(self):
        if self._parent is None:
            return "/" + self.name if self.name else "/"
        base = self._parent.path
        return (base.rstrip("/") + "/" + self.name)

    def parent(self):
        return self._parent

    def create(self, kind, name):
        kind = kind if isinstance(kind, str) else kind.__name__
        n = Node(self.td, kind, name, self)
        self.children[name] = n
        return n

    def op(self, path):
        if path in ("..",):
            return self._parent
        path = path[2:] if path.startswith("./") else path
        node = self
        for part in path.split("/"):
            if part == "..":
                node = node._parent
            elif part:
                node = node.children.get(part)
            if node is None:
                return None
        return node

    def destroy(self):
        self._parent.children.pop(self.name, None)

    def appendCustomPage(self, name):
        p = Page(self, name)
        self.pages.append(p)
        return p

    def clear(self):
        self.rows = []

    def appendRow(self, row):
        self.rows.append([str(c) for c in row])

    @property
    def module(self):
        if self._module is None:
            m = types.ModuleType(self.name)
            m.__dict__.update(self.td.globals_for(self))
            exec(compile(self.text, self.name, "exec"), m.__dict__)
            self._module = m
        return self._module

    def initializeExtensions(self):
        expr = self.par.ext0object.val
        g = dict(self.td.globals_for(self))
        g["me"] = self
        inst = eval(expr, g)
        setattr(self.ext, type(inst).__name__, inst)

    def save(self, path):
        Path(path).write_bytes(b"fake tox")
        self.td.saved.append(path)

    def loadTox(self, path):
        name = Path(path).stem
        n = self.create("baseCOMP", name)
        n.loaded_from = path
        return n


class Pane:
    def __init__(self, owner):
        self.owner = owner
        self.type = "NETWORKEDITOR"
        self.x = 120
        self.y = -40


class TD:
    def __init__(self, project_folder, palette_folder):
        self.root = Node(self, "baseCOMP", "", None)
        self.project1 = self.root.create("containerCOMP", "project1")
        self.resources = self.root.create("baseCOMP", "TDResources")
        self.queue = []
        self.saved = []
        self.viewed = []
        self.project = types.SimpleNamespace(folder=str(project_folder))
        self.app = types.SimpleNamespace(version="2023", build="12000", userPaletteFolder=str(palette_folder))
        self.ui = types.SimpleNamespace(panes=types.SimpleNamespace(current=Pane(self.project1)), viewFile=self.viewed.append)

    def run(self, script, *args, delayFrames=0, delayRef=None, **kw):
        self.queue.append((time.time() + delayFrames / 60.0, script, args))

    def opfn(self, path):
        if path.startswith("/"):
            return self.root.op(path[1:]) if path != "/" else self.root
        return self.root.op(path)

    def globals_for(self, node):
        opf = self.opfn

        class OpCall:
            TDResources = self.resources

            def __call__(self, p):
                return node.op(p) if not p.startswith("/") else opf(p)

        return {
            "op": OpCall(),
            "ui": self.ui,
            "app": self.app,
            "project": self.project,
            "run": self.run,
            "parent": lambda: node._parent if not node.isCOMP else node._parent,
            "PaneType": types.SimpleNamespace(NETWORKEDITOR="NETWORKEDITOR"),
            "baseCOMP": "baseCOMP",
            "textDAT": "textDAT",
            "tableDAT": "tableDAT",
            "parameterexecuteDAT": "parameterexecuteDAT",
        }

    def textport_globals(self):
        g = self.globals_for(self.project1)
        g["op"] = self.opfn
        return g

    def par_changed(self, par):
        owner = par.owner
        pe = owner.children.get("parexec") if owner.children else None
        if pe is None or par.style == "Pulse":
            return
        pe.module.onValueChange(par, None)

    def pulse(self, comp, name):
        comp.op("parexec").module.onPulse(getattr(comp.par, name))

    def pump(self, until, timeout=240):
        end = time.time() + timeout
        while time.time() < end:
            if until():
                return True
            if not self.queue:
                time.sleep(0.02)
                continue
            self.queue.sort(key=lambda q: q[0])
            when, script, args = self.queue[0]
            if when > time.time():
                time.sleep(0.01)
                continue
            self.queue.pop(0)
            exec(script, {"args": args})
        return until()


def env_ok():
    return bool(os.environ.get("SHELF_LIVE"))
