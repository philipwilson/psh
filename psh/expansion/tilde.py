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

    def expand(self, path: str) -> str:
        """Expand tilde in paths like ~ and ~user"""
        if not path.startswith('~'):
            return path

        # Directory-stack / PWD / OLDPWD tilde prefixes:
        #   ~+    -> $PWD            ~-    -> $OLDPWD
        #   ~+N   -> `dirs +N`       ~-N   -> `dirs -N`
        #   ~N    -> `dirs +N`
        # The prefix runs to the first '/' or end of word.
        if len(path) > 1 and (path[1] in '+-' or path[1].isdigit()):
            slash = path.find('/')
            prefix = path if slash == -1 else path[:slash]
            rest = '' if slash == -1 else path[slash:]
            expanded = self._expand_dirstack_prefix(prefix)
            if expanded is None:
                return path  # leave whole thing literal (out of range, etc.)
            return expanded + rest

        # Just ~ or ~/path
        if path == '~' or path.startswith('~/'):
            # The shell's HOME variable wins (HOME=/xyz; echo ~ → /xyz),
            # falling back to the password database like bash.
            home = self.state.get_variable('HOME')
            if not home:
                try:
                    home = pwd.getpwuid(os.getuid()).pw_dir
                except (KeyError, OSError):
                    home = '/'

            if path == '~':
                return home
            else:
                return home + path[1:]  # Replace ~ with home

        # ~username or ~username/path
        else:
            # Find where username ends
            slash_pos = path.find('/')
            if slash_pos == -1:
                username = path[1:]  # Everything after ~
                rest = ''
            else:
                username = path[1:slash_pos]
                rest = path[slash_pos:]

            # Look up user's home directory
            try:
                user_info = pwd.getpwnam(username)
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
