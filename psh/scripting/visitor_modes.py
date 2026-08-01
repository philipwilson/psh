"""CLI analysis modes (--validate, --format, --metrics, --security, --lint).

These modes parse the input and run an analysis visitor over the AST instead of
executing it. They live with the rest of the script-entry plumbing: their only
caller is ``__main__.main()``, and Shell itself keeps no CLI-mode logic beyond
the ONE mode name it was constructed with (``Shell.analysis_mode``).

The parse comes from :mod:`psh.scripting.analysis_session`, which walks the
same unit boundaries execution walks and threads parse-relevant state between
units — so what a script establishes as it runs is what analysis sees. This
module owns the CLI-facing half: the per-channel entry points, the error model
(syntax error 2 / internal defect via ``report_internal_defect``), and the
mode→visitor table.

Exactly one mode can be live: ``parse_invocation`` rejects two distinct
``--mode`` flags before a Shell exists, so there is no priority chain here to
silently pick a winner.
"""
import sys
from typing import TYPE_CHECKING, Any

from ..core import report_internal_defect
from ..core.exceptions import PshError

if TYPE_CHECKING:
    from ..shell import Shell


def _parse_for_analysis(shell: 'Shell', content: str,
                        drop_dangling_at_eof: bool = False) -> Any:
    """Parse *content* into an AST for analysis, unit by unit.

    Delegates to ``analysis_session.parse_for_analysis``, which walks the same
    unit boundaries execution walks and threads parse-relevant state (extglob,
    posix, the alias table, the active parser) from each unit to the next
    WITHOUT executing anything — so a script that enables extglob on line 1 and
    uses ``+(...)`` on line 2 analyzes exactly as it runs (remediation
    MEDIUM-9(a)). Each unit goes through ``lex_parse.lex_and_parse``, the same
    heredoc-aware lex→alias→parse pipeline execution uses, so analysis honours
    ``--parser`` and threads lexer options into nested-substitution re-lexing
    (reappraisal #19 H11). A heredoc BODY stays attached to its redirect.

    Line continuations are joined per unit (as
    ``SourceProcessor._preprocess_command`` does): the lexer does NOT collapse a
    continuation in every context (``then\\``, inside ``[[ ]]``), so without this
    analysis reported false syntax errors on valid scripts that execute fine.
    ``drop_dangling_at_eof`` mirrors the execution path's stream-vs-string rule
    for a trailing backslash at true EOF.

    ``--format``'s ``expand_aliases=False`` exception lives on the session; see
    ``AnalysisSession`` for that and for the which-transitions-apply rule.
    """
    from .analysis_session import parse_for_analysis
    return parse_for_analysis(shell, content,
                              drop_dangling_at_eof=drop_dangling_at_eof)


