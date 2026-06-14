"""Unit tests for the structured Word-AST analysis layer.

`psh/visitor/word_analysis.py` replaces the analysis visitors' regex-over-
rendered-strings with structured inspection of `Word.parts`. These tests pin the
helper behavior the validator/linter/security visitors rely on, especially the
distinctions that the old string scans got wrong (array subscripts, command vs
variable expansions, quoting, parameter defaults, nested operator-word refs).
"""

from psh.ast_nodes import SimpleCommand, Word
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import word_analysis as wa


def _word(src: str, index: int = 1) -> Word:
    """The Word at *index* of the first SimpleCommand parsed from *src*.

    index defaults to 1 (the first argument after the command word).
    """
    ast = parse(tokenize(src))
    cmds = []

    def walk(node):
        from dataclasses import fields, is_dataclass
        if isinstance(node, SimpleCommand):
            cmds.append(node)
        if is_dataclass(node):
            for f in fields(node):
                v = getattr(node, f.name)
                for x in (v if isinstance(v, list) else [v]):
                    if is_dataclass(x):
                        walk(x)

    walk(ast)
    return cmds[0].words[index]


def _refs(src: str, index: int = 1):
    return list(wa.iter_variable_references(_word(src, index)))


class TestIterVariableReferences:
    def test_simple_variable(self):
        (ref,) = _refs("echo $FOO")
        assert ref.name == "FOO"
        assert ref.braced is False
        assert ref.quoted is False
        assert ref.has_default is False
        assert ref.is_array_subscript is False

    def test_braced_variable(self):
        (ref,) = _refs("echo ${FOO}")
        assert ref.name == "FOO"

    def test_quoted_variable(self):
        (ref,) = _refs('echo "$FOO"')
        assert ref.name == "FOO"
        assert ref.quoted is True

    def test_array_subscript_strips_index(self):
        # ${arr[@]} stores 'arr[@]' in the expansion name; the bare name is 'arr'.
        (ref,) = _refs("echo ${arr[@]}")
        assert ref.name == "arr"
        assert ref.is_array_subscript is True

    def test_numeric_subscript_strips_index(self):
        (ref,) = _refs("echo ${arr[0]}")
        assert ref.name == "arr"
        assert ref.is_array_subscript is True

    def test_parameter_default_flagged(self):
        (ref,) = _refs("echo ${FOO:-default}")
        assert ref.name == "FOO"
        assert ref.has_default is True

    def test_assign_default_flagged(self):
        (ref,) = _refs("echo ${FOO:=default}")
        assert ref.has_default is True

    def test_alternate_operator_not_default(self):
        # ${FOO:+word} does NOT supply a value for an unset FOO.
        (ref,) = _refs("echo ${FOO:+set}")
        assert ref.has_default is False

    def test_prefix_strip_operator_not_default(self):
        (ref,) = _refs("echo ${FOO#prefix}")
        assert ref.has_default is False

    def test_nested_operator_word_reference(self):
        # ${FOO:-$BAR}: BAR lives in the raw operator word; recovered via fallback.
        refs = _refs("echo ${FOO:-${BAR}}")
        names = [r.name for r in refs]
        assert names == ["FOO", "BAR"]
        foo = refs[0]
        bar = refs[1]
        assert foo.has_default is True
        assert bar.has_default is False

    def test_command_substitution_is_not_a_variable_reference(self):
        assert _refs("echo $(ls)") == []

    def test_backtick_substitution_is_not_a_variable_reference(self):
        assert _refs("echo `ls`") == []

    def test_arithmetic_is_not_a_variable_reference(self):
        assert _refs("echo $((1 + x))") == []

    def test_single_quoted_dollar_is_literal(self):
        # '$FOO' is a literal string, not a variable reference.
        assert _refs("echo '$FOO'") == []

    def test_mixed_literal_and_expansion(self):
        (ref,) = _refs("echo a$FOO")
        assert ref.name == "FOO"

    def test_special_var_reference(self):
        (ref,) = _refs("echo $@")
        assert ref.name == "@"

    def test_referenced_variable_names(self):
        names = wa.referenced_variable_names(_word("echo ${FOO:-${BAR}}"))
        assert names == ["FOO", "BAR"]


