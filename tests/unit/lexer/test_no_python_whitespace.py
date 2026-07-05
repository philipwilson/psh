"""Architecture guardrail: no Python whitespace semantics in the lexer.

Shell token separators are space/tab/newline ONLY (POSIX <blank> + newline);
every other Unicode/control whitespace codepoint (NBSP, CR, VT, FF, U+2028, ...)
is an ordinary shell word character. Lexical whitespace decisions must therefore
route through `unicode_support.is_whitespace()`, NOT Python's `str.isspace()`
(which is True for the whole Unicode whitespace category and would, e.g., invert
`!<NBSP>false`'s exit status — lexer defect D2).

This test scans the production lexer package for `.isspace` attribute accesses
in ACTUAL CODE (comments and string literals are ignored via the `tokenize`
module, so the explanatory prose in the lexer that mentions `str.isspace()` is
not flagged). A site that genuinely wants the broader Python concept may opt out
with an inline `# allow-isspace: <reason>` comment; there are expected to be
none.
"""

import io
import pathlib
import tokenize

LEXER_DIR = pathlib.Path(__file__).resolve().parents[3] / "psh" / "lexer"
ALLOW_MARK = "# allow-isspace:"


def _isspace_code_hits(source: str):
    """Line numbers where `.isspace` appears as a real attribute access."""
    hits = []
    prev = None
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return hits
    for tok in toks:
        if (tok.type == tokenize.NAME and tok.string == "isspace"
                and prev is not None
                and prev.type == tokenize.OP and prev.string == "."):
            hits.append(tok.start[0])
        prev = tok
    return hits


def test_lexer_has_no_isspace_calls():
    offenders = []
    for path in sorted(LEXER_DIR.rglob("*.py")):
        source = path.read_text()
        lines = source.splitlines()
        for lineno in _isspace_code_hits(source):
            if ALLOW_MARK in lines[lineno - 1]:
                continue
            rel = path.relative_to(LEXER_DIR.parent.parent)
            offenders.append(f"{rel}:{lineno}: {lines[lineno - 1].strip()}")
    assert not offenders, (
        "Lexer whitespace decisions must use unicode_support.is_whitespace(), "
        "not str.isspace(). Offending site(s):\n" + "\n".join(offenders)
    )
