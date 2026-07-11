"""AST debug output formatting."""
import sys


def print_ast_debug(ast, ast_format, shell) -> None:
    """Print AST debug output in the requested format.

    Args:
        ast: The AST node to print.
        ast_format: Format string from command line (e.g. 'pretty', 'tree', 'dot').
        shell: Shell instance for reading PSH_AST_FORMAT variable and active parser.
    """
    # Check for format from command line, then from PSH_AST_FORMAT variable, then default
    format_type = ast_format
    if not format_type:
        format_type = shell.state.scope_manager.get_variable('PSH_AST_FORMAT') or 'tree'

    # Include parser name in debug header
    parser_name = shell.active_parser
    print(f"=== AST Debug Output ({parser_name}) ===", file=sys.stderr)

    try:
        if format_type == 'pretty':
            from ..parser.visualization import ASTPrettyPrinter
            formatter = ASTPrettyPrinter(
                indent_size=2,
                show_positions=True,
                compact_mode=False
            )
            output = formatter.visit(ast)
            print(output, file=sys.stderr)

        elif format_type == 'tree':
            from ..parser.visualization import AsciiTreeRenderer
            output = AsciiTreeRenderer.render(
                ast,
                show_positions=True,
                compact_mode=False
            )
            print(output, file=sys.stderr)

        elif format_type == 'compact':
            from ..parser.visualization import CompactAsciiTreeRenderer
            output = CompactAsciiTreeRenderer.render(ast)
            print(output, file=sys.stderr)

        elif format_type == 'dot':
            from ..parser.visualization import ASTDotGenerator
            generator = ASTDotGenerator(
                show_positions=True,
                color_by_type=True
            )
            output = generator.to_dot(ast)
            print(output, file=sys.stderr)
            print("\n# Save to file and visualize with:", file=sys.stderr)
            print("# dot -Tpng output.dot -o ast.png", file=sys.stderr)
            print("# xdg-open ast.png", file=sys.stderr)

        elif format_type == 'sexp':
            from ..parser.visualization.sexp_renderer import SExpressionRenderer
            output = SExpressionRenderer.render(
                ast,
                compact_mode=False,
                max_width=80,
                show_positions=True
            )
            print(output, file=sys.stderr)

        else:
            # An unknown format is explicit, not silently rendered as tree.
            # 'tree' is already the default when no format is requested
            # (see the PSH_AST_FORMAT fallback above); the only way to reach
            # here is an out-of-vocabulary value, which the except below turns
            # into a warning + the DebugASTVisitor fallback.
            raise ValueError(f"unknown AST format {format_type!r}")

    except (ValueError, TypeError, AttributeError) as e:
        # Fallback to default format if new formatters fail
        print(f"Warning: AST formatting failed ({e}), using default format", file=sys.stderr)
        from ..visitor import DebugASTVisitor
        debug_visitor = DebugASTVisitor()
        output = debug_visitor.visit(ast)
        print(output, file=sys.stderr)

    print("======================", file=sys.stderr)
