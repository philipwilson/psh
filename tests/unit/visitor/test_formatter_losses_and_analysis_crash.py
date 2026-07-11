"""--format round-trip fidelity + analysis modes survive syntax errors.

Two visitor findings from the 2026-06-21 appraisal:

* H10 — four distinct LOSSY ``--format`` defects (post-v0.505): a bare ``$var``
  before a name char lost its disambiguating braces (``${x}there`` -> ``$xthere``),
  quoted ``case`` patterns and the ``case`` subject lost their quotes, and
  embedded quotes/backticks in a double-quoted literal were not re-escaped — each
  produced output that re-parsed to DIFFERENT (or invalid) shell.
* H11 — every analysis mode (``--validate``/``--format``/``--metrics``/
  ``--security``/``--lint``) crashed with an uncaught Python traceback on a
  syntax error, because the handler caught only ``(ValueError, TypeError)`` while
  ``ParseError``/``UnclosedQuoteError`` derive from ``PshError``/``SyntaxError``.

The fixes route every word-bearing case node through the quote-preserving
``_format_word`` (with brace-disambiguation + double-quote re-escaping) and catch
``(PshError, SyntaxError)`` in the analysis entry points.
"""

import subprocess
import sys

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import FormatterVisitor


def _format(src: str) -> str:
    return FormatterVisitor().visit(parse(tokenize(src)))


def _run(*args: str):
    return subprocess.run([sys.executable, '-m', 'psh', *args],
                          capture_output=True, text=True)


# (source, must-appear-substring) — the formatted output must contain the
# round-trippable form, not the lossy one.
ROUNDTRIP_CASES = [
    ('echo ${x}there', '${x}there'),         # C1: brace disambiguation
    ('echo ${x}0', '${x}0'),                 # C1: digit follows
    ('case $v in "a b") echo m;; esac', '"a b")'),   # C2: pattern quotes
    ('echo "say \\"hi\\""', '\\"hi\\"'),     # C3: re-escape inner quotes
    ('case "a b" in "a b") echo m;; esac', 'case "a b" in'),  # C4: subject quotes
]


@pytest.mark.parametrize('source,needle',
                         [pytest.param(s, n, id=n) for s, n in ROUNDTRIP_CASES])
def test_format_is_roundtrippable(source, needle):
    formatted = _format(source)
    assert needle in formatted, f"{source!r} -> {formatted!r}"
    # And the formatted text must re-parse without error.
    parse(tokenize(formatted))


def test_format_brace_disambiguation_preserves_variable():
    # The lossy form `$xthere` references a different variable; the fixed form
    # `${x}there` references x then literal "there".
    fmt = _format('x=hi; echo ${x}there')
    assert '$xthere' not in fmt
    assert '${x}there' in fmt


class TestFormatBehaviorPreserved:
    """End-to-end: the reformatted script behaves like the original."""

    CASES = [
        'x=hi; echo ${x}there',
        'x="a b"; case $x in "a b") echo M;; *) echo N;; esac',
        'echo "say \\"hi\\""',
        'case "a b" in "a b") echo M;; *) echo N;; esac',
    ]

    @pytest.mark.parametrize('src', CASES)
    def test_behavior_unchanged(self, src):
        original = _run('-c', src)
        formatted = _format(src)
        reformatted = _run('-c', formatted)
        assert reformatted.stdout == original.stdout
        assert reformatted.returncode == original.returncode


class TestAnalysisModesSurviveSyntaxErrors:
    MODES = ['--validate', '--format', '--metrics', '--security', '--lint']

    @pytest.mark.parametrize('mode', MODES)
    def test_parse_error_is_clean(self, mode):
        r = _run(mode, '-c', 'if true; then echo x')   # missing fi
        assert 'Traceback' not in r.stderr
        assert r.returncode == 2
        assert 'psh:' in r.stderr

    @pytest.mark.parametrize('mode', MODES)
    def test_lexer_error_is_clean(self, mode):
        r = _run(mode, '-c', 'echo "unclosed')          # unterminated quote
        assert 'Traceback' not in r.stderr
        assert r.returncode == 2

    def test_valid_input_still_succeeds(self):
        r = _run('--validate', '-c', 'if true; then echo x; fi')
        assert r.returncode == 0
