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


# ---------------------------------------------------------------------------
# The tilde REPLACEMENT is literal — rows that vary the VALUE of HOME/PWD.
#
# Round 1 of this slot shipped the replacement RAW, so a HOME carrying a glob
# metacharacter became a live pattern. Every round-1 pin used HOME=/h/me, so
# none of them could see it: a corpus that never varies the value cannot catch
# a value-shape bug.
#
# Round 2 varied the value but built its near-miss subject at the WRONG
# character (`sed 's/./X/2'` rewrites the `a` of `/a*b`, giving `/X*b`, which a
# LIVE `/a*b` does not match either), so six of its rows answered the same
# whether the replacement was escaped or not. Every decoy below is instead
# DERIVED against bash 5.3.15 and recorded as an explicit (home, subject) pair:
# a subject the LIVE pattern matches and the LITERAL one does not. The
# derivation is `tools`-free and reproducible — for each candidate subject,
# compare `case SUBJ in $HOME)` (bash keeps a parameter expansion live) with
# `case SUBJ in ~)` (bash quotes a tilde expansion) and keep the pairs where
# the two answers differ.
#
# Homes with no metacharacter FOR A GIVEN CONSUMER have no decoy for it and are
# deliberately absent from that list rather than carried as an inert row: with
# nothing to escape, `escape(home) == home` and no row can discriminate.
# ---------------------------------------------------------------------------

#: HOME values whose text carries a pattern (or regex) metacharacter. Used for
#: the rows that must hold at ANY value — they are red-on-base for C042 — while
#: the escape-discriminating rows come from the derived tables below.
METACHAR_HOMES = ["/a*b", "/a?b", "/a[b]", "/a.b", "/a(b", "/a)b", "/a]b",
                  "/a b", "/a{b", "/a+b", "/a^b", "/a$b"]

#: (home, subject) where a LIVE glob replacement matches and a LITERAL one does
#: not — derived against bash 5.3.15 on 2026-09-08. The other homes carry no
#: GLOB metacharacter (`.`, `(`, `)`, `]`, ` `, `{`, `+`, `^`, `$` are literal
#: to a glob), so no glob row can discriminate the escape at them.
GLOB_DECOYS = [
    ("/a*b", "/aXb"),
    ("/a?b", "/aXb"),
    ("/a[b]", "/ab"),
    ("/a\\b", "/ab"),
]

#: (home, subject) where a LIVE regex replacement matches and a LITERAL one
#: does not — derived the same way against `[[ $s =~ $r ]]` vs `[[ $s =~ ~ ]]`.
REGEX_DECOYS = [
    ("/a*b", "/ab"),
    ("/a?b", "/ab"),
    ("/a[b]", "/ab"),
    ("/a.b", "/aXb"),
    ("/a\\b", "/ab"),
    ("/a+b", "/ab"),
]

GLOB_DECOY_IDS = [f"{h}-{s}" for h, s in GLOB_DECOYS]
REGEX_DECOY_IDS = [f"{h}-{s}" for h, s in REGEX_DECOYS]

#: Homes where the LITERAL pattern matches the home itself but a LIVE one does
#: NOT — the exact-subject direction of the same rule, also derived.
GLOB_EXACT_DISCRIMINATORS = ["/a[b]", "/a\\b"]
REGEX_EXACT_DISCRIMINATORS = ["/a*b", "/a?b", "/a[b]", "/a(b", "/a\\b",
                              "/a+b", "/a^b", "/a$b"]

