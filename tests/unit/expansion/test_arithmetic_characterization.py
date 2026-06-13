"""Characterization tests for shell arithmetic ($(( ... ))).

These freeze the CURRENT behavior of psh's arithmetic engine
(psh/expansion/arithmetic) so that the package decomposition refactor can be
proven to be a zero-behavior-change change. They drive the real public entry
points (evaluate_arithmetic / ArithTokenizer / ArithParser) the way the rest
of psh and the existing tests do.

If one of these ever needs to change, that is a behavior change and must be
justified against bash, not edited to match a refactor.
"""

import pytest

from psh.expansion.arithmetic import (
    ArithmeticError,
    ArithParser,
    ArithTokenizer,
    evaluate_arithmetic,
)
from psh.shell import Shell


@pytest.fixture
def sh():
    """A fresh shell with a few variables/arrays pre-seeded for var cases."""
    shell = Shell()
    st = shell.state
    st.set_variable("a", "5")
    st.set_variable("b", "3")
    st.set_variable("zero", "0")
    st.set_variable("neg", "-7")
    st.set_variable("hexv", "0x10")
    st.set_variable("octv", "010")
    st.set_variable("basev", "2#101")
    st.set_variable("expr_var", "2*3")
    st.set_variable("chain1", "chain2")
    st.set_variable("chain2", "99")
    # An indexed array for array-element read cases.
    shell.run_command("arr=(10 20 30)")
    return shell


def ev(expr, shell):
    return evaluate_arithmetic(expr, shell)


# ---------------------------------------------------------------------------
# Literals in all bases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("0", 0),
    ("42", 42),
    ("007", 7),            # leading-zero octal
    ("010", 8),            # octal
    ("0777", 511),         # octal
    ("0x10", 16),          # hex lower
    ("0X1f", 31),          # hex upper prefix, lower digits
    ("0xFF", 255),
    ("0b101", 0),          # NOTE: psh has no 0b binary literal; 0b is octal 0 then ident b -> see error case
    ("2#101", 5),          # base#digits
    ("16#ff", 255),
    ("8#17", 15),
    ("36#z", 35),
    ("36#Z", 35),          # case-insensitive for base <= 36
    ("64#A", 36),          # base > 36: A..Z are 36..61
    ("64#a", 10),
    ("64#@", 62),
    ("64#_", 63),
])
def test_literal_bases(expr, expected, sh):
    # 0b101 special-cased below; skip the parametrize entry that needs error semantics
    if expr == "0b101":
        pytest.skip("covered by error/edge cases")
    assert ev(expr, sh) == expected


def test_0b_is_not_binary(sh):
    # psh does not implement 0b binary literals. "0b101" tokenizes as octal 0
    # then identifier b101 -> "Unexpected token" style parse error.
    with pytest.raises(ArithmeticError):
        ev("0b101", sh)


# ---------------------------------------------------------------------------
# Unary operators
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("+5", 5),
    ("-5", -5),
    ("- -5", 5),         # unary minus twice (spaced so it isn't `--`)
    ("!0", 1),
    ("!5", 0),
    ("!!5", 1),
    ("~0", -1),
    ("~5", -6),
    ("-~5", 6),
])
def test_unary_operators(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# Binary arithmetic + precedence + associativity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("2 + 3", 5),
    ("10 - 3", 7),
    ("4 * 5", 20),
    ("20 / 4", 5),
    ("17 % 5", 2),
    ("7 / 2", 3),          # integer truncation
    ("-7 / 2", -3),        # truncates toward zero
    ("7 % -3", 1),         # C-style remainder, sign of dividend
    ("-7 % 3", -1),
    ("2 ** 8", 256),
    ("2 ** 3 ** 2", 512),  # power is right-associative: 2**(3**2)=2**9
    ("2 + 3 * 4", 14),     # precedence
    ("(2 + 3) * 4", 20),
    ("2 * 3 + 4", 10),
    ("10 - 3 - 2", 5),     # left-assoc subtraction
    ("100 / 10 / 2", 5),   # left-assoc division
    ("2 + 3 - 4 * 5 / 2", -5),
])
def test_binary_precedence(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# Comparisons (result 0/1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("3 < 5", 1),
    ("5 < 3", 0),
    ("3 > 5", 0),
    ("5 <= 5", 1),
    ("5 >= 6", 0),
    ("4 == 4", 1),
    ("4 != 4", 0),
    ("4 != 5", 1),
    ("1 < 2 == 1", 1),     # (1<2) -> 1, then ==1 -> 1
])
def test_comparisons(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# Logical operators (short-circuit) + bitwise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("1 && 1", 1),
    ("1 && 0", 0),
    ("0 && 1", 0),
    ("0 || 0", 0),
    ("0 || 5", 1),
    ("5 || 0", 1),
    ("3 && 0 || 1", 1),
    ("12 & 10", 8),
    ("12 | 3", 15),
    ("12 ^ 10", 6),
    ("1 << 4", 16),
    ("256 >> 2", 64),
    ("5 & 3 | 8", 9),     # & higher than |
    ("1 | 2 ^ 3", 1),     # ^ higher than |
])
def test_logical_bitwise(expr, expected, sh):
    assert ev(expr, sh) == expected


