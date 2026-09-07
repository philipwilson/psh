"""Tilde expansion in PATTERN words: ``case``, ``[[ == ]]``, ``${var#pat}`` (C042).

A pattern word is a word the shell expands and then matches against. bash
gives all of them the command-word tilde rule; psh's ``case`` walker had no
tilde step at all, so bash matched a branch psh silently skipped::

    env HOME=/h/me bash -c 'case $HOME in ~) echo tilde;; *) echo other;; esac'
    # bash 5.3.15: tilde     psh <= v0.786.0: other

The harm is a WRONG BRANCH taken with no diagnostic, so every row prints
which branch actually ran or which substring was actually removed — never a
bare exit status (D3).

``HOME`` is set through the child's ENVIRONMENT (``env=``), never assigned in
the script before the ``~`` is expanded (D14): an in-script ``HOME=/h/me``
ahead of the pattern would measure the assignment rather than the tilde rule,
and bash keeps its own startup home for ``~`` after ``HOME`` is unset, so a
script-assignment harness reads a different oracle than the one being pinned.

Rows run in all three input modes (``-c``, script file, stdin): the defect
was in word expansion and therefore mode independent, and a ``-c``-only suite
would not have proved it (D6).

Behaviour is bash 5.3.15 empirical — tilde expansion of pattern words is
long-standing, no bash 5.3 CHANGES item applies; the divergence was psh's.

Closes C042.
"""

import os

import pytest
from conformance_framework import ConformanceTest
from shell_oracle import is_comparable, run_bash, run_psh

#: The child's HOME. A path that does not exist on the host, so no row can
#: pass by accident through pathname expansion finding a real directory.
HOME = "/h/me"
CASE_ENV = {"HOME": HOME}