#: (id, command) run once per metacharacter HOME. These hold at EVERY home and
#: are red-on-base for C042; the ones that also discriminate the escape are the
#: exact-subject rows, at the homes listed above.
METACHAR_ROWS = [
    # The subject IS the home, so it must match — a live replacement (or a
    # regex that fails to compile) takes the wrong branch or errors.
    ("case_exact_subject",
     'case $HOME in ~) echo tilde;; *) echo other;; esac'),
    ("case_exact_subject_path",
     'case $HOME/z in ~/z) echo tilde;; *) echo other;; esac'),
    ("case_assignment_value_exact_subject",
     'case "x=$HOME" in x=~) echo tilde;; *) echo other;; esac'),
    ("test_eq_exact_subject",
     'if [[ $HOME == ~ ]]; then echo eq; else echo ne; fi'),
    ("test_ne_exact_subject",
     'if [[ $HOME != ~ ]]; then echo T; else echo F; fi'),
    ("test_regex_exact_subject_rc",
     '[[ $HOME =~ ~ ]]; echo rc=$?'),
    ("param_remove_prefix_exact",
     'v=$HOME/z; echo "[${v#~/}]"'),
    # The tail of the word keeps its glob power even though the replacement
    # does not: `~/a*` still globs on the `a*` the SOURCE supplied. This one
    # discriminates the opposite failure (over-escaping the tail).
    ("source_glob_tail_still_live",
     'case $HOME/abc in ~/a*) echo tilde;; *) echo other;; esac'),
]

METACHAR_IDS = [f"{name}-{home}" for home in METACHAR_HOMES
                for name, _ in METACHAR_ROWS]
METACHAR_CASES = [(command, home) for home in METACHAR_HOMES
                  for _, command in METACHAR_ROWS]


class TestTildeReplacementIsLiteral(ConformanceTest):
    """A metacharacter-bearing HOME is matched literally (C042, round-2 B1)."""

    @pytest.mark.parametrize("command,home", METACHAR_CASES, ids=METACHAR_IDS)
    def test_matches_bash(self, command, home):
        self.assert_identical_behavior(command, env={"HOME": home})


@pytest.mark.parametrize("command,home", METACHAR_CASES, ids=METACHAR_IDS)
def test_metachar_home_all_three_input_modes(command, home, tmp_path):
    """D6: the replacement rule holds in -c, script-file and stdin mode."""
    env = {"HOME": home}
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(env))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    for mode in ("dash_c", "script", "stdin"):
        mode_dir = tmp_path / mode
        mode_dir.mkdir()
        if mode == "dash_c":
            run = run_psh(["-c", command], cwd=str(mode_dir), env=dict(env))
        elif mode == "script":
            script = mode_dir / "case.sh"
            script.write_text(command + "\n")
            run = run_psh([str(script)], cwd=str(mode_dir), env=dict(env))
        else:
            run = run_psh([], stdin_data=command + "\n", cwd=str(mode_dir),
                          env=dict(env))
        assert is_comparable(run), f"harness failure in {mode}: {run!r}"
        assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
            f"psh diverges from bash in {mode} mode, HOME={home!r}, "
            f"{command!r}: psh={(run.stdout, run.returncode)!r} "
            f"bash={(bash.stdout, bash.returncode)!r}")


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
def test_metachar_home_both_parsers(parser, home, subject, tmp_path):
    """Both parsers build the same pattern Word, so both get the same rule.

    Uses a DERIVED near-miss subject (see `GLOB_DECOYS`). Until round 4 this
    row built its subject with `sed 's/./X/2'`, whose near-miss half is inert —
    a live `/a*b` does not match `/X*b` either — while the module header two
    hundred lines above claimed every decoy was a derived literal.
    """
    command = (f"case {subject!r} in ~) echo tilde;; *) echo other;; esac; "
               "case $HOME in ~) echo exact;; *) echo miss;; esac; "
               "[[ $HOME =~ ~ ]]; echo rc=$?")
    env = {"HOME": home}
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(env))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    run = run_psh(["--parser", parser, "-c", command], cwd=str(tmp_path),
                  env=dict(env))
    assert is_comparable(run), f"harness failure: {run!r}"
    assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
        f"{parser} parser, HOME={home!r}: psh="
        f"{(run.stdout, run.returncode)!r} "
        f"bash={(bash.stdout, bash.returncode)!r}")


