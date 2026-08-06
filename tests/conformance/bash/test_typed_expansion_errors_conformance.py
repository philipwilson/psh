"""Typed expansion/arithmetic error conformance — the MEDIUM-12b matrix.

Slot 3.5 replaced the broad/VT conversion nets on the expansion/arithmetic
error path with typed failures, and fixed the two EXIT-STATUS defects that
class of error carries. This battery pins the status model against live bash
5.2.26.

Two defect families, both status-only (the diagnostic TEXT matched bash at
base in every diverging cell — only the status was wrong):

**A10.1 — a forked child must not inherit the ``-c`` channel status.**
``fatal_expansion_status`` computes the shell-exit family's status from the
CHANNEL (127 under ``-c``, 1 for a script file / stdin) at the RAISE site, and
a forked child inherits ``command_mode`` — so psh's subshell died with 127
where bash's exits 1::

    bash -c '(echo ${x?boom}); echo "after rc=$?"'   ->  after rc=1
    psh  -c '(echo ${x?boom}); echo "after rc=$?"'   ->  after rc=127   (base)

Fixed by stamping the channel-derived status and re-mapping it at the fork
boundary through the ONE child-exit taxonomy
(``executor/child_policy.py#map_child_exception`` ->
``core/internal_errors.py#fatal_expansion_child_status``).

**Ruling (d) — errexit overrides the ``-c`` channel status.**
``bash -c 'set -e; echo ${x?boom}'`` exits **1**, not 127. Two properties of
this rule are load-bearing and BOTH DIRECTIONS are pinned below, because a
plausible misimplementation gets each one backwards:

* it reads the RAW errexit flag, NOT effective errexit — every suppressing
  context (``|| recover``, an ``if``/``while`` condition, ``!``, a non-final
  ``&&``) still yields 1 and none of them recovers. (Its sibling
  ``substitution_abort_status`` DOES subtract suppression; copying the sibling
  is the trap.) — ``TestErrexitIsRawFlagNotEffective``
* it is the CURRENT flag: ``set -e; set +e`` is back to 127. —
  ``TestErrexitFlagOffKeepsChannelStatus``

Every row was probed against live bash 5.2.26 at base 963c6eab (216-cell
matrix in tmp/a10/matrix.json; 24 cells diverged, all 24 are pinned here or
covered by the classes below) and re-run at the fix. Rows marked RED-ON-BASE
diverged at base; PARITY rows matched at base and are no-regression pins — the
battery is both a red-on-base battery and its own regression baseline.

Divergences NOT this slot's defect are pinned at the bottom as explicit
both-sides tests (house style): the PS4 + bad-subscript escape, which is a
successor row by integrator ruling, not an in-slot fix.
"""
import pytest
from shell_oracle import is_comparable, run_bash, run_psh

# The shell-exit ("fatal") expansion family: each entry is (id, setup+word).
# ``badname`` is in the family but its own exit_code is 1, so the -c channel
# never shows 127 for it — it is the family's control.
FATAL_CLASSES = [
    ("unset_q", "", "${x?boom}"),
    ("unset_colonq", "x=;", "${x:?boom}"),
    ("unknown_xform", "v=set;", "${v@Z}"),
]

# Boundaries that FORK. A fatal expansion inside one kills the child only.
FORK_BOUNDARIES = [
    ("subshell", "( echo {W} )"),
    ("cmdsub", "vv=$( echo {W} )"),
    ("backtick", "vv=`echo {W}`"),
]

# Boundaries that do NOT fork: the failure exits the whole shell.
NOFORK_BOUNDARIES = [
    ("direct", "echo {W}"),
    ("bracegroup", "{{ echo {W} ; }}"),
]


def _both(cmd):
    """Run one -c string in both shells; assert comparable; return (bash, psh)."""
    b = run_bash(["-c", cmd])
    p = run_psh(["-c", cmd])
    assert is_comparable(b), f"bash not comparable: {b}"
    assert is_comparable(p), f"psh not comparable: {p}"
    return b, p


def _assert_agree(cmd):
    """AGREEMENT form: psh's (stdout, status) equals bash's. Preferred over a
    fixed-status table so the pin tracks bash rather than a transcribed
    number."""
    b, p = _both(cmd)
    assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (
        f"cmd={cmd!r}\n bash: rc={b.returncode} out={b.stdout!r} "
        f"err={b.stderr!r}\n psh : rc={p.returncode} out={p.stdout!r} "
        f"err={p.stderr!r}")


