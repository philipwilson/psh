"""Array-subscript keying conformance (campaign W2 / reappraisal #21 A-family).

One feature — interpreting an array subscript — was implemented six
inconsistent ways across six modules (r21's signature finding). W2 replaced
them with one authority (``psh/expansion/subscript.py``): target kind FIRST
(the DECLARED variable decides indexed-vs-associative; an undeclared name is
indexed), then ONE interpretation per kind — associative keys get one
word/quote expansion under assignment-value semantics (no split, no glob, no
bare-name dereference), indexed subscripts expand then lazily
arithmetic-evaluate.

Every row was first probed against the 5.2 oracle at base d4db9c57 and holds
against bash 5.3.15 (Wave 0.1 re-verification, 2026-09-06; the rows that moved
with the oracle — the `case` procsub render, the sq-in-dq read-back, the
let_arith route, and HOME-via-environment for the tilde row — say so in
place): the A/Q/K rows were DIVERGENT at base and are red-on-base pins; the
I/S/V/R rows matched at base and are parity pins. Documented divergences live
at the bottom as explicit both-sides tests (house style of
test_nested_substitution_timing_conformance.py).
"""
import re
from pathlib import Path

import pytest
from conformance_framework import ConformanceTest
from oracle_policy import oracle_at_least
from shell_oracle import is_comparable, run_bash, run_psh

PSH_ROOT = Path(__file__).resolve().parents[3]


# bash 5.2 PATCH 24 began expanding a tilde inside an associative-array
# subscript: `HOME=/probe-home; declare -A a; a[~]=v; echo "${!a[@]}"` prints
# the literal `~` up to 5.2.23 and `/probe-home` from 5.2.24 on. Bisected by
# building each patch level from the GNU tarball + official patches on ONE
# Linux box, so the flip is the bash VERSION and not the platform:
#     5.2.22 -> ~     5.2.23 -> ~     5.2.24 -> /probe-home    5.2.25 -> /probe-home
# psh implements the current (>=5.2.24) behaviour. An oracle that predates the
# change (a distro build at patch level 21, say) skips the row rather than
# "widening" it to accept both answers, which would stop it proving anything on
# the hosts that CAN check it.
#
# The classifier is the policy API (Improvement Program 2026-09, D5):
# oracle_at_least fails CLOSED — an older series (5.1, say) skips instead of
# failing on a difference it cannot be expected to show, and an UNPARSEABLE
# version parses as (0, 0, 0) and skips too. This file used to re-parse
# resolve_bash().version with its own regex and compare the tuple against a
# private constant — a second implementation of the rule, now forbidden by
# tests/unit/tooling/test_no_version_literal_predicates.py.
#
# HOME reaches the row through the ENVIRONMENT, never an in-script assignment
# (D14). The Homebrew bash 5.3.15 bottle is linked against the installed
# readline, whose tilde expander resolves HOME from the process's STARTUP
# environment (its getenv-based sh_get_env_value wins under the two-level
# namespace), so `HOME=/probe-home; declare -A a; a[~]=v` keys the login home
# there — every unquoted `~` does, even after `export HOME=…`, while bash's own
# `cd` still honours the shell variable. That is an oracle-BINARY artefact, not
# bash semantics (a GNU-readline bash prints /probe-home), so psh must NOT copy
# it; with HOME supplied in the environment both shells print /probe-home.
_OLD_BASH_NO_SUBSCRIPT_TILDE = not oracle_at_least("5.2.24")

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
               "(classified by oracle_at_least, D5)")
    def test_tilde_expands_in_key(self):
        # D14: HOME via env=, not in-script — see the comment block above
        # _OLD_BASH_NO_SUBSCRIPT_TILDE (the installed-readline oracle bottle
        # resolves `~` from the startup environment).
        self.assert_identical_behavior(
            'declare -A a; a[~]=v; echo "${!a[@]}"', env={'HOME': '/probe-home'})


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
    'declare -A a; a["a]b"]=1; echo "read=${a["a]b"]}"',   # R2-3: quoted ] MID-key
])
def test_quote_aware_extent_read_side(cmd):
    """K1 read-side family: `${a["]"]}` and friends (the `${...}` classifier's
    subscript extent + operator scan are quote-aware), plus the builtin
    surfaces addressing the same key."""
    p, b = _both(cmd)
    assert p.stdout == b.stdout and p.returncode == b.returncode
    assert _psh_comb(cmd).stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    'declare -A a; a[[k]]=v; declare -p a',      # unquoted nesting keys [k]
    'a]x[0]=v; echo rc=$?',                      # ] before [ -> command word
    'declare -A a; a[]]=v; echo rc=$?',          # empty-then-] -> command word
    'declare -A a; a[x=1]=v; declare -p a',      # = INSIDE subscript keys x=1
    'declare -A a; a[x+=y]=v; declare -p a',     # += inside subscript is key text
    'declare -A a; a[2>x]=v; declare -p a',      # redirect-token slice keeps the fd (B2)
])
def test_head_scan_family_deltas_toward_bash(cmd):
    """R1-7 (round-1 verifier): base->tip head-scan deltas BEYOND the two
    declared riders, enumerated by the r17 battery — every one lands ON bash
    (base mis-keyed or mis-classified each). Both parsers."""
    p, b = _both(cmd)
    assert p.stdout == b.stdout and p.returncode == b.returncode, (cmd, p, b)
    assert _psh_comb(cmd).stdout == b.stdout, cmd


def test_head_scan_doubled_close_is_command_word():
    """R1-7: `a[k]]=v` — base MIS-KEYED it ([k]="]=v"); tip classifies it a
    command word like bash (rc-in-$? 127, nothing stored). Asserted on rc +
    diagnostics + no-key rather than raw declare -p bytes because bash
    renders a declared-but-empty assoc as `declare -A a` while psh renders
    `declare -A a=()` — a PRE-EXISTING declare -p formatting residual
    (out of slot scope, noted in the slot ledger), not a keying fact."""
    cmd = 'declare -A a; a[k]]=v; echo rc=$?; declare -p a'
    p, b = _both(cmd)
    assert 'rc=127' in b.stdout and 'command not found' in b.stderr
    assert 'rc=127' in p.stdout and 'command not found' in p.stderr
    assert '[k]' not in p.stdout and '[k]' not in b.stdout  # nothing stored
    assert 'rc=127' in _psh_comb(cmd).stdout


