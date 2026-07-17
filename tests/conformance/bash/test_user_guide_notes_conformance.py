"""Conformance tests backing user-guide inline notes.

The 2026-06-11 reappraisal (H3) found several user-guide chapters claiming
features were "not supported" when they actually work. The notes were
corrected to document the features as supported; this file pins each of
those corrected claims to bash so the guide cannot rot silently again.

Covered claims (chapter: feature):
- ch10: ``!`` pipeline negation, ``|&``, ``PIPESTATUS``
- ch09: ``>|`` force clobber, ``exec 3<> file`` read-write descriptors
- ch07: bitwise compound assignment operators
- ch05/ch16: ``${!var}`` indirection, ``${!prefix*}`` name matching,
  ``${array[@]#pattern}`` element-wise pattern removal
- ch16: ``${var@K}`` / ``${var@k}`` associative key/value transforms
  (reappraisal #16 H7 — flipped from "Not implemented")
- ch08: ``$"..."`` locale translation quoting
- ch11: ``[[ ! ... ]]`` negation (BASH_REMATCH groups are already covered
  by test_edge_cases.py)
- ch16: ``read -n`` / ``read -t`` / ``read -s`` / ``read -u`` (from an fd)
  (reappraisal #16 H7 flipped the stale ``read -u`` "unsupported" note)
- ch17: ``FUNCNAME`` full nested call stack (reappraisal #17 M1 — flipped
  from the stale "[0] only" row) + the ``main``-frame caveat pin
- ch17/ch04: non-interactive alias expansion (documented difference) and
  the ``shopt -u/-s expand_aliases`` toggle (reappraisal #17 M4)
"""

import os
import subprocess
import sys
import tempfile

from conformance_framework import ConformanceTest
from shell_oracle import resolve_bash


class TestPipelineNotes(ConformanceTest):
    def test_pipeline_negation_of_success(self):
        self.assert_identical_behavior('! true; echo $?')

    def test_pipeline_negation_of_failure(self):
        self.assert_identical_behavior('! false; echo $?')

    def test_pipeline_negation_in_if(self):
        self.assert_identical_behavior('if ! false; then echo ran; fi')

    def test_pipe_both_shorthand(self):
        self.assert_identical_behavior('{ echo out; echo err >&2; } |& sort')

    def test_pipestatus_array(self):
        self.assert_identical_behavior(
            'true | false | true; echo "${PIPESTATUS[@]}"')


class TestRedirectionNotes(ConformanceTest):
    def test_force_clobber_overrides_noclobber(self):
        self.assert_identical_behavior(
            'f=$(mktemp); set -o noclobber; '
            'echo forced >| "$f" && cat "$f"; rm -f "$f"')

    def test_read_write_descriptor(self):
        self.assert_identical_behavior(
            'f=$(mktemp); printf "l1\\nl2\\n" > "$f"; exec 3<> "$f"; '
            'read a <&3; read b <&3; echo "$a/$b"; exec 3>&-; rm -f "$f"')


class TestArithmeticAssignmentNotes(ConformanceTest):
    def test_bitwise_and_assign(self):
        self.assert_identical_behavior('x=12; ((x&=10)); echo $x')

    def test_bitwise_or_assign(self):
        self.assert_identical_behavior('x=12; ((x|=3)); echo $x')

    def test_bitwise_xor_assign(self):
        self.assert_identical_behavior('x=12; ((x^=10)); echo $x')

    def test_shift_left_assign(self):
        self.assert_identical_behavior('x=3; ((x<<=2)); echo $x')

    def test_shift_right_assign(self):
        self.assert_identical_behavior('x=12; ((x>>=2)); echo $x')


