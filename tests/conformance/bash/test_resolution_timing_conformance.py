"""Resolution-authority timing conformance — the A8 ordering matrix (HIGH-3).

A command's prefix assignments expand left to right, and a value's expansion
can perform a shell-state side effect. When that side effect is a write to
``POSIXLY_CORRECT`` (arithmetic assignment, ``${v:=}`` store, at any nesting
depth) it enables POSIX mode, under which a special builtin outranks a
same-named function. psh resolved the command BEFORE expanding the values, so
the dispatch was decided from stale state:

    eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN-PATH"
    bash 5.2.26: BUILTIN-PATH        psh at 241a923c: FN

The R3 slot's ``CommandEnvOverlay.has_posix_override`` detects a
``POSIXLY_CORRECT`` prefix by NAME, which cannot see a side effect inside the
VALUE of a differently-named prefix. Slot 3.4 splits the prefix application
into a two-phase transaction (``expand_prefix`` → resolve → ``commit_prefix``)
so resolution reads authoritative state.

Every row here was probed against live bash 5.2.26 at base 241a923c
(raw stdout/stderr/rc pairs in tmp/a8/raw_b*.json; post-fix pairs in
tmp/a8/fix_*.json). Rows marked RED-ON-BASE diverged at base; rows marked
PARITY matched at base and are no-regression pins — the matrix is both a
red-on-base battery and its own regression baseline.

Two divergences the matrix surfaced are NOT this slot's defect and are pinned
at the bottom as explicit both-sides tests (house style): posix-mode
function-name validation, and posix special-builtin redirection errors not
being fatal.
"""
from pathlib import Path
from typing import NamedTuple

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

PSH_ROOT = Path(__file__).resolve().parents[3]


def _psh(cmd, parser=None):
    argv = ['-c', cmd] if parser is None else ['--parser', parser, '-c', cmd]
    r = run_psh(argv, cwd=PSH_ROOT, timeout=15)
    assert is_comparable(r), r
    return r


def _bash(cmd):
    r = run_bash(['-c', cmd], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(r), r
    return r


def _both(cmd):
    """(psh, bash) results for identical ``-c`` runs, rd parser."""
    return _psh(cmd), _bash(cmd)


def _err_tail(result):
    """The diagnostic minus its shell-name prefix.

    psh writes ``psh: line 1: ...`` where bash writes ``<argv0>: line 1: ...``;
    the prefix difference is documented convention, so equality rows compare
    everything after the first ``: ``.
    """
    text = result.stderr.strip()
    return text.split(': ', 1)[1] if ': ' in text else text


def _assert_same(cmd):
    """psh and bash agree on stdout, exit status, and diagnostic tail."""
    p, b = _both(cmd)
    assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (
        f"cmd={cmd!r}\npsh ={p.stdout!r} rc={p.returncode} err={p.stderr!r}\n"
        f"bash={b.stdout!r} rc={b.returncode} err={b.stderr!r}")
    assert _err_tail(p) == _err_tail(b), (
        f"cmd={cmd!r}\npsh err={p.stderr!r}\nbash err={b.stderr!r}")


# ---------------------------------------------------------------------------
# Signature family — RED ON BASE (bash BUILTIN-PATH / psh FN)
# ---------------------------------------------------------------------------

SIGNATURE_CELLS = [
    pytest.param(
        'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN-PATH"',
        id='arith-assign'),
    pytest.param(
        'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
        'A=${POSIXLY_CORRECT:=1} eval "echo BUILTIN-PATH"',
        id='colon-equals-store'),
]


@pytest.mark.parametrize('cmd', SIGNATURE_CELLS)
def test_signature_side_effect_flips_posix_before_resolution(cmd):
    """RED ON BASE. The side effect enables posix mode, so the special builtin
    outranks the shadowing function — for the very command whose prefix did it."""
    p, b = _both(cmd)
    assert b.stdout == 'BUILTIN-PATH\n', b
    assert p.stdout == b.stdout


def test_name_level_prefix_still_resolves_in_posix_mode():
    """PARITY. The R3 name-level overlay path — must not regress."""
    _assert_same('eval(){ echo FN; }; POSIXLY_CORRECT=1 eval "echo B"')


@pytest.mark.parametrize('cmd', [
    pytest.param('eval(){ echo FN; }; A=1 eval "echo B"', id='no-side-effect'),
    pytest.param('eval(){ echo FN; }; A=$((Q=1)) eval "echo B"',
                 id='arith-write-to-other-name'),
    pytest.param('unset POSIXLY_CORRECT; eval(){ echo FN; }; '
                 'A=${POSIXLY_CORRECT+set} eval "echo B"', id='no-store-alt'),
])
def test_function_wins_without_a_posix_store(cmd):
    """PARITY controls: absent a POSIXLY_CORRECT STORE the function still wins."""
    p, b = _both(cmd)
    assert b.stdout == 'FN\n', b
    assert p.stdout == b.stdout


# ---------------------------------------------------------------------------
# Side-effect KIND axis — every in-process store flips (RED ON BASE)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('prefix', [
    pytest.param('A=$((POSIXLY_CORRECT=1))', id='arith-assign'),
    pytest.param('A=$((POSIXLY_CORRECT+=1))', id='arith-plus-equals'),
    pytest.param('A=$((POSIXLY_CORRECT++))', id='arith-postincrement'),
    pytest.param('A=${POSIXLY_CORRECT:=1}', id='colon-equals'),
    pytest.param('A=${POSIXLY_CORRECT:=}', id='colon-equals-EMPTY'),
    pytest.param('A=${POSIXLY_CORRECT=1}', id='equals-unset-only'),
])
def test_store_kind_flips_posix(prefix):
    """RED ON BASE. Any in-process store counts — including an EMPTY value
    (bash's coupling is presence-level, not value-level)."""
    cmd = f'unset POSIXLY_CORRECT; eval(){{ echo FN; }}; {prefix} eval "echo B"'
    p, b = _both(cmd)
    assert b.stdout == 'B\n', b
    assert p.stdout == b.stdout


def test_store_nested_inside_another_expansion_flips():
    """RED ON BASE. Nesting depth is not a limiter: the arithmetic write sits
    inside a ``:=`` default."""
    cmd = ('unset POSIXLY_CORRECT Z; eval(){ echo FN; }; '
           'A=${Z:=$((POSIXLY_CORRECT=1))} eval "echo B"')
    p, b = _both(cmd)
    assert b.stdout == 'B\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    pytest.param('unset POSIXLY_CORRECT; eval(){ echo FN; }; '
                 'A=$(POSIXLY_CORRECT=1; echo x) eval "echo B"', id='plain'),
    pytest.param('unset POSIXLY_CORRECT; eval(){ echo FN; }; '
                 'A=$(export POSIXLY_CORRECT=1; echo x) eval "echo B"',
                 id='exported'),
])
def test_command_substitution_is_not_a_resolution_input(cmd):
    """PARITY, and load-bearing for the design: a command substitution FORKS,
    so its write never reaches the parent and posix never flips. This is why
    the permitted-side-effects set is in-process stores only."""
    p, b = _both(cmd)
    assert b.stdout == 'FN\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('position,cmd', [
    ('first', 'A=$((POSIXLY_CORRECT=1)) B=2 C=3'),
    ('middle', 'B=2 A=$((POSIXLY_CORRECT=1)) C=3'),
    ('last', 'B=2 C=3 A=$((POSIXLY_CORRECT=1))'),
])
def test_store_position_in_the_prefix_list_is_not_a_limiter(position, cmd):
    """RED ON BASE. A side effect in the LAST prefix still flips resolution —
    so resolution must follow the last expansion, not the first."""
    full = f'eval(){{ echo FN; }}; {cmd} eval "echo B"'
    p, b = _both(full)
    assert b.stdout == 'B\n', b
    assert p.stdout == b.stdout


