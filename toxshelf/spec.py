import os
import re
from urllib.parse import unquote, urlparse

from .errors import ShelfError
from .semver import Range

_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_GH = re.compile(r"^(?:gh:|github:)?([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?((?:/[^@#]+)?)(?:([@#])(.+))?$")


class Spec:
    def __init__(self, kind, raw, owner=None, repo=None, subdir="", range_=None, ref=None, url=None, path=None, alias=None):
        self.kind = kind
        self.raw = raw
        self.owner = owner
        self.repo = repo
        self.subdir = subdir.strip("/") if subdir else ""
        self.range = range_ or Range("*")
        self.ref = ref
        self.url = url
        self.path = path
        self.alias = alias

    @property
    def source(self):
        if self.kind == "github":
            s = f"{self.owner}/{self.repo}"
            if self.subdir:
                s += "/" + self.subdir
            return s
        if self.kind == "url":
            return self.url
        if self.kind == "local":
            return self.path
        return self.alias

    def pinned(self):
        if self.ref:
            return f"#{self.ref}"
        return "" if self.range.is_any else f"@{self.range}"

    def __str__(self):
        return self.source + self.pinned()

    def __repr__(self):
        return f"Spec({self.kind}, {str(self)!r})"


def valid_name(name):
    return bool(_NAME.match(name or ""))


def clean_name(text):
    s = re.sub(r"[^a-z0-9._-]+", "-", (text or "").lower()).strip("-._")
    return s or "package"


def _split_version(text):
    for sep in ("@", "#"):
        if sep in text:
            head, tail = text.split(sep, 1)
            return head, sep, tail
    return text, None, None


def _with_version(spec, sep, tail):
    if sep == "@":
        try:
            spec.range = Range(tail)
        except ValueError:
            spec.ref = tail
    elif sep == "#":
        spec.ref = tail
    return spec


def parse(text, cwd=None):
    raw = (text or "").strip()
    if not raw:
        raise ShelfError("no package given")
    cwd = cwd or os.getcwd()

    if raw.startswith(("http://", "https://")):
        u = urlparse(raw)
        if u.netloc in ("github.com", "www.github.com"):
            parts = [unquote(p) for p in u.path.strip("/").split("/") if p]
            if len(parts) >= 2 and not raw.lower().endswith(".tox"):
                owner, repo = parts[0], parts[1]
                if repo.endswith(".git"):
                    repo = repo[:-4]
                ref, subdir = None, ""
                if len(parts) >= 4 and parts[2] in ("tree", "blob"):
                    ref = parts[3]
                    subdir = "/".join(parts[4:])
                elif len(parts) >= 4 and parts[2] == "releases" and parts[3] == "tag" and len(parts) >= 5:
                    ref = parts[4]
                s = Spec("github", raw, owner=owner, repo=repo, subdir=subdir, ref=ref)
                if u.fragment:
                    s.ref = u.fragment
                return s
            if len(parts) >= 5 and parts[2] == "blob" and raw.lower().endswith(".tox"):
                fixed = f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/{parts[3]}/{'/'.join(parts[4:])}"
                return Spec("url", raw, url=fixed)
        return Spec("url", raw, url=raw)

    head, sep, tail = _split_version(raw)
    local = head if os.path.isabs(head) else os.path.join(cwd, head)
    if head.startswith((".", "/", "~")) or re.match(r"^[A-Za-z]:[\\/]", head) or head.lower().endswith(".tox") or (os.path.exists(local) and "/" not in head.strip("/")):
        path = os.path.abspath(os.path.expanduser(local if not head.startswith("~") else head))
        return Spec("local", raw, path=path)

    m = _GH.match(head)
    if m and "/" in head:
        owner, repo, subdir = m.group(1), m.group(2), m.group(3)
        return _with_version(Spec("github", raw, owner=owner, repo=repo, subdir=subdir), sep, tail)

    if valid_name(head.lower()):
        return _with_version(Spec("alias", raw, alias=head.lower()), sep, tail)

    raise ShelfError(f"don't know how to install {raw!r}", "try owner/repo, a github url, a .tox url or a path")
