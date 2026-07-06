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


def _parse_for_analysis(shell: 'Shell', content: str) -> Any:
    """Parse *content* into an AST for analysis, heredoc-aware.

    Mirrors the execution path's parsing: when the input contains a heredoc,
    tokenize/parse WITH heredoc collection so a heredoc BODY is attached to its
    redirect instead of being parsed as separate commands. (Bare tokenize/parse
    skips heredoc collection, which made --security/--validate/--metrics/--lint/
    --format mis-analyze every heredoc body — e.g. `rm -rf /` in heredoc data
    reported as a real command.)
    """
    from ..utils import contains_heredoc

    # Join backslash-newline continuations before tokenizing, exactly as the
    # execution path does (SourceProcessor._preprocess_command). The lexer
    # does NOT collapse a continuation in every context (`then\`, inside
    # `[[ ]]`), so without this the analysis modes reported false syntax
    # errors on valid scripts that execute fine.
    from .input_preprocessing import process_line_continuations
    content = process_line_continuations(content)

    if contains_heredoc(content):
        from ..lexer import tokenize_with_heredocs
        from ..parser import parse_with_heredocs
        tokens, heredoc_map = tokenize_with_heredocs(
            content, strict=shell.state.options.get('posix', False),
            shell_options=shell.state.options)
        return parse_with_heredocs(tokens, heredoc_map)
    from ..lexer import tokenize
    from ..parser import parse
    # Pass shell_options so analysis/validation tokenizes in the SAME mode the
    # execution path would (posix/extglob) — mirroring the heredoc branch above.
    return parse(tokenize(content, shell_options=shell.state.options))


def _report_syntax_error(location: str, exc: Exception) -> int:
    """Print a syntax-error diagnostic and return 2 (bash's exit status for a
    syntax error under ``-n``).

    A lex/parse failure must NOT escape as an uncaught Python traceback — that
    defeats the entire purpose of ``--validate`` and friends. For a ParseError
    this now renders the FULL diagnostic (position, source line, caret,
    suggestions) — the same rich form the execution path prints — instead of
    the bare one-line reason it used to show.
    """
    from ..parser import ParseError
    message = exc.render() if isinstance(exc, ParseError) else f"syntax error: {exc}"
    print(f"psh: {location}: {message}", file=sys.stderr)
    return 2


def handle_visitor_mode_for_content(shell: 'Shell', content: str,
                                    location: str) -> int:
    """Run the selected analysis mode over *content* read from *location*.

    The SINGLE chokepoint every input channel routes through — ``-c`` command
    strings, script files, and piped stdin all analyze identical content
    identically (same output, same exit codes) and never execute it.
    *location* only labels diagnostics (``-c``, the script path, ``<stdin>``).
    """
    from ..core.exceptions import PshError
    try:
        ast = _parse_for_analysis(shell, content)
        return apply_visitor_mode(shell, ast)
    except (PshError, SyntaxError) as e:
        # ParseError (PshError), LexerError (PshError+SyntaxError), and
        # UnclosedQuoteError (SyntaxError) are all expected syntax errors.
        return _report_syntax_error(location, e)
    except (ValueError, TypeError) as e:
        print(f"Error parsing command: {e}", file=sys.stderr)
        return 1


def handle_visitor_mode_for_command(shell: 'Shell', command: str) -> int:
    """Run the selected analysis mode over a ``-c`` command string."""
    return handle_visitor_mode_for_content(shell, command, "-c")


def handle_visitor_mode_for_script(shell: 'Shell', script_path: str) -> int:
    """Run the selected analysis mode over a script file."""
    try:
        with open(script_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"psh: {script_path}: No such file or directory", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        # ValueError covers UnicodeDecodeError on a non-UTF-8 file.
        print(f"Error processing script: {e}", file=sys.stderr)
        return 1
    return handle_visitor_mode_for_content(shell, content, script_path)


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