# ---------------------------------------------------------------------------
# Resolution TARGET KIND axis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd', [
    pytest.param('eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo S"',
                 id='eval'),
    pytest.param(':(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) : ; echo "rc=$?"',
                 id='colon'),
    pytest.param('export(){ echo FN; }; unset V; '
                 'A=$((POSIXLY_CORRECT=1)) export V=1; echo "V=[${V-UNSET}]"',
                 id='export'),
    pytest.param('W=keep; unset(){ echo FN; }; '
                 'A=$((POSIXLY_CORRECT=1)) unset W; echo "W=[${W-UNSET}]"',
                 id='unset'),
    pytest.param('set(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) set -- x y; '
                 'echo "1=[$1]"', id='set'),
    pytest.param('shift(){ echo FN; }; set -- a b c; '
                 'A=$((POSIXLY_CORRECT=1)) shift; echo "1=[$1]"', id='shift'),
    pytest.param('exec(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) exec /bin/echo X; '
                 'echo AFTER', id='exec'),
    pytest.param('break(){ echo FN; }; for i in 1 2 3; do '
                 'A=$((POSIXLY_CORRECT=1)) break; done; echo "i=[$i]"',
                 id='break'),
    pytest.param('return(){ echo FN; }; '
                 'g(){ A=$((POSIXLY_CORRECT=1)) return; echo NOTREACHED; }; g; '
                 'echo "rc=$?"', id='return'),
])
def test_function_shadowing_a_special_builtin_loses_after_the_flip(cmd):
    """RED ON BASE. The whole special-builtin family — posix reorders lookup
    only for these, which is why the divergence is target-kind shaped."""
    _assert_same(cmd)


def test_source_shadowed_by_a_function(tmp_path):
    """RED ON BASE. ``.`` is a special builtin too."""
    script = tmp_path / 'sourced.sh'
    script.write_text('echo SOURCED\n')
    cmd = (f'.(){{ echo FN; }}; A=$((POSIXLY_CORRECT=1)) . {script}')
    p, b = _both(cmd)
    assert b.stdout == 'SOURCED\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    pytest.param('f(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) f', id='plain-function'),
    pytest.param('pwd(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) pwd',
                 id='function-over-REGULAR-builtin'),
    pytest.param('unset A; A=$((POSIXLY_CORRECT=1)) eval "echo S"',
                 id='unshadowed-special'),
    pytest.param('A=$((POSIXLY_CORRECT=1)) pwd >/dev/null && echo RAN',
                 id='regular-builtin'),
    pytest.param('A=$((POSIXLY_CORRECT=1)) /bin/echo EXT', id='external'),
    pytest.param('eval(){ echo FN; }; '
                 'A=$((POSIXLY_CORRECT=1)) command eval "echo S"',
                 id='command-prefix'),
    pytest.param('eval(){ echo FN; }; '
                 'A=$((POSIXLY_CORRECT=1)) builtin eval "echo S"',
                 id='builtin-prefix'),
])
def test_target_kinds_posix_does_not_reorder(cmd):
    """PARITY controls. posix reorders ONLY special-builtin-vs-function, so a
    plain function and a function over a REGULAR builtin still win."""
    _assert_same(cmd)


def test_command_not_found_runs_the_side_effects_first():
    """PARITY. bash runs the prefix side effects, reports not-found, rc 127,
    and the store PERSISTS."""
    _assert_same(
        'unset POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz 2>/dev/null; '
        'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
        'shopt -qo posix && echo posix-ON || echo posix-OFF')


# ---------------------------------------------------------------------------
# PERSISTENCE — the flip wins for the command that flipped it
# ---------------------------------------------------------------------------

def test_own_flip_makes_this_commands_prefix_persist():
    """RED ON BASE, and new territory: the mid-prefix flip and the POSIX
    special-builtin persistence rule interact, and the flip wins — the
    flipping command's OWN prefix persists."""
    cmd = ('unset POSIXLY_CORRECT A; A=$((POSIXLY_CORRECT=1)) eval ":"; '
           'echo "A=[${A-UNSET}]"')
    p, b = _both(cmd)
    assert b.stdout == 'A=[1]\n', b
    assert p.stdout == b.stdout


def test_own_flip_persistence_with_a_shadowing_function():
    """RED ON BASE. Same, where a function shadowed the special builtin."""
    cmd = ('unset POSIXLY_CORRECT A; eval(){ echo FN; }; '
           'A=$((POSIXLY_CORRECT=1)) eval ":"; echo "A=[${A-UNSET}]"')
    p, b = _both(cmd)
    assert b.stdout == 'A=[1]\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('target,cmd', [
    ('regular-builtin', 'A=$((POSIXLY_CORRECT=1)) pwd >/dev/null'),
    ('function', 'f(){ :; }; A=$((POSIXLY_CORRECT=1)) f'),
    ('external', 'A=$((POSIXLY_CORRECT=1)) /bin/echo x >/dev/null'),
    ('not-found', 'A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz 2>/dev/null'),
])
def test_flip_does_not_make_non_special_prefixes_persist(target, cmd):
    """PARITY. Persistence is the POSIX SPECIAL BUILTIN rule only."""
    full = f'unset POSIXLY_CORRECT A; {cmd}; echo "A=[${{A-UNSET}}]"'
    p, b = _both(full)
    assert b.stdout == 'A=[UNSET]\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('cmd', [
    pytest.param('unset POSIXLY_CORRECT; eval(){ echo FN; }; '
                 'A=$((POSIXLY_CORRECT=1)) eval ":"; '
                 'echo "pc=[${POSIXLY_CORRECT-UNSET}]"', id='variable-persists'),
    pytest.param('unset POSIXLY_CORRECT; eval(){ echo FN; }; '
                 'A=$((POSIXLY_CORRECT=1)) eval ":"; '
                 'shopt -qo posix && echo posix-ON || echo posix-OFF',
                 id='option-persists'),
    pytest.param('unset POSIXLY_CORRECT; eval(){ echo FN; }; '
                 'A=${POSIXLY_CORRECT:=1} eval ":"; '
                 'echo "pc=[${POSIXLY_CORRECT-UNSET}]"', id='store-persists'),
])
def test_the_side_effect_itself_persists_after_the_command(cmd):
    """The write is a REAL variable store, not a temporary binding, so it and
    the option it couples outlive the command (``shopt -qo posix`` is the
    subshell-safe reader; ``set -o`` is masked)."""
    _assert_same(cmd)


@pytest.mark.parametrize('cmd', [
    pytest.param('set -o posix; unset A; A=v eval ":"; echo "A=[${A-UNSET}]"',
                 id='posix-special-persists'),
    pytest.param('unset A; A=v eval ":"; echo "A=[${A-UNSET}]"',
                 id='default-mode-temporary'),
])
def test_preexisting_special_builtin_persistence_family(cmd):
    """PARITY. The R3 destination semantics this timing fix feeds into."""
    _assert_same(cmd)


# ---------------------------------------------------------------------------
# POSIX DIRECTION — flip-ON only; flip-OFF is unreachable by construction
# ---------------------------------------------------------------------------

def test_already_posix_is_a_no_op():
    """PARITY. Function defined BEFORE posix (bash refuses the definition in
    posix mode — see the documented divergence at the bottom)."""
    _assert_same('eval(){ echo FN; }; set -o posix; '
                 'A=$((POSIXLY_CORRECT=1)) eval "echo S"')