def test_logical_short_circuit_side_effects(sh):
    sh.state.set_variable("x", "0")
    # RHS assignment must NOT run because LHS of && is false.
    assert ev("0 && (x = 7)", sh) == 0
    assert sh.state.get_variable("x") == "0"
    # RHS must NOT run because LHS of || is true.
    assert ev("1 || (x = 9)", sh) == 1
    assert sh.state.get_variable("x") == "0"


# ---------------------------------------------------------------------------
# Shifts: masking and negative-count errors
# ---------------------------------------------------------------------------

def test_shift_count_masking(sh):
    # Shift count is masked with & 63.
    assert ev("1 << 64", sh) == 1
    assert ev("1 << 65", sh) == 2


@pytest.mark.parametrize("expr", ["1 << -1", "1 >> -1"])
def test_negative_shift_errors(expr, sh):
    with pytest.raises(ArithmeticError) as e:
        ev(expr, sh)
    assert "negative shift count" in str(e.value)


# ---------------------------------------------------------------------------
# Ternary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("1 ? 2 : 3", 2),
    ("0 ? 2 : 3", 3),
    ("5 > 3 ? 10 : 20", 10),
    ("0 ? 1 : 1 ? 2 : 3", 2),   # right-assoc / nested ternary
    ("1 ? 0 ? 7 : 8 : 9", 8),
])
def test_ternary(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# Comma operator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("1, 2, 3", 3),
    ("(1, 2), 4", 4),
])
def test_comma(expr, expected, sh):
    assert ev(expr, sh) == expected


def test_comma_evaluates_left_side_effects(sh):
    sh.state.set_variable("c", "0")
    assert ev("c = 5, c + 1", sh) == 6
    assert sh.state.get_variable("c") == "5"


