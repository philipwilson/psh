"""
Array initializer expansion conformance tests.

Pins the headline fixes from the 2026-06-11 code quality assessment
(Concrete Correctness Risk #1): array initializers ``a=(...)`` must use
the same quote-aware expansion pipeline as command arguments — quoted
glob patterns stay literal, unquoted expansions split on $IFS, and
``set -f`` suppresses globbing.
"""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


def _show(name='a'):
    """Value-based array dump (NOT ``declare -p``): index/key + value per
    line, so assertions pin VALUES not the ``declare -p`` formatting (assoc
    key ordering / trailing space differ from bash by design)."""
    return (f'for k in "${{!{name}[@]}}"; do '
            f'echo "[$k]=${{{name}[$k]}}"; done; echo "len=${{#{name}[@]}}"')


class TestArrayInitializerExpansion(ConformanceTest):
    """Array initialization expansion semantics."""

    def test_quoted_glob_stays_literal(self):
        """A quoted glob pattern in an initializer is not expanded."""
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch p1.txt p2.txt; '
            'a=("*.txt" *.txt); echo ${#a[@]} "${a[0]}" "${a[1]}" "${a[2]}"; '
            'cd /; rm -rf "$d"')

    def test_ifs_splitting_in_initializer(self):
        """Unquoted expansions in initializers split on $IFS."""
        self.assert_identical_behavior(
            'x="a:b:c"; IFS=:; a=($x); echo ${#a[@]} "${a[1]}"')

    def test_noglob_suppresses_initializer_globbing(self):
        """set -f keeps glob patterns literal inside initializers."""
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch p1.txt; '
            'set -f; a=(*.txt); echo ${#a[@]} "${a[0]}"; '
            'set +f; cd /; rm -rf "$d"')

    def test_quoted_array_splice_preserves_elements(self):
        """b=("${a[@]}") preserves elements; b=(${a[@]}) resplits."""
        self.assert_identical_behavior(
            'a=("x y" z); b=("${a[@]}"); c=(${a[@]}); '
            'echo ${#b[@]} ${#c[@]} "${b[0]}"')

    def test_scalar_element_assignment_no_glob_no_split(self):
        """a[0]=* stays literal: scalar assignment context, not a list."""
        self.assert_identical_behavior(
            'x="1 2"; a[0]=*; a[1]=$x; echo "${a[0]}" "${a[1]}" ${#a[@]}')

    def test_quoted_bracket_element_is_literal(self):
        """a=("[0]"=x): quoting the brackets makes a literal element, not an
        explicit-index assignment (fallback audit 2026-06-12 — the deleted
        legacy string re-parser wrongly assigned a[0]=x here)."""
        self.assert_identical_behavior(
            'a=("[0]"=x); echo ${#a[@]} "${a[0]}"')

    def test_fully_quoted_bracket_element_is_literal(self):
        """a=("[0]=x") is one literal element."""
        self.assert_identical_behavior(
            'a=("[0]=x"); echo ${#a[@]} "${a[0]}"')

    def test_unquoted_explicit_index_assignment(self):
        """a=([1]=x [3]=y z): unquoted explicit indices assign sparsely."""
        self.assert_identical_behavior(
            'a=([1]=x [3]=y z); echo ${#a[@]} "${a[1]}" "${a[3]}" "${a[4]}" '
            '"${!a[@]}"')