def test_arithmetic_cannot_turn_posix_OFF():
    """PARITY. Assigning 0 still SETS the variable, and the coupling is
    presence-level — so posix stays ON. Together with the command-substitution
    row this is why flip-OFF mid-prefix is unreachable, not merely untested."""
    _assert_same('eval(){ echo FN; }; POSIXLY_CORRECT=1; '
                 'A=$((POSIXLY_CORRECT=0)) eval "echo S"; '
                 'echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
                 'shopt -qo posix && echo posix-ON || echo posix-OFF')


def test_command_substitution_unset_cannot_turn_posix_OFF():
    """PARITY. The ``unset`` runs in a subshell."""
    _assert_same('eval(){ echo FN; }; POSIXLY_CORRECT=1; '
                 'A=$(unset POSIXLY_CORRECT; echo x) eval "echo S"')


def test_set_plus_o_posix_unsets_the_variable():
    """PARITY. The reverse coupling direction."""
    _assert_same('POSIXLY_CORRECT=1; set +o posix; '
                 'echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
                 'shopt -qo posix && echo posix-ON || echo posix-OFF')


def test_name_level_zero_value_still_flips():
    """PARITY. Presence counts, not truthiness."""
    _assert_same('eval(){ echo FN; }; unset POSIXLY_CORRECT; '
                 'POSIXLY_CORRECT=0 eval "echo S"')


def test_readonly_posixly_correct_blocks_the_flip():
    """PARITY (R3 rule). The assignment fails, so posix never turns on."""
    _assert_same('unset POSIXLY_CORRECT; readonly POSIXLY_CORRECT; '
                 'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo S"; '
                 'echo "rc=$?"')


# ---------------------------------------------------------------------------
# Left-to-right visibility and non-posix side-effect targets — MUST NOT FLIP
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd', [
    pytest.param('unset A B; A=1 B=$A eval \'echo "B=[$B]"\'',
                 id='literal-left-to-right'),
    pytest.param('unset Z; A=$((Z=7)) B=$Z eval \'echo "B=[$B]"\'',
                 id='arith-write-read-by-later-prefix'),
    pytest.param('unset Z; A=${Z:=7} B=$Z eval \'echo "B=[$B]"\'',
                 id='store-read-by-later-prefix'),
    pytest.param('set -- a b c; unset IFS; A=${IFS:=-} B="$*" '
                 'eval \'echo "B=[$B]"\'', id='IFS-written-then-used'),
    pytest.param('A=$((PATH=0)) /bin/echo abs-path-works; echo "rc=$?"',
                 id='PATH-clobbered-by-arithmetic'),
])
def test_left_to_right_value_visibility(cmd):
    """PARITY. Each value sees the assignments to its left — the property the
    staging area exists to preserve while the transaction defers routing."""
    _assert_same(cmd)


def test_path_written_by_a_store_drives_the_external_search(tmp_path):
    """PARITY. A PATH written INSIDE a value still governs which external runs
    (the external strategy's PATH search is deferred to execute time)."""
    bindir = tmp_path / 'pd'
    bindir.mkdir()
    prog = bindir / 'mycmd_xyz'
    prog.write_text('#!/bin/sh\necho MINE\n')
    prog.chmod(0o755)
    cmd = (f'OLD=$PATH; unset PATH; A=${{PATH:=$OLD:{bindir}}} mycmd_xyz; '
           f'echo "rc=$?"')
    p, b = _both(cmd)
    assert b.stdout == 'MINE\nrc=0\n', b
    assert p.stdout == b.stdout


# ---------------------------------------------------------------------------
# Temp-env visibility per target kind
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd', [
    pytest.param('f(){ echo "A=[$A] B=[$B]"; }; unset A B POSIXLY_CORRECT; '
                 'A=$((POSIXLY_CORRECT=1)) B=2 f', id='function'),
    pytest.param('unset A B POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) B=2 '
                 'eval \'echo "A=[$A] B=[$B]"\'', id='special-builtin'),
    pytest.param('unset A B POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) B=2 '
                 '/bin/sh -c \'echo "A=[$A] B=[$B]"\'', id='external'),
    pytest.param('unset A POSIXLY_CORRECT; '
                 'A=$((POSIXLY_CORRECT=1)) eval \'declare -p A\'',
                 id='declare-p-inside-special'),
])
def test_temp_env_visibility_with_the_flip_mid_list(cmd):
    """PARITY. What the command SEES is unchanged by the reorder."""
    _assert_same(cmd)


# ---------------------------------------------------------------------------
# Carry #7 — RANDOM in a prefix masks the dynamic special (RED ON BASE)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    # `$b`-read rather than `printenv b`: the read form carries no PATH
    # assumption, so the row means the same thing on Linux (where the
    # nightly runs) as on the macOS gate. Its neighbours already use it.
    pytest.param('RANDOM=1 b=$RANDOM /bin/sh -c \'echo "$b"\'', '1\n',
                 id='external-b-read'),
    pytest.param('RANDOM=1 b=$RANDOM eval \'echo "b=[$b]"\'', 'b=[1]\n',
                 id='special-builtin'),
    pytest.param('RANDOM=1 b=$RANDOM /bin/sh -c \'echo "b=[$b]"\'', 'b=[1]\n',
                 id='external-env'),
    pytest.param('RANDOM=1 b=$RANDOM c=$RANDOM eval \'echo "b=[$b] c=[$c]"\'',
                 'b=[1] c=[1]\n', id='two-later-reads'),
])
def test_carry7_later_prefix_reads_the_masked_literal(cmd, expected):
    """RED ON BASE (carry #7). A later prefix value reads the LITERAL temp
    binding, not a generated number — the temp env masks the dynamic special.

    The two-reads row is also the no-second-expansion probe: re-expanding the
    values would advance the generator and produce ``c != b``.
    """
    p, b = _both(cmd)
    assert b.stdout == expected, b
    assert p.stdout == b.stdout


def test_carry7_function_target_was_already_correct():
    """PARITY. The function route already staged into a scope, which masks the
    special — this row is why the carry was target-kind shaped."""
    p, b = _both('f(){ echo "b=$b"; }; RANDOM=1 b=$RANDOM f')
    assert b.stdout == 'b=1\n', b
    assert p.stdout == b.stdout


def test_carry7_masking_family_still_green():
    """PARITY. The shipped ``RANDOM=5 f`` masking behaviour."""
    p, b = _both('f(){ echo "$RANDOM"; }; RANDOM=5 f')
    assert b.stdout == '5\n', b
    assert p.stdout == b.stdout


def test_carry7_seed_does_not_persist_after_the_command():
    """PARITY. The prefix is temporary: RANDOM keeps generating afterwards."""
    _assert_same('RANDOM=1 /bin/echo x >/dev/null; r1=$RANDOM; r2=$RANDOM; '
                 '[ "$r1" = "$r2" ] && echo SAME || echo DIFFERENT')


def test_seconds_in_prefix_is_documented_NON_COVERAGE():
    """ACCIDENTALLY GREEN — recorded, never counted as carry-#7 evidence.

    ``SECONDS=100 b=$SECONDS`` takes the identical route RANDOM does, but
    reading SECONDS immediately after seeding it to 100 returns 100 either
    way, so the route defect is invisible through this observable. It is kept
    as a parity row and is explicitly NOT proof that the masking works — the
    RANDOM rows above are.
    """
    _assert_same('SECONDS=100 b=$SECONDS eval \'echo "b=[$b]"\'')


# ---------------------------------------------------------------------------
# RO1 — a readonly target is refused before any write (RED ON BASE)
# ---------------------------------------------------------------------------

