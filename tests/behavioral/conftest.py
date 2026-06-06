"""Fixtures for behavioral golden tests.

Note: the ``--compare-bash`` option is registered in the *root* conftest
(``tests/conftest.py``), not here. pytest only honours ``pytest_addoption``
from the rootdir conftest, so a copy here was silently ignored on full-suite
runs (``pytest tests/``) and the golden bash-comparison tests could never be
enabled. Run them with: ``pytest tests/behavioral --compare-bash``.
"""
