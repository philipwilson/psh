"""Byte-identity characterization corpus for ``HistoryExpander.expand_history``.

This is the safety net for the H22 scanner decomposition (reappraisal #19,
slot B6): the ``expand_history`` scanner was rewritten from three per-``!``
*backward* rescans (bracket / ``${...}`` / ``$((...))`` context detection) into
a single forward pass tracking those depths incrementally. The rewrite is a
**pure refactor** — it must produce byte-for-byte identical output to the
pre-refactor code on every input, warts included.

The golden file (``fixtures/history_expansion/corpus_golden.json``) captures the
exact ``(result, stderr, print_only_stdout)`` triple of the ORIGINAL scanner for
every corpus input against a seeded history. It was generated from the pre-B6
tree and is frozen; the test below re-runs the CURRENT ``expand_history`` and
asserts it still matches. Any divergence is a byte-identity regression.

Regenerate the golden (only when a behavior change is deliberate and reviewed)::

    python tests/unit/interactive/test_history_expansion_corpus.py

The corpus combines:
  * every history-expansion input exercised elsewhere in the suite (event
    designators, word designators, ``:h/:t/:r/:e/:s/:g&/:p`` modifiers,
    ``^old^new`` quick substitution, error cases);
  * the appraisal's nesting cases (``${!x}``-lookalikes, ``$((!x))``, ``[!a]``,
    quoted ``!`` in single and double quotes, ``!!``/``!n``/``!-n``/``!?str?``,
    backslash-escaped ``!``, ``!`` at EOL / before space/=/(, ``${arr[!i]}``,
    brace ``{a,!b}``);
  * adversarial state cases (unbalanced quotes/brackets/braces/parens, ``!``
    inside heredoc-looking text, brackets/braces/parens inside quotes and after
    backslashes — the cases that discriminate a quote-respecting rewrite from
    the original's quote-blind backward scans);
  * an exhaustive combinatorial sweep of all strings up to length 3 over the
    metacharacter alphabet, so structural interactions are covered mechanically.
"""

import contextlib
import io
import json
from itertools import product
from pathlib import Path

import pytest

from psh.shell import Shell

GOLDEN_PATH = (Path(__file__).parent / "fixtures" / "history_expansion"
               / "corpus_golden.json")

# ---------------------------------------------------------------------------
# Seeded histories (referenced by key so the golden stays readable).
# ---------------------------------------------------------------------------
HISTORIES = {
    "abg": ["echo alpha beta gamma"],
    "multi": ["ls /usr/bin", "grep foo bar.txt baz.txt", "cat a.c b.c"],
    "path1": ["cat /a/b/c.txt"],
    "path2": ["cat /p/q/r.tar.gz"],
    "sub_foo": ["echo foo boo"],
    "sub_hello": ["echo hello world"],
    "sub_aa": ["echo aa aa aa"],
    "prev": ["echo prev cmd"],
    "quoted": ["echo 'quoted arg' last"],
    "two": ["echo one two three", "echo aaa bbb"],
    "empty": [],
    "true": ["true"],
    "longpath": ["ls /some/long/path"],
    "dotfiles": ["echo .bashrc", "echo a.b.c"],
    "onetwothree": ["one two three"],
    "make": ["make build"],
    "echo_x": ["ECHO x"],
    # A history entry whose text itself contains metacharacters, so an
    # expansion inserts brackets/braces into `result` (does NOT affect the
    # raw-prefix scanner, but pins the emit path).
    "brackety": ["echo [x] {y} (z)"],
    # Combinatorial sweep history: multi-word so !!, !x, word designators and
    # modifiers all have something to resolve against.
    "cb": ["ab cd ef"],
}