class TestStringFallback:
    def test_simple(self):
        (ref,) = list(wa.iter_variable_references_in_text("$FOO"))
        assert ref.name == "FOO"
        assert ref.braced is False

    def test_braced_with_default(self):
        (ref,) = list(wa.iter_variable_references_in_text("${FOO:-x}"))
        assert ref.name == "FOO"
        assert ref.braced is True
        assert ref.has_default is True

    def test_braced_subscript(self):
        (ref,) = list(wa.iter_variable_references_in_text("${arr[0]}"))
        assert ref.name == "arr"
        assert ref.is_array_subscript is True

    def test_multiple(self):
        refs = list(wa.iter_variable_references_in_text("$A and $B"))
        assert [r.name for r in refs] == ["A", "B"]

    def test_empty_text(self):
        assert list(wa.iter_variable_references_in_text("")) == []

    def test_non_identifier_dollar_ignored(self):
        # $1 / $? do not match the identifier-shaped fallback pattern.
        assert list(wa.iter_variable_references_in_text("$1 $?")) == []


class TestClassification:
    def test_is_pure_literal(self):
        assert wa.is_pure_literal(_word("echo hello")) is True
        assert wa.is_pure_literal(_word("echo $FOO")) is False

    def test_has_command_substitution(self):
        assert wa.has_command_substitution(_word("echo $(ls)")) is True
        assert wa.has_command_substitution(_word("echo `ls`")) is True
        assert wa.has_command_substitution(_word("echo $FOO")) is False

    def test_has_arithmetic_expansion(self):
        assert wa.has_arithmetic_expansion(_word("echo $((1+1))")) is True
        assert wa.has_arithmetic_expansion(_word("echo $FOO")) is False

    def test_has_parameter_expansion(self):
        assert wa.has_parameter_expansion(_word("echo ${FOO:-x}")) is True
        assert wa.has_parameter_expansion(_word("echo $FOO")) is False

    def test_has_variable_reference(self):
        assert wa.has_variable_reference(_word("echo $FOO")) is True
        assert wa.has_variable_reference(_word("echo ${FOO}")) is True
        assert wa.has_variable_reference(_word("echo $(ls)")) is False
        assert wa.has_variable_reference(_word("echo hello")) is False

    def test_is_arithmetic_only(self):
        assert wa.is_arithmetic_only(_word("echo $((COUNT))")) is True
        # An arithmetic expansion with adjacent literal text is not "only".
        assert wa.is_arithmetic_only(_word("echo x$((1))")) is False
        assert wa.is_arithmetic_only(_word("echo $FOO")) is False

    def test_has_unquoted_variable_expansion(self):
        assert wa.has_unquoted_variable_expansion(_word("echo $FOO")) is True
        assert wa.has_unquoted_variable_expansion(_word('echo "$FOO"')) is False
        # Command sub is not a *variable* expansion for this predicate.
        assert wa.has_unquoted_variable_expansion(_word("echo $(ls)")) is False

    def test_has_unquoted_expansion_of_any_kind(self):
        assert wa.has_unquoted_expansion_of_any_kind(_word("echo $(ls)")) is True
        assert wa.has_unquoted_expansion_of_any_kind(_word('echo "$FOO"')) is False


class TestMetacharacterInjection:
    def test_clean_expansion_no_metachar(self):
        assert wa.contains_metacharacters_in_unquoted_expansion(
            _word("echo $FOO")
        ) is False

    def test_no_expansion_no_finding(self):
        assert wa.contains_metacharacters_in_unquoted_expansion(
            _word("echo plain")
        ) is False

    def test_quoted_expansion_excluded(self):
        assert wa.contains_metacharacters_in_unquoted_expansion(
            _word('echo "$FOO"')
        ) is False
