import hashlib
import io
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse, unquote

from . import github, manifest, net
from .errors import ShelfError
from .paths import cache_dir
from .semver import Version
from .spec import Spec, clean_name


class Fetched:
    def __init__(self, **kw):
        self.name = kw.get("name")
        self.version = kw.get("version") or "0.0.0"
        self.kind = kw.get("kind")
        self.source = kw.get("source")
        self.ref = kw.get("ref")
        self.sha = kw.get("sha")
        self.url = kw.get("url")
        self.root = kw.get("root")
        self.manifest = kw.get("manifest")
        self.files = kw.get("files") or []
        self.integrity = kw.get("integrity") or ""

    @property
    def dependencies(self):
        return self.manifest.dependencies if self.manifest else {}

    @property
    def description(self):
        return self.manifest.description if self.manifest else ""

    @property
    def touchdesigner(self):
        return self.manifest.touchdesigner if self.manifest else ""

    @property
    def tox(self):
        return [f for f in self.files if f.lower().endswith(".tox")]

    def lock_entry(self):
        e = {"version": self.version, "kind": self.kind, "source": self.source, "integrity": self.integrity}
        if self.ref:
            e["ref"] = self.ref
        if self.sha:
            e["sha"] = self.sha
        if self.url:
            e["url"] = self.url
        if self.dependencies:
            e["dependencies"] = self.dependencies
        return e


