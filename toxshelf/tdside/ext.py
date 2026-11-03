import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ShelfExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.q = queue.Queue()
        self.busy = False
        self.waiting = False
        self.pending = []
        run("args[0].Hello()", self, delayFrames=30, delayRef=op.TDResources)

    @property
    def par(self):
        return self.ownerComp.par

    def Exe(self):
        p = self.par.Shelfexe.eval()
        if p:
            return p
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "tox-shelf" / "bin" / "shelf.exe"
        if local.is_file():
            return str(local)
        return shutil.which("shelf") or "shelf"

    def Cmd(self, args):
        exe = self.Exe()
        base = [exe]
        if Path(exe).name.lower().startswith("python"):
            base += ["-m", "toxshelf"]
        return base + ["--json"] + [str(a) for a in args]

    def InProject(self):
        return self.par.Scope.eval() == "project"

    def Status(self, text):
        self.par.Status = text

    def Run(self, args, done=None, label=None, quiet=False):
        if self.busy:
            if not any(p[0] == args for p in self.pending):
                self.pending.append((args, done, label, quiet))
            return True
        self.busy = True
        if label:
            self.Status(label)
        cwd = project.folder if self.InProject() else None
        cmd = self.Cmd(args)

        def work():
            try:
                r = subprocess.run(cmd, capture_output=True, cwd=cwd, creationflags=NO_WINDOW, timeout=900)
                lines = r.stdout.decode("utf-8", "replace").strip().splitlines()
                data = None
                for line in reversed(lines):
                    try:
                        data = json.loads(line)
                        break
                    except ValueError:
                        continue
                if data is None:
                    err = r.stderr.decode("utf-8", "replace").strip()
                    data = {"ok": False, "error": err[-300:] or "shelf didn't say anything"}
            except FileNotFoundError:
                data = {"ok": False, "error": "couldn't find shelf", "hint": "install it (see the readme) or point Shelf Exe at shelf.exe"}
            except subprocess.TimeoutExpired:
                data = {"ok": False, "error": "shelf took too long"}
            except Exception as e:
                data = {"ok": False, "error": str(e)}
            self.q.put((done, data, quiet))

        threading.Thread(target=work, daemon=True).start()
        if not self.waiting:
            self.waiting = True
            run("args[0].Poll()", self, delayFrames=4, delayRef=op.TDResources)
        return True

    def Poll(self):
        try:
            done, data, quiet = self.q.get_nowait()
        except queue.Empty:
            run("args[0].Poll()", self, delayFrames=4, delayRef=op.TDResources)
            return
        self.waiting = False
        self.busy = False
        try:
            if not data.get("ok"):
                if not quiet:
                    msg = "error: " + str(data.get("error"))
                    if data.get("hint"):
                        msg += " (" + str(data["hint"]) + ")"
                    self.Status(msg)
            elif done:
                done(data)
        finally:
            if self.pending and not self.busy:
                self.Run(*self.pending.pop(0))

    def Hello(self):
        build = f"{app.version}.{app.build}"

        def palette(_):
            folder = getattr(app, "userPaletteFolder", "")
            if folder:
                self.Run(["config", "set", "palette", folder], lambda d: self.Refresh(), quiet=True)
            else:
                self.Refresh()

        self.Run(["config", "set", "td_build", build], palette)

    def OnPar(self, par):
        n = par.name
        if n == "Install":
            self.Install()
        elif n == "Place":
            self.Place(self.par.Installed.eval())
        elif n == "Remove":
            self.Remove(self.par.Installed.eval())
        elif n == "Update":
            self.Update()
        elif n == "Refresh":
            self.Refresh()
        elif n == "Searchgo":
            self.Search()
        elif n == "Results":
            pick = par.eval()
            if pick:
                self.par.Package = pick
        elif n == "Scope":
            self.Refresh()
        elif n == "Openfolder":
            self.OpenFolder()

    def Install(self, spec=None):
        spec = (spec or self.par.Package.eval()).strip()
        if not spec:
            self.Status("type a package in first, like intrapersonal/wintd")
            return
        build = f"{app.version}.{app.build}"

        def finished(data):
            got = data.get("installed", [])
            roots = [g for g in got if not g.get("dependency_of")]
            names = ", ".join(g["name"] for g in got) or "nothing"
            warn = data.get("warnings") or []
            self.Status(f"installed {names}" + (" | " + "; ".join(warn) if warn else ""))
            self.Refresh(select=roots[0]["name"] if roots else None, then_place=bool(self.par.Placeafter.eval()) and bool(roots))

        if self.InProject():
            if not Path(project.folder, "shelf.json").is_file():
                self.Run(["init", "--project"], lambda d: self.Run(["add", spec], finished, f"adding {spec}..."), "setting up the project...")
                return
            self.Run(["add", spec], finished, f"adding {spec}...")
        else:
            self.Run(["install", spec, "--td", build], finished, f"installing {spec}...")

    def Remove(self, name):
        if not name:
            self.Status("pick something under Installed first")
            return
        args = ["remove", name] if self.InProject() else ["remove", "-g", name]

        def finished(data):
            self.Status("removed " + ", ".join(data.get("removed", [])))
            self.Refresh()

        self.Run(args, finished, f"removing {name}...")

    def Update(self):
        args = ["update"] if self.InProject() else ["update", "-g", "--td", f"{app.version}.{app.build}"]

        def finished(data):
            got = data.get("updated", [])
            changed = [g for g in got if g.get("previous_sha", g.get("sha")) != g.get("sha") or g.get("previous", g.get("version")) != g.get("version")]
            self.Status("updated " + ", ".join(g["name"] for g in changed) if changed else "everything's up to date")
            self.Refresh()

        self.Run(args, finished, "checking for updates...")

    def Refresh(self, select=None, then_place=False):
        args = ["list"] if self.InProject() else ["list", "-g"]

        def finished(data):
            rows = data.get("packages", [])
            t = self.ownerComp.op("packages")
            t.clear()
            t.appendRow(["name", "version", "from", "tox"])
            for r in rows:
                t.appendRow([r.get("name", ""), r.get("version", ""), r.get("from", ""), " ".join(r.get("tox") or [])])
            names = [r["name"] for r in rows]
            p = self.par.Installed
            p.menuNames = names
            p.menuLabels = [f"{r['name']}  {r.get('version') or ''}".strip() for r in rows]
            if select and select in names:
                p.val = select
            if self.par.Status.eval() in ("", "loading..."):
                self.Status(f"{len(names)} installed" if names else "nothing installed yet")
            if then_place and select:
                self.Place(select)

        self.Run(args, finished, quiet=True)

    def Search(self):
        q = self.par.Search.eval().strip()

        def finished(data):
            res = data.get("results", [])
            t = self.ownerComp.op("results")
            t.clear()
            t.appendRow(["name", "repo", "description", "stars", "indexed"])
            for r in res:
                t.appendRow([r.get("name", ""), r.get("repo", ""), r.get("description", ""), r.get("stars", ""), int(bool(r.get("indexed")))])
            p = self.par.Results
            p.menuNames = [r["name"] for r in res]
            p.menuLabels = [(r["name"] + ("  ★" + str(r["stars"]) if r.get("stars") else "") + ("  - " + r["description"][:50] if r.get("description") else "")) for r in res]
            self.Status(f"{len(res)} results, pick one under Results then hit Install" if res else "nothing found")

        self.Run(["search", "-n", "25"] + q.split(), finished, f"searching {q}..." if q else "searching...")

    def Place(self, name):
        if not name:
            self.Status("pick something under Installed first")
            return
        args = ["where", name] if self.InProject() else ["where", "-g", name]

        def finished(data):
            paths = data.get("tox", [])
            made = [self.LoadTox(p, i) for i, p in enumerate(paths)]
            made = [m for m in made if m is not None]
            self.Status(f"placed {', '.join(m.name for m in made)}" if made else f"couldn't load {name}")

        self.Run(args, finished, f"placing {name}...")

    def Target(self):
        try:
            pane = ui.panes.current
            if pane is not None and pane.type == PaneType.NETWORKEDITOR:
                owner = pane.owner
                if owner == self.ownerComp or owner.path.startswith(self.ownerComp.path + "/"):
                    return self.ownerComp.parent(), None
                return owner, pane
        except Exception:
            pass
        return self.ownerComp.parent(), None

    def LoadTox(self, path, i=0):
        target, pane = self.Target()
        try:
            comp = target.loadTox(path)
        except Exception as e:
            self.Status(f"td couldn't load {Path(path).name}: {e}")
            return None
        if pane is not None:
            comp.nodeX = int(getattr(pane, "x", 0)) + i * 180
            comp.nodeY = int(getattr(pane, "y", 0)) - i * 40
        else:
            comp.nodeX = self.ownerComp.nodeX + 200 + i * 180
            comp.nodeY = self.ownerComp.nodeY - 150
        if self.InProject():
            try:
                rel = os.path.relpath(path, project.folder).replace("\\", "/")
                if not rel.startswith(".."):
                    comp.par.externaltox = rel
                    if hasattr(comp.par, "enableexternaltox"):
                        comp.par.enableexternaltox = True
            except ValueError:
                pass
        comp.current = True
        return comp

    def OpenFolder(self):
        if self.InProject():
            folder = Path(project.folder) / "shelf_modules"
        else:
            folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "tox-shelf" / "packages"
        folder.mkdir(parents=True, exist_ok=True)
        ui.viewFile(str(folder))