def test_divergence_doubled_open_unclosed_family():
    """R1-7: `a[[k]=v` (unclosed inner bracket) — base MIS-KEYED `[k`; tip
    refuses the malformed head and runs it as a command (rc-in-$? 127,
    nothing stored); bash instead treats the word as INCOMPLETE INPUT and
    fails rc 2 wanting the matching `]` (lexer-continuation family, same
    ceremony carry area as the other lexer word-extent rows). Both sides
    pinned; psh's half improves on base (no silent mis-key) without
    reaching bash's continuation model."""
    cmd = 'declare -A a; a[[k]=v; echo rc=$?; declare -p a'
    p, b = _both(cmd)
    assert b.returncode == 2 and 'EOF' in b.stderr        # bash: wants more input
    assert 'rc=127' in p.stdout and 'command not found' in p.stderr
    assert '[k' not in p.stdout.replace('a[[k]=v', '')     # nothing mis-keyed
    assert 'rc=127' in _psh_comb(cmd).stdout


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
    an associative subscript never RUNS — its frame is literal key text while
    its body expands like any word ($-forms/cmdsubs/quote removal; nested
    frames stay literal). psh formerly executed the procsub at keying time
    and keyed /dev/fd/N."""
    for cmd in (
        'declare -A a; a[<(printf x)]=v; declare -p a',
        'declare -A a; a[x<(y)]=v; declare -p a',            # mixed spelling
        "declare -A a; a['<(printf k)']=v; echo \"read=${a[<(printf k)]}\"",
        "declare -A a; a['<(printf x)']=v; unset -v 'a[<(printf x)]'; declare -p a",
        "declare -A a; a['<(printf x)']=v; test -v 'a[<(printf x)]'; echo rc=$?",
        'declare -A a; a["<(printf x)"]=v; declare -p a',    # quoted spelling
        # Frame literal, BODY expands (bash): $-forms/cmdsubs/quotes inside
        # the spelling behave as in any word; nested frames stay literal.
        'declare -A a; a[\'<(cat )\']=v; echo "read=${a[<(cat $y)]}"',
        'declare -A a; y=Q; a[\'<(cat Q)\']=v; echo "read=${a[<(cat $y)]}"',
        "declare -A a; a['<(cat )']=v; test -v 'a[<(cat $y)]'; echo rc=$?",
        "declare -A a; a['<(cat )']=v; unset -v 'a[<(cat $y)]'; declare -p a",
        'declare -A a; a[\'<(x q)\']=v; echo "read=${a[<(x $(echo q))]}"',
        'declare -A a; a[\'<(cat q)\']=v; echo "read=${a[<(cat \'q\')]}"',
        'declare -A a; a[\'<(a <(b))\']=v; echo "read=${a[<(a <(b))]}"',
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


def test_sq_in_dq_readback_round_trips():
    """PARITY — formerly the R1-6 declared divergence, CLOSED on the ORACLE
    side (empirical, 5.3.15; the nearest NEWS item is 5.3 `t. array_expand_once:
    new shopt option, replaces assoc_expand_once`): with the assoc target
    DECLARED and the sq-spelling key PRE-WRITTEN, `"${h['$(if)']}"` reads
    back v (rc 0) in BOTH shells and both psh parsers. The 5.2 oracle treated
    the dq-context subscript as expansion-bearing text at READ time,
    attempted the `$(if)` command substitution and failed rc 1 with a syntax
    error — it could not read back the key its own write stored — while psh
    keyed the single-quoted spelling literally in both directions; bash now
    agrees with psh. The UNDECLARED-target half of this family (runtime
    stage parity, wording-only residual) is
    test_sq_inside_dq_subscript_runtime_stage_parity above. The oracle-side
    flip is recorded in the program's FLIP-PINS.md (Wave 0.1)."""
    cmd = 'declare -A h; h[\'$(if)\']=v; echo "read=${h[\'$(if)\']}"; echo rc=$?'
    p, b = _both(cmd)
    assert b.returncode == 0 and b.stdout == 'read=v\nrc=0\n', b
    assert b.stderr == ''                      # no runtime cmdsub attempt
    assert p.returncode == 0 and p.stdout == b.stdout
    assert _psh_comb(cmd).stdout == p.stdout


def test_divergence_lexer_splits_quoted_space_subscript():
    """2.3-discovered CARRY (MEDIUM-4's LEXER half — out of slot 2.3's
    boundary, ruled a ceremony carry row): psh's LEXER splits an element
    word at a SPACE that follows a QUOTED section inside the brackets —
    `a['x=1'a b+=]=v` tokenizes as TWO words, so psh runs a command
    (`a['x=1'a: command not found`, rc 127) where bash keeps ONE word and
    keys `x=1a b+=`. The unquoted form (`arr[key with space]=v`) stays one
    word and works in both. Pre-existing and base-identical at 4c319a04
    (slot-2.3 ledger, RESULTS-tip-genfuzz.txt family 3); flips when the
    lexer-extent carry is closed."""
    cmd = "declare -A a; a['x=1'a b+=]=v; echo rc=$?; declare -p a"
    p, b = _both(cmd)
    assert b.stdout == 'rc=0\ndeclare -A a=(["x=1a b+="]="v" )\n'  # bash keys it
    assert p.stdout == 'rc=127\ndeclare -A a=()\n'    # psh: split -> command
    assert 'command not found' in p.stderr
    assert _psh_comb(cmd).stdout == p.stdout            # both parsers (lexer-level)
    # Control: unquoted spaces inside brackets stay ONE word in both shells.
    ok = 'declare -A a; a[key with space]=v; declare -p a'
    po, bo = _both(ok)
    assert po.stdout == bo.stdout == 'declare -A a=(["key with space"]="v" )\n'


def test_divergence_unset_nonbracket_arg_silent():
    """2.3-discovered CARRY (unset ARG-CLASSIFICATION, outside the slot-2.3
    builtins grant, ruled a ceremony carry row): an unset argument that
    contains `[` but does NOT end with `]` — `unset -v 'a["]"'` — never
    reaches the element-keying sites (split_subscript requires the trailing
    `]`), so psh falls through to a SILENT rc-0 no-op, while bash reports
    `unset: a["]"': not a valid identifier` (rc 1, loud) and continues.
    Neither shell unsets anything (keys intact in both). Pre-existing and
    base-identical at 4c319a04 (slot-2.3 ledger, m12/m13 probes); flips when
    the unset arg-classification carry is closed."""
    cmd = 'declare -A a; a["]"]=1; unset -v \'a["]"\'; echo rc=$?; declare -p a'
    p, b = _both(cmd)
    assert b.stdout == 'rc=1\ndeclare -A a=(["]"]="1" )\n'   # bash: rc 1, loud
    assert 'not a valid identifier' in b.stderr
    assert p.stdout == 'rc=0\ndeclare -A a=(["]"]="1" )\n'   # psh: silent no-op
    assert p.stderr == ''
    assert _psh_comb(cmd).stdout == p.stdout


# --- B2 (round 2): bash re-renders procsub spellings from its parse ---------
# The keying identity is spelling-level, and bash's stored spelling is its
# print_command RE-RENDER for the covered construct subset (whitespace
# collapse, trailing-; drop, canonical redirect spacing). psh implements that
# rule in expansion/procsub_render.py with ONE structural render-vs-raw
# predicate; uncovered constructs keep the RAW spelling (declared
# normalization residual — pins below).