class TestInitializerValueTilde(ConformanceTest):
    """Tilde expansion inside initializer elements (bash 5.2, probed
    2026-06-13 — Tier B10a flipped the assoc-init value-tilde accident).

    The rule: assignment-shaped VALUE tilde (after a literal ``=`` in
    the element) does NOT expand in either array-initializer flavor,
    while a LEADING tilde and the value of an explicit ``[k]=`` element
    DO expand.
    """

    def test_assoc_bare_element_value_tilde_stays_literal(self):
        """declare -A h; h=(P=~/x v): the element is the literal KEY
        'P=~/x' — psh expanded the tilde until v0.326 (the pinned
        historical accident, now fixed)."""
        self.assert_identical_behavior(
            'declare -A h; h=(P=~/x v); echo "${!h[@]}"')

    def test_assoc_bare_element_colon_tilde_stays_literal(self):
        self.assert_identical_behavior(
            'declare -A h; h=(P=a:~:b v); echo "${!h[@]}"')

    def test_assoc_leading_tilde_still_expands(self):
        """A BARE leading tilde in key or value position expands.

        NOT assert_identical_behavior: bash point releases disagree in
        this corner — 5.2.26 (dev machine) expands a bare tilde in
        assoc pair-form key/value positions, 5.2.21 (Ubuntu CI runner)
        keeps it literal. psh follows the 5.2.26 behavior; this test
        pins psh's output directly so it holds on either bash.
        """
        import os
        home = os.path.expanduser('~')
        result = self.framework.run_in_psh('declare -A h; h=(~ v); echo "${!h[@]}"')
        assert result.stdout.strip() == home
        result = self.framework.run_in_psh('declare -A h; h=(k ~/x); echo "${h[k]}"')
        assert result.stdout.strip() == f"{home}/x"

    def test_assoc_explicit_subscript_value_tilde_expands(self):
        """[k]=~/x goes through scalar assignment-value semantics.

        psh-only pin: same bash 5.2.21-vs-5.2.26 divergence as
        test_assoc_leading_tilde_still_expands (see its docstring).
        """
        import os
        home = os.path.expanduser('~')
        result = self.framework.run_in_psh('declare -A h; h=([k]=~/x); echo "${h[k]}"')
        assert result.stdout.strip() == f"{home}/x"

    def test_indexed_element_value_tilde_stays_literal(self):
        """The indexed-array twin: a=(P=~/x) keeps the tilde literal."""
        self.assert_identical_behavior('a=(P=~/x); echo "${a[0]}"')

    def test_indexed_explicit_subscript_value_tilde_expands(self):
        self.assert_identical_behavior('a=([0]=~/x); echo "${a[0]}"')


class TestAssocInitFieldExpansions(ConformanceTest):
    """Field expansions ("$@", "${a[@]}") inside assoc bare initializers
    join into ONE word with single spaces — bash 5.2, probed 2026-06-13
    (Tier B10a; psh used to split/glob them via a pre-policy path).
    """

    def test_unquoted_at_joins_to_single_key(self):
        self.assert_identical_behavior(
            'set -- "a b" c; declare -A h; h=($@); '
            'echo "len=${#h[@]} keys=${!h[@]}"')

    def test_quoted_at_joins_to_single_key(self):
        self.assert_identical_behavior(
            'set -- "a b" c; declare -A h; h=("$@"); '
            'echo "len=${#h[@]} keys=${!h[@]}"')

    def test_array_splice_joins_to_single_key(self):
        self.assert_identical_behavior(
            'a=("x y" z); declare -A h; h=(${a[@]}); '
            'echo "len=${#h[@]} keys=${!h[@]}"')
        self.assert_identical_behavior(
            'a=("x y" z); declare -A h; h=("${a[@]}"); '
            'echo "len=${#h[@]} keys=${!h[@]}"')

    def test_affixed_at_joins_within_the_word(self):
        self.assert_identical_behavior(
            'set -- x y; declare -A h; h=(pre"$@"post v); echo "${!h[@]}"')

    def test_join_uses_spaces_not_ifs(self):
        self.assert_identical_behavior(
            'set -- x y; IFS=:; declare -A h; h=($@ v); echo "${!h[@]}"')

    def test_glob_parameter_stays_literal(self):
        self.assert_identical_behavior(
            'set -- "*" c; declare -A h; h=($@); echo "${!h[@]}"')

    def test_declare_scalar_value_at_joins(self):
        """Same engine path: declare v="$@" joins with spaces (psh used
        to keep only the first field)."""
        self.assert_identical_behavior(
            'set -- a b; declare v="$@"; echo "[$v]"')


