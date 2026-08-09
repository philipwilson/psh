"""Parse tree visualization builtin for interactive AST inspection."""

from typing import List, NamedTuple, Optional

from ..lexer import tokenize
from ..parser import ParseError, create_parser
from .base import Builtin
from .registry import builtin


class _OptionScan(NamedTuple):
    """Outcome of parse-tree's option scan.

    ``status`` is the builtin's exit code when the scan already finished the
    command (``-h``, or a usage error whose diagnostic has been printed), and
    ``None`` when the caller should carry on with the remaining fields.
    """

    status: Optional[int]
    format_type: str
    show_positions: bool
    command_args: List[str]


@builtin
class ParseTreeBuiltin(Builtin):
    """Show parse tree for shell commands."""

    name = "parse-tree"

    @property
    def synopsis(self) -> str:
        return "parse-tree [-f FORMAT] [-p] COMMAND"

    @property
    def help(self) -> str:
        return """parse-tree: parse-tree [-f FORMAT] [-p] COMMAND
    Show parse tree for shell commands.

    Parses COMMAND and displays its abstract syntax tree in the
    specified format.

    Options:
      -f FORMAT    Output format (default: tree)
                   Formats: pretty, tree, compact, dot
      -p           Show position information in the tree
      -h           Show this help

    Exit Status:
    Returns success unless a parse error occurs."""

    def _scan_options(self, args: List[str], shell) -> "_OptionScan":
        """Scan the option cluster, stopping at the first operand.

        Owns every usage diagnostic and every early exit: ``-h`` prints help,
        a bad ``-f`` argument or an unknown option is a rc-2 usage error. The
        returned :class:`_OptionScan` carries ``status`` when the builtin is
        already finished and ``None`` when the caller should go on to parse.
        """
        format_type = "tree"
        show_positions = False
        command_args: List[str] = []

        i = 1
        while i < len(args):
            arg = args[i]

            if arg == "-h" or arg == "--help":
                self.write_line(self.help, shell)
                return _OptionScan(0, format_type, show_positions, command_args)
            elif arg == "-f" or arg == "--format":
                if i + 1 >= len(args):
                    self.error("-f requires a format argument", shell)
                    return _OptionScan(2, format_type, show_positions, command_args)
                format_type = args[i + 1]
                if format_type not in ["pretty", "tree", "compact", "dot"]:
                    self.error(f"invalid format: {format_type}", shell)
                    return _OptionScan(2, format_type, show_positions, command_args)
                i += 2
            elif arg == "-p" or arg == "--positions":
                show_positions = True
                i += 1
            elif arg.startswith("-"):
                self.error(f"unknown option: {arg}", shell)
                return _OptionScan(2, format_type, show_positions, command_args)
            else:
                # Rest are command arguments
                command_args = args[i:]
                break

        if not command_args:
            self.error("no command specified", shell)
            return _OptionScan(2, format_type, show_positions, command_args)

        return _OptionScan(None, format_type, show_positions, command_args)

    def _render(self, ast, format_type: str, show_positions: bool,
                shell) -> str:
        """Render ``ast`` in the requested format.

        One arm per format. The renderer imports stay deferred and stay in
        THIS module (the module's function-level import cap is measured, not
        slack), so they travel with the arm that uses them rather than being
        hoisted as a side effect of this extraction.
        """
        if format_type == "pretty":
            from ..parser.visualization import ASTPrettyPrinter
            formatter = ASTPrettyPrinter(
                show_positions=show_positions,
                compact_mode=False
            )
            return formatter.visit(ast)

        elif format_type == "tree":
            from ..parser.visualization import AsciiTreeRenderer
            return AsciiTreeRenderer.render(
                ast,
                show_positions=show_positions,
                compact_mode=False
            )

        elif format_type == "compact":
            from ..parser.visualization import CompactAsciiTreeRenderer
            return CompactAsciiTreeRenderer.render(ast)

        elif format_type == "dot":
            from ..parser.visualization import ASTDotGenerator
            generator = ASTDotGenerator(
                show_positions=show_positions,
                color_by_type=True
            )
            output = generator.to_dot(ast)

            # Add helpful comment for DOT format
            self.write_line("# Graphviz DOT format - save to file and render with:", shell)
            self.write_line("# dot -Tpng output.dot -o ast.png && xdg-open ast.png", shell)
            self.write_line("", shell)
            return output

        # Unreachable: _scan_options rejects any format outside the four
        # above with rc 2 before this runs. Stated as a defect rather than
        # left implicit — inline, the same impossible state produced an
        # UnboundLocalError on `output`, which said nothing about why.
        raise ValueError(f"unhandled parse-tree format: {format_type!r}")

    def execute(self, args: List[str], shell) -> int:
        """Execute the parse-tree builtin."""
        if len(args) < 2:
            self.usage("usage: parse-tree [options] command", shell)
            return 2

        scan = self._scan_options(args, shell)
        if scan.status is not None:
            return scan.status
        format_type = scan.format_type
        show_positions = scan.show_positions

        # Join command arguments back into a single command
        command = " ".join(scan.command_args)

        try:
            # Parse the command, honoring the live shell options (extglob,
            # posix) so the displayed AST matches what the executor would
            # tokenize — e.g. `shopt -s extglob; parse-tree '@(a|b)'`. Thread the
            # options as lexer_options too (via the public create_parser adapter
            # over the one entry), so a NESTED substitution body re-lexes with the
            # same extglob budget (remediation R3-6b: the old direct Parser(...)
            # tokenized with the options but dropped them for the nested re-lex).
            tokens = tokenize(command, shell_options=shell.state.options)
            ast = create_parser(tokens, source_text=command,
                                lexer_options=shell.state.options).parse()

            output = self._render(ast, format_type, show_positions, shell)

            self.write_line(output, shell)
            return 0

        except ParseError as e:
            # The ONE user-input error class here. A
            # `(ValueError, TypeError, AttributeError)` net used to sit below
            # this and turn any tokenizer/parser/visitor DEFECT into a bland
            # "visualization error". It was measured unreachable from user
            # input (remediation 5C.1: 124 cells = 4 formats x 31 inputs,
            # including unclosed quotes, `$(((((`, `${x@Q}`, `;;` and `&&` --
            # the handler body never executed) and removed, so a defect now
            # surfaces under the strict-errors taxonomy instead of being
            # reported to the user as a display problem.
            self.error(f"parse error: {e}", shell)
            return 1


