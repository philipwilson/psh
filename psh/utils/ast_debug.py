"""AST debug output formatting."""
import sys


class UnknownASTFormat(ValueError):
    """The requested AST debug format is not one this module renders.

    Raised by :func:`print_ast_debug` for an out-of-vocabulary format name and
    caught by that same function, which warns and falls back to
    ``DebugASTVisitor``.

    The ONE reachable route is the SHELL variable: ``PSH_AST_FORMAT=bogus`` as
    an assignment on a preceding line, with ``--debug-ast`` active. Two routes
    that look plausible and are not: ``--debug-ast=bogus`` is rejected by the
    invocation parser (``invocation.py`` holds a closed format vocabulary), and
    ``PSH_AST_FORMAT`` in the process ENVIRONMENT is never consulted — this
    module reads ``shell.state.scope_manager.get_variable``, so an env var
    silently resolves to the default ``tree``. Both were replayed as
    non-reaching; ``tests/unit/utils/test_ast_debug_format_fallback_5c1.py``
    drives the real one. It is a
    distinct type so the fallback catches ONLY this — a ``TypeError`` or
    ``AttributeError`` from inside a formatter is a defect and must surface,
    not be downgraded to a warning (remediation 5C.1, MEDIUM-12).

    It subclasses ``ValueError`` deliberately: ``psh.utils`` is the runtime
    LEAF layer (``test_import_layering.py::test_utils_is_a_runtime_leaf``), so
    it cannot import ``PshError`` from ``psh.core`` at module level, and a
    builtin base keeps any external caller's expectations intact.
    """


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
            from ..parser.visualization import SExpressionRenderer
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
            # here is an out-of-vocabulary value — e.g. PSH_AST_FORMAT=bogus —
            # which the handler below turns into a warning + the
            # DebugASTVisitor fallback. That path is USER-REACHABLE and its
            # output is pinned; it is the reason this raise is TYPED rather
            # than the handler being deleted outright.
            raise UnknownASTFormat(f"unknown AST format {format_type!r}")

    except UnknownASTFormat as e:
        # Fall back to the default format for a format name we do not know.
        #
        # This handler used to read `except (ValueError, TypeError,
        # AttributeError)`, which ALSO swallowed any TypeError/AttributeError
        # raised inside ANY formatter — a real defect in a renderer was
        # downgraded to a warning and a silent fallback, so the tree looked
        # fine and the bug never surfaced. The only user-reachable member of
        # that set was this function's OWN unknown-format raise, so 5C.1 typed
        # that raise and narrowed the catch to it: the warning + fallback below
        # is byte-identical for an unknown format, and a formatter defect now
        # surfaces under the strict-errors taxonomy.
        print(f"Warning: AST formatting failed ({e}), using default format", file=sys.stderr)
        from ..visitor import DebugASTVisitor
        debug_visitor = DebugASTVisitor()
        output = debug_visitor.visit(ast)
        print(output, file=sys.stderr)

    print("======================", file=sys.stderr)
