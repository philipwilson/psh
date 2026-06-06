"""Small shared predicates for the analysis visitors.

These name checks that more than one analysis visitor (security, validator,
linter) would otherwise spell out inline. The visitors keep their own policy —
which contexts they flag, at what severity, with what message — but share the
underlying classification here.
"""


def has_unquoted_expansion(word, arg: str) -> bool:
    """True if *arg* carries an unquoted ``$`` expansion (word-split risk).

    *word* is the Word AST node for *arg*; *arg* is its expanded-source text.
    A wholly-quoted word is safe; otherwise a ``$`` in the text indicates an
    unquoted expansion subject to word splitting / globbing.
    """
    return not word.is_quoted and '$' in arg
