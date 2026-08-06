"""M8 regression locks for the typed expansion/arithmetic error path (3.5).

An M8 lock answers one question per disposition class: *if someone puts the
defect back, does a NAMED pin in the default run fail, and does it fail for its
OWN reason?* A ratchet that merely happens to be green proves nothing; these
tests re-introduce each removed net and show the specific guard biting.

Two mutation styles, chosen by what the named pin actually reads:

* **Static classes** — the pin is an AST detector over the source, so the
  mutation is applied to the source TEXT in memory and the pin's own detector
  function is called on it. Nothing on disk is touched, and the assertion
  exercises the exact predicate the pin asserts.
* **Behavioural classes** — the pin is a conformance row, so the mutation is
  applied to a COPY of ``psh/`` in the test's own ``tmp_path`` and a real psh
  runs out of that copy. The live worktree is never modified, so these are
  safe under xdist.

Each test names the pin it is locking, and asserts the pin's OWN failure mode
(a detector hit / the specific status regression), never a generic error.
"""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH_SRC = ROOT / "psh"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The pins under lock, loaded as modules so we can call their detectors.
RATCHET = _load("_r23_ratchet", "tests/unit/tooling/test_subscript_no_broad_except.py")
Q2 = _load("_q2_ledger", "tests/unit/tooling/test_broad_valueerror_catch_q2.py")


def _mutate(rel, old, new):
    """Return the source of ``rel`` with ``old`` replaced by ``new`` (once).
    Asserts the anchor is unique — a fail-OPEN anchor would make the whole
    lock vacuous (the lesson-8 trap)."""
    src = (ROOT / rel).read_text()
    assert src.count(old) == 1, (
        f"M8 anchor is not unique in {rel} ({src.count(old)} matches): {old!r}. "
        "The lock cannot be trusted until the anchor is fixed.")
    return src.replace(old, new, 1)


# --------------------------------------------------------------------------
# Static class 1: the PS4 net re-widened  ->  the 2.3/3.5 broad-except ratchet
# --------------------------------------------------------------------------

def test_m8_ps4_rewidened_is_caught_by_the_broad_except_ratchet():
    """LOCKS: test_subscript_no_broad_except.py::
    test_guarded_modules_have_no_broad_except

    psh/expansion/manager.py entered GUARDED when its PS4 fallback narrowed
    from `except Exception` to `except PshError`. Put it back and the ratchet's
    own detector must flag it as a broad handler."""
    rel = "psh/expansion/manager.py"
    clean = RATCHET.broad_handlers((ROOT / rel).read_text(), rel)
    assert clean == [], (
        f"precondition: {rel} is in GUARDED and must be clean now, got {clean}")

    mutated = _mutate(rel, "        except PshError:\n            return ps4",
                      "        except Exception:\n            return ps4")
    hits = RATCHET.broad_handlers(mutated, rel)
    assert hits, "the ratchet detector did NOT bite the re-widened PS4 net"
    assert hits[0][2] == "Exception", hits
    assert rel in RATCHET.GUARDED, (
        "the lock is vacuous unless the module is actually guarded")


# --------------------------------------------------------------------------
# Static class 2: the 797 VT net restored  ->  the same ratchet (as a lock)
#                 and, separately, the Q2 ledger's unclassified check
# --------------------------------------------------------------------------

_NET_797 = '''    except ShellArithmeticError as e:
        print(f"psh: arithmetic error: {e}", file=sys.stderr)
        # Raise exception to stop command execution (like bash)
        raise ExpansionError(f"arithmetic error: {e}") from e'''

_NET_797_RESTORED = _NET_797 + '''
    except (ValueError, TypeError) as e:
        print(f"psh: unexpected arithmetic error: {e}", file=sys.stderr)
        raise ExpansionError(f"unexpected arithmetic error: {e}") from e'''


