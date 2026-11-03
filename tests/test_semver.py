import pytest

from toxshelf.semver import Range, Version


def v(s):
    return Version.parse(s)


VERSIONS = [v(x) for x in ["0.3.1", "0.3.4", "0.4.0", "1.0.0", "1.2.0", "1.2.5", "2.0.0-beta.1", "2.0.0", "2.1.0-rc.1"]]


@pytest.mark.parametrize(
    "rng,want",
    [
        ("*", "2.0.0"),
        ("latest", "2.0.0"),
        ("^1.0", "1.2.5"),
        ("^1.2.0", "1.2.5"),
        ("~1.2.0", "1.2.5"),
        ("~1.0", "1.0.0"),
        ("1.x", "1.2.5"),
        ("1", "1.2.5"),
        ("^0.3.1", "0.3.4"),
        ("^0.4", "0.4.0"),
        (">=1.1 <2", "1.2.5"),
        ("1.2.0 - 1.2.4", "1.2.0"),
        ("<1 || >=2", "2.0.0"),
        ("=1.0.0", "1.0.0"),
        ("v1.2.0", "1.2.0"),
        ("^3", None),
    ],
)
def test_best(rng, want):
    got = Range(rng).best(VERSIONS)
    assert (str(got) if got else None) == want


def test_prerelease_needs_opt_in():
    assert Range("^2.0.0-beta").best(VERSIONS) == v("2.0.0")
    assert Range("^1.0").best(VERSIONS, allow_pre=True) == v("1.2.5")
    assert Range(">=2.1.0-rc.1").matches(v("2.1.0-rc.1"))


def test_ordering():
    assert v("1.0.0-alpha") < v("1.0.0-alpha.1") < v("1.0.0-beta") < v("1.0.0")
    assert v("v1.2") == v("1.2.0")
    assert v("v.1.0.0") == v("1.0.0")
    assert v("ver.1.3") == v("1.3.0")
    assert v("release-2.0.1") == v("2.0.1")
    assert str(v("1.2.3-rc.1+abc")) == "1.2.3-rc.1+abc"


def test_bad():
    assert Version.try_parse("main") is None
    with pytest.raises(ValueError):
        Range("banana")
