"""Scanner-vs-parser agreement for ``$(...)`` extents.

The command-substitution boundary scanner
(:func:`psh.lexer.cmdsub_scanner.find_command_substitution_end`) models a
deliberately small copy of the shell grammar to decide where ``$(`` ends.
The real arbiter of a substitution body is the *parser*: when psh executes
``$(body)`` it strips the delimiters and parses ``body`` as a command list
(``psh/expansion/command_sub.py``: ``cmd_sub[2:-1]``). If the scanner and
the parser disagreed about which ``)`` is the closer, the parser would be
handed a truncated or over-long body.

This test pins their agreement over a *generated* corpus of tricky bodies
(nested ``$()``, ``case`` statements, comments, all quote forms,
arithmetic, ``;;``/``;&``/``;;&`` separators, here-strings, nested control
structures). For each body it asserts:

  * the scanner finds a closer, and the extent it picks is exactly the
    body (the ``)`` we appended), and
  * the parser accepts that same body as a complete parse with no leftover
    tokens — i.e. the closing ``)`` the scanner chose is the one parsing
    ``$(body)`` would consume.

Both layers are driven by the same lexer/parser the rest of psh uses
(``psh.lexer.tokenize`` / ``psh.parser.parse``), the same helpers exercised
by ``tests/unit/lexer/test_cmdsub_extent.py`` and
``tests/integration/parsing/test_cmdsub_grammar.py``. Forms whose body psh's
parser does not (yet) accept on its own — notably extglob ``@(a|b)``
patterns, which are a runtime option the standalone parser does not enable —
are out of scope here: there is no parser acceptance to agree with. They are
covered by the frozen characterization harness and bash conformance tests.

The corpus is built deterministically (no randomness) so the test is stable.
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.cmdsub_scanner import find_command_substitution_end
from psh.lexer.token_types import TokenType
from psh.parser import parse


def _build_corpus():
    """Deterministically generate tricky ``$(...)`` bodies.

    Returns a list of ``(label, body)`` pairs. ``body`` is the text that
    would appear between ``$(`` and the closing ``)``; every entry is a
    body psh's standalone parser accepts (extglob patterns excluded — see
    the module docstring).
    """
    # Base bodies, each individually a valid command list.
    base = [
        ('simple', 'echo hello'),
        ('semicolons', 'echo a; echo b; echo c'),
        ('pipeline', 'echo a | grep a | wc -l'),
        ('and_or', 'true && echo y || echo n'),
        ('sq_paren', "echo 'a)b)c'"),
        ('dq_paren', 'echo "a)b)c"'),
        ('ansi_c_paren', "echo $'a)b'"),
        ('escaped_paren', 'echo \\) done'),
        ('arith', 'echo $((1 + 2 * 3))'),
        ('brace_param', 'echo ${x:-default)}'),
        ('comment_paren', 'echo hi # a ) in a comment\necho bye'),
        ('subshell', '(echo inner)'),
        ('brace_group', '{ echo hi; }'),
        ('if', 'if true; then echo t; fi'),
        ('for', 'for i in a b c; do echo "$i"; done'),
        ('while', 'while false; do break; done'),
        ('case_basic', 'case x in x) echo A;; esac'),
        ('case_paren_pattern', 'case x in (x) echo A;; esac'),
        ('case_alternation', 'case y in a|b|y) echo M;; esac'),
        ('case_multi_branch',
         'case b in a) echo A;; b) echo B;; *) echo Z;; esac'),
        ('case_fallthrough', 'case x in x) echo one;& y) echo two;; esac'),
        ('case_continue', 'case x in x) echo one;;& *) echo two;; esac'),
        ('case_esac_only', 'case x in esac'),
        ('case_subject_cmdsub',
         'case $(echo x) in x) echo hi;; esac'),
        ('here_string', 'cat <<< word'),
    ]

    corpus = list(base)

    # Wrap every base body in a nested command substitution: $(echo $(BODY)).
    for label, body in base:
        corpus.append(('nest_' + label, 'echo $(' + body + ')'))

    # Put case bodies through a second case nesting level.
    case_bodies = [(lbl, b) for lbl, b in base if lbl.startswith('case')]
    for label, body in case_bodies:
        corpus.append(
            ('case_around_' + label,
             'case outer in o) ' + body + ';; esac'))

    # Compose pairs of base bodies with separators (deterministic order).
    for sep in (';', '|', '&&'):
        a_label, a_body = base[0]      # simple
        b_label, b_body = base[16]     # case_basic
        corpus.append(
            ('compose_%s' % sep.strip(';|&') or 'pipe',
             '%s %s %s' % (a_body, sep, b_body)))

    return corpus


CORPUS = _build_corpus()


@pytest.mark.parametrize(
    "label,body", CORPUS, ids=[lbl for lbl, _ in CORPUS])
def test_scanner_extent_matches_parser_acceptance(label, body):
    """The scanner's closing ``)`` is the one the parser consumes."""
    # 1. Scanner: feed the body followed by its real closing paren.
    text = body + ')'
    end, found = find_command_substitution_end(text, 0)
    assert found, (
        "scanner failed to find a closer for body %r" % body)
    scanned_body = text[:end - 1]
    assert scanned_body == body, (
        "scanner picked a different extent: %r != %r"
        % (scanned_body, body))

    # 2. Parser: the body the scanner delimited must be a complete parse.
    #    parse() raises ParseError on garbage or an incomplete command,
    #    so a clean return means the parser accepts exactly this body.
    ast = parse(tokenize(scanned_body))
    assert ast is not None


@pytest.mark.parametrize(
    "label,body", CORPUS, ids=[lbl for lbl, _ in CORPUS])
def test_lexer_cmdsub_token_uses_scanner_extent(label, body):
    """The lexer's COMMAND_SUB token spans exactly the scanner's extent.

    This ties the standalone scanner to the lexer that actually feeds the
    parser. Bodies that start with ``(`` are skipped: ``$((`` is the greedy
    arithmetic-expansion dispatch in both the lexer and the scanner, so the
    whole thing tokenizes as arithmetic, not command substitution.
    """
    if body.startswith('('):
        pytest.skip("$(( is arithmetic, not command substitution")
    full = '$(' + body + ')'
    cmdsub = [t for t in tokenize(full) if t.type == TokenType.COMMAND_SUB]
    assert cmdsub, "no COMMAND_SUB token produced for %r" % full
    assert cmdsub[0].value == full, (
        "COMMAND_SUB token %r != expected %r"
        % (cmdsub[0].value, full))


def test_corpus_is_nontrivial():
    """Guard against the generator silently producing an empty corpus."""
    assert len(CORPUS) >= 50
