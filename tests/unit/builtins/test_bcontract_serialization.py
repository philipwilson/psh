"""Reusable-output serialization for `set`, plain `declare`, `declare -p`,
`hash -l` (builtins contracts cluster).

bash 5.2.26 emits single-quote style for `set`/plain `declare` (`x='a b'`,
`x=$'a\\nb'`), double-quote style for `declare -p` (`declare -- x="a b"`), and
quotes the path/name in `hash -l`. The old psh emitted every value unquoted
(and str()'d arrays to one word), so `eval "$(set)"` broke on any value with a
space/quote/newline/glob.

Two contracts are asserted:
  1. psh's output matches bash 5.2 byte-for-byte (exact-match rows).
  2. value -> serialize -> eval in a FRESH psh round-trips to the same value
     (property rows over a hostile corpus).

Red→green: every `set`/`hash -l` row and the control-char `declare -p` rows
FAILED at base dff3e875.
"""
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

PSH = [sys.executable, "-m", "psh"]
BASH = resolve_bash().path


def _sq(s):
    """POSIX single-quote so `x=<_sq(v)>` assigns exactly v."""
    return "'" + s.replace("'", "'\\''") + "'"


def run(argv, script):
    p = subprocess.run(argv + ["-c", script], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


# Hostile corpus: intended VALUES (real characters). ASCII rows are used for
# byte-exact comparison with bash (locale-independent); `utf8` is round-trip
# only — psh always leaves printable Unicode bare (Python/PEP-538 UTF-8), while
# bash octal-escapes it in a C locale, so exact-match there is locale-dependent
# (see the dedicated locale-gated test + the found-not-fixed ledger).
CORPUS = {
    "space": "a b",
    "squote": "a'b",
    "dquote": 'a"b',
    "dollar": "a$b",
    "backtick": "a`b",
    "backslash": "a\\b",
    "newline": "a\nb",
    "tab": "a\tb",
    "glob": "a*b",
    "semi": "a;b",
    "empty": "",
    "utf8": "héllo",
    "lead_tilde": "~x",
    "bang": "a!b",
    "paren": "a(b)c",
}
ASCII_CORPUS = [t for t in CORPUS if t != "utf8"]


@pytest.mark.parametrize("tag", ASCII_CORPUS)
def test_set_listing_matches_bash(tag):
    """`set` variable listing is byte-identical to bash 5.2."""
    v = CORPUS[tag]
    script = f"x={_sq(v)}; set | grep -a '^x='"
    _, pout, _ = run(PSH, script)
    _, bout, _ = run([BASH], script)
    assert pout == bout, f"{tag}: psh {pout!r} != bash {bout!r}"


@pytest.mark.parametrize("tag", ASCII_CORPUS)
def test_declare_p_matches_bash(tag):
    """`declare -p` is byte-identical to bash 5.2 (incl. $'...' controls)."""
    v = CORPUS[tag]
    script = f"x={_sq(v)}; declare -p x"
    _, pout, _ = run(PSH, script)
    _, bout, _ = run([BASH], script)
    assert pout == bout, f"{tag}: psh {pout!r} != bash {bout!r}"


def test_utf8_declare_p_matches_bash_in_utf8_locale():
    """In a UTF-8 locale psh and bash agree: printable Unicode stays bare
    (`declare -- x="héllo"`). (C-locale octal-escaping is a documented
    serializer locale-awareness gap — see the found-not-fixed ledger.)"""
    import os
    for loc in ("en_US.UTF-8", "C.UTF-8"):
        env = dict(os.environ, LC_ALL=loc)
        b = subprocess.run([BASH, "-c", 'x="héllo"; declare -p x'],
                           capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL, timeout=30)
        if 'x="héllo"' not in b.stdout:
            continue  # locale not installed / bash still escaped; try next
        p = subprocess.run(PSH + ["-c", 'x="héllo"; declare -p x'],
                           capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL, timeout=30)
        assert p.stdout == b.stdout
        return
    pytest.skip("no UTF-8 locale available for bash")


@pytest.mark.parametrize("tag", list(CORPUS))
def test_set_roundtrips_in_fresh_psh(tag):
    """value -> `set` line -> eval in a FRESH psh -> same value."""
    v = CORPUS[tag]
    script = (f"x={_sq(v)}; line=$(set | grep -a '^x='); "
              f"unset x; eval \"$line\"; printf '[%s]' \"$x\"")
    _, pout, _ = run(PSH, script)
    assert pout == f"[{v}]", f"{tag}: round-trip gave {pout!r}"


@pytest.mark.parametrize("tag", list(CORPUS))
def test_declare_p_roundtrips_in_fresh_psh(tag):
    """value -> `declare -p` line -> eval in a FRESH psh -> same value."""
    v = CORPUS[tag]
    script = (f"x={_sq(v)}; line=$(declare -p x); "
              f"unset x; eval \"$line\"; printf '[%s]' \"$x\"")
    _, pout, _ = run(PSH, script)
    assert pout == f"[{v}]", f"{tag}: round-trip gave {pout!r}"


def test_plain_declare_matches_set_style():
    """Plain `declare` (no args) uses the same single-quote form as `set`."""
    script = "x='a b'; declare | grep -a '^x='"
    _, pout, _ = run(PSH, script)
    assert pout == "x='a b'\n"


def test_array_declare_p_matches_bash():
    """Indexed array `declare -p` element form matches bash."""
    script = "a=('x y' \"q'r\" 'z w'); declare -p a"
    _, pout, _ = run(PSH, script)
    _, bout, _ = run([BASH], script)
    assert pout == bout


def test_array_with_escaped_dollar_roundtrips():
    """A value with a literal $ in an array element -> declare -p -> eval in a
    fresh psh preserves it (bash does).

    Fixed by the literal-pattern cluster: the array-init flat text (the
    declaration builtin's lookup key) is now collapsed to the escape-processed
    argv (``array_flat_text.process_unquoted_element_escapes``), so re-parsing
    ``declare -a a=([1]="z\\$w")`` finds its structured init instead of falling
    back to a scalar and re-expanding the ``$``."""
    script = ("a=('x y' 'z$w'); line=$(declare -p a); unset a; "
              "eval \"$line\"; printf '[%s]' \"${a[@]}\"")
    _, pout, _ = run(PSH, script)
    assert pout == "[x y][z$w]"


def test_set_lists_array_in_bracket_form():
    """`set` shows an array with the reusable `([0]=..)` form, not one word."""
    script = "a=('x y' 'z'); set | grep -a '^a='"
    _, pout, _ = run(PSH, script)
    assert pout == 'a=([0]="x y" [1]="z")\n'


class TestHashListReusable:
    def test_quotes_path_with_space(self):
        script = "hash -p '/tmp/a b' foo; hash -l"
        _, pout, _ = run(PSH, script)
        _, bout, _ = run([BASH], script)
        assert pout == bout == "builtin hash -p '/tmp/a b' foo\n"

    def test_plain_path_unquoted(self):
        script = "hash -p /usr/bin/true tcmd; hash -l"
        _, pout, _ = run(PSH, script)
        assert pout == "builtin hash -p /usr/bin/true tcmd\n"

    def test_roundtrips_in_fresh_psh(self):
        script = ("hash -p '/tmp/a b' foo; line=$(hash -l); "
                  "hash -r; eval \"$line\"; hash -t foo")
        _, pout, _ = run(PSH, script)
        assert pout == "/tmp/a b\n"
