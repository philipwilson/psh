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
    """Run script in psh; return combined output with digits -> 'N'."""
    r = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       capture_output=True, text=True, timeout=15)
    return re.sub(r"\d", "N", r.stdout + r.stderr)


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
    assert _psh_shape('TIMEFORMAT="cpu=%P"; { time true; } 2>&1') == "cpu=N.NN\n"


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
