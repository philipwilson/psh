"""CLI analysis modes (--validate, --format, --metrics, --security, --lint).

These modes parse the input and run an analysis visitor over the AST
instead of executing it. They live with the rest of the script-entry
plumbing: their only caller is ``__main__.main()``, and Shell itself
keeps no CLI-mode logic beyond storing the flags it was constructed with.
"""

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..shell import Shell


def handle_visitor_mode_for_command(shell: 'Shell', command: str) -> int:
    """Run the selected analysis mode over a ``-c`` command string."""
    try:
        from ..lexer import tokenize
        from ..parser import parse

        tokens = tokenize(command)
        ast = parse(tokens)

        return apply_visitor_mode(shell, ast)
    except (ValueError, TypeError) as e:
        print(f"Error parsing command: {e}", file=sys.stderr)
        return 1


def handle_visitor_mode_for_script(shell: 'Shell', script_path: str) -> int:
    """Run the selected analysis mode over a script file."""
    try:
        # Read and parse the script file
        with open(script_path, 'r') as f:
            content = f.read()

        from ..lexer import tokenize
        from ..parser import parse

        tokens = tokenize(content)
        ast = parse(tokens)

        return apply_visitor_mode(shell, ast)
    except FileNotFoundError:
        print(f"psh: {script_path}: No such file or directory", file=sys.stderr)
        return 1
    except (ValueError, TypeError, OSError) as e:
        print(f"Error processing script: {e}", file=sys.stderr)
        return 1


def apply_visitor_mode(shell: 'Shell', ast: Any) -> int:
    """Apply the analysis visitor selected by the shell's CLI mode flags."""
    if shell.validate_only:
        from ..visitor import EnhancedValidatorVisitor
        validator = EnhancedValidatorVisitor()
        validator.visit(ast)
        print(validator.get_summary())
        error_count = sum(1 for i in validator.issues if i.severity.value == 'error')
        return 1 if error_count > 0 else 0

    if shell.format_only:
        from ..visitor import FormatterVisitor
        formatter = FormatterVisitor()
        formatted_code = formatter.visit(ast)
        print(formatted_code)
        return 0

    if shell.metrics_only:
        from ..visitor import MetricsVisitor
        metrics = MetricsVisitor()
        metrics.visit(ast)
        print(metrics.get_summary())
        return 0

    if shell.security_only:
        from ..visitor import SecurityVisitor
        security = SecurityVisitor()
        security.visit(ast)
        print(security.get_summary())
        issue_count = len(security.issues)
        return 1 if issue_count > 0 else 0

    if shell.lint_only:
        from ..visitor import LinterVisitor
        linter = LinterVisitor()
        linter.visit(ast)
        print(linter.get_summary())
        issue_count = len(linter.issues)
        return 1 if issue_count > 0 else 0

    return 0