def test_readonly_declared_unset_refuses_a_function_prefix():
    """RED ON BASE. bash's SKIP-AND-CONTINUE shape, pinned exactly: the error
    is reported, the variable stays UNSET, the command still runs, rc 0.

    psh accepted the assignment at base because the function route's install
    consults a lookup that returns None for a declared-unset readonly cell,
    so the refusal never fired. The transaction now checks with a direct scope
    scan BEFORE any write.
    """
    p, b = _both('readonly RX; f(){ echo "RX=[${RX-UNSET}]"; }; RX=1 f; '
                 'echo "rc=$?"')
    assert b.stdout == 'RX=[UNSET]\nrc=0\n', b
    assert 'readonly variable' in b.stderr
    assert p.stdout == b.stdout
    assert _err_tail(p) == _err_tail(b)


@pytest.mark.parametrize('cmd', [
    pytest.param('RX=keep; readonly RX; f(){ echo "RX=[${RX-UNSET}]"; }; RX=1 f; '
                 'echo "rc=$?"', id='readonly-SET-over-function'),
    pytest.param('readonly RX; RX=1 eval \'echo "RX=[${RX-UNSET}]"\'; '
                 'echo "rc=$?"', id='readonly-UNSET-over-builtin'),
    pytest.param('readonly RX; RX=1 /bin/sh -c \'echo "RX=[${RX-UNSET}]"\'; '
                 'echo "rc=$?"', id='readonly-UNSET-over-external'),
])
def test_readonly_refusal_controls_must_stay_green(cmd):
    """PARITY controls for the RO1 fix — these already matched at base."""
    _assert_same(cmd)


@pytest.mark.parametrize('prefix,ident', [
    pytest.param('POSIXLY_CORRECT=1', 'name-level'),
    pytest.param('RX=$((POSIXLY_CORRECT=1))', 'value-side-arith'),
    pytest.param('RX=${POSIXLY_CORRECT:=1}', 'value-side-store'),
])
def test_readonly_refusal_does_not_flip_posix(prefix, ident):
    """A refused assignment must not enable posix, by either spelling.

    The row previously walked only the NAME-level form — the one spelling
    this slot did NOT need to fix — while the value-side spellings, which are
    the axis the slot exists for, went unpinned. They refuse for different
    reasons: the name-level flip is blocked because the binding is never
    installed, the value-side flip because the VALUE is never evaluated.
    """
    setup = ('readonly POSIXLY_CORRECT; ' if ident == 'name-level'
             else 'unset POSIXLY_CORRECT; readonly RX; ')
    _assert_same(f'{setup}f(){{ echo FN; }}; '
                 f'{{ {prefix} f; }} 2>/dev/null; echo "rc=$?"; '
                 'echo "pc=[${POSIXLY_CORRECT-UNSET}]"')


# ---------------------------------------------------------------------------
# INPUT MODE and PARSER axes (measured non-differentiating; pinned so)
# ---------------------------------------------------------------------------

MODE_CELLS = [
    pytest.param(
        'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo B"', 'B\n',
        id='signature-arith'),
    pytest.param(
        'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
        'A=${POSIXLY_CORRECT:=1} eval "echo B"', 'B\n', id='signature-store'),
    pytest.param('RANDOM=1 b=$RANDOM eval \'echo "b=[$b]"\'', 'b=[1]\n',
                 id='carry7'),
]


