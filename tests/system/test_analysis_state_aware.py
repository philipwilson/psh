"""Analysis modes see the state the script establishes (remediation 2.6).

MEDIUM-9(a): analysis parsed the whole input under the option state the shell
was CONSTRUCTED with, while execution parses unit by unit under state that
evolves — so `shopt -s extglob` on line 1 plus `+(...)` on line 2 EXECUTED
(rc 0) and FAILED `--validate` (rc 2, syntax error). The analysis session
(`psh/scripting/analysis_session.py`) walks execution's own unit boundaries and
threads parse-relevant state between units without executing anything.

RED-ON-BASE: every row in `test_state_aware_signature` is rc 2 at 42f75591 and
rc != 2 here, on all three channels and both parsers, for all five modes.

Not every class here is red at BASE, and the distinction matters. Three classes
are red at the DISSOLVED round-1 tip 053750e5 instead, because they pin
regressions this slot's own fix rounds introduced and then removed:
`TestHeredocBodiesAreNotCommandText` (a body-blind re-lex),
`TestAliasPositionDiscipline` (a position-blind re-walk), and the
help/version rows in `TestModeCombinationRejected`. Each says so in its own
docstring; none is presented as base evidence.

DECLARED REGRESSION GUARDS (not red-on-base evidence — remediation 2.6 R1-G):
`test_alias_defined_then_used_*` was already GREEN at base, because whole-file
analysis lexed the file as ONE token stream and `AliasManager.expand_aliases`
honours a definition made earlier in the same stream. Going per-unit is exactly
where that could have been lost, so these rows guard it.

ORACLES: two distinct ones, never mixed in a row — `bash` EXECUTING and the
same binary under `-n`. `bash -n` does not execute `shopt` either, so it
reports the same false syntax error psh used to; psh's divergence from it is
deliberate and pinned in `test_two_static_surfaces_split`.
"""
import re

import pytest

from tests.harness.shell_oracle import is_comparable, run_bash, run_psh

PARSERS = ["rd", "combinator"]
MODES = ["validate", "format", "metrics", "security", "lint"]

# The #22 signature: parse-relevant option enabled in unit 1, used in unit 2.
EXTGLOB_SCRIPT = "shopt -s extglob\ncase ab in +(a)b) echo MATCH;; esac\n"
# Same content as ONE unit — execution fails too, so analysis must also fail.
SAME_UNIT_SCRIPT = "shopt -s extglob; case ab in +(a)b) echo MATCH;; esac\n"
# No parse-relevant state change anywhere.
PLAIN_SCRIPT = "x=1\nif [ \"$x\" = 1 ]; then\n  echo one\nfi\n"


def _script(tmp_path, text, name="s.sh"):
    (tmp_path / name).write_text(text)
    return str(tmp_path)


def _psh(tmp_path, args, *, stdin=None):
    return run_psh(args, cwd=str(tmp_path), stdin_data=stdin)


class TestStateAwareAnalysis:
    """MEDIUM-9(a): what executes must analyze."""

    @pytest.mark.parametrize("parser", PARSERS)
    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("channel", ["file", "command", "stdin"])
    def test_state_aware_signature(self, tmp_path, parser, mode, channel):
        _script(tmp_path, EXTGLOB_SCRIPT)
        flags = ["--parser", parser, f"--{mode}"]
        if channel == "file":
            result = _psh(tmp_path, flags + ["s.sh"])
        elif channel == "command":
            result = _psh(tmp_path, flags + ["-c", EXTGLOB_SCRIPT])
        else:
            result = _psh(tmp_path, flags, stdin=EXTGLOB_SCRIPT)
        assert is_comparable(result)
        # rc 2 is the syntax-error status. Any other status means the unit
        # PARSED — which is the whole claim; the per-mode status (0 or 1 for
        # findings) is that mode's own business.
        assert result.returncode != 2, result.stderr
        assert "Parse error" not in result.stderr

    @pytest.mark.parametrize("parser", PARSERS)
    def test_script_executes_at_both_ends(self, tmp_path, parser):
        """The control the signature rests on: this script RUNS, and = bash."""
        _script(tmp_path, EXTGLOB_SCRIPT)
        psh = _psh(tmp_path, ["--parser", parser, "s.sh"])
        bash = run_bash(["s.sh"], cwd=str(tmp_path))
        assert is_comparable(psh) and is_comparable(bash)
        assert (psh.returncode, psh.stdout) == (bash.returncode, bash.stdout)
        assert psh.stdout == "MATCH\n"

    @pytest.mark.parametrize("parser", PARSERS)
    def test_same_unit_change_does_not_apply(self, tmp_path, parser):
        """A directive cannot affect the parse of its OWN unit — execution's
        rule, so analysis must not be more permissive than execution here."""
        _script(tmp_path, SAME_UNIT_SCRIPT)
        execution = _psh(tmp_path, ["--parser", parser, "s.sh"])
        analysis = _psh(tmp_path, ["--parser", parser, "--validate", "s.sh"])
        bash = run_bash(["s.sh"], cwd=str(tmp_path))
        assert is_comparable(execution) and is_comparable(analysis)
        assert is_comparable(bash)
        assert execution.returncode == 2 and bash.returncode == 2
        assert analysis.returncode == 2


