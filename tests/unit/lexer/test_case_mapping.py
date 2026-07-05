"""Unit tests for length-safe (single-codepoint) case mapping.

bash's case-mod (${x^^}, declare -u) maps each codepoint to at most one
codepoint (C-library towupper/towlower). Python's str.upper()/str.lower()
apply the *full* Unicode mappings, which can GROW the string (ß -> "SS",
ﬀ -> "FF", İ -> "i̇"). psh reproduces the length-safe simple mapping; see
psh/lexer/unicode_support.py. Pinned against bash 5.2 for the codepoints that
agree across libc versions (ASCII, Latin-1, ß, ﬀ, İ, main Greek/Cyrillic).
"""

from psh.lexer.unicode_support import simple_lower, simple_upper, toggle_case


class TestLengthSafety:
    """No codepoint is ever expanded to more than one codepoint."""

    def test_sharp_s_upper_unchanged(self):
        # str.upper() would give "SS" (grows length); bash keeps ß.
        assert simple_upper("straße") == "STRAßE"

    def test_sharp_s_lower_roundtrip(self):
        assert simple_lower("STRAßE") == "straße"

    def test_ff_ligature_upper_unchanged(self):
        # str.upper() would give "FF".
        assert simple_upper("ﬀ") == "ﬀ"

    def test_dotted_capital_i_lower_is_plain_i(self):
        # str.lower() gives 'i' + combining dot (2 codepoints); simple = 'i'.
        assert simple_lower("İ") == "i"
        assert len(simple_lower("İ")) == 1

    def test_iota_dialytika_tonos_upper_unchanged(self):
        # U+0390 ΐ: full upper is 3 codepoints; simple keeps it.
        assert simple_upper("ΐ") == "ΐ"

    def test_all_mappings_length_preserving(self):
        # Exhaustive guard: neither mapping ever changes the codepoint count.
        for cp in range(0x110000):
            c = chr(cp)
            assert len(simple_upper(c)) == 1, hex(cp)
            assert len(simple_lower(c)) == 1, hex(cp)
            assert len(toggle_case(c)) == 1, hex(cp)


class TestCommonMappings:
    """Everyday characters still map exactly like bash."""

    def test_ascii_upper(self):
        assert simple_upper("hello world") == "HELLO WORLD"

    def test_ascii_lower(self):
        assert simple_lower("HELLO WORLD") == "hello world"

    def test_accented_upper(self):
        assert simple_upper("café") == "CAFÉ"

    def test_accented_lower(self):
        assert simple_lower("CAFÉ") == "café"

    def test_greek(self):
        assert simple_lower("Ω") == "ω"
        assert simple_upper("ω") == "Ω"

    def test_cyrillic(self):
        assert simple_upper("привет") == "ПРИВЕТ"
        assert simple_lower("ПРИВЕТ") == "привет"


class TestToggle:
    """toggle_case flips each codepoint (bash's iswupper test)."""

    def test_ascii_mixed(self):
        assert toggle_case("HeLLo123") == "hEllO123"

    def test_upper_to_lower(self):
        assert toggle_case("ABC") == "abc"

    def test_lower_to_upper(self):
        assert toggle_case("abc") == "ABC"

    def test_accented(self):
        assert toggle_case("Café") == "cAFÉ"

    def test_dotted_capital_i_toggles_to_i(self):
        # İ is uppercase → lowercased via the length-safe rule to plain 'i'.
        assert toggle_case("İ") == "i"

    def test_sharp_s_stays(self):
        # ß has no single-codepoint uppercase → toggling leaves it.
        assert toggle_case("ß") == "ß"
