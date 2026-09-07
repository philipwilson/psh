"""The one trailing-redirection helper shared by every combinator production.

A compound command may carry a trailing redirection list — ``done > file``,
``fi 2>&1``, ``esac >log``, ``} < in``, and equally ``(( i-- )) >/dev/null``
and ``[[ a == b ]] > f``. Parsing it in exactly ONE place is what keeps a
production from silently forgetting it.

Forgetting is not a cosmetic AST difference. An unconsumed redirect is picked
up by the statement-list loop (``commands/statements.py``) as a SECOND
statement, which both drops the redirection and replaces the compound's exit
status with the redirect-only command's 0::

    python -m psh --parser combinator -c \
        'i=3; while (( i-- )) >/dev/null; do :; done'   # never terminated

Owner: :meth:`TrailingRedirectMixin._parse_trailing_redirects`.
"""

from typing import TYPE_CHECKING, List, Tuple

from ...ast_nodes import Redirect
from ...lexer.token_types import Token
from .core import many

if TYPE_CHECKING:
    from .commands import CommandParsers


class TrailingRedirectMixin:
    """Supplies ``_parse_trailing_redirects`` to a combinator parser module.

    Mixed into every class that builds AST nodes with a ``redirects`` field:
    ``ControlStructureParsers`` (loops, conditionals, subshell/brace groups,
    function definitions) and ``SpecialCommandParsers`` (``(( ))``, ``[[ ]]``).
    The only requirement on the host is a wired ``self.commands``.
    """

    # Type-only declaration: the host class assigns this in its ``__init__``
    # (and rewires it in ``set_command_parsers``). Annotation, not assignment,
    # so no runtime attribute is created here.
    commands: "CommandParsers"

    def _parse_trailing_redirects(self, tokens: List[Token], pos: int
                                  ) -> Tuple[List[Redirect], int]:
        """Parse trailing redirections after a compound command.

        Called after the closing token (``done``, ``fi``, ``esac``, ``}``,
        ``)``, ``))``, ``]]``) to collect redirections like ``done > file``.
        A trailing ``&`` is NOT consumed here: backgrounding applies to the
        whole and-or list and is handled at that level (POSIX).

        Returns:
            Tuple of (redirects, new_pos)
        """
        # A trailing redirection list is exactly *zero or more* redirections,
        # which is precisely ``many``: it applies ``redirection`` until it stops
        # matching, gathering the results (and never fails — an empty list is a
        # valid, successful parse).
        result = many(self.commands.redirection).parse(tokens, pos)
        redirects: List[Redirect] = list(result.value or [])
        return redirects, result.position