@builtin
class ShowASTBuiltin(Builtin):
    """Alias for parse-tree with pretty format."""

    name = "show-ast"

    @property
    def synopsis(self) -> str:
        return "show-ast [-p] COMMAND"

    @property
    def help(self) -> str:
        return """show-ast: show-ast [-p] COMMAND
    Alias for 'parse-tree -f pretty'.

    Parses COMMAND and displays the AST in pretty-printed format.
    Accepts the same options as parse-tree (except -f).

    Exit Status:
    Returns success unless a parse error occurs."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the show-ast builtin (alias for parse-tree -f pretty)."""
        # Prepend -f pretty to the arguments
        new_args = ["show-ast", "-f", "pretty"] + args[1:]

        # Delegate to parse-tree builtin
        parse_tree = ParseTreeBuiltin()
        return parse_tree.execute(new_args, shell)


@builtin
class ASTDotBuiltin(Builtin):
    """Generate Graphviz DOT format for AST."""

    name = "ast-dot"

    @property
    def synopsis(self) -> str:
        return "ast-dot [-p] COMMAND"

    @property
    def help(self) -> str:
        return """ast-dot: ast-dot [-p] COMMAND
    Generate Graphviz DOT format for AST.

    Alias for 'parse-tree -f dot'. Parses COMMAND and outputs the AST
    in DOT format suitable for rendering with Graphviz.

    Exit Status:
    Returns success unless a parse error occurs."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the ast-dot builtin (alias for parse-tree -f dot)."""
        # Prepend -f dot to the arguments
        new_args = ["ast-dot", "-f", "dot"] + args[1:]

        # Delegate to parse-tree builtin
        parse_tree = ParseTreeBuiltin()
        return parse_tree.execute(new_args, shell)
