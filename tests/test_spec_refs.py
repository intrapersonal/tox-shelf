from toxshelf.github import Refs, parse_refs
from toxshelf.spec import parse


def pkt(s):
    b = s.encode() if isinstance(s, str) else s
    return f"{len(b) + 4:04x}".encode() + b


def test_parse_refs():
    data = (
        pkt("# service=git-upload-pack\n")
        + b"0000"
        + pkt(b"a" * 40 + b" HEAD\0multi_ack symref=HEAD:refs/heads/main agent=git/x\n")
        + pkt("a" * 40 + " refs/heads/main\n")
        + pkt("b" * 40 + " refs/heads/dev\n")
        + pkt("c" * 40 + " refs/tags/v1.0.0\n")
        + pkt("d" * 40 + " refs/tags/v1.0.0^{}\n")
        + pkt("e" * 40 + " refs/tags/notes\n")
        + b"0000"
    )
    refs, head = parse_refs(data)
    assert head == "refs/heads/main"
    r = Refs(refs, head)
    assert r.head == ("main", "a" * 40)
    assert r.tags()["v1.0.0"] == "d" * 40
    assert r.find("dev") == ("dev", "b" * 40)
    assert r.find("ddddddd")[1] == "d" * 40
    assert r.find("nope") == (None, None)


def test_specs():
    s = parse("intrapersonal/wintd@^1.2")
    assert (s.kind, s.owner, s.repo, str(s.range)) == ("github", "intrapersonal", "wintd", "^1.2")
    s = parse("intrapersonal/wintd#dev")
    assert s.ref == "dev"
    s = parse("someone/repo/components/thing@1.0.0")
    assert s.subdir == "components/thing"
    s = parse("https://github.com/a/b/tree/dev/sub/dir")
    assert (s.kind, s.ref, s.subdir) == ("github", "dev", "sub/dir")
    s = parse("https://github.com/a/b/blob/main/x/y.tox")
    assert s.kind == "url" and s.url == "https://raw.githubusercontent.com/a/b/main/x/y.tox"
    assert parse("https://example.com/x.tox").kind == "url"
    assert parse("wintd").kind == "alias"
    assert parse("someone/repo@main").ref == "main"
    assert parse("./thing.tox").kind == "local"
