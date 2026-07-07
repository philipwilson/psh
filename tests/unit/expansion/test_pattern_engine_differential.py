"""Pattern-engine differential battery: psh vs live bash, bash as the oracle.

This is the BEHAVIOR LOCK for the compiled pattern engine (expansion appraisal
finding #6). It exercises all five shell-pattern consumers — ``case``,
``[[ string == pattern ]]``, ``${var#/%/##/%%}`` removal, ``${var/}`` /
``${var//}`` substitution, and pathname expansion — across the full syntax
matrix (plain globs, ranges, POSIX classes, all five extglob operators,
negation, nested extglob, quoted/literal metacharacters, bracket sets holding
metacharacters, empty patterns, anchoring) and compares psh output against
bash 5.x row by row. Any UNEXPECTED divergence fails the suite; the two known
pre-existing quirks are listed in ``KNOWN_DIVERGENCES`` and asserted stable.

The rows are batched into ONE script per bucket and each shell is spawned once
per bucket (fast, truly differential). It is designed to pass UNCHANGED before
and after the engine flip — proving the reroute is behaviour-preserving.
"""
import os
import shutil
import subprocess
import sys

import pytest


def _find_bash():
    if "BASH_PATH" in os.environ and os.access(os.environ["BASH_PATH"], os.X_OK):
        return os.environ["BASH_PATH"]
    for p in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("bash")


BASH = _find_bash()
PSH = [sys.executable, "-m", "psh"]

pytestmark = pytest.mark.skipif(BASH is None, reason="bash oracle not available")


# (id, subject, pattern, quoted). quoted=True wraps the pattern in double quotes
# at each use site so its metacharacters are literal — the real-world way
# escapes reach the matcher (the literal `case ... a\[b)` syntax hits a separate
# PARSER limitation, tracked out of scope for the pattern-matching engine).
ROWS = [
    ("plain1", "abc", "a*", False), ("plain2", "abc", "*c", False),
    ("plain3", "abc", "a?c", False), ("plain4", "abc", "abc", False),
    ("plain5", "", "*", False), ("plain6", "", "?", False),
    ("plain7", "a/b", "a*b", False), ("plain8", "abc", "*", False),
    ("plain9", "abc", "a*c", False), ("plain10", "aXbXc", "a*c", False),
    ("rng1", "b", "[a-c]", False), ("rng2", "d", "[a-c]", False),
    ("rng3", "b", "[!a-c]", False), ("rng4", "B", "[a-c]", False),
    ("rng5", "5", "[0-9]", False), ("rng6", "b", "[^a-c]", False),
    ("rng7", "-", "[a-]", False), ("rng8", "a", "[]a]", False),
    ("rng9", "]", "[]a]", False), ("rng10", "z", "[z-a]", False),
    ("cls1", "a", "[[:alpha:]]", False), ("cls2", "5", "[[:digit:]]", False),
    ("cls3", "a", "[[:digit:]]", False), ("cls4", "A", "[[:upper:]]", False),
    ("cls5", "a", "[[:lower:]]", False), ("cls6", " ", "[[:space:]]", False),
    ("cls7", "!", "[[:punct:]]", False), ("cls8", "f", "[[:xdigit:]]", False),
    ("cls9", "abc", "[[:alpha:]]*", False),
    ("cls10", "a1", "[[:alpha:]][[:digit:]]", False),
    ("cls11", "x", "[![:digit:]]", False),
    ("at1", "abc", "a@(b|x)c", False), ("at2", "axc", "a@(b|x)c", False),
    ("at3", "ayc", "a@(b|x)c", False), ("at4", "abbc", "a@(b|bb)c", False),
    ("q1", "ac", "a?(b)c", False), ("q2", "abc", "a?(b)c", False),
    ("q3", "abbc", "a?(b)c", False), ("q4", "", "?(x)", False),
    ("star1", "ac", "a*(b)c", False), ("star2", "abbbc", "a*(b)c", False),
    ("star3", "abxbc", "a*(b)c", False), ("star4", "aaa", "*(a)", False),
    ("star5", "aaab", "*(a)", False),
    ("plus1", "ac", "a+(b)c", False), ("plus2", "abc", "a+(b)c", False),
    ("plus3", "abbbc", "a+(b)c", False), ("plus4", "aaa", "+(a)", False),
    ("neg1", "abc", "!(abc)", False), ("neg2", "abd", "!(abc)", False),
    ("neg3", "foo", "!(*.txt)", False), ("neg4", "a.txt", "!(*.txt)", False),
    ("neg5", "abc", "a!(x)c", False), ("neg6", "axc", "a!(x)c", False),
    ("neg7", "", "!(x)", False),
    ("nest1", "abcabc", "*(a@(b)c)", False),
    ("nest2", "abab", "+(@(a|b))", False),
    ("nest3", "xy", "@(x|@(y|z))y", False),
    ("nest4", "aabb", "*(a)*(b)", False), ("nest5", "abab", "*(ab)", False),
    ("qm1", "a*b", "a*b", True), ("qm2", "axb", "a*b", True),
    ("qm3", "a?b", "a?b", True), ("qm4", "a[b", "a[b", True),
    ("qm5", "a(b", "a(b", True), ("qm6", "a|b", "a|b", True),
    ("qm7", "abc", "a?b", True),
    ("brk1", "*", "[*?]", False), ("brk2", "a", "[*?]", False),
    ("brk3", "-", "[-a]", False), ("brk4", "^", "[a^]", False),
    ("brk5", "!", "[a!]", False),
    ("emp1", "", "", True), ("emp2", "x", "", True), ("emp3", "", "abc", False),
    ("anc1", "abcdef", "abc*", False), ("anc2", "abcdef", "*def", False),
    ("anc3", "abcdef", "*cd*", False),
]

