"""Array-subscript keying conformance (campaign W2 / reappraisal #21 A-family).

One feature — interpreting an array subscript — was implemented six
inconsistent ways across six modules (r21's signature finding). W2 replaced
them with one authority (``psh/expansion/subscript.py``): target kind FIRST
(the DECLARED variable decides indexed-vs-associative; an undeclared name is
indexed), then ONE interpretation per kind — associative keys get one
word/quote expansion under assignment-value semantics (no split, no glob, no
bare-name dereference), indexed subscripts expand then lazily
arithmetic-evaluate.

Every parity row here was probed against bash 5.2 at base d4db9c57 (see
tmp/boundary-ledgers/W2-probes/matrix_base.txt): the A/Q/K rows were DIVERGENT
at base and are red-on-base pins; the I/S/V/R rows matched at base and are
parity pins. Documented divergences live at the bottom as explicit both-sides
tests (house style of test_nested_substitution_timing_conformance.py).
"""
import re
from pathlib import Path

import pytest
from conformance_framework import ConformanceTest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

PSH_ROOT = Path(__file__).resolve().parents[3]


def _oracle_version_tuple():
    """The oracle bash's ``(major, minor, patch)``, or None if unparseable."""
    m = re.match(r'(\d+)\.(\d+)\.(\d+)', resolve_bash().version)
    return tuple(int(g) for g in m.groups()) if m else None


# bash 5.2 PATCH 24 began expanding a tilde inside an associative-array
# subscript: `HOME=/probe-home; declare -A a; a[~]=v; echo "${!a[@]}"` prints
# the literal `~` up to 5.2.23 and `/probe-home` from 5.2.24 on. Bisected by
# building each patch level from the GNU tarball + official patches on ONE
# Linux box, so the flip is the bash VERSION and not the platform:
#     5.2.22 -> ~     5.2.23 -> ~     5.2.24 -> /probe-home    5.2.25 -> /probe-home
# psh implements the current (>=5.2.24) behaviour. The Linux nightly's distro
# bash is 5.2.21, where the oracle itself predates the change -- so the row is
# skipped there rather than being "widened" to accept both answers, which would
# stop it proving anything on the hosts that CAN check it.
#
# The gate FAILS CLOSED. A full version-tuple compare means an older series
# (5.1, say) also skips instead of failing on a difference it cannot be
# expected to show, and an UNPARSEABLE version skips too rather than running the
# row against an oracle whose behaviour here is unknown. Earlier this compared
# the patch field only when the version happened to be a 5.2, so anything else
# fell through and ran.
_TILDE_IN_SUBSCRIPT_VERSION = (5, 2, 24)
_ORACLE_VERSION = _oracle_version_tuple()
_OLD_BASH_NO_SUBSCRIPT_TILDE = (
    _ORACLE_VERSION is None or _ORACLE_VERSION < _TILDE_IN_SUBSCRIPT_VERSION)

# Shell-name diagnostic prefix (`psh: line 1: ` / `bash: line 1: `): stripped
# where a row compares MESSAGE BODIES (the framework compares raw stderr, and
# the argv0 prefix legitimately differs between the shells).
_PREFIX_RE = re.compile(r'^[^:\n]*: (line \d+: )?', re.MULTILINE)


def _strip_prefix(stderr: str) -> str:
    return _PREFIX_RE.sub('', stderr)