_B2_ATOMS = {
    'simple': 'echo hi', 'quoted_sq': "echo 'a b'", 'quoted_dq': 'echo "x  y"',
    'var': 'cat $y', 'cmdsub': 'echo $(echo q)', 'nested_ps': 'cat <(echo z)',
    'redirect': 'echo hi > /dev/null', 'redirect_in': 'wc -l < /etc/hosts',
    'pipeline': 'echo a | wc -l', 'andlist': 'true && echo b',
    'two_cmds': 'echo a; echo b', 'subshell': '(echo s)',
    'fd_dup': 'echo e 2>&1', 'append_red': 'cat >> log',
    'fd2_red': 'echo x 2> e', 'dup_to_2': 'echo y >&2',
    'in_red_var': 'read n < $f', 'brace_grp': '{ echo g; }',
    'dup_explicit': 'echo z 1>&2',
    # R4-1: backgrounded bodies render with bash's `stmt &` rule.
    'bg_simple': 'sleep 0 &', 'bg_two': 'echo a & echo b',
}
_B2_SPACINGS = {
    'tidy': lambda b: b,
    'pad': lambda b: ' ' + b + ' ',
    'runs': lambda b: b.replace(' ', '  '),
    'tabs': lambda b: b.replace(' ', '\t'),
    'pad_runs': lambda b: '  ' + b.replace(' ', '   ') + '  ',
}
_B2_TRAILING = {'none': '', 'semi': ';', 'semi_sp': ' ; '}


def _b2_cells():
    """The GENERATED ruled space: 19 atoms x 5 spacings x 3 trailings x 2
    directions = 570 cells, minus the 12 SEPARATED-SUBSHELL cells (subshell
    atom under pad/pad_runs), which bash re-renders via its bimodal `((`
    disambiguation — those are the residual divergence test below."""
    for aname, atom in _B2_ATOMS.items():
        for sname, sp in _B2_SPACINGS.items():
            if aname == 'subshell' and sname in ('pad', 'pad_runs'):
                continue
            for tname, tr in _B2_TRAILING.items():
                if aname.startswith('bg_') and tname != 'none':
                    # `... & ;` is a bash syntax error — the trailing-;
                    # dimension does not compose with backgrounded atoms.
                    continue
                for d in '<>':
                    yield d + '(' + sp(atom) + tr + ')'


def _b2_key_script(cells):
    """One script printing each cell's stored key NUL-delimited, in order."""
    out = []
    for spelling in cells:
        out.append('declare -A a=()')
        out.append('a[%s]=v' % spelling)
        out.append('for k in "${!a[@]}"; do printf \'%s\\0\' "$k"; done')
    return '\n'.join(out) + '\n'


def _b2_lexer_survivors(cells):
    """Partition cells by the PRE-EXISTING lexer word-extent carry: a cell is
    end-to-end testable only when psh's lexer keeps `a[SPELLING]=v` ONE word
    (the split family — quoted-section/$-form boundaries inside brackets —
    is test_divergence_lexer_splits_quoted_space_subscript's carry, NOT a
    keying fact). Returns (survivors, excluded)."""
    from psh.lexer import tokenize
    from psh.lexer.token_types import TokenType
    survivors, excluded = [], []
    for spelling in cells:
        try:
            toks = [t for t in tokenize(f'a[{spelling}]=v')
                    if t.type != TokenType.EOF]
        except Exception:
            excluded.append(spelling)
            continue
        (survivors if len(toks) == 1 else excluded).append(spelling)
    return survivors, excluded


def test_procsub_key_render_matrix(tmp_path):
    """B2 condition-3 pin: the generated ruled space keys BYTE-IDENTICALLY
    in psh (both parsers) and bash — batched into ONE run per shell. The
    ENGINE-level instrument covered all 558 comparable cells (ledger,
    B2-STAGE2-matrix-2.txt: 97.9% of 570 incl. the residual family); this
    END-TO-END pin covers the subset deliverable through psh's lexer (the
    split family is the pinned lexer carry) and asserts that subset stays
    large enough to keep the pin meaningful."""
    cells, excluded = _b2_lexer_survivors(list(_b2_cells()))
    # R2-5: floors at the LIVE partition (408 survivors / 150 excluded at
    # round 3) with small headroom — a survivor drop below 400 or an
    # excluded growth past 160 means the lexer carry family GREW (or the
    # partition broke); both must be looked at, not absorbed.
    assert len(cells) >= 400, (len(cells), 'lexer-survivor floor (live 408)')
    assert len(excluded) <= 160, (len(excluded), 'carry family grew? (live 150)')
    script = tmp_path / 'matrix.sh'
    script.write_text(_b2_key_script(cells))
    b = run_bash([str(script)], cwd=PSH_ROOT, timeout=120)
    rd = run_psh([str(script)], cwd=PSH_ROOT, timeout=240)
    comb = run_psh(['--parser', 'combinator', str(script)], cwd=PSH_ROOT,
                   timeout=240)
    assert is_comparable(b) and is_comparable(rd) and is_comparable(comb)
    bkeys = b.stdout.split('\0')
    rdkeys = rd.stdout.split('\0')
    combkeys = comb.stdout.split('\0')
    assert len(bkeys) == len(cells) + 1, (len(bkeys), len(cells))
    bad = [(cells[i], bkeys[i], rdkeys[i] if i < len(rdkeys) else None)
           for i in range(len(cells))
           if i >= len(rdkeys) or bkeys[i] != rdkeys[i]]
    assert not bad, f"{len(bad)} rd cells diverge; first 5: {bad[:5]}"
    badc = [(cells[i], bkeys[i], combkeys[i] if i < len(combkeys) else None)
            for i in range(len(cells))
            if i >= len(combkeys) or bkeys[i] != combkeys[i]]
    assert not badc, f"{len(badc)} comb cells diverge; first 5: {badc[:5]}"


def test_divergence_procsub_separated_subshell_residual():
    """B2 residual, subfamily 1 (both sides): a SEPARATED subshell body —
    `<( (echo s) )` — is re-rendered declare-f-style by bash's bimodal `((`
    disambiguation (`( echo s )`, outer spacing partially kept), while psh
    keeps the RAW spelling. GLUED subshells are raw-preserved by bash itself
    (spacing runs and trailing `;` kept byte-for-byte) and psh matches them
    — pinned in the matrix above."""
    cmd = 'declare -A a; a[<( (echo s) )]=v; for k in "${!a[@]}"; do printf "%s" "$k"; done'
    p, b = _both(cmd)
    assert b.stdout == '<( ( echo s ))'          # bash: separated re-render
    assert p.stdout == '<( (echo s) )'           # psh: raw spelling
    assert _psh_comb(cmd).stdout == p.stdout


@pytest.mark.parametrize('body,bash_key', [
    ('if true; then echo x; fi', '<(if true; then\n    echo x;\nfi)'),
    ('for i in 1 2; do echo x; done', '<(for i in 1 2;\ndo\n    echo x;\ndone)'),
    ('while false; do :; done', '<(while false; do\n    :;\ndone)'),
    ('case x in y) echo n;; esac', '<(case x in y)\n        echo n\n    ;;\nesac)'),
])
def test_divergence_procsub_compound_render_residual(body, bash_key):
    """B2 residual, subfamily 2 (condition-4 both-sides pins): COMPOUND
    bodies — bash embeds its printer's MULTILINE byte-layout (4-space
    indent, per-construct breaks, the first `case` pattern kept on the
    `case x in` line — bash 5.3.15's layout, empirical; the 5.2 printer broke
    after a trailing space and put the pattern on its own line — and the
    expanded-empty `$i` leaving `echo ;`); psh keeps the RAW spelling (the
    declared normalization residual — HIGH-4 is closed WITH this residual)."""
    cmd = ('declare -A a; a[<(%s)]=v; '
           'for k in "${!a[@]}"; do printf "%%s" "$k"; done' % body)
    p, b = _both(cmd)
    assert b.stdout == bash_key, (body, b.stdout)
    assert p.stdout == '<(' + body + ')', (body, p.stdout)   # psh: raw
    assert _psh_comb(cmd).stdout == p.stdout


