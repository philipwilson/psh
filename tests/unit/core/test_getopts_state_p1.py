"""Core-state Phase 1: typed getopts continuation state (A3 / builtins P1.8).

``getopts`` tracked only a within-word cursor + OPTIND, not the argument
SOURCE or the current option word. Changing the explicit argument list (or
switching argv<->explicit) at the same OPTIND resumed the stale within-word
offset and raised ``string index out of range``. A manual ``OPTIND=1`` mid
cluster also failed to reset the cursor.

Probed bash 5.2 semantics (tmp/probe_getopts.sh):
  - the cursor is preserved across calls with the SAME source word;
  - it resets to 1 when the option word or argument source changes;
  - it resets whenever OPTIND is ASSIGNED (even to the same value).

xfail(strict=True) on the crash/reset cases; regressions pin the cases psh
already gets right. Fixed by the typed GetoptsState in Commit 6.
"""

import pytest

from psh.shell import Shell


def _run(script):
    import contextlib
    import io
    sh = Shell(norc=True)
    try:
        buf = io.StringIO()
        sh.stdout = buf
        # echo writes to sys.stdout in-process, so redirect that too (the
        # captured_shell fixture uses the same both-streams approach).
        with contextlib.redirect_stdout(buf):
            rc = sh.run_command(script)
        return rc, buf.getvalue()
    finally:
        sh.close()


@pytest.mark.xfail(strict=True, reason="A3: cursor keyed only to OPTIND; a "
                   "shorter next word overruns -> string index out of range. "
                   "Fixed by GetoptsState (Commit 6).")
def test_explicit_source_word_change_no_crash():
    rc, out = _run(
        'getopts abc o -ab; echo "1 $o $OPTIND"; '
        'getopts abc o -c; echo "2 $o $OPTIND"')
    # bash: 1 a 1 / 2 c 2
    assert "2 c 2" in out
    assert "string index out of range" not in out


@pytest.mark.xfail(strict=True, reason="A3: switching explicit->positional "
                   "source at the same OPTIND overruns. Fixed Commit 6.")
def test_argv_to_positional_switch_no_crash():
    rc, out = _run(
        'set -- -x; getopts ab o -ab; echo "1 $o"; '
        'getopts abx o; echo "2 $o $OPTIND"')
    # bash: 1 a / 2 x 2
    assert "2 x 2" in out
    assert "string index out of range" not in out


@pytest.mark.xfail(strict=True, reason="A3: manual OPTIND=1 mid-cluster does "
                   "not reset the within-word cursor. Fixed Commit 6.")
def test_optind_reset_midcluster_restarts():
    rc, out = _run(
        'set -- -ab; getopts ab o; echo "1 $o"; '
        'OPTIND=1; getopts ab o; echo "2 $o $OPTIND"')
    # bash: 1 a / 2 a 1  (OPTIND=1 restarts the scan of -ab)
    assert "2 a 1" in out


class TestGetoptsRegression:
    """Cases psh already handles — must survive the GetoptsState rewrite."""

    def test_explicit_cluster_preserved(self):
        rc, out = _run(
            'getopts ab o -ab; echo "1 $o $OPTIND"; '
            'getopts ab o -ab; echo "2 $o $OPTIND"; '
            'getopts ab o -ab; echo "3 $o $OPTIND $?"')
        assert "1 a 1" in out and "2 b 2" in out and "3 ? 2 1" in out

    def test_positional_cluster_preserved(self):
        rc, out = _run(
            'set -- -ab; getopts ab o; echo "1 $o $OPTIND"; '
            'getopts ab o; echo "2 $o $OPTIND"')
        assert "1 a 1" in out and "2 b 2" in out

    def test_silent_mode_bad_option_cluster(self):
        rc, out = _run(
            'getopts :ab o -az; echo "1 $o <$OPTARG> $OPTIND"; '
            'getopts :ab o -az; echo "2 $o <$OPTARG> $OPTIND"')
        assert "1 a <> 1" in out and "2 ? <z> 2" in out

    def test_realistic_optind_reset_between_parses(self):
        # The documented idiom: reset OPTIND=1 to reparse a fresh word set.
        rc, out = _run(
            'getopts ab o -a; echo "1 $o"; '
            'OPTIND=1; getopts ab o -b; echo "2 $o $OPTIND"')
        assert "1 a" in out and "2 b 2" in out
