"""Test command builtin for conditionals."""
import os
import stat
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class TestBuiltin(Builtin):
    """Test command for conditionals."""

    @property
    def name(self) -> str:
        return "test"

    @property
    def synopsis(self) -> str:
        return "test [EXPRESSION]"

    @property
    def help(self) -> str:
        return """test: test [EXPRESSION]
    Evaluate conditional expression.

    Returns 0 (true) or 1 (false) depending on the evaluation of EXPR.
    Expressions may be unary, binary, or combined with -a (AND), -o (OR),
    ! (NOT), and ( ) grouping.

    File operators:
      -e FILE    FILE exists
      -f FILE    FILE exists and is a regular file
      -d FILE    FILE exists and is a directory
      -s FILE    FILE exists and has size > 0
      -r FILE    FILE exists and is readable
      -w FILE    FILE exists and is writable
      -x FILE    FILE exists and is executable
      -L FILE    FILE exists and is a symbolic link
      -b FILE    FILE is a block device
      -c FILE    FILE is a character device
      -p FILE    FILE is a named pipe
      -S FILE    FILE is a socket
      -t FD      FD is opened on a terminal

    String operators:
      -z STRING        STRING has zero length
      -n STRING        STRING has non-zero length
      S1 = S2          Strings are equal
      S1 != S2         Strings are not equal

    Integer operators:
      N1 -eq N2   N1 equals N2         N1 -ne N2   N1 not equal to N2
      N1 -lt N2   N1 less than N2      N1 -gt N2   N1 greater than N2
      N1 -le N2   N1 less or equal     N1 -ge N2   N1 greater or equal

    File comparison:
      F1 -nt F2   F1 is newer than F2
      F1 -ot F2   F1 is older than F2
      F1 -ef F2   F1 and F2 are the same file

    Exit Status:
    Returns 0 if EXPRESSION is true, 1 if false, 2 on error."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the test builtin."""
        # Remove 'test' from args
        test_args = args[1:]
        return self.evaluate_test(test_args, shell)

    def evaluate_test(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate test expression."""
        if not args:
            return 1  # False

        # Check for leading ! (negation)
        negate = False
        if args[0] == '!':
            negate = True
            args = args[1:]  # Remove the !
            if not args:
                return 1  # ! with no args is false

        # Evaluate the expression
        result = self._evaluate_expression(args, shell)

        # Apply negation if needed
        if negate:
            result = 0 if result != 0 else 1

        return result

    def _evaluate_expression(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate test expression without negation."""
        if not args:
            return 1  # False

        # Handle parenthesized grouping: ( expr )
        if args[0] == '(' and ')' in args:
            return self._evaluate_with_parens(args, shell)

        if len(args) == 1:
            # Single argument - true if non-empty string
            return 0 if args[0] else 1

        if len(args) == 2:
            # Unary operators
            op, arg = args
            return self.evaluate_unary(op, arg, shell)

        if len(args) == 3:
            # Binary operators
            arg1, op, arg2 = args
            return self._evaluate_binary(arg1, op, arg2, shell)

        if len(args) == 4:
            # Check if we have a split operator (e.g., ! = becoming != )
            # This handles cases like: test hello ! = hello
            arg1, op_part1, op_part2, arg2 = args
            combined_op = op_part1 + op_part2

            # Check if the combined operator is valid
            if combined_op in ['!=', '==', '=~']:
                return self._evaluate_binary(arg1, combined_op, arg2, shell)

        # Handle logical operators -a and -o
        # Scan for -o first (lower precedence), then -a, skipping
        # operators inside parenthesized groups.
        for target_op in ('-o', '-a'):
            depth = 0
            for i in range(len(args)):
                if args[i] == '(':
                    depth += 1
                elif args[i] == ')':
                    depth -= 1
                elif args[i] == target_op and depth == 0:
                    if i == 0 or i == len(args) - 1:
                        self.error(f"{target_op}: binary operator expected", shell)
                        return 2
                    left_result = self._evaluate_expression(args[:i], shell)
                    if target_op == '-a' and left_result != 0:
                        return left_result
                    if target_op == '-o' and left_result == 0:
                        return 0
                    return self._evaluate_expression(args[i+1:], shell)

        # If we get here, it's a complex expression we don't support
        return 2

    def _evaluate_with_parens(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate an expression that starts with '('."""
        # Find matching closing paren
        depth = 0
        for i, arg in enumerate(args):
            if arg == '(':
                depth += 1
            elif arg == ')':
                depth -= 1
                if depth == 0:
                    # Evaluate the inner expression
                    inner = args[1:i]
                    inner_result = self._evaluate_expression(inner, shell)
                    # If there are more args after ')', handle them
                    rest = args[i+1:]
                    if not rest:
                        return inner_result
                    # rest should start with -a or -o
                    if rest[0] in ('-a', '-o') and len(rest) > 1:
                        if rest[0] == '-a':
                            if inner_result != 0:
                                return inner_result
                            return self._evaluate_expression(rest[1:], shell)
                        else:  # -o
                            if inner_result == 0:
                                return 0
                            return self._evaluate_expression(rest[1:], shell)
                    self.error(f"syntax error near '{rest[0]}'", shell)
                    return 2
        self.error("missing ')'", shell)
        return 2

    def evaluate_unary(self, op: str, arg: str, shell: 'Shell') -> int:
        """Evaluate unary operators."""
        if op == '-z':
            # True if string is empty
            return 0 if not arg else 1
        elif op == '-n':
            # True if string is non-empty
            return 0 if arg else 1
        elif op == '-f':
            # True if file exists and is regular file
            return 0 if os.path.isfile(arg) else 1
        elif op == '-d':
            # True if file exists and is directory
            return 0 if os.path.isdir(arg) else 1
        elif op == '-e':
            # True if file exists
            return 0 if os.path.exists(arg) else 1
        elif op == '-r':
            # True if file is readable
            return 0 if os.path.isfile(arg) and os.access(arg, os.R_OK) else 1
        elif op == '-w':
            # True if file is writable
            return 0 if os.path.isfile(arg) and os.access(arg, os.W_OK) else 1
        elif op == '-x':
            # True if file is executable
            return 0 if os.path.isfile(arg) and os.access(arg, os.X_OK) else 1
        elif op == '-s':
            # True if file exists and has size > 0
            try:
                return 0 if os.path.isfile(arg) and os.path.getsize(arg) > 0 else 1
            except (OSError, IOError):
                return 1
        elif op == '-L' or op == '-h':
            # True if file exists and is a symbolic link
            return 0 if os.path.islink(arg) else 1
        elif op == '-b':
            # True if file exists and is a block device
            try:
                st = os.stat(arg)
                return 0 if stat.S_ISBLK(st.st_mode) else 1
            except (OSError, IOError):
                return 1
        elif op == '-c':
            # True if file exists and is a character device
            try:
                st = os.stat(arg)
                return 0 if stat.S_ISCHR(st.st_mode) else 1
            except (OSError, IOError):
                return 1
        elif op == '-p':
            # True if file exists and is a named pipe (FIFO)
            try:
                st = os.stat(arg)
                return 0 if stat.S_ISFIFO(st.st_mode) else 1
            except (OSError, IOError):
                return 1
        elif op == '-S':
            # True if file exists and is a socket
            try:
                st = os.stat(arg)
                return 0 if stat.S_ISSOCK(st.st_mode) else 1
            except (OSError, IOError):
                return 1
        elif op == '-k':
            # True if file has sticky bit set
            try:
                st = os.stat(arg)
                return 0 if st.st_mode & stat.S_ISVTX else 1
            except (OSError, IOError):
                return 1
        elif op == '-u':
            # True if file has setuid bit set
            try:
                st = os.stat(arg)
                return 0 if st.st_mode & stat.S_ISUID else 1
            except (OSError, IOError):
                return 1
        elif op == '-g':
            # True if file has setgid bit set
            try:
                st = os.stat(arg)
                return 0 if st.st_mode & stat.S_ISGID else 1
            except (OSError, IOError):
                return 1
        elif op == '-O':
            # True if file is owned by effective user ID
            try:
                st = os.stat(arg)
                return 0 if st.st_uid == os.geteuid() else 1
            except (OSError, IOError):
                return 1
        elif op == '-G':
            # True if file is owned by effective group ID
            try:
                st = os.stat(arg)
                return 0 if st.st_gid == os.getegid() else 1
            except (OSError, IOError):
                return 1
        elif op == '-N':
            # True if file was modified since it was last read
            try:
                st = os.stat(arg)
                return 0 if st.st_mtime > st.st_atime else 1
            except (OSError, IOError):
                return 1
        elif op == '-t':
            # True if file descriptor is open and refers to a terminal
            try:
                fd = int(arg)
                return 0 if os.isatty(fd) else 1
            except (ValueError, OSError):
                return 1
        elif op == '-v':
            # True if variable is set (bash nameref support)
            # This requires access to shell state to check variables
            # For now, we'll need to handle this specially in the shell
            return 2  # Indicate special handling needed
        else:
            self.error(f"{op}: unary operator expected", shell)
            return 2  # Unknown operator

    def _evaluate_binary(self, arg1: str, op: str, arg2: str, shell: 'Shell') -> int:
        """Evaluate binary operators."""
        if op == '=':
            return 0 if arg1 == arg2 else 1
        elif op == '!=':
            return 0 if arg1 != arg2 else 1
        elif op == '<':
            # bash extension: string sorts before arg2 in ASCII/byte order
            # (test/[ uses byte order, NOT the locale collation [[ ]] uses)
            return 0 if arg1 < arg2 else 1
        elif op == '>':
            # bash extension: string sorts after arg2 in ASCII/byte order
            return 0 if arg1 > arg2 else 1
        elif op == '-eq':
            try:
                return 0 if int(arg1) == int(arg2) else 1
            except ValueError:
                self.error("integer expression expected", shell)
                return 2
        elif op == '-ne':
            try:
                return 0 if int(arg1) != int(arg2) else 1
            except ValueError:
                self.error("integer expression expected", shell)
                return 2
        elif op == '-lt':
            try:
                return 0 if int(arg1) < int(arg2) else 1
            except ValueError:
                self.error("integer expression expected", shell)
                return 2
        elif op == '-le':
            try:
                return 0 if int(arg1) <= int(arg2) else 1
            except ValueError:
                self.error("integer expression expected", shell)
                return 2
        elif op == '-gt':
            try:
                return 0 if int(arg1) > int(arg2) else 1
            except ValueError:
                self.error("integer expression expected", shell)
                return 2
        elif op == '-ge':
            try:
                return 0 if int(arg1) >= int(arg2) else 1
            except ValueError:
                self.error("integer expression expected", shell)
                return 2
        elif op == '-nt':
            # True if file1 is newer than file2 (modification time)
            try:
                stat1 = os.stat(arg1)
                stat2 = os.stat(arg2)
                return 0 if stat1.st_mtime > stat2.st_mtime else 1
            except (OSError, IOError):
                return 1
        elif op == '-ot':
            # True if file1 is older than file2 (modification time)
            try:
                stat1 = os.stat(arg1)
                stat2 = os.stat(arg2)
                return 0 if stat1.st_mtime < stat2.st_mtime else 1
            except (OSError, IOError):
                return 1
        elif op == '-ef':
            # True if file1 and file2 refer to the same file (same device and inode)
            try:
                stat1 = os.stat(arg1)
                stat2 = os.stat(arg2)
                return 0 if (stat1.st_dev == stat2.st_dev and stat1.st_ino == stat2.st_ino) else 1
            except (OSError, IOError):
                return 1
        else:
            self.error(f"{op}: binary operator expected", shell)
            return 2  # Unknown operator


@builtin
class BracketBuiltin(Builtin):
    """[ command (alias for test)."""

    @property
    def name(self) -> str:
        return "["

    @property
    def synopsis(self) -> str:
        return "[ EXPRESSION ]"

    @property
    def help(self) -> str:
        return """[: [ EXPRESSION ]
    Evaluate conditional expression.

    This is a synonym for the 'test' builtin, but the last argument
    must be a literal ] to match the opening [.

    See 'help test' for the full list of supported operators.

    Exit Status:
    Returns 0 if EXPRESSION is true, 1 if false, 2 on error."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the [ builtin."""
        # For [ command, last argument must be ]
        if len(args) < 2 or args[-1] != ']':
            self.error("missing ']'", shell)
            return 2  # Syntax error

        # Remove [ and ], then evaluate as test
        test_args = args[1:-1]
        test_builtin = TestBuiltin()
        return test_builtin.evaluate_test(test_args, shell)