def test_divergence_procsub_compound_dollar_body_lexer_blocked():
    """B2 residual x lexer carry: the PROBED `for` shape carried `$i`, whose
    `$i;` boundary inside the brackets trips the PRE-EXISTING lexer
    word-split (test_divergence_lexer_splits_quoted_space_subscript family)
    BEFORE the keying engine can apply the raw-spelling residual — psh
    parse-errors and stores nothing, while bash keys its multiline render
    with the expanded-empty `$i` leaving `echo ;`. Both sides pinned."""
    cmd = ('declare -A a; a[<(for i in 1 2; do echo $i; done)]=v; '
           'for k in "${!a[@]}"; do printf "%s" "$k"; done')
    p, b = _both(cmd)
    assert b.stdout == '<(for i in 1 2;\ndo\n    echo ;\ndone)'
    assert p.returncode != 0 and p.stdout == ''
    pc = _psh_comb(cmd)
    assert pc.returncode != 0 and pc.stdout == ''


# --- Round 3 (B1): three-tier procsub keying --------------------------------

_B1_BODIES = {
    'psub_if': '<(if)', 'psub_out': '>(if)', 'psub_while': '<(while)',
    'psub_valid': '<(cat q)', 'psub_var': '<(if $y)', 'psub_unclosed': '<(',
    'cmdsub_if': '$(if)',
}
_B1_ROUTES = {
    'testv_present':  "declare -A a; y=Q\na['{q}']=v\ntest -v 'a[{q}]'; echo rc=$?\n",
    'testv_absent':   "declare -A a; y=Q; a[x]=v\ntest -v 'a[{q}]'; echo rc=$?\n",
    'unset_present':  "declare -A a; y=Q\na['{q}']=v; a[x]=2\nunset -v 'a[{q}]'; echo rc=$?\ndeclare -p a\n",
    'unset_absent':   "declare -A a; y=Q; a[x]=2\nunset -v 'a[{q}]'; echo rc=$?\ndeclare -p a\n",
    'indirection':    "declare -A a; y=Q\na['{q}']=v\nk='a[{q}]'\necho \"read=${{!k}}\"; echo rc=$?\n",
    'nameref':        "declare -A a; y=Q\na['{q}']=v\ndeclare -n r='a[{q}]'\necho \"read=$r\"; echo rc=$?\n",
    'printf_v':       "declare -A a; y=Q\nprintf -v 'a[{q}]' pv; echo rc=$?\ndeclare -p a\n",
    'read_into':      "declare -A a; y=Q\nread -r 'a[{q}]' <<< rv; echo rc=$?\ndeclare -p a\n",
    'let_arith':      "declare -A a; y=Q\nlet 'a[{q}]=7'; echo rc=$?\ndeclare -p a\n",
    'dparen':         "declare -A a; y=Q\n(( a[{q}]=8 )); echo rc=$?\ndeclare -p a\n",
}
# Cells where psh deliberately differs — each attributed to a DECLARED family.
_B1_DIVERGENT_CELLS = {
    # The MEASURED non-equal cell set (artifact B1R3-matrix-FINAL.txt — the
    # post-round-3 authority; two earlier table drafts were built from stale
    # artifacts, recorded in the slot ledger). Every INVALID-cmdsub word
    # route diverges the SAME way: psh ATTEMPTS the substitution (deferred
    # execution — bash's mechanism) but keeps its continue-on-inner-error
    # model where bash aborts the frame — the declared I3/s2 family that
    # slot 2.4 owns. indirection/nameref moved INTO this family from an
    # ACCIDENTAL pre-round-3 match (the old typed abort mimicked bash's
    # abort observables by a different mechanism) — declared per C3.
    ('testv_present', 'cmdsub_if'):  'I3/s2 frame fatality',
    ('testv_absent', 'cmdsub_if'):   'I3/s2 frame fatality',
    ('unset_present', 'cmdsub_if'):  'I3/s2 fatality + assoc enumeration order',
    ('unset_absent', 'cmdsub_if'):   'I3/s2 fatality (rc-line presence)',
    ('indirection', 'cmdsub_if'):    'I3/s2 frame fatality (was accidental match)',
    ('nameref', 'cmdsub_if'):        'I3/s2 frame fatality (was accidental match)',
    ('printf_v', 'cmdsub_if'):       'I3/s2 frame fatality',
    ('read_into', 'cmdsub_if'):      'I3/s2 frame fatality',
    ('let_arith', 'cmdsub_if'):      'I3/s2 frame fatality',
    ('dparen', 'psub_unclosed'):     'bash arith-extent wants ] (rc 2); psh keys the literal frame',
    ('dparen', 'psub_var'):          'PRE-EXISTING (( ))-extent parse failure on $var-before-) '
                                     '(base==tip byte-identical rc 2; lexer-extent family)',
}


def test_procsub_runtime_route_matrix(tmp_path):
    """B1 (round 3): the per-route x validity matrix, pinned. bash NEVER
    parses a procsub body at keying time — invalid/unclosed spellings key
    literally, $-forms expand inside even invalid frames, and runtime
    strings are never re-rendered. Every cell runs INDIVIDUALLY (the 2.2
    batching lesson); rc+stdout must equal bash except the declared cells
    (each attributed to its family)."""
    unexpected = []
    for bname, body in _B1_BODIES.items():
        for rname, template in _B1_ROUTES.items():
            script = tmp_path / f'{rname}__{bname}.sh'
            script.write_text(template.format(q=body))
            b = run_bash([str(script)], cwd=PSH_ROOT, timeout=15)
            rd = run_psh([str(script)], cwd=PSH_ROOT, timeout=15)
            comb = run_psh(['--parser', 'combinator', str(script)],
                           cwd=PSH_ROOT, timeout=15)
            assert is_comparable(b) and is_comparable(rd) and is_comparable(comb)
            assert (rd.returncode, rd.stdout) == (comb.returncode, comb.stdout), \
                (rname, bname, rd, comb)
            equal = (rd.returncode, rd.stdout) == (b.returncode, b.stdout)
            declared = (rname, bname) in _B1_DIVERGENT_CELLS
            if equal == declared:
                unexpected.append((rname, bname, 'now-equal' if equal else 'diverged',
                                   b, rd))
    assert not unexpected, unexpected[:4]