class TestDeclarationBuiltinArrayInit(ConformanceTest):
    """Declaration builtins (declare/typeset/local/export/readonly) route
    ``name=(...)`` through the SAME structured expansion as the bare
    ``a=(...)`` path (one engine; the serialize-then-shlex-reparse is gone).

    These cases all MISMATCHED bash before the unification (Ugly 6 fix); a
    value-based dump pins the bash-correct result and excludes the
    pre-existing ``declare -p`` display-format differences (assoc key
    ordering, trailing space) and the pre-existing ``-i`` integer-array
    arithmetic gap, which are out of this refactor's scope.
    """

    def test_declare_adjacent_quoted_joins(self):
        """declare -a a=("x""y") joins to one element (was [x][y]; shlex
        lost adjacent-quote joining)."""
        self.assert_identical_behavior(
            'declare -a a=("x""y"); ' + _show())

    def test_declare_indexed_append(self):
        """declare -a a+=(...) appends (the += arg form did not parse before
        — '2: command not found')."""
        self.assert_identical_behavior(
            'declare -a a=(1); declare -a a+=(2 3); ' + _show())

    def test_declare_assoc_append(self):
        self.assert_identical_behavior(
            'declare -A m=([k]=v); declare -A m+=([j]=w); ' + _show('m'))

    def test_declare_assoc_bare_keys(self):
        """declare -A m=(k1 v1 k2 v2): alternating bare key/value pairs (the
        string-reparse produced an empty array)."""
        self.assert_identical_behavior(
            'declare -A m=(k1 v1 k2 v2); ' + _show('m'))

    def test_declare_explicit_indices(self):
        """declare -a a=([2]=x [0]=y): explicit indices (were literals)."""
        self.assert_identical_behavior(
            'declare -a a=([2]=x [0]=y); ' + _show())

    def test_declare_tilde_element(self):
        self.assert_identical_behavior(
            'declare -a a=(~/foo); echo "${a[0]}"')

    def test_declare_command_substitution_element(self):
        """declare -a a=($(echo p q)): cmdsub splits (was mangled)."""
        self.assert_identical_behavior(
            'declare -a a=($(echo p q)); ' + _show())

    def test_export_creates_array(self):
        """export e=(a b) makes an indexed array (psh stored a scalar string
        '(a b)' before)."""
        self.assert_identical_behavior(
            'export e=(a b); ' + _show('e'))

    def test_readonly_array(self):
        self.assert_identical_behavior(
            'readonly r=(x y); ' + _show('r'))

    def test_local_array_in_function(self):
        self.assert_identical_behavior(
            'f() { local a=(1 2); ' + _show() + '; }; f')

    def test_local_assoc_in_function(self):
        self.assert_identical_behavior(
            'f() { local -A m=([k]=v [j]="x y"); ' + _show('m') + '; }; f')

    def test_local_indexed_append_in_function(self):
        self.assert_identical_behavior(
            'f() { local a=(1); local a+=(2 3); ' + _show() + '; }; f')

    def test_declare_x_array_not_exported(self):
        """declare -x a=(1 2): an array gets the export attr but is never
        written to the environment (no child sees it)."""
        self.assert_identical_behavior(
            'declare -x a=(1 2); ' + _show() + '; printenv a; echo "rc=$?"')

    def test_quoted_paren_value_is_scalar(self):
        """declare "a=(1 2)": the quoted parens are literal — bash keeps a
        SCALAR (psh wrongly array-ified via the now-deleted string path)."""
        self.assert_identical_behavior(
            'declare "a=(1 2)"; echo "[${a}]"')

    def test_dynamic_paren_value_is_scalar(self):
        """declare a=$x with x='(1 2)': a scalar in bash (not array syntax)."""
        self.assert_identical_behavior(
            "x='(1 2)'; declare a=$x; echo \"[${a}]\"")

    def test_eval_declare_array_flows_through_structured_path(self):
        """eval re-parses, so the parser builds the structured init."""
        self.assert_identical_behavior(
            'eval "declare -a a=(1 2 3)"; ' + _show())

    def test_typeset_array(self):
        """typeset is declare (ksh alias) — same structured path."""
        self.assert_identical_behavior(
            'typeset -a a=("x""y" z); ' + _show())