# ---------------------------------------------------------------------------
# Variable references (incl. recursive/base-prefixed/chained values)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("a", 5),
    ("a + b", 8),
    ("a * b", 15),
    ("neg", -7),
    ("hexv", 16),       # value "0x10"
    ("octv", 8),        # value "010"
    ("basev", 5),       # value "2#101"
    ("expr_var", 6),    # value "2*3" evaluated
    ("expr_var + 1", 7),
    ("chain1", 99),     # chain1 -> chain2 -> 99
    ("undefined_var", 0),
    ("undefined_var + 4", 4),
])
def test_variable_references(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# Array element read / assign
# ---------------------------------------------------------------------------

def test_array_element_read(sh):
    assert ev("arr[0]", sh) == 10
    assert ev("arr[1]", sh) == 20
    assert ev("arr[2]", sh) == 30
    assert ev("arr[1] + arr[2]", sh) == 50
    assert ev("arr[a - 4]", sh) == 20   # index expression: 5-4=1


def test_array_element_assign(sh):
    assert ev("arr[1] = 99", sh) == 99
    assert ev("arr[1]", sh) == 99


def test_array_element_compound_assign(sh):
    assert ev("arr[0] += 5", sh) == 15
    assert ev("arr[0]", sh) == 15


def test_array_assign_creates_array(sh):
    assert ev("fresh[2] = 7", sh) == 7
    assert ev("fresh[2]", sh) == 7
    assert ev("fresh[0]", sh) == 0


# ---------------------------------------------------------------------------
# Assignment (simple + compound) — persistence checked
# ---------------------------------------------------------------------------

def test_simple_assignment(sh):
    assert ev("x = 12", sh) == 12
    assert sh.state.get_variable("x") == "12"


def test_assignment_is_right_associative(sh):
    assert ev("p = q = 5", sh) == 5
    assert sh.state.get_variable("p") == "5"
    assert sh.state.get_variable("q") == "5"


@pytest.mark.parametrize("expr,start,expected,stored", [
    ("v += 3", "10", 13, "13"),
    ("v -= 4", "10", 6, "6"),
    ("v *= 3", "10", 30, "30"),
    ("v /= 3", "10", 3, "3"),
    ("v %= 3", "10", 1, "1"),
    ("v <<= 2", "1", 4, "4"),
    ("v >>= 1", "8", 4, "4"),
    ("v &= 6", "12", 4, "4"),
    ("v |= 1", "8", 9, "9"),
    ("v ^= 5", "12", 9, "9"),
])
def test_compound_assignment(expr, start, expected, stored, sh):
    sh.state.set_variable("v", start)
    assert ev(expr, sh) == expected
    assert sh.state.get_variable("v") == stored


# ---------------------------------------------------------------------------
# Pre / post increment & decrement
# ---------------------------------------------------------------------------

def test_pre_increment(sh):
    sh.state.set_variable("i", "5")
    assert ev("++i", sh) == 6
    assert sh.state.get_variable("i") == "6"


def test_pre_decrement(sh):
    sh.state.set_variable("i", "5")
    assert ev("--i", sh) == 4
    assert sh.state.get_variable("i") == "4"


def test_post_increment(sh):
    sh.state.set_variable("i", "5")
    assert ev("i++", sh) == 5
    assert sh.state.get_variable("i") == "6"


def test_post_decrement(sh):
    sh.state.set_variable("i", "5")
    assert ev("i--", sh) == 5
    assert sh.state.get_variable("i") == "4"


def test_increment_unset_var(sh):
    assert ev("fresh_i++", sh) == 0
    assert sh.state.get_variable("fresh_i") == "1"


# ---------------------------------------------------------------------------
# Parentheses / grouping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("(5)", 5),
    ("((5))", 5),
    ("(2 + 3) * (4 - 1)", 15),
    ("-(3 + 4)", -7),
])
def test_parentheses(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# 64-bit signed wrapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,expected", [
    ("2 ** 63", -9223372036854775808),
    ("2 ** 64", 0),
    ("9223372036854775807 + 1", -9223372036854775808),
])
def test_signed64_wrapping(expr, expected, sh):
    assert ev(expr, sh) == expected


# ---------------------------------------------------------------------------
# Empty / whitespace expressions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr", ["", "   ", "\t"])
def test_empty_expression_is_zero(expr, sh):
    assert ev(expr, sh) == 0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_division_by_zero(sh):
    with pytest.raises(ArithmeticError) as e:
        ev("1 / 0", sh)
    assert "Division by zero" in str(e.value)


def test_modulo_by_zero(sh):
    with pytest.raises(ArithmeticError) as e:
        ev("1 % 0", sh)
    assert "Division by zero" in str(e.value)


def test_division_by_zero_via_var(sh):
    with pytest.raises(ArithmeticError):
        ev("10 / zero", sh)


def test_negative_exponent(sh):
    with pytest.raises(ArithmeticError) as e:
        ev("2 ** -1", sh)
    assert "exponent less than 0" in str(e.value)