class TestParameterExpansionNotes(ConformanceTest):
    def test_indirect_expansion(self):
        self.assert_identical_behavior('foo=bar; bar=baz; echo "${!foo}"')

    def test_variable_name_prefix_matching(self):
        self.assert_identical_behavior(
            'MYV_A=1; MYV_B=2; OTHER=3; echo "${!MYV_*}"')

    def test_array_pattern_removal_suffix(self):
        self.assert_identical_behavior('arr=(a.txt b.txt); echo "${arr[@]%.txt}"')

    def test_array_pattern_removal_prefix(self):
        self.assert_identical_behavior('arr=(x/y/c a/b/z); echo "${arr[@]##*/}"')

    def test_prefix_matching_at_form(self):
        self.assert_identical_behavior(
            'MYV_A=1; MYV_B=2; OTHER=3; echo "${!MYV_@}"')

    def test_prefix_matching_quoted_at_splits(self):
        self.assert_identical_behavior(
            'MYV_A=1; MYV_B=2; for v in "${!MYV_@}"; do echo "w:$v"; done')

    def test_prefix_matching_no_match(self):
        self.assert_identical_behavior(
            'unset ZQ1 ZQ2 2>/dev/null; echo "[${!ZQ_*}]"')


class TestAssocKeyValueTransformNotes(ConformanceTest):
    """``${var@K}`` / ``${var@k}`` — associative key/value transforms.

    Reappraisal #16 H7 flipped the ch17 row from "Not implemented" to "Full
    support". For scalars, indexed arrays, and single-key associative arrays
    the output is byte-identical to bash. For MULTI-key associative arrays the
    key/value PAIRS are identical but iterate in psh's insertion order rather
    than bash's hash order — a pre-existing, documented psh-wide associative
    ordering property, exercised here by comparing the sorted pair sets.
    """

    def test_at_K_scalar(self):
        self.assert_identical_behavior('v=hello; echo "${v@K}"')

    def test_at_k_scalar(self):
        self.assert_identical_behavior('v=hello; echo "${v@k}"')

    def test_at_K_indexed_array(self):
        self.assert_identical_behavior('arr=(x y z); echo "${arr[@]@K}"')

    def test_at_k_indexed_array(self):
        self.assert_identical_behavior('arr=(x y z); echo "${arr[@]@k}"')

    def test_at_K_single_key_assoc(self):
        self.assert_identical_behavior(
            'declare -A m=([solo]=v); echo "${m[@]@K}"')

    def test_at_k_single_key_assoc(self):
        self.assert_identical_behavior(
            'declare -A m=([solo]=v); echo "${m[@]@k}"')

    def test_at_K_multi_key_assoc_same_pairs(self):
        # Multi-key assoc: identical key/value pairs, only iteration order
        # differs (insertion vs hash). Compare the sorted whitespace tokens.
        cmd = 'declare -A m=([a]=1 [b]=2 [c]=3); echo "${m[@]@K}"'
        psh = self.framework.run_in_psh(cmd)
        bash = self.framework.run_in_bash(cmd)
        assert psh.exit_code == bash.exit_code == 0
        assert sorted(psh.stdout.split()) == sorted(bash.stdout.split()), (
            f"@K pairs differ: psh={psh.stdout!r} bash={bash.stdout!r}")


class TestReadFromFdNotes(ConformanceTest):
    """``read -u FD`` reads from a numbered file descriptor.

    Reappraisal #16 H7 flipped the stale ch17 note claiming ``-u`` is the one
    unsupported read option.
    """

    def test_read_u_from_opened_fd(self):
        self.assert_identical_behavior(
            'printf "one\\ntwo\\n" > f; exec 3< f; '
            'read -u 3 a; read -u 3 b; echo "$a-$b"; exec 3<&-')

    def test_read_u_fd0_default(self):
        self.assert_identical_behavior(
            'echo hi | { read -u 0 x; echo "[$x]"; }')

    def test_read_u_raw_mode(self):
        self.assert_identical_behavior(
            'printf "a\\\\b\\n" > f; exec 4< f; read -u 4 -r x; echo "[$x]"; '
            'exec 4<&-')


class TestQuotingNotes(ConformanceTest):
    def test_locale_translation_quoting_literal(self):
        self.assert_identical_behavior('echo $"hello world"')

    def test_locale_translation_quoting_expands(self):
        self.assert_identical_behavior('x=v; echo $"val: $x"')


class TestDoubleBracketNegationNotes(ConformanceTest):
    def test_negated_unary_test(self):
        self.assert_identical_behavior(
            '[[ ! -f /nonexistent_psh_conformance ]] && echo ok')

    def test_negated_condition_with_and(self):
        self.assert_identical_behavior('[[ ! -z x && -n x ]] && echo ok')