# (id, command). Each prints the branch taken or the text produced.
ROWS = [
    # --- case patterns: the C042 repro set ------------------------------
    ("case_bare_tilde",
     'case $HOME in ~) echo tilde;; *) echo other;; esac'),
    ("case_tilde_path",
     'case $HOME/x in ~/x) echo tilde;; *) echo other;; esac'),
    ("case_tilde_glob_tail",
     'case $HOME/abc in ~/a*) echo tilde;; *) echo other;; esac'),
    ("case_tilde_in_alternation",
     'case $HOME in foo|~) echo tilde;; *) echo other;; esac'),
    ("case_tilde_first_of_alternation",
     'case $HOME/x in ~|~/x) echo tilde;; *) echo other;; esac'),
    ("case_tilde_plus_is_pwd",
     'case $PWD in ~+) echo tildeplus;; *) echo other;; esac'),
    ("case_tilde_minus_is_oldpwd",
     'cd /; cd /usr; case $OLDPWD in ~-) echo tildeminus;; *) echo other;; esac'),
    ("case_tilde_user",
     'case ~root in ~root) echo tilderoot;; *) echo other;; esac'),
    ("case_tilde_colon_bounded",
     'case "$HOME:x" in ~:x) echo tilde;; *) echo other;; esac'),
    ("case_tilde_then_quoted_expansion",
     'u=x; case $HOME/x in ~/"$u") echo tilde;; *) echo other;; esac'),
    ("case_tilde_then_cmdsub",
     'case "$HOME/x" in ~/$(echo x)) echo tilde;; *) echo other;; esac'),
    ("case_tilde_inside_function",
     'f() { case $HOME in ~) echo tilde;; *) echo other;; esac; }; f'),
    ("case_tilde_inside_subshell",
     '( case $HOME in ~) echo tilde;; *) echo other;; esac )'),
    ("case_tilde_with_noglob",
     'set -f; case $HOME in ~) echo tilde;; *) echo other;; esac'),
    # --- case patterns: assignment-shaped value tilde -------------------
    ("case_value_tilde_after_equals",
     'case "x=$HOME" in x=~) echo tilde;; *) echo other;; esac'),
    ("case_value_tilde_after_equals_path",
     'case "x=$HOME/y" in x=~/y) echo tilde;; *) echo other;; esac'),
    ("case_value_tilde_after_colon_in_value",
     'case "x=a:$HOME:b" in x=a:~:b) echo tilde;; *) echo other;; esac'),
    ("case_value_tilde_append_assignment",
     'case "x+=$HOME" in x+=~) echo tilde;; *) echo other;; esac'),
    # --- case patterns: where the tilde must STAY literal ---------------
    ("case_single_quoted_tilde_is_literal",
     "case '~' in '~') echo lit;; *) echo other;; esac"),
    ("case_double_quoted_tilde_is_literal",
     'case "~" in "~") echo lit;; *) echo other;; esac'),
    ("case_quoted_tilde_does_not_match_home",
     "case $HOME in '~') echo lit;; *) echo other;; esac"),
    ("case_escaped_tilde_is_literal",
     "case '~' in \\~) echo lit;; *) echo other;; esac"),
    ("case_mid_word_tilde_is_literal",
     "case 'a~' in a~) echo lit;; *) echo other;; esac"),
    ("case_colon_without_assignment_is_literal",
     'case "x:$HOME" in x:~) echo tilde;; *) echo other;; esac'),
    ("case_bare_equals_is_not_an_assignment",
     'case "=$HOME" in =~) echo tilde;; *) echo other;; esac'),
    ("case_invalid_identifier_is_not_an_assignment",
     'case "1x=$HOME" in 1x=~) echo tilde;; *) echo other;; esac'),
    ("case_tilde_before_expansion_is_literal",
     'u=x; case $HOME in ~$u) echo tilde;; *) echo other;; esac'),
    ("case_tilde_before_quoted_part_is_literal",
     'case "$HOME*" in ~\'*\') echo tilde;; *) echo other;; esac'),
    ("case_unknown_user_stays_literal",
     "case '~nosuchuser-zz' in ~nosuchuser-zz) echo lit;; *) echo other;; esac"),
    ("case_second_colon_tilde_without_assignment",
     'case "$HOME:$HOME" in ~:~) echo tilde;; *) echo other;; esac'),
    # --- [[ == ]] / [[ != ]] pattern operands ---------------------------
    ("test_eq_bare_tilde",
     'if [[ $HOME == ~ ]]; then echo eq; else echo ne; fi'),
    ("test_eq_tilde_path",
     'if [[ $HOME/x == ~/x ]]; then echo eq; else echo ne; fi'),
    ("test_eq_tilde_glob_tail",
     'if [[ $HOME/abc == ~/a* ]]; then echo eq; else echo ne; fi'),
    ("test_eq_tilde_plus",
     'if [[ $PWD == ~+ ]]; then echo eq; else echo ne; fi'),
    ("test_ne_bare_tilde",
     'if [[ $HOME != ~ ]]; then echo ne; else echo eq; fi'),
    ("test_eq_quoted_tilde_is_literal",
     "if [[ $HOME == '~' ]]; then echo eq; else echo ne; fi"),
    ("test_eq_value_tilde_after_equals",
     'if [[ x=$HOME == x=~ ]]; then echo eq; else echo ne; fi'),
    ("test_eq_value_tilde_after_colon_in_value",
     'if [[ a=b:$HOME == a=b:~ ]]; then echo eq; else echo ne; fi'),
    ("test_eq_colon_without_assignment_is_literal",
     'if [[ x:$HOME == x:~ ]]; then echo eq; else echo ne; fi'),
    # --- [[ =~ ]] regex operand -----------------------------------------
    # bash expands a word-leading tilde in the regex operand too; psh's
    # `_rhs_regex` docstring used to claim the opposite.
    ("test_regex_leading_tilde_expands",
     "if [[ $HOME/x =~ ~/x ]]; then echo eq; else echo ne; fi"),
    ("test_regex_leading_tilde_no_longer_matches_literal_tilde",
     "if [[ '~' =~ ~ ]]; then echo eq; else echo ne; fi"),
    ("test_regex_tilde_plus",
     'if [[ $PWD =~ ~+ ]]; then echo eq; else echo ne; fi'),
    ("test_regex_quoted_tilde_is_literal",
     "if [[ '~' =~ '~' ]]; then echo eq; else echo ne; fi"),
    ("test_regex_mid_word_tilde_is_literal",
     "if [[ 'a~b' =~ a~b ]]; then echo eq; else echo ne; fi"),
    # --- ANSI-C quoted operands stay literal ----------------------------
    # Consolidating the two [[ ]] RHS walkers onto the owner also closed a
    # defect neither slot was hunting: the old walker ran its DOUBLE-QUOTE
    # recipe on a $'...' part, so a `$` the lexer had already resolved was
    # expanded a second time. The first row below was `ne` at base b6ec6f95.
    ("test_ansi_c_dollar_is_not_re_expanded",
     "b=Z; p='a$b'; if [[ $p == $'a$b' ]]; then echo eq; else echo ne; fi"),
    ("test_ansi_c_glob_is_literal",
     "p='a*b'; if [[ $p == $'a*b' ]]; then echo eq; else echo ne; fi"),
    ("test_ansi_c_glob_does_not_match_as_pattern",
     "p='aXb'; if [[ $p == $'a*b' ]]; then echo eq; else echo ne; fi"),
    ("test_ansi_c_backslash_survives",
     "p=$'a\\\\b'; if [[ $p == $'a\\\\b' ]]; then echo eq; else echo ne; fi"),
    ("test_ansi_c_regex_operand_is_literal",
     "p='aXb'; if [[ $p =~ $'a.b' ]]; then echo eq; else echo ne; fi"),
    ("test_ansi_c_case_pattern_is_literal",
     "case 'aXb' in $'a*b') echo T;; *) echo o;; esac"),
    # --- ${var#pat} family: the substring actually removed ---------------
    ("param_remove_prefix_tilde_slash",
     'v=$HOME/x; echo "[${v#~/}]"'),
    ("param_remove_prefix_bare_tilde",
     'v=$HOME/x; echo "[${v#~}]"'),
    ("param_remove_longest_prefix_tilde",
     'v=$HOME/x/y; echo "[${v##~/*}]"'),
    ("param_remove_suffix_tilde",
     'v=a$HOME; echo "[${v%~*}]"'),
    ("param_remove_longest_suffix_tilde",
     'v=a$HOME/b; echo "[${v%%~*}]"'),
    ("param_substitute_tilde",
     'v=$HOME/x; echo "[${v/~/X}]"'),
    ("param_substitute_all_tilde_slash",
     'v=$HOME/x; echo "[${v//~\\//X}]"'),
    ("param_remove_prefix_tilde_plus",
     'cd /usr; v=$PWD/x; echo "[${v#~+/}]"'),
    ("param_quoted_tilde_is_literal",
     "v='~x'; echo \"[${v#'~'}]\""),
    ("param_escaped_tilde_is_literal",
     "v='~x'; echo \"[${v#\\~}]\""),
    ("param_value_tilde_is_a_word_only_rule",
     "v='x=/h/me/y'; echo \"[${v#x=~}]\""),
    ("param_replacement_half_is_not_a_pattern",
     'v=ax; echo "[${v/x/~}]"'),
]

