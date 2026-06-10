"""Pattern-operator operand expansion (v0.266.0).

Operands of ``${x#pat}``/``${x%pat}``/``${x/pat/repl}`` and the case-mod
operators undergo variable/command/arithmetic expansion with one level of
quote removal, like bash. Replacements are inserted literally (never as
regex templates) with bash 5.2 patsub_replacement ``&`` semantics.

Every expectation here was verified against bash 5.2.
"""



def run(shell, cmd):
    shell.run_command(cmd)
    return shell.get_stdout()


class TestVariableInPattern:
    """$var, $(cmd) and $((expr)) expand inside pattern operands."""

    def test_suffix_removal_with_variable(self, captured_shell):
        assert run(captured_shell, 'ext=.txt; f=a.txt; echo "${f%$ext}"') == "a\n"

    def test_prefix_removal_with_variable(self, captured_shell):
        assert run(captured_shell, 'p=a; f=abc; echo ${f#$p}') == "bc\n"

    def test_substitution_pattern_from_variable(self, captured_shell):
        assert run(captured_shell, 'x=abc y=b; echo "${x/$y/Z}"') == "aZc\n"

    def test_command_sub_in_pattern(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x#$(echo a)}"') == "bc\n"

    def test_arithmetic_in_pattern(self, captured_shell):
        assert run(captured_shell, 'x=a2c; echo "${x/$((1+1))/Z}"') == "aZc\n"

    def test_unquoted_expansion_is_glob_active(self, captured_shell):
        # p='*' unquoted keeps its glob power: matches the whole value
        assert run(captured_shell, 'p="*"; x=abc; echo "${x/$p/Z}"') == "Z\n"

    def test_unquoted_expansion_question_mark(self, captured_shell):
        assert run(captured_shell, 'p="?c"; x=abc; echo "${x#a$p}"') == "\n"

    def test_dirname_pattern_from_variable(self, captured_shell):
        assert run(captured_shell,
                   'f=/path/to/file.txt; d="*/"; echo "${f##$d}"') == "file.txt\n"


class TestQuotedPattern:
    """Quoted operand text matches literally (one quote level removed)."""

    def test_single_quoted_pattern(self, captured_shell):
        assert run(captured_shell, "f=abc; echo \"${f#'a'}\"") == "bc\n"

    def test_double_quoted_glob_is_literal(self, captured_shell):
        # "*" quoted: literal star, matches the * in the value
        assert run(captured_shell, 'x="a*c"; echo "${x/"*"/Z}"') == "aZc\n"

    def test_quoted_expansion_is_literal(self, captured_shell):
        # "$p" quoted: result loses glob power, no literal * to match
        assert run(captured_shell, 'p="*"; x=abc; echo "${x/"$p"/Z}"') == "abc\n"

    def test_quoted_expansion_matches_literal_text(self, captured_shell):
        assert run(captured_shell,
                   'x="[a]bc"; p="[a]"; echo "${x/"$p"/Z}"') == "Zbc\n"


class TestReplacementLiteral:
    """Replacements are literal — never regex templates."""

    def test_backslash_digit_not_group_reference(self, captured_shell):
        # Previously crashed with "invalid group reference"
        assert run(captured_shell, r'x=abc; echo "${x/b/\1}"') == "a1c\n"

    def test_backslash_n_not_newline(self, captured_shell):
        assert run(captured_shell, r'x=aXbXc; echo "${x//X/\n}"') == "anbnc\n"

    def test_escaped_backslash(self, captured_shell):
        assert run(captured_shell, r'x=abc; echo "${x/b/\\1}"') == "a\\1c\n"

    def test_backslash_from_variable_stays_literal(self, captured_shell):
        assert run(captured_shell, r'r="\1"; x=abc; echo "${x/b/$r}"') == "a\\1c\n"

    def test_variable_in_replacement(self, captured_shell):
        assert run(captured_shell, 'x=abc; y=R; echo "${x/b/$y}"') == "aRc\n"

    def test_command_sub_in_replacement(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/b/$(echo Z)}"') == "aZc\n"

    def test_empty_variable_in_replacement(self, captured_shell):
        assert run(captured_shell, 'x=abc; u=""; echo "[${x/b/$u}]"') == "[ac]\n"


class TestPatsubAmpersand:
    """bash 5.2 patsub_replacement: unquoted & stands for the match."""

    def test_ampersand_is_match(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/b/[&]}"') == "a[b]c\n"

    def test_multiple_ampersands(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/b/one&two&}"') == "aonebtwobc\n"

    def test_ampersand_in_global_substitution(self, captured_shell):
        assert run(captured_shell, 'x=aXbXc; echo "${x//X/[&]}"') == "a[X]b[X]c\n"

    def test_ampersand_with_prefix_anchor(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/#a/&-}"') == "a-bc\n"

    def test_ampersand_with_suffix_anchor(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/%c/-&}"') == "ab-c\n"

    def test_escaped_ampersand_is_literal(self, captured_shell):
        assert run(captured_shell, r'x=abc; echo "${x/b/\&}"') == "a&c\n"

    def test_double_quoted_ampersand_is_literal(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/b/"&"}"') == "a&c\n"

    def test_single_quoted_ampersand_is_literal(self, captured_shell):
        assert run(captured_shell, "x=abc; echo \"${x/b/'&'}\"") == "a&c\n"

    def test_ampersand_from_expansion_is_active(self, captured_shell):
        # bash 5.2: & produced by an expansion still stands for the match
        assert run(captured_shell, 'r="&"; x=abc; echo "${x/b/$r}"') == "abc\n"

    def test_ampersand_in_pattern_side_is_plain(self, captured_shell):
        assert run(captured_shell, 'x="a&c"; echo "${x//&/-}"') == "a-c\n"


class TestSplitAndEdgeCases:
    def test_escaped_slash_in_pattern(self, captured_shell):
        assert run(captured_shell, r'x=a/b/c; echo "${x//\//-}"') == "a-b-c\n"

    def test_slash_inside_arithmetic_does_not_split(self, captured_shell):
        assert run(captured_shell, 'x=a2c; echo "${x/$((4/2))/Z}"') == "aZc\n"

    def test_deletion_no_separator(self, captured_shell):
        assert run(captured_shell, 'x=aXbXc; echo "${x//X}"') == "abc\n"

    def test_empty_pattern_is_noop(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x///Z}"') == "abc\n"

    def test_trailing_backslash_in_replacement(self, captured_shell):
        assert run(captured_shell, 'x=abc; echo "${x/b/y\\\\}"') == "ay\\c\n"


class TestCaseModification:
    """Case-mod patterns match single characters; ^/, test only the first."""

    def test_first_char_not_matching_pattern(self, captured_shell):
        # ^ only examines the first char; 'b' never matches 'a'
        assert run(captured_shell, 'v=abc; echo "${v^b}"') == "abc\n"

    def test_first_char_matching_pattern(self, captured_shell):
        assert run(captured_shell, 'v=abc; echo "${v^a}"') == "Abc\n"

    def test_multichar_pattern_never_matches(self, captured_shell):
        # the pattern is matched per character, so 'bc' matches nothing
        assert run(captured_shell, 'v=abc; echo "${v^^bc}"') == "abc\n"

    def test_pattern_from_variable(self, captured_shell):
        assert run(captured_shell, 'v=abc p=b; echo "${v^^$p}"') == "aBc\n"

    def test_first_with_variable_pattern(self, captured_shell):
        assert run(captured_shell, 'v=abc p=b; echo "${v^$p}"') == "abc\n"

    def test_class_pattern_all(self, captured_shell):
        assert run(captured_shell,
                   'v="hello world"; echo "${v^^[lo]}"') == "heLLO wOrLd\n"


class TestArrayPerElement:
    def test_suffix_removal_with_variable_per_element(self, captured_shell):
        assert run(captured_shell,
                   'a=(foo.txt bar.txt); ext=.txt; echo "${a[@]%$ext}"') == "foo bar\n"

    def test_substitution_with_variable_per_element(self, captured_shell):
        assert run(captured_shell,
                   'a=(abc adc); p=b; echo "${a[@]/$p/X}"') == "aXc adc\n"

    def test_ampersand_per_element(self, captured_shell):
        assert run(captured_shell,
                   'a=(abc adc); echo "${a[@]/b/&&}"') == "abbc adc\n"

    def test_case_mod_per_element(self, captured_shell):
        assert run(captured_shell, 'a=(one two); echo "${a[@]^^o}"') == "One twO\n"