def test_render_tiers():
    """C1/C2 (round 3): bash's THREE render tiers, pinned. Source write AND
    source read re-render covered procsub spellings; ARITH-held subscripts
    keep the spelling RAW (load-bearing: the parse-time splice must never
    reach arithmetic regions); RUNTIME strings are never rendered."""
    # tier a: source read finds a tidy-written key through a spaced spelling
    # and vice versa (both parsers).
    for cmd in ('declare -A a; a[<(cat q)]=v; echo "read=${a[<( cat  q )]}"',
                'declare -A a; a[<( cat  q )]=v; echo "read=${a[<(cat q)]}"'):
        p, b = _both(cmd)
        assert p.stdout == b.stdout == 'read=v\n', (cmd, p, b)
        assert _psh_comb(cmd).stdout == b.stdout
    # tier b: arith keeps the spelling raw, spaces and all.
    cmd = 'declare -A a; (( a[<( cat  q )]=8 )); declare -p a'
    p, b = _both(cmd)
    assert p.stdout == b.stdout and '"<( cat  q )"' in b.stdout
    assert _psh_comb(cmd).stdout == b.stdout
    # tier c: a runtime string is NOT rendered — the spaced spelling does not
    # address the tidy-written key (bash no-ops; the key survives).
    cmd = "declare -A a; a[<(cat q)]=v; unset -v 'a[<( cat  q )]'; declare -p a"
    p, b = _both(cmd)
    assert p.stdout == b.stdout and '"<(cat q)"' in b.stdout
    assert _psh_comb(cmd).stdout == b.stdout


_UNLEXABLE_ROUTE_ROWS = [
    # (route, script, disposition) — the unclosed-QUOTE junk arg `a["]` per
    # route, MEASURED post-R4-2 (the whole-string extent rule reclassified
    # several routes toward bash; probe battery in the slot ledger) and
    # re-measured against bash 5.3.15 (Wave 0.1): only let_arith moved, on
    # the bash side — see the declared_typed branch.
    # match = rc+stdout equal bash; rendering_only = equal modulo the
    # documented empty-assoc declare -p residual; declared = pinned
    # divergence (bash per-builtin rc/wording vs psh's uniform classes).
    ('testv', 'declare -A a; a[x]=1; test -v \'a["]\'; echo rc=$?', 'match'),
    ('unset', 'declare -A a; a[x]=1; unset -v \'a["]\'; echo rc=$?; declare -p a', 'match'),
    ('indirection', 'declare -A a; a[x]=1; k=\'a["]\'; echo "read=${!k}"; echo rc=$?', 'match'),
    ('dparen', 'declare -A a; (( a["]=8 )); echo rc=$?; declare -p a', 'match'),
    ('nameref', 'declare -A a; a[x]=1; declare -n r=\'a["]\'; echo "read=$r"; echo rc=$?', 'match_quiet_stderr'),
    ('read_into', 'declare -A a; read -r \'a["]\' <<< rv; echo rc=$?; declare -p a', 'rendering_only'),
    ('printf_v', 'declare -A a; printf -v \'a["]\' pv; echo rc=$?; declare -p a', 'declared_rc'),
    ('let_arith', 'declare -A a; let \'a["]=7\'; echo rc=$?; declare -p a', 'declared_typed'),
]


@pytest.mark.parametrize('route,cmd,disposition', _UNLEXABLE_ROUTE_ROWS,
                         ids=[r[0] for r in _UNLEXABLE_ROUTE_ROWS])
def test_unlexable_subscript_route_audit(route, cmd, disposition):
    p, b = _both(cmd)
    pc = _psh_comb(cmd)
    assert (p.returncode, p.stdout) == (pc.returncode, pc.stdout)
    if disposition in ('match', 'match_quiet_stderr'):
        assert (p.returncode, p.stdout) == (b.returncode, b.stdout), (route, p, b)
        # match_quiet_stderr: psh's declare -n path is silent where bash
        # warns (wording-family footnote; observables equal).
    elif disposition == 'rendering_only':
        assert p.returncode == b.returncode
        assert p.stdout.replace('declare -A a=()', 'declare -A a') == b.stdout
        assert 'not a valid identifier' in p.stderr
    elif disposition == 'declared_rc':
        # bash: printf rc-in-$? 2 (usage); psh: 1 via the dispatch channel —
        # same identifier wording, line continues in both.
        assert 'rc=2' in b.stdout and 'rc=1' in p.stdout
        assert 'not a valid identifier' in b.stderr
        assert 'not a valid identifier' in p.stderr
    else:  # declared_typed — the arith route still surfaces the typed class
        # bash 5.3.15 (empirical): `let` DROPS the invalid-identifier
        # assignment with a diagnostic, stores nothing, the line continues,
        # and let's status is the truth of the expression VALUE (`=7` ->
        # rc=0; `let 'a["]=0'` -> rc=1). The 5.2 oracle pinned `rc=1` from
        # the let itself. psh keeps its typed abort of the line (rc 1,
        # nothing printed, `bad array subscript`) — the divergence WIDENED
        # on the oracle side; psh's disposition is unchanged.
        assert b.returncode == 0 and 'rc=0' in b.stdout, (route, b)
        assert 'declare -A a\n' in b.stdout, (route, b)      # nothing stored
        assert 'not a valid identifier' in b.stderr, (route, b)
        assert p.returncode == 1 and p.stdout == ''
        assert 'bad array subscript' in p.stderr


def test_empty_assoc_key_set_route_rejected():
    """(R4-3 note: the FULL route x spelling family now lives in
    test_empty_assoc_key_route_matrix below; these two original legs stay
    as the red-on-base anchor rows.)

    Round-3 plan-C-radius fix (base-verified pre-existing gap): the
    set-var route (printf -v / read) rejected nothing for an
    (expanded-)EMPTY assoc key and stored [""] where bash reports
    "NAME[RAW]: bad array subscript" (rc 1, line continues). Now rejected
    like the source-write path; psh's stderr adds its builtin-name prefix
    (wording family) and its empty-assoc declare -p renders `a=()`
    (documented rendering residual) — rc and no-key-stored are pinned."""
    for cmd in ("declare -A a; e=; printf -v 'a[$e]' pv; echo rc=$?; declare -p a",
                "declare -A a; e=; read -r 'a[$e]' <<< rv; echo rc=$?; declare -p a"):
        p, b = _both(cmd)
        assert 'rc=1' in b.stdout and '[""]' not in b.stdout
        assert 'bad array subscript' in b.stderr
        assert 'rc=1' in p.stdout and '[""]' not in p.stdout, (cmd, p)
        assert 'bad array subscript' in p.stderr
        assert _psh_comb(cmd).stdout == p.stdout


def test_divergence_assignment_prefix_element_split():
    """R2-7 (round-2 verifier evidence, base-identical PRE-EXISTING carry):
    an element assignment inside an ASSIGNMENT-PREFIX run — `foo=1
    bar[0]=2` — is a pure prefix statement in bash (rc 0, bar created);
    psh splits it and runs `bar[0]=2` as a command (rc-in-$? 127, no
    array). Both parsers, stdin channel (the probed one)."""
    script = 'foo=1 bar[0]=2; echo rc=$?; declare -p bar\n'
    b = run_bash([], stdin_data=script, cwd=PSH_ROOT, timeout=15)
    rd = run_psh([], stdin_data=script, cwd=PSH_ROOT, timeout=15)
    comb = run_psh(['--parser', 'combinator'], stdin_data=script,
                   cwd=PSH_ROOT, timeout=15)
    assert is_comparable(b) and is_comparable(rd) and is_comparable(comb)
    assert b.stdout == 'rc=0\ndeclare -a bar=([0]="2")\n'
    assert 'rc=127' in rd.stdout and 'command not found' in rd.stderr
    assert (rd.returncode, rd.stdout) == (comb.returncode, comb.stdout)


