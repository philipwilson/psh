"""Trailing redirects on `(( ))` / `[[ ]]` under the combinator parser (C020).

The combinator parser used to leave a trailing redirect on an arithmetic
command or an enhanced test unconsumed, so the statement-list loop absorbed
it as a SECOND statement. Two things were lost silently: the redirection
never applied, and the compound's exit status was replaced by the
redirect-only command's 0. The `while` row below is the sharp end — the loop
never terminated::

    python -m psh --parser combinator -c \
        'i=3; while (( i-- )) >/dev/null; do :; done'

The recursive descent parser was always correct, so it is carried here as a
control: each row is asserted against bash under BOTH parsers, and a
regression in either is a failure. Rows run in all three input modes (`-c`,
script file, stdin) because the defect was in the parser and therefore mode
independent — a `-c`-only suite would not have proved that.

Behaviour is bash 5.3.15 empirical (POSIX/bash have always applied a
compound command's redirections to the compound); nothing here follows a
bash 5.3 change, so no CHANGES citation applies.

Closes C020.
"""

import os
import re
import sys

import pytest
from conformance_framework import ConformanceTest, ConformanceTestFramework
from shell_oracle import is_comparable, run_bash, run_psh

COMBINATOR_ARGV = [sys.executable, "-m", "psh", "--parser", "combinator"]

# (id, command). Each is a shape the combinator got wrong, or a neighbour
# that must not regress. Every row prints something that DEPENDS on the
# redirect having been applied to the compound: an exit status the redirect-
# only second statement would have overwritten, or the bytes in a file.
ROWS = [
    # The five INVENTORY C020 shapes.
    ("test_redirect_status", '[[ a == b ]] > /dev/null; echo rc=$?'),
    ("arith_redirect_status", '(( 0 )) > /dev/null; echo rc=$?'),
    ("readonly_diag_redirected",
     'readonly r=5; (( r=9 )) 2>/dev/null; echo after=$?'),
    ("arith_redirect_in_if",
     'if (( 0 )) > /dev/null; then echo T; else echo F; fi'),
    ("arith_redirect_while_terminates",
     'i=3; n=0; while (( i-- )) >/dev/null; do n=$((n+1)); '
     '[ $n -gt 6 ] && break; done; echo iters=$n i=$i'),
    # Redirect operators other than `>` on `[[ ]]`.
    ("test_dup_operator", '[[ a == b ]] 2>&1; echo rc=$?'),
    ("test_append_operator", '[[ a == b ]] >> out.txt; echo rc=$?'),
    ("test_input_operator",
     'echo hi > in.txt; [[ a == b ]] < in.txt; echo rc=$?'),
    ("test_fd_variable_operator", '[[ a == b ]] {v}> fv.txt; echo rc=$? v=$v'),
    ("test_heredoc_operator",
     '[[ a == b ]] <<EOF\nbody\nEOF\necho rc=$?'),
    # `(( ))` inside every compound context that consumes its status.
    ("arith_redirect_in_while",
     'i=2; while (( i-- )) >/dev/null; do echo x; done; echo done-i=$i'),
    ("arith_redirect_in_until",
     'i=0; until (( i++ >= 2 )) >/dev/null; do echo u; done; echo until-i=$i'),
    ("arith_redirect_and_and", '(( 0 )) >/dev/null && echo AND || echo OR'),
    ("arith_redirect_or_or", '(( 1 )) >/dev/null || echo OR2; echo rc=$?'),
    # A redirect followed by `&&` — the helper must stop at the operator.
    ("test_redirect_then_and", '[[ a == a ]] >/dev/null && echo YES'),
    # A redirection LIST, not a single redirect.
    ("arith_two_redirects", '(( 0 )) >o1.txt 2>o2.txt; echo rc=$?'),
    # A command-substitution redirect target is expanded, once.
    ("test_redirect_cmdsub_target",
     '[[ a == b ]] > "$(echo cs.txt)"; echo rc=$?; ls cs.txt'),
    # `&` still backgrounds the and-or list rather than being eaten.
    ("arith_redirect_background", '(( 1 )) >/dev/null & wait; echo rc=$?'),
]

ROW_IDS = [name for name, _ in ROWS]
ROW_COMMANDS = [command for _, command in ROWS]


class TestCombinatorTrailingRedirects(ConformanceTest):
    """The combinator parser matches bash on trailing redirects (C020)."""

    @property
    def framework(self):
        """A framework whose psh runs the COMBINATOR parser, not the default."""
        if not hasattr(self, '_framework'):
            self._framework = ConformanceTestFramework(psh_path=COMBINATOR_ARGV)
        return self._framework

    @pytest.mark.parametrize("command", ROW_COMMANDS, ids=ROW_IDS)
    def test_combinator_matches_bash(self, command):
        self.assert_identical_behavior(command)


