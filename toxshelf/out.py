import os
import sys

_color = None


def color():
    global _color
    if _color is None:
        _color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        if _color and os.name == "nt":
            try:
                import ctypes

                k = ctypes.windll.kernel32
                h = k.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                if k.GetConsoleMode(h, ctypes.byref(mode)):
                    k.SetConsoleMode(h, mode.value | 0x0004)
            except Exception:
                _color = False
    return _color


def _wrap(code, s):
    return f"\033[{code}m{s}\033[0m" if color() else str(s)


def bold(s):
    return _wrap("1", s)


def dim(s):
    return _wrap("2", s)


def green(s):
    return _wrap("32", s)


def yellow(s):
    return _wrap("33", s)


def red(s):
    return _wrap("31", s)


def cyan(s):
    return _wrap("36", s)


def say(*parts):
    print(" ".join(str(p) for p in parts))


def note(msg):
    print(dim(msg), file=sys.stderr)


def warn(msg):
    print(yellow("! ") + str(msg), file=sys.stderr)


def fail(msg, hint=None):
    print(red("x ") + str(msg), file=sys.stderr)
    if hint:
        print(dim("  " + hint), file=sys.stderr)


def table(rows, headers=None):
    rows = [[str(c) for c in r] for r in rows]
    if headers:
        rows = [list(headers)] + rows
    if not rows:
        return
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for n, r in enumerate(rows):
        line = "  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip()
        print(bold(line) if headers and n == 0 else line)