#: (directory name, near-miss basename) for `~+`, derived the same way as
#: `GLOB_DECOYS`: a basename the LIVE `$PWD` pattern matches and the LITERAL one
#: does not. `a.b` and `a(b` carry no GLOB metacharacter and so have no glob
#: decoy; they are covered by the regex row below instead.
TILDE_PLUS_GLOB_DECOYS = [("a*b", "aXb"), ("a?b", "aXb"), ("a[b]", "ab")]


@pytest.mark.parametrize("dirname,near_miss", TILDE_PLUS_GLOB_DECOYS,
                         ids=[d for d, _ in TILDE_PLUS_GLOB_DECOYS])
def test_tilde_plus_replacement_is_literal(dirname, near_miss, tmp_path):
    """``~+`` is ``$PWD``, and an ordinary directory name carries `*` or `[`.

    This is the realistic shape of round-2 B1: no HOME games, just a working
    directory called ``my.project`` or ``a[1]``. The near-miss basename is a
    derived literal, not a `sed` rewrite: the parent path is taken from `$PWD`
    so the row is location independent, and only the basename varies.
    """
    workdir = tmp_path / dirname
    workdir.mkdir()
    command = (f'case "${{PWD%/*}}/{near_miss}" in ~+) echo tilde;; '
               '*) echo other;; esac; '
               'case "$PWD" in ~+) echo exact;; *) echo miss;; esac')
    bash = run_bash(["-c", command], cwd=str(workdir))
    run = run_psh(["-c", command], cwd=str(workdir))
    assert is_comparable(bash) and is_comparable(run), (bash, run)
    # The row is only a control if bash actually distinguishes the two subjects.
    assert bash.stdout == "other\nexact\n", (dirname, bash.stdout)
    assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
        f"cwd={dirname!r}: psh={(run.stdout, run.returncode)!r} "
        f"bash={(bash.stdout, bash.returncode)!r}")


@pytest.mark.parametrize("dirname", ["a*b", "a.b", "a[b]", "a?b", "a(b"])
def test_tilde_plus_regex_operand_compiles(dirname, tmp_path):
    """The `~+` replacement reaches `re.compile` escaped, at any cwd shape."""
    workdir = tmp_path / dirname
    workdir.mkdir()
    command = '[[ $PWD =~ ~+ ]]; echo rc=$?'
    bash = run_bash(["-c", command], cwd=str(workdir))
    run = run_psh(["-c", command], cwd=str(workdir))
    assert is_comparable(bash) and is_comparable(run), (bash, run)
    assert run.stdout == "rc=0\n", (dirname, run.stdout, run.stderr)
    assert "invalid regex" not in run.stderr, run.stderr
    assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode)


@pytest.mark.parametrize("home", ["/a[b", "/a(b", "/a)b", "/a*b", "/a+b"])
def test_regex_operand_replacement_compiles(home, tmp_path):
    """B2: a metacharacter home must not reach ``re.compile`` as regex source.

    At round-1 tip these were ``psh: [[: invalid regex …``, rc 2, where bash
    matches with rc 0 — a script that ran silently at base started erroring.
    """
    command = '[[ $HOME =~ ~ ]]; echo rc=$?'
    env = {"HOME": home}
    bash = run_bash(["-c", command], cwd=str(tmp_path), env=dict(env))
    run = run_psh(["-c", command], cwd=str(tmp_path), env=dict(env))
    assert is_comparable(bash) and is_comparable(run), (bash, run)
    assert run.stdout == "rc=0\n", (home, run.stdout, run.stderr)
    assert "invalid regex" not in run.stderr, run.stderr
    assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode)


# ---------------------------------------------------------------------------
# Derived-decoy rows: each one is known to CHANGE ANSWER when the escape moves.
# ---------------------------------------------------------------------------

