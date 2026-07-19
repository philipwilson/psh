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
import subprocess
import sys
from pathlib import Path

import pytest
from conformance_framework import ConformanceTest
from shell_oracle import resolve_bash

PSH_ROOT = Path(__file__).resolve().parents[3]

# Shell-name diagnostic prefix (`psh: line 1: ` / `bash: line 1: `): stripped
# where a row compares MESSAGE BODIES (the framework compares raw stderr, and
# the argv0 prefix legitimately differs between the shells).
_PREFIX_RE = re.compile(r'^[^:\n]*: (line \d+: )?', re.MULTILINE)


def _strip_prefix(stderr: str) -> str:
    return _PREFIX_RE.sub('', stderr)


def _run(shell_argv, cmd):
    return subprocess.run(shell_argv + ['-c', cmd], capture_output=True,
                          text=True, cwd=PSH_ROOT, timeout=15)


def _psh(cmd):
    return _run([sys.executable, '-m', 'psh'], cmd)


def _bash(cmd):
    return _run([resolve_bash().path], cmd)


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


def test_divergence_quote_blind_extent_in_assignment_word():
    """K1 (routed residual, lexer extent — NOT keying): `a["a]b"]=1` — bash's
    assignment-word scan respects quotes around `]`; psh's tracker stops at
    the first `]`. Keying itself is consistent: both shells store ONE
    element."""
    cmd = 'declare -A a; a["a]b"]=1; declare -p a'
    p, b = _psh(cmd), _bash(cmd)
    assert '["a]b"]="1"' in b.stdout
    assert p.stdout != b.stdout  # flips when the lexer extent fix lands


def test_divergence_procsub_in_subscript_read_time():
    """S3-carry (routed residual, parser scan — NOT keying): bash validates a
    `<(...)`-spelled procsub inside a subscript at READ time (`a[<(if)]=1`
    rejects the whole buffer, dead branches included) while treating
    `1<(2)` as arithmetic; a VALID `<(echo hi)` carries to a RUNTIME arith
    error. psh currently defers the invalid spelling to runtime."""
    dead = 'true || a[<(if)]=1; echo ran'
    b = _bash(dead)
    assert 'ran' not in b.stdout and b.returncode != 0  # bash: read-time
    p = _psh(dead)
    assert 'ran' in p.stdout  # psh: deferred (routed to the S3/S4 scan family)
    # Both shells treat `1<(2)` as arithmetic, not a procsub:
    arith = 'a[1<(2)]=x; declare -p a'
    pb, bb = _psh(arith), _bash(arith)
    assert '[1]="x"' in bb.stdout and '[1]="x"' in pb.stdout


def test_divergence_sq_inside_dq_subscript():
    """S3-verify carry (routed residual, parser dq-context scan): single
    quotes inside a DOUBLE-QUOTED `${h['...']}` — with a cmdsub spelling
    bash defers to runtime (arith error on the undeclared name) while psh
    rejects at parse time. The plain spelling works identically."""
    ok = "declare -A h; h[\"k\"]=v; echo \"${h['k']}\""
    p, b = _psh(ok), _bash(ok)
    assert p.stdout == b.stdout == 'v\n'
    bad = 'echo "${h[\'$(if)\']}"'
    pb, bb = _psh(bad), _bash(bad)
    assert bb.returncode == 1 and 'syntax error' in bb.stderr  # runtime arith
    assert pb.returncode != 0  # psh: parse-time (earlier stage; declared)


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