_HEADSCAN_PRE = ['a', 'a\\', 'A_1']
_HEADSCAN_SUB = ['k', '"]"', '\\]', 'b[i]', 'x=1', 'x+=y', ']]']
_HEADSCAN_OPS = ['=v', '+=v', 'x=v', ']=v', '=""']


def test_generated_head_scan_battery(tmp_path):
    """B2 (round 3): the GENERATED head-scan space — every PRE x SUB x OPS
    head compared rc+stdout+stderr-presence to bash, INDIVIDUAL runs (the
    batching desync lesson), both parsers lockstep. This battery supersedes
    the two hand enumerations that each came up short; the space includes
    all seven round-2-verifier families (escaped-bracket heads, doubled
    brackets, trailing junk after a well-formed head, underscore names).
    Known-divergent cells are attributed by the SAME families already
    pinned in this file (lexer word-split carry; empty-assoc declare -p
    rendering residual is avoided by comparing stdout only when bash's
    declare output is non-empty-array-form)."""
    declared_familes_hit = []
    unexpected = []
    for pre in _HEADSCAN_PRE:
        for sub in _HEADSCAN_SUB:
            for ops in _HEADSCAN_OPS:
                head = f'declare -A a; {pre}[{sub}]{ops}'
                script = tmp_path / 'cell.sh'
                script.write_text(head + '; echo rc=$?; declare -p a 2>&1\n')
                b = run_bash([str(script)], cwd=PSH_ROOT, timeout=15)
                rd = run_psh([str(script)], cwd=PSH_ROOT, timeout=15)
                comb = run_psh(['--parser', 'combinator', str(script)],
                               cwd=PSH_ROOT, timeout=15)
                assert is_comparable(b) and is_comparable(rd)
                assert is_comparable(comb)
                assert (rd.returncode, rd.stdout) == (comb.returncode,
                                                     comb.stdout), (head, rd, comb)
                cell = (pre, sub, ops)
                if (rd.returncode, rd.stdout) == (b.returncode, b.stdout):
                    continue
                # Attribute divergent cells to the declared families:
                if 'declare -A a\n' in b.stdout and 'declare -A a=()' in rd.stdout \
                        and rd.stdout.replace('declare -A a=()',
                                              'declare -A a') == b.stdout:
                    declared_familes_hit.append((cell, 'empty-assoc declare -p rendering'))
                    continue
                if b.returncode == 2 and 'EOF' in b.stderr:
                    declared_familes_hit.append((cell, 'bash continuation (lexer-unclosed family)'))
                    continue
                unexpected.append((cell, b.returncode, b.stdout, rd.returncode,
                                   rd.stdout, rd.stderr[-120:]))
    assert not unexpected, (len(unexpected), unexpected[:5])


@pytest.mark.parametrize('cmd', [
    # R4-1 family: bash renders a backgrounded statement `<stmt> &`; the `&`
    # separates statements; runtime strings stay raw (tidy spelling = raw).
    'declare -A a; a[<( sleep 0  & )]=v; for k in "${!a[@]}"; do printf "%s" "$k"; done',
    'declare -A a; a[<( echo a &  echo b )]=v; for k in "${!a[@]}"; do printf "%s" "$k"; done',
    'declare -A a; a[<(echo a & echo b &)]=v; for k in "${!a[@]}"; do printf "%s" "$k"; done',
    'declare -A a; a[<(true && echo b &)]=v; for k in "${!a[@]}"; do printf "%s" "$k"; done',
    "declare -A a; a[<(sleep 0 &)]=v; test -v 'a[<(sleep 0 &)]'; echo rc=$?",
    "declare -A a; a[<(sleep 0 &)]=v; unset -v 'a[<(sleep 0 &)]'; declare -p a",
    'declare -A a; a[<((echo s) &)]=v; for k in "${!a[@]}"; do printf "%s" "$k"; done',
])
def test_background_body_family(cmd):
    p, b = _both(cmd)
    assert p.stdout == b.stdout and p.returncode == b.returncode, (cmd, p, b)
    assert _psh_comb(cmd).stdout == b.stdout


def test_headscan_k_close_x_is_command_word():
    """R4-5(c): `a[k]]x=v` — base MIS-KEYED ([k]="]x=v"); tip = bash command
    word (rc-in-$? 127; nothing stored; rendering-residual-aware asserts)."""
    cmd = 'declare -A a; a[k]]x=v; echo rc=$?; declare -p a'
    p, b = _both(cmd)
    assert 'rc=127' in b.stdout and 'command not found' in b.stderr
    assert 'rc=127' in p.stdout and 'command not found' in p.stderr
    assert '[k]' not in p.stdout and '[k]' not in b.stdout
    assert 'rc=127' in _psh_comb(cmd).stdout


def test_divergence_A1_doubled_open_unclosed_family():
    """R4-5(c): `A_1[[k]=v` (underscore name + unclosed inner bracket) — base
    MIS-KEYED ["[k"]; tip refuses as a command word (rc-in-$? 127); bash
    treats the word as INCOMPLETE INPUT rc 2 (the lexer-continuation family,
    same as test_divergence_doubled_open_unclosed_family)."""
    cmd = 'declare -A A_1; A_1[[k]=v; echo rc=$?; declare -p A_1'
    p, b = _both(cmd)
    assert b.returncode == 2 and 'EOF' in b.stderr
    assert 'rc=127' in p.stdout and 'command not found' in p.stderr
    assert '"[k"' not in p.stdout
    assert 'rc=127' in _psh_comb(cmd).stdout


def test_divergence_pipe_amp_body_render():
    """R4-5(d): bash CANONICALIZES `|&` to its expansion `2>&1 |` in the
    key-render; psh keeps the raw spelling (|& is outside the covered
    subset — the declared normalization residual). Both sides pinned."""
    cmd = ('declare -A a; a[<( echo a |&  wc -l )]=v; '
           'for k in "${!a[@]}"; do printf "%s" "$k"; done')
    p, b = _both(cmd)
    assert b.stdout == '<(echo a 2>&1 | wc -l)'
    assert p.stdout == '<( echo a |&  wc -l )'
    assert _psh_comb(cmd).stdout == p.stdout


def test_divergence_comment_in_body():
    """R4-5(d): a `#` comment inside a procsub body comments out the closing
    `)` for bash (rc 2, wants more input — its extent honors comments); psh's
    scanner treats `#` literally and keys the spelling (lexer/extent family;
    base ran the procsub, worse). Both sides pinned."""
    cmd = 'declare -A a; a[<(echo hi # c)]=v; echo rc=$?; declare -p a'
    p, b = _both(cmd)
    assert b.returncode == 2 and 'EOF' in b.stderr
    assert p.returncode == 0 and '"<(echo hi # c)"' in p.stdout
    assert _psh_comb(cmd).stdout == p.stdout