@pytest.mark.parametrize("expr", [
    "2 +",          # malformed - trailing operator
    "* 3",          # leading binary operator
    "2 3",          # unexpected token after expression
    "(2 + 3",       # unbalanced paren
    "2 + 3)",       # extra close paren
    "1 ? 2",        # ternary missing colon
    "@",            # unexpected char
    "0x",           # bad hex literal
    "1#5",          # invalid base (< 2)
    "99#1",         # invalid base (> 64)
    "++5",          # pre-increment needs identifier
    "--5",          # pre-decrement needs identifier (not unary minus twice)
])
def test_malformed_expressions(expr, sh):
    with pytest.raises(ArithmeticError):
        ev(expr, sh)


def test_octal_invalid_digit(sh):
    # 08 / 09 are invalid octal; bash-style "value too great for base" error.
    with pytest.raises(ArithmeticError) as e:
        ev("08", sh)
    assert "value too great for base" in str(e.value)


def test_invalid_base_number_no_digits(sh):
    with pytest.raises(ArithmeticError):
        ev("16#", sh)


# ---------------------------------------------------------------------------
# Double-quote tolerance inside $(( ))
# ---------------------------------------------------------------------------

def test_double_quotes_are_stripped(sh):
    # bash tolerates double-quoted operands; quotes are stripped.
    assert ev('"5" + "3"', sh) == 8


# ---------------------------------------------------------------------------
# Tokenizer-level characterization (public ArithTokenizer)
# ---------------------------------------------------------------------------

def _types(expr):
    return [t.type.name for t in ArithTokenizer(expr).tokenize()]


def test_tokenizer_number():
    toks = ArithTokenizer("42").tokenize()
    assert toks[0].type.name == "NUMBER"
    assert toks[0].value == 42
    assert toks[-1].type.name == "EOF"


def test_tokenizer_multichar_operators():
    assert _types("a += 1") == ["IDENTIFIER", "PLUS_ASSIGN", "NUMBER", "EOF"]
    assert _types("a <<= 1") == ["IDENTIFIER", "LSHIFT_ASSIGN", "NUMBER", "EOF"]
    assert _types("a ** b") == ["IDENTIFIER", "POWER", "IDENTIFIER", "EOF"]
    assert _types("a ++") == ["IDENTIFIER", "INCREMENT", "EOF"]
    assert _types("a && b || c") == [
        "IDENTIFIER", "AND", "IDENTIFIER", "OR", "IDENTIFIER", "EOF"]
    assert _types("<< >> <= >= == !=") == [
        "LSHIFT", "RSHIFT", "LE", "GE", "EQ", "NE", "EOF"]


def test_tokenizer_unexpected_char():
    with pytest.raises(SyntaxError):
        ArithTokenizer("`").tokenize()


# ---------------------------------------------------------------------------
# Parser-level characterization (public ArithParser) — AST shape
# ---------------------------------------------------------------------------

def _parse(expr):
    return ArithParser(ArithTokenizer(expr).tokenize()).parse()


def test_parser_precedence_shape():
    ast = _parse("2 + 3 * 4")
    assert ast.op.name == "PLUS"
    assert ast.right.op.name == "MULTIPLY"


def test_parser_parens_shape():
    ast = _parse("(2 + 3) * 4")
    assert ast.op.name == "MULTIPLY"
    assert ast.left.op.name == "PLUS"


def test_parser_ternary_shape():
    ast = _parse("x > 0 ? x : -x")
    assert hasattr(ast, "condition")
    assert hasattr(ast, "true_expr")
    assert hasattr(ast, "false_expr")


def test_parser_empty_is_number_zero():
    ast = _parse("")
    assert ast.value == 0


# ---------------------------------------------------------------------------
# End-to-end via the shell ($((...)) in echo)
# ---------------------------------------------------------------------------

def test_end_to_end_echo(sh):
    # run_command writes to real stdout, so just confirm exit status and
    # variable side effects through the full expansion path here.
    sh.state.set_variable("n", "10")
    rc = sh.run_command("echo $((n * 2)) > /dev/null")
    assert rc == 0
    # post-increment side effect persists through full expansion path
    sh.run_command(": $((n++))")
    assert sh.state.get_variable("n") == "11"
