"""Test command builtin for conditionals."""
import os
import stat
from typing import TYPE_CHECKING, List

from ..core import AssociativeArray, IndexedArray
from ..expansion.subscript import SubscriptUse, TargetKind
from ..utils.file_tests import file_newer_than, file_older_than, files_same
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def variable_is_set(shell: 'Shell', var_ref: str) -> bool:
    """True if ``var_ref`` names a set variable or an existing array element.

    Supports ``name`` and ``array[key]`` (indexed or associative). Shared by
    the ``test``/``[`` builtin's ``-v`` operator and the ``[[ -v ... ]]`` test
    evaluator so both answer identically.
    """
    if '[' in var_ref and var_ref.endswith(']'):
        var_name = var_ref[:var_ref.index('[')]
        key_expr = var_ref[var_ref.index('[') + 1:-1]
        # The ONE subscript authority keys by target kind (campaign W2), the
        # same routing as unset (environment.py#_unset_array_element): an
        # associative target keys on one word/quote expansion; everything else
        # — indexed array, scalar, or an UNSET name — arithmetic-evaluates.
        # bash 5.2 (probe-verified 2026-07-19, W2-probes/test_v_matrix.txt):
        # an EMPTY subscript is silently unset; an invalid-arithmetic
        # subscript is the same FATAL line-discarding error as on read/write,
        # even when the name itself is unset (`test -v 'z[1//]'` aborts
        # before the lookup); a negative out-of-range index warns
        # "NAME: bad array subscript" (non-fatal) and reports unset.
        subscript = shell.expansion_manager.subscript
        var_obj = shell.state.scope_manager.get_variable_object(var_name)
        if var_obj is not None and isinstance(var_obj.value, AssociativeArray):
            return subscript.associative_key(key_expr) in var_obj.value
        idx = subscript.evaluate(key_expr, TargetKind.INDEXED,
                                 SubscriptUse.TEST_V)  # fatal on bad arith
        if idx is None or var_obj is None:
            # Empty subscript (silently unset) or unset name — the subscript
            # was still arithmetic-evaluated first, exactly like bash.
            return False
        assert isinstance(idx, int)
        if isinstance(var_obj.value, IndexedArray):
            if var_obj.value.negative_out_of_range(idx):
                print(f"{shell.state.error_location_prefix()}"
                      f"{var_name}: bad array subscript",
                      file=shell.state.stderr)
                return False
            return var_obj.value.get(idx) is not None
        # Scalar: acts as a one-element array at index 0 (bash).
        return var_obj.value is not None and idx == 0

    # Bare name. For an array, bash's `-v name` tests element 0 (`-v name[0]`),
    # so an empty array — even one explicitly assigned `=()` — is "unset".
    var_obj = shell.state.scope_manager.get_variable_object(var_ref)
    if var_obj is None:
        return False
    if isinstance(var_obj.value, IndexedArray):
        return 0 in var_obj.value
    if isinstance(var_obj.value, AssociativeArray):
        return "0" in var_obj.value
    return True


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

    Variable / option operators:
      -v NAME    NAME is a set variable (or array element)
      -R NAME    NAME is a set nameref variable
      -o OPT     shell option OPT (as in `set -o OPT`) is enabled

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

    # The $2 tokens that make a 3-argument expression a *binary* test. Per the
    # POSIX `test` algorithm (and bash) these are recognised BEFORE `$1` is
    # treated as `!` or `(` — so `test ! = x` is `"!" = "x"` (false), not a
    # negation, and `test "(" -ef ")"` is a file comparison, not a group.
    # `-a`/`-o` are the XSI 3-argument string-AND/OR primaries.
    _BINARY_PRIMARIES = frozenset({
        '=', '==', '!=', '<', '>',
        '-eq', '-ne', '-lt', '-le', '-gt', '-ge',
        '-nt', '-ot', '-ef',
        '-a', '-o',
    })

    @staticmethod
    def _negate(rc: int) -> int:
        """Negate a test result, propagating usage/syntax errors (rc 2).

        bash negates only the boolean: `! true` → 1, `! false` → 0. A `!`
        applied to an expression that is itself an *error* (rc 2) keeps the
        error — e.g. `test ! a b c` is rc 2, not 0.
        """
        if rc == 2:
            return 2
        return 1 if rc == 0 else 0

    def evaluate_test(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate a `test`/`[` expression via the POSIX argument-count
        algorithm.

        The dispatch is driven PRIMARILY by the number of arguments (POSIX
        XBD `test`); within a count, a binary primary in `$2` is recognised
        before `$1` is interpreted as `!` or `(`. Expressions of more than
        four arguments (and the 4-argument non-`!` forms) fall through to the
        bash-extension parser in `_evaluate_expression` (parenthesised groups,
        `-a`/`-o` with precedence).
        """
        n = len(args)
        if n == 0:
            return 1  # False
        if n == 1:
            # Single argument — true iff non-empty.
            return 0 if args[0] else 1
        if n == 2:
            return self._eval_two_args(args, shell)
        if n == 3:
            return self._eval_three_args(args, shell)
        if n == 4 and args[0] == '!':
            # POSIX 4-argument rule: leading `!` negates the 3-argument test
            # of the remainder (`test ! a = b`, `test ! -f x`).
            return self._negate(self._eval_three_args(args[1:], shell))
        # 4 non-`!` arguments and everything longer: the bash-extension
        # expression parser (grouping / -a / -o / leading `!`).
        return self._evaluate_expression(args, shell)

    def _eval_two_args(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate a 2-argument test (`$1 $2`)."""
        op, arg = args
        if op == '!':
            # `test ! STRING` negates the one-argument (non-empty) test.
            return self._negate(0 if arg else 1)
        return self.evaluate_unary(op, arg, shell)

    def _eval_three_args(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate a 3-argument test (`$1 $2 $3`) per the POSIX order."""
        arg1, op, arg2 = args
        if op in self._BINARY_PRIMARIES:
            # Binary primary in $2 wins over any !/( in $1 (POSIX/bash).
            return self._evaluate_binary(arg1, op, arg2, shell)
        if arg1 == '!':
            # `test ! $2 $3` negates the 2-argument test of `$2 $3`.
            return self._negate(self._eval_two_args([op, arg2], shell))
        if arg1 == '(' and arg2 == ')':
            # `( STRING )` — one-argument (non-empty) test of the inner token.
            return 0 if op else 1
        # $2 isn't a binary primary and $1 isn't !/( — bash reports $2.
        self.error(f"{op}: binary operator expected", shell)
        return 2

    def _evaluate_expression(self, args: List[str], shell: 'Shell') -> int:
        """Evaluate a test expression (bash-extension parser).

        Reached for >4 arguments, the 4-argument non-`!` forms, and
        recursively for the operands of `-a`/`-o` and parenthesised groups —
        so it must handle short sub-expressions too.
        """
        if not args:
            return 1  # False

        # Leading `!` negates the rest (bash). A LONE `!` is not negation — it
        # is the one-argument non-empty-string test (`test !` → 0), so only
        # negate when an operand follows.
        if args[0] == '!' and len(args) > 1:
            return self._negate(self._evaluate_expression(args[1:], shell))

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

        # NOTE: no "split operator" reconstruction (`test a ! = b` as `a != b`)
        # — bash does not do it either: every such 4-argument form
        # (`a ! = b`, `a = = b`, `a = ~ b`) is "too many arguments", rc 2.

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

        # If we get here it's a 4+-argument expression that isn't any
        # recognized combination — bash diagnoses these as "too many
        # arguments" (e.g. `[ x = ab ac ]`, `[ a b c d ]`), status 2.
        # The message must be printed, not just the silent rc.
        self.error("too many arguments", shell)
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
            # True if the path is readable — for ANY file type, including
            # directories and special files (bash defers to os.access; an
            # `isfile` guard would wrongly fail `-r /dev/null`, `-r /usr/bin`).
            # os.access already returns False for a nonexistent path.
            return 0 if os.access(arg, os.R_OK) else 1
        elif op == '-w':
            # True if the path is writable (any file type; see -r).
            return 0 if os.access(arg, os.W_OK) else 1
        elif op == '-x':
            # True if the path is executable/searchable (any file type — a
            # directory with the search bit set is `-x`; see -r).
            return 0 if os.access(arg, os.X_OK) else 1
        elif op == '-s':
            # True if the path exists and has a nonzero size — for ANY file
            # type, including a directory (bash uses stat, not isfile; an
            # `isfile` guard wrongly failed `-s DIR`). os.path.getsize follows
            # symlinks and raises for a missing/broken path -> false.
            try:
                return 0 if os.path.getsize(arg) > 0 else 1
            except OSError:
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
            # True if the named variable (or array element) is set.
            return 0 if variable_is_set(shell, arg) else 1
        elif op == '-R':
            # True if the named variable is a set nameref (bash). An empty
            # `declare -n r` is stored unset (None here), so only a nameref
            # with a target — even an unset target — counts.
            var_obj = shell.state.scope_manager.get_variable_object(arg)
            return 0 if (var_obj is not None and var_obj.is_nameref) else 1
        elif op == '-o':
            # True iff the named shell option (as spelled by `set -o NAME`)
            # is enabled. An unknown option name is simply false — bash does
            # not treat it as an error here.
            return 0 if shell.state.options.get(arg, False) else 1
        else:
            self.error(f"{op}: unary operator expected", shell)
            return 2  # Unknown operator

    # Signed 64-bit range for test's integer operands (bash uses intmax_t).
    _INT64_MIN = -(2 ** 63)
    _INT64_MAX = 2 ** 63 - 1

    @classmethod
    def _to_int64(cls, arg: str) -> int:
        """Parse a test/[ integer operand as bash does (signed 64-bit, base 10).

        bash's test uses intmax_t, so a non-numeric operand OR one outside the
        signed 64-bit range is rejected as "integer expression expected".
        Raises ValueError whose message is the offending token (matching bash's
        "TOKEN: integer expression expected") in both cases.
        """
        try:
            value = int(arg)
        except ValueError:
            raise ValueError(arg) from None
        if not (cls._INT64_MIN <= value <= cls._INT64_MAX):
            raise ValueError(arg)
        return value

    def _evaluate_binary(self, arg1: str, op: str, arg2: str, shell: 'Shell') -> int:
        """Evaluate binary operators."""
        if op == '=' or op == '==':
            # bash accepts == as a synonym for = in test/[ (literal string
            # equality — no globbing, unlike [[ ]]).
            return 0 if arg1 == arg2 else 1
        elif op == '!=':
            return 0 if arg1 != arg2 else 1
        elif op == '-a':
            # 3-argument form `[ s1 -a s2 ]`: AND of the operands' string
            # non-emptiness (POSIX XSI binary primary). Distinct from the
            # multi-arg -a that combines whole expressions (handled in
            # _evaluate_expression's logical scan, which only runs for len>3).
            return 0 if (arg1 and arg2) else 1
        elif op == '-o':
            # 3-argument form `[ s1 -o s2 ]`: OR of string non-emptiness.
            return 0 if (arg1 or arg2) else 1
        elif op == '<':
            # bash extension: string sorts before arg2. Codepoint (byte) order,
            # deliberately: bash's `test`/`[` `<`/`>` use BYTE order in EVERY
            # locale (verified: `[ a \< B ]` is false under both C and
            # en_US.UTF-8), UNLIKE `[[ < ]]`, which honours LC_COLLATE
            # (`[[ a < B ]]` is true under en_US.UTF-8). So this stays codepoint
            # while enhanced_test_evaluator routes `[[ < ]]` through the locale
            # service — the divergence is bash's, and psh reproduces it.
            return 0 if arg1 < arg2 else 1
        elif op == '>':
            # bash extension: string sorts after arg2; byte order (see '<').
            return 0 if arg1 > arg2 else 1
        elif op == '-eq':
            try:
                return 0 if self._to_int64(arg1) == self._to_int64(arg2) else 1
            except ValueError as e:
                self.error(f"{e}: integer expression expected", shell)
                return 2
        elif op == '-ne':
            try:
                return 0 if self._to_int64(arg1) != self._to_int64(arg2) else 1
            except ValueError as e:
                self.error(f"{e}: integer expression expected", shell)
                return 2
        elif op == '-lt':
            try:
                return 0 if self._to_int64(arg1) < self._to_int64(arg2) else 1
            except ValueError as e:
                self.error(f"{e}: integer expression expected", shell)
                return 2
        elif op == '-le':
            try:
                return 0 if self._to_int64(arg1) <= self._to_int64(arg2) else 1
            except ValueError as e:
                self.error(f"{e}: integer expression expected", shell)
                return 2
        elif op == '-gt':
            try:
                return 0 if self._to_int64(arg1) > self._to_int64(arg2) else 1
            except ValueError as e:
                self.error(f"{e}: integer expression expected", shell)
                return 2
        elif op == '-ge':
            try:
                return 0 if self._to_int64(arg1) >= self._to_int64(arg2) else 1
            except ValueError as e:
                self.error(f"{e}: integer expression expected", shell)
                return 2
        elif op == '-nt':
            # File1 newer than file2 (bash's existence-asymmetric rule).
            # Shared with [[ ]] via psh.utils.file_tests — see that module.
            return 0 if file_newer_than(arg1, arg2) else 1
        elif op == '-ot':
            # File1 older than file2 (existence-asymmetric; shared helper).
            return 0 if file_older_than(arg1, arg2) else 1
        elif op == '-ef':
            # File1 and file2 are the same file (same device + inode).
            return 0 if files_same(arg1, arg2) else 1
        else:
            self.error(f"{op}: binary operator expected", shell)
            return 2  # Unknown operator


@builtin
class BracketBuiltin(TestBuiltin):
    """[ command (alias for test).

    Subclasses TestBuiltin and evaluates through ``self`` so error messages
    carry the ``[`` prefix (its own ``name``) rather than ``test`` — matching
    bash, which reports e.g. ``[: 1: unary operator expected``.
    """

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

        # Remove [ and ], then evaluate as test (through self, so errors use
        # this builtin's '[' name prefix).
        test_args = args[1:-1]
        return self.evaluate_test(test_args, shell)
