"""Conformance: serialize -> re-parse must not change behavior (C033, C231).

bash is the reference for the executable round-trip contract: its own
``declare -f`` text, re-evaluated in bash, reproduces what the function did.
psh must (a) hold the same contract and (b) produce the same answers.

The live defect this closes: psh's formatter restored ``${…}`` braces only
before an ``[A-Za-z0-9_]`` character, so a brace expansion after a delimited
reference lost them — and brace expansion runs BEFORE parameter expansion, so
the re-parsed function read OTHER variables. Reproduce with (bash 5.3.15
prints ``11 12`` on both lines)::

    v=1 v1=A v2=B; f() { echo ${v}{1,2}; }; f
    eval "$(declare -f f)"; f

Empirical, bash 5.3.15 — POSIX leaves the text of ``declare -f`` unspecified,
so only the BEHAVIOR of the re-evaluated text is compared, never the bytes
(bash's layout is ``f () \\n{ \\n    …\\n}``, psh's is its own canonical
style). The corpus is ``tests/harness/roundtrip_corpus.py``; every row runs in
all three input modes (-c, script file, stdin).
"""

import os
import tempfile

import pytest
from roundtrip_corpus import (
    ROW_IDS,
    direct_script,
    roundtrip_script,
    split_rows,
)
from shell_oracle import is_comparable, run_bash, run_psh

MODES = ["-c", "file", "stdin"]


def _run(runner, script, mode, cwd):
    if mode == "-c":
        r = runner(["-c", script, "sh", "posarg"], timeout=60, cwd=cwd)
    elif mode == "stdin":
        r = runner(["-s", "posarg"], stdin_data=script, stdin_mode="pipe",
                   timeout=60, cwd=cwd)
    else:
        path = os.path.join(cwd, "corpus.sh")
        with open(path, "w") as fh:
            fh.write(script)
        r = runner([path, "posarg"], timeout=60, cwd=cwd)
    assert is_comparable(r), r
    return r


@pytest.fixture(scope="module")
def passes():
    """{mode: {shell: (direct_rows, roundtrip_rows, stderr pair)}}."""
    out = {}
    for mode in MODES:
        per_shell = {}
        for shell, runner in (("bash", run_bash), ("psh", run_psh)):
            with tempfile.TemporaryDirectory() as d:
                direct = _run(runner, direct_script(), mode, d)
            with tempfile.TemporaryDirectory() as d:
                rt = _run(runner, roundtrip_script(), mode, d)
            per_shell[shell] = (split_rows(direct.stdout), split_rows(rt.stdout),
                                (direct.stderr, rt.stderr))
        out[mode] = per_shell
    return out


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("row_id", ROW_IDS)
def test_bash_holds_the_round_trip_contract(row_id, mode, passes):
    """The reference itself: bash's ``declare -f`` re-eval changes nothing."""
    direct, rt, _ = passes[mode]["bash"]
    assert rt[row_id] == direct[row_id], (
        f"[{row_id}/{mode}] bash: {direct[row_id]!r} -> {rt[row_id]!r}")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("row_id", ROW_IDS)
def test_psh_matches_bash_before_and_after_the_round_trip(row_id, mode, passes):
    """psh's answers equal bash's, both directly and after the re-eval."""
    b_direct, b_rt, _ = passes[mode]["bash"]
    p_direct, p_rt, _ = passes[mode]["psh"]
    assert p_direct[row_id] == b_direct[row_id], (
        f"[{row_id}/{mode}] direct call: bash {b_direct[row_id]!r} "
        f"vs psh {p_direct[row_id]!r}")
    assert p_rt[row_id] == b_rt[row_id], (
        f"[{row_id}/{mode}] after eval \"$(declare -f f)\": "
        f"bash {b_rt[row_id]!r} vs psh {p_rt[row_id]!r}")


@pytest.mark.parametrize("mode", MODES)
def test_neither_shell_diagnoses_anything(mode, passes):
    """Both passes are silent in both shells.

    A dropped ``psh: error: [Errno 1] Operation not permitted`` host flake
    identifies itself here instead of looking like a conformance regression.
    """
    assert passes[mode]["bash"][2] == ("", "")
    assert passes[mode]["psh"][2] == ("", "")


# ---------------------------------------------------------------------------
# The same spelling rule on the EXPANSION path, where it is not a round trip
# at all: psh rebuilds the pre-expansion source of the parts that follow a
# ``:``-bounded tilde prefix, and used to rebuild ``${v}`` as ``$v``. bash
# leaves the parameter expansion untouched there, so the two shells printed
# different text for a plain `echo`.
# ---------------------------------------------------------------------------

_TILDE_CASES = [
    ("braced_after_tilde_colon", "v=1\necho ~:${v}"),
    ("bare_after_tilde_colon", "v=1\necho ~:$v"),
    ("braced_after_tilde_colon_then_slash", "v=1\necho ~:${v}/x"),
    ("braced_after_named_tilde_colon", "v=1\necho ~root:${v}b"),
    ("control_braced_after_tilde_slash", "v=1\necho ~/${v}b"),
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case_id,script", _TILDE_CASES,
                         ids=[c[0] for c in _TILDE_CASES])
def test_tilde_prefix_keeps_the_source_spelling(case_id, script, mode):
    """``echo ~:${v}`` prints what bash prints (HOME via env, D14)."""
    env = {"HOME": "/probe-home"}
    with tempfile.TemporaryDirectory() as bd, tempfile.TemporaryDirectory() as pd:
        bash = _run(lambda a, **k: run_bash(a, env=env, **k), script, mode, bd)
        psh = _run(lambda a, **k: run_psh(a, env=env, **k), script, mode, pd)
    assert psh.stdout == bash.stdout, (
        f"[{case_id}/{mode}] bash {bash.stdout!r} vs psh {psh.stdout!r}")
    assert psh.returncode == bash.returncode
    assert bash.stderr == "" and psh.stderr == ""