def integrity(root, files):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8") + b"\0")
        with open(Path(root) / rel, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        h.update(b"\0")
    return "sha256-" + h.hexdigest()


def _safe_extract(data, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except tarfile.TarError:
        raise ShelfError("download came back broken, try again")
    with tf:
        for m in tf.getmembers():
            parts = PurePosixPath(m.name).parts
            if len(parts) <= 1:
                continue
            rel = PurePosixPath(*parts[1:])
            if rel.is_absolute() or ".." in rel.parts:
                continue
            target = dest.joinpath(*rel.parts)
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    continue
                with src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


def _tarball(owner, repo, sha):
    cached = cache_dir() / "tarballs" / f"{owner}-{repo}-{sha}.tar.gz"
    if cached.is_file():
        return cached.read_bytes()
    data = github.tarball(owner, repo, sha)
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, cached)
    except OSError:
        pass
    return data


def _git_checkout(owner, repo, sha, dest):
    git = shutil.which("git")
    if not git:
        return False
    import subprocess

    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".git-tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    flags = {"creationflags": 0x08000000} if os.name == "nt" else {}
    url = f"https://github.com/{owner}/{repo}.git"
    steps = [
        [git, "init", "-q"],
        [git, "-c", "advice.detachedHead=false", "fetch", "-q", "--depth", "1", url, sha],
        [git, "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD"],
    ]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    for cmd in steps:
        r = subprocess.run(cmd, cwd=tmp, capture_output=True, env=env, **flags)
        if r.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            return False
    shutil.rmtree(tmp / ".git", ignore_errors=True)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return True


def _download_repo(owner, repo, sha, dest):
    try:
        _safe_extract(_tarball(owner, repo, sha), dest)
    except ShelfError:
        if not _git_checkout(owner, repo, sha, dest):
            raise


def _semver_tags(refs):
    out = {}
    for tag, sha in refs.tags().items():
        v = Version.try_parse(tag)
        if v is not None:
            out[v] = (tag, sha)
    return out


def pick_github(spec, refs):
    tags = _semver_tags(refs)
    if spec.ref:
        ref, sha = refs.find(spec.ref)
        if not sha:
            raise ShelfError(f"{spec.owner}/{spec.repo} has no branch, tag or commit called {spec.ref!r}")
        v = Version.try_parse(ref)
        return ref, sha, (str(v) if v and ref in refs.tags() else None)
    if tags:
        best = spec.range.best(tags.keys())
        if best is None and spec.range.is_any:
            best = spec.range.best(tags.keys(), allow_pre=True)
        if best is None:
            have = ", ".join(str(v) for v in sorted(tags)[-6:])
            raise ShelfError(f"no version of {spec.owner}/{spec.repo} matches {spec.range}", f"it has: {have}")
        tag, sha = tags[best]
        return tag, sha, str(best)
    if not spec.range.is_any:
        raise ShelfError(
            f"{spec.owner}/{spec.repo} doesn't have any version tags",
            f"install it without a version, or pin a branch with {spec.owner}/{spec.repo}#main",
        )
    branch, sha = refs.head
    if not sha:
        raise ShelfError(f"couldn't figure out the default branch of {spec.owner}/{spec.repo}")
    return branch, sha, None


def _finish(kind, root, default_name, version, source, ref=None, sha=None, url=None, subdir=""):
    base = Path(root) / subdir if subdir else Path(root)
    if subdir and not base.is_dir():
        raise ShelfError(f"{subdir} doesn't exist in {source}")
    m = manifest.load(base, required=False)
    if m is not None and m.is_package:
        bad = m.problems(strict=False)
        if bad:
            raise ShelfError(f"{source} has a broken shelf.json: " + "; ".join(bad))
        name = m.name or clean_name(default_name)
        if not version:
            version = m.version or None
    else:
        deps = m.dependencies if m is not None else {}
        m = manifest.synthesize(base, default_name, version)
        if m is None:
            raise ShelfError(f"no .tox files in {source}")
        if deps:
            m.data["dependencies"] = deps
        name = m.name
    if not version:
        version = "0.0.0"
    files = m.files()
    missing = [f for f in files if not (base / f).is_file()]
    if missing:
        raise ShelfError(f"{source} is missing {', '.join(missing)}")
    return Fetched(
        name=name,
        version=version,
        kind=kind,
        source=source,
        ref=ref,
        sha=sha,
        url=url,
        root=base,
        manifest=m,
        files=files,
        integrity=integrity(base, files),
    )


def fetch(spec, workdir, lookup=None):
    workdir = Path(workdir)
    if spec.kind == "alias":
        if lookup is None:
            raise ShelfError(f"don't know what {spec.alias!r} is")
        target = lookup(spec.alias)
        if target is None:
            raise ShelfError(f"{spec.alias!r} isn't in the index", "use owner/repo instead, or `shelf search` for it")
        from .spec import parse

        real = parse(target)
        real.range, real.ref = spec.range, spec.ref or real.ref
        return fetch(real, workdir, lookup)

    if spec.kind == "github":
        refs = github.ls_remote(spec.owner, spec.repo)
        ref, sha, version = pick_github(spec, refs)
        dest = workdir / f"{spec.owner}-{spec.repo}-{sha[:12]}"
        if not dest.is_dir():
            _download_repo(spec.owner, spec.repo, sha, dest)
        name = spec.subdir.rsplit("/", 1)[-1] if spec.subdir else spec.repo
        return _finish("github", dest, name, version, spec.source, ref=ref, sha=sha, subdir=spec.subdir)

    if spec.kind == "url":
        data = net.get(spec.url, timeout=180, what=spec.url)
        fname = unquote(os.path.basename(urlparse(spec.url).path)) or "component.tox"
        if not fname.lower().endswith(".tox"):
            fname += ".tox"
        dest = workdir / ("url-" + hashlib.sha1(spec.url.encode()).hexdigest()[:12])
        dest.mkdir(parents=True, exist_ok=True)
        (dest / fname).write_bytes(data)
        f = _finish("url", dest, fname[:-4], None, spec.url, url=spec.url)
        f.sha = hashlib.sha256(data).hexdigest()
        return f

    if spec.kind == "local":
        p = Path(spec.path)
        if p.is_file():
            if not p.name.lower().endswith(".tox"):
                raise ShelfError(f"{p} isn't a .tox")
            dest = workdir / ("local-" + hashlib.sha1(str(p).encode()).hexdigest()[:12])
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest / p.name)
            return _finish("local", dest, p.stem, None, str(p))
        if p.is_dir():
            return _finish("local", p, p.name, None, str(p))
        raise ShelfError(f"{p} doesn't exist")

    raise ShelfError(f"can't fetch {spec}")


def fetch_locked(entry, workdir):
    kind = entry.get("kind")
    if kind == "github":
        src = entry["source"]
        parts = src.split("/")
        owner, repo, subdir = parts[0], parts[1], "/".join(parts[2:])
        sha = entry["sha"]
        dest = Path(workdir) / f"{owner}-{repo}-{sha[:12]}"
        if not dest.is_dir():
            _download_repo(owner, repo, sha, dest)
        name = subdir.rsplit("/", 1)[-1] if subdir else repo
        f = _finish("github", dest, name, entry.get("version"), src, ref=entry.get("ref"), sha=sha, subdir=subdir)
    else:
        spec = Spec(kind, entry.get("source"), url=entry.get("url"), path=entry.get("source"))
        f = fetch(spec, workdir)
    want = entry.get("integrity")
    if want and f.integrity != want:
        raise ShelfError(
            f"{entry.get('source')} changed since it was locked",
            "if you trust the change run `shelf sync --update`",
        )
    return f
