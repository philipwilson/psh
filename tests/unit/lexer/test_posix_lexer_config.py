"""POSIX mode reaches the lexer configuration (defect D3).

`_make_config` derives `LexerConfig.posix_mode` from the active shell options
(`set -o posix`), so the lexer's POSIX-aware identifier paths — previously dead
because `posix_mode` was never set on the public path — now activate. Under
posix the lexer restricts identifiers to the ASCII portable set, consistent
with the executor/state-layer name validation (T3-5). With posix OFF (the
default) tokenization is byte-identical to before — psh's documented lenient
Unicode-identifier extension still applies.

bash cannot be used as an oracle here: it classifies identifier bytes, not
codepoints, so its Unicode-name behavior is locale-dependent byte-soup that psh
(codepoint-aware) deliberately does not reproduce. These tests therefore pin
psh's own posix-vs-nonposix contract at the token level.
"""

import pytest

# POSIX name-truncation is a RECOGNIZER behavior; assert on the pre-fusion
# stream (word fusion composites adjacent word-like tokens in public tokenize()).
from lexer_test_helpers import tokenize_unfused as tokenize  # noqa: E402

from psh.lexer import _make_config
from psh.lexer.token_types import TokenType


def _types(text, **kw):
    return [(t.type, t.value) for t in tokenize(text, **kw) if t.type != TokenType.EOF]


# --- _make_config derives posix_mode from shell options ---------------------

def test_make_config_default_posix_off():
    assert _make_config().posix_mode is False
    assert _make_config(None).posix_mode is False


def test_make_config_posix_from_shell_options():
    assert _make_config({"posix": True}).posix_mode is True
    assert _make_config({"posix": False}).posix_mode is False
    assert _make_config({}).posix_mode is False


# --- lexer identifier behavior gated on posix -------------------------------

def test_unicode_variable_expansion_default_is_variable():
    """Non-posix (default): `$ünïcödé` is a single VARIABLE expansion."""
    types = _types("echo $ünïcödé")
    assert (TokenType.VARIABLE, "ünïcödé") in types


def test_unicode_variable_expansion_posix_is_literal():
    """Posix: `$ünïcödé` is NOT a valid expansion — `$` is a literal word char,
    so no VARIABLE token is emitted for the Unicode name."""
    types = _types("echo $ünïcödé", shell_options={"posix": True})
    assert (TokenType.VARIABLE, "ünïcödé") not in types
    assert not any(t == TokenType.VARIABLE for t, _ in types)


def test_ascii_variable_unchanged_in_both_modes():
    """ASCII `$x` is a VARIABLE in BOTH modes (posix restricts only non-ASCII)."""
    off = _types("echo $x", shell_options={"posix": False})
    on = _types("echo $x", shell_options={"posix": True})
    assert (TokenType.VARIABLE, "x") in off
    assert (TokenType.VARIABLE, "x") in on


def test_mixed_name_truncates_at_non_ascii_under_posix():
    """Posix: `$aünb` reads only the ASCII prefix `a` as the variable name."""
    types = _types("echo $aünb", shell_options={"posix": True})
    assert (TokenType.VARIABLE, "a") in types
    assert (TokenType.VARIABLE, "aünb") not in types


@pytest.mark.parametrize("opts", [None, {}, {"posix": False}, {"extglob": True}])
def test_posix_off_variants_all_lenient(opts):
    """Every non-posix option shape keeps the lenient Unicode name (invariant:
    posix OFF is unchanged)."""
    types = _types("echo $ünïcödé", shell_options=opts)
    assert (TokenType.VARIABLE, "ünïcödé") in types