class TestRecursiveDescentTrailingRedirects(ConformanceTest):
    """Control: the reference parser was correct and stays correct (C020)."""

    @pytest.mark.parametrize("command", ROW_COMMANDS, ids=ROW_IDS)
    def test_recursive_descent_matches_bash(self, command):
        self.assert_identical_behavior(command)


def _psh_modes(command, cwd, parser):
    """Run one command through psh in all three input modes.

    Returns {mode: (stdout, returncode)}. Each mode gets its own subdirectory
    so rows that create files (``out.txt``, ``cs.txt``) cannot see each
    other's leftovers.
    """
    outcomes = {}
    for mode in ("dash_c", "script", "stdin"):
        mode_dir = os.path.join(cwd, mode)
        os.makedirs(mode_dir, exist_ok=True)
        parser_args = ["--parser", parser]
        if mode == "dash_c":
            run = run_psh([*parser_args, "-c", command], cwd=mode_dir)
        elif mode == "script":
            script = os.path.join(mode_dir, "case.sh")
            with open(script, "w") as handle:
                handle.write(command + "\n")
            run = run_psh([*parser_args, script], cwd=mode_dir)
        else:
            run = run_psh([*parser_args], stdin_data=command + "\n",
                          cwd=mode_dir)
        assert is_comparable(run), f"harness failure in {mode}: {run!r}"
        outcomes[mode] = (run.stdout, run.returncode)
    return outcomes


@pytest.mark.parametrize("command", ROW_COMMANDS, ids=ROW_IDS)
@pytest.mark.parametrize("parser", ["combinator", "rd"])
def test_all_three_input_modes_match_bash(command, parser, tmp_path):
    """D6: every row holds in -c, script-file and stdin mode, both parsers."""
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    modes = _psh_modes(command, str(tmp_path), parser)
    for mode, (stdout, returncode) in modes.items():
        assert (stdout, returncode) == (bash.stdout, bash.returncode), (
            f"{parser} parser diverges from bash in {mode} mode for "
            f"{command!r}: psh={(stdout, returncode)!r} "
            f"bash={(bash.stdout, bash.returncode)!r}")


def test_diagnostic_bytes_land_in_the_redirected_file(tmp_path):
    """D3: the redirect applies to the compound, proven by the file contents.

    A status-only assertion would pass against a parser that dropped the
    redirect but happened to report the right code, so this row reads back
    what was actually written to fd 2 and checks the terminal saw none of it.
    """
    command = ('r=5; readonly r; (( r=9 )) 2>err.txt; echo after=$?; '
               'printf "captured=%s\\n" "$(wc -c < err.txt)"')
    for parser in ("combinator", "rd"):
        case_dir = tmp_path / parser
        case_dir.mkdir()
        run = run_psh(["--parser", parser, "-c", command], cwd=str(case_dir))
        assert is_comparable(run), f"harness failure: {run!r}"

        assert "after=1\n" in run.stdout, run.stdout
        # The diagnostic was redirected, so it is NOT on the inherited stderr.
        assert "readonly variable" not in run.stderr, (
            f"{parser}: diagnostic leaked past the redirect: {run.stderr!r}")
        # ...and it IS in the file, which therefore is not empty.
        error_text = (case_dir / "err.txt").read_text()
        assert "readonly variable" in error_text, (
            f"{parser}: err.txt did not receive the diagnostic: "
            f"{error_text!r}")


@pytest.mark.parametrize("source", ['(( 0 )) > /dev/null', '[[ a == b ]] > /dev/null'])
def test_debug_ast_shows_one_statement_carrying_the_redirect(source):
    """`--debug-ast` renders ONE statement whose node owns the redirect.

    This is the operator-visible face of the defect: the two parsers used to
    print a different number of top-level statements for the same source, and
    `--debug-ast` was how the split was first seen. psh-only output, so no
    bash side.
    """
    trees = {}
    for parser in ("combinator", "rd"):
        run = run_psh(["--parser", parser, "--debug-ast", "-c", source])
        assert is_comparable(run), f"harness failure: {run!r}"
        text = run.stdout + run.stderr
        assert "statements: [1 items]" in text, (
            f"{parser}: expected one top-level statement for {source!r}, got:\n{text}")
        assert "redirects: [1 items]" in text, (
            f"{parser}: redirect missing from the AST for {source!r}:\n{text}")
        # The redirect belongs to the compound, so no SimpleCommand was
        # invented to carry it.
        assert "SimpleCommand" not in text, (
            f"{parser}: redirect was split onto a SimpleCommand for {source!r}:\n{text}")
        # Drop the banner (it names the parser) and the `@lineN` position
        # annotations, which only the recursive descent parser attaches — an
        # unrelated pre-existing gap, not part of this invariant.
        body = text.split("=== AST Debug Output", 1)[-1].split("\n", 1)[-1]
        trees[parser] = re.sub(r" @line\d+", "", body)

    assert trees["combinator"] == trees["rd"], (
        f"combinator and rd render different AST shapes for {source!r}:\n"
        f"--- rd ---\n{trees['rd']}\n--- combinator ---\n{trees['combinator']}")
