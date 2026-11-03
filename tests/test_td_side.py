import os
import sys

import pytest

from conftest import ROOT, make_pkg
from fake_td import TD
from toxshelf.tdside import bootstrap


@pytest.fixture(autouse=True)
def _importable(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def build(tmp_path, shelf_home):
    home, pal = shelf_home
    proj = tmp_path / "tdproject"
    proj.mkdir()
    td = TD(proj, pal)
    src = bootstrap.source(sys.executable, home)
    exec(compile(src, "bootstrap", "exec"), td.textport_globals())
    comp = td.project1.op("shelf")
    return td, comp, proj, pal


def test_builder_makes_the_comp(tmp_path, shelf_home):
    td, c, proj, pal = build(tmp_path, shelf_home)
    assert c is not None and c.isCOMP
    for name in ("Package", "Install", "Scope", "Installed", "Place", "Remove", "Update", "Search", "Searchgo", "Results", "Status", "Shelfexe", "About"):
        assert hasattr(c.par, name), name
    assert c.par.Scope.menuNames == ["global", "project"]
    assert c.par.Shelfexe.eval() == sys.executable
    assert c.par.Status.readOnly
    assert hasattr(c.ext, "ShelfExt")
    assert (pal / "shelf" / "shelf.tox").is_file()
    assert c.op("packages").rows[0] == ["name", "version", "from", "tox"]


def test_rebuild_replaces(tmp_path, shelf_home):
    td, c, proj, pal = build(tmp_path, shelf_home)
    c.nodeX = 555
    home, _ = shelf_home
    exec(compile(bootstrap.source(sys.executable, home), "bootstrap", "exec"), td.textport_globals())
    c2 = td.project1.op("shelf")
    assert c2 is not c and c2.nodeX == 555


def test_hello_install_place_remove_global(tmp_path, shelf_home):
    td, c, proj, pal = build(tmp_path, shelf_home)
    ext = c.ext.ShelfExt
    td.pump(lambda: not ext.busy and not ext.waiting and c.par.Status.eval() == "nothing installed yet", timeout=60)
    assert c.par.Status.eval() == "nothing installed yet", c.par.Status.eval()

    lib = make_pkg(tmp_path / "lib", "glow", tox=("glow.tox",))
    c.par.Package = str(lib)
    td.pulse(c, "Install")
    assert td.pump(lambda: "glow" in c.par.Installed.menuNames and not ext.busy and "glow" in [n.name for n in td.project1.children.values()], timeout=60), c.par.Status.eval()
    placed = td.project1.op("glow")
    assert placed.loaded_from.endswith("glow.tox")
    assert placed.nodeX == 120
    assert c.op("packages").rows[1][0] == "glow"

    c.par.Installed = "glow"
    td.pulse(c, "Remove")
    assert td.pump(lambda: c.par.Status.eval().startswith("removed") and not ext.busy, timeout=60)
    td.pump(lambda: c.par.Installed.menuNames == [] and not ext.busy, timeout=30)
    assert c.par.Installed.menuNames == []


def test_project_scope_links_external(tmp_path, shelf_home):
    td, c, proj, pal = build(tmp_path, shelf_home)
    ext = c.ext.ShelfExt
    td.pump(lambda: not ext.busy and not ext.waiting and c.par.Status.eval() != "loading...", timeout=60)
    lib = make_pkg(tmp_path / "lib", "glow", tox=("glow.tox",))
    c.par.Scope = "project"
    td.pump(lambda: not ext.busy and not ext.waiting, timeout=30)
    c.par.Package = str(lib)
    td.pulse(c, "Install")
    assert td.pump(lambda: td.project1.op("glow") is not None and not ext.busy, timeout=60), c.par.Status.eval()
    assert (proj / "shelf.json").is_file()
    assert (proj / "shelf_modules" / "glow" / "glow.tox").is_file()
    assert td.project1.op("glow").par.externaltox.eval() == "shelf_modules/glow/glow.tox"


def test_missing_cli_says_so(tmp_path, shelf_home):
    td, c, proj, pal = build(tmp_path, shelf_home)
    c.par.Shelfexe = str(tmp_path / "nope.exe")
    ext = c.ext.ShelfExt
    td.pump(lambda: not ext.busy and not ext.waiting, timeout=60)
    c.par.Package = "x/y"
    td.pulse(c, "Install")
    assert td.pump(lambda: "couldn't find shelf" in c.par.Status.eval(), timeout=30), c.par.Status.eval()