class TestDerivedDecoys(ConformanceTest):
    """Near-miss subjects a LIVE replacement matches and a LITERAL one does not.

    These are the rows that hold the escape. Each pair was derived against
    bash 5.3.15 rather than assumed, and each is proved to redden when the
    escape is dropped (see the slot's round-3 handoff for the counts).
    """

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_case_near_miss_does_not_match(self, home, subject):
        self.assert_identical_behavior(
            f'case {subject!r} in ~) echo tilde;; *) echo other;; esac',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_case_path_near_miss_does_not_match(self, home, subject):
        self.assert_identical_behavior(
            f'case {subject + "/z"!r} in ~/z) echo tilde;; *) echo other;; esac',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_case_assignment_value_near_miss(self, home, subject):
        self.assert_identical_behavior(
            f'case {"x=" + subject!r} in x=~) echo tilde;; *) echo other;; esac',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_eq_near_miss(self, home, subject):
        self.assert_identical_behavior(
            f'if [[ {subject!r} == ~ ]]; then echo eq; else echo ne; fi',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_ne_near_miss(self, home, subject):
        self.assert_identical_behavior(
            f'if [[ {subject!r} != ~ ]]; then echo T; else echo F; fi',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", REGEX_DECOYS, ids=REGEX_DECOY_IDS)
    def test_regex_near_miss(self, home, subject):
        self.assert_identical_behavior(
            f'if [[ {subject!r} =~ ~ ]]; then echo eq; else echo ne; fi',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_dollar_home_stays_live(self, home, subject):
        """The OTHER half of bash's rule, on a subject that can see it.

        bash quotes the result of tilde expansion and does NOT quote the
        result of parameter expansion, so this row MATCHES on exactly the
        subjects the `~` rows above miss. Round 2's version of this control
        used the broken decoy and was inert against an over-escaping change;
        this one reddens.
        """
        self.assert_identical_behavior(
            f'case {subject!r} in $HOME) echo live;; *) echo other;; esac',
            env={"HOME": home})


@pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
def test_derived_decoy_all_three_input_modes(home, subject, tmp_path):
    """D6: the derived glob decoy holds in -c, script-file and stdin mode."""
    command = (f'case {subject!r} in ~) echo tilde;; *) echo other;; esac; '
               f'case {subject!r} in $HOME) echo live;; *) echo other;; esac')
    env = {"HOME": home}
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(env))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    for mode in ("dash_c", "script", "stdin"):
        mode_dir = tmp_path / mode
        mode_dir.mkdir()
        if mode == "dash_c":
            run = run_psh(["-c", command], cwd=str(mode_dir), env=dict(env))
        elif mode == "script":
            script = mode_dir / "case.sh"
            script.write_text(command + "\n")
            run = run_psh([str(script)], cwd=str(mode_dir), env=dict(env))
        else:
            run = run_psh([], stdin_data=command + "\n", cwd=str(mode_dir),
                          env=dict(env))
        assert is_comparable(run), f"harness failure in {mode}: {run!r}"
        assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
            f"{mode} mode, HOME={home!r}, subject={subject!r}: "
            f"psh={(run.stdout, run.returncode)!r} "
            f"bash={(bash.stdout, bash.returncode)!r}")


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
def test_derived_decoy_both_parsers(parser, home, subject, tmp_path):
    """Both parsers build the same pattern Word, so both get the same rule."""
    command = (f'case {subject!r} in ~) echo tilde;; *) echo other;; esac; '
               f'case $HOME in ~) echo exact;; *) echo miss;; esac')
    env = {"HOME": home}
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(env))
    run = run_psh(["--parser", parser, "-c", command], cwd=str(tmp_path),
                  env=dict(env))
    assert is_comparable(bash) and is_comparable(run), (bash, run)
    assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
        f"{parser} parser, HOME={home!r}: psh="
        f"{(run.stdout, run.returncode)!r} bash={(bash.stdout, bash.returncode)!r}")


# ---------------------------------------------------------------------------
# The colon-extent collapse site — the third escape site, unpinned until now.
#
# bash's tilde WORD runs from a word-leading `~` to the first unquoted `/`, so a
# `:` sits INSIDE it: `~:REST` is one tilde word and bash makes ALL of it
# literal. `TildeExpander.word_end` is that boundary, distinct from
# `prefix_end` (which stops at `/` OR `:` and decides what EXPANDS).
#
# EXCEPT in an ASSIGNMENT-SHAPED word, where `:` ends the tilde word too and the
# remainder therefore stays LIVE — `case 'x=/h/me:XX' in x=~:*)` MATCHES in bash
# while the non-assignment control `case '/h/me:XX' in ~:*)` does not. psh gets
# this right because `_expand_assignment_value_tildes` splits the value on `:`
# before escaping; `TestAssignmentColonExceptionSite` below is what holds it.
#
# `o` alone proves nothing: a shell that never expanded the tilde also prints
# `o`. Separating the hypotheses needs four subjects per pattern — see
# `TildeExpander.word_end` and `test_four_subject_separation` below.
#
# Round 2 escaped only the replacement here, which left the remainder live and
# diverged from bash the moment the remainder carried a metacharacter:
#     env HOME=/h/me psh -c "case '/h/me:XX' in ~:*) echo M;; *) echo o;; esac"
# printed `M` at round-2 tip where bash 5.3.15 and psh at base b6ec6f95 print
# `o` — a regression round 2 shipped and no pin could see.
# ---------------------------------------------------------------------------

#: (id, command). Rows whose pattern word is a colon-bounded tilde EXTENT whose
#: remainder carries a metacharacter, in one literal part.
COLON_EXTENT_ROWS = [
    ("extent_star_in_remainder_is_literal",
     'case "$HOME:XX" in ~:*) echo M;; *) echo o;; esac'),
    ("extent_star_matches_itself",
     'case "$HOME:*" in ~:*) echo M;; *) echo o;; esac'),
    ("extent_qmark_in_remainder_is_literal",
     'case "$HOME:Q" in ~:?) echo M;; *) echo o;; esac'),
    ("extent_bracket_in_remainder_is_literal",
     'case "$HOME:a" in ~:[a]) echo M;; *) echo o;; esac'),
    ("extent_bracket_matches_itself",
     'case "$HOME:[a]" in ~:[a]) echo M;; *) echo o;; esac'),
    ("extent_test_eq_star_is_literal",
     'if [[ "$HOME:XX" == ~:* ]]; then echo M; else echo o; fi'),
    ("extent_test_eq_star_matches_itself",
     'if [[ "$HOME:*" == ~:* ]]; then echo M; else echo o; fi'),
    ("extent_regex_dot_is_literal",
     'if [[ "$HOME:X" =~ ~:. ]]; then echo M; else echo o; fi'),
    ("extent_regex_dot_matches_itself",
     'if [[ "$HOME:." =~ ~:. ]]; then echo M; else echo o; fi'),
    ("extent_dirstack_star_is_literal",
     'cd /; case "/:XX" in ~+:*) echo M;; *) echo o;; esac'),
    # The '/' BOUNDS the tilde word: past it, the source word's glob is live.
    ("extent_slash_bounds_the_literal_zone",
     'case "$HOME:*/YY" in ~:*/*) echo M;; *) echo o;; esac'),
]

#: The multi-PART form: `~:$u` is a tilde extent spilling into an expansion
#: part, which the collapse rewrites into one pre-expanded literal. The
#: expansion is taken VERBATIM (bash's tilde_find_word quirk), so the subject
#: carries the literal text `$u`, not its value.
COLON_EXTENT_MULTIPART_ROWS = [
    ("extent_multipart_case_near_miss",
     "u=Z; case '{subject}:$u' in ~:$u) echo M;; *) echo o;; esac"),
    ("extent_multipart_case_exact",
     "u=Z; case \"$HOME:\\$u\" in ~:$u) echo M;; *) echo o;; esac"),
    ("extent_multipart_test_eq_near_miss",
     "u=Z; if [[ '{subject}:$u' == ~:$u ]]; then echo M; else echo o; fi"),
    ("extent_multipart_test_eq_exact",
     "u=Z; if [[ \"$HOME:\\$u\" == ~:$u ]]; then echo M; else echo o; fi"),
    ("extent_multipart_regex_exact_rc",
     "u=Z; [[ \"$HOME:\\$u\" =~ ~:$u ]]; echo rc=$?"),
]


class TestColonExtentCollapseSite(ConformanceTest):
    """The whole tilde WORD is literal, remainder included (V2-B1)."""

    @pytest.mark.parametrize("home", ["/h/me", "/a*b", "/a[b]"])
    @pytest.mark.parametrize("command", [c for _, c in COLON_EXTENT_ROWS],
                             ids=[n for n, _ in COLON_EXTENT_ROWS])
    def test_single_part_extent(self, command, home):
        self.assert_identical_behavior(command, env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    @pytest.mark.parametrize(
        "command", [c for _, c in COLON_EXTENT_MULTIPART_ROWS],
        ids=[n for n, _ in COLON_EXTENT_MULTIPART_ROWS])
    def test_multipart_extent(self, command, home, subject):
        self.assert_identical_behavior(
            command.replace("{subject}", subject), env={"HOME": home})


@pytest.mark.parametrize("home", ["/h/me", "/a*b"])
@pytest.mark.parametrize("command", [c for _, c in COLON_EXTENT_ROWS],
                         ids=[n for n, _ in COLON_EXTENT_ROWS])
def test_colon_extent_all_three_input_modes(command, home, tmp_path):
    """D6: the tilde-word boundary holds in all three input modes."""
    env = {"HOME": home}
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(env))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    for mode in ("dash_c", "script", "stdin"):
        mode_dir = tmp_path / mode
        mode_dir.mkdir()
        if mode == "dash_c":
            run = run_psh(["-c", command], cwd=str(mode_dir), env=dict(env))
        elif mode == "script":
            script = mode_dir / "case.sh"
            script.write_text(command + "\n")
            run = run_psh([str(script)], cwd=str(mode_dir), env=dict(env))
        else:
            run = run_psh([], stdin_data=command + "\n", cwd=str(mode_dir),
                          env=dict(env))
        assert is_comparable(run), f"harness failure in {mode}: {run!r}"
        assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
            f"{mode} mode, HOME={home!r}, {command!r}: "
            f"psh={(run.stdout, run.returncode)!r} "
            f"bash={(bash.stdout, bash.returncode)!r}")


# ---------------------------------------------------------------------------
# The assignment colon-segment site — round 2 left it on one golden row.
# ---------------------------------------------------------------------------

ASSIGNMENT_SEGMENT_ROWS = [
    ("assign_value_tilde_exact_subject",
     'case "x=a:$HOME:b" in x=a:~:b) echo M;; *) echo o;; esac'),
    ("assign_value_tilde_head_stays_raw",
     'case "x+=$HOME" in x+=~) echo M;; *) echo o;; esac'),
    ("assign_value_tilde_first_segment",
     'case "x=$HOME:b" in x=~:b) echo M;; *) echo o;; esac'),
    ("assign_value_tilde_test_eq",
     'if [[ "x=a:$HOME:b" == x=a:~:b ]]; then echo M; else echo o; fi'),
    ("assign_value_tilde_regex_rc",
     '[[ "x=a:$HOME:b" =~ x=a:~:b ]]; echo rc=$?'),
    ("assign_value_tilde_slash_tail_live",
     'case "x=$HOME/abc" in x=~/a*) echo M;; *) echo o;; esac'),
]


class TestAssignmentSegmentSite(ConformanceTest):
    """The assignment colon-segment escape, pinned outside the golden file."""

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    @pytest.mark.parametrize("command",
                             [c for _, c in ASSIGNMENT_SEGMENT_ROWS],
                             ids=[n for n, _ in ASSIGNMENT_SEGMENT_ROWS])
    def test_exact_subject(self, command, home):
        self.assert_identical_behavior(command, env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_near_miss_does_not_match(self, home, subject):
        self.assert_identical_behavior(
            f'case {"x=a:" + subject + ":b"!r} in x=a:~:b) '
            'echo M;; *) echo o;; esac',
            env={"HOME": home})

    @pytest.mark.parametrize("home,subject", GLOB_DECOYS, ids=GLOB_DECOY_IDS)
    def test_near_miss_first_segment(self, home, subject):
        self.assert_identical_behavior(
            f'case {"x=" + subject + ":b"!r} in x=~:b) '
            'echo M;; *) echo o;; esac',
            env={"HOME": home})


# ---------------------------------------------------------------------------
# The ASSIGNMENT-shaped exception to the tilde-word rule.
#
# In an assignment-shaped word bash's tilde word ends at `:` as well as `/`, so
# the remainder after a `:` stays LIVE — the opposite of the plain rule. Round 3
# stated the rule without this exception in four places while the code had it
# right, and no row in any layer could see the difference: a mutation applying
# the stated rule uniformly (the round-3 verifier's M5) left 0/127 unit, 0/60
# golden and 0/549 conformance nodes red. These rows are what dies under it.
#
# Every corpus row before this one puts a metacharacter-free segment after the
# tilde (`x=a:~:b`, `x=~:b`, `x+=~`), so the escape's scope past the colon was
# unobservable in all of them. The metacharacter has to live in a LATER SEGMENT,
# not in HOME, for the decision to show.
# ---------------------------------------------------------------------------

ASSIGNMENT_COLON_EXCEPTION_ROWS = [
    # bash MATCHES: assignment-shaped, so ':' ended the tilde word and the '*'
    # in the later segment is a live pattern.
    ("assign_colon_remainder_is_live",
     'case "x=$HOME:XX" in x=~:*) echo M;; *) echo o;; esac'),
    ("assign_colon_remainder_is_live_mid_value",
     'case "x=a:$HOME:XX" in x=a:~:*) echo M;; *) echo o;; esac'),
    ("assign_colon_remainder_is_live_append",
     'case "x+=$HOME:XX" in x+=~:*) echo M;; *) echo o;; esac'),
    ("assign_colon_remainder_is_live_qmark",
     'case "x=$HOME:Q" in x=~:?) echo M;; *) echo o;; esac'),
    ("assign_colon_remainder_is_live_bracket",
     'case "x=$HOME:a" in x=~:[a]) echo M;; *) echo o;; esac'),
    ("assign_colon_remainder_live_test_eq",
     'if [[ "x=$HOME:XX" == x=~:* ]]; then echo M; else echo o; fi'),
    # bash does NOT match: the same shape WITHOUT the assignment prefix, where
    # the ':' is inside the tilde word and the '*' is literal. This control is
    # what makes the rows above mean something.
    ("control_no_assignment_remainder_is_literal",
     'case "$HOME:XX" in ~:*) echo M;; *) echo o;; esac'),
    ("control_no_assignment_remainder_matches_itself",
     'case "$HOME:*" in ~:*) echo M;; *) echo o;; esac'),
    # The replacement itself is still escaped inside an assignment: the
    # exception widens the live zone, it does not switch the escape off.
    ("assign_replacement_still_escaped",
     'case "x=$HOME:XX" in x=~:*) echo M;; *) echo o;; esac; '
     'case "x=/aXb:YY" in x=~:*) echo M2;; *) echo o2;; esac'),
]


class TestAssignmentColonExceptionSite(ConformanceTest):
    """`:` ends the tilde word in an assignment-shaped word (round-4 B1)."""

    @pytest.mark.parametrize("home", ["/h/me", "/a*b", "/a[b]"])
    @pytest.mark.parametrize(
        "command", [c for _, c in ASSIGNMENT_COLON_EXCEPTION_ROWS],
        ids=[n for n, _ in ASSIGNMENT_COLON_EXCEPTION_ROWS])
    def test_matches_bash(self, command, home):
        self.assert_identical_behavior(command, env={"HOME": home})


@pytest.mark.parametrize("home", ["/h/me", "/a*b"])
@pytest.mark.parametrize(
    "command", [c for _, c in ASSIGNMENT_COLON_EXCEPTION_ROWS],
    ids=[n for n, _ in ASSIGNMENT_COLON_EXCEPTION_ROWS])
def test_assignment_colon_exception_all_three_input_modes(command, home,
                                                          tmp_path):
    """D6: the exception holds in -c, script-file and stdin mode."""
    env = {"HOME": home}
    bash_dir = tmp_path / "bash"
    bash_dir.mkdir()
    bash = run_bash(["-c", command], cwd=str(bash_dir), env=dict(env))
    assert is_comparable(bash), f"bash harness failure: {bash!r}"

    for mode in ("dash_c", "script", "stdin"):
        mode_dir = tmp_path / mode
        mode_dir.mkdir()
        if mode == "dash_c":
            run = run_psh(["-c", command], cwd=str(mode_dir), env=dict(env))
        elif mode == "script":
            script = mode_dir / "case.sh"
            script.write_text(command + "\n")
            run = run_psh([str(script)], cwd=str(mode_dir), env=dict(env))
        else:
            run = run_psh([], stdin_data=command + "\n", cwd=str(mode_dir),
                          env=dict(env))
        assert is_comparable(run), f"harness failure in {mode}: {run!r}"
        assert (run.stdout, run.returncode) == (bash.stdout, bash.returncode), (
            f"{mode} mode, HOME={home!r}, {command!r}: "
            f"psh={(run.stdout, run.returncode)!r} "
            f"bash={(bash.stdout, bash.returncode)!r}")


@pytest.mark.parametrize("pattern,lit", [("~:*", "*"), ("~:?", "?"),
                                         ("~:[a]", "[a]")])
def test_four_subject_separation(pattern, lit, tmp_path):
    """Four subjects per pattern, because `o` alone proves nothing.

    A shell that never tilde-expanded also answers `o` to
    `case '/h/me:XX' in ~:*)`. Only the whole M/o/o/o ROW identifies "expanded,
    then the whole word made literal" — and WHICH cell does the separating is
    pattern dependent, which is why every row is asserted rather than one cell.
    Measured against the two psh tips that embody the rival hypotheses
    (`b6ec6f95` never expanded; `f712bc1e` expanded but left the metacharacter
    live):

        ~:*    correct M/o/o/o   left-live M/M/o/o   never-expanded o/o/M/M
        ~:[a]  correct M/o/o/o   left-live o/o/o/o   never-expanded o/o/o/o
        ~:?    correct M/o/o/o   left-live M/o/o/o (indistinguishable here)

    So at `~:*` it is column 2 that kills "left live"; at `~:[a]` column 1 does;
    at `~:?` the pattern pins only the never-expanded direction.
    """
    env = {"HOME": "/h/me"}
    subjects = [f"/h/me:{lit}", "/h/me:XX", f"~:{lit}", "~:XX"]
    command = "; ".join(
        f"case {s!r} in {pattern}) echo M;; *) echo o;; esac" for s in subjects)
    bash = run_bash(["-c", command], cwd=str(tmp_path), env=dict(env))
    run = run_psh(["-c", command], cwd=str(tmp_path), env=dict(env))
    assert is_comparable(bash) and is_comparable(run), (bash, run)
    assert bash.stdout == "M\no\no\no\n", (pattern, bash.stdout)
    assert run.stdout == bash.stdout, (pattern, run.stdout, bash.stdout)
