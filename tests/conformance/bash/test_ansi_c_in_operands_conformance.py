r"""Conformance: ANSI-C ``$'...'`` decoded inside parameter-expansion operands,
and the full ``${var@E}`` escape set.

bash decodes ``$'...'`` (ANSI-C quoting) when it appears inside a
parameter-expansion operand — the default value (``${x:-$'\t'}``), a pattern
(``${x#$'\t'}``, ``${x/$'\t'/...}``), and a replacement (``${x/b/$'\t'}``).
And ``${var@E}`` applies the *full* ANSI-C escape set. psh previously left
``$'...'`` literal in operands and had an incomplete ``@E`` decoder (no octal /
``\cX`` / ``\u`` / ``\U``). Regression pin for reappraisal #10 R12.A; the fix
routes every site through the one canonical decoder
(``lexer/pure_helpers.handle_ansi_c_escape``).
"""


from conformance_framework import ConformanceTest


class TestAnsiCInOperandsConformance(ConformanceTest):
    """``$'...'`` is decoded in default/pattern/replacement operands."""

    def test_default_value_ansi_c_tab(self):
        self.assert_identical_behavior(r"""unset x; printf '%s' "${x:-$'\t'}" """)

    def test_default_value_ansi_c_newline(self):
        self.assert_identical_behavior(r"""unset x; printf '%s' "${x:-$'a\nb'}" """)

    def test_prefix_strip_ansi_c_tab(self):
        self.assert_identical_behavior(r"""x=$'\tfoo'; printf '%s' "${x#$'\t'}" """)

    def test_patsub_match_ansi_c_tab(self):
        self.assert_identical_behavior(r"""x=$'a\tb'; printf '%s' "${x/$'\t'/X}" """)

    def test_replacement_to_ansi_c_tab(self):
        self.assert_identical_behavior(r"""x=abc; printf '%s' "${x/b/$'\t'}" """)


class TestVarTransformEConformance(ConformanceTest):
    """``${var@E}`` applies the full ANSI-C escape set."""

    def test_e_simple_escapes(self):
        self.assert_identical_behavior(r'''x='a\tb\nc'; printf '%s' "${x@E}" ''')

    def test_e_octal(self):
        self.assert_identical_behavior(r'''x='\101\102'; printf '%s' "${x@E}" ''')

    def test_e_control_char(self):
        self.assert_identical_behavior(r'''x='\cI'; printf '%s' "${x@E}" ''')

    def test_e_hex(self):
        self.assert_identical_behavior(r'''x='\x41\x42'; printf '%s' "${x@E}" ''')
