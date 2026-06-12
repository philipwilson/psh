"""Unit tests for psh/expansion/param_parser.py — the single ${...} parser.

Covers every form in the module-docstring grammar reference (one or more
cases per documented line), the scan-strategy disambiguations, and the
bash-adjudicated fix families from the B5 migration.
"""

import pytest

from psh.expansion.param_parser import parse_parameter_expansion


def triple(content):
    node = parse_parameter_expansion(content)
    return (node.parameter, node.operator, node.word)


class TestPlainParameters:
    """Operator None; the evaluator resolves the name."""

    @pytest.mark.parametrize('content', [
        'var', 'HOME', '_x9', '@', '*', '?', '$', '!', '-', '0', '5', '42',
    ])
    def test_plain_names_and_specials(self, content):
        assert triple(content) == (content, None, None)

    @pytest.mark.parametrize('content', [
        'arr[3]', 'arr[@]', 'arr[*]', 'a[x,y]', 'a[x^y]', 'h["k 1"]',
        'arr[i+1]', 'arr[arr[0]+1]', 'arr[-1]',
    ])
    def test_subscripts_stay_plain(self, content):
        assert triple(content) == (content, None, None)

    def test_empty_content(self):
        assert triple('') == ('', None, None)

    def test_unclosed_bracket_suppresses_scan(self):
        # ${a[x:-d — an unclosed subscript never yields an operator.
        assert triple('a[x:-d') == ('a[x:-d', None, None)


class TestLength:
    def test_var(self):
        assert triple('#v') == ('v', '#', None)

    def test_array_at(self):
        assert triple('#arr[@]') == ('arr[@]', '#', None)

    def test_array_element(self):
        assert triple('#arr[3]') == ('arr[3]', '#', None)

    def test_bare_hash_is_positional_count(self):
        assert triple('#') == ('', '#', None)

    @pytest.mark.parametrize('content,param', [
        ('#-', '-'), ('#?', '?'), ('#@', '@'), ('#*', '*'), ('#!', '!'),
        ('##', '#'), ('#0', '0'), ('#12', '12'),
    ])
    def test_length_of_special_parameters(self, content, param):
        assert triple(content) == (param, '#', None)

    @pytest.mark.parametrize('content,expected', [
        # '#' is itself the parameter when the rest is not a whole spec
        # (bash: ${#-} is length of $-, but ${#-d} is $# with default d).
        ('#:-default', ('#', ':-', 'default')),
        ('#-d', ('#', '-', 'd')),
        ('#+d', ('#', '+', 'd')),
    ])
    def test_hash_as_parameter_with_operator(self, content, expected):
        assert triple(content) == expected


class TestIndirection:
    def test_plain(self):
        assert triple('!var') == ('var', '!', None)

    def test_positional(self):
        assert triple('!1') == ('1', '!', None)

    @pytest.mark.parametrize('content,param', [
        ('!#', '#'), ('!?', '?'), ('!$', '$'), ('!-', '-'), ('!!', '!'),
    ])
    def test_special_parameter_indirection(self, content, param):
        assert triple(content) == (param, '!', None)

    def test_array_keys(self):
        assert triple('!arr[@]') == ('arr[@]', '!', None)
        assert triple('!arr[*]') == ('arr[*]', '!', None)

    def test_array_element_indirection(self):
        # F5: bash a=(HOME); ${!a[0]} -> value of $HOME
        assert triple('!a[0]') == ('a[0]', '!', None)
        assert triple('!h[k]') == ('h[k]', '!', None)

    def test_prefix_listing(self):
        assert triple('!prefix*') == ('prefix', '!*', '')
        assert triple('!prefix@') == ('prefix', '!@', '')

    def test_empty_prefix_listing(self):
        # Historical: ${!@}/${!*} list every variable name.
        assert triple('!@') == ('', '!@', '')
        assert triple('!*') == ('', '!*', '')

    def test_indirection_with_operator_keeps_bang_in_parameter(self):
        # The evaluator resolves the indirection before applying the op.
        assert triple('!v:-d') == ('!v', ':-', 'd')
        assert triple('!ref%lo') == ('!ref', '%', 'lo')
        assert triple('!10:-none') == ('!10', ':-', 'none')

    def test_escaped_bang_is_bang(self):
        assert triple('\\!arr[@]') == ('arr[@]', '!', None)


class TestDefaults:
    @pytest.mark.parametrize('content,expected', [
        ('v:-d', ('v', ':-', 'd')),
        ('v:=d', ('v', ':=', 'd')),
        ('v:?m', ('v', ':?', 'm')),
        ('v:+a', ('v', ':+', 'a')),
        ('v-d', ('v', '-', 'd')),
        ('v=d', ('v', '=', 'd')),
        ('v?m', ('v', '?', 'm')),
        ('v+a', ('v', '+', 'a')),
    ])
    def test_scalar(self, content, expected):
        assert triple(content) == expected

    @pytest.mark.parametrize('content,expected', [
        # F1: conditional, not a slice with a signed offset.
        ('a[@]:-def', ('a[@]', ':-', 'def')),
        ('a[*]:-d', ('a[*]', ':-', 'd')),
        ('a[@]:=d', ('a[@]', ':=', 'd')),
        ('a[@]:?m', ('a[@]', ':?', 'm')),
        ('a[@]:+y', ('a[@]', ':+', 'y')),
        ('a[k]:-d', ('a[k]', ':-', 'd')),
        ('arr[5]:=five', ('arr[5]', ':=', 'five')),
        # F2: non-colon operators after a closed subscript.
        ('arr[0]-d', ('arr[0]', '-', 'd')),
        ('x[0]+s', ('x[0]', '+', 's')),
        ('x[0]=v', ('x[0]', '=', 'v')),
        ('x[0]?m', ('x[0]', '?', 'm')),
        ('a[@]-def', ('a[@]', '-', 'def')),
        ('a[i+1]+x', ('a[i+1]', '+', 'x')),
    ])
    def test_subscripted(self, content, expected):
        assert triple(content) == expected

    def test_operand_not_parsed(self):
        # Quotes / nesting / expansions stay verbatim in the word.
        assert triple('v:-${w:-x}') == ('v', ':-', '${w:-x}')
        assert triple('v:-"a b"') == ('v', ':-', '"a b"')
        assert triple('v:-x@Q') == ('v', ':-', 'x@Q')  # F3


