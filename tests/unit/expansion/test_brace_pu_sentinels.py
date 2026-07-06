"""Brace expansion must not corrupt private-use Unicode (expansion Phase-1a F3).

Token-stream brace expansion carries out-of-band metadata (the range-empty
marker; composite-run placeholders) as single characters embedded in the string
handed to the core expander. It used fixed private-use code points (U+F8FF for
range-empty, U+E000+ for composite placeholders), so a literal U+F8FF in the
input was DELETED and a literal U+E000 COLLIDED with a placeholder. The
placeholders are now chosen per expansion to avoid every code point present in
the run, so every code point is ordinary data.

All expectations bash-5.2-verified (tmp/probe_brace_pu.py). The private-use
characters are injected via chr() so the assertions are exact.
"""
import pytest

E000 = chr(0xE000)
E001 = chr(0xE001)
F000 = chr(0xF000)
F8FE = chr(0xF8FE)
F8FF = chr(0xF8FF)
SUPP = chr(0xF0000)  # supplementary private-use plane


class TestPrivateUsePreserved:
    def test_f8ff_not_deleted(self, captured_shell):
        # doc repro 1: literal U+F8FF (the old range-empty sentinel) survives.
        captured_shell.run_command(f"printf '<%s>' {F8FF}{{a,b}}")
        assert captured_shell.get_stdout() == f"<{F8FF}a><{F8FF}b>"

    def test_e000_placeholder_collision(self, captured_shell):
        # doc repro 2: literal U+E000 with a quoted part (composite path).
        captured_shell.run_command(f'printf \'<%s>\' {E000}"x"{{a,b}}')
        assert captured_shell.get_stdout() == f"<{E000}xa><{E000}xb>"

    @pytest.mark.parametrize('pu', [E000, E001, F000, F8FE, F8FF, SUPP])
    def test_pu_unquoted_with_list(self, captured_shell, pu):
        captured_shell.run_command(f"printf '<%s>' {pu}{{a,b}}")
        assert captured_shell.get_stdout() == f"<{pu}a><{pu}b>"

    @pytest.mark.parametrize('pu', [E000, E001, F8FF, SUPP])
    def test_pu_quoted_composite_with_expansion(self, captured_shell, pu):
        captured_shell.run_command(f'v=hi; printf \'<%s>\' {pu}"$v"{{a,b}}')
        assert captured_shell.get_stdout() == f"<{pu}hia><{pu}hib>"

    def test_pu_as_list_items(self, captured_shell):
        captured_shell.run_command(f"printf '<%s>' {{{E000},{E001}}}")
        assert captured_shell.get_stdout() == f"<{E000}><{E001}>"

    def test_pu_only_word_no_brace_unchanged(self, captured_shell):
        captured_shell.run_command(f"printf '<%s>' {F8FF}{F8FF}")
        assert captured_shell.get_stdout() == f"<{F8FF}{F8FF}>"


class TestRangeEmptyWithPrivateUse:
    def test_cross_case_range_keeps_backslash_empty(self, captured_shell):
        # bash: {Z..a} keeps the backslash position (ASCII 92) as an empty word.
        captured_shell.run_command("printf '<%s>' {Z..a}")
        assert captured_shell.get_stdout() == "<Z><[><><]><^><_><`><a>"

    def test_f8ff_prefix_on_cross_case_range(self, captured_shell):
        # The literal U+F8FF prefix must survive AND the backslash-empty be kept.
        captured_shell.run_command(f"printf '<%s>' {F8FF}{{Z..a}}")
        expected = ''.join(f"<{F8FF}{c}>" for c in ['Z', '[', '', ']',
                                                    '^', '_', '`', 'a'])
        assert captured_shell.get_stdout() == expected

    def test_f8ff_in_numeric_range_word(self, captured_shell):
        captured_shell.run_command(f"printf '<%s>' x{F8FF}{{1..3}}")
        assert captured_shell.get_stdout() == (
            f"<x{F8FF}1><x{F8FF}2><x{F8FF}3>")


class TestNoRegressionForOrdinaryInput:
    def test_plain_list(self, captured_shell):
        captured_shell.run_command("printf '<%s>' {a,b,c}")
        assert captured_shell.get_stdout() == "<a><b><c>"

    def test_numeric_range(self, captured_shell):
        captured_shell.run_command("printf '<%s>' {1..4}")
        assert captured_shell.get_stdout() == "<1><2><3><4>"

    def test_composite_with_expansion(self, captured_shell):
        captured_shell.run_command('f=F; printf \'<%s>\' "$f"{1,2}')
        assert captured_shell.get_stdout() == "<F1><F2>"
