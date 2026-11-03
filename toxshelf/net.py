import json
import os
import time
import urllib.error
import urllib.request

from . import __version__
from .errors import ShelfError
from .paths import load_config

UA = f"tox-shelf/{__version__}"


def _token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or load_config().get("token") or ""


def get(url, headers=None, timeout=60, tries=3, what=None):
    h = {"User-Agent": UA}
    if "api.github.com" in url:
        h["Accept"] = "application/vnd.github+json"
        tok = _token()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
    if headers:
        h.update(headers)
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or (e.code == 401 and "github.com/" in url and ".git/" in url):
                raise ShelfError(f"couldn't find {what or url}", "check the spelling, or the repo might be private")
            if e.code in (401, 403) and "api.github.com" in url:
                left = e.headers.get("X-RateLimit-Remaining")
                if left == "0":
                    raise ShelfError(
                        "github rate limit hit",
                        "set a token with `shelf config set token <your token>` or the GITHUB_TOKEN env var",
                    )
                raise ShelfError(f"github said no ({e.code}) for {what or url}")
            if e.code < 500 and e.code != 429:
                raise ShelfError(f"{e.code} from {url}")
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(0.6 * (attempt + 1))
    reason = getattr(last, "reason", last)
    raise ShelfError(f"couldn't reach {url} ({reason})", "check your internet connection")


def get_json(url, **kw):
    data = get(url, **kw)
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        raise ShelfError(f"got garbage back from {url}")
