"""$TIMEFORMAT directive formatting for the `time` keyword (executor F15).

psh now honors TIMEFORMAT (previously it always printed its default report).
Timing values are non-deterministic, so directive tests pin the output SHAPE
(digits normalized). The deterministic corners (%-free format, empty format,
%%) are pinned exactly against bash by the golden cases and
tests/conformance/bash/test_timeformat_conformance.py.

Directives: %%, %[p][l]R/U/S (precision p 0-3 default 3, l long form), %P
(CPU percentage, 2 decimals). An empty TIMEFORMAT suppresses the report;
`time -p` keeps its own POSIX format regardless of TIMEFORMAT.
"""

import re
import subprocess
import sys


def _psh_shape(script: str) -> str:
    """Run script in psh; return combined output with digits -> 'N'.

    An integer part collapses to a SINGLE 'N' however many digits it has;
    fractional digits stay one-for-one, so each directive's precision is
    still pinned exactly. The WIDTH of an integer part is not a property of
    the format — it is a property of the machine (an elapsed %R can be 0.207
    or 11.807), so shape tests stay width-blind by design.

    HISTORY: this normalization was originally forced by a %P VALUE defect —
    user/sys came from ``os.times()`` in 10 ms ticks, so a tick landing
    inside a sub-millisecond ``time true`` printed P in the thousands
    (measured: P=11934.31, the flake carried as #8) and sub-tick commands
    printed P=0.00. That mechanism was FIXED (CR-R2: getrusage microsecond
    deltas in ``_cpu_seconds``); %P magnitude is now pinned by
    ``TestCpuPercentMagnitude`` below, and this helper's width-blindness
    remains only for the machine-dependent integer widths of R/U/S.
    """
    r = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       capture_output=True, text=True, timeout=15)
    text = r.stdout + r.stderr
    text = re.sub(r"\d+(?=\.)", "N", text)   # integer part -> one N
    return re.sub(r"\d", "N", text)          # remaining digits -> N each


def test_default_format_when_unset():
    assert _psh_shape("{ time true; } 2>&1") == \
        "\nreal\tNmN.NNNs\nuser\tNmN.NNNs\nsys\tNmN.NNNs\n"


def test_custom_seconds_format():
    assert _psh_shape('TIMEFORMAT="elapsed=%R"; { time true; } 2>&1') == \
        "elapsed=N.NNN\n"


def test_empty_suppresses_report():
    assert _psh_shape("TIMEFORMAT=; { time true; } 2>&1; echo END") == "END\n"


def test_literal_percent():
    # Digits in the literal text are normalized to N too (100 -> NNN).
    assert _psh_shape('TIMEFORMAT="100%% done %R"; { time true; } 2>&1') == \
        "NNN% done N.NNN\n"


def test_cpu_percent_two_decimals():
    # FORMAT leg: %P is emitted with exactly TWO decimal places whatever its
    # value (the integer width is a property of the machine/load, not the
    # format). The VALUE envelope is TestCpuPercentMagnitude's job.
    r = subprocess.run([sys.executable, "-m", "psh", "-c",
                        'TIMEFORMAT="cpu=%P"; { time true; } 2>&1'],
                       capture_output=True, text=True, timeout=15)
    assert re.fullmatch(r"cpu=\d+\.\d{2}\n", r.stdout), repr(r.stdout)


def _cpu_percent(script: str) -> float:
    """Run a TIMEFORMAT="cpu=%P" script in psh and return %P as a float."""
    r = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       capture_output=True, text=True, timeout=15)
    m = re.fullmatch(r"cpu=(\d+\.\d{2})\n", r.stdout)
    assert m, repr((r.stdout, r.stderr))
    return float(m.group(1))


class TestCpuPercentMagnitude:
    """%P VALUE envelope (CR-R2 rider, v0.774.0).

    user/sys now come from getrusage microsecond deltas (``_cpu_seconds``),
    so %P is a true CPU percentage. RED at base (os.times() 10 ms tick):
    sub-tick commands printed the ZERO face P=0.00 (measured 60/60 idle for
    ``time true``) and a tick landing inside a sub-millisecond span printed
    the ABSURD face in the thousands (measured 11934.31). The envelopes are
    deliberately wide — load changes the values — but both defect faces sit
    far outside every one of them. Probe transcripts:
    checkpoint-r/instruments/qr/ (mechanism) + the rider's p01 battery.
    """

    def test_time_true_percentage_live_and_sane(self):
        # Base zero face fails the lower bound; absurd face fails the upper.
        # (psh's in-process `time true` span is Python machinery, so its true
        # percentage sits near 100 — CPU ~= wall; measured 98.5-100.9.)
        for _ in range(5):
            p = _cpu_percent('TIMEFORMAT="cpu=%P"; { time true; } 2>&1')
            assert 0.0 < p < 200.0, p

    def test_sleep_percentage_near_zero_but_nonzero(self):
        # A mostly-waiting span: tiny but NONZERO percentage (measured
        # psh 1.69-2.20 vs bash 0.73-1.24). Base printed exactly 0.00.
        p = _cpu_percent('TIMEFORMAT="cpu=%P"; { time sleep 0.2; } 2>&1')
        assert 0.0 < p < 15.0, p

    def test_external_child_cpu_counted(self):
        # Children-rusage route: base printed 0.00 (child CPU invisible
        # below the tick). Measured 87-91 at tip.
        p = _cpu_percent('TIMEFORMAT="cpu=%P"; { time /usr/bin/true; } 2>&1')
        assert 0.0 < p < 200.0, p

    def test_cpu_bound_loop_near_100(self):
        # MUST-HOLD CONTROL, green at base too: at ~0.3 s of pure CPU the
        # old tick quantization was already fine (P~=100). Pins that the fix
        # did not break the case that always worked.
        p = _cpu_percent(
            'TIMEFORMAT="cpu=%P"; { time eval '
            "'i=0; while [ $i -lt 1500 ]; do i=$((i+1)); done'; } 2>&1")
        assert 50.0 < p < 150.0, p


def test_precision_zero():
    assert _psh_shape('TIMEFORMAT="%0R"; { time true; } 2>&1') == "N\n"


def test_precision_two():
    assert _psh_shape('TIMEFORMAT="%2R"; { time true; } 2>&1') == "N.NN\n"


def test_long_form():
    assert _psh_shape('TIMEFORMAT="%lR"; { time true; } 2>&1') == "NmN.NNNs\n"


def test_long_form_with_precision():
    assert _psh_shape('TIMEFORMAT="%2lR"; { time true; } 2>&1') == "NmN.NNs\n"


def test_all_directives():
    assert _psh_shape(
        'TIMEFORMAT="r=%R u=%U s=%S p=%P"; { time true; } 2>&1') == \
        "r=N.NNN u=N.NNN s=N.NNN p=N.NN\n"


def test_multiline_format():
    assert _psh_shape("TIMEFORMAT=$'R:%R\\nU:%U'; { time true; } 2>&1") == \
        "R:N.NNN\nU:N.NNN\n"


def test_dash_p_ignores_timeformat():
    # `time -p` forces the POSIX seconds format regardless of TIMEFORMAT.
    assert _psh_shape('TIMEFORMAT="IGNORED%R"; { time -p true; } 2>&1') == \
        "real N.NN\nuser N.NN\nsys N.NN\n"