class TestTransitionRule:
    """Rule R3 (remediation 2.6 R1-F): monotone enables, isolation respected."""

    @pytest.mark.parametrize("script,applies", [
        # reached and not isolated — execution says LIVE, analysis agrees
        ("if true; then shopt -s extglob; fi\necho @(a|b)\n", True),
        ("true && shopt -s extglob\necho @(a|b)\n", True),
        ("{ shopt -s extglob; }\necho @(a|b)\n", True),
        ("for i in a; do shopt -s extglob; done\necho @(a|b)\n", True),
        ("e() { shopt -s extglob; }\ne\necho @(a|b)\n", True),
        ("set -o extglob\necho @(a|b)\n", True),
        # STATE-ISOLATED — execution discards the change, so analysis must too
        ("( shopt -s extglob )\necho @(a|b)\n", False),
        ("shopt -s extglob | cat\necho @(a|b)\n", False),
        ("x=$(shopt -s extglob)\necho @(a|b)\n", False),
        ("shopt -s extglob &\nwait\necho @(a|b)\n", False),
        # R11-B N1, ENABLE direction: a never-reached ENABLE is treated as
        # LIVE, the declared permissiveness of the monotone rule.
        ("e() { shopt -s extglob; }\necho @(a|b)\n", True),
        ("while false; do shopt -s extglob; done\necho @(a|b)\n", True),
        ("case z in a) shopt -s extglob;; esac\necho @(a|b)\n", True),
        ("true || shopt -s extglob\necho @(a|b)\n", True),
        # R11-B N1 AS ORDERED, DISABLE direction: the never-reached class is
        # about DISABLES, where the monotone rule does the opposite work — the
        # disable is IGNORED, so an earlier enable survives and the construct
        # still parses. Round 4 caught the enable mirrors above being shipped
        # in place of these; they are the deliverable.
        ("shopt -s extglob\ne() { shopt -u extglob; }\necho @(a|b)\n", True),
        ("shopt -s extglob\nwhile false; do shopt -u extglob; done\n"
         "echo @(a|b)\n", True),
        ("shopt -s extglob\ncase z in a) shopt -u extglob;; esac\n"
         "echo @(a|b)\n", True),
        ("shopt -s extglob\ntrue || shopt -u extglob\necho @(a|b)\n", True),
    ])
    def test_isolation_decides_whether_a_change_applies(self, tmp_path,
                                                        script, applies):
        _script(tmp_path, script)
        result = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(result)
        assert (result.returncode != 2) is applies, result.stderr

    def test_disable_is_permissive_by_design(self, tmp_path):
        """DECLARED PERMISSIVE ROW (R1-F). A disable never narrows the session
        state: execution rejects this script (extglob is off again by the time
        line 3 parses) while analysis accepts it. Narrowing would let a
        conditional disable re-invent the false syntax errors this session
        exists to remove, so analysis stays a SUPERSET — it can miss an error,
        never invent one. Asserted in the DIVERGENT direction, so closing this
        gap would be a visible flip."""
        _script(tmp_path, "shopt -s extglob\nshopt -u extglob\necho @(a|b)\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 2      # execution rejects
        assert analysis.returncode != 2       # analysis accepts (permissive)

    @pytest.mark.parametrize("script", [
        "eval 'shopt -s extglob'\necho @(a|b)\n",
        "printf 'shopt -s extglob\\n' > sub.sh\n. ./sub.sh\necho @(a|b)\n",
    ])
    def test_declared_residual_eval_and_source_stay_blind(self, tmp_path, script):
        """DECLARED DIVERGENCE (R1-C). A directive inside an `eval` STRING or a
        `source`d FILE is invisible to analysis: seeing it would mean executing
        the very thing analysis promises not to execute. Execution applies it;
        analysis does not. Asserted in the divergent direction."""
        _script(tmp_path, script)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0      # execution applies it
        assert analysis.returncode == 2       # analysis cannot see it


class TestAliasRegressionGuards:
    """DECLARED REGRESSION GUARDS — GREEN AT BASE (R1-G), not red-on-base.

    Whole-file analysis threaded alias state for free (one file = one token
    stream). Per-unit analysis has to carry definitions forward itself, so
    these rows exist to catch the one thing going incremental could have LOST.
    """

    @pytest.mark.parametrize("parser", PARSERS)
    @pytest.mark.parametrize("channel", ["file", "command", "stdin"])
    def test_alias_defined_then_used_still_analyzes(self, tmp_path, parser,
                                                    channel):
        script = "alias iff='if true; then'\niff echo X; fi\n"
        _script(tmp_path, script)
        flags = ["--parser", parser, "--validate"]
        if channel == "file":
            result = _psh(tmp_path, flags + ["s.sh"])
        elif channel == "command":
            result = _psh(tmp_path, flags + ["-c", script])
        else:
            result = _psh(tmp_path, flags, stdin=script)
        assert is_comparable(result)
        assert result.returncode == 0, result.stderr

    def test_format_still_does_not_expand_aliases(self, tmp_path):
        """The #19 T6 ruling survives verbatim: --format is source-to-source,
        so it reprints the user's word and never the alias body."""
        _script(tmp_path, 'alias zz="printf UNIQUE_XYZ"\nzz\n')
        result = _psh(tmp_path, ["--format", "s.sh"])
        assert is_comparable(result)
        assert result.stdout.count("UNIQUE_XYZ") == 1, result.stdout
        assert "zz" in result.stdout.splitlines()[-1]


class TestTwoStaticSurfaces:
    """R1-E: psh has two static checks and they answer different questions."""

    def test_two_static_surfaces_split(self, tmp_path):
        """`-n` is bash's `set -n` and stays pinned to it — bash -n does not
        execute `shopt`, so both report the syntax error. `--validate` is psh's
        own analysis and is state-aware. The divergence is deliberate."""
        _script(tmp_path, EXTGLOB_SCRIPT)
        psh_n = _psh(tmp_path, ["-n", "s.sh"])
        bash_n = run_bash(["-n", "s.sh"], cwd=str(tmp_path))
        validate = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(psh_n) and is_comparable(bash_n)
        assert is_comparable(validate)
        assert psh_n.returncode == bash_n.returncode == 2   # pinned together
        assert validate.returncode == 0                     # deliberately not


class TestUnitLineDiagnostics:
    """R1-B: an analysis syntax error names its line, as execution's does.

    At base analysis had no line to name — the whole input was one parse, so
    the prefix was a bare `psh: <source>:`. Parsing unit by unit gives analysis
    the same `<source>:<line>:` prefix execution prints.
    """

    SCRIPT = "echo fine\necho also fine\nif\n"

    @pytest.mark.parametrize("channel", ["file", "command", "stdin"])
    def test_syntax_error_carries_its_line(self, tmp_path, channel):
        """rd: the reported line is the line the error is really on (3)."""
        _script(tmp_path, self.SCRIPT)
        flags = ["--parser", "rd", "--validate"]
        if channel == "file":
            result = _psh(tmp_path, flags + ["s.sh"])
            label = "s.sh"
        elif channel == "command":
            result = _psh(tmp_path, flags + ["-c", self.SCRIPT])
            label = "-c"
        else:
            result = _psh(tmp_path, flags, stdin=self.SCRIPT)
            label = "<stdin>"
        assert is_comparable(result)
        assert result.returncode == 2
        assert f"psh: {label}:3:" in result.stderr, result.stderr

    @pytest.mark.parametrize("parser", PARSERS)
    def test_analysis_location_matches_execution_location(self, tmp_path, parser):
        """The claim that survives BOTH parsers: analysis reports a syntax
        error at the same place execution does.

        Under `--parser combinator` that place is line 1 rather than line 3,
        because the combinator never stamps top-level statement lines. That is
        the PRE-EXISTING campaign-ledger row

            2.2 carry: combinator ignores line_offset for TOP-LEVEL statements

        (unified LEDGER Part D, owned by the parser successor). Analysis does
        not inherit it from this slot — it CONVERGES on execution, which has
        always reported that line. Deriving the expected prefix from execution
        rather than hard-coding it means this row keeps passing when the carry
        closes; `test_combinator_toplevel_line_is_the_2_2_carry` is the
        tripwire that ANNOUNCES the close.
        """
        _script(tmp_path, self.SCRIPT)
        execution = _psh(tmp_path, ["--parser", parser, "s.sh"])
        analysis = _psh(tmp_path, ["--parser", parser, "--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == analysis.returncode == 2
        prefix = [line for line in execution.stderr.splitlines()
                  if line.startswith("psh: s.sh:")][0].split(" Parse error")[0]
        assert prefix in analysis.stderr, (prefix, analysis.stderr)

    def test_combinator_toplevel_line_is_the_2_2_carry(self, tmp_path):
        """CARRY TRIPWIRE — EXPECTED TO FLIP, and that is the point.

        This asserts the combinator's CURRENT, WRONG line number (1 for an
        error on line 3) on both the analysis and execution surfaces, so that
        closing

            2.2 carry: combinator ignores line_offset for TOP-LEVEL statements

        fails here loudly instead of improving psh in silence. When that carry
        closes, delete this test and tighten the sibling row above to assert
        line 3 for both parsers. A failure here is NOT a regression in slot
        2.6 — it is the carry being fixed.
        """
        _script(tmp_path, self.SCRIPT)
        analysis = _psh(tmp_path, ["--parser", "combinator", "--validate", "s.sh"])
        execution = _psh(tmp_path, ["--parser", "combinator", "s.sh"])
        assert is_comparable(analysis) and is_comparable(execution)
        assert "psh: s.sh:1:" in analysis.stderr, analysis.stderr
        assert "psh: s.sh:1:" in execution.stderr, execution.stderr


class TestHeredocWordCorruption:
    """R1-D co-land: whole-file analysis corrupted words after a heredoc body.

    NOT the r18 lexer no-progress crash and NOT the scanner-balancing class:
    nothing crashes here and no construct is left unterminated — this is a
    span-offset bug that only the whole-file analysis parse could reach,
    because only it put a heredoc BODY and a later command in one buffer.
    Base (42f75591, rd): the loop variable parses as `F\\n}\\n` and --format
    reprints a broken header. Execution and the combinator were always correct.
    """

    SCRIPT = ("usage() {\n    cat <<EOF\nabc\nEOF\n}\n"
              "for file in a b; do echo $file; done\n")

    @pytest.mark.parametrize("parser", PARSERS)
    def test_word_after_heredoc_body_is_intact(self, tmp_path, parser):
        _script(tmp_path, self.SCRIPT)
        result = _psh(tmp_path, ["--parser", parser, "--format", "s.sh"])
        assert is_comparable(result)
        assert "for file in a b; do" in result.stdout, result.stdout

    def test_validator_sees_the_real_loop_variable(self, tmp_path):
        """The corruption reached the AST, not just the formatter."""
        _script(tmp_path, self.SCRIPT)
        result = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(result)
        assert result.returncode == 0, result.stderr
        assert "var: file" in result.stdout, result.stdout
        assert "var: F" not in result.stdout, result.stdout

    def test_metrics_counted_the_corrupted_word_as_a_variable(self, tmp_path):
        """R8-E-2: the --metrics face of the same corruption. The mangled loop
        variable was counted as an extra variable, so the reported figure was
        silently wrong — no error, just a number nobody could check. Base
        (42f75591, rd) reported 4; the correct count is 3."""
        _script(tmp_path, self.SCRIPT)
        result = _psh(tmp_path, ["--metrics", "s.sh"])
        assert is_comparable(result)
        assert "Variables Used:             3" in result.stdout, result.stdout

    def test_execution_control_unchanged(self, tmp_path):
        """Execution never had the bug and still does not — = bash."""
        _script(tmp_path, self.SCRIPT)
        psh = _psh(tmp_path, ["s.sh"])
        bash = run_bash(["s.sh"], cwd=str(tmp_path))
        assert is_comparable(psh) and is_comparable(bash)
        assert (psh.returncode, psh.stdout) == (bash.returncode, bash.stdout)
        assert psh.stdout == "a\nb\n"


class TestFormatPosixRender:
    """R1-J: --format threads OPTION state, so it cannot change meaning.

    Base: `set -o posix` then `echo $äö` reprinted as `echo ${äö}` — under
    posix the lexer treats `$äö` as LITERAL text, so the base output turned
    literal text into a variable expansion. Declared improvement.
    """

    def test_posix_literal_is_not_reprinted_as_an_expansion(self, tmp_path):
        _script(tmp_path, "set -o posix\necho $äö\n")
        result = _psh(tmp_path, ["--format", "s.sh"])
        assert is_comparable(result)
        assert "${äö}" not in result.stdout, result.stdout
        assert "echo $äö" in result.stdout, result.stdout

    def test_validate_stops_reporting_issues_about_a_literal(self, tmp_path):
        """R8-E-2: the --validate face of the same mis-parse. Reading `$äö` as
        an expansion under posix produced TWO findings about a variable that
        does not exist in the script — an undefined-variable warning and an
        unquoted-expansion info. Base (42f75591) reported 2 issues; the correct
        answer is none, because posix makes that text literal."""
        _script(tmp_path, "set -o posix\necho $äö\n")
        result = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(result)
        assert result.returncode == 0
        assert "No issues found" in result.stdout, result.stdout

    def test_posix_named_fd_is_a_word_not_a_redirect(self, tmp_path):
        """R8-E-2: the named-fd face. Under posix the lexer does not accept a
        non-portable `{name}` as a file-descriptor name, so `exec {äö}<f` is a
        COMMAND followed by a redirect. Base reprinted it as the named-fd form
        it had mis-parsed."""
        _script(tmp_path, "set -o posix\nexec {äö}<f\n")
        result = _psh(tmp_path, ["--format", "s.sh"])
        assert is_comparable(result)
        assert "exec {äö} <f" in result.stdout, result.stdout


class TestModeCombinationRejected:
    """MEDIUM-9(b) / R1-A, end to end at the CLI."""

    @pytest.mark.parametrize("flags", [
        ["--validate", "--lint"],
        ["--lint", "--validate"],
        ["--security", "--format"],
        ["--validate", "--format", "--metrics", "--security", "--lint"],
    ])
    def test_distinct_modes_are_a_usage_error(self, tmp_path, flags):
        _script(tmp_path, PLAIN_SCRIPT)
        result = _psh(tmp_path, flags + ["s.sh"])
        assert is_comparable(result)
        assert result.returncode == 2
        for flag in flags:
            assert flag in result.stderr, result.stderr
        # The run analyzed NOTHING — rejection precedes Shell construction.
        assert result.stdout == ""

    @pytest.mark.parametrize("flags,expect", [
        (["--help", "--validate", "--lint"], "Usage: psh"),
        (["--validate", "--lint", "--help"], "Usage: psh"),
        (["--version", "--validate", "--lint"], "version"),
        (["--validate", "--lint", "--version"], "version"),
    ])
    def test_help_and_version_still_answer(self, tmp_path, flags, expect):
        """R8-E-1: the exclusivity rule must not swallow --help/--version.
        RED at the dissolved tip 62f2bd45 (rc 2, usage error); base and this
        tip both answer with rc 0."""
        _script(tmp_path, PLAIN_SCRIPT)
        result = _psh(tmp_path, flags)
        assert is_comparable(result)
        assert result.returncode == 0, result.stderr
        assert expect in result.stdout, result.stdout

    def test_repeating_one_mode_is_fine(self, tmp_path):
        _script(tmp_path, PLAIN_SCRIPT)
        once = _psh(tmp_path, ["--lint", "s.sh"])
        twice = _psh(tmp_path, ["--lint", "--lint", "s.sh"])
        assert is_comparable(once) and is_comparable(twice)
        assert (once.returncode, once.stdout) == (twice.returncode, twice.stdout)


class TestHeredocBodiesAreNotCommandText:
    """R8-A regression pins. RED AT THE DISSOLVED TIP 62f2bd45, not at base.

    The first analysis session absorbed alias state by re-tokenizing each
    unit's RAW TEXT with the plain lexer, which lexes heredoc BODIES as command
    text. Three faces, one cause, one fix: the absorption pass now consumes the
    SAME heredoc-aware token stream the real parse produces, so a body is never
    lexed at all.

    These are REGRESSION pins: base (42f75591) was green, the dissolved tip was
    red. They exist because the round-1 corpus used bodies like `abc`/`body`/`x`
    — an observability gap, since no body could SAY anything a lexer would
    choke on.
    """

    QUOTE_BODIES = [
        "cat <<EOF\nit's here\nEOF\n",                       # apostrophe
        "cat <<EOF\nsay \"hi\"\nEOF\n",                      # double quote
        "cat <<-EOF\n\tit's tabbed\nEOF\n",                  # <<- form
        "cat <<'EOF'\nit's quoted-delimiter\nEOF\n",         # quoted delimiter
        "cat <<EOF\nit's one\nEOF\ncat <<EOF2\nit's two\nEOF2\n",   # two heredocs
        "f() {\n  cat <<EOF\n  it's nested\nEOF\n}\nf\n",    # body in a function
        "cat <<EOF\ndon't `echo x` $(echo y)\nEOF\n",        # body with substitutions
    ]

    @pytest.mark.parametrize("mode", MODES)
    @pytest.mark.parametrize("script", QUOTE_BODIES)
    def test_quote_bearing_heredoc_body_analyzes_clean(self, tmp_path, mode,
                                                       script):
        _script(tmp_path, script)
        analysis = _psh(tmp_path, [f"--{mode}", "s.sh"])
        execution = _psh(tmp_path, ["s.sh"])
        assert is_comparable(analysis) and is_comparable(execution)
        assert execution.returncode == 0, execution.stderr
        assert analysis.returncode != 2, analysis.stderr
        assert "Unclosed" not in analysis.stderr

    def test_alias_inside_a_heredoc_body_is_data_not_state(self, tmp_path):
        """A heredoc body is text the shell hands to a command; an `alias` line
        in one defines nothing. Analysis must reach the same verdict execution
        does — which it cannot if it lexes the body as commands."""
        _script(tmp_path, "cat <<EOF\nalias iff='if true; then'\nEOF\n"
                          "iff echo X; fi\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        # The alias was never defined, so the later line is a syntax error in
        # BOTH surfaces. The pin is the AGREEMENT.
        assert execution.returncode == analysis.returncode == 2

    @pytest.mark.parametrize("parser", PARSERS)
    def test_every_unit_error_carries_a_line_prefix(self, tmp_path, parser):
        """Face three: the lex half used to escape the session's own error
        envelope, printing a bare `psh: file:` with NO line at all. Every
        per-unit lex OR parse failure now routes through the envelope and
        carries a `file:N:` prefix.

        The prefix FORM is what this asserts for both parsers. WHICH N appears
        under `--parser combinator` is governed by the pre-existing row

            2.2 carry: combinator ignores line_offset for TOP-LEVEL statements

        so the literal line is asserted for rd only; the combinator's current
        value is pinned by `test_combinator_toplevel_line_is_the_2_2_carry`.
        """
        _script(tmp_path, "cat <<EOF\nit's fine\nEOF\necho ok\nif\n")
        result = _psh(tmp_path, ["--parser", parser, "--validate", "s.sh"])
        assert is_comparable(result)
        assert result.returncode == 2
        assert re.search(r"^psh: s\.sh:\d+: ", result.stderr, re.M), result.stderr
        if parser == "rd":
            assert "psh: s.sh:5:" in result.stderr, result.stderr


class TestDirectiveSpellingAxis:
    """R8-B/R8-D: a directive is recognized however it is SPELLED.

    Red at base AND at the dissolved tip: the first fix recognized only the
    bare `shopt -s` / `set -o` heads while claiming to apply "every option
    ENABLE found in a parsed unit" — the MEDIUM-9 signature surviving on the
    first axis of the catalogue (spelling).
    """

    ENABLES = [
        "builtin shopt -s extglob",
        "command shopt -s extglob",
        "\\shopt -s extglob",
        "x=1 shopt -s extglob",
        "shopt -sq extglob",
        "shopt -qs extglob",
        "set -e -o extglob",
        "command builtin shopt -s extglob",
        "x=1 y=2 builtin shopt -s extglob",
        # R9-C-3: a backslash before an ordinary character is just quoting, so
        # every one of these runs `shopt` — the head normalizer must see past
        # backslashes ANYWHERE in the word, not only a leading one.
        "sh\\opt -s extglob",
        "s\\hopt -s extglob",
        "shop\\t -s extglob",
        "\\s\\h\\o\\p\\t -s extglob",
        # the -o pair need not be first, and -- after it does not undo it
        "set -o extglob -- a b",
        # R11-A: quoting a command NAME does not change which command runs, so
        # these all execute `shopt` — measured in psh and bash 5.2.26.
        "'shopt' -s extglob",
        '"shopt" -s extglob',
        "sh''opt -s extglob",
        "'sh'opt -s extglob",
        "s'h'opt -s extglob",
        # unquoted backslashes in the FLAG and the OPERAND resolve too
        "shopt -s ext\\glob",
        "shopt \\-s extglob",
    ]

    #: Near-misses: they LOOK like directives and must NOT be treated as one.
    #: Each was MEASURED against execution — every row leaves extglob off.
    NON_ENABLES = [
        "shopt -p extglob",        # print, not set
        "shopt -u extglob",        # unset (monotone: never narrows, but also
                                   # must not ENABLE)
        "myshopt -s extglob",      # different command
        "shopts -s extglob",       # different command
        "echo shopt -s extglob",   # an argument, not a command
        "set -s extglob",          # -s is not -o
        "shopt -s histappend",     # a real option, but not parse-relevant
        "set -o pipefail",         # ditto
        # R9-C-1: `--` ends option scanning; these set $1/$2 instead.
        "set -- -o extglob",
        "set -e -- -o extglob",
        # R9-C-2: a cluster carrying BOTH letters is refused by the builtin
        # ("cannot set and unset shell options simultaneously", rc 1, option
        # untouched) — measured identical in psh and bash 5.2.26.
        "shopt -su extglob",
        "shopt -us extglob",
        # R13-A: the SEPARATE-WORD spelling of the same refusal. The corpus
        # above held the cluster SHAPE constant, so the recognizer encoded the
        # measurement for one spelling of a rule the builtin applies to both.
        "shopt -s -u extglob",
        "shopt -u -s extglob",
        "shopt -s -q -u extglob",
        # R11-A: a QUOTED backslash is ordinary text, so these are commands of
        # that literal name, not `shopt`. Both shells agree; the recognizer
        # must read the lexer's per-part quote context rather than strip
        # backslashes on sight.
        "'sh\\opt' -s extglob",
        '"sh\\\\opt" -s extglob',
        "'shopt -s extglob'",
        # the operand mirror: a quoted backslash in the OPTION NAME too
        "shopt -s 'ext\\glob'",
    ]

    @pytest.mark.parametrize("directive", ENABLES)
    def test_spelling_is_recognized(self, tmp_path, directive):
        _script(tmp_path, f"{directive}\necho @(a|b)\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0, execution.stderr
        assert analysis.returncode != 2, analysis.stderr

    @pytest.mark.parametrize("directive", NON_ENABLES)
    def test_near_miss_is_not_mistaken_for_a_directive(self, tmp_path,
                                                       directive):
        """The recognizer must not become a substring search: each of these
        leaves extglob OFF, so the later line stays a syntax error."""
        _script(tmp_path, f"{directive}\necho @(a|b)\n")
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(analysis)
        assert analysis.returncode == 2, analysis.stdout


class TestExpandAliasesIsOrderedNotMonotone:
    """R8-B: expand_aliases follows its MEASURED semantics, not the monotone
    rule extglob/posix use.

    Execution truth table (psh, script channel), measured before the fix:
      define,use -> expanded · define,DISABLE,use -> NOT expanded (127)
      define,disable,ENABLE,use -> expanded · disable in SUBSHELL -> expanded
      disable in if-TRUE -> NOT expanded · disable in if-FALSE -> expanded
    Analysis follows the value rule (last write wins) under the same STRUCTURAL
    rules as every other option; it cannot evaluate reachability, which is the
    declared cost pinned by the last row here.
    """

    ALIAS = "alias iff='if true; then'\n"
    USE = "iff echo X; fi\n"

    def test_disable_stops_expansion_in_later_units(self, tmp_path):
        _script(tmp_path, self.ALIAS + "shopt -u expand_aliases\n" + self.USE)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 2 and analysis.returncode == 2

    def test_re_enabling_restores_expansion(self, tmp_path):
        _script(tmp_path, self.ALIAS + "shopt -u expand_aliases\n"
                          "shopt -s expand_aliases\n" + self.USE)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0 and analysis.returncode == 0

    def test_disable_inside_a_subshell_does_not_escape(self, tmp_path):
        _script(tmp_path, self.ALIAS + "( shopt -u expand_aliases )\n" + self.USE)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0 and analysis.returncode == 0

    def test_definitions_still_land_while_expansion_is_off(self, tmp_path):
        """`alias` DEFINES even when expansion is unset — only expansion is
        gated — so re-enabling later finds the alias already there."""
        _script(tmp_path, "shopt -u expand_aliases\n" + self.ALIAS
                          + "shopt -s expand_aliases\n" + self.USE)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0 and analysis.returncode == 0

    def test_unreached_conditional_disable_is_the_declared_cost(self, tmp_path):
        """DECLARED DIVERGENCE (R8-B). Ordered semantics mean a disable that
        execution never reaches still narrows analysis — the one place the
        option axis can produce a false syntax error, accepted because
        modelling expand_aliases as monotone would model a shell nobody runs.
        Asserted in the DIVERGENT direction so closing it is a visible flip."""
        _script(tmp_path, self.ALIAS
                          + "if false; then shopt -u expand_aliases; fi\n"
                          + self.USE)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0      # execution never disables
        assert analysis.returncode == 2       # analysis does — declared


class TestAliasPositionDiscipline:
    """R9-A regression pins. THREE-POINT SHAPE: green at base 42f75591, RED at
    the dissolved tip 053750e5, green here.

    The fix round absorbed alias definitions by scanning each unit's token
    stream for the WORDS `alias`/`unalias` — which dropped the command-position
    guard the real expander applies. The shell only treats those words as
    commands in command position; as ARGUMENTS they are ordinary text.

    This was the slot's SECOND reinvention of an existing decider (the first
    dropped the heredoc grammar). The absorption pass now RUNS
    `AliasManager.expand_aliases` with the session table as its overlay, so the
    position discipline is inherited rather than re-derived: a decider's guards
    are part of the decider.
    """

    def test_argument_position_unalias_does_not_wipe_the_table(self, tmp_path):
        """FACE 1 (false RED at the dissolved tip). `echo unalias -a` is an
        argument; it unaliases nothing, so the later alias still expands."""
        _script(tmp_path, "alias iff='if true; then'\necho unalias -a\n"
                          "iff echo X; fi\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0, execution.stderr
        assert analysis.returncode == 0, analysis.stderr

    def test_argument_position_alias_does_not_define(self, tmp_path):
        """FACE 2 (false GREEN at the dissolved tip). `echo alias iff=...` is
        an argument; it defines nothing, so the later line is a syntax error in
        both surfaces — and bash agrees about the script."""
        _script(tmp_path, "echo alias iff='if true; then'\niff echo X; fi\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        bash = run_bash(["s.sh"], cwd=str(tmp_path))
        assert is_comparable(execution) and is_comparable(analysis)
        assert is_comparable(bash)
        assert execution.returncode == 2 and analysis.returncode == 2
        assert bash.returncode == 2

    #: The alias-axis twin of the option axis's near-miss controls: shapes that
    #: LOOK like alias state changes and are not. psh EXECUTION is the oracle
    #: here — bash defaults expand_aliases off non-interactively, a documented
    #: psh divergence, so the claim is analysis-agrees-with-psh-execution.
    NEAR_MISSES = [
        "alias iff='if true; then'\necho unalias -a\niff echo X; fi\n",
        "alias iff='if true; then'\nprintf '%s' alias\niff echo X; fi\n",
        "alias iff='if true; then'\necho alias zz=1\niff echo X; fi\n",
        "echo alias iff='if true; then'\niff echo X; fi\n",
        "cat <<EOF\nalias iff='if true; then'\nEOF\niff echo X; fi\n",
        "alias iff='if true; then'\naliasx foo 2>/dev/null\niff echo X; fi\n",
    ]

    #: The real thing, in command position — these DO change alias state.
    REAL_CHANGES = [
        "alias iff='if true; then'\niff echo X; fi\n",
        "alias iff='if true; then'\nunalias iff\niff echo X; fi\n",
        "alias iff='if true; then'\ntrue; unalias iff\niff echo X; fi\n",
        "alias iff='if true; then'\nunalias -a\niff echo X; fi\n",
    ]

    @pytest.mark.parametrize("script", NEAR_MISSES + REAL_CHANGES)
    def test_analysis_agrees_with_execution_about_alias_state(self, tmp_path,
                                                              script):
        """One assertion for both lists: whatever psh EXECUTION concludes about
        the alias table, analysis concludes too. Splitting them into expected
        statuses would let a wrong-but-consistent recognizer pass."""
        _script(tmp_path, script)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == analysis.returncode, (
            f"execution rc={execution.returncode} but analysis "
            f"rc={analysis.returncode} for:\n{script}")


class TestQuotedHeadIsNotADirective:
    """R11-A blocker pins. THREE-POINT SHAPE: green at base 42f75591, RED at
    the dissolved tip b254ca52, green here.

    `_normalize_head` stripped backslashes unconditionally, so `'sh\\opt'` —
    a word the shell treats as a command of that literal name — was read as
    `shopt`. The lexer already knows the difference: every LiteralPart carries
    `quoted`/`quote_char`, and a backslash is quoting only in an UNQUOTED part.

    This was the slot's THIRD re-derivation of something the pipeline already
    knew (after a body-blind re-lex and a position-blind re-walk), which is why
    the fix ships with a sanctioned-sites guard —
    tests/unit/scripting/test_analysis_session.py::TestNoUnsanctionedStringSurgery
    — rather than only these two rows.
    """

    def test_quoted_head_does_not_invent_a_disable(self, tmp_path):
        """FALSE-RED face: the invented `expand_aliases` disable made analysis
        stop expanding a live alias, failing a script that runs clean."""
        _script(tmp_path, "alias iff='if true; then'\n"
                          "'sh\\opt' -u expand_aliases\niff echo X; fi\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0, execution.stderr
        assert analysis.returncode == 0, analysis.stderr

    @pytest.mark.parametrize("script", [
        "'sh\\opt' -s extglob\necho @(a|b)\n",
        '"sh\\\\opt" -s extglob\necho @(a|b)\n',
    ])
    def test_quoted_head_does_not_invent_an_enable(self, tmp_path, script):
        """FALSE-GREEN face: the invented extglob enable made analysis accept a
        script BOTH shells reject."""
        _script(tmp_path, script)
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        bash = run_bash(["s.sh"], cwd=str(tmp_path))
        assert is_comparable(execution) and is_comparable(analysis)
        assert is_comparable(bash)
        assert execution.returncode == 2 and bash.returncode == 2
        assert analysis.returncode == 2

    def test_expansion_head_is_a_declared_residual(self, tmp_path):
        """DECLARED DIVERGENCE. A head that is an EXPANSION (`c=shopt; $c -s
        extglob`) has no statically knowable value, so analysis cannot see the
        directive — the same family as the eval/source residual, and for the
        same reason: resolving it would mean executing. Pre-existing (base
        recognized no spelling at all) and newly VISIBLE now that the spelling
        class is named. Asserted in the divergent direction."""
        _script(tmp_path, "c=shopt\n$c -s extglob\necho @(a|b)\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0      # execution resolves $c and applies it
        assert analysis.returncode == 2       # analysis cannot, and says so

    def test_function_shadowed_shopt_is_absorbed_anyway(self, tmp_path):
        """R11-B N12, DECLARED control row. Analysis is not resolution-aware:
        a `shopt` shadowed by a shell FUNCTION is still absorbed as a
        directive, so analysis accepts more than the shell does here. Recorded
        as measured; general resolution-awareness is a successor row."""
        _script(tmp_path, "shopt() { :; }\nshopt -s extglob\necho @(a|b)\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 2      # the function ran; extglob is off
        assert analysis.returncode == 0       # analysis absorbed it anyway


class TestDeclaredAnalysisSideEffects:
    """R11-B N2/N3: two measured consequences of going per-unit, DECLARED.

    Neither changes execution. Both are recorded here rather than left for a
    reader to discover, because "declared + pinned + doc'd" is the standard
    this slot is held to.
    """

    def test_combinator_error_detail_line_is_unit_relative(self, tmp_path):
        """N2. Under `--parser combinator` the DETAIL line inside a parse
        error ("(line N, column C)") is unit-relative, because each unit is
        now parsed on its own. The `psh: file:N:` PREFIX is unaffected.

        This rides the pre-existing ledger row

            2.2 carry: combinator ignores line_offset for TOP-LEVEL statements

        and closing that carry is expected to move both. No parser internals
        were touched by this slot.
        """
        _script(tmp_path, "echo one\necho two\nif\n")
        result = _psh(tmp_path, ["--parser", "combinator", "--validate", "s.sh"])
        assert is_comparable(result)
        assert result.returncode == 2
        assert "(line 1," in result.stderr, result.stderr

    def test_alias_defined_then_used_across_a_heredoc(self, tmp_path):
        """N3. An alias defined before a heredoc still expands after it —
        analysis threads the definition across the unit boundary the heredoc
        creates. Execution is unchanged and is asserted alongside, so the pin
        cannot pass by both surfaces breaking together. Cross-ref: the B100
        alias-heredoc successor row covers bodies collected at expansion time,
        which is a different question.
        """
        _script(tmp_path, "alias iff='if true; then'\ncat <<EOF\nplain body\nEOF\n"
                          "iff echo X; fi\n")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0, execution.stderr
        assert analysis.returncode == 0, analysis.stderr


class TestAliasAxisNormalizationAsymmetry:
    """R11-B N13 / R13-B(3): a DECLARED, base-faithful limitation.

    The OPTION axis normalizes a directive's head through the prefixes that do
    not change which builtin runs. The ALIAS axis does not: absorption runs
    `AliasManager.expand_aliases`, whose command-position walk recognizes the
    bare words `alias`/`unalias` only. So four spellings that DEFINE an alias
    at execution are invisible to analysis.

    Preserved rather than fixed here on purpose. Closing it means widening the
    alias decider's own recognition, which lives in psh/expansion/ —
    STOP-and-report scope for this slot — and building a second, wider
    recognizer beside it is precisely the fault class this slot hit three
    times (R8-A, R9-A, R11-A). Base absorbed nothing at all, so this is
    base-faithful. The successor home is the public AliasManager
    analysis-overlay seam (R5-C / R8-E-9), whose row now names these rows.

    Asserted in the DIVERGENT direction, so closing it fails here loudly.
    """

    USE = "iff echo X; fi\n"

    @pytest.mark.parametrize("definition", [
        "command alias iff='if true; then'",
        "builtin alias iff='if true; then'",
        "x=1 alias iff='if true; then'",
        "\\alias iff='if true; then'",
    ])
    def test_normalized_alias_spellings_are_not_absorbed(self, tmp_path,
                                                         definition):
        _script(tmp_path, f"{definition}\n{self.USE}")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == 0, execution.stderr   # the alias IS defined
        assert analysis.returncode == 2                      # analysis misses it

    def test_the_bare_spelling_is_absorbed(self, tmp_path):
        """The control: without a prefix the two agree, so the rows above pin
        the NORMALIZATION gap and not a broken alias axis."""
        _script(tmp_path, f"alias iff='if true; then'\n{self.USE}")
        execution = _psh(tmp_path, ["s.sh"])
        analysis = _psh(tmp_path, ["--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == analysis.returncode == 0
