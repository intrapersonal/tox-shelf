from urllib.parse import quote

from . import net
from .errors import ShelfError


def _pkt_lines(data):
    i = 0
    n = len(data)
    while i + 4 <= n:
        try:
            size = int(data[i:i + 4], 16)
        except ValueError:
            raise ShelfError("couldn't read refs from github")
        if size == 0:
            i += 4
            yield None
            continue
        if size < 4 or i + size > n:
            raise ShelfError("couldn't read refs from github")
        yield data[i + 4:i + size]
        i += size


def parse_refs(data):
    refs = {}
    head = None
    caps_seen = False
    for line in _pkt_lines(data):
        if line is None:
            continue
        if line.startswith(b"#"):
            continue
        line = line.rstrip(b"\n")
        if not caps_seen and b"\0" in line:
            line, caps = line.split(b"\0", 1)
            caps_seen = True
            for cap in caps.decode("utf-8", "replace").split():
                if cap.startswith("symref=HEAD:"):
                    head = cap.split(":", 1)[1]
        parts = line.decode("utf-8", "replace").split(" ", 1)
        if len(parts) != 2:
            continue
        sha, name = parts
        if name.endswith("^{}"):
            refs[name[:-3]] = sha
        elif name not in refs:
            refs[name] = sha
    return refs, head


class Refs:
    def __init__(self, refs, head):
        self.refs = refs
        self.head_ref = head

    @property
    def head(self):
        if self.head_ref and self.head_ref in self.refs:
            return self.head_ref[len("refs/heads/"):], self.refs[self.head_ref]
        if "HEAD" in self.refs:
            return "HEAD", self.refs["HEAD"]
        return None, None

    def tags(self):
        return {k[len("refs/tags/"):]: v for k, v in self.refs.items() if k.startswith("refs/tags/")}

    def branches(self):
        return {k[len("refs/heads/"):]: v for k, v in self.refs.items() if k.startswith("refs/heads/")}

    def find(self, ref):
        if ref in self.tags():
            return ref, self.tags()[ref]
        if ref in self.branches():
            return ref, self.branches()[ref]
        if len(ref) >= 7 and all(c in "0123456789abcdef" for c in ref.lower()):
            for sha in self.refs.values():
                if sha.startswith(ref.lower()):
                    return ref, sha
            if len(ref) == 40:
                return ref, ref.lower()
        return None, None


def ls_remote(owner, repo):
    url = f"https://github.com/{quote(owner)}/{quote(repo)}.git/info/refs?service=git-upload-pack"
    data = net.get(url, what=f"{owner}/{repo} on github")
    refs, head = parse_refs(data)
    if not refs:
        raise ShelfError(f"{owner}/{repo} is empty")
    return Refs(refs, head)


def tarball(owner, repo, sha):
    return net.get(
        f"https://codeload.github.com/{quote(owner)}/{quote(repo)}/tar.gz/{sha}",
        timeout=180,
        what=f"{owner}/{repo}@{sha[:7]}",
    )


def _search(q, limit):
    data = net.get_json(
        f"https://api.github.com/search/repositories?q={quote(q)}&sort=stars&order=desc&per_page={limit}",
        what="github search",
    )
    return [
        {
            "repo": item.get("full_name", ""),
            "description": item.get("description") or "",
            "stars": item.get("stargazers_count", 0),
            "topics": item.get("topics") or [],
            "updated": item.get("pushed_at") or "",
        }
        for item in data.get("items", [])
    ]


def search(query, limit=20):
    query = (query or "").strip()
    out = _search(f"{query} topic:touchdesigner".strip(), limit)
    if query and len(out) < limit:
        seen = {r["repo"] for r in out}
        for r in _search(f"{query} touchdesigner in:name,description", limit):
            if r["repo"] not in seen:
                out.append(r)
    return out[:limit]


def repo_info(owner, repo):
    return net.get_json(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}", what=f"{owner}/{repo}")