@pytest.mark.parametrize('cmd,expected', MODE_CELLS)
def test_signature_holds_in_script_mode(cmd, expected, tmp_path):
    script = tmp_path / 'probe.sh'
    script.write_text(cmd + '\n')
    p = run_psh([str(script)], cwd=PSH_ROOT, timeout=15)
    b = run_bash([str(script)], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(p) and is_comparable(b)
    assert b.stdout == expected, b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('cmd,expected', MODE_CELLS)
def test_signature_holds_under_the_combinator_parser(cmd, expected):
    p = _psh(cmd, parser='combinator')
    b = _bash(cmd)
    assert b.stdout == expected, b
    assert p.stdout == b.stdout


# ---------------------------------------------------------------------------
# DOCUMENTED DIVERGENCES — surfaced by this matrix, NOT this slot's defect.
# Both-sides pins so a successor slot sees the exact current shape.
# ---------------------------------------------------------------------------

def test_divergence_posix_mode_function_name_validation():
    """OUT OF CHARTER (slot 3.4 matrix cell X1).

    In posix mode bash refuses to DEFINE a function named after a special
    builtin; psh accepts it. This is function-definition validation, not
    resolution timing — it reproduces with no prefix and no side effect. It is
    why the ``already-posix`` rows above define the function first.
    """
    cmd = 'set -o posix; eval(){ echo FN; }; echo "rc=$?"'
    p, b = _both(cmd)
    assert b.returncode == 2 and b.stdout == ''
    assert 'is a special builtin' in b.stderr
    # psh's CURRENT shape — update this row when a successor slot fixes it.
    assert p.returncode == 0 and p.stdout == 'rc=0\n'


def test_divergence_posix_special_builtin_redirect_error_not_fatal():
    """OUT OF CHARTER (slot 3.4 matrix cell R4).

    POSIX makes a redirection error on a SPECIAL BUILTIN fatal to a
    non-interactive shell; bash exits, psh continues. Reproduces with posix
    PRE-SET and no prefix side effect, so it is destination semantics rather
    than resolution timing.
    """
    cmd = 'set -o posix; A=1 eval ":" > /nonexistent_dir_xyz/f; echo AFTER'
    p, b = _both(cmd)
    assert b.returncode == 1 and b.stdout == ''
    # psh's CURRENT shape — update this row when a successor slot fixes it.
    assert p.stdout == 'AFTER\n'


@pytest.mark.parametrize('cmd', [
    pytest.param('A=1 eval ":" > /nonexistent_dir_xyz/f; echo AFTER',
                 id='non-posix-special-builtin'),
    pytest.param('set -o posix; A=1 pwd > /nonexistent_dir_xyz/f; echo AFTER',
                 id='posix-regular-builtin'),
    pytest.param('unset POSIXLY_CORRECT A; '
                 'A=$((POSIXLY_CORRECT=1)) /bin/echo x > /nonexistent_dir_xyz/f; '
                 'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"',
                 id='flip-then-external'),
    pytest.param('unset POSIXLY_CORRECT; '
                 'A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz > /nonexistent_dir_xyz/f; '
                 'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"',
                 id='flip-then-not-found'),
])
def test_redirection_error_rows_that_do_agree(cmd):
    """PARITY. The redirect-error surface agrees everywhere EXCEPT the posix ×
    special-builtin cell isolated above — which bounds that divergence."""
    _assert_same(cmd)


# ---------------------------------------------------------------------------
# F-FAMILY (R5/SEM-1, R6 condition 1) — the staging container is invisible to
# whole-table ENUMERATION while the transaction is in flight, and a leaked
# staging scope is enumeration-INVISIBLE pollution, so its absence is pinned
# as hard as its invisibility.
# ---------------------------------------------------------------------------

# Every pattern is ANCHORED. An unanchored one matches the NAME inside another
# variable's VALUE — bash's own BASH_EXECUTION_STRING holds the script text, so
# `grep ' TQ='` scored a spurious hit and made a correct implementation look
# wrong. The forcing test below proves each enumerator can still return 1.
ENUMERATORS = [
    pytest.param("set | grep -c '^TQ='", id='set'),
    pytest.param("export -p | grep -cE '^(declare -x|export) TQ='", id='export-p'),
    pytest.param("declare -p 2>/dev/null | grep -cE '^declare -[^ ]* TQ='",
                 id='declare-p-no-name'),
]


@pytest.mark.parametrize('enumerator', ENUMERATORS)
def test_enumerator_can_see_an_installed_binding(enumerator):
    """FORCING CONTROL. Each enumerator above asserts a 0; an enumerator that
    can ONLY return 0 would pass those rows while proving nothing. Here the
    same command runs against a really-installed TQ and must report 1 in both
    shells."""
    p, b = _both(f'export TQ=1; {enumerator}')
    assert b.stdout == '1\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('enumerator', ENUMERATORS)
@pytest.mark.parametrize('staged', [1, 2], ids=['one-binding', 'two-bindings'])
def test_staged_bindings_are_invisible_to_enumeration(enumerator, staged):
    """RED ON TIP-AS-IS (round 1). A later prefix value's command substitution
    must NOT see bindings that are staged but not yet installed."""
    prefix = 'TQ=1 ' + ('TR=2 ' if staged == 2 else '')
    cmd = (f'unset TQ TR; {prefix}B=$({enumerator}) '
           f'/bin/sh -c \'echo "[$B]"\'')
    p, b = _both(cmd)
    assert b.stdout == '[0]\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('enumerator', ENUMERATORS)
def test_staged_bindings_invisible_to_enumeration_in_script_mode(enumerator,
                                                                 tmp_path):
    script = tmp_path / 'probe.sh'
    script.write_text(f'unset TQ; TQ=1 B=$({enumerator}) /bin/sh -c \'echo "[$B]"\'\n')
    p = run_psh([str(script)], cwd=PSH_ROOT, timeout=15)
    b = run_bash([str(script)], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(p) and is_comparable(b)
    assert b.stdout == '[0]\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('enumerator', ENUMERATORS)
@pytest.mark.parametrize('staged', [1, 2], ids=['one-binding', 'two-bindings'])
def test_staged_bindings_invisible_to_enumeration_FUNCTION_target(enumerator,
                                                                 staged):
    """RED ON BASE — and the only route where base was actually wrong.

    Base leaked here ([1]) while matching bash on the external route ([0]),
    so an external-only battery could never have caught it: it was
    red-on-round-1-tip but green-on-base, which is the wrong end to prove.
    TARGET KIND is this slot's own new axis and the battery has to walk it.
    """
    prefix = 'TQ=1 ' + ('TR=2 ' if staged == 2 else '')
    cmd = f'unset TQ TR; f(){{ echo "[$B]"; }}; {prefix}B=$({enumerator}) f'
    p, b = _both(cmd)
    assert b.stdout == '[0]\n', b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('enumerator', ENUMERATORS)
def test_staged_bindings_invisible_to_enumeration_in_stdin_mode(enumerator):
    """The third input mode (N4) — `-c` and script are covered above."""
    script = f'unset TQ; TQ=1 B=$({enumerator}) /bin/sh -c \'echo "[$B]"\'\n'
    p = run_psh([], cwd=PSH_ROOT, timeout=15, stdin_data=script)
    b = run_bash([], cwd=PSH_ROOT, timeout=15, stdin_data=script)
    assert is_comparable(p) and is_comparable(b)
    assert b.stdout == '[0]\n', b
    assert p.stdout == b.stdout


def test_function_body_DOES_enumerate_its_prefix_vars_after_adoption():
    """The other side of the flag: adoption is the only transition, and after
    it the function body enumerates its prefix vars (bash merges them into the
    call's locals). Invisibility must not leak past the staging window."""
    p, b = _both('f(){ set | grep -c "^TQ="; }; TQ=1 f')
    assert b.stdout == '1\n', b
    assert p.stdout == b.stdout


# ---------------------------------------------------------------------------
# SEM-3 (R6 condition 1c) — an expansion error in a 2nd+ prefix value must not
# leak the staging scope. Asserted on BOTH observables: enumeration is clean
# AND the scope stack is back where it started.
# ---------------------------------------------------------------------------

# SUBJECT SHAPE is load-bearing here. The error must fire on a LATER prefix,
# with at least one binding ALREADY STAGED — that staged binding is the thing
# that leaks. A construction whose error fires on the FIRST prefix has nothing
# staged and cannot leak, so it passes at a tip that IS leaking and proves
# nothing. Both rows below were verified to leak at round-1 tip 7952a721
# (`A-IN-ENUM` there, `A-NOT-IN-ENUM` here and in bash).
ERROR_PREFIXES = [
    pytest.param('unset A; A=1 B=$((1/0))', id='arith-error'),
    pytest.param('declare -n r=s; declare -n s=r; unset A; A=1 r=1',
                 id='nameref-cycle'),
]


@pytest.mark.parametrize('bad', ERROR_PREFIXES)
def test_expansion_error_does_not_leak_the_staging_scope(bad, tmp_path):
    """Post-error, a staged name must not appear in enumeration. A leaked
    staging scope would be INVISIBLE to enumeration itself, so this row is
    paired with the depth row below — neither alone would catch it."""
    script = tmp_path / 'probe.sh'
    script.write_text(f'{bad} /bin/echo x\n'
                      'set | grep -q "^A=" && echo A-IN-ENUM || echo A-NOT-IN-ENUM\n')
    p = run_psh([str(script)], cwd=PSH_ROOT, timeout=15)
    b = run_bash([str(script)], cwd=PSH_ROOT, timeout=15)
    assert is_comparable(p) and is_comparable(b)
    assert b.stdout.strip().endswith('A-NOT-IN-ENUM'), b
    assert p.stdout.strip().endswith('A-NOT-IN-ENUM'), p


@pytest.mark.parametrize('bad', ERROR_PREFIXES)
@pytest.mark.parametrize('mode', ['-c', 'script'])
def test_expansion_error_restores_scope_depth_and_leaves_no_staging_scope(
        bad, mode, tmp_path):
    """The invariant a behavioural probe cannot see: zero residual staging
    scopes AND the scope stack restored. Measured in-process, because a leaked
    flagged scope is by construction absent from every enumeration surface."""
    from psh.shell import Shell
    shell = Shell()
    try:
        sm = shell.state.scope_manager
        before = len(sm.scope_stack)
        shell.run_command(f'{bad} /bin/echo x')
        assert len(sm.scope_stack) == before, (
            f'scope stack grew: {before} -> {len(sm.scope_stack)}')
        assert not any(getattr(s, 'is_staging', False) for s in sm.scope_stack), (
            'a staging scope survived the command — enumeration-invisible '
            'pollution')
    finally:
        shell.close() if hasattr(shell, 'close') else None


# ---------------------------------------------------------------------------
# SEM-2 (R5, ruling (b) AMENDED) — a nameref-to-element prefix takes no route:
# no write-through, and no diagnostic. RED ON BASE (base wrote through and
# emitted a readonly diagnostic bash does not emit).
# ---------------------------------------------------------------------------

def test_nameref_to_element_prefix_is_visible_in_command():
    """The binding IS visible to the command through name lookup."""
    _assert_same('a=(x y); declare -n r=a[0]; r=NEW eval \'echo "[$r]"\'')


def test_nameref_to_element_prefix_does_not_write_through():
    """RED ON BASE. bash does not write through for the PREFIX form."""
    p, b = _both('a=(x y); declare -n r=a[0]; r=NEW /bin/echo run >/dev/null; '
                 'echo "a=(${a[*]})"')
    assert b.stdout == 'a=(x y)\n', b
    assert p.stdout == b.stdout


def test_nameref_to_element_prefix_emits_no_diagnostic_CONTROL():
    """PARITY CONTROL — passes at base too, so it is NOT red-on-base evidence.

    Relabelled: this row shipped claiming RED ON BASE while omitting the
    `readonly` that makes base diverge, i.e. a false red-claim standing in
    for an unpinned cell. The real D4 cell is the next test.
    """
    p, b = _both('a=(x y); declare -n r=a[0]; r=NEW /bin/echo run')
    assert b.stderr == '', b
    assert p.stderr == b.stderr
    assert p.stdout == b.stdout


def test_readonly_nameref_to_element_prefix_emits_no_diagnostic():
    """RED ON BASE (the real D4). With the array READONLY, base emitted
    `a: readonly variable`; bash is silent and so is the tip, because the
    prefix takes no route at all and never attempts the write."""
    p, b = _both('a=(x y); readonly a; declare -n r=a[0]; r=NEW eval "echo ran"')
    assert b.stdout == 'ran\n' and b.stderr == '', b
    assert p.stdout == b.stdout
    assert p.stderr == b.stderr


@pytest.mark.parametrize('cmd,expected', [
    pytest.param('a=(x y); a=NEW /bin/echo run >/dev/null; echo "a=(${a[*]})"',
                 'a=(x y)\n', id='array-object-append-non-destructive'),
    pytest.param('a=(x y); a[0]=NEW /bin/echo run >/dev/null 2>&1; '
                 'echo "a=(${a[*]})"', 'a=(x y)\n',
                 id='direct-subscript-rejected-upstream'),
])
def test_seed_route_controls_still_hold(cmd, expected):
    """CONTROL (R5 SEM-2 v): the SEED route still serves what it should.
    Dynamic specials are covered by the carry-#7 rows above."""
    p, b = _both(cmd)
    assert b.stdout == expected, b
    assert p.stdout == b.stdout


# ---------------------------------------------------------------------------
# NIT N2 — RO1's other observables. The headline row pins stdout+rc; these pin
# the rest of the shape so "skip and continue" is nailed down, not inferred.
# ---------------------------------------------------------------------------

def test_ro1_readonly_refusal_still_applies_the_other_assignments():
    """bash SKIPS the refused one and applies the rest — the command runs with
    a partial temp env, it is not aborted."""
    p, b = _both('readonly RX; f(){ echo "RX=[${RX-UNSET}] OK=[${OK-UNSET}]"; }; '
                 '{ RX=1 OK=2 f; } 2>/dev/null')
    assert b.stdout == 'RX=[UNSET] OK=[2]\n', b
    assert p.stdout == b.stdout


def test_ro1_readonly_refusal_leaves_no_residue_after_the_command():
    _assert_same('readonly RX; f(){ :; }; { RX=1 f; } 2>/dev/null; '
                 'echo "after=[${RX-UNSET}]"')


def test_ro1_readonly_refusal_diagnostic_is_emitted_once():
    """One diagnostic per refused assignment — not none, not per-phase twice
    (the two-phase split makes double-reporting the natural failure mode)."""
    p, b = _both('readonly RX; f(){ :; }; RX=1 f')
    assert b.stderr.count('readonly variable') == 1, b
    assert p.stderr.count('readonly variable') == 1, p


# ---------------------------------------------------------------------------
# NIT N8 — the value-side posix flip newly REACHES a pre-existing rc-shape
# divergence. The flip is this slot's; the rc 1-vs-127 gap is not — it
# reproduces identically at round-1 tip and via `set -o posix` with a
# name-level prefix, i.e. it predates the transaction work and is
# successor-owned. Pinned both-sides so the successor sees the exact shape,
# and so the newly-reachable route stays covered meanwhile.
# ---------------------------------------------------------------------------


def test_divergence_readonly_prefix_rc_under_a_value_side_flip():
    """OUT OF CHARTER (rc shape). A readonly prefix error alongside a
    value-side POSIXLY_CORRECT flip: both shells report the readonly error and
    abort the line (no AFTER), but bash exits 127 where psh exits 1."""
    cmd = ('unset POSIXLY_CORRECT; readonly RX 2>/dev/null; eval(){ echo FN; }; '
           'RX=1 A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN"; echo AFTER=$?')
    p, b = _both(cmd)
    # Agreed part: the diagnostic fires and the line dies before AFTER.
    assert 'readonly variable' in b.stderr and 'AFTER' not in b.stdout, b
    assert 'readonly variable' in p.stderr and 'AFTER' not in p.stdout, p
    # The divergence, pinned both sides. bash 127 / psh 1 — update when a
    # successor slot unifies the rc shape.
    assert b.returncode == 127, b
    assert p.returncode == 1, p


def test_nameref_cycle_prefix_matches_bash_end_to_end():
    """PARITY. What actually holds at this tip: warning text, continuation and
    rc all agree. Kept as no-regression coverage of the path SEM-3 touches."""
    _assert_same('declare -n a=b; declare -n b=a; A=1 B=$a /bin/echo ran; '
                 'echo AFTER')


# ---------------------------------------------------------------------------
# A8 AXIS — the command's OWN NAME VARIABLE (`c=echo; c=printf $c ...`).
#
# The amendment lists this axis and the round-1/round-2 matrices had ZERO
# cells for it: a dropped axis under a "matrix complete" claim. All four cells
# MATCH at base and at tip, so they are EQUALITY rows — the axis is covered by
# showing it does not move, which is a result, not an absence.
#
# What they pin: the command WORD is expanded before the prefix assignments
# apply, so `c=printf $c hi` still runs the OLD `c` (echo). The transaction
# reordered when values EXPAND, not when the command word does.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd', [
    pytest.param('c=echo; c=printf $c hi', id='prefix-rebinds-the-name-var'),
    pytest.param('unset c; c=/bin/echo $c x', id='name-var-unset-at-expansion'),
    pytest.param('c=echo; A=$((POSIXLY_CORRECT=1)) c=/bin/echo $c y',
                 id='name-var-rebound-under-a-value-side-flip'),
    pytest.param('eval(){ echo FN; }; '
                 'c=eval A=$((POSIXLY_CORRECT=1)) $c "echo VIA-NAMEVAR"',
                 id='name-var-naming-a-shadowed-special-under-a-flip'),
])
def test_command_own_name_variable_axis(cmd):
    """EQUALITY (matched at base and tip). Pinned so the axis stops being a
    gap in the matrix rather than a claim about it."""
    _assert_same(cmd)