class TestA101ForkBoundaryChildStatus:
    """RED-ON-BASE: the child's status must be 1, not the -c channel's 127."""

    @pytest.mark.parametrize("cls_id,setup,word",
                             FATAL_CLASSES, ids=[c[0] for c in FATAL_CLASSES])
    @pytest.mark.parametrize("b_id,tmpl", FORK_BOUNDARIES,
                             ids=[b[0] for b in FORK_BOUNDARIES])
    def test_after_marker_matches_bash(self, cls_id, setup, word, b_id, tmpl):
        # The 9 cells that diverged at base (3 classes x 3 fork boundaries).
        body = tmpl.format(W=word)
        _assert_agree(f'{setup}{body}; echo "after rc=$?"')

    @pytest.mark.parametrize("cls_id,setup,word",
                             FATAL_CLASSES, ids=[c[0] for c in FATAL_CLASSES])
    @pytest.mark.parametrize("b_id,tmpl", FORK_BOUNDARIES,
                             ids=[b[0] for b in FORK_BOUNDARIES])
    def test_child_status_read_through_suppression(self, cls_id, setup, word,
                                                   b_id, tmpl):
        """The child's OWN status, read through a suppressing ``||`` so the
        parent survives to report it."""
        body = tmpl.format(W=word)
        _assert_agree(f'{setup}{body} || echo "child rc=$?"')

    def test_errexit_inside_the_fork_does_not_change_the_child_status(self):
        """The sibling substitution_child_abort_status goes 1 -> 2 under
        errexit IN the child; this family does NOT. Pinning the difference so
        a future 'make it consistent with the sibling' bounces."""
        _assert_agree('( set -e; echo ${x?boom} ) || echo "child rc=$?"')


class TestA101NoForkBoundaryKeepsChannelStatus:
    """PARITY: without a fork there is no child, so the -c channel status
    (127) still applies. This is the other half of the A10.1 rule — a fix that
    simply made everything 1 would pass the class above and fail here."""

    @pytest.mark.parametrize("cls_id,setup,word",
                             FATAL_CLASSES, ids=[c[0] for c in FATAL_CLASSES])
    @pytest.mark.parametrize("b_id,tmpl", NOFORK_BOUNDARIES,
                             ids=[b[0] for b in NOFORK_BOUNDARIES])
    def test_shell_exits_with_channel_status(self, cls_id, setup, word,
                                             b_id, tmpl):
        body = tmpl.format(W=word)
        _assert_agree(f'{setup}{body}; echo "after rc=$?"')


class TestErrexitOverridesChannelStatus:
    """RED-ON-BASE: errexit forces 1 over the -c channel's 127."""

    @pytest.mark.parametrize("cls_id,setup,word",
                             FATAL_CLASSES, ids=[c[0] for c in FATAL_CLASSES])
    @pytest.mark.parametrize("b_id,tmpl", NOFORK_BOUNDARIES,
                             ids=[b[0] for b in NOFORK_BOUNDARIES])
    def test_direct_and_brace_group(self, cls_id, setup, word, b_id, tmpl):
        body = tmpl.format(W=word)
        _assert_agree(f'set -e; {setup}{body}; echo "after rc=$?"')

    @pytest.mark.parametrize("spelling", ["set -e", "set -o errexit"])
    def test_both_errexit_spellings(self, spelling):
        _assert_agree(f'{spelling}; echo ${{x?boom}}')

    def test_set_u_violation(self):
        _assert_agree('set -e; set -u; echo $undef')

    def test_through_eval(self):
        _assert_agree("set -e; eval 'echo ${x?boom}'; echo TAIL")

    @pytest.mark.parametrize("cls_id,setup,word",
                             FATAL_CLASSES, ids=[c[0] for c in FATAL_CLASSES])
    @pytest.mark.parametrize("b_id,tmpl", FORK_BOUNDARIES,
                             ids=[b[0] for b in FORK_BOUNDARIES])
    def test_composition_with_the_fork_boundary(self, cls_id, setup, word,
                                                b_id, tmpl):
        """THE COMPOSITION CELL of the slot's two status changes (D-3.4 lesson
        3: all three of 3.4's regressions lived at composition cells). errexit
        is on AND the failure is inside a fork: the child's status comes from
        the A10.1 rule, and the parent's errexit exit then carries it."""
        body = tmpl.format(W=word)
        _assert_agree(f'set -e; {setup}{body}; echo TAIL')