class TestSlice:
    @pytest.mark.parametrize('content,expected', [
        ('v:2', ('v', ':', '2')),
        ('v:2:3', ('v', ':', '2:3')),
        ('v: -3', ('v', ':', ' -3')),
        ('v:(-3):2', ('v', ':', '(-3):2')),
        ('v:1+1:2', ('v', ':', '1+1:2')),
        ('@:2', ('@', ':', '2')),
        ('arr[@]:1:2', ('arr[@]', ':', '1:2')),
        ('arr[*]:1:2', ('arr[*]', ':', '1:2')),
        ('s[@]:1:-1', ('s[@]', ':', '1:-1')),
        ('a[@]: -2', ('a[@]', ':', ' -2')),
        ('arr[0]:1:3', ('arr[0]', ':', '1:3')),
    ])
    def test_slices(self, content, expected):
        assert triple(content) == expected


class TestPatternRemoval:
    @pytest.mark.parametrize('content,expected', [
        ('v#p', ('v', '#', 'p')),
        ('v##p', ('v', '##', 'p')),
        ('v%p', ('v', '%', 'p')),
        ('v%%p', ('v', '%%', 'p')),
        ('arr[@]##*/', ('arr[@]', '##', '*/')),
        ('files[0]%.*', ('files[0]', '%', '.*')),
        ('v#"$w"', ('v', '#', '"$w"')),
    ])
    def test_removal(self, content, expected):
        assert triple(content) == expected


class TestSubstitution:
    @pytest.mark.parametrize('content,expected', [
        ('v/p/r', ('v', '/', 'p/r')),
        ('v//p/r', ('v', '//', 'p/r')),
        ('v/#p/r', ('v', '/#', 'p/r')),
        ('v/%p/r', ('v', '/%', 'p/r')),
        # No replacement: operand kept verbatim, no trailing '/' invented.
        ('x/pat', ('x', '/', 'pat')),
        ('x//pat', ('x', '//', 'pat')),
        ('VAR/', ('VAR', '/', '')),
        ('x//', ('x', '//', '')),
        ('a[@]/b/X', ('a[@]', '/', 'b/X')),
        ('x/a\\/b/Z', ('x', '/', 'a\\/b/Z')),
    ])
    def test_substitution(self, content, expected):
        assert triple(content) == expected


class TestCaseModification:
    @pytest.mark.parametrize('content,expected', [
        ('v^', ('v', '^', '')),
        ('v^^', ('v', '^^', '')),
        ('v,', ('v', ',', '')),
        ('v,,', ('v', ',,', '')),
        ('v,,pattern', ('v', ',,', 'pattern')),
        ('v^^[a-m]', ('v', '^^', '[a-m]')),
        ('v^^$p', ('v', '^^', '$p')),
        ('arr[@]^^', ('arr[@]', '^^', '')),
        ('arr[@]^^[a-m]', ('arr[@]', '^^', '[a-m]')),
        ('a[x,y]^^', ('a[x,y]', '^^', '')),  # ',' in subscript is not an op
        ('a[x^y],,', ('a[x^y]', ',,', '')),
    ])
    def test_case_mod(self, content, expected):
        assert triple(content) == expected


class TestTransforms:
    @pytest.mark.parametrize('letter', list('QEPAUuLakK'))
    def test_each_letter(self, letter):
        assert triple(f'v@{letter}') == ('v', f'@{letter}', '')

    def test_array_and_positional(self):
        assert triple('arr[@]@Q') == ('arr[@]', '@Q', '')
        assert triple('@@Q') == ('@', '@Q', '')

    def test_only_in_final_position(self):
        # '@'+letter not at the end is no transform: plain (unset) name.
        assert triple('v@Qx') == ('v@Qx', None, None)

    def test_unknown_letter_is_plain(self):
        assert triple('v@X') == ('v@X', None, None)


class TestScanStrategy:
    """Earliest position wins; longest operator at that position."""

    def test_longest_at_position(self):
        # ':-' must beat ':' at the same position, else 'v:-d' would be a
        # slice with offset '-d'.
        assert triple('v:-d') == ('v', ':-', 'd')

    def test_earliest_position(self):
        # ':' at 1 beats '##' at 3.
        assert triple('v:2##') == ('v', ':', '2##')

    def test_operator_chars_in_operand_do_not_match(self):
        assert triple('v:-a:b-c') == ('v', ':-', 'a:b-c')

    def test_unrecognized_text_is_plain(self):
        # ${v~~} (bash's undocumented case-toggle) is not implemented;
        # historical behavior: a plain (unset) name.
        assert triple('v~~') == ('v~~', None, None)


class TestStrRoundTrip:
    """The AST no longer lies: str(node) reproduces the source form."""

    @pytest.mark.parametrize('content', [
        'var', 'arr[@]', 'v:-d', 'arr[@]:1:2', 'x^^', 'v/p/r', '#v', '#',
        'v@Q', 'a[x,y]:-gone',
    ])
    def test_round_trip(self, content):
        assert str(parse_parameter_expansion(content)) == '${' + content + '}'