# ---------------------------------------------------------------------------
# B1 (R14) — REFUSE BEFORE EVALUATE.
#
# bash never evaluates the value of an assignment it is going to refuse. psh
# evaluated first and refused after, so a refused prefix's value still ran its
# side effects; when one of those flipped posix, the refusal then took the
# POSIX prefix-error branch and ABORTED a statement bash runs. That was a
# regression born from the COMPOSITION of two in-slot fixes (the RO1 refusal
# and the value-side posix flip) — neither wrong alone.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('value', [
    pytest.param('$((POSIXLY_CORRECT=1))', id='arith-flip'),
    pytest.param('${POSIXLY_CORRECT:=1}', id='store-flip'),
])
@pytest.mark.parametrize('define,invoke', [
    pytest.param('f(){ echo FN; }', 'f', id='function'),
    pytest.param('eval(){ echo FN; }', 'eval "echo FN"',
                 id='function-shadowing-special'),
])
@pytest.mark.parametrize('extra', ['', 'C=3 '], ids=['alone', 'extra-prefix'])
def test_refused_prefix_does_not_flip_posix_or_abort(value, define, invoke,
                                                     extra):
    """RED ON ROUND-3 TIP (the regression) — the statement must still run,
    rc 0, and posix must stay OFF because the refused value was never
    evaluated."""
    cmd = (f'unset POSIXLY_CORRECT; readonly RX; {define}; '
           f'{extra}RX={value} {invoke}; '
           'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"')
    p, b = _both(cmd)
    assert 'rc=0' in b.stdout and 'pc=[UNSET]' in b.stdout, b
    assert p.stdout == b.stdout


