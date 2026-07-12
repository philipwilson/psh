"""Alias token-stream transform conformance (Tier R8.6b — the full move).

R8.6b moved alias expansion from a runtime argv-reparse to a TOKEN-STREAM
transform at the lex->parse boundary (AliasManager.expand_aliases). This
file pins the behaviours the move is responsible for, against real bash:

  * command-position detection inside compound commands (if/while/for/case/
    subshell/brace-group/&&/||/|/elif/else/until and pattern positions);
  * a quoted command word is NOT alias-expanded (WORD vs STRING token);
  * trailing-space chaining (a value ending in a space expands the NEXT word);
  * `shopt -s/-u expand_aliases` is accepted (no "invalid option" error).

COMPARISON CONTRACT (same as the R8.6a injection test): bash needs
`shopt -s expand_aliases` plus the alias on its own line to expand in a -c
script; psh ALWAYS expands (a documented divergence) and treats
`shopt expand_aliases` as a no-op gate. We compare stdout + exit code +
stderr-emptiness, isolating the transform behaviour from the orthogonal
always-expand / shopt-no-op divergences.
"""


from conformance_framework import ConformanceTestFramework

_framework = ConformanceTestFramework()


def assert_parity(bash_lines: str, psh_lines: str):
    """Run a bash script (own-line alias defs + shopt) and the equivalent psh
    script, asserting parity on stdout, exit code, and stderr-emptiness."""
    bash = _framework.run_in_bash("shopt -s expand_aliases\n" + bash_lines)
    psh = _framework.run_in_psh(psh_lines)
    assert psh.stdout == bash.stdout and psh.exit_code == bash.exit_code \
        and bool(psh.stderr) == bool(bash.stderr), (
        f"psh/bash differ\nbash script: {bash_lines!r}\npsh script: {psh_lines!r}\n"
        f"PSH:  stdout={psh.stdout!r} stderr={psh.stderr!r} exit={psh.exit_code}\n"
        f"Bash: stdout={bash.stdout!r} stderr={bash.stderr!r} exit={bash.exit_code}"
    )


class TestAliasCommandPositionInCompounds:
    """An alias expands only where a command is expected (bash semantics)."""

    def test_inside_if_then(self):
        assert_parity("alias g='echo G'\nif true; then g; fi",
                      "alias g='echo G'; if true; then g; fi")

    def test_as_if_condition(self):
        assert_parity("alias t='true'\nif t; then echo Y; fi",
                      "alias t='true'; if t; then echo Y; fi")

    def test_inside_while_do(self):
        assert_parity(
            "alias g='echo G'\ni=0; while [ $i -lt 2 ]; do g; i=$((i+1)); done",
            "alias g='echo G'; i=0; while [ $i -lt 2 ]; do g; i=$((i+1)); done")

    def test_inside_until_do(self):
        assert_parity(
            "alias g='echo G'\ni=0; until [ $i -ge 1 ]; do g; i=1; done",
            "alias g='echo G'; i=0; until [ $i -ge 1 ]; do g; i=1; done")

    def test_inside_for_do(self):
        assert_parity("alias g='echo G'\nfor x in 1 2; do g; done",
                      "alias g='echo G'; for x in 1 2; do g; done")

    def test_inside_case_body(self):
        assert_parity("alias g='echo G'\ncase a in a) g;; esac",
                      "alias g='echo G'; case a in a) g;; esac")

    def test_inside_subshell(self):
        assert_parity("alias g='echo G'\n( g )",
                      "alias g='echo G'; ( g )")

    def test_inside_brace_group(self):
        assert_parity("alias g='echo G'\n{ g; }",
                      "alias g='echo G'; { g; }")

    def test_after_and_and(self):
        assert_parity("alias g='echo G'\ntrue && g",
                      "alias g='echo G'; true && g")

    def test_after_or_or(self):
        assert_parity("alias g='echo G'\nfalse || g",
                      "alias g='echo G'; false || g")

    def test_after_pipe(self):
        assert_parity("alias g='echo G'\necho hi | g",
                      "alias g='echo G'; echo hi | g")

    def test_after_semicolon(self):
        assert_parity("alias g='echo G'\necho first; g",
                      "alias g='echo G'; echo first; g")

    def test_in_elif_branch(self):
        assert_parity(
            "alias g='echo G'\nif false; then echo a; elif true; then g; fi",
            "alias g='echo G'; if false; then echo a; elif true; then g; fi")

    def test_in_else_branch(self):
        assert_parity(
            "alias g='echo G'\nif false; then echo a; else g; fi",
            "alias g='echo G'; if false; then echo a; else g; fi")

    def test_nested_brace_if(self):
        assert_parity("alias g='echo G'\n{ if true; then g; fi; }",
                      "alias g='echo G'; { if true; then g; fi; }")

    def test_double_semicolon_case_body(self):
        assert_parity(
            "alias g='echo G'\ncase a in b) echo b;; a) g;; esac",
            "alias g='echo G'; case a in b) echo b;; a) g;; esac")