_R43_ROWS = [
    # (id, cmd, disposition) — R4-3 route x spelling matrix
    # (R43-emptykey-matrix.txt; the earlier printf/read x a[$e] pin is
    # superseded by this full family).
    ('printf_raw', "declare -A a; printf -v 'a[]' pv; echo rc=$?; declare -p a", 'declared'),
    ('printf_expanded', "declare -A a; e=''; printf -v 'a[$e]' pv; echo rc=$?; declare -p a", 'declared'),
    ('read_raw', "declare -A a; read -r 'a[]' <<< rv; echo rc=$?; declare -p a", 'declared'),
    ('read_expanded', "declare -A a; e=''; read -r 'a[$e]' <<< rv; echo rc=$?; declare -p a", 'declared'),
    ('assign_default_raw', 'declare -A a; : "${a[]:=xx}"; echo rc=$?; declare -p a', 'match'),
    ('assign_default_expanded', 'declare -A a; e=\'\'; : "${a[$e]:=xx}"; echo rc=$?; declare -p a', 'match'),
    ('nameref_raw', "declare -A a; declare -n r='a[]'; r=nv; echo rc=$?; declare -p a", 'rendering_only'),
    ('nameref_expanded', "declare -A a; e=''; declare -n r='a[$e]'; r=nv; echo rc=$?; declare -p a", 'declared_fatality'),
    ('let_raw', "declare -A a; let 'a[]=5'; echo rc=$?; declare -p a", 'arith_family'),
    ('dparen_expanded', "declare -A a; e=''; (( a[$e]=6 )); echo rc=$?; declare -p a", 'arith_family'),
]


@pytest.mark.parametrize('rid,cmd,disposition', _R43_ROWS,
                         ids=[r[0] for r in _R43_ROWS])
def test_empty_assoc_key_route_matrix(rid, cmd, disposition):
    """R4-3: the empty-assoc-key faces, per route x spelling. MATCH rows
    (the `:=` expansion faces — bash's discard-line bad-substitution /
    bad-array-subscript classes, now implemented); DECLARED rows: builtin
    wording/rc faces (bash per-builtin: printf raw rc-in-$? 2
    not-valid-identifier, expanded rc 1; psh uniform rc 1 bad-array-
    subscript — joins the declared builtin-route family) and the nameref
    expanded FATALITY face (bash aborts rc 1; psh continues rc-in-$? 1);
    rendering_only = equal modulo the documented empty-assoc declare -p
    residual; arith_family = the PRE-EXISTING declared empty-arith
    divergence (bash warns + continues rc-in-$? 0; psh rc 1). In EVERY row
    psh stores NOTHING (the companion fix) and rd == comb."""
    p, b = _both(cmd)
    pc = _psh_comb(cmd)
    assert (p.returncode, p.stdout) == (pc.returncode, pc.stdout)
    assert '[""]' not in p.stdout          # never a silent empty-key store
    assert '[""]' not in b.stdout
    if disposition == 'match':
        assert (p.returncode, p.stdout) == (b.returncode, b.stdout), (rid, p, b)
    elif disposition == 'rendering_only':
        assert p.returncode == b.returncode
        assert p.stdout.replace('declare -A a=()', 'declare -A a') == b.stdout
        assert p.stderr.strip() and b.stderr.strip()
    elif disposition == 'declared_fatality':
        assert b.returncode == 1 and b.stdout == ''
        assert 'rc=1' in p.stdout and 'bad array subscript' in p.stderr
    elif disposition == 'arith_family':
        assert 'rc=0' in b.stdout and b.stderr.strip()   # bash warns, continues
        assert 'rc=1' in p.stdout                        # psh: B#3 family
    else:  # declared builtin faces
        assert b.stderr.strip() and p.stderr.strip()
        assert 'rc=1' in p.stdout
        assert b.stdout.startswith('rc=')


