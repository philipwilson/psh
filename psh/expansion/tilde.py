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
        if not path.startswith('~'):
            return path

        end = self.prefix_end(path)
        prefix, rest = path[:end], path[end:]

        # Directory-stack / PWD / OLDPWD tilde prefixes:
        #   ~+    -> $PWD            ~-    -> $OLDPWD
        #   ~+N   -> `dirs +N`       ~-N   -> `dirs -N`
        #   ~N    -> `dirs +N`
        if len(prefix) > 1 and (prefix[1] in '+-' or prefix[1].isdigit()):
            expanded = self._expand_dirstack_prefix(prefix)
            if expanded is None:
                return path  # leave whole thing literal (out of range, etc.)
            return expanded + rest

        # Just ~ (possibly with /path or :rest following)
        if prefix == '~':
            # The shell's HOME variable wins (HOME=/xyz; echo ~ → /xyz),
            # falling back to the password database like bash.
            home = self.state.get_variable('HOME')
            if not home:
                try:
                    home = pwd.getpwuid(os.getuid()).pw_dir
                except (KeyError, OSError):
                    home = '/'
            return home + rest

        # ~username (possibly with /path or :rest following)
        try:
            user_info = pwd.getpwnam(prefix[1:])
            return user_info.pw_dir + rest
        except KeyError:
            # User not found, return unchanged
            return path

    def _dir_stack(self):
        """Effective directory stack as ``dirs`` would show it.

        Index 0 is the top (current dir). bash keeps the top synced with
        ``cd``; psh's stack does not, so we force index 0 to the current
        ``$PWD`` to match bash for the dir-stack tilde forms.
        """
        pwd = self.state.get_variable('PWD') or os.getcwd()
        stack_obj = getattr(self.state, 'directory_stack', None)
        if stack_obj is None or stack_obj.size() == 0:
            return [pwd]
        stack = list(stack_obj.stack)
        stack[0] = pwd
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
