"""CLI analysis modes (--validate, --format, --metrics, --security, --lint).

These modes parse the input and run an analysis visitor over the AST
instead of executing it. They live with the rest of the script-entry
plumbing: their only caller is ``__main__.main()``, and Shell itself
keeps no CLI-mode logic beyond storing the flags it was constructed with.
"""
import sys
from typing import TYPE_CHECKING, Any

from ..core import report_internal_defect
from ..core.exceptions import PshError

if TYPE_CHECKING:
    from ..shell import Shell


def _parse_for_analysis(shell: 'Shell', content: str,
                        drop_dangling_at_eof: bool = False) -> Any:
    """Parse *content* into an AST for analysis via the shared pipeline.

    Routes through ``scripting.lex_parse.lex_and_parse`` — the SAME
    heredoc-aware lex→alias→parse pipeline the execution path uses — so analysis
    honours the active parser (``--parser combinator``), threads the shell's
    lexer options (extglob) into nested-substitution re-lexing, and consults the
    alias table at the seam, exactly as execution does. (This copy had drifted:
    it ignored ``--parser`` and dropped ``lexer_options`` / alias expansion —
    reappraisal #19 H11.) A heredoc BODY is still attached to its redirect
    rather than parsed as separate commands.

    Line continuations are joined first (as
    ``SourceProcessor._preprocess_command`` does): the lexer does NOT collapse a
    continuation in every context (``then\\``, inside ``[[ ]]``), so without this
    analysis reported false syntax errors on valid scripts that execute fine.
    ``drop_dangling_at_eof`` mirrors the execution path's stream-vs-string rule
    for a trailing backslash at true EOF.

    One deliberate exception: ``--format`` parses with ``expand_aliases=False``.
    The advisory modes analyze what would EXECUTE, so they see through aliases;
    but ``--format`` is a SOURCE-TO-SOURCE tool — reprinting ``zz`` as its alias
    body would rewrite the user's script, not format it (integrator ruling,
    reappraisal #19 T6).
    """
    from .input_preprocessing import process_line_continuations
    from .lex_parse import lex_and_parse
    content = process_line_continuations(
        content, drop_dangling_at_eof=drop_dangling_at_eof)
    return lex_and_parse(content, shell,
                         expand_aliases=not shell.format_only,
                         lexer_options=shell.state.options)


def _report_syntax_error(location: str, exc: Exception) -> int:
    """Print an analysis syntax-error diagnostic and return 2 (bash's ``-n``
    status for a syntax error).

    A lex/parse failure must NOT escape as an uncaught Python traceback — that
    defeats the entire purpose of ``--validate`` and friends. The detail form
    (rich ParseError caret vs ``syntax error: <reason>``) is shared with the
    execution renderer through ``lex_parse.render_syntax_error_detail``, so the
    two cannot drift.

    This renderer stays distinct from ``SourceProcessor._report_syntax_error``:
    analysis has only a bare *location* LABEL (``-c``, the script path,
    ``<stdin>``) — the whole content was parsed at once, so there is no
    per-command start line to fall back to and no ``input_source``. The
    ParseError's own ``(line N, column C)`` and source-line caret still appear
    (analysis threads ``source_text`` into the parser via ``lex_and_parse``).
    """
    from .lex_parse import render_syntax_error_detail
    print(f"psh: {location}: {render_syntax_error_detail(exc)}", file=sys.stderr)
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
    try:
        ast = _parse_for_analysis(shell, content,
                                  drop_dangling_at_eof=drop_dangling_at_eof)
        return apply_visitor_mode(shell, ast)
    except (PshError, SyntaxError) as e:
        # ParseError (PshError) and UnclosedQuoteError (PshError+SyntaxError
        # as of the r19-P6 dual-rooting) are all expected syntax errors —
        # render and return 2.
        return _report_syntax_error(location, e)
    except Exception as e:
        # Anything else escaping the parse OR a visitor is an INTERNAL DEFECT.
        # Mirror the execution boundary (SourceProcessor._classify_buffered_
        # error): re-raise it under strict-errors so the suite surfaces it, and
        # otherwise report it as an internal defect (rc 1). This replaces the
        # old `except (ValueError, TypeError)` swallow that masked visitor bugs
        # as a bland "Error parsing command" exit-1. An OSError (e.g. a failed
        # read inside a visitor) is an expected shell error, so
        # report_internal_defect renders it without re-raising.
        return report_internal_defect(
            shell.state, e, prefix=f"{location}: unexpected error: ",
            stream=sys.stderr)


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
    validation_result = shell.script_manager.validate_script_file(
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