# ---------------------------------------------------------------------------
# Hand-enumerated cases: (history_key, command).
# ---------------------------------------------------------------------------
HAND_CASES = [
    # --- Event designators (from conformance + word-designator suites) ---
    ("abg", "!!"),
    ("multi", "!1"), ("multi", "!3"), ("multi", "!-1"), ("multi", "!-3"),
    ("multi", "!ls"), ("multi", "!grep"), ("multi", "!?foo?"),
    ("two", "!1:$"), ("two", "!1:^"), ("two", "!1:2"), ("two", "!echo:^"),
    ("two", "!-2:2"), ("two", "!-1:$"),
    ("prev", "echo !!"), ("make", "sudo !!"),
    # --- Word designators on !! ---
    ("abg", "!!:0"), ("abg", "!!:1"), ("abg", "!!:2"), ("abg", "!!:3"),
    ("abg", "!!:$"), ("abg", "!!:^"), ("abg", "!!:*"),
    ("abg", "!!:1-2"), ("abg", "!!:2-"), ("abg", "!!:2*"), ("abg", "!!:1-$"),
    ("abg", "!$"), ("abg", "!^"), ("abg", "!*"),
    ("abg", "!:0"), ("abg", "!:1"), ("abg", "!:$"),
    ("abg", "!!:-0"), ("abg", "!!:-1"), ("abg", "!!:-2"), ("abg", "!!:-3"),
    ("abg", "!!:-$"),
    ("multi", "!grep:2"), ("multi", "!grep:$"),
    ("longpath", "!$"),
    ("abg", "echo !$"), ("true", "echo X!$Y"),
    ("true", "echo pre !* post"), ("true", "echo !$"), ("true", "echo !^"),
    ("quoted", "echo !:1"), ("quoted", "echo !:2"), ("quoted", "echo !$"),
    # --- Bad word specifiers / out of range ---
    ("true", "echo !!:5"), ("true", "echo !!:1-9"), ("true", "echo !!:2-1"),
    ("abg", "echo !!:5"), ("abg", "!!:9"), ("onetwothree", "!!:5"),
    # --- Modifiers :h :t :r :e (+ chaining) ---
    ("path1", "!!:h"), ("path1", "!!:t"), ("path1", "!!:r"), ("path1", "!!:e"),
    ("path1", "!!:$:h"), ("path1", "!!:$:t"),
    ("path2", "!!:$:r"), ("path2", "!!:$:e"),
    ("path1", "!!:t:r"),
    ("dotfiles", "!!:r"), ("dotfiles", "!!:e"),
    # --- Modifiers :s / :gs / :& / :p ---
    ("sub_foo", "!!:s/o/0/"), ("sub_foo", "!!:gs/o/0/"), ("sub_foo", "!!:s|o|0|"),
    ("sub_foo", "!!:s/foo/X/"), ("sub_foo", "!!:1:s/o/0/"),
    ("sub_foo", "!!:s/o/0/:gs/0/Z/"),
    ("sub_hello", "!!:s/hello/goodbye/"), ("sub_aa", "!!:gs/aa/bb/"),
    ("onetwothree", "!!:s/two/2/:s/three/3/"),
    ("sub_foo", "!!:s/o/0/ then !!:&"),
    ("abg", "!!:p"), ("abg", "!!:Z"),
    ("abg", "!!:s/NOPE/X/"),
    # --- Quick substitution ^old^new ---
    ("sub_foo", "^o^0"), ("sub_foo", "^o^0^"), ("sub_foo", "^foo^bar"),
    ("sub_hello", "^hello^goodbye"), ("echo_x", "^ECHO^echo"),
    ("sub_foo", "^^"), ("sub_foo", "^nomatch^x"), ("empty", "^o^0"),
    ("sub_foo", "^o^0^extra"),
    # --- Quoting: single quotes suppress, double quotes do not ---
    ("prev", "echo \"see !!\""), ("prev", "echo \"x !! y\""),
    ("prev", "echo \"it's !!\""), ("prev", "echo '!!'"),
    ("prev", "echo \\!!"), ("prev", "echo \\!foo"), ("prev", "echo \"a\\!b\""),
    ("prev", "a!=b"), ("prev", "echo \"${x} !!\""),
    ("abg", "echo 'literal !!'"), ("abg", "echo a!=b"),
    ("abg", "[[ ! -f x ]]"), ("multi", "[[ ! -f x ]]"),
    ("abg", "echo '!$'"), ("abg", "a!=b"), ("abg", "[[ ! x ]]"),
    ("abg", "echo hi!"),
    # --- Nesting cases (appraisal): ${...} lookalikes ---
    ("prev", "${!x}"), ("prev", "echo ${!x}"), ("prev", "echo ${!x} !!"),
    ("prev", "${!x} !!"), ("prev", "${x!!y}"), ("prev", "echo ${x} !!"),
    ("prev", "${arr[!i]}"), ("prev", "echo ${arr[!i]} !!"),
    ("prev", "echo ${x[!i]}"),
    # --- Nesting cases: $((...)) arithmetic ---
    ("prev", "$((!x))"), ("prev", "echo $((!x))"), ("prev", "$(( !x ))"),
    ("prev", "echo $(( !x )) !!"), ("prev", "$((5 != 3))"),
    ("prev", "echo $((a!=b))"), ("prev", "$(( a != b )) !!"),
    ("prev", "echo $((1+1)) !!"), ("prev", "$(($(($x)) !! ))"),
    # --- Nesting cases: [...] bracket globs ---
    ("prev", "[!a]"), ("prev", "echo [!abc]"), ("prev", "echo x[!a]z"),
    ("prev", "ls [!a] !!"), ("prev", "echo [abc] !!"), ("prev", "[a-z]!!"),
    ("prev", "echo x[!a]z !!"),
    # --- Nesting cases: brace lists ---
    ("prev", "{a,!b}"), ("prev", "echo {a,!b}"), ("prev", "echo {a,!b} !!"),
    # --- Backslash escapes ---
    ("prev", "\\!"), ("prev", "\\!!"), ("prev", "echo \\!x"),
    ("prev", "a\\!b !!"), ("prev", "\\!! !!"),
    # --- ! at EOL / before space, =, ( ---
    ("prev", "!"), ("prev", "foo!"), ("prev", "! foo"), ("prev", "echo ! x"),
    ("prev", "a!(b"), ("prev", "foo !( bar"), ("prev", "!="),
    ("prev", "echo hi! there"), ("prev", "!!!"), ("prev", "!! !!"),
    # --- Adversarial: unbalanced quotes ---
    ("prev", "echo 'unclosed"), ("prev", "echo \"unclosed !!"),
    ("prev", "echo 'unclosed !!"), ("prev", "'!!"), ("prev", "\"!!"),
    ("prev", "echo \"a'b !!\""),
    # --- Adversarial: unbalanced brackets/braces/parens (quote-blind) ---
    ("prev", "echo [ !!"), ("prev", "echo ] !!"), ("prev", "echo ][ !!"),
    ("prev", "echo ${ !!"), ("prev", "echo } !!"), ("prev", "echo }{ !!"),
    ("prev", "echo $(( !!"), ("prev", "echo )) !!"), ("prev", "echo )( !!"),
    ("prev", "[!!"), ("prev", "${!!"), ("prev", "$((!!"),
    ("prev", "echo [a]!!"), ("prev", "echo [a] !!"),
    ("prev", "echo ${x}!!"), ("prev", "echo $((x))!!"),
    # --- Discriminators: metachars INSIDE quotes / after backslash, then a
    #     later unquoted !.  The original scanner is quote-blind on these. ---
    ("cb", "'[' !!"), ("cb", "'[' !a"), ("cb", "\"[\" !!"),
    ("cb", "'${' !!"), ("cb", "'}' !!"), ("cb", "'$((' !!"),
    ("cb", "'))' !!"), ("cb", "\\[ !!"), ("cb", "\\${ !!"),
    ("cb", "']' '[' !!"), ("cb", "'[]' !!"), ("cb", "'[' ']' !!"),
    ("cb", "echo '[x]' !!"), ("cb", "echo \"[x]\" !!"),
    # --- ! inside heredoc-looking text (psh scans the whole string) ---
    ("prev", "cat <<EOF"), ("prev", "cat <<EOF\n!!\nEOF"),
    ("prev", "cat <<'EOF'\n!!\nEOF"),
    # --- Embedded / multiple refs on one line ---
    ("abg", "echo !$ and !^"), ("multi", "!1 !2 !3"),
    ("prev", "!! !! !!"), ("abg", "x!$y!^z"),
    # --- histexpand off path is tested separately; here everything on ---
    ("empty", "!!"), ("empty", "!1"), ("abg", "!nonexistent"),
    ("brackety", "!!"), ("brackety", "!! !!"), ("brackety", "echo !$"),
]