def _report_syntax_error(location: str, exc: Exception,
                         start_line: int = 0) -> int:
    """Print an analysis syntax-error diagnostic and return 2 (bash's ``-n``
    status for a syntax error).

    A lex/parse failure must NOT escape as an uncaught Python traceback — that
    defeats the entire purpose of ``--validate`` and friends. The detail form
    (rich ParseError caret vs ``syntax error: <reason>``) is shared with the
    execution renderer through ``lex_parse.render_syntax_error_detail``, so the
    two cannot drift.

    The location carries a LINE, exactly as ``SourceProcessor._report_syntax_
    error`` renders it: the error's own absolute line when the ParseError knows
    it (bash reports the line the error is ON), else the line the failing UNIT
    started on. Analysis could not do this while the whole input was one parse
    with no per-command start line; parsing unit by unit gives it the same
    ``<source>:<line>:`` prefix execution prints.
    """
    from ..parser import ParseError
    from .lex_parse import render_syntax_error_detail
    line = start_line
    if (isinstance(exc, ParseError) and exc.error_context
            and exc.error_context.line):
        line = exc.error_context.line
    where = f"{location}:{line}" if line > 0 else location
    print(f"psh: {where}: {render_syntax_error_detail(exc)}", file=sys.stderr)
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
    from .analysis_session import AnalysisSyntaxError
    try:
        ast = _parse_for_analysis(shell, content,
                                  drop_dangling_at_eof=drop_dangling_at_eof)
        return apply_visitor_mode(shell, ast)
    except AnalysisSyntaxError as e:
        # A unit failed to parse. The session knows WHICH unit, so the
        # diagnostic can point at it the way execution's does.
        if not isinstance(e.error, (PshError, SyntaxError)):
            return report_internal_defect(
                shell.state, e.error, prefix=f"{location}: unexpected error: ",
                stream=sys.stderr)
        return _report_syntax_error(location, e.error, e.start_line)
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
    from .program_source import ProgramSource

    # Pre-flight file checks (missing 127, directory/unreadable/binary 126)
    # via the SAME validator the execution path uses.
    validation_result = shell.script_manager.validate_script_file(
        script_path)
    if validation_result != 0:
        return validation_result

    try:
        # The script-file channel of the one program-text boundary: the
        # exact text the executor sees (same decode, CR normalization, and
        # stream NUL policy — program_source.py).
        content = ProgramSource.script_file(script_path).read_text()
    except OSError as e:
        # A race (file vanished after the pre-flight) or other read error.
        print(f"psh: {script_path}: {e}", file=sys.stderr)
        return 1
    # A script file is a stream input: a dangling backslash at EOF drops,
    # exactly as the execution path treats it.
    return handle_visitor_mode_for_content(shell, content, script_path,
                                           drop_dangling_at_eof=True)


def _run_validate(ast: Any) -> int:
    from ..visitor import EnhancedValidatorVisitor
    validator = EnhancedValidatorVisitor()
    validator.visit(ast)
    print(validator.get_summary())
    error_count = sum(1 for i in validator.issues if i.severity.value == 'error')
    return 1 if error_count > 0 else 0


def _run_format(ast: Any) -> int:
    from ..visitor import FormatterVisitor
    print(FormatterVisitor().visit(ast))
    return 0


def _run_metrics(ast: Any) -> int:
    from ..visitor import MetricsVisitor
    metrics = MetricsVisitor()
    metrics.visit(ast)
    print(metrics.get_summary())
    return 0


def _run_security(ast: Any) -> int:
    from ..visitor import SecurityVisitor
    security = SecurityVisitor()
    security.visit(ast)
    print(security.get_summary())
    return 1 if security.issues else 0


def _run_lint(ast: Any) -> int:
    from ..visitor import LinterVisitor
    linter = LinterVisitor()
    linter.visit(ast)
    print(linter.get_summary())
    return 1 if linter.issues else 0


#: One runner per analysis mode, keyed by the name ``Shell.analysis_mode``
#: holds. A TABLE, not a priority chain: the if-chain this replaces resolved
#: "two modes requested" by running whichever it tested first (validate beat
#: lint, so ``psh --validate --lint f.sh`` never linted, silently). That state
#: is now rejected at invocation parsing, and a table cannot re-invent a winner.
_MODE_RUNNERS = {
    'validate': _run_validate,
    'format': _run_format,
    'metrics': _run_metrics,
    'security': _run_security,
    'lint': _run_lint,
}


def apply_visitor_mode(shell: 'Shell', ast: Any) -> int:
    """Run the shell's selected analysis visitor over *ast*.

    ``shell.analysis_mode`` is ONE mode name or None; None means no analysis
    mode was requested (status 0, nothing printed). Statuses are per mode:
    ``--validate``/``--security``/``--lint`` return 1 when they found
    something, ``--format``/``--metrics`` always 0. A syntax error is status 2
    and is reported by the caller, never here.
    """
    if shell.analysis_mode is None:
        return 0
    return _MODE_RUNNERS[shell.analysis_mode](ast)
