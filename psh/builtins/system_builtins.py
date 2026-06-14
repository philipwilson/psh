"""POSIX umask and times builtins."""

import os
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class UmaskBuiltin(Builtin):
    """Display or set the file mode creation mask."""

    @property
    def name(self) -> str:
        return "umask"

    @property
    def synopsis(self) -> str:
        return "umask [-p] [-S] [mode]"

    @property
    def description(self) -> str:
        return "Display or set the file mode creation mask"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        opts, operands = self.parse_flags(args, shell, flags='pS')
        if opts is None:
            return 2

        if not operands:
            # Display the current mask (reading requires a set/restore)
            mask = os.umask(0)
            os.umask(mask)
            if opts['S']:
                self.write_line(self._symbolic(mask), shell)
            elif opts['p']:
                self.write_line(f"umask {mask:04o}", shell)
            else:
                self.write_line(f"{mask:04o}", shell)
            return 0

        mode = operands[0]
        if mode and mode[0].isdigit():
            # Octal mode
            try:
                mask = int(mode, 8)
            except ValueError:
                self.error(f"{mode}: octal number out of range", shell)
                return 1
            if mask > 0o777 or mask < 0:
                self.error(f"{mode}: octal number out of range", shell)
                return 1
            os.umask(mask)
            return 0

        # Symbolic mode: clauses operate on the ALLOWED permissions
        # (the complement of the mask), per POSIX.
        current = os.umask(0)
        os.umask(current)
        allowed = self._apply_symbolic(mode, ~current & 0o777, shell)
        if allowed is None:
            return 1
        os.umask(~allowed & 0o777)
        return 0

    @staticmethod
    def _symbolic(mask: int) -> str:
        """Render a mask as u=...,g=...,o=... (allowed permissions)."""
        allowed = ~mask & 0o777
        parts = []
        for who, shift in (('u', 6), ('g', 3), ('o', 0)):
            bits = (allowed >> shift) & 0o7
            perms = ('r' if bits & 4 else '') + \
                    ('w' if bits & 2 else '') + \
                    ('x' if bits & 1 else '')
            parts.append(f"{who}={perms}")
        return ','.join(parts)

    def _apply_symbolic(self, mode: str, allowed: int, shell: 'Shell'):
        """Apply symbolic clauses (u+rwx,g-w,o=,a=rx) to allowed perms."""
        perm_bits = {'r': 4, 'w': 2, 'x': 1}
        who_shifts = {'u': (6,), 'g': (3,), 'o': (0,), 'a': (6, 3, 0)}

        for clause in mode.split(','):
            i = 0
            shifts: set[int] = set()
            while i < len(clause) and clause[i] in who_shifts:
                shifts.update(who_shifts[clause[i]])
                i += 1
            if not shifts:
                shifts = {6, 3, 0}
            if i >= len(clause) or clause[i] not in '+-=':
                bad = clause[i] if i < len(clause) else clause[-1:] or mode[:1]
                self.error(f"`{bad}': invalid symbolic mode operator", shell)
                return None
            op = clause[i]
            i += 1
            bits = 0
            for c in clause[i:]:
                if c not in perm_bits:
                    self.error(f"`{c}': invalid symbolic mode character", shell)
                    return None
                bits |= perm_bits[c]
            for shift in shifts:
                if op == '+':
                    allowed |= bits << shift
                elif op == '-':
                    allowed &= ~(bits << shift)
                else:  # '='
                    allowed = (allowed & ~(0o7 << shift)) | (bits << shift)
        return allowed & 0o777

    @property
    def help(self) -> str:
        return """umask: umask [-p] [-S] [mode]

    Display or set the file mode creation mask.

    With no mode, print the current mask. With an octal or symbolic
    mode, set the mask.

    Options:
      -S    Print the mask in symbolic form (u=rwx,g=rx,o=rx)
      -p    Print in a form reusable as input (umask 0022)

    Exit Status:
    Returns 0 unless mode is invalid or an invalid option is given."""


@builtin
class TimesBuiltin(Builtin):
    """Display accumulated user and system times."""

    @property
    def name(self) -> str:
        return "times"

    @property
    def synopsis(self) -> str:
        return "times"

    @property
    def description(self) -> str:
        return "Display process times for the shell and its children"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        t = os.times()

        def fmt(seconds: float) -> str:
            minutes = int(seconds // 60)
            return f"{minutes}m{seconds - minutes * 60:.3f}s"

        self.write_line(f"{fmt(t.user)} {fmt(t.system)}", shell)
        self.write_line(f"{fmt(t.children_user)} {fmt(t.children_system)}", shell)
        return 0

    @property
    def help(self) -> str:
        return """times: times

    Print the accumulated user and system CPU times for the shell
    (first line) and for processes run from the shell (second line).

    Exit Status:
    Always succeeds."""