# Pre-existing psh<->bash divergences NOT introduced by the engine work. Excluded
# from the equality lock and asserted stable so a regression here is still caught.
KNOWN_DIVERGENCES = {
    # Empty-subject zero-width substitution quirk (PRE-EXISTING; confirmed on
    # base main b3f18815 before this campaign). On an EMPTY subject bash
    # suppresses the zero-width match for a zero-width-capable extglob group in
    # the unanchored (${x/}, ${x//}) and prefix-anchored (${x/#}) substitution
    # forms; psh emits it. Not derivable from the match extent -- the matcher
    # returns the correct reachable-end set {0}, and the SUFFIX form (${x/%})
    # already matches bash, so this is a bash operator-and-anchor-specific empty
    # quirk, left as-is (out of scope for the pattern-engine work).
    "q4_sub1", "q4_sub2", "q4_sub3", "neg7_sub3",
}


def _shq(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _pat(pat, quoted):
    return f'"{pat}"' if quoted else pat


def _render(rid, subj, pat, quoted):
    p = _pat(pat, quoted)
    return [
        f"s={_shq(subj)}; case \"$s\" in {p}) echo '{rid}_case=Y';; "
        f"*) echo '{rid}_case=N';; esac",
        f"s={_shq(subj)}; if [[ \"$s\" == {p} ]]; then echo '{rid}_dbr=Y'; "
        f"else echo '{rid}_dbr=N'; fi",
        f"s={_shq(subj)}; printf '{rid}_rem1=%s\\n' \"${{s#{p}}}\"; "
        f"printf '{rid}_rem2=%s\\n' \"${{s##{p}}}\"; "
        f"printf '{rid}_rem3=%s\\n' \"${{s%{p}}}\"; "
        f"printf '{rid}_rem4=%s\\n' \"${{s%%{p}}}\"",
        f"s={_shq(subj)}; printf '{rid}_sub1=%s\\n' \"${{s/{p}/Z}}\"; "
        f"printf '{rid}_sub2=%s\\n' \"${{s//{p}/Z}}\"; "
        f"printf '{rid}_sub3=%s\\n' \"${{s/#{p}/Z}}\"; "
        f"printf '{rid}_sub4=%s\\n' \"${{s/%{p}/Z}}\"",
    ]


def _run(shell, script, env_extra=None, cwd=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    sh = shell if isinstance(shell, list) else [shell]
    return subprocess.run(sh + ["-c", script], capture_output=True, text=True,
                          env=env, cwd=cwd, stdin=subprocess.DEVNULL, timeout=90)


def _tags(out):
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def _compare(script, env_extra=None, cwd=None):
    """Run script in bash and psh; return (bash_tags, psh_tags, unexpected)."""
    b = _run(BASH, script, env_extra, cwd)
    p = _run(PSH, script, env_extra, cwd)
    bt, pt = _tags(b.stdout), _tags(p.stdout)
    unexpected = [(k, bt.get(k), pt.get(k)) for k in bt
                  if bt.get(k) != pt.get(k) and k not in KNOWN_DIVERGENCES]
    return bt, pt, unexpected


def test_string_consumers_match_bash():
    """case / [[ == ]] / ${#} removal / ${/} substitution match bash (C locale)."""
    lines = ["shopt -s extglob"]
    for rid, subj, pat, quoted in ROWS:
        lines += _render(rid, subj, pat, quoted)
    script = "\n".join(lines) + "\n"
    bt, pt, unexpected = _compare(script, env_extra={"LC_ALL": "C"})
    assert bt, "bash produced no tagged output"
    assert not unexpected, "psh diverges from bash on: " + "; ".join(
        f"{k}: bash={b!r} psh={p!r}" for k, b, p in unexpected)
    # The documented quirks must still be present (and still divergent).
    for k in KNOWN_DIVERGENCES:
        assert k in bt


def test_known_divergences_are_still_divergent():
    """Pin that the documented quirks remain exactly as documented.

    If a future change accidentally *fixes* one, this fails loudly so the
    KNOWN_DIVERGENCES list (and the campaign's found-not-fixed record) is
    updated deliberately rather than drifting silently.
    """
    script = ("shopt -s extglob\n"
              "s=''; printf 'q4_sub1=%s\\n' \"${s/?(x)/Z}\"\n"
              "s=''; printf 'q4_sub2=%s\\n' \"${s//?(x)/Z}\"\n"
              "s=''; printf 'q4_sub3=%s\\n' \"${s/#?(x)/Z}\"\n"
              "s=''; printf 'neg7_sub3=%s\\n' \"${s/#!(x)/Z}\"\n"
              # The SUFFIX form is NOT part of the quirk: bash and psh agree.
              "s=''; printf 'q4_sub4=%s\\n' \"${s/%?(x)/Z}\"\n")
    bt = _tags(_run(BASH, script, {"LC_ALL": "C"}).stdout)
    pt = _tags(_run(PSH, script, {"LC_ALL": "C"}).stdout)
    for k in ("q4_sub1", "q4_sub2", "q4_sub3", "neg7_sub3"):
        assert bt.get(k) == "" and pt.get(k) == "Z", k
    assert bt.get("q4_sub4") == "Z" and pt.get("q4_sub4") == "Z"


# Pathname (glob) fileset: no case-colliding names (APFS is case-insensitive).
_GLOB_FILES = ["abc", "abd", "axc", "a.txt", "b.txt", "xyz", "a1", "9x", ".hidden"]
_GLOB_DIRS = ["sub"]
_GLOB_SUBFILES = {"sub": ["deep.txt", "inner"]}
_GLOB_PATTERNS = [
    "a*", "*.txt", "a?c", "[ab]*", "[[:alpha:]]*", "[[:digit:]]*",
    "a@(bc|xc)", "!(*.txt)", "+(a)*", "?(a)bc", "*[0-9]", "[!a]*",
    "sub/*", "sub/*.txt", "nomatch*",
]


@pytest.fixture()
def _glob_dir(tmp_path):
    for name in _GLOB_FILES:
        (tmp_path / name).write_text("x")
    for d in _GLOB_DIRS:
        (tmp_path / d).mkdir()
        for f in _GLOB_SUBFILES.get(d, []):
            (tmp_path / d / f).write_text("x")
    return str(tmp_path)


def test_pathname_expansion_matches_bash(_glob_dir):
    """Pathname expansion (incl. extglob components, classes, ordering) == bash.

    Compares the fully expanded, collation-ordered result of ``echo <pat>`` for
    each pattern; an unmatched pattern stays literal in both shells (nullglob
    off), so the raw output is directly comparable.
    """
    lines = ["shopt -s extglob"]
    for i, pat in enumerate(_GLOB_PATTERNS):
        lines.append(f"printf 'g{i}=[%s]\\n' \"$(echo {pat})\"")
    script = "\n".join(lines) + "\n"
    bt, pt, unexpected = _compare(script, env_extra={"LC_ALL": "C"},
                                  cwd=_glob_dir)
    assert bt
    assert not unexpected, "glob diverges from bash on: " + "; ".join(
        f"{k}: bash={b!r} psh={p!r}" for k, b, p in unexpected)


# --- UTF-8 locale rows: pin that v0.655 class semantics are host-faithful -----
_UTF8_CLASS_ROWS = [
    ("u_alpha_e", "é", "[[:alpha:]]"), ("u_alpha_zh", "中", "[[:alpha:]]"),
    ("u_upper_E", "É", "[[:upper:]]"), ("u_lower_e", "é", "[[:lower:]]"),
    ("u_alnum_e", "é", "[[:alnum:]]"), ("u_alpha_a", "a", "[[:alpha:]]"),
    ("u_digit_3", "3", "[[:digit:]]"),
]


def _utf8_available():
    import locale as _locale
    saved = _locale.setlocale(_locale.LC_CTYPE)
    try:
        _locale.setlocale(_locale.LC_CTYPE, "en_US.UTF-8")
        return True
    except _locale.Error:
        return False
    finally:
        _locale.setlocale(_locale.LC_CTYPE, saved)


@pytest.mark.skipif(not _utf8_available(),
                    reason="en_US.UTF-8 locale not available on this host")
@pytest.mark.parametrize("loc", ["C", "en_US.UTF-8"])
def test_posix_class_semantics_match_bash_by_locale(loc):
    """POSIX classes in [[ == ]] and case match host bash under C and UTF-8.

    Locks the v0.655 locale-class behaviour end to end: under C the non-ASCII
    subjects do not match [[:alpha:]] etc.; under en_US.UTF-8 they do — in both
    shells. The engine flip must preserve this per-locale membership exactly.
    """
    lines = []
    for rid, subj, pat in _UTF8_CLASS_ROWS:
        lines.append(
            f"s={_shq(subj)}; if [[ \"$s\" == {pat} ]]; then echo '{rid}=Y'; "
            f"else echo '{rid}=N'; fi")
    script = "\n".join(lines) + "\n"
    bt, pt, unexpected = _compare(script, env_extra={"LC_ALL": loc})
    assert bt
    assert not unexpected, f"[{loc}] class semantics diverge: " + "; ".join(
        f"{k}: bash={b!r} psh={p!r}" for k, b, p in unexpected)
