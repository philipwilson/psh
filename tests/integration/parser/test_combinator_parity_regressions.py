"""Combinator-parser parity regressions (ground-up reappraisal, v0.276.0).

The 2026-06-10 reappraisal found the combinator parser had drifted behind
two recursive-descent fixes from v0.266–v0.269:

1. Function-definition trailing redirects were applied at *definition*
   time instead of at each call (``f() { ...; } > file`` created the file
   immediately and ``f`` wrote to stdout).
2. Case patterns lost their quote context, so quoted glob characters
   stayed active (``case ab in "a*")`` wrongly matched).

These tests run the same scripts under bash, psh --parser rd, and
psh --parser combinator and require all three to agree.
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path

PSH = [sys.executable, '-m', 'psh']


def run_bash(cmd, cwd=None):
    return subprocess.run([BASH, '-c', cmd], capture_output=True,
                          text=True, cwd=cwd)


def run_psh(cmd, parser, cwd=None):
    return subprocess.run(PSH + ['--parser', parser, '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


def assert_three_way(cmd, cwd=None):
    """bash, rd, and combinator must produce identical stdout and rc."""
    bash = run_bash(cmd, cwd=cwd)
    rd = run_psh(cmd, 'rd', cwd=cwd)
    comb = run_psh(cmd, 'combinator', cwd=cwd)
    assert rd.stdout == bash.stdout, (
        f"rd vs bash for {cmd!r}: {rd.stdout!r} != {bash.stdout!r}")
    assert comb.stdout == bash.stdout, (
        f"combinator vs bash for {cmd!r}: {comb.stdout!r} != {bash.stdout!r}")
    assert rd.returncode == bash.returncode
    assert comb.returncode == bash.returncode


class TestCasePatternQuoteContext:
    """Quoted case-pattern text must match literally; unquoted globs stay active."""

    def test_quoted_glob_is_literal(self):
        assert_three_way(
            'case "ab" in "a*") echo literal;; a*) echo glob;; esac')

    def test_quoted_glob_matches_itself(self):
        assert_three_way(
            'case "a*" in "a*") echo literal;; *) echo other;; esac')

    def test_quoted_variable_pattern_is_literal(self):
        assert_three_way(
            'x=foo; case foo in "$x") echo var-literal;; *) echo other;; esac')

    def test_unquoted_glob_still_active(self):
        assert_three_way('case abc in a?c) echo glob;; *) echo no;; esac')

    def test_alternation_mixed_quoting(self):
        assert_three_way(
            'case "x*" in a|"x*") echo second;; *) echo other;; esac')


class TestKeywordSpelledArgumentInBody:
    """An argument that merely spells like a terminator keyword is a word.

    The R9.C3 recursion-based compound-body parser fixed a slicer bug: the old
    token-slicer matched ``done``/``fi`` by value across the whole body span, so
    ``echo done`` inside a loop body was mis-detected as the loop terminator.
    The recursion only checks for terminators at statement-start position, so
    such arguments are consumed as plain words — matching bash and rd.
    """

    def test_done_as_argument_in_while_body(self):
        assert_three_way('while true; do echo done; break; done')

    def test_done_as_argument_in_for_body(self):
        assert_three_way('for i in 1 2; do echo done; done')

    def test_fi_as_argument_in_then_body(self):
        assert_three_way('if true; then echo fi; fi')

    def test_keyword_argument_in_nested_body(self):
        assert_three_way('for i in 1; do if true; then echo done; fi; done')

    def test_esac_as_argument_in_case_body(self):
        assert_three_way('case x in a) echo esac;; *) echo other;; esac')

    def test_close_brace_as_argument_in_function_body(self):
        # R11.P3 retired the function-body brace-slicer; a '}' that is an
        # argument ('echo }') is no longer mis-read as the body's closer.
        assert_three_way('f() { echo }; }; f')

    def test_nested_brace_group_in_function_body(self):
        assert_three_way('f() { { echo hi; }; }; f')


class TestLineContinuationAfterOperator:
    """A newline after a pipe / and-or operator continues the command.

    R12.A: the combinator pipeline/and-or parsers did not skip a NEWLINE after
    `|`/`|&`/`&&`/`||`, so a command split across a line after the operator
    (`echo a |\\ncat`) was rejected under --parser combinator while bash and rd
    accept it. Fixed by skipping NEWLINE tokens after the operator.
    """

    def test_newline_after_pipe(self):
        assert_three_way('echo a |\ncat')

    def test_newline_after_and_and(self):
        assert_three_way('echo a &&\necho b')

    def test_newline_after_or_or(self):
        assert_three_way('false ||\necho c')

    def test_newline_in_multi_stage_pipe(self):
        assert_three_way('echo x |\ntr a-z A-Z |\ncat')


class TestKeywordSpelledArgumentInCondition:
    """A 'do'/'then' spelled as an argument in a loop/if CONDITION is a word.

    The R11.P3 condition-header recursion fixed the symmetric slicer bug: the
    old token-slicer ended the condition at the first ``do``/``then`` by value,
    so ``while echo do; ...`` (do as an argument to echo) was mis-detected as
    the loop's ``do`` keyword. Parsing the condition by recursion only stops at
    a command-position terminator, so such arguments are plain words — matching
    bash and rd.
    """

    def test_do_as_argument_in_while_condition(self):
        assert_three_way('while echo do; false; do echo body; break; done')

    def test_do_as_argument_in_until_condition(self):
        assert_three_way('until echo do; true; do echo body; done')

    def test_then_as_argument_in_if_condition(self):
        assert_three_way('if echo then; then echo hi; fi')

    def test_then_as_argument_in_elif_condition(self):
        assert_three_way('if false; then :; elif echo then; then echo e; fi')

    def test_multi_statement_condition_still_works(self):
        assert_three_way('while echo a; false; do echo body; break; done')


class TestFunctionDefinitionRedirects:
    """Redirects on a definition apply at each call, not at definition."""

    def test_posix_function_redirect_applies_per_call(self, tmp_path):
        cmd = ('f() { echo hi; } > out.txt; '
               'ls out.txt 2>/dev/null && echo created-at-def; '
               'f; cat out.txt')
        bash_dir = tmp_path / 'bash'
        comb_dir = tmp_path / 'comb'
        bash_dir.mkdir()
        comb_dir.mkdir()
        bash = run_bash(cmd, cwd=bash_dir)
        comb = run_psh(cmd, 'combinator', cwd=comb_dir)
        assert comb.stdout == bash.stdout
        assert comb.returncode == bash.returncode

    def test_keyword_function_redirect_applies_per_call(self, tmp_path):
        cmd = 'function g { echo kw; } > out.txt; g; cat out.txt'
        bash_dir = tmp_path / 'bash'
        comb_dir = tmp_path / 'comb'
        bash_dir.mkdir()
        comb_dir.mkdir()
        bash = run_bash(cmd, cwd=bash_dir)
        comb = run_psh(cmd, 'combinator', cwd=comb_dir)
        assert comb.stdout == bash.stdout
        assert comb.returncode == bash.returncode

    def test_definition_without_redirect_unaffected(self):
        assert_three_way('f() { echo plain; }; f; f')

    def test_redirect_accumulates_appends(self, tmp_path):
        cmd = ('f() { echo line; } >> log.txt; f; f; '
               'wc -l < log.txt | tr -d " "')
        bash_dir = tmp_path / 'bash'
        comb_dir = tmp_path / 'comb'
        bash_dir.mkdir()
        comb_dir.mkdir()
        bash = run_bash(cmd, cwd=bash_dir)
        comb = run_psh(cmd, 'combinator', cwd=comb_dir)
        assert comb.stdout == bash.stdout


class TestTimePrefix:
    """`time [-p]` prefixes a pipeline (reappraisal #15 L1).

    The v0.558 `time` reserved word never reached the combinator parser:
    every `time ...` command was rc=2 "Expected command". The combinator now
    mirrors the RD grammar: TIME (with optional `-p`) precedes `!` and times
    the whole following pipeline; `time` with no command times an empty
    pipeline. stderr carries the timing output, so only stdout/rc compare.
    """

    def test_time_simple_command(self):
        assert_three_way('time echo hi')

    def test_time_p_flag(self):
        assert_three_way('time -p true')

    def test_time_whole_pipeline(self):
        assert_three_way('time sleep 0 | cat')

    def test_time_subshell(self):
        assert_three_way('time (echo sub)')

    def test_time_brace_group(self):
        assert_three_way('time { echo grp; }')

    def test_time_no_command(self):
        assert_three_way('time')

    def test_time_p_no_command(self):
        assert_three_way('time -p')

    def test_time_preserves_exit_status(self):
        assert_three_way('time false; echo rc=$?')

    def test_time_while_loop(self):
        assert_three_way('time while false; do :; done')

    def test_time_in_and_or_chain(self):
        assert_three_way('time echo a && echo b')

    def test_time_inside_function(self):
        assert_three_way('f() { time echo infn; }; f')

    def test_time_in_command_substitution(self):
        assert_three_way('echo $(time echo cs 2>/dev/null)')


class TestHeredocsUnderCombinator:
    """Heredocs execute under --parser combinator (reappraisal #15 L2).

    The combinator's redirection builder dropped ``token.heredoc_key``, so
    bodies could never populate — masked because the source processor
    silently routed ALL heredoc input to the RD parser. The key now flows
    through and heredoc input parses with the ACTIVE parser.
    """

    def test_body_expands_variables(self):
        assert_three_way('x=42; cat <<EOF\nvalue $x\nEOF')

    def test_quoted_delimiter_suppresses_expansion(self):
        assert_three_way("x=42; cat <<'EOF'\nvalue $x\nEOF")

    def test_backslash_delimiter_suppresses_expansion(self):
        assert_three_way('x=42; cat <<\\EOF\nvalue $x\nEOF')

    def test_dash_variant_strips_tabs(self):
        assert_three_way('cat <<-EOF\n\tindented\n\tEOF')

    def test_two_heredocs_one_line(self):
        assert_three_way('cat <<A; cat <<B\nfirst\nA\nsecond\nB')

    def test_heredoc_in_pipeline(self):
        assert_three_way('cat <<EOF | tr a-z A-Z\nshout\nEOF')

    def test_heredoc_feeds_while_read(self):
        # Trailing redirect on a compound (`done <<EOF`): populated by the
        # processor's single per-node redirect chokepoint.
        assert_three_way(
            'while read line; do echo "got: $line"; done <<EOF\none\ntwo\nEOF')

    def test_heredoc_in_if_body(self):
        assert_three_way('if true; then cat <<EOF\nin-if\nEOF\nfi')

    def test_heredoc_in_function_body(self):
        assert_three_way('f() { cat <<EOF\nin-fn\nEOF\n}; f')

    def test_composite_delimiter(self):
        assert_three_way('x=1; cat <<E"O"F\ncomposite $x\nEOF')


class TestBackgroundAndOrList:
    """A trailing '&' backgrounds the whole and-or list (reappraisal #15 L3).

    The combinator consumed '&' per simple command / per compound, so
    `a && b &` ran `a` in the FOREGROUND and backgrounded only `b`. The '&'
    now lives at the and-or level, mirroring the RD parser's
    parse_and_or_list/_apply_background.
    """

    def test_whole_chain_backgrounds(self):
        # With the left side foreground, 'a' printed BEFORE 'fg'.
        assert_three_way('sleep 0.4 && echo a & echo fg; wait')

    def test_simple_background(self):
        assert_three_way('echo a & wait')

    def test_subshell_background(self):
        assert_three_way('(echo a) & wait')

    def test_brace_group_background(self):
        assert_three_way('{ echo a; } & wait')

    def test_failed_left_skips_right(self):
        assert_three_way('false && echo x & wait; echo done')

    def test_loop_background(self):
        assert_three_way('for i in 1 2; do echo $i; done & wait')

    def test_background_ordering_deterministic(self):
        assert_three_way('{ sleep 0.2; echo one; } & echo two; wait')

    def test_amp_then_pipe_rejected(self):
        assert_three_way('(echo a) & | cat')

    def test_amp_then_and_and_rejected(self):
        assert_three_way('(echo a) & && echo b')

    def test_amp_then_semicolon_rejected(self):
        assert_three_way('echo a & ; echo b')


class TestFunctionCompoundBodies:
    """A function body may be any compound command, not only { } (bash)."""

    def test_if_body(self):
        assert_three_way('f() if true; then echo ifbody; fi; f')

    def test_subshell_body(self):
        assert_three_way('f() (echo subbody); f')

    def test_for_body(self):
        assert_three_way('f() for i in 1 2; do echo $i; done; f')

    def test_while_body(self):
        assert_three_way('f() while false; do :; done; echo rc=$?')

    def test_until_body(self):
        assert_three_way('f() until false; do break; done; f; echo rc=$?')

    def test_case_body(self):
        assert_three_way('f() case x in x) echo cx;; esac; f')

    def test_arithmetic_body(self):
        assert_three_way('f() ((1+1)); f; echo rc=$?')

    def test_compound_body_definition_redirect(self):
        assert_three_way('f() if true; then echo r; fi > /dev/null; f')

    def test_plain_word_body_still_rejected(self):
        assert_three_way('f() break')

    def test_enhanced_test_body(self):
        # Reappraisal #17 F1: the combinator's non-brace body guard lacked
        # DOUBLE_LBRACKET, rejecting `f() [[ ... ]]` (rd/bash accept).
        assert_three_way('f() [[ 1 == 1 ]]; f && echo t')

    def test_enhanced_test_body_false(self):
        assert_three_way('f() [[ 1 == 2 ]]; f || echo f')

    def test_enhanced_test_body_uses_arguments(self):
        assert_three_way('f() [[ $1 == a ]]; f a && echo yes; f b || echo no')

    def test_enhanced_test_body_with_redirect(self):
        assert_three_way('f() [[ 1 == 1 ]] >/dev/null; f; echo rc=$?')

    def test_enhanced_test_body_in_case(self):
        assert_three_way('case x in x) f() [[ 1 == 1 ]]; f && echo m;; esac')


class TestPipelineNegationRuns:
    """`!` may repeat, each occurrence toggling the exit status (bash).

    Reappraisal #17 F2: the combinator consumed exactly one `!`
    (optional(exclamation)), rejecting `! ! cmd` with a parse error while
    rd/bash accept it. The consume is now a run with parity toggling,
    mirroring the recursive descent parser (v0.592).
    """

    def test_double_negation_true(self):
        assert_three_way('! ! true; echo $?')

    def test_double_negation_false(self):
        assert_three_way('! ! false; echo $?')

    def test_triple_negation_true(self):
        assert_three_way('! ! ! true; echo $?')

    def test_triple_negation_false(self):
        assert_three_way('! ! ! false; echo $?')

    def test_single_negation_still_works(self):
        assert_three_way('! true; echo $?')

    def test_double_negation_in_if_condition(self):
        assert_three_way('if ! ! true; then echo y; else echo n; fi')

    def test_double_negation_of_pipeline(self):
        assert_three_way('! ! echo x | cat; echo rc=$?')

    def test_double_negation_of_brace_group(self):
        assert_three_way('! ! { echo g; }; echo $?')

    def test_time_then_negation_run(self):
        # `time` precedes the `!` run; timing output goes to stderr.
        assert_three_way('time ! ! true 2>/dev/null; echo rc=$?')


class TestUnclosedExpansionsRejected:
    """Unclosed expansions are syntax errors, not literal words (bash rc=2).

    The combinator accepted `echo ${` as a variable literally named '${'
    (and the other four unclosed forms similarly); it now rejects them at
    word-consumption time like the RD parser.
    """

    def test_unclosed_parameter_expansion(self):
        assert_three_way('echo ${')

    def test_unclosed_command_substitution(self):
        assert_three_way('echo $(foo')

    def test_unclosed_backtick(self):
        assert_three_way('echo `foo')

    def test_unclosed_arithmetic(self):
        assert_three_way('echo $((1+')


class TestNamedFdRedirectCombinator:
    """Named-fd redirects ``{var}>file`` must not be dropped (reappraisal #16).

    The combinator read ``op_token.fd`` but never ``op_token.var_fd``, so
    ``exec {fd}>/dev/null`` parsed as a plain ``exec >/dev/null`` — silently
    clobbering the shell's own stdout and leaving ``$fd`` unset. The bare
    dynamic-dup form (``>&$var``) was likewise mis-composed: the ``$var``
    target leaked into the command as an argument. Both now mirror the
    recursive descent parser and match bash.
    """

    def test_named_fd_open(self):
        assert_three_way('exec {fd}>/dev/null; echo fd=$fd')

    def test_named_fd_append(self):
        assert_three_way('exec {fd}>>/dev/null; echo fd=$fd')

    def test_named_fd_input(self):
        assert_three_way('exec {fd}</dev/null; echo fd=$fd')

    def test_named_fd_readwrite(self):
        assert_three_way('exec {fd}<>/dev/null; echo fd=$fd')

    def test_named_fd_clobber(self):
        assert_three_way('exec {fd}>|/dev/null; echo fd=$fd')

    def test_named_fd_on_simple_command(self):
        assert_three_way('echo hi {fd}>/dev/null; echo fd=$fd')

    def test_named_fd_dup_out(self):
        assert_three_way('exec {fd}>&1; echo hello >&$fd')

    def test_named_fd_dup_dynamic_target(self):
        # {fd2}>&$fd : named-fd prefix AND a dynamic dup target.
        assert_three_way('exec {fd}>/dev/null; exec {fd2}>&$fd; echo fd2=$fd2')

    def test_plain_dynamic_dup_no_arg_leak(self):
        # >&$var was composited wrong: $var leaked as a command argument
        # (`echo hi >&$v` printed `hi1` instead of `hi`).
        assert_three_way('v=1; echo hi >&$v')


class TestEnhancedTestCompoundRejected:
    """The combinator rejects ``[[ ]]`` forms it cannot model (reappraisal #16).

    Boolean compounds (``&&``/``||``), parenthesised grouping, and multi-token
    ``=~`` regexes are an educational-scope gap. The old flat space-join
    fallback returned a plausible-but-WRONG exit status; the parser now
    HARD-REJECTS these with a committed parse error (exit 2) instead of
    shipping a silently-wrong answer. (bash/rd accept them; the combinator's
    honest rejection is a documented, deliberate divergence.)
    """

    def _assert_combinator_rejects(self, cmd):
        # rd still matches bash; the combinator rejects cleanly with rc 2 and
        # produces no stdout (the whole line fails to parse).
        bash = run_bash(cmd)
        rd = run_psh(cmd, 'rd')
        comb = run_psh(cmd, 'combinator')
        assert rd.stdout == bash.stdout and rd.returncode == bash.returncode, (
            f"rd vs bash for {cmd!r}")
        assert comb.returncode == 2, (
            f"combinator should reject {cmd!r} with rc 2, got "
            f"{comb.returncode} (stdout={comb.stdout!r})")
        assert comb.stdout == '', (
            f"combinator should print nothing for rejected {cmd!r}, "
            f"got {comb.stdout!r}")

    def test_and_compound_rejected(self):
        self._assert_combinator_rejects('[[ a == a && b == b ]]; echo $?')

    def test_or_compound_rejected(self):
        self._assert_combinator_rejects('[[ a == b || c == c ]]; echo $?')

    def test_grouping_rejected(self):
        self._assert_combinator_rejects('[[ ( a == a ) ]]; echo $?')

    def test_regex_with_parens_rejected(self):
        self._assert_combinator_rejects('[[ abc =~ (a|b)c ]]; echo $?')

    def test_negated_compound_rejected(self):
        self._assert_combinator_rejects('[[ ! a == a && b == b ]]; echo $?')

    def test_numeric_compound_rejected(self):
        self._assert_combinator_rejects('[[ 1 -lt 2 && 3 -gt 2 ]]; echo $?')

    def test_simple_binary_still_accepted(self):
        # Guard: the simple forms the combinator DOES model keep working.
        assert_three_way('[[ a == a ]]; echo $?')

    def test_simple_unary_still_accepted(self):
        assert_three_way('[[ -n foo ]]; echo $?')

    def test_negated_simple_still_accepted(self):
        assert_three_way('[[ ! a == b ]]; echo $?')


class TestArrayEscapeResidualParity:
    """Array-element escape residuals (task #38) must agree across bash, rd, and
    combinator: both parsers feed the same shared array-init paths, and the key
    fix + debris-escape fix must land identically under each."""

    def test_residual_backslash_indexed(self):
        assert_three_way(r'declare -a arr=(a\\b c); declare -p arr')

    def test_residual_backslash_assoc(self):
        assert_three_way(r'declare -A a=([k]=a\\b); declare -p a')

    def test_assoc_value_escaped_dollar(self):
        assert_three_way(r'declare -A a=([k]=a\$b); declare -p a; echo "<${a[k]}>"')

    def test_assoc_value_escaped_dquote(self):
        assert_three_way(r'declare -A a=([k]=a\"b); declare -p a')

    def test_assoc_value_escaped_squote(self):
        assert_three_way(r"declare -A a=([k]=a\'b); declare -p a")

    def test_bracket_word_argument(self):
        assert_three_way(r'echo [k]=a\$b')

    def test_subscript_expansion_preserved(self):
        assert_three_way(r'k=key; declare -A a=([$k]=v); declare -p a')

    def test_subscript_quoted_key_preserved(self):
        assert_three_way(r'declare -A a=(["a b"]=v); declare -p a')

    def test_ordinary_array_idempotent(self):
        assert_three_way(r'declare -a n=(1 2 3); declare -p n')
