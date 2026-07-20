"""Unit pins for the ONE subscript authority (campaign W2, r21 A-family).

``SubscriptEvaluator`` (psh/expansion/subscript.py) is the single interpreter
for array subscripts: target kind FIRST (decided by the caller from the
DECLARED variable), then one interpretation per kind. These tests pin the
service surface directly plus the routed behavior of every consumer site
(read, write, is-set, unset, test -v, arithmetic, initializer).
"""
import pytest

from psh.expansion.subscript import SubscriptUse, TargetKind


@pytest.fixture
def subscript(captured_shell):
    return captured_shell.expansion_manager.subscript


class TestWordFromText:
    """The re-lex bridge: raw subscript source -> ONE Word."""

    def test_composite_quoting_concatenates(self, subscript):
        word = subscript.word_from_text("'a''b'")
        assert [p.text for p in word.parts] == ['a', 'b']

    def test_unquoted_gap_preserved(self, subscript):
        word = subscript.word_from_text('a b')
        assert ''.join(p.text for p in word.parts) == 'a b'

    def test_leading_and_trailing_space_preserved(self, subscript):
        word = subscript.word_from_text(' foo ')
        assert ''.join(p.text for p in word.parts) == ' foo '

    def test_empty_text_single_literal(self, subscript):
        word = subscript.word_from_text('')
        assert len(word.parts) == 1 and word.parts[0].text == ''

    def test_ansi_c_decoded_by_lexer(self, subscript):
        word = subscript.word_from_text("$'x\\ty'")
        assert word.parts[0].text == 'x\ty'


class TestAssociativeKey:
    """One word/quote expansion under assignment-value semantics."""

    @pytest.mark.parametrize('raw,key', [
        ("'a''b'", 'ab'),
        ('"a"' + "'b'", 'ab'),
        ("a$'b'", 'ab'),
        ("'$k'", '$k'),          # single quotes suppress
        ('a b', 'a b'),          # unquoted spaces preserved, no splitting
        (' foo ', ' foo '),      # never stripped
        ('a]b', 'a]b'),
        ("$'x\\ty'", 'x\ty'),    # ANSI-C decode
        ('KEY', 'KEY'),          # bare name is LITERAL (r21 A1)
        ('"a b"', 'a b'),
        ('', ''),
    ])
    def test_key_rows(self, subscript, raw, key):
        assert subscript.associative_key(raw) == key

    def test_dollar_variable_expands(self, captured_shell, subscript):
        captured_shell.run_command('k=KEY')
        assert subscript.associative_key('$k') == 'KEY'
        assert subscript.associative_key('"$k"') == 'KEY'
        assert subscript.associative_key("'$k'") == '$k'

    def test_bare_name_never_dereferences(self, captured_shell, subscript):
        captured_shell.run_command('k=other')
        assert subscript.associative_key('k') == 'k'

    def test_tilde_expands(self, captured_shell, subscript):
        captured_shell.run_command('HOME=/probe-home')
        assert subscript.associative_key('~') == '/probe-home'

    def test_no_glob_no_split(self, subscript, tmp_path):
        # A glob metachar key stays literal; a spaced key stays one key.
        assert subscript.associative_key('*') == '*'
        assert subscript.associative_key('a *') == 'a *'