@pytest.mark.parametrize('cmd', [
    # R4-2: the whole-string extent rule — a malformed runtime-string arg
    # (`a[]]`, extent closes early) must NEVER alias the stored `]` key.
    # THE DESTRUCTIVE ROW: unset refuses loudly, key preserved (bash).
    'declare -A a; a["]"]=1; a[x]=2; unset -v \'a[]]\'; echo rc=$?; declare -p a',
    # Sibling interplay: -v reports unset while `]` IS set.
    'declare -A a; a["]"]=1; test -v \'a[]]\'; echo rc=$?',
    'declare -A a; a["]"]=1; [[ -v \'a[]]\' ]]; echo rc=$?',
    # Valid-arg control: the well-formed spelling still addresses the key.
    'declare -A a; a["]"]=1; a[x]=2; unset -v \'a["]"]\'; echo rc=$?; declare -p a',
    # Probe-first indirection/nameref legs (both matched bash outright —
    # `invalid variable name` classes; no new divergence to declare).
    'declare -A a; a["]"]=1; k=\'a[]]\'; echo "read=${!k}"; echo rc=$?',
    'declare -A a; a["]"]=1; declare -n r=\'a[]]\'; echo "read=$r"; echo rc=$?',
])
def test_runtime_arg_whole_string_extent_rule(cmd):
    """R4-2 (round 4): split_subscript's shape rule is WHOLE-STRING — the
    quote-aware extent of the first `[` must close exactly at the final `]`.
    All six legs equal bash on rc+stdout (both parsers)."""
    p, b = _both(cmd)
    assert (p.returncode, p.stdout) == (b.returncode, b.stdout), (cmd, p, b)
    pc = _psh_comb(cmd)
    assert (pc.returncode, pc.stdout) == (p.returncode, p.stdout)


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
    # --- SUBJECT SHAPE: the axis that decides whether a row can detect this
    # defect at all (with a plain `a b` subject in unquoted outer context the
    # space-join is undone by re-splitting, reproducing bash by accident) ---
    ('unset x; set -- "a 1" "b 2"; printf "<%s>" ${x:-"$@"}', '<a 1><b 2>'),
    ('unset x; set -- "" b; printf "<%s>" "${x:-"$@"}"', '<><b>'),
    ('unset x; set -- "a	z" b; printf "<%s>" ${x:-"$@"}', '<a\tz><b>'),
    ('unset x; set -- "a*" b; printf "<%s>" "${x:-"$@"}"', '<a*><b>'),
    # --- non-colon twins and the alternate family -------------------------
    ('unset x; set -- "a 1" b; printf "<%s>" "${x-"$@"}"', '<a 1><b>'),
    ('x=set; set -- "a 1" b; printf "<%s>" "${x+"$@"}"', '<a 1><b>'),
    # --- POSITIONAL COUNT, including the empty-$@ boundary rule ------------
    ('unset x; set -- a; printf "<%s>" "${x:-"$@"}"', '<a>'),
    ('unset x; set -- a b c; printf "<%s>" "${x:-"$@"}"', '<a><b><c>'),
    ('unset x; set --; printf "<%s>|" pre"${x:-"$@"}"post', '<prepost>|'),
    # --- nested and mixed operands ----------------------------------------
    ('unset x y; set -- "a 1" b; printf "<%s>" "${x:-${y:-"$@"}}"', '<a 1><b>'),
    ('unset x; set -- a b; printf "<%s>" "${x:-pre"$@"post}"', '<prea><bpost>'),
    # --- array views: the [@]/[*] joiner must not touch a TRIGGERED operand
    ('unset a; set -- "a 1" b; printf "<%s>" "${a[@]:-"$@"}"', '<a 1><b>'),
    ('unset a; set -- "a 1" b; printf "<%s>" "${a[*]:-"$@"}"', '<a 1><b>'),
    # the pinned single-field preserve, both quote states (in QUOTED outer
    # context the operand's single quotes are LITERAL — DQ rules — so they
    # appear in the output; unquoted they are removed. One field either way.)
    ("unset a; printf \"<%s>\" \"${a[*]:-'p q'}\"", "<'p q'>"),
    ("unset a; printf \"<%s>\" ${a[*]:-'p q'}", '<p q>'),
    # --- IFS: field boundaries are not made of IFS -------------------------
    ('unset x; IFS=:; set -- "a 1" b; printf "<%s>" "${x:-"$@"}"', '<a 1><b>'),
    ('unset x; IFS=; set -- "a 1" b; printf "<%s>" ${x:-"$@"}', '<a 1><b>'),
])
def test_operand_at_preserves_fields(cmd, bash_out):
    """A ``"$@"`` inside a value-operand word KEEPS its fields (HIGH-6).

    FLIPPED in remediation slot 3.3 from ``test_divergence_operand_at_flattens``,
    which pinned the divergence: the operand IR carried per-segment quote
    protection but no FIELD dimension, so multiple positionals collapsed into
    one space-joined field. The operand result is now a field vector
    (``psh/expansion/operands.py``: ``OperandValue``) and the boundaries reach
    the Word walker's splice algebra intact.

    Rows are AGREEMENT-FORM (psh == bash) with the bash side ALSO pinned to a
    literal, so a shared regression in both shells cannot pass unnoticed.

    Row selection: a ``set -- a b`` subject in UNQUOTED outer context cannot
    detect this defect, so the shape/count/IFS rows carry the detection
    weight. A BARE ``$@`` is deliberately absent — it is a different,
    successor-owned mechanism (``test_operand_bare_at_ifs_divergence``).
    """
    p, b = _psh(cmd), _bash(cmd)
    assert b.stdout == bash_out, f"bash oracle moved: {b.stdout!r}"
    assert p.stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    # signature cell
    'unset x; set -- a b; printf "<%s>" "${x:-"$@"}"',
    # subject shape: the row that can actually detect the flatten
    'unset x; set -- "a 1" "b 2"; printf "<%s>" ${x:-"$@"}',
    # ZERO-POSITIONAL pair — the empty-field representation, both faces
    'n() { echo "n=$#"; }; unset x; set --; n ${x:-"$@"}',
    'n() { echo "n=$#"; }; unset x; set --; n "${x:-"$@"}"',
    # array VIEW as operand content (round-1 B2 family)
    'unset x; a=("m n" o); printf "<%s>" "${x:-"${a[@]}"}"',
    # alternate face + nesting
    'x=S; set -- "a 1" b; printf "<%s>" "${x:+"$@"}"',
    'unset x y; set -- "a 1" b; printf "<%s>" "${x:-${y:-"$@"}}"',
])
def test_operand_at_preserves_fields_combinator(cmd):
    """The COMBINATOR parser leg for the flipped pin.

    Round-1 blocker B3: the ledger claimed "the existing pin runs `_psh_comb`"
    — it did not; the base pin body ran `_psh`/`_bash` only, and neither the
    flipped pin nor the battery referenced the combinator at all. The claim
    was inherited from the brief and repeated without derivation. This test is
    the claim made TRUE rather than retracted, since the parser axis is worth
    covering: the fix lives in expansion, so both parsers must agree with bash.

    Kept as a separate function rather than folded into the equality pin so a
    combinator-only regression names itself in the failure output.
    """
    b = _bash(cmd)
    assert _psh(cmd).stdout == b.stdout
    assert _psh_comb(cmd).stdout == b.stdout


@pytest.mark.parametrize('cmd,bash_out,psh_out', [
    ('unset x; IFS=X; set -- aXq b; printf "<%s>" ${x:-$@}',
     '<aXq b>', '<a><q b>'),
    ('unset x; IFS=XY; set -- aXq b; printf "<%s>" ${x:-$@}',
     '<aXq b>', '<a><q b>'),
    ('unset x; IFS="X "; set -- aXq b; printf "<%s>" ${x:-$@}',
     '<aXq><b>', '<a><q><b>'),
])
def test_operand_bare_at_ifs_divergence(cmd, bash_out, psh_out):
    """DOCUMENTED PRE-EXISTING DIVERGENCE (successor-owned): a BARE ``$@``
    inside a value operand under a NON-DEFAULT IFS.

    bash protects the parameter CONTENT from splitting while the separator
    joining the fields stays split-eligible, so ``aXq`` survives intact under
    ``IFS=X`` even though ``X`` is an IFS character. Neither a
    join-then-split model nor a splice-fields model reproduces all three rows,
    so slot 3.3 shipped no guess: it preserves the pre-field behaviour here
    EXACTLY (measured identical at base d0f7d929) and owns only the PROTECTED
    ``"$@"`` form.

    Pinned BOTH SIDES in the divergent direction — flipping it is a ruling,
    not a drive-by. The successor that models the rule flips it to equality.
    """
    p, b = _psh(cmd), _bash(cmd)
    assert b.stdout == bash_out, f"bash oracle moved: {b.stdout!r}"
    assert p.stdout == psh_out, f"psh moved: {p.stdout!r}"


@pytest.mark.parametrize('cmd,bash_out,psh_out', [
    ('unset x; set -- a b; case "a b" in ${x:-"$@"}) echo HIT;; *) echo MISS;; esac',
     'MISS\n', 'HIT\n'),
    ('unset x; set -- a b; case a in ${x:-"$@"}) echo HIT;; *) echo MISS;; esac',
     'HIT\n', 'MISS\n'),
])
def test_case_pattern_multifield_operand_divergence(cmd, bash_out, psh_out):
    """DOCUMENTED PRE-EXISTING DIVERGENCE (successor-owned): a multi-field
    value operand used as a ``case`` PATTERN.

    bash matches the FIRST FIELD only; psh joins the fields into one pattern.
    Slot 3.3 made this projection EXPLICIT
    (``ExpansionManager.expand_word_as_pattern``) WITHOUT changing behaviour —
    the join is exactly what base did — so these rows are a declared exclusion
    from that slot's "matrix matches bash" claim, not a regression. Both
    directions pinned so the successor's flip is visible.
    """
    p, b = _psh(cmd), _bash(cmd)
    assert b.stdout == bash_out, f"bash oracle moved: {b.stdout!r}"
    assert p.stdout == psh_out, f"psh moved: {p.stdout!r}"