def test_m8_restored_797_net_is_a_broad_except_when_spelled_broadly():
    """LOCKS: test_subscript_no_broad_except.py::
    test_guarded_modules_have_no_broad_except

    psh/expansion/arithmetic/evaluator.py is in GUARDED as a LOCK: it has no
    broad handler to remove, so the entry exists to stop one appearing on the
    arithmetic error path. Re-introduce the removed net in its widest form and
    the ratchet must bite."""
    rel = "psh/expansion/arithmetic/evaluator.py"
    assert rel in RATCHET.GUARDED
    assert RATCHET.broad_handlers((ROOT / rel).read_text(), rel) == []

    mutated = _mutate(
        rel, _NET_797,
        _NET_797 + '\n    except Exception as e:\n'
                   '        raise ExpansionError(str(e)) from e')
    hits = RATCHET.broad_handlers(mutated, rel)
    assert hits and hits[0][2] == "Exception", hits


def test_m8_rewidened_enhanced_test_net_is_caught_by_the_q2_ledger():
    """LOCKS: test_broad_valueerror_catch_q2.py::test_no_unclassified_vt_catch

    The `[[ ]]` net narrowed to (TestExpressionError, OSError) and its
    BROAD_MASKING entry was deleted. Re-widening it back to raw VT must
    reappear as an UNCLASSIFIED candidate — the ledger is shrink-only, so a
    returning masker has no entry to hide behind."""
    rel = "psh/executor/core.py"
    live_now = Q2.broad_vt_candidates((ROOT / rel).read_text(), rel)
    sigs_now = {c for c in live_now if "evaluate" in c[2]}
    assert not sigs_now, (
        f"precondition: the [[ ]] net must not be a VT candidate now: {sigs_now}")

    mutated = _mutate(
        rel,
        "            except (TestExpressionError, OSError) as e:",
        "            except (ValueError, TypeError, OSError) as e:")
    cands = Q2.broad_vt_candidates(mutated, rel)
    restored = [c for c in cands
                if c[1] == ("ValueError", "TypeError", "OSError")]
    assert restored, f"Q2 detector did not bite the re-widened net: {cands}"
    classified = set(Q2.BROAD_MASKING) | set(Q2.NARROW_SAFE)
    assert restored[0] not in classified, (
        "the re-widened net must be UNCLASSIFIED (its ledger entry was pruned "
        "when it narrowed) so test_no_unclassified_vt_catch fails")


def test_m8_restored_dead_ve_leg_is_caught_by_the_q2_ledger():
    """LOCKS: test_broad_valueerror_catch_q2.py::test_no_unclassified_vt_catch

    The four-site dead-ValueError class (core.py `(( ))` + control_flow.py's
    three for(( )) legs) had its VE names dropped and its two NARROW_SAFE
    entries pruned. Putting a VE back makes the site a VT candidate again with
    no classification."""
    rel = "psh/executor/control_flow.py"
    mutated = _mutate(
        rel,
        "                        except (ReadonlyVariableError, NamerefCycleError,\n"
        "                                ArithmeticError) as e:\n"
        "                            # A bad condition expr stops the loop with status 1",
        "                        except (ReadonlyVariableError, NamerefCycleError,\n"
        "                                ValueError, ArithmeticError) as e:\n"
        "                            # A bad condition expr stops the loop with status 1")
    cands = Q2.broad_vt_candidates(mutated, rel)
    classified = set(Q2.BROAD_MASKING) | set(Q2.NARROW_SAFE)
    unclassified = [c for c in cands if c not in classified]
    assert unclassified, (
        f"restoring the dead VE leg produced no unclassified candidate: {cands}")


# --------------------------------------------------------------------------
# Behavioural classes: mutate a COPY of psh/ and run a real shell from it
# --------------------------------------------------------------------------

def _psh_copy(tmp_path):
    dst = tmp_path / "psh"
    shutil.copytree(PSH_SRC, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return tmp_path


def _run_from(tree, cmd):
    env = {**os.environ, "PYTHONPATH": str(tree)}
    env.pop("PSH_STRICT_ERRORS", None)
    return subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                          cwd=str(tree), capture_output=True, text=True,
                          env=env, timeout=60)