class TestErrexitIsRawFlagNotEffective:
    """MUST-HOLD, the first of ruling (d)'s two directions.

    Every suppressing context still yields 1 AND still exits — because the
    shell-exit is the expansion's own, and errexit only colours its status.
    An implementation that subtracted the suppression (copying the
    substitution_abort_status sibling) would return 127 here and recover."""

    @pytest.mark.parametrize("shape", [
        'echo ${x?boom} || echo RECOVERED; echo TAIL',
        'if echo ${x?boom}; then :; fi; echo TAIL',
        '! echo ${x?boom}; echo TAIL',
        'echo ${x?boom} && echo AND; echo TAIL',
        'while echo ${x?boom}; do break; done; echo TAIL',
    ], ids=["or_recover", "if_cond", "negation", "and_nonfinal", "while_cond"])
    def test_suppressing_context_still_exits_with_errexit_status(self, shape):
        _assert_agree(f'set -e; {shape}')


class TestErrexitFlagOffKeepsChannelStatus:
    """MUST-HOLD, the second direction: the rule reads the CURRENT flag."""

    def test_set_plus_e_restores_the_channel_status(self):
        _assert_agree('set -e; set +e; echo ${x?boom}')

    @pytest.mark.parametrize("cls_id,setup,word",
                             FATAL_CLASSES, ids=[c[0] for c in FATAL_CLASSES])
    def test_no_errexit_keeps_channel_status(self, cls_id, setup, word):
        _assert_agree(f'{setup}echo {word}')


class TestUntouchedFamilies:
    """PARITY: the families the slot must NOT have moved."""

    @pytest.mark.parametrize("errexit", ["", "set -e; "])
    @pytest.mark.parametrize("word", ["$((1/0))", "${a[1//]}"],
                             ids=["div0", "bad_subscript"])
    @pytest.mark.parametrize("b_id,tmpl", FORK_BOUNDARIES + NOFORK_BOUNDARIES,
                             ids=[b[0] for b in FORK_BOUNDARIES + NOFORK_BOUNDARIES])
    def test_discard_family_unchanged(self, errexit, word, b_id, tmpl):
        """The discard-line family is errexit-immune and was never channel
        -dependent: `( echo $((1/0)) )` was already 1 in both shells."""
        _assert_agree(f'{errexit}{tmpl.format(W=word)}; echo "after rc=$?"')

    @pytest.mark.parametrize("errexit", ["", "set -e; "])
    def test_badname_is_the_familys_rc1_control(self, errexit):
        """``${}`` is in the shell-exit family but its own exit_code is 1, so
        the -c channel never showed 127 for it — it never diverged, and must
        not start."""
        _assert_agree(f'{errexit}echo ${{}}; echo "after rc=$?"')

    @pytest.mark.parametrize("code", [5, 42])
    def test_exit_builtin_child_status_is_untouched(self, code):
        """The stamp is keyed, not blanket: a real ``exit`` in a subshell still
        carries its own code through the SystemExit arm."""
        _assert_agree(f'( exit {code} ) || echo "child rc=$?"')

    def test_exit_127_in_a_subshell_is_the_collision_control(self):
        """COLLISION CONTROL. 127 is the exact value a buggy stamp check would
        silently rewrite to 1 — and the arbitrary-code controls above cannot
        see that failure, because 5 and 42 are never what the channel rule
        produces. A real ``exit 127`` must still be 127: the stamp is an
        attribute on the exception, not a comparison against its status."""
        _assert_agree('( exit 127 ) || echo "child rc=$?"')

    def test_exit_127_from_a_command_not_found_child(self):
        """The same collision reached the natural way: a not-found command in a
        subshell genuinely exits 127."""
        _assert_agree('( nosuchcommand_zz ) 2>/dev/null || echo "child rc=$?"')

    def test_readonly_assignment_abort_child_status_is_untouched(self):
        """D-3.4-s3's neighbourhood: a readonly-refusal abort is an UNSTAMPED
        TopLevelAbort and keeps .status at a fork. Same rc pair (1 vs 127) as
        A10.1, different raise site — this pin is the fence."""
        _assert_agree('readonly r=1; ( r=2 ) || echo "child rc=$?"')

    @pytest.mark.parametrize("boundary", ["( echo ${x?boom} )",
                                          "vv=$( echo ${x?boom} )"],
                             ids=["subshell", "cmdsub"])
    def test_script_and_stdin_channels_were_already_right(self, boundary,
                                                          tmp_path):
        """All 72 script-file and stdin cells matched at base (those channels
        never used 127) — no-regression pins."""
        script = f'{boundary}; echo "after rc=$?"\n'
        f = tmp_path / "s.sh"
        f.write_text(script)
        b, p = run_bash([str(f)]), run_psh([str(f)])
        assert is_comparable(b) and is_comparable(p)
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode)

        b2 = run_bash([], stdin_data=script, stdin_mode="pipe")
        p2 = run_psh([], stdin_data=script, stdin_mode="pipe")
        assert is_comparable(b2) and is_comparable(p2)
        assert (p2.stdout, p2.returncode) == (b2.stdout, b2.returncode)


