"""Tilde expansion implementation."""
import os
import pwd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..shell import Shell


class TildeExpander:
    """Handles tilde expansion (~, ~user)."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

    @staticmethod
    def prefix_end(path: str) -> int:
        """End index of the leading tilde-prefix in *path*.

        bash delimits a tilde-prefix at the first unquoted ``/`` OR ``:``
        (the ``:`` via tilde_additional_suffixes — ``echo ~:x`` expands to
        ``$HOME:x``; probed bash 5.2). Returns ``len(path)`` when neither
        appears. This is THE boundary rule, shared by :meth:`expand`, the
        word-leading decision (word_expander._leading_tilde_expandable
        documents the all-unquoted-literal requirement layered on top),
        and the operand walkers (operands._tilde_prefix).
        """
        for i in range(1, len(path)):
            if path[i] in '/:':
                return i
        return len(path)

    def expand(self, path: str) -> str:
        """Expand a leading tilde-prefix: ~, ~user, ~+/~-/~N (+ optional rest).

        The prefix runs to the first ``/`` or ``:`` (see prefix_end); the
        rest of *path* is appended verbatim. An inexpansible prefix (unknown
        user, out-of-range dirstack index) leaves the WHOLE path literal.
        """
        split = self.expand_split(path)
        return path if split is None else split[0] + split[1]

    @staticmethod
    def word_end(path: str) -> int:
        """End index of the tilde WORD in *path*: the first ``/``, or its end.

        bash has TWO tilde boundaries and they are NOT the same; the
        distinction is load-bearing and this method is the second one.

        - The tilde PREFIX — the part that EXPANDS — ends at the first ``/``
          **or** ``:`` (:meth:`prefix_end`).
        - The tilde WORD — the part bash makes LITERAL when the word is a
          pattern — ends at the first ``/``. **EXCEPT in an assignment-shaped
          word**, where ``:`` ends it too, so the remainder after a ``:`` stays
          LIVE there. bash calls its ``tilde_find_word`` in assignment mode for
          those; psh gets the same answer because
          ``word_expander._expand_assignment_value_tildes`` splits the value on
          ``:`` FIRST and hands this method one colon-free segment at a time.

        Proving the rule needs FOUR subjects per pattern, not two: ``o`` alone
        is also what a shell that never expanded the tilde would print, so only
        the full ROW identifies the behaviour. Measured against bash 5.3.15 and
        against psh at the two tips that embody the rival hypotheses —
        ``b6ec6f95`` never expanded a ``case`` pattern's tilde, and
        ``f712bc1e`` expanded it but left the metacharacter live::

            pattern  hypothesis            '/h/me:LIT'  '/h/me:XX'  '~:LIT'  '~:XX'
            ~:*      correct (and bash)         M           o          o        o
            ~:*      expanded, left live        M           M          o        o
            ~:*      never expanded             o           o          M        M
            ~:[a]    correct (and bash)         M           o          o        o
            ~:[a]    expanded, left live        o           o          o        o
            (LIT is the pattern's own remainder text: '*', '?', '[a]'.)

        WHICH cell does the separating is pattern dependent, which is why the
        pin carries the whole row rather than one cell. At ``~:*`` column 2
        kills "expanded, left live" and columns 1/3/4 kill "never expanded"; at
        ``~:[a]`` the live hypothesis collapses to all-``o`` so column 1 is what
        separates it; at ``~:?`` the live hypothesis is indistinguishable from
        correct (``?`` matches one character and ``XX`` is two), so that pattern
        pins only the never-expanded direction.

        The ``/`` boundary is one-sided, and the assignment exception flips the
        ``:`` one::

            case '/h/me:*/YY'  in ~:*/*)  esac   # M: 1st * inside and literal,
                                                 #    2nd past the '/' and live
            case 'x=/h/me:XX'  in x=~:*)  esac   # M: assignment-shaped, so the
                                                 #    ':' ended the word and the
                                                 #    * is LIVE
            case '/h/me:XX'    in ~:*)    esac   # o: control, not assignment
                                                 #    shaped, so the * is literal

        Round 2 of slot 1.11 escaped only the replacement and left the
        remainder live, which is exactly the last row printing ``M``.
        """
        cut = path.find('/', 1)
        return len(path) if cut == -1 else cut

    def expand_escaped(self, path: str, escape) -> str:
        """:meth:`expand`, with *escape* applied to the whole tilde WORD.

        bash makes a tilde expansion match LITERALLY when the word is a
        pattern, while text the source word supplied OUTSIDE the tilde word
        keeps its metacharacter power. It does NOT quote the result of
        parameter expansion — that is the other half of the rule::

            HOME='/a*b'; case '/aXb' in ~)     esac   # no match  (~ is literal)
            HOME='/a*b'; case '/aXb' in $HOME) esac   # MATCHES   ($HOME is live)

        A pattern-word caller passes its own escape (``glob_escape`` for a glob
        pattern, ``re.escape`` for a ``[[ =~ ]]`` regex source). What gets
        escaped is the replacement PLUS the remainder of the tilde word
        (:meth:`word_end`), because bash quotes the tilde word whole; what
        follows the word's ``/`` boundary is returned untouched, so
        ``case $HOME/ab in ~/a*)`` still globs on the ``a*``. Command-word
        callers pass nothing and keep the raw join.
        """
        split = self.expand_split(path)
        if split is None:
            return path
        replacement, rest = split
        # The tilde WORD continues past the prefix's ':' boundary to the first
        # '/'. `word_end` indexes into `path`; `rest` starts where the prefix
        # ended, so shift by the prefix length to split `rest` at the same
        # character. Everything up to there is literal, the tail stays live.
        prefix_len = len(path) - len(rest)
        cut = self.word_end(path) - prefix_len
        inside, outside = rest[:cut], rest[cut:]
        return escape(replacement + inside) + outside

    def expand_split(self, path: str):
        """``(replacement, rest)`` for a leading tilde-prefix, or None.

        THE single decision behind :meth:`expand` and :meth:`expand_escaped`:
        *replacement* is the text the tilde-prefix expanded TO and *rest* is
        the remainder of *path*, verbatim. ``None`` means nothing expands and
        the WHOLE path stays literal (no leading ``~``, an unknown user, an
        out-of-range dirstack index) — the two callers both re-emit *path*
        unchanged in that case, so the "leave it whole" rule is stated once.
        """
        if not path.startswith('~'):
            return None

        end = self.prefix_end(path)
        prefix, rest = path[:end], path[end:]

        # Directory-stack / PWD / OLDPWD tilde prefixes:
        #   ~+    -> $PWD            ~-    -> $OLDPWD
        #   ~+N   -> `dirs +N`       ~-N   -> `dirs -N`
        #   ~N    -> `dirs +N`
        if len(prefix) > 1 and (prefix[1] in '+-' or prefix[1].isdigit()):
            expanded = self._expand_dirstack_prefix(prefix)
            if expanded is None:
                return None  # leave whole thing literal (out of range, etc.)
            return expanded, rest

        # Just ~ (possibly with /path or :rest following)
        if prefix == '~':
            # The shell's HOME variable wins (HOME=/xyz; echo ~ -> /xyz),
            # falling back to the password database like bash.
            home = self.state.get_variable('HOME')
            if not home:
                try:
                    home = pwd.getpwuid(os.getuid()).pw_dir
                except (KeyError, OSError):
                    home = '/'
            return home, rest

        # ~username (possibly with /path or :rest following)
        try:
            user_info = pwd.getpwnam(prefix[1:])
        except KeyError:
            return None  # User not found, leave the path unchanged
        return user_info.pw_dir, rest

    def _dir_stack(self):
        """Effective directory stack as ``dirs`` would show it.

        Index 0 is the top (current dir). bash keeps the top synced with
        ``cd``; psh's stack does not, so we force index 0 to the current
        ``$PWD`` to match bash for the dir-stack tilde forms.
        """
        pwd_dir = self.state.get_variable('PWD') or os.getcwd()
        stack_obj = getattr(self.state, 'directory_stack', None)
        if stack_obj is None or stack_obj.size() == 0:
            return [pwd_dir]
        stack = list(stack_obj.stack)
        stack[0] = pwd_dir
        return stack

    def _expand_dirstack_prefix(self, prefix: str):
        """Expand ~+, ~-, ~+N, ~-N, ~N. Returns None to leave it literal."""
        body = prefix[1:]  # drop leading '~'

        # ~+ alone -> $PWD ; ~- alone -> $OLDPWD
        if body == '+':
            return self.state.get_variable('PWD') or os.getcwd()
        if body == '-':
            oldpwd = self.state.get_variable('OLDPWD')
            return oldpwd if oldpwd else None

        # ~N / ~+N -> dirs +N (from the top/left) ; ~-N -> dirs -N (from the
        # bottom/right). N must be all digits, otherwise it is not this form.
        if body and body[0] in '+-':
            sign = body[0]
            num = body[1:]
        else:
            sign = '+'
            num = body
        if not num.isdigit():
            return None
        n = int(num)
        stack = self._dir_stack()
        idx = n if sign == '+' else len(stack) - 1 - n
        if idx < 0 or idx >= len(stack):
            return None  # out of range -> bash leaves the word literal
        return stack[idx]
