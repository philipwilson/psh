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


def _parse_for_analysis(shell: 'Shell', content: str,
                        drop_dangling_at_eof: bool = False) -> Any:
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
    content = process_line_continuations(
        content, drop_dangling_at_eof=drop_dangling_at_eof)

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
                                    location: str,
                                    drop_dangling_at_eof: bool = False) -> int:
    """Run the selected analysis mode over *content* read from *location*.

    The SINGLE chokepoint every input channel routes through — ``-c`` command
    strings, script files, and piped stdin all analyze identical content
    identically (same output, same exit codes) and never execute it.
    *location* only labels diagnostics (``-c``, the script path, ``<stdin>``).
    ``drop_dangling_at_eof`` mirrors the execution path's per-input-mode rule
    for a trailing backslash at EOF (stream inputs — script file, stdin —
    drop it; ``-c`` keeps it literal), so analysis sees the same text
    execution would.
    """
    from ..core.exceptions import PshError
    try:
        ast = _parse_for_analysis(shell, content,
                                  drop_dangling_at_eof=drop_dangling_at_eof)
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
    """Run the selected analysis mode over a script file.

    Reads the file EXACTLY as the executor would — the same pre-flight
    ``validate_script_file`` checks (so a missing file returns 127, a
    directory/unreadable/binary file 126, matching ``psh script_path`` and
    ``bash -n`` instead of a flat 1) and the same ``FileInput`` reader
    (``errors='surrogateescape'``, CRLF-normalized). A non-UTF-8-but-valid
    script that runs fine therefore also validates fine, instead of crashing
    the analysis with a ``UnicodeDecodeError``.
    """
    from .input_sources import FileInput

    # Pre-flight file checks (missing 127, directory/unreadable/binary 126)
    # via the SAME validator the execution path uses.
    validation_result = shell.script_manager.script_validator.validate_script_file(
        script_path)
    if validation_result != 0:
        return validation_result

    try:
        with FileInput(script_path) as file_input:
            # Reconstruct the exact text the executor's accumulator sees:
            # FileInput split the raw bytes into CR-normalized physical lines.
            content = '\n'.join(file_input.lines)
    except OSError as e:
        # A race (file vanished after the pre-flight) or other read error.
        print(f"psh: {script_path}: {e}", file=sys.stderr)
        return 1
    # A script file is a stream input: a dangling backslash at EOF drops,
    # exactly as the execution path treats it.
    return handle_visitor_mode_for_content(shell, content, script_path,
                                           drop_dangling_at_eof=True)


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
