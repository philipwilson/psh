"""Analysis modes see the state the script establishes (remediation 2.6).

MEDIUM-9(a): analysis parsed the whole input under the option state the shell
was CONSTRUCTED with, while execution parses unit by unit under state that
evolves — so `shopt -s extglob` on line 1 plus `+(...)` on line 2 EXECUTED
(rc 0) and FAILED `--validate` (rc 2, syntax error). The analysis session
(`psh/scripting/analysis_session.py`) walks execution's own unit boundaries and
threads parse-relevant state between units without executing anything.

RED-ON-BASE: every row in `test_state_aware_signature` is rc 2 at 42f75591 and
rc != 2 here, on all three channels and both parsers, for all five modes.

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
        cwd = _script(tmp_path, EXTGLOB_SCRIPT)
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
        assert cwd  # the script file was the input for the file channel

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

        Under `--parser combinator` that place is line 1 rather than line 3 —
        the parser never stamps top-level statement lines, a PRE-EXISTING
        defect (LEDGER Part D, "2.2 carry: combinator ignores line_offset for
        TOP-LEVEL statements", owned by the parser successor). Analysis does
        not inherit it from this slot; it CONVERGES on execution, which has
        always reported that line. Pinning the two together means closing the
        carry moves both surfaces at once, or fails here.
        """
        _script(tmp_path, self.SCRIPT)
        execution = _psh(tmp_path, ["--parser", parser, "s.sh"])
        analysis = _psh(tmp_path, ["--parser", parser, "--validate", "s.sh"])
        assert is_comparable(execution) and is_comparable(analysis)
        assert execution.returncode == analysis.returncode == 2
        prefix = [line for line in execution.stderr.splitlines()
                  if line.startswith("psh: s.sh:")][0].split(" Parse error")[0]
        assert prefix in analysis.stderr, (prefix, analysis.stderr)


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
        assert "var: file" in result.stdout or result.returncode == 0
        assert "var: F" not in result.stdout, result.stdout

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

    def test_repeating_one_mode_is_fine(self, tmp_path):
        _script(tmp_path, PLAIN_SCRIPT)
        once = _psh(tmp_path, ["--lint", "s.sh"])
        twice = _psh(tmp_path, ["--lint", "--lint", "s.sh"])
        assert is_comparable(once) and is_comparable(twice)
        assert (once.returncode, once.stdout) == (twice.returncode, twice.stdout)
