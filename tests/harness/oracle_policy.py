"""Oracle policy — which bash the differential tests are pinned to.

Improvement Program 2026-09, standing rules D1 and D5
(``docs/reviews/improvement_program_2026-09-06.md`` §4):

* The differential contract is bash major.minor :data:`EXPECTED_BASH_MM`,
  resolved by :func:`shell_oracle.resolve_bash` (``BASH_PATH`` -> Homebrew ->
  PATH).  The patch level is recorded wherever the oracle is reported but is
  not part of the contract (a patch bump is allowed and logged).
* Drift is caught ONCE, loudly: ``run_tests.py`` preflights
  :func:`oracle_matches_policy` before any test phase and the attestation
  writer refuses on the same mismatch.  ``test_bash_oracle_resolution.py``
  carries the in-suite twin for bare ``pytest`` runs.
* Version-sensitive rows are classified by :func:`oracle_at_least` (the
  ``oracle_min`` marker / golden ``min_bash`` key) and platform-sensitive rows
  by a PROBED predicate, :func:`oracle_feature`, never by an OS or version
  literal in test code.

Invariant: this module never compares against a hard-coded *observed*
version — the only literal it owns is the policy constant.
"""
from __future__ import annotations

import re
import subprocess
from typing import Callable, Dict, Optional, Tuple

from shell_oracle import BashOracle, resolve_bash

#: The contract: bash major.minor the pins are verified against.  Changing
#: this is a Wave-0-shaped re-baseline slot, never an in-slot edit (D1).
EXPECTED_BASH_MM = "5.3"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(version: str) -> Tuple[int, int, int]:
    """``'5.3.15(1)-release'`` -> ``(5, 3, 15)``; unparseable -> ``(0, 0, 0)``."""
    m = _VERSION_RE.match(version or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def oracle_major_minor(oracle: Optional[BashOracle] = None) -> str:
    """``'5.3'`` for the resolved (or given) oracle."""
    oracle = oracle or resolve_bash()
    major, minor, _ = parse_version(oracle.version)
    return f"{major}.{minor}"


def oracle_summary(oracle: Optional[BashOracle] = None) -> str:
    """One-line identification printed by the runner, the pytest header and
    conformance failure messages: ``oracle: /path/to/bash 5.3.15(1)-release``."""
    oracle = oracle or resolve_bash()
    return f"oracle: {oracle.path} {oracle.version}"


def oracle_matches_policy(oracle: Optional[BashOracle] = None) -> Tuple[bool, str]:
    """``(True, summary)`` when the resolved major.minor equals the policy,
    else ``(False, <loud drift message>)``.

    The message tells the reader what to do: retune in a Wave-0-shaped slot,
    never edit pins in place to make a drifted oracle green.
    """
    oracle = oracle or resolve_bash()
    found = oracle_major_minor(oracle)
    if found == EXPECTED_BASH_MM:
        return True, oracle_summary(oracle)
    return False, (
        f"oracle drift: resolved bash {oracle.version} at {oracle.path}, "
        f"policy is {EXPECTED_BASH_MM} — run a Wave-0-shaped retune "
        f"(docs/reviews/improvement_program_2026-09-06.md §6), do not edit "
        f"pins in place; pass --oracle-override only for that slot."
    )


def oracle_at_least(minimum: str, oracle: Optional[BashOracle] = None) -> bool:
    """True when the oracle's version is >= ``minimum`` (``'5.3'`` or ``'5.3.15'``)."""
    oracle = oracle or resolve_bash()
    return parse_version(oracle.version) >= parse_version(minimum)


# --- probed platform features ------------------------------------------------

def _run_oracle(path: str, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [path, "-c", script], stdin=subprocess.DEVNULL, capture_output=True,
        timeout=10, encoding="utf-8", errors="surrogateescape",
    )


def _probe_x87_long_double(path: str) -> bool:
    """x86-64 glibc formats bash's ``long double`` ``%a`` with the explicit
    integer bit in the leading digit (``printf '%a' 1`` -> ``0x8p-3``);
    IEEE-double platforms (arm64, macOS) print ``0x1p+0``."""
    out = _run_oracle(path, r"printf '%a\n' 1").stdout.strip()
    return bool(re.match(r"^-?0x[89a-fA-F]", out))


def _probe_funsub(path: str) -> bool:
    """bash 5.3 function substitution ``${ cmd; }`` parses and runs."""
    return _run_oracle(path, "x=${ :; }").returncode == 0


_FEATURE_PROBES: Dict[str, Callable[[str], bool]] = {
    "x87_long_double": _probe_x87_long_double,
    "funsub": _probe_funsub,
}
_FEATURE_CACHE: Dict[Tuple[str, str], bool] = {}


def oracle_feature(name: str, oracle: Optional[BashOracle] = None) -> bool:
    """Probe (once per process) whether the oracle exhibits ``name``.

    Unknown names raise ``KeyError`` — a misspelled classifier must not
    silently skip or run a row.
    """
    if name not in _FEATURE_PROBES:
        raise KeyError(f"unknown oracle feature {name!r}; known: {sorted(_FEATURE_PROBES)}")
    oracle = oracle or resolve_bash()
    key = (oracle.path, name)
    if key not in _FEATURE_CACHE:
        _FEATURE_CACHE[key] = _FEATURE_PROBES[name](oracle.path)
    return _FEATURE_CACHE[key]


if __name__ == "__main__":  # pragma: no cover - manual check
    ok, msg = oracle_matches_policy()
    print(("OK " if ok else "DRIFT ") + msg)
    for feature in _FEATURE_PROBES:
        print(f"{feature}: {oracle_feature(feature)}")