@pytest.mark.parametrize('tail,ident', [
    pytest.param('f', 'function'),
    pytest.param('eval ":"', 'special-builtin-LAYER'),
    pytest.param('/bin/echo x >/dev/null', 'external'),
])
def test_refused_prefix_contributes_zero_side_effects(tail, ident):
    """RED ON BASE (declared toward-bash delta). The refused value's write
    must not happen at all: base left Z=9, bash and the tip leave it UNSET.
    This is the census row — a refused assignment contributes NO side
    effects, on every route."""
    cmd = f'unset Z; readonly RX; f(){{ :; }}; RX=$((Z=9)) {tail}; echo "Z=[${{Z-UNSET}}]"'
    p, b = _both(cmd)
    assert 'Z=[UNSET]' in b.stdout, b
    assert p.stdout == b.stdout


def test_refused_prefix_value_is_invisible_to_later_prefixes():
    """Interleave cell: a refused assignment contributes nothing for a LATER
    prefix's expansion to read."""
    _assert_same('unset Z; readonly RX; RX=$((Z=9)) B=${Z-UNSET} '
                 'eval \'echo "B=[$B]"\'')


def test_refused_prefix_then_erroring_later_value_leaves_no_staging_scope():
    """COMPOSITION CELL (R14): B1's hoist and SEM-3's unwinding share phase 1.
    A refusal followed by an erroring value in a LATER prefix must still leave
    the scope stack restored and no staging scope behind."""
    from psh.shell import Shell
    shell = Shell()
    sm = shell.state.scope_manager
    before = len(sm.scope_stack)
    shell.run_command('readonly RX; unset A; RX=1 A=1 B=$((1/0)) /bin/echo x')
    assert len(sm.scope_stack) == before, (
        f'scope stack grew: {before} -> {len(sm.scope_stack)}')
    assert not any(getattr(s, 'is_staging', False) for s in sm.scope_stack)


# ---------------------------------------------------------------------------
# B3 (R14) — RO1's control-flow observables, all toward-bash, all declared.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('setup,ident', [
    pytest.param('set -e; ', 'errexit'),
    pytest.param('set -o posix; ', 'posix'),
])
def test_refused_prefix_control_flow_under_errexit_and_posix(setup, ident):
    """RED ON BASE. Base ran the function and continued (rc 0); bash and the
    tip abort the statement (rc 1)."""
    cmd = f'{setup}readonly RX; f(){{ echo FN; }}; RX=1 f; echo AFTER'
    p, b = _both(cmd)
    assert b.returncode == 1 and 'AFTER' not in b.stdout, b
    assert (p.stdout, p.returncode) == (b.stdout, b.returncode)


def test_declare_r_spelling_now_diagnoses_like_bash():
    """RED ON BASE — mislabelled as a CONTROL when first written.

    Its stdout leg does not move (`FN`/`AFTER`, rc 0 everywhere), which is
    what made it look like a control. Its STDERR leg does: base emitted no
    diagnostic at all where bash prints `RY: readonly variable`. It is a
    facet of the declared RO1 diagnostic fix, so it is tip-equality
    evidence, not a bounding row — and counting it as a control inflated the
    bounding set.
    """
    p, b = _both('declare -r RY; f(){ echo FN; }; RY=1 f; echo AFTER')
    assert 'readonly variable' in b.stderr, b
    assert p.stdout == b.stdout
    assert _err_tail(p) == _err_tail(b)


@pytest.mark.parametrize('cmd,ident', [
    pytest.param('readonly RX; RX=1 eval ":"; echo AFTER', 'LAYER-route'),
    pytest.param('RX=keep; readonly RX; f(){ echo FN; }; RX=1 f; echo AFTER',
                 'SET-readonly'),
])
def test_refused_prefix_control_flow_controls(cmd, ident):
    """The TWO genuine bounding controls — neither leg moved between base and
    tip, so the toward-bash rows above are bounded rather than open-ended."""
    _assert_same(cmd)


# ---------------------------------------------------------------------------
# B5 (R14) — the $((RANDOM)) axis: arithmetic-context read of a staged
# dynamic special. Dropped from the matrix; it hid an already-flipped row.
# ---------------------------------------------------------------------------

def test_arithmetic_context_read_of_a_staged_dynamic_special():
    """RED ON BASE. `RANDOM=1 b=$((RANDOM))` — bash 1, base 10791, tip 1.
    Fixed by the staging mask, but on an axis the matrix never walked, so it
    was an unpinned toward-bash row until the harness found it."""
    p, b = _both('RANDOM=1 b=$((RANDOM)) eval \'echo "[$b]"\'')
    assert b.stdout == '[1]\n', b
    assert p.stdout == b.stdout


def test_arithmetic_context_read_function_target_CONTROL():
    """CONTROL — matched at base too."""
    _assert_same('f(){ echo "[$b]"; }; RANDOM=1 b=$((RANDOM)) f')


def test_nameref_prefix_target_is_preserved_not_destroyed():
    """N3 — the nameref itself survives a prefix write through it."""
    _assert_same('declare -n r=t; t=orig; r=NEW /bin/echo run >/dev/null; '
                 'declare -p r')


# ---------------------------------------------------------------------------
# DOCUMENTED DIVERGENCES added this round — pre-existing at BOTH ends, no
# in-slot fix (R14 B4 / N2). Successor-owned; see the ledger rows.
# ---------------------------------------------------------------------------

def test_divergence_nameref_to_element_prefix_invisible_to_a_function():
    """OUT OF CHARTER (B4). A nameref-to-element prefix IS visible to eval and
    to an external, but NOT to a function body: bash `r=[NEW]`, psh `r=[x]` at
    base and tip alike. Likely subsumed by Option (A)'s model work."""
    cmd = 'a=(x y); declare -n r=a[0]; f(){ echo "r=[$r]"; }; r=NEW f'
    p, b = _both(cmd)
    assert b.stdout == 'r=[NEW]\n', b
    # psh's CURRENT shape at both ends — update when a successor fixes it.
    assert p.stdout == 'r=[x]\n', p


def test_divergence_prefix_name_listing_during_staging():
    """OUT OF CHARTER (N2). `${!PREFIX*}` is a fourth whole-table surface that
    the staging scope does not hide: bash lists nothing mid-staging, psh lists
    the staged name — at base and tip alike. Deliberately NOT fixed in-slot:
    widening is_staging semantics mid-slot is the change R14 forbade."""
    cmd = 'unset TQ; TQ=1 B=$(echo ${!TQ*}) /bin/sh -c \'echo "[$B]"\''
    p, b = _both(cmd)
    assert b.stdout == '[]\n', b
    assert p.stdout == '[TQ]\n', p


# ---------------------------------------------------------------------------
# N10 — the signature cells in stdin mode. `-c` and script were covered from
# round 1; stdin is the third input mode and was never walked for these.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', MODE_CELLS)
def test_signature_holds_in_stdin_mode(cmd, expected):
    p = run_psh([], cwd=PSH_ROOT, timeout=15, stdin_data=cmd + '\n')
    b = run_bash([], cwd=PSH_ROOT, timeout=15, stdin_data=cmd + '\n')
    assert is_comparable(p) and is_comparable(b)
    assert b.stdout == expected, b
    assert p.stdout == b.stdout


def _assert_same_behaviour(cmd):
    """stdout + rc equality, plus diagnostic PRESENCE — not its wording.

    Used by the generated KIND family, where some kinds fail through psh's
    arithmetic/expansion error path. Those message SHAPES differ from bash by
    documented convention (`arithmetic error: Division by zero` vs
    `1/0: division by 0 (error token is "0")`) and are slot 3.5's territory,
    not this slot's. What this family is testing is whether the value was
    EVALUATED, which stdout, rc, and the presence of a diagnostic answer
    exactly; asserting the wording would make the family fail for a reason it
    is not about.
    """
    p, b = _both(cmd)
    assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (
        f"cmd={cmd!r}\npsh ={p.stdout!r} rc={p.returncode} err={p.stderr!r}\n"
        f"bash={b.stdout!r} rc={b.returncode} err={b.stderr!r}")
    assert bool(p.stderr.strip()) == bool(b.stderr.strip()), (
        f"cmd={cmd!r}: one shell diagnosed and the other did not\n"
        f"psh err={p.stderr!r}\nbash err={b.stderr!r}")