ROW_IDS = [name for name, _ in ROWS]
ROW_COMMANDS = [command for _, command in ROWS]


class TestPatternWordTilde(ConformanceTest):
    """psh matches bash on tilde expansion in pattern words (C042)."""

    @pytest.mark.parametrize("command", ROW_COMMANDS, ids=ROW_IDS)
    def test_matches_bash(self, command):
        self.assert_identical_behavior(command, env=dict(CASE_ENV))


def _psh_modes(command, cwd):
    """Run one command through psh in all three input modes.

    Returns {mode: (stdout, returncode)}. Each mode gets its own directory so
    a row that changes directory cannot see another mode's state.
    """
    outcomes = {}
    for mode in ("dash_c", "script", "stdin"):
        mode_dir = os.path.join(cwd, mode)
        os.makedirs(mode_dir, exist_ok=True)
        if mode == "dash_c":
            run = run_psh(["-c", command], cwd=mode_dir, env=dict(CASE_ENV))
        elif mode == "script":
            script = os.path.join(mode_dir, "case.sh")
            with open(script, "w") as handle:
                handle.write(command + "\n")
            run = run_psh([script], cwd=mode_dir, env=dict(CASE_ENV))
        else:
            run = run_psh([], stdin_data=command + "\n", cwd=mode_dir,
                          env=dict(CASE_ENV))
        assert is_comparable(run), f"harness failure in {mode}: {run!r}"
        outcomes[mode] = (run.stdout, run.returncode)
    return outcomes


@pytest.mark.parametrize("command", ROW_COMMANDS, ids=ROW_IDS)
def test_all_three_input_modes_match_bash(command, tmp_path):
    """D6: every row holds in -c, script-file and stdin mode."""
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(CASE_ENV))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    modes = _psh_modes(command, str(tmp_path))
    for mode, (stdout, returncode) in modes.items():
        assert (stdout, returncode) == (bash.stdout, bash.returncode), (
            f"psh diverges from bash in {mode} mode for {command!r}: "
            f"psh={(stdout, returncode)!r} "
            f"bash={(bash.stdout, bash.returncode)!r}")


def test_case_body_of_the_tilde_branch_actually_runs(tmp_path):
    """D3: the tilde branch's own side effect, not just its echo.

    A row that only printed a word could pass against a shell that matched
    the wrong arm but happened to print the same text. This row makes the
    tilde arm write a file that no other arm writes, then reads it back.
    """
    command = ('case $HOME in '
               '~) echo tilde > matched.txt;; '
               '*) echo other > matched.txt;; esac; '
               'cat matched.txt')
    run = run_psh(["-c", command], cwd=str(tmp_path), env=dict(CASE_ENV))
    assert is_comparable(run), f"harness failure: {run!r}"
    assert run.stdout == "tilde\n", run.stdout
    assert (tmp_path / "matched.txt").read_text() == "tilde\n"

    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(CASE_ENV))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"
    assert (bash_dir / "matched.txt").read_text() == "tilde\n"


def test_tilde_pattern_does_not_glob_the_filesystem(tmp_path):
    """The expanded tilde is a PATTERN, not a path that must exist.

    ``HOME`` points at a directory that does not exist, so a shell that
    resolved the pattern against the filesystem would fail this row while a
    shell that matched it as text passes.
    """
    command = 'case $HOME in ~) echo tilde;; *) echo other;; esac'
    for runner in (run_psh, run_bash):
        run = runner(["-c", command], cwd=str(tmp_path), env=dict(CASE_ENV))
        assert is_comparable(run), f"harness failure: {run!r}"
        assert run.stdout == "tilde\n", f"{runner.__name__}: {run.stdout!r}"
    assert not os.path.exists(HOME)
