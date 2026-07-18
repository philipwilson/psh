"""Nested-substitution error-timing conformance (nested-program campaign).

Bash validates the syntax of *modern* command and process substitutions
(``$(...)``, ``<(...)``, ``>(...)``) when it READS the enclosing command, not
when it later expands them. An invalid body therefore rejects the whole input
buffer before ANY command in it executes, and bash's read-time check does this
even when the substitution would never run (``false && echo $(if)``).

psh historically stored the substitution body as raw text
(``CommandSubstitution.command``) and parsed it only at expansion time, so
earlier commands in the buffer had already executed and the syntax error
surfaced mid-stream with the wrong exit status. This module pins bash's timing.

Two groups:

* ERROR-TIMING  — invalid modern substitutions must reject at parse time
  (nothing executes; exit status is bash's). Campaign S3 extended this to the
  syntax-bearing regions whose own grammar stays lazy — parameter-expansion
  operands, arithmetic templates, and array subscripts — which previously
  routed through the raw-string engines and were documented divergences.
* BEHAVIOR LOCKS — valid substitutions, alias timing, legacy-backtick
  continue-around-errors, heredoc bodies, byte content, deep nesting, and
  incomplete-input handling must stay identical to bash / to psh-today.

The exit-CODE divergence (bash 127 vs psh's uniform 2 in string channels) and
the heredoc-body case remain documented divergences at the bottom (the 127
mapping is I3's job; the S3 timing match holds regardless). The broader S3
timing matrix (quoting × channel × dead-branch × backtick-vs-$()) lives in
``test_syntax_template_timing_conformance.py``.

All cases drive full-buffer execution through subprocesses so psh and bash are
directly comparable (see CLAUDE.md bash-verification workflow).
"""

import os
import subprocess
import sys
import tempfile

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path

# Run the worktree's psh, not any editable-installed copy in site-packages.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_ENV = dict(os.environ, PYTHONPATH=_ROOT)


def _psh_c(cmd):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        capture_output=True, text=True, timeout=30,
        cwd=_ROOT, env=_ENV, stdin=subprocess.DEVNULL)


def _bash_c(cmd):
    return subprocess.run(
        [BASH, "-c", cmd], capture_output=True, text=True, timeout=30,
        cwd=_ROOT, stdin=subprocess.DEVNULL)


def _psh_stdin(script):
    return subprocess.run(
        [sys.executable, "-m", "psh"], input=script,
        capture_output=True, text=True, timeout=30, cwd=_ROOT, env=_ENV)


def _bash_stdin(script):
    return subprocess.run(
        [BASH], input=script, capture_output=True, text=True, timeout=30,
        cwd=_ROOT)


def _run_file(argv_prefix, script, env=None):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                     dir=os.path.join(_ROOT, "tmp")) as f:
        f.write(script)
        path = f.name
    try:
        return subprocess.run(
            argv_prefix + [path], capture_output=True, text=True, timeout=30,
            cwd=_ROOT, env=env, stdin=subprocess.DEVNULL)
    finally:
        os.unlink(path)


# ==========================================================================
# ERROR-TIMING: invalid modern substitution rejects the whole buffer.
# (Was xfail(strict) before the nested-program + S3 template work landed.)
# ==========================================================================