class TestArithAssociativeKeyProvenance:
    """Arithmetic associative subscripts key with PROVENANCE (campaign W2/CV1).

    The subscript's $-forms are held out of the arithmetic pre-pass
    (arithmetic/evaluator.py#_arith_preexpand), so it reaches the ONE keying
    engine RAW and is keyed exactly like a non-arithmetic ``h[$k]=v``: source-
    spelled quotes/backslashes are removed, but characters arriving via ``$k``
    stay LITERAL and a substituted ``$`` is never rescanned. Every row is
    bash 5.2-verified (tmp/boundary-ledgers/CV-probes/cv1_matrix.sh)."""

    def _key(self, sh, setup, sub):
        # Write via arithmetic, then read the stored key back out with declare.
        sh.clear_output()
        sh.run_command(f'declare -A h; {setup}; (( h[{sub}]=1 )); declare -p h')
        return sh.get_stdout()

    def test_substituted_double_quotes_stay_literal(self, captured_shell):
        # k='"q"' -> bash keys "q" (quotes kept), NOT q.
        out = self._key(captured_shell, "k='\"q\"'", '$k')
        assert '["\\"q\\""]="1"' in out

    def test_substituted_single_quotes_stay_literal(self, captured_shell):
        out = self._key(captured_shell, "k=\"'a b'\"", '$k')
        assert '["\'a b\'"]="1"' in out

    def test_substituted_backslash_dollar_stays_literal(self, captured_shell):
        out = self._key(captured_shell, "k='\\$x'", '$k')
        assert '\\$x' in out  # backslash + dollar retained, not stripped

    def test_source_double_quotes_are_removed(self, captured_shell):
        # SOURCE-spelled quotes ARE removed (h["q"] keys q) — provenance cuts
        # the other way for characters spelled in the arithmetic source.
        out = self._key(captured_shell, ':', '"q"')
        assert '[q]="1"' in out

    def test_braced_substitution_stays_literal(self, captured_shell):
        out = self._key(captured_shell, "k='\"q\"'", '${k}')
        assert '["\\"q\\""]="1"' in out

    def test_mixed_source_and_substituted(self, captured_shell):
        # p is source (kept), $k contributes its literal quotes.
        out = self._key(captured_shell, "k='\"q\"'", 'p$k')
        assert '["p\\"q\\""]="1"' in out

    def test_dollar_literal_never_reexpanded(self, captured_shell):
        # Doctrine $-half (must stay bash-exact): a substituted literal $x is
        # NOT re-expanded — keys \$x, not x's value.
        out = self._key(captured_shell, "x=5; k='$x'", '$k')
        assert '\\$x' in out and '[5]' not in out

    def test_read_side_missing_key(self, captured_shell):
        # h has key q; reading with k='"q"' looks up "q" (absent) -> 0.
        captured_shell.clear_output()
        captured_shell.run_command(
            'declare -A h; h[q]=7; k=\'"q"\'; echo $(( h[$k] ))')
        assert captured_shell.get_stdout().strip() == '0'


class TestIndexedIndex:
    """Expand then arithmetic-evaluate (bare names deref arithmetically)."""

    def test_expression(self, subscript):
        assert subscript.indexed_index('1+1') == 2

    def test_dollar_variable(self, captured_shell, subscript):
        captured_shell.run_command('i=3')
        assert subscript.indexed_index('$i') == 3

    def test_bare_name_dereferences(self, captured_shell, subscript):
        captured_shell.run_command('i=2')
        assert subscript.indexed_index('i') == 2

    def test_bare_name_recursion(self, captured_shell, subscript):
        captured_shell.run_command('i=j; j=2')
        assert subscript.indexed_index('i') == 2

    def test_unset_name_is_zero(self, subscript):
        assert subscript.indexed_index('junk') == 0

    def test_whitespace_tolerated(self, subscript):
        assert subscript.indexed_index(' 1 + 1 ') == 2


class TestEvaluateDispatch:
    def test_associative(self, subscript):
        assert subscript.evaluate("'a''b'", TargetKind.ASSOCIATIVE,
                                  SubscriptUse.READ) == 'ab'

    def test_indexed(self, subscript):
        assert subscript.evaluate('1+1', TargetKind.INDEXED,
                                  SubscriptUse.READ) == 2