# ===========================================================================
# SIDE-EFFECT KIND FAMILY — GENERATED, not hand-enumerated (R18 B1/B2).
#
# This axis was dropped three times, the last time on the axis a ruling had
# just created. Hand-enumerated rows drop silently because nothing counts
# what is missing; a generated cross-product cannot, because adding a KIND
# row below automatically walks every route and both refusal states.
#
# The rule the family proves, on every kind: a REFUSED assignment's value is
# never evaluated, so it contributes NOTHING — no store, no command
# substitution, no fatal expansion, no trace line. bash is the oracle for
# each cell; base got most of them wrong in the same direction.
# ===========================================================================

class Kind(NamedTuple):
    """One side-effect kind plus the observable that detects evaluation."""
    ident: str
    setup: str      # runs before the command
    value: str      # the prefix VALUE whose evaluation we are detecting
    observe: str    # runs after; prints the evidence
    fatal: bool = False   # an unevaluated-vs-evaluated difference that
                          # ABORTS the shell when it does happen


SIDE_EFFECT_KINDS = [
    Kind('arith-assign', 'unset Z; ', '$((Z=9))', 'echo "Z=[${Z-UNSET}]"'),
    Kind('assign-default-store', 'unset Z; ', '${Z:=9}', 'echo "Z=[${Z-UNSET}]"'),
    Kind('arith-increment', 'unset Z; ', '$((Z+=9))', 'echo "Z=[${Z-UNSET}]"'),
    Kind('set-u-unbound', 'set -u; ', '$UNSETVAR', 'echo AFTER', fatal=True),
    Kind('param-null-fatal', '', '${NOPE?boom}', 'echo AFTER', fatal=True),
    Kind('arith-error-fatal', '', '$((1/0))', 'echo AFTER', fatal=True),
]

ROUTES = [
    pytest.param('f', id='function'),
    pytest.param('eval ":"', id='special-LAYER'),
    pytest.param('/bin/echo x >/dev/null', id='external'),
]


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('kind', SIDE_EFFECT_KINDS, ids=lambda k: k.ident)
def test_refused_prefix_evaluates_no_side_effect_kind(kind, route):
    """RED ON BASE for most kinds. A refused assignment contributes nothing,
    whatever the value's KIND and whatever the command resolves to."""
    cmd = (f'{kind.setup}readonly RX; f(){{ :; }}; '
           f'RX={kind.value} {route}; {kind.observe}')
    _assert_same_behaviour(cmd)


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('kind', SIDE_EFFECT_KINDS, ids=lambda k: k.ident)
def test_unrefused_prefix_DOES_evaluate_each_kind_CONTROL(kind, route):
    """CONTROL — the other half of every row above. Without the readonly the
    value IS evaluated, so the rows above are detecting the refusal rather
    than an observable that never fires."""
    cmd = (f'{kind.setup}unset RX; f(){{ :; }}; '
           f'RX={kind.value} {route}; {kind.observe}')
    _assert_same_behaviour(cmd)


@pytest.mark.parametrize('kind', [k for k in SIDE_EFFECT_KINDS if k.fatal],
                         ids=lambda k: k.ident)
@pytest.mark.parametrize('mode', ['file', 'stdin'])
def test_refused_prefix_fatal_kinds_do_not_abort_the_script(kind, mode,
                                                            tmp_path):
    """RED ON BASE, and the sharpest of the family: base ABORTED the script
    (rc 127 / rc 1, no output) where bash runs on. A script that used to stop
    now continues — a behaviour change that only shows up in file and stdin
    modes, which is why the fatal kinds carry the mode axis."""
    script = f'{kind.setup}readonly RX\nf(){{ echo FN; }}\nRX={kind.value} f\necho AFTER\n'
    if mode == 'file':
        path = tmp_path / 'probe.sh'
        path.write_text(script)
        p = run_psh([str(path)], cwd=PSH_ROOT, timeout=15)
        b = run_bash([str(path)], cwd=PSH_ROOT, timeout=15)
    else:
        p = run_psh([], cwd=PSH_ROOT, timeout=15, stdin_data=script)
        b = run_bash([], cwd=PSH_ROOT, timeout=15, stdin_data=script)
    assert is_comparable(p) and is_comparable(b)
    assert 'AFTER' in b.stdout, b
    assert (p.stdout, p.returncode) == (b.stdout, b.returncode)


def test_refused_prefix_command_substitution_never_runs(tmp_path):
    """RED ON BASE. The kind whose evidence is a side effect on the FILESYSTEM
    rather than in the shell: base ran the substitution, bash and the tip do
    not."""
    marker = tmp_path / 'ran'
    refused = f'readonly RX; f(){{ :; }}; RX=$(touch {marker}; echo x) f'
    p, b = _both(refused)
    assert is_comparable(p) and is_comparable(b)
    assert not marker.exists(), 'bash must not run a refused value'
    control = f'unset RX; f(){{ :; }}; RX=$(touch {marker}; echo x) f'
    _psh(control)
    assert marker.exists(), 'CONTROL: an unrefused value DOES run'


def test_refused_prefix_is_not_traced(tmp_path):
    """RED ON BASE, pinned on the TRACE — the observable that moved. Under
    `set -x` base emitted a `+` line for the assignment it then refused."""
    cmd = 'set -x; readonly RX; f(){ :; }; RX=1 B=2 f'
    p, b = _both(cmd)
    assert b.stderr.count('\n+ ') + b.stderr.startswith('+ ') > 0, b
    plus_b = len([ln for ln in b.stderr.splitlines() if ln.startswith('+')])
    plus_p = len([ln for ln in p.stderr.splitlines() if ln.startswith('+')])
    assert plus_p == plus_b, (
        f'trace line count differs: psh {plus_p} vs bash {plus_b}\n'
        f'psh:\n{p.stderr}\nbash:\n{b.stderr}')


# ---------------------------------------------------------------------------
# B3 (R18) — the NAMEREF spelling of the posix store. Away-from-bash, and
# newly REACHED by the reorder rather than caused by it: psh's posix hook
# couples on a nameref write-through where bash's does not. N8-class — pinned
# both sides, NOT fixed in-slot (the hook is core, shipped, and has its own
# family of pins).
# ---------------------------------------------------------------------------

def test_divergence_nameref_spelled_posix_store_flips_dispatch():
    """OUT OF CHARTER. bash: the write reaches POSIXLY_CORRECT but posix does
    NOT turn on, so the function still wins. psh couples on the write-through,
    so the special builtin wins. Base matched bash here only because it never
    looked at the value; the reorder makes the pre-existing hook divergence
    reach dispatch."""
    cmd = ('unset POSIXLY_CORRECT; declare -n npc=POSIXLY_CORRECT; '
           'eval(){ echo FN; }; A=$((npc=1)) eval "echo BP"')
    p, b = _both(cmd)
    assert b.stdout == 'FN\n', b
    # psh's CURRENT shape — this pin FLIPS when the hook is fixed, which is
    # the successor's obligation, not this slot's.
    assert p.stdout == 'BP\n', p


def test_nameref_name_level_posix_prefix_flips_in_BOTH_shells_CONTROL():
    """BOUNDING CONTROL. The name-level nameref spelling flips in bash too, so
    the divergence above is specific to the VALUE-side write-through and not
    to namerefs generally."""
    _assert_same('unset POSIXLY_CORRECT; declare -n npc=POSIXLY_CORRECT; '
                 'eval(){ echo FN; }; npc=1 eval "echo BP"')
