"""The two fd-prefix operator tables stay in parity (round-3 blocker R9-A).

THE CLASS THIS PREVENTS, which has now cost three rounds:

* round 2 — the named-fd table had `>>` but no `<<`, so `{v}<<EOF` never
  registered a here-document and its body executed as commands;
* round 3 — the same table gained `<<`/`<<-` but still lacked `<<<`, which
  the SIBLING digit-fd table has had all along.

Each time the fix closed the shape in front of it and the sibling table was
the actual universe. So the structural discharge is not another row in a
corpus, it is this guard: **the named-fd operator table must cover the
digit-fd table's operator set**, and any deliberate exclusion must be listed
HERE with its reason, where the next person changing either table will see it.

The tables are read out of the source rather than re-declared, so the guard
cannot drift from what the lexer actually does.
"""
import ast
import pathlib

import pytest

_SOURCE = (pathlib.Path(__file__).resolve().parents[3]
           / "psh" / "lexer" / "recognizers" / "operator.py")

# Operators the NAMED-fd table may lack, with the reason. Empty today: every
# digit-fd operator is also reachable with a `{name}` prefix. An entry here is
# a claim that bash does NOT accept the named form -- verify against the oracle
# before adding one.
_DELIBERATE_EXCLUSIONS: dict[str, str] = {}


def _table_operators(func_name):
    """The operator strings a recognizer's redirect table matches, read from
    the SOURCE so the guard tracks the code rather than a copy of it."""
    tree = ast.parse(_SOURCE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            ops = set()
            for sub in ast.walk(node):
                # `for op, tok_type in (('<<<', X), ('<<-', Y), ...)`
                if isinstance(sub, ast.Tuple) and len(sub.elts) == 2 \
                        and isinstance(sub.elts[0], ast.Constant) \
                        and isinstance(sub.elts[0].value, str):
                    ops.add(sub.elts[0].value)
            return ops
    pytest.fail(f"{func_name} not found in {_SOURCE}")


def test_the_two_tables_were_actually_found():
    """Non-vacuity: a parse that found nothing would make the parity check
    below pass trivially."""
    digit = _table_operators("_try_fd_prefixed_redirect")
    named = _table_operators("_try_var_fd_redirect")
    assert len(digit) >= 5, digit
    assert len(named) >= 5, named
    # The two operators whose absence caused rounds 2 and 3.
    assert "<<" in digit and "<<<" in digit, digit


def test_named_fd_table_covers_the_digit_fd_table():
    """THE parity invariant."""
    digit = _table_operators("_try_fd_prefixed_redirect")
    named = _table_operators("_try_var_fd_redirect")
    missing = {op for op in digit - named if op not in _DELIBERATE_EXCLUSIONS}
    assert not missing, (
        f"the named-fd operator table is missing {sorted(missing)}, which the "
        "digit-fd table accepts. A `{name}` prefix must reach every operator a "
        "digit prefix reaches, or the omission must be listed in "
        "_DELIBERATE_EXCLUSIONS with a reason checked against bash."
    )


def test_every_declared_exclusion_is_really_absent():
    """Keeps the exclusion list honest: an entry that is no longer missing is
    stale and must be removed, or it would silence a future regression."""
    digit = _table_operators("_try_fd_prefixed_redirect")
    named = _table_operators("_try_var_fd_redirect")
    stale = [op for op in _DELIBERATE_EXCLUSIONS if op not in digit - named]
    assert not stale, f"stale _DELIBERATE_EXCLUSIONS entries: {stale}"


@pytest.mark.parametrize("op", ["<<", "<<-", "<<<"])
def test_the_heredoc_family_is_reachable_with_a_named_fd(op):
    """The three operators this class kept losing, asserted individually so a
    failure names the spelling rather than a set difference."""
    assert op in _table_operators("_try_var_fd_redirect")
