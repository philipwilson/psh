"""Global pytest configuration for psh tests."""
import os


def pytest_configure(config):
    """Pin the environment the whole suite (and its subprocesses) runs under.

    This is the only load-bearing content of the repo-root conftest; test
    fixtures and markers live in ``tests/conftest.py`` and ``pytest.ini``.
    """
    # Ensure subprocesses can import the local psh package when invoked via
    # ``python -m psh`` by propagating the repository root through PYTHONPATH.
    repo_root = os.path.dirname(os.path.abspath(__file__))
    existing = os.environ.get('PYTHONPATH')
    path_entries = [repo_root]
    if existing:
        path_entries.append(existing)
    os.environ['PYTHONPATH'] = os.pathsep.join(path_entries)

    # Run the entire suite with strict-errors enabled so a genuine INTERNAL
    # DEFECT (a Python bug surfacing as an unexpected exception) fails loudly
    # instead of being masked as an ordinary exit-1. This env var seeds the
    # strict-errors option at Shell construction, so it covers BOTH in-process
    # shells AND subprocess ``python -m psh`` instances.
    #
    # Expected shell errors are NOT affected: per the taxonomy in
    # psh/core/internal_errors.py, PshError / OSError / SyntaxError reaching a
    # last-resort guard pass through to normal handling (print + exit 1) even
    # under strict mode. Only true defects (RuntimeError, AttributeError,
    # TypeError, ...) are re-raised.
    os.environ['PSH_STRICT_ERRORS'] = '1'

    # Pin the whole suite to the C locale. psh is now locale-SENSITIVE (it reads
    # LC_ALL/LC_CTYPE/LC_COLLATE/LANG at startup — see psh/core/locale_service.py),
    # so without a pin the suite's behaviour would follow the developer's ambient
    # locale (e.g. en_GB.UTF-8) and thousands of tests that assert codepoint glob
    # ordering / byte string comparison / ASCII character classes would flip.
    # LC_ALL=C makes psh compute C mode -> no setlocale, byte-identical to its
    # historical locale-blind behaviour -> the suite is deterministic on every
    # machine. Locale-SENSITIVE behaviour is covered by conformance tests that
    # set an explicit UTF-8 locale in their subprocess env (which overrides this
    # pin for that child only). Python's own UTF-8 mode is unaffected: it was
    # fixed at interpreter startup from the real ambient locale, so non-ASCII
    # test strings still round-trip. Set here (session start) before any in-process
    # Shell reads os.environ.
    os.environ['LC_ALL'] = 'C'
