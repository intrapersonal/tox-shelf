import json
import os

import pytest

from conftest import make_pkg
from toxshelf import cli, manifest, project, store
from toxshelf.errors import ShelfError


def run(capsys, *args):
    code = cli.main(["--json", *args])
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return code, json.loads(out)


def test_global_install_remove(tmp_path, shelf_home, capsys):
    home, pal = shelf_home
    make_pkg(tmp_path / "dep", "dep", tox=("dep.tox",))
    make_pkg(tmp_path / "app", "app", tox=("a.tox", "sub/b.tox"), deps={"../dep": "*"}, extra={"docs/readme.txt": "hi"})
    code, res = run(capsys, "install", str(tmp_path / "app"))
    assert code == 0, res
    names = {d["name"]: d for d in res["installed"]}
    assert set(names) == {"app", "dep"}
    assert names["dep"]["dependency_of"] == "app"
    assert (home / "packages" / "app" / "sub" / "b.tox").is_file()
    assert (pal / "shelf" / "app" / "b.tox").is_file()
    assert (pal / "shelf" / "dep" / "dep.tox").is_file()

    code, res = run(capsys, "list", "-g")
    assert {p["name"] for p in res["packages"]} == {"app", "dep"}

    code, res = run(capsys, "remove", "-g", "dep")
    assert code == 1 and "needed by app" in res["error"]

    code, res = run(capsys, "remove", "-g", "app")
    assert code == 0 and set(res["removed"]) == {"app", "dep"}
    assert not (pal / "shelf" / "app").exists()
    assert store.installed() == {}


def test_bare_tox_and_folder_without_manifest(tmp_path, shelf_home, capsys):
    t = tmp_path / "Cool Thing.tox"
    t.write_bytes(b"x")
    code, res = run(capsys, "install", str(t))
    assert code == 0 and res["installed"][0]["name"] == "cool-thing"
    make_pkg(tmp_path / "loose", "loose", tox=("release/one.tox", "dev/scratch.tox", "examples/ex.tox"), manifest=False)
    code, res = run(capsys, "install", str(tmp_path / "loose"))
    assert code == 0
    code, res = run(capsys, "where", "-g", "loose")
    assert [os.path.basename(p) for p in res["tox"]] == ["one.tox"]


def test_project_flow(tmp_path, shelf_home, capsys, monkeypatch):
    make_pkg(tmp_path / "libs" / "dep", "dep", tox=("dep.tox",))
    make_pkg(tmp_path / "libs" / "fx", "fx", tox=("fx.tox",), deps={"../dep": "*"})
    proj = tmp_path / "myproj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    code, res = run(capsys, "init")
    assert code == 0 and res["package"] is False
    code, res = run(capsys, "add", "../libs/fx")
    assert code == 0, res
    m = manifest.load(proj)
    assert list(m.dependencies) == ["../libs/fx"]
    lock = project.read_lock(proj)
    assert lock["packages"]["fx"]["root"] == "../libs/fx"
    assert lock["packages"]["dep"]["by"] == ["fx"]
    assert (proj / "shelf_modules" / "dep" / "dep.tox").is_file()

    code, res = run(capsys, "where", "fx")
    assert res["tox"][0].endswith(os.path.join("shelf_modules", "fx", "fx.tox"))

    import shutil

    shutil.rmtree(proj / "shelf_modules")
    code, res = run(capsys, "sync", "--frozen")
    assert code == 0 and {d["name"] for d in res["installed"]} == {"fx", "dep"}
    code, res = run(capsys, "sync")
    assert res["installed"] == []

    (tmp_path / "libs" / "fx" / "fx.tox").write_bytes(b"changed")
    shutil.rmtree(proj / "shelf_modules" / "fx")
    code, res = run(capsys, "sync")
    assert code == 1 and "changed since it was locked" in res["error"]
    code, res = run(capsys, "sync", "--update")
    assert code == 0

    code, res = run(capsys, "drop", "fx")
    assert set(res["removed"]) == {"fx", "dep"}
    assert project.read_lock(proj)["packages"] == {}
    assert not (proj / "shelf_modules" / "fx").exists()


def test_shared_dep_survives(tmp_path, shelf_home, monkeypatch):
    make_pkg(tmp_path / "dep", "dep", tox=("dep.tox",))
    make_pkg(tmp_path / "a", "a", tox=("a.tox",), deps={"../dep": "*"})
    make_pkg(tmp_path / "b", "b", tox=("b.tox",), deps={"../dep": "*"})
    proj = tmp_path / "p"
    proj.mkdir()
    project.init(proj, package=False)
    project.add(proj, ["../a"])
    project.add(proj, ["../b"])
    assert sorted(project.read_lock(proj)["packages"]["dep"]["by"]) == ["a", "b"]
    project.drop(proj, ["a"])
    assert set(project.read_lock(proj)["packages"]) == {"b", "dep"}


def test_check_and_init_package(tmp_path, shelf_home, capsys, monkeypatch):
    d = make_pkg(tmp_path / "mine", "x", tox=("comp.tox",), manifest=False)
    monkeypatch.chdir(d)
    code, res = run(capsys, "init", "--name", "My Comp")
    assert res["package"] and res["manifest"]["name"] == "my-comp"
    code, res = run(capsys, "check")
    assert code == 0 and res["ok"]
    data = json.loads((d / "shelf.json").read_text())
    data["tox"].append("missing.tox")
    data["version"] = "one"
    (d / "shelf.json").write_text(json.dumps(data))
    code, res = run(capsys, "check")
    assert not res["ok"] and len(res["problems"]) == 2


def test_errors(tmp_path, shelf_home):
    with pytest.raises(ShelfError):
        store.remove(["nope"])
    with pytest.raises(ShelfError):
        store.install([str(tmp_path / "missing")])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ShelfError, match="no .tox"):
        store.install([str(empty)])