class TestConsumerSitesKeyIdentically:
    """Every consumer routes through the service — one keying per kind."""

    def test_write_read_isset_unset_agree(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A h; k=other; h[k]=5')
        assert sh.run_command('echo "${h[k]}"') == 0
        assert sh.get_stdout().strip() == '5'
        sh.clear_output()
        sh.run_command('echo "${h[k]+SET}"')
        assert sh.get_stdout().strip() == 'SET'
        sh.clear_output()
        sh.run_command('unset "h[k]"; echo "${h[k]:-gone}"')
        assert sh.get_stdout().strip() == 'gone'

    def test_composite_write_then_plain_read(self, captured_shell):
        sh = captured_shell
        sh.run_command("declare -A h; h['a''b']=v; echo \"${h[ab]}\"")
        assert sh.get_stdout().strip() == 'v'

    def test_ansi_c_write_then_plain_read(self, captured_shell):
        sh = captured_shell
        sh.run_command("declare -A a; a[$'k']=1; echo \"${a[k]}\"")
        assert sh.get_stdout().strip() == '1'

    def test_test_v_uses_assoc_key_rule(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A h; h["k 1"]=v')
        assert sh.run_command('test -v "h[k 1]"') == 0
        # Quote removal applies inside the subscript (bash: SET) — the sq
        # spelling addresses the SAME key `k 1`:
        assert sh.run_command('test -v "h[\'k 1\']"') == 0
        assert sh.run_command('test -v "h[absent]"') == 1

    def test_test_v_indexed_routes_through_authority(self, captured_shell):
        # Bounce blocker A: the indexed arm of -v arithmetic-evaluates via
        # the service — expression, bare-name deref (with recursion),
        # negative index, scalar-as-index-0 (all bash 5.2).
        sh = captured_shell
        sh.run_command('a=(x y z); i=j; j=1; s=5')
        assert sh.run_command('test -v "a[1+1]"') == 0
        assert sh.run_command('test -v "a[i]"') == 0
        assert sh.run_command('test -v "a[-1]"') == 0
        assert sh.run_command('test -v "a[9]"') == 1
        assert sh.run_command('test -v "s[0]"') == 0
        assert sh.run_command('test -v "s[1-1]"') == 0
        assert sh.run_command('test -v "s[1]"') == 1

    def test_test_v_empty_subscript_silently_unset(self, captured_shell):
        sh = captured_shell
        sh.run_command('a=(x y); e=')
        assert sh.run_command('test -v "a[]"') == 1
        assert sh.run_command('test -v "a[$e]"') == 1
        assert sh.get_stderr() == ''

    def test_test_v_negative_oor_warns_nonfatal(self, captured_shell):
        sh = captured_shell
        sh.run_command('a=(x y)')
        assert sh.run_command('test -v "a[-9]"') == 1
        assert 'a: bad array subscript' in sh.get_stderr()

    def test_unset_empty_subscript_is_noop(self, captured_shell):
        sh = captured_shell
        sh.run_command('a=(1 2); e=; unset "a[]"; unset "a[$e]"; '
                       'echo "[${a[0]:-gone}]"')
        assert sh.get_stdout().strip() == '[1]'

    def test_initializer_and_element_write_agree(self, captured_shell):
        sh = captured_shell
        sh.run_command("declare -A h=([a'b']=init); h[a'b']=elem; "
                       'echo "${h[ab]}"')
        assert sh.get_stdout().strip() == 'elem'

    def test_arith_assoc_key_quote_removal(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A h; h[k]=5; echo $((h["k"]))')
        assert sh.get_stdout().strip() == '5'

    def test_arith_verbatim_spaced_key(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A h; h["a b"]=4; echo $((h[a b]))')
        assert sh.get_stdout().strip() == '4'

    def test_arith_key_never_stripped(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A h; h[foo]=1; echo $((h[ foo ]))')
        assert sh.get_stdout().strip() == '0'

    def test_undeclared_quoted_subscript_is_indexed(self, captured_shell):
        # target-kind-first: quoting does NOT infer associative (bash).
        sh = captured_shell
        sh.run_command('u1["k"]=x; declare -p u1')
        out = sh.get_stdout()
        assert 'declare -a u1' in out and '[0]="x"' in out

    def test_assoc_empty_key_write_rejected(self, captured_shell):
        sh = captured_shell
        rc = sh.run_command('declare -A a; a[""]=v')
        assert rc == 1
        assert 'bad array subscript' in sh.get_stderr()

    def test_unsubscripted_assoc_is_key_zero(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A a=([0]=zero [x]=y); echo "[$a]"')
        assert sh.get_stdout().strip() == '[zero]'


class TestArithVerbatimSubscript:
    """The arith tokenizer captures subscripts verbatim (r21 A3)."""

    def test_nested_brackets(self, captured_shell):
        sh = captured_shell
        sh.run_command('b=(1 0); a=(9 8); echo $((a[b[0]]))')
        assert sh.get_stdout().strip() == '8'

    def test_comma_expression(self, captured_shell):
        sh = captured_shell
        sh.run_command('a=(10 20 30); echo $((a[1,2]))')
        assert sh.get_stdout().strip() == '30'

    def test_side_effect_once(self, captured_shell):
        sh = captured_shell
        sh.run_command('a=(9 8 7); i=0; echo $((a[i++ + 1])) $i')
        assert sh.get_stdout().strip() == '8 1'

    def test_no_dollar_reexpansion(self, captured_shell):
        sh = captured_shell
        sh.run_command("declare -A h; k='$x'; x=5; h['$x']=111; h[5]=222; "
                       'echo $((h[$k]))')
        assert sh.get_stdout().strip() == '111'

    def test_adjacency_required(self, captured_shell):
        sh = captured_shell
        rc = sh.run_command('declare -A h; h[k]=9; echo $(( h [k] ))')
        assert rc != 0 or '9' not in sh.get_stdout()

    def test_unclosed_subscript_error(self, captured_shell):
        sh = captured_shell
        rc = sh.run_command('declare -A h; h[k]=1; echo $((h[k))')
        assert rc == 1
        assert 'bad array subscript' in sh.get_stderr()

    def test_empty_subscript_error(self, captured_shell):
        sh = captured_shell
        rc = sh.run_command('declare -A h; e=; h[x]=3; echo $((h[$e]))')
        assert rc == 1
        assert 'h[]: bad array subscript' in sh.get_stderr()

    def test_arith_write_creates_string_key(self, captured_shell):
        sh = captured_shell
        sh.run_command('declare -A h; k="a b"; (( h[$k]=2 )); declare -p h')
        assert '["a b"]="2"' in sh.get_stdout()
