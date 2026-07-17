"""Fixtures for behavioral golden tests.

Note: the ``--compare-bash`` option is registered in the *root* conftest
(``tests/conftest.py``), not here. pytest only honours ``pytest_addoption``
from the rootdir conftest, so a copy here was silently ignored on full-suite
runs (``pytest tests/``) and the golden bash-comparison tests could never be
enabled. Run them with: ``pytest tests/behavioral --compare-bash``.
"""

import os
import sys


def pytest_report_header(config):
    """Record which bash acted as the oracle, like run_conformance_tests.py.

    Only meaningful when ``--compare-bash`` is active (otherwise no bash runs),
    so the line is emitted only then. Mirrors the conformance runner's
    "Bash oracle: ..." line so a failing --compare-bash run makes it obvious
    *which* bash produced the reference output (resolve_bash's BASH_PATH ->
    Homebrew -> PATH resolution, not necessarily the PATH bash).
    """
    if not config.getoption("--compare-bash", default=False):
        return None
    harness_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "harness")
    sys.path.insert(0, harness_dir)
    from shell_oracle import resolve_bash
    oracle = resolve_bash()
    return f"golden bash oracle: {oracle.path} ({oracle.version})"
