"""Drift-lock for the analysis-visitor advisories (reappraisal #19 T10).

The analysis visitors (validator, enhanced validator, linter, security, metrics)
are teaching artifacts that emit *advisories* about a script. Historically several
advisories were plain wrong — they fired on idiomatic code (false positives) or
never fired on the pattern they claimed to catch. T10 fixed seven of them and
consolidated four twin code paths. This file is the guard that keeps the sidecar
honest:

(a) A **clean-corpus ratchet**: a curated corpus of genuinely idiomatic shell
    snippets (harvested from ``tests/behavioral/golden_cases.yaml`` inputs plus a
    few hand-written idioms) is run through every advisory mode and must produce
    ZERO advisories. If any fixed false positive regresses — or a new one appears
    — a corpus entry lights up and this test fails.

(b) One **positive case per fixed advisory**: the advisory still fires on the real
    pattern (so the fixes narrowed the checks, they did not delete them), paired
    with the negative case (the idiomatic shape that used to false-positive).

One documented allowlist entry: the linter's content-independent "no explicit
error handling" reminder fires once on any script lacking ``set -e``. It is a
deliberate style nudge, not a construct-specific false positive, so the ratchet
filters it (the A3 cluster-detection fix is pinned separately below). Everything
else — every warning/error and every construct-specific advisory — must be absent
from the corpus.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import (
    EnhancedValidatorVisitor,
    LinterVisitor,
    MetricsVisitor,
    SecurityVisitor,
)
from psh.visitor.constants import PREDEFINED_VARIABLES, is_assignment

# The one content-independent style nudge the ratchet tolerates (see module docstring).
_ERROR_HANDLING_NUDGE = "Script has no explicit error handling"


def _ast(src):
    return parse(tokenize(src))


def _issue_messages(visitor_cls, src):
    v = visitor_cls()
    v.visit(_ast(src))
    return [getattr(i, "message", str(i)) for i in v.issues]


def _advisories(src):
    """All advisory messages a script produces across validate/lint/security,
    minus the tolerated error-handling nudge. Metrics has no advisory channel."""
    out = []
    for cls in (EnhancedValidatorVisitor, LinterVisitor, SecurityVisitor):
        out.extend(
            m for m in _issue_messages(cls, src) if _ERROR_HANDLING_NUDGE not in m
        )
    return out


def _validate_messages(src):
    return _issue_messages(EnhancedValidatorVisitor, src)


def _lint_messages(src):
    return _issue_messages(LinterVisitor, src)


def _security_types(src):
    v = SecurityVisitor()
    v.visit(_ast(src))
    return {i.issue_type for i in v.issues}


def _metrics(src):
    v = MetricsVisitor()
    v.visit(_ast(src))
    return v.metrics


# ---------------------------------------------------------------------------
# (a) Clean-corpus ratchet
# ---------------------------------------------------------------------------

# Idiomatic, advisory-clean shell. Most are verbatim golden_cases.yaml inputs
# (harvested by running every single-line golden through the advisory filter);
# the rest are hand-written idioms. The final three are the exact shapes that
# used to false-positive (bare `cat file`, `cd` with an option flag, a plain `>`
# redirect) — kept here so the ratchet directly locks those fixes.
CLEAN_CORPUS = [
    # quoting / expansion (golden-derived)
    "echo 'hello world'",
    'var=hello; echo "$var"',
    'var=world; echo "hello $var"',
    'var=hello; echo "${var}world"',
    'a=x; b=y; echo "$a-$b"',
    'echo "$HOME"',
    'echo "${IFS+set}"',
    'echo "*"',
    'echo "result: $(echo 42)"',
    'set -- a b c; printf "[%s]\\n" "$@"',
    'x=; echo "[$x]"',
    # arithmetic (A5 negative surface: plain variable arithmetic is safe)
    'echo $((1 + 2))',
    'echo $(( (2 + 3) * 4 ))',
    # pipelines / and-or / control flow
    'echo hello | cat',
    'true && echo yes',
    'false || echo fallback',
    'if true; then echo yes; else echo no; fi',
    # idiomatic additions
    'set -euo pipefail',
    'greet() { echo "hi $1"; }; greet there',
    'func() { local v="$1"; echo "$v"; }; func x',
    'if [[ -f "$file" ]]; then echo yes; fi',
    'if [[ -n "$USER" ]]; then echo "$USER"; fi',
    'case "$1" in a) echo one ;; *) echo other ;; esac',
    'readonly CONST="value"; echo "$CONST"',
    'declare -a arr=(1 2 3); echo "${arr[@]}"',
    'echo "$@"',
    'ls -l',
    'grep pattern file.txt',
    # was-a-false-positive, now clean (locks A1 useless-cat, A6 cd-arity, noclobber rider)
    'cat file.txt',
    'cd -P /tmp',
    'cd -',
    'echo hi > out.txt',
]


@pytest.mark.parametrize("src", CLEAN_CORPUS)
def test_clean_corpus_has_no_advisories(src):
    """Idiomatic scripts produce zero advisories across validate/lint/security."""
    advisories = _advisories(src)
    assert advisories == [], f"{src!r} produced advisories: {advisories}"


@pytest.mark.parametrize("src", CLEAN_CORPUS)
def test_clean_corpus_metrics_do_not_crash(src):
    """The metrics mode (no advisory channel) runs cleanly on the corpus."""
    v = MetricsVisitor()
    v.visit(_ast(src))
    assert isinstance(v.get_summary(), str)


# ---------------------------------------------------------------------------
# (b) One positive + negative case per fixed advisory
# ---------------------------------------------------------------------------

class TestAdvisoryPositiveAndNegative:
    # A1 — useless-use-of-cat is owned by the linter (real pipeline), and the
    # validator's misfiring copy is gone.
    def test_a1_useless_cat_positive_linter(self):
        assert any("Useless use of cat" in m for m in _lint_messages("cat f | grep x"))

    def test_a1_useless_cat_negative_validator(self):
        assert not any(
            "Useless use of cat" in m for m in _validate_messages("cat file.txt")
        )

    def test_a1_validator_direct_visit_does_not_crash(self):
        # The dead `_in_pipeline` default used to raise TypeError on a direct
        # SimpleCommand visit.
        from psh.visitor.validator_visitor import ValidatorVisitor
        ast = _ast("cat file.txt")
        sc = ast.statements[0].pipelines[0].commands[0]
        v = ValidatorVisitor()
        v.visit_SimpleCommand(sc)  # must not raise

    # A2 — a bare assignment is not an undefined function call.
    def test_a2_bare_assignment_negative(self):
        assert not any(
            "called but not defined" in m for m in _lint_messages("FOO=bar")
        )

    def test_a2_real_undefined_function_positive(self):
        assert any(
            "Function 'myfunc' is called but not defined" in m
            for m in _lint_messages("myfunc arg")
        )

    # A3 — `set -eu` (clustered flags) counts as error handling.
    def test_a3_clustered_flags_negative(self):
        assert not any(
            _ERROR_HANDLING_NUDGE in m for m in _lint_messages("set -eu\necho hi")
        )
        assert not any(
            _ERROR_HANDLING_NUDGE in m
            for m in _lint_messages("set -euo pipefail\necho hi")
        )

    def test_a3_no_flags_still_nags_positive(self):
        assert any(_ERROR_HANDLING_NUDGE in m for m in _lint_messages("echo hi"))

    # A4 — quoted `"$@"` is not flagged; embedded unquoted `$@` is.
    def test_a4_quoted_at_in_assignment_negative(self):
        assert not any('Unquoted $@' in m for m in _validate_messages('FOO="$@"'))

    def test_a4_unquoted_at_positive(self):
        assert any('Unquoted $@' in m for m in _validate_messages('echo pre$@'))

    # A5 — arithmetic injection fires only on injectable shapes.
    def test_a5_plain_arithmetic_negative(self):
        assert "ARITHMETIC_INJECTION" not in _security_types("(( i = i + 1 ))")

    def test_a5_command_substitution_positive(self):
        assert "ARITHMETIC_INJECTION" in _security_types("(( y = $(whoami) ))")

    def test_a5_braced_subscript_positive(self):
        assert "ARITHMETIC_INJECTION" in _security_types("(( z = ${arr[$i]} ))")

    # A6 — cd-arity counts non-option operands.
    def test_a6_option_flag_negative(self):
        assert not any(
            "too many arguments" in m for m in _validate_messages("cd -P /tmp")
        )

    def test_a6_two_operands_positive(self):
        assert any(
            "cd: too many arguments" in m for m in _validate_messages("cd a b")
        )

    def test_a6_bare_dash_is_an_operand(self):
        """`-` means "cd to $OLDPWD" — an OPERAND, not an option flag.

        `cd - extra` is therefore two operands and must warn (integrator
        ruling, T10 bounce fold-in; red on the pre-fold-in tip c8fdbca3 where
        the startswith('-') filter swallowed the bare `-`), while a lone
        `cd -` stays clean.
        """
        assert any(
            "cd: too many arguments" in m for m in _validate_messages("cd - extra")
        )
        assert not any(
            "too many arguments" in m for m in _validate_messages("cd -")
        )

    # A7 — process substitutions are counted (were always 0).
    def test_a7_process_substitution_counted(self):
        m = _metrics("diff <(echo a) <(echo b)")
        assert m.process_substitutions == 2

    def test_a7_command_substitution_not_counted_as_procsub(self):
        m = _metrics('echo "$(date)"')
        assert m.process_substitutions == 0
        assert m.command_substitutions == 1


# ---------------------------------------------------------------------------
# Twin-consolidation guards
# ---------------------------------------------------------------------------

class TestTwinConsolidation:
    def test_predefined_variables_agree_across_validate_and_lint(self):
        # HOSTNAME is a predefined variable: neither mode may flag it undefined.
        src = 'echo "$HOSTNAME"'
        assert not any("undefined" in m for m in _validate_messages(src))
        assert not any("may be undefined" in m for m in _lint_messages(src))

    def test_predefined_variables_is_the_single_source(self):
        from psh.visitor.enhanced_validator_visitor import VariableTracker
        assert VariableTracker().special_vars is PREDEFINED_VARIABLES

    def test_is_assignment_single_predicate(self):
        assert is_assignment("FOO=bar")
        assert is_assignment("a_b=c")
        assert is_assignment("_x=1")
        # A hyphen is not a valid variable-name char (the old enhanced-validator
        # predicate accepted it and defined variable `a-b`).
        assert not is_assignment("a-b=c")
        assert not is_assignment("=x")
        assert not is_assignment("echo")
        assert not is_assignment("FOO+=x")  # append form deliberately excluded

    # --- discriminating pins for the hyphen-rejecting convergence -----------
    # The three tests below each go RED under the verifier's mutation (a
    # hyphen-accepting is_assignment, i.e. the old enhanced-validator
    # `.replace('-','')...isalnum()` predicate restored): under that mutation
    # `a-b=c` is (wrongly) treated as defining variable `a-b`. The generic
    # "$a stays undefined after a-b=c" shape does NOT discriminate (it passes
    # on base too, which defined `a-b`, not `a`) — these pin the observable
    # differences directly.

    def test_hyphen_word_records_no_metrics_variable(self):
        """--metrics on `a-b=c` records ZERO variables.

        Kill-mutation: a hyphen-accepting is_assignment makes MetricsVisitor
        add 'a-b' to variable_names (Variables Used 0 -> 1)."""
        m = _metrics("a-b=c")
        assert m.variable_names == set()

    def test_hyphen_word_not_defined_in_variable_tracker(self):
        """The enhanced validator's VariableTracker does not define 'a-b'.

        Kill-mutation: a hyphen-accepting is_assignment makes
        _process_variable_assignments record VariableInfo(name='a-b')."""
        v = EnhancedValidatorVisitor()
        v.visit(_ast("a-b=c"))
        assert not v.var_tracker.is_defined("a-b")

    def test_hyphen_word_value_text_not_scanned(self):
        """--validate is SILENT about `$q` inside the word `a-b=$q`.

        Integrator ruling (T10 bounce): `a-b=c` is not an assignment — it is a
        command WORD — so analysis stays silent about its text (the =-suffix is
        not an assignment value to be scanned for undefined variables).

        Kill-mutation: a hyphen-accepting is_assignment routes the `$q` suffix
        through _check_string_for_undefined_vars, emitting
        "Possible use of undefined variable '$q'" (the base behavior)."""
        msgs = _validate_messages("a-b=$q")
        assert not any("undefined variable '$q'" in m for m in msgs), msgs

    def test_dangerous_command_tables_single_sourced(self):
        # Security uses DANGEROUS_COMMANDS; the linter uses its own caution table.
        # Both live in constants.py side by side (no cross-file duplication).
        from psh.visitor import constants
        assert "eval" in constants.DANGEROUS_COMMANDS
        assert "eval" in constants.LINTER_CAUTION_COMMANDS
        # The two are deliberately different (rm is caution-only; source/. are
        # code-execution only).
        assert "rm" in constants.LINTER_CAUTION_COMMANDS
        assert "rm" not in constants.DANGEROUS_COMMANDS
        assert "source" in constants.DANGEROUS_COMMANDS
        assert "source" not in constants.LINTER_CAUTION_COMMANDS

    def test_unquoted_test_operand_routine_shared(self):
        # Both the linter and the enhanced validator flag an unquoted operand in
        # a test comparison via the one shared routine.
        src = "x=1; [ $x = y ]"
        assert any("in test" in m for m in _lint_messages(src))
        assert any("in test" in m for m in _validate_messages(src))

    # --- the union operator set's NEW firings (positive, red-on-base) -------
    # unquoted_test_operands unions the two old walks' coverage: the linter
    # gains left-of-binary operands and the -z/-n/-L/-h unary forms; the
    # enhanced validator gains the numeric comparisons. These pin the union in
    # BOTH modes; each goes red under a mutation reverting the routine to
    # either old walk (left-neighbor-only union set, or the old
    # file+string-only validator sets).

    def test_numeric_comparison_left_operand_fires_both_modes(self):
        """`[ $x -eq 5 ]`: $x is the LEFT operand of a numeric comparison.

        Red-on-base in BOTH modes: the old linter walk checked only the
        left NEIGHBOR (nothing precedes $x), and the old validator walk had
        no numeric operators at all."""
        src = "x=1; [ $x -eq 5 ]"
        assert any(
            "Unquoted variable '$x' in test command" in m
            for m in _lint_messages(src)
        )
        assert any(
            "Unquoted variable '$x' in test" in m
            for m in _validate_messages(src)
        )

    def test_z_unary_operand_fires_both_modes(self):
        """`[ -z $x ]`: unquoted operand of the -z unary string test.

        Red-on-base in BOTH modes: -z was in neither old operator set."""
        src = "x=1; [ -z $x ]"
        assert any(
            "Unquoted variable '$x' in test command" in m
            for m in _lint_messages(src)
        )
        assert any(
            "Unquoted variable '$x' in test" in m
            for m in _validate_messages(src)
        )

    def test_quoted_test_operands_clean_both_modes(self):
        # The quoted forms of both new firings stay clean (negative control).
        for src in ('x=1; [ "$x" -eq 5 ]', 'x=1; [ -z "$x" ]'):
            assert not any("in test" in m for m in _lint_messages(src)), src
            assert not any("in test" in m for m in _validate_messages(src)), src


# ---------------------------------------------------------------------------
# Rider
# ---------------------------------------------------------------------------

class TestNoclobberRiderDropped:
    def test_plain_redirect_no_noclobber_advisory(self):
        msgs = _validate_messages("echo hi > out.txt")
        assert not any("overwrite" in m or "append" in m for m in msgs)