class TestReadOptionNotes(ConformanceTest):
    def test_read_n_char_count(self):
        self.assert_identical_behavior('echo abcdef | { read -n 3 v; echo "$v"; }')

    def test_read_t_timeout(self):
        self.assert_identical_behavior('echo hi | { read -t 5 v; echo "$v"; }')

    def test_read_s_silent(self):
        self.assert_identical_behavior('echo secret | { read -s v; echo "$v"; }')


class TestFuncnameNotes(ConformanceTest):
    """ch17: FUNCNAME populates the full nested-function call stack.

    Reappraisal #17 M1 — the compatibility-table row claimed "[0] only;
    full call stack not populated" long after psh populated the whole
    stack. The row was flipped to "Full support"; these tests prove it
    (and pin the one honest caveat: bash's ``main``/``source`` base
    frames, which belong to the unimplemented BASH_SOURCE/BASH_LINENO
    cluster, are not appended).
    """

    def test_funcname_full_call_stack(self):
        self.assert_identical_behavior(
            'a(){ b;}; b(){ c;}; c(){ echo "${FUNCNAME[@]}";}; a')

    def test_funcname_indexed_frames_and_length(self):
        self.assert_identical_behavior(
            'a(){ b;}; b(){ c;}; c(){ echo "${FUNCNAME[0]}|${FUNCNAME[1]}|'
            '${FUNCNAME[2]}|${#FUNCNAME[@]}";}; a')

    def test_funcname_unset_outside_functions(self):
        self.assert_identical_behavior('echo "outside=[${FUNCNAME[@]:-unset}]"')

    def test_funcname_star_join(self):
        self.assert_identical_behavior('a(){ b;}; b(){ echo "${FUNCNAME[*]}";}; a')

    def test_funcname_script_base_frames_differ(self):
        """Caveat pin: in a script FILE bash appends a ``main`` base frame.

        psh's function frames are identical, but the bash-only ``main``
        (and ``source``) frames arrive with the BASH_SOURCE/BASH_LINENO
        work — this pin fails when that lands, forcing the ch17 caveat to
        be retired.
        """
        script = 'a(){ b;}; b(){ c;}; c(){ echo "${FUNCNAME[@]}";}; a\n'
        with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as f:
            f.write(script)
            path = f.name
        try:
            root = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '..', '..', '..'))
            psh = subprocess.run([sys.executable, '-m', 'psh', path],
                                 capture_output=True, text=True,
                                 cwd=root, timeout=15)
            bash = subprocess.run([resolve_bash().path, path], capture_output=True,
                                  text=True, timeout=15)
            assert psh.stdout == 'c b a\n', psh.stdout
            assert bash.stdout == 'c b a main\n', bash.stdout
        finally:
            os.unlink(path)


class TestAliasExpansionNotes(ConformanceTest):
    """ch17 (17.3) / ch04: alias expansion in non-interactive shells.

    psh deliberately keeps ``expand_aliases`` ON in every mode where bash
    defaults it OFF non-interactively (documented difference, reappraisal
    #17 M4). The ``shopt`` toggle itself must then behave exactly like
    bash's: ``shopt -u expand_aliases`` disables expansion for
    subsequently-parsed commands and ``shopt -s`` re-enables it.
    """

    def test_alias_expands_noninteractively_documented_difference(self):
        self.assert_documented_difference(
            'alias ll="echo ALIAS_EXPANDED"; ll',
            'ALIAS_EXPANSION_NONINTERACTIVE')

    def test_same_line_alias_definition_is_psh_extension(self):
        # bash never expands an alias used on the line that defines it.
        self.assert_psh_extension('alias hi="echo hello"; hi')

    def test_shopt_u_expand_aliases_disables(self):
        self.assert_identical_behavior(
            'shopt -u expand_aliases\nalias ll="echo X"\n'
            'll 2>/dev/null; echo rc=$?')

    def test_shopt_s_expand_aliases_reenables(self):
        self.assert_identical_behavior(
            'shopt -u expand_aliases\nalias ll="echo X"\nll 2>/dev/null\n'
            'shopt -s expand_aliases\nll')