class TestTypedErrorObservables:
    """PARITY: the user-facing behaviour of each site whose catch changed."""

    @pytest.mark.parametrize("cmd", [
        'echo $((1/0)); echo TAIL',
        '(( 08 )); echo rc=$?',
        'for ((i=08; 0; 0)); do break; done; echo rc=$?',
        'v=abcdefgh; echo X${v:2:-99}Y; echo rc=$?',
        'a=(1 2 3 4); echo X${a[@]:1:-99}Y; echo rc=$?',
        'v=abcdefgh; echo X${v:2:3}Y',
        '[[ x =~ ^x$ ]]; echo rc=$?',
        '[[ 08 -eq 8 ]]; echo rc=$?',
        '[[ -f /nonexistent/zz ]]; echo rc=$?',
        '[[ 1 -eq 1 && 2 -eq 2 ]]; echo rc=$?',
    ], ids=["arith_div0", "arith_cmd_badoctal", "cfor_badoctal",
            "substr_neg_scalar", "substr_neg_array", "substr_ok",
            "regex_ok", "test_badoctal", "file_test", "compound"])
    def test_status_and_stdout_match_bash(self, cmd):
        _assert_agree(cmd)

    def test_invalid_regex_is_a_typed_user_error_not_a_masked_defect(self):
        """The one USER-reachable ValueError in the [[ ]] evaluator is now
        TestExpressionError. Status 2 matches bash; psh additionally prints a
        diagnostic bash omits (pre-existing, pinned both-sides below)."""
        b, p = _both('[[ x =~ [ ]]; echo rc=$?')
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode)
        assert "invalid regex" in p.stderr

    @pytest.mark.parametrize("ps4,needle", [
        ("$((1/0)) ", "arithmetic error"),
        ("${x?boom} ", "boom"),
        ("${v@Z} ", "bad substitution"),
    ], ids=["arith", "fatal_q", "badsub"])
    def test_ps4_expansion_error_falls_back_to_raw_text(self, ps4, needle):
        """The PS4 net narrowed from ``except Exception`` to ``except
        PshError``; the bash-parity fallback shape is unchanged."""
        cmd = f"v=s; set -x; PS4='{ps4}'; echo hi"
        b, p = _both(cmd)
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode)
        assert needle in p.stderr
        assert ps4.strip() in p.stderr  # the RAW text was emitted


class TestDeclaredDivergences:
    """Both-sides pins for divergences that are NOT this slot's defect.
    Recorded so a future change to either side is a deliberate act."""

    def test_ps4_bad_subscript_aborts_in_psh_but_not_bash(self):
        """SUCCESSOR ROW (integrator ruling, slot 3.5 §7): a bad SUBSCRIPT in
        PS4 raises TopLevelAbort — a BaseException, so it escapes the PS4
        fallback (which catches PshError, and caught Exception before: neither
        covers it). bash falls back to the raw text and continues; psh discards
        the command. Narrowing the net neither caused nor cured this: the row
        is byte-identical before and after. NOT fixed in-slot — a third
        TopLevelAbort-adjacent behaviour change would multiply composition
        cells."""
        cmd = "set -x; PS4='${a[1//]} '; echo hi"
        b, p = _both(cmd)
        assert b.returncode == 0 and "hi" in b.stdout      # bash continues
        assert p.returncode == 1 and p.stdout == ""        # psh discards
        assert "1//" in b.stderr or "syntax error" in b.stderr

    def test_invalid_regex_diagnostic_is_psh_only(self):
        """psh prints ``psh: [[: invalid regex: ...``; bash prints nothing.
        Status agrees (2). Pre-existing wording divergence, unchanged by the
        typing work."""
        b, p = _both('[[ x =~ [ ]]; echo rc=$?')
        assert b.returncode == p.returncode
        assert b.stderr == ""
        assert "invalid regex" in p.stderr
