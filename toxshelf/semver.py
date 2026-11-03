import re
from functools import total_ordering

_VERSION = re.compile(
    r"^(?:v|ver|version|release|rel)?[._-]?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


@total_ordering
class Version:
    def __init__(self, major, minor=0, patch=0, pre=(), build=""):
        self.major = int(major)
        self.minor = int(minor)
        self.patch = int(patch)
        self.pre = tuple(pre)
        self.build = build

    @classmethod
    def parse(cls, text):
        v = cls.try_parse(text)
        if v is None:
            raise ValueError(f"not a version: {text!r}")
        return v

    @classmethod
    def try_parse(cls, text):
        if text is None:
            return None
        m = _VERSION.match(str(text).strip())
        if not m:
            return None
        major, minor, patch, pre, build = m.groups()
        pre_parts = tuple(int(p) if p.isdigit() else p for p in pre.split(".")) if pre else ()
        return cls(major, minor or 0, patch or 0, pre_parts, build or "")

    @property
    def core(self):
        return (self.major, self.minor, self.patch)

    @property
    def prerelease(self):
        return bool(self.pre)

    def _pre_key(self):
        if not self.pre:
            return (1,)
        return (0,) + tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in self.pre)

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.core == other.core and self.pre == other.pre

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return (self.core, self._pre_key()) < (other.core, other._pre_key())

    def __hash__(self):
        return hash((self.core, self.pre))

    def __str__(self):
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            s += "-" + ".".join(str(p) for p in self.pre)
        if self.build:
            s += "+" + self.build
        return s

    def __repr__(self):
        return f"Version({str(self)!r})"


_COMPARATOR = re.compile(r"^(<=|>=|<|>|=|\^|~)?\s*(.+)$")
_PARTIAL = re.compile(r"^v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(?:-([0-9A-Za-z.-]+))?$")


def _wild(p):
    return p is None or p in ("x", "X", "*")


def _expand(op, text):
    m = _PARTIAL.match(text)
    if not m:
        raise ValueError(f"bad version range: {text!r}")
    a, b, c, pre = m.groups()
    if _wild(a):
        return [(">=", Version(0, 0, 0))] if op in ("", "=", "^", "~", ">=") else []
    major = int(a)
    if _wild(b):
        lo, hi = Version(major), Version(major + 1)
        return _bounds(op, lo, hi)
    minor = int(b)
    if _wild(c):
        lo, hi = Version(major, minor), Version(major, minor + 1)
        if op == "^":
            hi = Version(major + 1) if major else Version(0, minor + 1)
        return _bounds(op, lo, hi)
    patch = int(c)
    v = Version(major, minor, patch, Version.parse(f"0.0.0-{pre}").pre if pre else ())
    if op in ("", "="):
        return [("=", v)]
    if op == "^":
        if major:
            hi = Version(major + 1)
        elif minor:
            hi = Version(0, minor + 1)
        else:
            hi = Version(0, 0, patch + 1)
        return [(">=", v), ("<", hi)]
    if op == "~":
        return [(">=", v), ("<", Version(major, minor + 1))]
    return [(op, v)]


def _bounds(op, lo, hi):
    if op in ("", "=", "^", "~"):
        return [(">=", lo), ("<", hi)]
    if op == ">":
        return [(">=", hi)]
    if op == ">=":
        return [(">=", lo)]
    if op == "<":
        return [("<", lo)]
    if op == "<=":
        return [("<", hi)]
    return [(op, lo)]


def _test(op, a, b):
    if op == "=":
        return a == b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        if a.prerelease and not b.prerelease and a.core == b.core:
            return False
        return a < b
    if op == "<=":
        return a <= b
    raise ValueError(op)


class Range:
    def __init__(self, text="*"):
        self.text = (text or "*").strip()
        self.sets = []
        raw = self.text
        if raw in ("", "*", "latest", "x", "X"):
            self.sets = [[(">=", Version(0, 0, 0))]]
            return
        for alt in raw.split("||"):
            alt = alt.strip()
            comps = []
            hyphen = re.match(r"^(\S+)\s+-\s+(\S+)$", alt)
            if hyphen:
                comps += _expand(">=", hyphen.group(1))
                comps += _expand("<=", hyphen.group(2))
            else:
                tokens = re.findall(r"(?:<=|>=|<|>|=|\^|~)?\s*[^\s<>=^~]+", alt)
                if not tokens:
                    raise ValueError(f"bad version range: {alt!r}")
                for tok in tokens:
                    m = _COMPARATOR.match(tok.strip())
                    comps += _expand(m.group(1) or "", m.group(2).strip())
            self.sets.append(comps)

    def matches(self, version, allow_pre=False):
        if isinstance(version, str):
            version = Version.try_parse(version)
            if version is None:
                return False
        for comps in self.sets:
            if not all(_test(op, version, v) for op, v in comps):
                continue
            if version.prerelease and not allow_pre:
                if not any(v.prerelease and v.core == version.core for _, v in comps):
                    continue
            return True
        return False

    def best(self, versions, allow_pre=False):
        good = [v for v in versions if self.matches(v, allow_pre)]
        return max(good) if good else None

    @property
    def is_any(self):
        return self.text in ("", "*", "latest", "x", "X")

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"Range({self.text!r})"


def caret(version):
    v = Version.parse(str(version)) if not isinstance(version, Version) else version
    return f"^{v.major}.{v.minor}.{v.patch}"