def _psh(cmd):
    r = run_psh(['-c', cmd], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(r), r
    return r


def _bash(cmd):
    r = run_bash(['-c', cmd], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(r), r
    return r


class TestAssocBareNameIsLiteral(ConformanceTest):
    """r21 A1: a bare-name assoc key is a LITERAL, never a variable deref."""

    def test_read_does_not_deref_same_named_variable(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=1; k=other; h[other]=X; echo "${h[k]}"')

    def test_write_and_read_agree_on_literal_key(self):
        self.assert_identical_behavior(
            'declare -A h; k=other; h[k]=5; echo "${h[k]}"')

    def test_unset_removes_the_literal_key(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=1; k=other; unset "h[k]"; '
            'echo "${h[k]:-gone}"')

    def test_plus_operator_sees_literal_key(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=v; k=zzz; echo "${h[k]+SET}"')


class TestIsSetMatchesRead(ConformanceTest):
    """r21 A2: the +/-/? operators key exactly like the bare read."""

    def test_quoted_spaced_key_dq(self):
        self.assert_identical_behavior(
            'declare -A h; h["k 1"]=v; echo "${h["k 1"]+SET} ${h["k 1"]}"')

    def test_quoted_spaced_key_sq(self):
        self.assert_identical_behavior(
            "declare -A h; h['k 1']=v; "
            'echo "${h[\'k 1\']+SET} ${h[\'k 1\']}"')

    def test_dash_default_on_absent_key(self):
        self.assert_identical_behavior(
            'declare -A a; printf "%s\\n" "${a[nope]-UNSET}"')


class TestArithSubscriptVerbatim(ConformanceTest):
    """r21 A3: arith subscripts are captured verbatim, keyed by target kind."""

    def test_spaced_assoc_key_in_arith(self):
        self.assert_identical_behavior(
            'declare -A h; h["a b"]=4; echo $((h[a b]))')

    def test_whitespace_not_stripped(self):
        # bash keys " foo " (unset) -> 0, NOT the stripped "foo" -> 1.
        self.assert_identical_behavior(
            'declare -A h; h[foo]=1; echo $((h[ foo ]))')

    def test_plain_assoc_key_in_arith(self):
        self.assert_identical_behavior(
            'declare -A h; h[foo]=7; echo $((h[foo]))')

    def test_arith_increment_string_key(self):
        self.assert_identical_behavior(
            'declare -A h; h[foo]=7; (( h[foo]++ )); echo "${h[foo]}"')

    def test_let_string_key(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=3; let "h[k]=5"; echo "${h[k]}"')

    def test_quoted_key_in_arith_quote_removed(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=5; echo $((h["k"]))')

    def test_quoted_spaced_key_in_arith(self):
        self.assert_identical_behavior(
            'declare -A h; h["q w"]=4; echo $((h["q w"]))')

    def test_no_dollar_reexpansion_in_arith(self):
        # The arith pre-pass substituted $k once; bash never rescans the
        # substituted value: k='$x' keys the LITERAL $x, not x's value.
        self.assert_identical_behavior(
            'declare -A h; k="\\$x"; x=5; h["\\$x"]=111; h[5]=222; '
            'echo $((h[$k]))')

    def test_arith_write_keys_like_arith_read(self):
        self.assert_identical_behavior(
            'declare -A h; k="a b"; (( h[$k]=2 )); declare -p h')

    def test_nested_indexed_subscript(self):
        self.assert_identical_behavior(
            'b=(1 0); a=(9 8); echo $((a[b[0]]))')

    def test_comma_expression_index(self):
        self.assert_identical_behavior(
            'a=(10 20 30); echo $((a[1,2]))')

    def test_side_effect_fires_once(self):
        self.assert_identical_behavior(
            'a=(9 8 7); i=0; echo $((a[i++ + 1])) $i')

    def test_compound_assign_side_effect_once(self):
        self.assert_identical_behavior(
            'a=(5 5 5); b=1; (( a[b++] += 1 )); echo "${a[1]} $b"')

    def test_quoted_indexed_subscript_in_arith(self):
        self.assert_identical_behavior('a=(5 6); echo $((a["1"]))')

    def test_indexed_lazy_arith_error_at_evaluation(self):
        # A VALID-spelling arithmetic error surfaces at evaluation (both
        # shells error; stderr wording differs and is pinned separately).
        self.assert_identical_behavior(
            'declare -A h; h[a.b]=5; echo $((h[a.b]))')

    def test_nameref_arith_string_key(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=1; declare -n r=h; (( r[k]++ )); '
            'echo "${h[k]}"')


class TestArithSubscriptProvenance(ConformanceTest):
    """CV1: an arith associative key tracks PROVENANCE — quote/escape removal
    applies to SOURCE-spelled characters only, NEVER to characters arriving via
    ``$k``. These rows were DIVERGENT before v0.750.0 (psh quote-removed the
    substituted text); the doctrine $-half (no re-expansion of a substituted
    ``$``) stays bash-exact. Probed against bash 5.2
    (tmp/boundary-ledgers/CV-probes/cv1_matrix.sh)."""

    def test_substituted_double_quotes_stay_literal(self):
        # k='"q"' -> bash keys "q" (quotes kept), not q.
        self.assert_identical_behavior(
            'declare -A h; k=\'"q"\'; (( h[$k]=3 )); declare -p h')

    def test_substituted_single_quotes_stay_literal(self):
        self.assert_identical_behavior(
            'declare -A h; k="\'a b\'"; (( h[$k]=5 )); declare -p h')

    def test_substituted_backslash_dollar_stays_literal(self):
        self.assert_identical_behavior(
            "declare -A h; k='\\$x'; (( h[$k]=9 )); declare -p h")

    def test_braced_substitution_stays_literal(self):
        self.assert_identical_behavior(
            'declare -A h; k=\'"q"\'; (( h[${k}]=1 )); declare -p h')

    def test_mixed_source_and_substituted(self):
        self.assert_identical_behavior(
            'declare -A h; k=\'"q"\'; (( h[p$k]=1 )); declare -p h')

    def test_read_side_substituted_quotes_miss(self):
        # h has plain key q; k='"q"' looks up the quoted key (absent) -> 0.
        self.assert_identical_behavior(
            'declare -A h; h[q]=7; k=\'"q"\'; echo $(( h[$k] ))')

    def test_read_side_substituted_quotes_hit(self):
        self.assert_identical_behavior(
            'declare -A h; h[\'"q"\']=7; k=\'"q"\'; echo $(( h[$k] ))')

    def test_let_spelling_substituted_quotes(self):
        self.assert_identical_behavior(
            'declare -A h; k=\'"q"\'; let \'h[$k]=1\'; declare -p h')

    def test_for_loop_spelling_substituted_quotes(self):
        self.assert_identical_behavior(
            'declare -A h; k=\'"q"\'; '
            'for (( h[$k]=0; h[$k]<1; h[$k]++ )); do :; done; declare -p h')


class TestArithExtraDquoteRound(ConformanceTest):
    r"""CV1 B1: an arithmetic-COMMAND body (`(( ))`/`$(( ))`) is not
    shell-word-processed, so bash applies an EXTRA round-1 dquote pass to
    SOURCE-spelled subscript text before the associative keying —
    `(( expr )) == let "expr"` — while `let` (its arg already shell-processed)
    does NOT. The unified W2/CV1 engine dropped this extra round; these rows were
    RED at the fix's tip (kept `"q"`), GREEN on base and after. Substituted text
    is provenance-protected: it survives both rounds LITERAL. Bash 5.2-verified.
    """

    def test_backslash_dquote_write(self):
        # (( h[\"q\"]=1 )) -> bash q (round1 \" -> ", round2 removes it).
        self.assert_identical_behavior(
            r'declare -A h; (( h[\"q\"]=1 )); declare -p h')

    def test_backslash_dquote_read(self):
        self.assert_identical_behavior(
            r'declare -A h; h[q]=7; echo $(( h[\"q\"] ))')

    def test_double_backslash(self):
        self.assert_identical_behavior(
            r'declare -A h; (( h[\\q]=1 )); declare -p h')

    def test_backslash_letter(self):
        self.assert_identical_behavior(
            r'declare -A h; (( h[\q]=1 )); declare -p h')

    def test_backslash_dollar_stays_literal(self):
        # The extra round must NOT un-escape \$ into an expandable $x.
        self.assert_identical_behavior(
            r'declare -A h; x=5; (( h[\$x]=1 )); declare -p h')

    def test_substituted_survives_extra_round(self):
        # k's quotes arrive via $k and survive BOTH rounds literal.
        self.assert_identical_behavior(
            'declare -A h; k=\'"q"\'; (( h["x$k"]=1 )); declare -p h')

    def test_let_has_no_extra_round(self):
        # let 'h[\"q\"]=1' keeps "q" (one round only) — contrast with (( )).
        self.assert_identical_behavior(
            r"""declare -A h; let 'h[\"q\"]=1'; declare -p h""")


class TestArithSourceQuotesModelR1R2M1(ConformanceTest):
    r"""CV1 B1 round-2 bounce fixes. The extra round-1 dquote pass is applied
    ONLY to a SOURCE, substitution-free subscript in a `(( ))`/`$(( ))` context;
    it is dropped for `[[` operands (R1) and re-evaluated STORED values (R2,
    let-like), and round-2 quote removal runs ONLY for substitution-free
    subscripts — a subscript with ANY expansion keeps its round-1 output final
    (M1). All rows RED at the prior fix tip, bash 5.2-verified."""

    def test_r1_double_bracket_operand_is_let_like(self):
        # A [[ ]] numeric operand is a shell word (quote-processed), so no extra
        # round: bash keys "q" -> unset -> 7 != -> NO.
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; [[ 'h[\"q\"]' -eq 7 ]] && echo Y || echo N""")

    def test_r2_stored_value_bare_name(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; y='h[\"q\"]'; echo $(( y ))""")

    def test_r2_stored_value_dollar_expanded(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; y='h[\"q\"]'; echo $(( $y ))""")

    def test_r2_stored_value_name_chain(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; z=y; y='h[\"q\"]'; echo $(( z ))""")

    def test_r2_stored_array_element(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; a=('h[\"q\"]'); echo $(( a[0] ))""")

    def test_m1_escaped_dquote_around_sub_no_round2(self):
        # \"$k\" has an expansion, so round-1 output "Q" is FINAL (no round-2).
        self.assert_identical_behavior(
            r"""declare -A h; k=Q; (( h[\"$k\"]=1 )); declare -p h""")

    def test_m1_sub_then_escaped_dquote(self):
        self.assert_identical_behavior(
            r"""declare -A h; k=Q; (( h[$k\"z\"]=1 )); declare -p h""")

    def test_m1_cmdsub_then_escaped_dquote(self):
        self.assert_identical_behavior(
            r"""declare -A h; (( h[$(echo a)\"z\"]=1 )); declare -p h""")

    def test_m1_escaped_dquote_around_escaped_dollar(self):
        # \"\$x\" has a $ (escaped), so round-1 output "$x" is FINAL.
        self.assert_identical_behavior(
            r"""declare -A h; (( h[\"\$x\"]=1 )); declare -p h""")

    def test_m1_control_substitution_free_still_removes(self):
        # \"q\" (no $) still gets round-1 + round-2 -> q (control, stays green).
        self.assert_identical_behavior(
            r"""declare -A h; (( h[\"q\"]=1 )); declare -p h""")


class TestArithIntegerAttributeLetLikeM2(ConformanceTest):
    r"""CV1 M2: an INTEGER-attribute value (declare -i / local -i / -ai element,
    scalar or +=) is a shell-processed value, so an associative subscript inside
    it gets NO extra `(( ))` round-1 dquote pass — `declare -i v='h[\"q\"]'`
    keys "q" -> unset -> 0 (bash), not q -> 7. Pre-existing divergence, converged
    into the arith_source_quotes class. bash 5.2-verified."""

    def test_declare_i_scalar(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; declare -i v='h[\"q\"]'; echo $v""")

    def test_local_i_scalar(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; f(){ local -i v='h[\"q\"]'; echo $v; }; f""")

    def test_i_scalar_append(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; declare -i v=0; v+='h[\"q\"]'; echo $v""")

    def test_ai_element(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; declare -ai a; a[0]='h[\"q\"]'; echo ${a[0]}""")

    def test_ai_element_append(self):
        self.assert_identical_behavior(
            r"""declare -A h; h[q]=7; declare -ai a=(1); a[0]+='h[\"q\"]'; echo ${a[0]}""")


def _arith_key(cmd):
    """(stdout, rc) of psh/bash for an arith-subscript write, for the carrier
    documented-divergence rows (they compare psh vs bash EXPLICITLY, since they
    intentionally differ)."""
    p = _psh(cmd)
    b = _bash(cmd)
    return p.stdout, b.stdout


def test_divergence_arith_nested_quote_carriers():
    r"""CV1 B1 carry (register #23): a SINGLE-nested source quote in an
    arithmetic subscript — `(( h['"q"']=1 ))` / `(( h["'q'"]=1 ))` — is fully
    quote-removed by bash (key `q`) but psh's model applies only ONE extra
    dquote round (round 1 does not treat `'`/`"` as delimiters), keying the inner
    quotes literally. Divergent on BASE too (pre-existing, NOT a regression);
    the model's documented limit. bash 5.2-verified both-sides."""
    p1, b1 = _arith_key('declare -A h; (( h[\'"q"\']=1 )); declare -p h')
    assert '[q]="1"' in b1                       # bash removes both quote layers
    assert '["\\"q\\""]="1"' in p1               # psh keys the inner "q"
    p2, b2 = _arith_key('declare -A h; (( h["\'q\'"]=1 )); declare -p h')
    assert '[q]="1"' in b2
    assert '["\'q\'"]="1"' in p2                 # psh keys the inner 'q'


class TestAnsiCKeyDecode(ConformanceTest):
    """r21 A4: $'...' subscripts decode like any word."""

    def test_ansi_c_key_decodes_on_write_and_read(self):
        self.assert_identical_behavior(
            "declare -A a; a[$'k']=1; echo \"${a[k]}=${a[$'k']}\"; "
            'declare -p a')

    def test_ansi_c_tab_key_declare_p_roundtrip(self):
        self.assert_identical_behavior(
            "declare -A a; a[$'x\\ty']=1; declare -p a")

    def test_ansi_c_spaced_key_in_arith(self):
        self.assert_identical_behavior(
            "declare -A h; h[$'t u']=9; echo $((h[$'t u']))")


class TestUnsubscriptedAssoc(ConformanceTest):
    """r21 A5: $assoc expands as ${assoc[0]} (string key "0")."""

    def test_dollar_assoc_reads_key_zero(self):
        self.assert_identical_behavior(
            'declare -A a=([0]=zero [x]=y); echo "[$a]"')

    def test_dollar_assoc_empty_without_key_zero(self):
        self.assert_identical_behavior(
            'declare -A a=([k]=v); echo "[$a]"')

    def test_braced_form_too(self):
        self.assert_identical_behavior(
            'declare -A a=([0]=z); echo "[${a}]"')


class TestCompositeQuoting(ConformanceTest):
    """S3 carry: composite-quoted assoc keys concatenate after quote removal."""

    def test_two_single_quoted_runs(self):
        self.assert_identical_behavior(
            "declare -A h; h['a''b']=v; declare -p h")

    def test_double_then_single(self):
        self.assert_identical_behavior(
            'declare -A h; h["a"\'b\']=v; declare -p h')

    def test_literal_then_ansi_c(self):
        self.assert_identical_behavior(
            "declare -A h; h[a$'b']=v; declare -p h")

    def test_unquoted_var_expands(self):
        self.assert_identical_behavior(
            'declare -A h; k=KEY; h[$k]=v; declare -p h')

    def test_double_quoted_var_expands(self):
        self.assert_identical_behavior(
            'declare -A h; k=KEY; h["$k"]=v; declare -p h')

    def test_single_quoted_var_stays_literal(self):
        self.assert_identical_behavior(
            "declare -A h; k=KEY; h['$k']=v; declare -p h")

    def test_command_substitution_key(self):
        self.assert_identical_behavior(
            'declare -A h; h[$(echo cs)]=v; declare -p h')

    def test_unquoted_spaces_preserved(self):
        self.assert_identical_behavior(
            'declare -A h; h["a b"]=v; echo "${h[a b]}"')

    @pytest.mark.skipif(
        _OLD_BASH_NO_SUBSCRIPT_TILDE,
        reason="oracle bash is older than 5.2.24 (or its version could not be "
               "parsed); 5.2.24 introduced tilde expansion in associative-array "
               "subscripts and psh implements the current behaviour "
               "(see _TILDE_IN_SUBSCRIPT_VERSION)")
    def test_tilde_expands_in_key(self):
        self.assert_identical_behavior(
            'HOME=/probe-home; declare -A a; a[~]=v; echo "${!a[@]}"')


class TestTargetKindBeforeInterpretation(ConformanceTest):
    """The architectural core: the DECLARED variable decides, then interpret."""

    def test_undeclared_quoted_subscript_is_indexed(self):
        self.assert_identical_behavior(
            'h["Accept"]=x; h["Other"]=y; echo "${h[0]}"; declare -p h')

    def test_undeclared_name_arith_default(self):
        self.assert_identical_behavior('echo $((a[3-3]))')

    def test_scalar_subscript_zero(self):
        self.assert_identical_behavior('x=5; echo $((x[0]))')

    def test_scalar_subscript_via_param(self):
        self.assert_identical_behavior('x=5; echo "${x[0]}-${x[1]:-no}"')

    def test_declare_A_midscript_switches_keying(self):
        self.assert_identical_behavior(
            'declare -A h; h[k]=assoc1; echo "${h[k]}"')

    def test_local_assoc_shadowing_global_indexed(self):
        self.assert_identical_behavior(
            'a=(g0 g1); f() { local -A a; a[k]=L; echo "${a[k]}-${a[0]:-no}"; }; '
            'f; echo "${a[0]}"')

    def test_empty_key_write_rejected(self):
        # stderr carries the shell-name prefix (framework compares raw bytes),
        # so this row pins prefix-stripped bodies + rc explicitly.
        cmd = 'declare -A a; a[""]=empty; echo "rc=$?"'
        p, b = _psh(cmd), _bash(cmd)
        assert p.returncode == b.returncode == 1
        assert _strip_prefix(p.stderr) == _strip_prefix(b.stderr)
        assert 'a[""]: bad array subscript' in p.stderr

    def test_empty_expansion_key_write_rejected(self):
        cmd = 'declare -A a; e=; a[$e]=x; echo "rc=$?"'
        p, b = _psh(cmd), _bash(cmd)
        assert p.returncode == b.returncode == 1
        assert _strip_prefix(p.stderr) == _strip_prefix(b.stderr)
        assert 'a[$e]: bad array subscript' in p.stderr


class TestIndexedArithmetic(ConformanceTest):
    """Indexed subscripts: expand then (lazily) arithmetic-evaluate."""

    def test_expression_subscript(self):
        self.assert_identical_behavior('a[1+1]=x; echo "${a[2]}"')

    def test_dollar_variable_subscript(self):
        self.assert_identical_behavior('i=3; a[$i]=y; echo "${a[3]}"')

    def test_bare_name_derefs_arithmetically(self):
        self.assert_identical_behavior('i=2; a[i]=z; echo "${a[2]}"')

    def test_bare_name_recursion(self):
        self.assert_identical_behavior('i=j; j=2; a[i]=w; echo "${a[2]}"')

    def test_negative_index_read(self):
        self.assert_identical_behavior('a=(0 1 2 3); echo "${a[-1]}"')

    def test_negative_index_write(self):
        self.assert_identical_behavior('a=(x y); a[-1]=Z; echo "${a[1]}"')

    def test_whitespace_in_arith_subscript(self):
        self.assert_identical_behavior('a[ 1 + 1 ]=x; echo "${a[2]}"')

    def test_octal_invalid_rc(self):
        # Identical prefix-stripped stderr AND the fatal-discard rc (the
        # framework compares raw stderr, so the shell-name prefix rows pin
        # explicitly).
        cmd = 'a[08]=x; echo "rc=$?"'
        p, b = _psh(cmd), _bash(cmd)
        assert p.returncode == b.returncode == 1
        assert _strip_prefix(p.stderr) == _strip_prefix(b.stderr)
        assert 'value too great for base (error token is "08")' in p.stderr
        # DIRECT prefix pin (deliberately NOT satisfiable via _strip_prefix,
        # which normalizes both the old and new shapes): the subscript
        # arithmetic diagnostic carries the v0.690 location prefix like
        # bash's `bash: line 1: 08: ...`. A regression to the old bare
        # `psh: 08: ...` must turn this row red (bounce blocker B).
        assert p.stderr.startswith('psh: line 1: 08:'), p.stderr

    def test_huge_index_overflow(self):
        self.assert_identical_behavior(
            'a[999999999999999999]=x; echo "rc=$?"; echo "${a[999999999999999999]}"')


class TestSpecialSubscriptsAndBuiltins(ConformanceTest):
    """@/* subscripts, test -v, unset, declare -p round trips."""

    def test_assoc_at_expansion_sorted(self):
        # Enumeration ORDER is a documented divergence (bash hash order);
        # the VALUE SET is pinned order-independently.
        self.assert_identical_behavior(
            'declare -A a=([x]=1 [y]=2); printf "%s\\n" "${a[@]}" | sort')

    def test_assoc_length(self):
        self.assert_identical_behavior(
            'declare -A a=([x]=1 [y]=2); echo "${#a[@]}"')

    def test_assoc_keys_sorted(self):
        self.assert_identical_behavior(
            'declare -A a=([x]=1 [y]=2); printf "%s\\n" "${!a[@]}" | sort')

    def test_assoc_at_is_literal_write_key(self):
        self.assert_identical_behavior(
            'declare -A a; a[@]=X; declare -p a')

    def test_assoc_star_key_rendering(self):
        self.assert_identical_behavior(
            'declare -A a; a["*"]=star; declare -p a')

    def test_assoc_key_class_rendering_rows(self):
        # One row per renderer key class (single-key so enumeration order
        # cannot interfere): whole-string ~ (quoted), embedded dot / @
        # (bare), shell-special ! (quoted). Control-char, space, @ and *
        # classes are pinned by their own rows in this file.
        for cmd in ('declare -A a; a["~"]=t; declare -p a',
                    'declare -A a; a[a.b]=d; declare -p a',
                    'declare -A a; a[a@b]=e; declare -p a',
                    'declare -A a; a["a!b"]=x; declare -p a'):
            self.assert_identical_behavior(cmd)

    def test_test_v_assoc_key(self):
        self.assert_identical_behavior(
            'declare -A a=([x]=1); test -v "a[x]" && echo yes || echo no')

    def test_test_v_expands_subscript(self):
        self.assert_identical_behavior(
            'declare -A a=([zzz]=1); k=zzz; test -v "a[$k]" && echo Y || echo N')

    def test_bracket_bracket_v_assoc(self):
        self.assert_identical_behavior(
            'declare -A a=([k]=1); [[ -v a[k] ]] && echo yes || echo no')

    def test_bracket_bracket_v_indexed(self):
        self.assert_identical_behavior(
            'a=(1 2 3); [[ -v a[1] ]] && echo yes || echo no; '
            '[[ -v a[9] ]] && echo yes || echo no')

    def test_unset_assoc_element(self):
        self.assert_identical_behavior(
            'declare -A a=([x]=1); unset "a[x]"; declare -p a')

    def test_unset_indexed_at_empties_array(self):
        # bash 5.2 keeps the (now empty) array variable: `declare -a a=()`.
        self.assert_identical_behavior(
            'a=(1 2); unset "a[@]"; declare -p a; echo "rc=$?"')

    def test_unset_empty_subscript_is_noop(self):
        self.assert_identical_behavior(
            'a=(1 2); unset "a[]"; echo "rc=$? [${a[0]:-gone}]"')

    def test_unset_expanded_empty_subscript_is_noop(self):
        self.assert_identical_behavior(
            'a=(1 2); e=; unset "a[$e]"; echo "rc=$? [${a[0]:-gone}]"')

    def test_test_v_arith_expression_subscript(self):
        self.assert_identical_behavior(
            'a=(x y z); test -v "a[1+1]" && echo Y || echo N')

    def test_test_v_bare_name_derefs(self):
        self.assert_identical_behavior(
            'a=(x y z); i=2; test -v "a[i]" && echo Y || echo N')

    def test_test_v_bare_name_recursion(self):
        self.assert_identical_behavior(
            'a=(x y z); i=j; j=1; test -v "a[i]" && echo Y || echo N')

    def test_test_v_negative_index(self):
        self.assert_identical_behavior(
            'a=(x y z); test -v "a[-1]" && echo Y || echo N')

    def test_test_v_scalar_index_zero(self):
        self.assert_identical_behavior(
            'x=5; test -v "x[0]" && echo Y || echo N; '
            'test -v "x[1]" && echo Y || echo N; '
            'test -v "x[1-1]" && echo Y || echo N')

    def test_test_v_unset_name_still_reports_unset(self):
        self.assert_identical_behavior(
            'unset z; test -v "z[0]" && echo Y || echo N')

    def test_test_v_empty_subscript_silently_unset(self):
        self.assert_identical_behavior(
            'a=(x y); test -v "a[]"; echo after rc=$?')

    def test_test_v_expanded_empty_silently_unset(self):
        self.assert_identical_behavior(
            'a=(x y); e=; test -v "a[$e]"; echo after rc=$?')

    def test_bracket_bracket_v_arith_rows(self):
        self.assert_identical_behavior(
            'a=(x y z); [[ -v a[1+1] ]] && echo Y || echo N; '
            'i=2; [[ -v a[i] ]] && echo Y || echo N; '
            '[[ -v a[-1] ]] && echo Y || echo N; '
            'x=5; [[ -v x[0] ]] && echo Y || echo N')

    def test_test_v_negative_out_of_range_warns(self):
        # Non-fatal warning + unset (prefix-stripped bodies match).
        cmd = 'a=(x y); test -v "a[-9]"; echo after rc=$?'
        p, b = _psh(cmd), _bash(cmd)
        assert p.returncode == b.returncode == 0
        assert p.stdout == b.stdout == 'after rc=1\n'
        assert _strip_prefix(p.stderr) == _strip_prefix(b.stderr)
        assert 'a: bad array subscript' in p.stderr

    def test_test_v_invalid_arith_is_fatal(self):
        # bash fatally discards the line (`after` never runs, rc 1) — psh
        # matches the BEHAVIOR; the message wording is the documented general
        # arith-tokenizer divergence (see
        # test_divergence_arith_error_wording_not_keying).
        for cmd in ('a=(x y); test -v "a[1//]"; echo after rc=$?',
                    'unset z; test -v "z[1//]"; echo after rc=$?',
                    'a=(x y); [[ -v a[1//] ]]; echo after rc=$?',
                    'a=(x y); [[ -v "a[1//]" ]]; echo after rc=$?'):
            p, b = _psh(cmd), _bash(cmd)
            assert p.returncode == b.returncode == 1, (cmd, p, b)
            assert 'after' not in p.stdout and 'after' not in b.stdout
            assert p.stderr.strip() and b.stderr.strip()

    def test_declare_p_spaced_keys_roundtrip(self):
        self.assert_identical_behavior(
            'declare -A a=([k1]=v1 [k2]="v 2"); declare -p a')

    def test_key_containing_bracket_via_quotes_read(self):
        self.assert_identical_behavior(
            'declare -A a; a["x"]=1; echo "${a[x]}"')

    def test_at_A_transform_key_rendering(self):
        self.assert_identical_behavior(
            'declare -A a; a["k 1"]=3; echo "${a[@]@A}"')

    def test_at_K_transform_key_rendering(self):
        self.assert_identical_behavior(
            'declare -A a; a["k 1"]=3; echo "${a[@]@K}"')

    def test_at_K_indexed_bare_keys(self):
        self.assert_identical_behavior('a=(x y); echo "${a[@]@K}"')


# ---------------------------------------------------------------------------
# Documented divergences — explicit both-sides pins (do NOT silently vanish).
# ---------------------------------------------------------------------------

def test_divergence_arith_error_wording_not_keying():
    """I8/I10: invalid indexed subscripts error in BOTH shells (same rc);
    only the arithmetic error WORDING differs — a pre-existing, general
    arith-tokenizer divergence (identical text for plain $((1.5))), not a
    keying one."""
    for cmd in ('a[1.5]=x', 'a[1//]=x'):
        p, b = _psh(cmd), _bash(cmd)
        assert p.returncode == 1 and b.returncode == 1, (cmd, p, b)
        assert p.stderr.strip() and b.stderr.strip()
    # Same psh wording for the subscript and the plain expression — proves
    # the divergence is the general arith family, not subscript keying.
    sub = _psh('a[1.5]=x').stderr
    plain = _psh(': $((1.5))').stderr
    assert "Unexpected character '.'" in sub
    assert "Unexpected character '.'" in plain


def test_divergence_assoc_enumeration_order():
    """${a[@]} / declare -p enumeration order: psh uses insertion order
    (Python dict), bash uses hash-table order (an implementation artifact
    that varies by key). Values/keys match as SETS (pinned sorted above)."""
    cmd = 'declare -A a=([x]=1); a[@]=X; echo "${a[@]}"'
    p, b = _psh(cmd), _bash(cmd)
    assert sorted(p.stdout.split()) == sorted(b.stdout.split()) == ['1', 'X']


def test_divergence_empty_arith_subscript_fatality():
    """$((h[$e])) with e empty: BOTH shells report `h[]: bad array
    subscript`; bash warns (twice) and continues with 0, psh treats it as a
    fatal arithmetic error discarding the line (cleaner; declared)."""
    cmd = 'declare -A h; e=; h[x]=3; echo $((h[$e])); echo after'
    p, b = _psh(cmd), _bash(cmd)
    assert 'bad array subscript' in p.stderr and 'bad array subscript' in b.stderr
    assert 'after' in b.stdout      # bash continues
    assert 'after' not in p.stdout  # psh discards the line (declared)


def test_divergence_arith_subscript_adjacency_required():
    """`$(( h [k] ))` (space before `[`): an error in BOTH shells — the
    subscript attaches only when `[` is adjacent (wording differs)."""
    cmd = 'declare -A h; h[k]=9; echo $(( h [k] ))'
    p, b = _psh(cmd), _bash(cmd)
    assert p.returncode != 0 or p.stderr.strip()
    assert b.returncode != 0 or b.stderr.strip()
    assert '9' not in p.stdout and '9' not in b.stdout


# --- Remediation 2.3 flips: the K1 extent, procsub-identity, and sq-in-dq ---
# rows below were divergence pins until slot 2.3 (quote-aware extent scanner,
# procsub keying identity + read-time rejection). Now equality/parity pins.

def _both(cmd):
    """(psh, bash) results for identical `-c` runs, rd parser."""
    return _psh(cmd), _bash(cmd)


def _psh_comb(cmd):
    r = run_psh(['--parser', 'combinator', '-c', cmd], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(r), r
    return r


def test_quote_aware_extent_in_assignment_word():
    """K1 FLIPPED (2.3): the assignment-word subscript extent is quote-aware —
    `a["a]b"]=1` keys `a]b` in both shells (psh formerly truncated at the
    first `]` and mis-keyed `"a` through the broad-catch literal fallback)."""
    cmd = 'declare -A a; a["a]b"]=1; declare -p a'
    p, b = _both(cmd)
    assert '["a]b"]="1"' in b.stdout
    assert p.stdout == b.stdout
    assert _psh_comb(cmd).stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    'declare -A a; a["]"]=ok; declare -p a; echo ok',      # dq ]
    "declare -A a; a[']']=x; declare -p a",                # sq ]
    'declare -A a; a[\\]]=x; declare -p a',                # backslash ]
    "declare -A a; a[$']']=x; declare -p a",               # ANSI-C ]
    'declare -A a; a["+="]=v; declare -p a',               # quoted += not the operator
    "declare -A a; a[']'x]=v; declare -p a",               # quote then text
    'declare -A a; a["["]=L; declare -p a',                # dq [ (parity kept)
    'i=1; b=(9 8 7); c[b[i]]=N; declare -p c',             # unquoted nesting
    'declare -A a; a[$(echo "]")]=c; declare -p a',        # ] inside cmdsub
    'declare -A a; a["]"]=1; a["]"]+=2; declare -p a',     # append via quoted ]
    'declare -A a=(["]"]=I); declare -p a',                # init path (parity kept)
])
def test_quote_aware_extent_family(cmd):
    """The full K1 write-side family: every quote/escape/substitution carrier
    of `]` spans to the REAL close on BOTH parsers (bash-identical bytes)."""
    p, b = _both(cmd)
    assert p.stdout == b.stdout and p.returncode == b.returncode
    assert _psh_comb(cmd).stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    'declare -A a; a["]"]=ok; echo "read=${a["]"]}"',      # dq read-back
    "declare -A a; a[']']=ok; echo read=${a[']']}",        # sq read-back
    'declare -A a; a["]"]=V; echo "${a["]"]:-d}"',         # operator after subscript
    'declare -A a; a["]"]=hello; echo "${#a["]"]}"',       # length form
    'declare -A a; a["]"]=R; echo "read=${a[$(echo "]")]}"',  # cmdsub ] read
    'declare -A a; a["]"]=1; a[x]=2; unset -v \'a["]"]\'; echo rc=$?; declare -p a',
    'declare -A a; a["]"]=1; test -v \'a["]"]\'; echo rc=$?',
])
def test_quote_aware_extent_read_side(cmd):
    """K1 read-side family: `${a["]"]}` and friends (the `${...}` classifier's
    subscript extent + operator scan are quote-aware), plus the builtin
    surfaces addressing the same key."""
    p, b = _both(cmd)
    assert p.stdout == b.stdout and p.returncode == b.returncode
    assert _psh_comb(cmd).stdout == b.stdout


def test_element_head_requires_adjacent_operator():
    """2.3 rider (probe e1): `a[k]x=v` is a COMMAND word in bash (`command
    not found`), not an element assignment — psh formerly parsed it as
    `a[k]=v`-with-junk. The `=` must sit immediately after the closing `]`."""
    cmd = 'a[k]x=v; echo rc=$?'
    p, b = _both(cmd)
    assert b.stdout == p.stdout == 'rc=127\n'
    assert 'command not found' in p.stderr and 'command not found' in b.stderr
    assert _psh_comb(cmd).stdout == b.stdout


def test_procsub_in_subscript_keys_literal_spelling():
    """HIGH-4 FLIPPED (2.3), identity half: an unquoted `<(...)` spelling in
    an associative subscript is the LITERAL key — bash never runs it (psh
    formerly executed it at keying time and keyed /dev/fd/N)."""
    for cmd in (
        'declare -A a; a[<(printf x)]=v; declare -p a',
        'declare -A a; a[x<(y)]=v; declare -p a',            # mixed spelling
        "declare -A a; a['<(printf k)']=v; echo \"read=${a[<(printf k)]}\"",
        "declare -A a; a['<(printf x)']=v; unset -v 'a[<(printf x)]'; declare -p a",
        "declare -A a; a['<(printf x)']=v; test -v 'a[<(printf x)]'; echo rc=$?",
        'declare -A a; a["<(printf x)"]=v; declare -p a',    # quoted spelling
    ):
        p, b = _both(cmd)
        assert p.stdout == b.stdout and p.returncode == b.returncode, (cmd, p, b)
        assert '/dev/fd' not in p.stdout, cmd
        assert _psh_comb(cmd).stdout == b.stdout, cmd


def test_procsub_in_subscript_never_launches(tmp_path):
    """HIGH-4 identity: the procsub BODY never runs at keying time (no side
    effects) — probed via a would-be side-effect file."""
    marker = tmp_path / 'side.out'
    script = tmp_path / 'probe.sh'
    script.write_text(
        f'declare -A a; a[<(echo RAN > {marker})]=v; sleep 0.2; '
        f'test -f {marker} && echo SIDE_EFFECT || echo NO_SIDE_EFFECT\n')
    for r in (run_psh([str(script)], cwd=PSH_ROOT, timeout=15),
              run_psh(['--parser', 'combinator', str(script)],
                      cwd=PSH_ROOT, timeout=15),
              run_bash([str(script)], cwd=PSH_ROOT, timeout=15)):
        assert is_comparable(r), r
        assert r.stdout == 'NO_SIDE_EFFECT\n', r


def test_procsub_in_subscript_read_time_rejection(tmp_path):
    """HIGH-4 FLIPPED (2.3), timing half: an INVALID `<(...)` body anywhere in
    a word-context subscript rejects the whole buffer at READ time — dead
    branches included — in both shells (file mode rc 2; the `-c` 2-vs-127
    residual is slot 2.4's pin). Arith context and quoted spellings defer in
    both."""
    rejected = [
        'true || a[<(if)]=1; echo ran\n',        # dead branch, in-procsub
        'true || a[>(if)]=1; echo ran\n',        # out-procsub
        'true || a[1<(if)]=x; echo ran\n',       # mid-subscript spelling
        'true || echo "${a[<(if)]}"; echo ran\n',  # reference subscript
    ]
    deferred = [
        'true || : $((a[<(if)])); echo ran\n',   # arith context: no validation
        'true || echo "${a["<(if)"]}"\necho ran\n',   # quoted spelling defers
        "true || echo \"${a['<(if)']}\"\necho ran\n",
    ]
    for body in rejected + deferred:
        script = tmp_path / 'probe.sh'
        script.write_text(body)
        bash_r = run_bash([str(script)], cwd=PSH_ROOT, timeout=15)
        rd_r = run_psh([str(script)], cwd=PSH_ROOT, timeout=15)
        comb_r = run_psh(['--parser', 'combinator', str(script)],
                         cwd=PSH_ROOT, timeout=15)
        assert is_comparable(bash_r) and is_comparable(rd_r), (body, bash_r, rd_r)
        assert is_comparable(comb_r), (body, comb_r)
        if body in rejected:
            assert bash_r.returncode == 2 and 'ran' not in bash_r.stdout, body
        else:
            assert bash_r.returncode == 0 and 'ran' in bash_r.stdout, body
        for r in (rd_r, comb_r):
            assert r.returncode == bash_r.returncode, (body, r)
            assert r.stdout == bash_r.stdout, (body, r)


def test_procsub_arith_control_rows():
    """`1<(2)` stays arithmetic (`<` operator) and a VALID `<(echo hi)` on an
    INDEXED target still fails as arithmetic at RUNTIME — identical outcomes
    (rc + stdout; the arith error WORDING is the recorded general family)."""
    cmd = 'a[1<(2)]=x; declare -p a'
    p, b = _both(cmd)
    assert p.stdout == b.stdout and '[1]="x"' in b.stdout
    assert _psh_comb(cmd).stdout == b.stdout
    runtime = 'a[<(echo hi)]=1; echo rc=$?'
    p, b = _both(runtime)
    assert p.returncode == b.returncode == 1
    assert p.stdout == b.stdout == ''
    assert p.stderr.strip() and b.stderr.strip()


def test_sq_inside_dq_subscript_runtime_stage_parity():
    """S3-verify carry FLIPPED to a parity row (2.3): `"${h['$(if)']}"` is a
    RUNTIME failure in BOTH shells. The pin's old psh-side claim ("rejects at
    parse time") was already stale at the campaign launch base 0215279c
    (slot-2.3 ledger, RESULTS-0215279c-drift.txt): both shells defer — the
    dead-branch and next-line probes prove stage parity; only the runtime
    error WORDING differs (psh: nested parse error + arith error; bash: its
    runtime cmdsub's syntax error), which stays documented here."""
    ok = "declare -A h; h[\"k\"]=v; echo \"${h['k']}\""
    p, b = _both(ok)
    assert p.stdout == b.stdout == 'v\n'
    bad = 'echo "${h[\'$(if)\']}"'
    pb, bb = _both(bad)
    assert pb.returncode == bb.returncode == 1
    assert pb.stdout == bb.stdout == ''
    assert 'syntax error' in bb.stderr and pb.stderr.strip()  # wording differs
    # Stage parity, dead branch: NEITHER shell validates at read time.
    dead = "true || echo \"${h['$(if)']}\"; echo ran"
    pd, bd = _both(dead)
    assert pd.stdout == bd.stdout == 'ran\n'
    assert pd.returncode == bd.returncode == 0
    assert bd.stderr == '' and pd.stderr == ''
    # Stage parity, continuation: the NEXT line still runs in both.
    nxt = 'echo "${h[\'$(if)\']}"\necho nextline'
    pn = run_psh([], stdin_data=nxt + '\n', cwd=PSH_ROOT, timeout=15)
    bn = run_bash([], stdin_data=nxt + '\n', cwd=PSH_ROOT, timeout=15)
    assert is_comparable(pn) and is_comparable(bn)
    assert pn.stdout == bn.stdout == 'nextline\n'
    # The dq-nested assignment-word control (s5): sq inside dq inside an
    # ASSIGNMENT subscript IS read-time validated in both shells.
    s5 = 'declare -A h; h["\'$(if)\'"]=X\necho set rc=$?'
    ps = run_psh([], stdin_data=s5 + '\n', cwd=PSH_ROOT, timeout=15)
    bs = run_bash([], stdin_data=s5 + '\n', cwd=PSH_ROOT, timeout=15)
    assert is_comparable(ps) and is_comparable(bs)
    assert ps.returncode == bs.returncode == 2
    assert ps.stdout == bs.stdout == ''


@pytest.mark.parametrize('cmd', [
    "declare -A a; a[']']=v; echo read=${a[']']}",       # sq, unquoted outer
    "declare -A a; a[']']=v; echo \"read=${a[']']}\"",   # sq, dq outer
    'declare -A a; a["]"]=v; echo read=${a["]"]}',       # dq, unquoted outer
    'declare -A a; a["]"]=v; echo "read=${a["]"]}"',     # dq, dq outer
    "declare -A a; a[$'[']=v; echo read=${a[$'[']}",     # ansi-c [, unq outer
    "declare -A a; a[$']'x]=v; echo read=${a[$']'x]}",   # ansi-c ], unq outer
    "declare -A a; a[$'k']=v; echo \"read=${a[$'k']}\"",  # ansi-c plain, dq outer
])
def test_bracket_carrier_read_matrix_parity(cmd):
    """2.3 g-matrix, parity cells: every sq/dq bracket carrier reads back in
    BOTH outer contexts, and ANSI-C carriers in the UNQUOTED outer context —
    identical bytes (18 of the 20 probed cells; the 2 divergent cells are the
    next test)."""
    p, b = _both(cmd)
    assert p.stdout == b.stdout == 'read=v\n' and p.returncode == b.returncode
    assert _psh_comb(cmd).stdout == b.stdout


def test_divergence_dq_ansi_bracket_read():
    """2.3 DECLARED divergence (g-matrix cells g6/g8, ruling requested in the
    slot ledger): a DOUBLE-QUOTED `"${a[...]}"` read whose subscript carries
    an ANSI-C-quoted BRACKET — bash textually decodes the `$'...'` early
    inside its dq-`${...}` scan (its own error shows `${a[[]}`) and then
    FAILS rc 1 on the bracket it just materialised, unable to read back the
    very key its write path stored. psh's ONE quote-aware extent reads the
    key (self-consistent write/read round-trip). At base 4c319a04 psh
    happened to reject too (quote-blind extent -> bad substitution rc 1);
    the tip behavior is the deliberate one."""
    for cmd, key_probe in [
        ('declare -A a; a[$\'[\']=v; echo "read=${a[$\'[\']}"', 'read=v\n'),
        ('declare -A a; a[$\']\'x]=v; echo "read=${a[$\']\'x]}"', 'read=v\n'),
    ]:
        p, b = _both(cmd)
        assert b.returncode == 1 and b.stdout == ''       # bash: cannot read back
        assert 'bad substitution' in b.stderr or 'no closing' in b.stderr
        assert p.returncode == 0 and p.stdout == key_probe  # psh: round-trips
        assert _psh_comb(cmd).stdout == key_probe


def test_divergence_unlexable_subscript_typed_error():
    """2.3 rider (probe e2) — documented divergence, both sides pinned: an
    un-lexable subscript held RAW by the arithmetic path (`$((h['x]))`) is a
    LEXER-level rc-2 reject of the whole buffer in bash (the quote spans the
    rest of the source), while psh's arith tokenizer captures the subscript
    verbatim and the keying engine raises its typed rc-1
    `['x]: bad array subscript` (SubscriptSyntaxError, discard-line) — the
    former broad-catch silently keyed the junk literally and printed 0."""
    cmd = "declare -A h; h[x]=1; echo $((h['x])); echo after"
    p, b = _both(cmd)
    assert b.returncode == 2 and 'EOF' in b.stderr        # bash: lexer reject
    assert p.returncode == 1                              # psh: typed keying error
    assert "['x]: bad array subscript" in p.stderr
    assert p.stdout == b.stdout == ''                     # neither prints 0/after
    pc = _psh_comb(cmd)
    assert pc.returncode == 1 and "['x]: bad array subscript" in pc.stderr


@pytest.mark.parametrize('cmd,bash_out', [
    ('unset x; set -- a b; printf "<%s>" "${x:-"$@"}"', '<a><b>'),
    ('unset x; set -- a b; printf "<%s>" ${x:-"$@"}', '<a><b>'),
    ('x=set; set -- a b; printf "<%s>" "${x:+"$@"}"', '<a><b>'),
    ('unset x; set -- "a 1" b; printf "<%s>" "${x:-"$@"}"', '<a 1><b>'),
])
def test_divergence_operand_at_flattens(cmd, bash_out):
    """W1-verify carry (nit 9, W1/W2 seam residue): `"$@"` inside a
    parameter-operand word yields separate fields in bash; psh's
    OperandResult mini-IR carries protection but not field boundaries, so
    the fields flatten to one (space-joined). Base-identical (probed at
    d4db9c57); needs field-boundary-carrying operand results (W1/W3)."""
    p, b = _psh(cmd), _bash(cmd)
    assert b.stdout == bash_out
    # psh: ONE field, space-joined:
    joined = '<' + bash_out.replace('><', ' ').strip('<>') + '>'
    assert p.stdout == joined
