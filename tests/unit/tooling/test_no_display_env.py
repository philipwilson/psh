"""The test environment must not expose an X11 display (finding: XQuartz autostart).

On macOS with XQuartz installed, the login environment carries
``DISPLAY=/var/run/com.apple.launchd.*/org.xquartz:0`` — a socket that
launchd watches, auto-starting XQuartz the moment ANY X11-capable client
connects. Tests spawn thousands of subprocesses (psh, bash, externals);
one X-aware child with an inherited DISPLAY pops a GUI mid-run.

``tests/conftest.py`` strips DISPLAY/XAUTHORITY at import time so every
test process (including xdist workers) and everything they spawn runs
X11-free; the conformance framework strips them again in its env builder
as belt-and-braces. This canary fails if either strip is removed while
the invoking environment carries a DISPLAY (on machines with no DISPLAY
set it passes trivially — it is a canary for the leak, not a universal
invariant).
"""

import os


def test_no_display_in_test_environ():
    assert 'DISPLAY' not in os.environ, (
        "DISPLAY leaked into the test environment — the conftest.py strip "
        "is missing or ran too late; any X11-capable subprocess can now "
        "auto-start XQuartz mid-run."
    )


def test_no_xauthority_in_test_environ():
    assert 'XAUTHORITY' not in os.environ, (
        "XAUTHORITY leaked into the test environment (see DISPLAY canary)."
    )