def _apply(tree, rel_in_psh, old, new):
    p = tree / "psh" / rel_in_psh
    src = p.read_text()
    assert src.count(old) == 1, (
        f"M8 anchor not unique in {rel_in_psh}: {old!r}")
    p.write_text(src.replace(old, new, 1))


@pytest.mark.parametrize("mutation,cmd,healthy,broken,pin", [
    (
        # R3 condition (iii): un-stamp the SystemExit carrier ALONE, leaving
        # the TopLevelAbort raise still stamped. This is the mutation that
        # reproduces the near-miss in this slot's own implementation — the
        # ruled design stamped only the TopLevelAbort, and a `-c` invocation
        # has is_script_mode True, so the shell-exit family leaves by the
        # SystemExit route and the channel's 127 leaked into the forked child.
        # The `-c` subshell pin must fail for its OWN reason: after rc=127.
        ("core/internal_errors.py",
         "            exc_exit.fatal_expansion_channel = channel  # type: ignore[attr-defined]",
         "            exc_exit.fatal_expansion_channel = False  # type: ignore[attr-defined]"),
        '( echo ${x?boom} ); echo "after rc=$?"',
        "after rc=1\n", "after rc=127\n",
        "test_typed_expansion_errors_conformance.py::"
        "TestA101ForkBoundaryChildStatus::test_after_marker_matches_bash",
    ),
    (
        # The COLLISION mutation: a stamp check that compared the STATUS
        # (== 127) instead of reading the attribute would pass every A10.1 row
        # and silently rewrite a real `exit 127`. Locks the collision control
        # row in the battery.
        ("executor/child_policy.py",
         "        if getattr(exc, 'fatal_expansion_channel', False):\n"
         "            # Same stamp, second route",
         "        if exc.code == 127:\n"
         "            # Same stamp, second route"),
        '( exit 127 ) || echo "child rc=$?"',
        "child rc=127\n", "child rc=1\n",
        "test_typed_expansion_errors_conformance.py::"
        "TestUntouchedFamilies::test_exit_127_in_a_subshell_is_the_collision_control",
    ),
    (
        # Drop the errexit override: `set -e` under -c goes back to 127.
        ("core/internal_errors.py",
         "            if state.options.get('errexit', False):\n"
         "                # errexit forces 1 over the -c channel status. RAW flag, not\n"
         "                # effective errexit — see the docstring's two pinned\n"
         "                # properties (ruling (d)).\n"
         "                code = 1\n"
         "            else:\n"
         "                code = getattr(exc, 'exit_code', 127)  # UnboundVariable: 127",
         "            code = getattr(exc, 'exit_code', 127)  # UnboundVariable: 127"),
        'set -e; echo ${x?boom}',
        None, None,
        "test_typed_expansion_errors_conformance.py::"
        "TestErrexitOverridesChannelStatus::test_both_errexit_spellings",
    ),
], ids=["a101_systemexit_carrier_unstamped", "stamp_check_by_status_collision",
        "errexit_override_removed"])
def test_m8_behavioural_mutation_regresses_the_named_pin(
        tmp_path, mutation, cmd, healthy, broken, pin):
    """Each mutation must reproduce the ORIGINAL defect's observable, which is
    precisely what the named conformance pin asserts."""
    tree = _psh_copy(tmp_path)

    before = _run_from(tree, cmd)
    _apply(tree, *mutation)
    after = _run_from(tree, cmd)

    if healthy is not None:
        assert before.stdout == healthy, (
            f"unmutated copy is not healthy: {before.stdout!r} / {before.stderr!r}")
        assert after.stdout == broken, (
            f"mutation did not reproduce the defect the pin guards ({pin}): "
            f"{after.stdout!r}")
    else:
        # status-only observable
        assert before.returncode == 1, (
            f"unmutated copy is not healthy: rc={before.returncode}")
        assert after.returncode == 127, (
            f"mutation did not reproduce the defect the pin guards ({pin}): "
            f"rc={after.returncode}")
    assert before.returncode != after.returncode or before.stdout != after.stdout