class TestAliasNotInCommandPosition:
    """An alias name that is NOT in command position is left literal."""

    def test_plain_argument_not_expanded(self):
        assert_parity("alias foo='BAR'\necho foo foo",
                      "alias foo='BAR'; echo foo foo")

    def test_for_loop_item_not_expanded(self):
        # `g` after `in` is a loop ITEM, not a command.
        assert_parity("alias g='echo G'\nfor x in g h; do echo $x; done",
                      "alias g='echo G'; for x in g h; do echo $x; done")

    def test_case_selector_not_expanded(self):
        # The selector word after `case` is not a command.
        assert_parity("alias g='echo G'\ncase g in g) echo m;; esac",
                      "alias g='echo G'; case g in g) echo m;; esac")

    def test_keyword_lookalike_argument_not_expanded(self):
        assert_parity("alias g='echo G'\necho if g then",
                      "alias g='echo G'; echo if g then")


class TestQuotedCommandWordNotExpanded:
    """A quoted first word is a STRING token, not a bare WORD, so it is NOT
    alias-expanded (matches bash)."""

    def test_single_quoted_command_word(self):
        assert_parity("alias ll='echo LL'\n'll' 2>/dev/null; echo rc=$?",
                      "alias ll='echo LL'; 'll' 2>/dev/null; echo rc=$?")

    def test_double_quoted_command_word(self):
        assert_parity('alias ll=\'echo LL\'\n"ll" 2>/dev/null; echo rc=$?',
                      'alias ll=\'echo LL\'; "ll" 2>/dev/null; echo rc=$?')

    def test_backslash_bypass(self):
        assert_parity("alias ls='echo ALIASED'\n\\ls 2>/dev/null; echo rc=$?",
                      "alias ls='echo ALIASED'; \\ls 2>/dev/null; echo rc=$?")


class TestTrailingSpaceChaining:
    """A value ending in a space makes the NEXT word also alias-expand."""

    def test_two_level_chain(self):
        assert_parity("alias a='echo '\nalias b='B'\na b",
                      "alias a='echo '; alias b='B'; a b")

    def test_no_chain_without_trailing_space(self):
        assert_parity("alias a='echo'\nalias b='B'\na b",
                      "alias a='echo'; alias b='B'; a b")

    def test_three_level_chain(self):
        assert_parity("alias a='echo '\nalias b='nice '\nalias c='C'\na b c",
                      "alias a='echo '; alias b='nice '; alias c='C'; a b c")


class TestShoptExpandAliasesAccepted:
    """`shopt -s/-u expand_aliases` is recognized (no "invalid option")."""

    def test_shopt_set_accepted(self):
        psh = _framework.run_in_psh("shopt -s expand_aliases; echo ok")
        assert psh.stdout == "ok\n"
        assert psh.exit_code == 0
        assert "invalid shell option name" not in psh.stderr

    def test_shopt_unset_accepted_does_not_disable(self):
        # Even after `shopt -u expand_aliases` psh still expands (no-op gate).
        psh = _framework.run_in_psh(
            "alias g='echo G'; shopt -u expand_aliases; g")
        assert psh.stdout == "G\n"
        assert psh.exit_code == 0

    def test_self_recursion_guard(self):
        # `alias echo='echo wrapped'; echo hi` expands once -> `echo wrapped hi`.
        assert_parity("alias echo='echo wrapped'\necho hi",
                      "alias echo='echo wrapped'; echo hi")
