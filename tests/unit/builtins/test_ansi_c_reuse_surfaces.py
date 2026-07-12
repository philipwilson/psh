r"""Four-surface ANSI-C ``$'...'`` reuse convergence (T11).

bash 5.2 renders ONE ``$'...'`` shape for a control-char value across every
reusable-output surface — ``${var@Q}``, ``printf %q``, ``declare -p`` and the
``set`` listing (octal ``\NNN`` for controls, named where bash has them,
``\E`` for ESC). Before T11 psh emitted THREE divergent shapes (hex via
``printf %q``, octal-no-``\E`` via ``@Q``, octal+``\E`` via declare/set); the
encoder is now the single ``ansi_c_encode`` authority so all four agree.

Probed byte-exact against bash 5.2 (tmp/r19-ledgers/T11-probes, 2026-07-12).
"""

import pytest


def _surface(shell, setexpr, tail):
    shell.clear_output()
    assert shell.run_command(f"{setexpr}; {tail}") == 0
    return shell.get_stdout()


def _set_line(shell, setexpr):
    """The `set` listing line for variable v (strip the rest of the dump)."""
    shell.clear_output()
    assert shell.run_command(f"{setexpr}; set") == 0
    for line in shell.get_stdout().splitlines():
        if line.startswith('v='):
            return line
    raise AssertionError("no v= line in set output")


# (value-construction, expected one-shape $'...' body) — matches bash 5.2.
CASES = [
    (r"v=$'\x01'",          r"$'\001'"),
    (r"v=$'\x1b'",          r"$'\E'"),
    (r"v=$'\x7f'",          r"$'\177'"),
    (r"v=$'a\nb'",          r"$'a\nb'"),
    (r"v=$'a\tb'",          r"$'a\tb'"),
    (r"v=$'a\x07b'",        r"$'a\ab'"),
    (r"v=$'a\x01b\x1bc'",   r"$'a\001b\Ec'"),
]


class TestFourSurfaceConvergence:
    @pytest.mark.parametrize("setexpr,shape", CASES)
    def test_all_four_surfaces_render_one_shape(self, captured_shell, setexpr, shape):
        atq = _surface(captured_shell, setexpr, 'printf "%s" "${v@Q}"')
        pq = _surface(captured_shell, setexpr, 'printf "%q" "$v"')
        declp = _surface(captured_shell, setexpr, 'declare -p v')
        setl = _set_line(captured_shell, setexpr)

        assert atq == shape, f"@Q: {atq!r} != {shape!r}"
        assert pq == shape, f"printf %q: {pq!r} != {shape!r}"
        assert declp == f"declare -- v={shape}\n", f"declare -p: {declp!r}"
        assert setl == f"v={shape}", f"set: {setl!r}"


class TestRedOnBaseShapes:
    """The specific divergences the fix closes (pre-fix these disagreed)."""

    def test_printf_q_was_hex_now_octal(self, captured_shell):
        # pre-fix: $'\x01\x1b'
        assert _surface(captured_shell, r"v=$'\x01\x1b'",
                        'printf "%q" "$v"') == r"$'\001\E'"

    def test_at_q_was_octal_esc_now_E(self, captured_shell):
        # pre-fix: $'\001\033'
        assert _surface(captured_shell, r"v=$'\x01\x1b'",
                        'printf "%s" "${v@Q}"') == r"$'\001\E'"