# Each entry is (id, command-run-via -c). In every case bash rejects the whole
# buffer (nothing executes), so asserting psh matches bash's (rc, stdout) pins
# the timing. Positions cover: bare arg, parameter-expansion word, process subs,
# nested $(), assignment value, redirect target, case subject, if/while headers,
# function body, and several distinct invalid inner tokens.
_ERROR_TIMING_C = [
    ("bare_arg", "echo before; echo $(if); echo after"),
    ("procsub_in", "echo before; cat <(if); echo after"),
    ("procsub_out", "echo before; echo hi >(if); echo after"),
    ("nested_cmdsub", "echo before; echo $( $(if) ); echo after"),
    ("assignment_value", "echo before; x=$(if); echo after rc=$?"),
    ("redirect_target", "echo before; echo x > $(if); echo after"),
    ("case_subject", "echo before; case $(if) in *) echo x;; esac; echo after"),
    ("if_header", "echo before; if $(if); then echo t; fi; echo after"),
    ("while_header", "echo before; while $(if); do echo t; break; done; echo z"),
    ("function_body", "echo before; f() { echo $(if); }; f; echo after"),
    ("inner_fi", "echo before; echo $(fi); echo after"),
    ("inner_done", "echo before; echo $(done); echo after"),
    ("inner_then", "echo before; echo $(then); echo after"),
    ("inner_leading_pipe", "echo before; echo $(| cat); echo after"),
    ("inner_leading_semi", "echo before; echo $(; echo x); echo after"),
    # Caught even when the substitution would NEVER execute (read-time check).
    ("never_exec_false_and", "false && echo $(if); echo done"),
    ("never_exec_if_false", "if false; then echo $(if); fi; echo done"),
    ("never_exec_after_return", "f() { return 0; echo $(if); }; f; echo done"),
    # Alias-injected syntax is NOT consulted by bash's read-time check, so the
    # bare `done` is a syntax error at parse time (psh-today accepts it because
    # it parses the body at exec time WITH the alias — the fix aligns to bash).
    ("alias_injected_syntax",
     "shopt -s expand_aliases; alias beg='for i in 1 2; do'; "
     "echo $(beg echo hi; done); echo after"),
    # Campaign S3: the nested-shell-grammar check now also covers the syntax-
    # bearing regions whose OWN grammar stays lazy — parameter-expansion
    # operands, arithmetic templates ($(( )), (( )), C-style for clauses), and
    # array subscripts. These were documented divergences until S3 (they routed
    # through the raw-string operand/arith/subscript engines); they now reject
    # at read time like bash. (Backticks and single-quoted bodies stay lazy —
    # pinned separately in test_syntax_template_timing_conformance.py.)
    ("operand_default", "echo before; x=set; echo ${x:-$(if)}; echo after"),
    ("operand_default_unset", "echo before; unset x; echo ${x:-$(if)}; echo after"),
    ("operand_assign", "echo before; unset x; echo ${x:=$(if)}; echo after"),
    ("operand_altern", "echo before; x=y; echo ${x:+$(if)}; echo after"),
    ("operand_error_op", "echo before; x=y; echo ${x:?$(if)}; echo after"),
    ("operand_prefix_removal", "echo before; x=abc; echo ${x#$(if)}; echo after"),
    ("operand_suffix_removal", "echo before; x=abc; echo ${x%$(if)}; echo after"),
    ("operand_substitute", "echo before; x=abc; echo ${x/$(if)/z}; echo after"),
    ("operand_dquoted", "echo before; x=set; echo ${x:-\"$(if)\"}; echo after"),
    ("operand_nested", "echo before; x=set; echo ${x:-${y:-$(if)}}; echo after"),
    ("operand_procsub", "echo before; x=set; echo ${x:-<(if)}; echo after"),
    ("arith_expansion", "echo before; echo $(( $(if) + 1 )); echo after"),
    ("arith_command", "echo before; (( $(if) )); echo after"),
    ("arith_param_in_arith", "echo before; echo $(( ${x:-$(if)} )); echo after"),
    ("cstyle_for_init", "echo before; for ((i=$(if); i<2; i++)); do echo x; done; echo after"),
    ("cstyle_for_cond", "echo before; for ((i=0; $(if); i++)); do echo x; done; echo after"),
    ("cstyle_for_update", "echo before; for ((i=0; i<2; i=$(if))); do echo x; done; echo after"),
    ("subscript_ref", "echo before; a=(1 2 3); echo ${a[$(if)]}; echo after"),
    ("subscript_assign", "echo before; a[$(if)]=v; echo after"),
    ("subscript_arith_lvalue", "echo before; (( a[$(if)] = 1 )); echo after"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cid,cmd", _ERROR_TIMING_C, ids=[c[0] for c in _ERROR_TIMING_C])
def test_invalid_modern_substitution_rejects_whole_buffer(cid, cmd):
    p = _psh_c(cmd)
    b = _bash_c(cmd)
    # bash rejects the whole -c buffer before running anything.
    assert b.stdout == "" and b.returncode != 0, (cid, b.stdout, b.returncode)
    # psh must now do the same: nothing executes, non-zero exit. (The exact
    # code is a separate, documented divergence — bash uses 127 for a
    # cmdsub-body syntax error in -c mode; see the divergence test below.)
    assert p.stdout == "", (cid, "stdout not empty", repr(p.stdout))
    assert p.returncode != 0, (cid, "rc", p.returncode)


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_invalid_cmdsub_rejects_in_stdin_script():
    # stdin is read command-by-command, so "echo before" runs, then the next
    # command's cmdsub syntax error aborts — bash and psh agree here.
    script = "echo before\necho $(if)\necho after\n"
    p = _psh_stdin(script)
    b = _bash_stdin(script)
    assert b.stdout == "before\n", b.stdout
    assert p.stdout == b.stdout, repr(p.stdout)
    assert p.returncode == b.returncode != 0, (p.returncode, b.returncode)
    assert "after" not in p.stdout


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_invalid_cmdsub_rejects_in_script_file():
    script = "echo before\necho $(if)\necho after\n"
    p = _run_file([sys.executable, "-m", "psh"], script, env=_ENV)
    b = _run_file([BASH], script)
    assert p.returncode == b.returncode != 0, (p.returncode, b.returncode)
    # "before" ran (command-by-command); "after" did not (error aborted it).
    assert p.stdout == b.stdout == "before\n", (repr(p.stdout), repr(b.stdout))


# ==========================================================================
# BEHAVIOR LOCKS: these already match bash and MUST stay matching.
# ==========================================================================

_VALID_MATCH = [
    ("valid_cmdsub", "echo before; echo $(echo hi); echo after"),
    ("valid_procsub_in", "echo before; cat <(echo hi); echo after"),
    ("valid_nested_cmdsub", "echo $(echo $(echo deep))"),
    ("valid_triple_nested", "echo $(echo $(echo $(printf x)))"),
    ("valid_backtick", "echo before; echo `echo hi`; echo after"),
    ("valid_multiline_cmdsub", "echo $(\necho one\necho two\n)"),
    ("valid_heredoc_in_cmdsub", "echo $(cat <<EOF\nhi\nEOF\n)"),
    ("valid_cmdsub_in_dquotes", 'echo "x=$(echo hi)y"'),
    ("valid_cmdsub_with_pipe", "echo $(echo hi | tr a-z A-Z)"),
    ("valid_cmdsub_control", "echo $(if true; then echo yes; fi)"),
    ("valid_cmdsub_loop", "echo $(for i in 1 2 3; do echo $i; done)"),
    ("valid_cmdsub_case", "echo $(case x in x) echo m;; esac)"),
    ("valid_cmdsub_semicolons", "echo $(echo a; echo b; echo c)"),
    ("valid_assignment_cmdsub", "x=$(echo hi); echo $x"),
    ("valid_param_default_cmdsub", "echo ${u:-$(echo dflt)}"),
    ("valid_redirect_target_cmdsub", "d=$(pwd); echo hi > $(echo /dev/null); echo ok"),
    ("valid_procsub_diff_style", "cat <(echo a) <(echo b)"),
    # Legacy backtick: bash CONTINUES around an inner syntax error (it defers
    # parts of backtick parsing) — the buffer is NOT rejected. psh matches.
    ("backtick_inner_error_continues", "echo before; echo `if`; echo after"),
    # Unbalanced outer paren is caught by the OUTER lexer/parser already.
    ("unbalanced_outer_paren", "echo before; echo $(echo x)); echo after"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cid,cmd", _VALID_MATCH, ids=[c[0] for c in _VALID_MATCH])
def test_substitution_behavior_matches_bash(cid, cmd):
    p = _psh_c(cmd)
    b = _bash_c(cmd)
    assert p.stdout == b.stdout, (cid, "stdout", repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode, (cid, "rc", p.returncode, b.returncode)


# Alias timing: cmdsub bodies execute against the RUNTIME alias table. These
# pin that behavior (which the fix must NOT change).
_ALIAS_MATCH = [
    ("alias_active_in_cmdsub",
     "shopt -s expand_aliases; alias ll='echo LL'; echo $(ll)"),
    ("alias_defined_prior_line",
     "shopt -s expand_aliases\nalias foo='echo A'\necho $(foo)"),
    ("alias_defined_then_undefined",
     "shopt -s expand_aliases; alias foo='echo A'; unalias foo; echo $(foo)"),
    ("alias_used_before_def",
     "shopt -s expand_aliases; echo $(foo); alias foo='echo A'"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cid,cmd", _ALIAS_MATCH, ids=[c[0] for c in _ALIAS_MATCH])
def test_alias_timing_in_cmdsub_matches_bash(cid, cmd):
    p = _psh_c(cmd)
    b = _bash_c(cmd)
    assert p.stdout == b.stdout, (cid, repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode, (cid, p.returncode, b.returncode)


# Command-substitution status semantics ($?, pure-assignment status).
_STATUS_MATCH = [
    ("cmdsub_status_success", "echo $(true); echo $?"),
    ("cmdsub_status_failure", "echo $(false); echo $?"),
    ("cmdsub_exit_code_prop", "x=$(exit 7); echo $?"),
    ("cmdsub_in_command_status", "$(false) 2>/dev/null; echo done"),
    ("cmdsub_last_of_body", "echo $(false; true); echo $?"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cid,cmd", _STATUS_MATCH, ids=[c[0] for c in _STATUS_MATCH])
def test_cmdsub_status_matches_bash(cid, cmd):
    p = _psh_c(cmd)
    b = _bash_c(cmd)
    assert p.stdout == b.stdout, (cid, repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode, (cid, p.returncode, b.returncode)


# Trap and multi-line body semantics inside command substitution.
_MISC_MATCH = [
    ("trap_exit_in_cmdsub", 'x=$(trap "echo T" EXIT; echo body); echo "[$x]"'),
    ("cmdsub_strips_trailing_newlines", "printf '<%s>' \"$(printf 'a\\n\\n\\n')\""),
    ("cmdsub_preserves_internal_newlines", 'echo "$(printf "a\\nb")"'),
    ("procsub_reads_body_output", "wc -l < <(printf 'a\\nb\\nc\\n')"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cid,cmd", _MISC_MATCH, ids=[c[0] for c in _MISC_MATCH])
def test_cmdsub_misc_matches_bash(cid, cmd):
    p = _psh_c(cmd)
    b = _bash_c(cmd)
    assert p.stdout == b.stdout, (cid, repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode, (cid, p.returncode, b.returncode)


def test_cmdsub_nonutf8_byte_roundtrips():
    """A non-UTF-8 byte survives command substitution (surrogateescape).

    psh-only lock (bash's byte handling is separately covered); pins that the
    fix does not disturb the v0.651 byte path.
    """
    r = _psh_c(r"""x=$(python3 -c 'import os;os.write(1,bytes([255]))'); printf %s "$x" | od -An -tx1""")
    assert "ff" in r.stdout, r.stdout


# ==========================================================================
# INCOMPLETE INPUT: an unterminated `$(` is a continuation / syntax error in
# both shells and must stay so (PS2 path via the CommandAccumulator).
# ==========================================================================

@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_unterminated_cmdsub_is_error_not_silent():
    p = _psh_stdin("echo $(\n")
    b = _bash_stdin("echo $(\n")
    assert p.returncode != 0 and b.returncode != 0, (p.returncode, b.returncode)
    assert p.stdout == "" == b.stdout


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_unterminated_cmdsub_c_mode_is_error():
    for cmd in ("echo $(", "echo $(foo", "cat <(echo"):
        p = _psh_c(cmd)
        b = _bash_c(cmd)
        assert p.returncode != 0 and b.returncode != 0, (cmd, p.returncode, b.returncode)


# ==========================================================================
# DEEP NESTING: valid deep `$(...)` works; over-deep yields a CLEAN parse
# error (a ParseError / "too deeply nested"), never a Python traceback.
# ==========================================================================

def test_deep_valid_cmdsub_nesting_works():
    depth = 40
    cmd = "echo " + "$(echo " * depth + "hi" + ")" * depth
    r = _psh_c(cmd)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "hi\n", repr(r.stdout)


def test_over_deep_cmdsub_nesting_is_clean_error():
    # Beyond MAX_SUBSTITUTION_NESTING psh reports a clean ParseError (never a
    # Python traceback) and bounds the interim re-parse cost. bash accepts far
    # deeper nesting — a documented divergence of the extract-and-reparse
    # approach until the lexer gains token-level substitution recursion.
    depth = 150
    cmd = "echo " + "$(echo " * depth + "hi" + ")" * depth
    r = _psh_c(cmd)
    assert r.returncode != 0, r.stdout
    assert "Traceback (most recent call last)" not in r.stderr, r.stderr[-400:]
    assert "nested too deeply" in r.stderr, r.stderr[-400:]


# ==========================================================================
# DOCUMENTED DIVERGENCES (intentionally OUT of scope: raw-string engine, not
# the Word AST). Pin the boundary so it stays explicit.
# ==========================================================================

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", [
    "echo $(if)",                       # top-level command sub
    "cat <(if)",                        # process sub
    "x=set; echo ${x:-$(if)}",          # S3: parameter-expansion operand
    "echo $(( $(if) + 1 ))",            # S3: arithmetic template
    "a=(1 2); echo ${a[$(if)]}",        # S3: array subscript
    "a[$(if)]=v",                       # S3: element-assignment subscript
])
def test_divergence_c_mode_exit_code_is_127_in_bash(cmd):
    """A substitution-body syntax error in ``bash -c`` exits 127 (a quirk of
    bash's string-execution channels: -c/eval/source; stdin/file exit 2). psh
    uses its uniform syntax-error code 2 in every channel. The TIMING match
    (nothing executes, whole buffer rejected at read time) holds across the
    whole S3 family; only the exact code differs, and that 127/frame-abort
    mapping is the I3 consumer of S3's typed SubstitutionSyntaxError."""
    b = _bash_c(cmd)
    p = _psh_c(cmd)
    assert b.returncode == 127                  # bash -c quirk (all substitutions)
    assert p.returncode == 2                     # psh: uniform syntax-error code
    assert b.stdout == p.stdout == ""            # neither executes anything


# ==========================================================================
# LEXER-OPTION FIDELITY: the nested parse must re-lex the substitution body
# with the SAME shell options (extglob) as the outer command. `shopt -s
# extglob` on its own line runs before the next line — and its $() body — is
# parsed, so the body's `@(a|b)` is a valid extglob pattern at parse time.
# Regression pin for the lexer_options threading (create_parser AND the
# CommandAccumulator trial parse); dropping either wrongly rejects the body.
# ==========================================================================

_EXTGLOB_VALID = (
    "shopt -s extglob\n"
    "echo $(case a in @(a|b)) echo m;; *) echo n;; esac)")


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_extglob_pattern_in_cmdsub_relexes_via_c():
    p = _psh_c(_EXTGLOB_VALID)
    b = _bash_c(_EXTGLOB_VALID)
    assert p.stdout == b.stdout == "m\n", (repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode == 0, (p.returncode, b.returncode)


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_extglob_pattern_in_cmdsub_relexes_via_script_file():
    # The script-file path re-parses through the source processor rather than
    # reusing the accumulator's trial AST, so this pins the create_parser
    # threading site independently of the -c/accumulator path above.
    p = _run_file([sys.executable, "-m", "psh"], _EXTGLOB_VALID + "\n", env=_ENV)
    b = _run_file([BASH], _EXTGLOB_VALID + "\n")
    assert p.stdout == b.stdout == "m\n", (repr(p.stdout), repr(b.stdout))
    assert p.returncode == b.returncode == 0, (p.returncode, b.returncode)


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_extglob_cmdsub_body_syntax_error_still_rejects():
    # extglob is enabled for the body, but a genuine syntax error inside the
    # (properly closed) substitution must still reject at parse — the re-lex
    # does not make the nested parser lenient. `before` runs (line 2), the
    # cmdsub on line 3 rejects, `after` never runs.
    cmd = ("shopt -s extglob\necho before\n"
           "echo $(case a in @(a|b)) echo m;; esac; fi)\necho after")
    p = _psh_c(cmd)
    b = _bash_c(cmd)
    assert b.returncode != 0 and "after" not in b.stdout      # bash rejects
    assert p.returncode != 0, p.stdout                         # psh rejects too
    assert "after" not in p.stdout, repr(p.stdout)
    assert "Traceback (most recent call last)" not in p.stderr, p.stderr[-300:]


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_param_expansion_word_cmdsub_now_rejects_at_read_time():
    """CLOSED S3 divergence: `${x:-$(if)}` now rejects at read time like bash.

    The ``$(if)`` lives inside the parameter-expansion default WORD. Until S3,
    param_parser stored it as a raw string and the operand engine expanded it at
    runtime, so psh continued past it. S3's WordTemplate validates the nested
    modern substitution when the command is READ, so the whole buffer is
    rejected before anything runs — matching bash. (rc differs: bash 127 in -c,
    psh's uniform 2 — see the 127 family pin above.)"""
    cmd = "echo before; echo ${x:-$(if)}; echo after"
    b = _bash_c(cmd)
    p = _psh_c(cmd)
    assert b.returncode != 0 and b.stdout == ""     # bash rejects whole buffer
    assert p.returncode != 0 and p.stdout == ""     # psh now rejects it too
    assert "before" not in p.stdout and "after" not in p.stdout


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_arith_embedded_cmdsub_now_rejects_at_read_time():
    """CLOSED S3 divergence: `$(( $(if) ))` now rejects at read time like bash.

    The inner $() sits inside an ARITH_EXPANSION token. S3's ArithmeticTemplate
    validates nested modern substitutions in the arithmetic region at read time
    (the arithmetic grammar itself stays lazy), so the buffer is rejected before
    anything runs — matching bash."""
    cmd = "echo before; echo $(( $(if) )); echo after"
    b = _bash_c(cmd)
    p = _psh_c(cmd)
    assert b.returncode != 0 and b.stdout == ""     # bash rejects whole buffer
    assert p.returncode != 0 and p.stdout == ""     # psh now rejects it too
    assert "before" not in p.stdout


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_divergence_alias_local_to_cmdsub_body():
    """`$(alias h=...; h)`: bash does not activate an alias defined in the SAME
    read unit (h -> command not found), while psh expands aliases over the whole
    parse unit (h -> H). This is a PRE-EXISTING alias-granularity divergence,
    unrelated to nested substitutions and unchanged by this campaign (execution
    still re-parses the body against runtime alias state)."""
    cmd = "shopt -s expand_aliases; echo $(alias h='echo H'; h)"
    b = _bash_c(cmd)
    p = _psh_c(cmd)
    assert b.stdout == "\n"           # bash: h not found -> empty substitution
    assert p.stdout == "H\n"          # psh: whole-unit alias expansion (today)


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_divergence_heredoc_body_cmdsub_stays_runtime():
    """A `$(if)` inside a heredoc BODY is expanded by the raw-string engine at
    execution time in both shells (rc=0, execution continues). Only the exact
    emitted content differs (out of scope)."""
    cmd = "echo before\ncat <<EOF\n$(if)\nEOF\necho after"
    b = _bash_c(cmd)
    p = _psh_c(cmd)
    assert b.returncode == 0 and p.returncode == 0   # both continue past it
    assert "before" in p.stdout and "after" in p.stdout
