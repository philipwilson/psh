"""Both-sides DECLARED-DIVERGENCE pins for the bash 5.3 retune (Wave 0.3).

A declared-divergence pin asserts the oracle's (bash 5.3.15) CURRENT output
AND psh's CURRENT output for one command, in every input mode the runner
offers (``-c``, script file, stdin -- D6), so the pin goes red the moment
EITHER side moves:

* the ORACLE side moving means the oracle drifted (a new bash) -- run a
  Wave-0-shaped re-baseline, never edit the expectation in place;
* the PSH side moving means the Wave 2 slot named by ``slot`` landed its
  fix -- the row is then flipped into a plain parity pin (both sides equal)
  and its ``FLIP-PINS.md`` row is closed.

``bash`` / ``psh`` are the expected ``(stdout, exit status)`` of each side.
stderr is compared by PRESENCE only (shell-name prefixes and wording
differ); ``stderr`` selects the shape -- ``"both"`` (both diagnose),
``"bash"`` (only bash diagnoses; psh silently succeeds), ``"same"`` (mere
presence agreement) or ``None`` -- and ``stderr_has`` names a wording
fragment that every diagnosing side must contain.

Shared by the family files of Wave 0.3 package G (trap entry status has its
own cell table in test_exit_trap_status_precedence_conformance.py).  Uses
only the shell-oracle runner -- never ``subprocess`` -- so the anti-spawn
guard (tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py) is
satisfied by construction.
"""

from shell_oracle import is_comparable, run_bash, run_psh

MODES = ("command", "script", "stdin")


def run_in_mode(runner, mode, command, tmp_path, tag):
    """Run ``command`` in one input mode through the shell-oracle runner.

    ``runner`` is ``run_psh`` / ``run_bash`` (a CALLABLE, never a shell-name
    string: a literal ``"bash"`` argument trips the oracle-resolution guard,
    which cannot tell a mode selector from a hard-coded oracle binary).
    ``tag`` only names the temp script file under ``tmp_path``.
    """
    if mode == "command":
        return runner(["-c", command])
    if mode == "script":
        path = tmp_path / f"{tag}.sh"
        path.write_text(command + "\n")
        return runner([str(path)])
    if mode == "stdin":
        return runner([], stdin_data=command + "\n", stdin_mode="pipe")
    raise ValueError(f"unknown input mode {mode!r}")


def assert_declared_divergence(command, *, bash, psh, tmp_path, slot,
                               modes=MODES, stderr="both", stderr_has=None):
    """Pin ``command`` both sides in each of ``modes``; see the module doc."""
    for mode in modes:
        b = run_in_mode(run_bash, mode, command, tmp_path, "oracle")
        p = run_in_mode(run_psh, mode, command, tmp_path, "psh")
        assert is_comparable(b), b
        assert is_comparable(p), p
        assert (b.stdout, b.returncode) == bash, (
            f"[{mode}] ORACLE side moved for {command!r}: "
            f"bash {b.stdout!r} rc={b.returncode}, expected {bash} "
            f"(oracle drift -> re-baseline, do not edit in place)")
        assert (p.stdout, p.returncode) == psh, (
            f"[{mode}] PSH side moved for {command!r} (slot {slot} landed? "
            f"flip this row): psh {p.stdout!r} rc={p.returncode}, "
            f"expected {psh}")
        diagnosing = []
        if stderr == "both":
            assert b.stderr and p.stderr, (
                f"[{mode}] a side stayed silent for {command!r}: "
                f"psh={p.stderr!r} bash={b.stderr!r}")
            diagnosing = [b, p]
        elif stderr == "bash":
            assert b.stderr and not p.stderr, (
                f"[{mode}] expected only bash to diagnose {command!r}: "
                f"psh={p.stderr!r} bash={b.stderr!r}")
            diagnosing = [b]
        elif stderr == "same":
            assert bool(b.stderr) == bool(p.stderr), (
                f"[{mode}] stderr-presence disagreement for {command!r}: "
                f"psh={p.stderr!r} bash={b.stderr!r}")
            diagnosing = [r for r in (b, p) if r.stderr]
        elif stderr is not None:
            raise ValueError(f"unknown stderr shape {stderr!r}")
        if stderr_has is not None:
            for r in diagnosing:
                assert stderr_has in r.stderr, (mode, command, r.stderr)