# ---------------------------------------------------------------------------
# Combinatorial sweep: all strings length 1..3 over the metacharacter alphabet,
# run against a fixed multi-word history.  Mechanically covers structural
# interactions the hand cases might miss.
# ---------------------------------------------------------------------------
_ALPHABET = ["!", "'", '"', "\\", "[", "]", "{", "}", "(", ")", "$", "a", " "]


def _combinatorial_cases():
    cases = []
    for length in (1, 2, 3):
        for combo in product(_ALPHABET, repeat=length):
            cases.append(("cb", "".join(combo)))
    return cases


CORPUS = HAND_CASES + _combinatorial_cases()


# ---------------------------------------------------------------------------
# Capture harness: the exact observable outputs of one expand_history call.
# ---------------------------------------------------------------------------
def _capture(expander, history, command):
    """Return ``{result, stderr, pstdout}`` for one expand_history call.

    ``result`` is the return value (expanded string, ``None`` on error, ``''``
    for a ``:p`` print-only expansion, or ``"<EXC:...>"`` if it raised).
    ``stderr`` is the error text (``report_errors=True``).  ``pstdout`` is what
    a ``:p`` modifier printed to ``shell.stdout``.
    """
    expander.state.history[:] = list(history)
    expander._last_sub = None
    expander._print_only = False
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    saved_stdout = expander.shell.stdout
    expander.shell.stdout = buf_out
    try:
        with contextlib.redirect_stderr(buf_err):
            result = expander.expand_history(
                command, print_expansion=False, report_errors=True)
    except Exception as exc:  # pragma: no cover - defensive; frozen if it fires
        result = f"<EXC:{type(exc).__name__}:{exc}>"
    finally:
        expander.shell.stdout = saved_stdout
    return {"result": result, "stderr": buf_err.getvalue(),
            "pstdout": buf_out.getvalue()}


def _make_expander():
    shell = Shell(norc=True)
    shell.state.options["histexpand"] = True
    return shell.history_expander


def _run_corpus():
    """Capture every corpus case against the current expand_history."""
    expander = _make_expander()
    out = []
    for hist_key, command in CORPUS:
        out.append(_capture(expander, HISTORIES[hist_key], command))
    return out


def _load_golden():
    with open(GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("idx", range(len(CORPUS)))
def test_expand_history_byte_identical_to_frozen_golden(idx):
    """Every corpus input expands byte-identically to the frozen baseline."""
    golden = _load_golden()
    assert len(golden) == len(CORPUS), (
        "golden length drifted from corpus; regenerate deliberately")
    hist_key, command = CORPUS[idx]
    expander = _make_expander()
    actual = _capture(expander, HISTORIES[hist_key], command)
    assert actual == golden[idx], (
        f"expand_history output changed for {command!r} (history {hist_key!r}):\n"
        f"  golden: {golden[idx]!r}\n  actual: {actual!r}")


def _regenerate():
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _run_corpus()
    with open(GOLDEN_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {len(data)} corpus entries to {GOLDEN_PATH}")


if __name__ == "__main__":
    _regenerate()
