"""Conformance pins for the five Q1 service protocols (§13).

These prove two things at once:

1. **Completeness / correct producer mapping.** Each protocol is STRUCTURALLY
   satisfied by the canonical producer named in its docstring — the ``Shell``
   for ``IOContext``, ``ShellState`` for ``VariableAccess``, the
   ``ExpansionManager`` for ``ExpansionContext``, the ``JobManager`` for
   ``JobRuntime``, and ``ShellState.locale`` (``LocaleService``) for
   ``LocaleContext``. ``isinstance`` here checks member PRESENCE (the protocols
   are ``@runtime_checkable``), which is exactly "does the producer expose this
   surface".

2. **Behavioral inertness of the migrations.** The Q1 migrations (``make_reader``
   / ``InputCursorRegistry.cursor_for_fd`` now take ``IOContext``) change ONLY
   annotations — they keep working because ``Shell`` already IS an
   ``IOContext``. ``test_iocontext_is_a_real_narrowing`` goes further: a minimal
   stub carrying only the three streams (NOT a ``Shell``) satisfies the protocol
   and drives ``make_reader`` — so the narrowing is genuine, not cosmetic.
"""

import io
import typing

import pytest

from psh import protocols as P
from psh.protocols import (
    ExpansionContext,
    IOContext,
    JobRuntime,
    LocaleContext,
    VariableAccess,
)
from psh.shell import Shell

# The EXACT member-name set of each protocol — frozen (protocol-side sharpness).
# The isinstance conformance pins below are producer-side only: they would still
# pass if a protocol GAINED or LOST a member the producer happens to have. This
# freeze makes any change to a protocol's surface a deliberate edit here.
EXPECTED_MEMBERS = {
    "VariableAccess": {"get_variable", "set_variable", "get_special_variable"},
    "ExpansionContext": {"expand_string_variables", "expand_assignment_value_word",
                         "variable_expander", "word_expander"},
    "IOContext": {"stdin", "stdout", "stderr"},
    "JobRuntime": {"shell_state", "terminal_pgid_if_owned", "create_job",
                   "set_foreground_job", "transfer_terminal_control",
                   "wait_for_job", "report_signal_death_at",
                   "finish_foreground_job", "remove_job"},
    "LocaleContext": {"collate_key", "compare", "upper", "lower", "toggle",
                      "in_class"},
}


def test_protocol_member_sets_are_frozen():
    assert set(EXPECTED_MEMBERS) == set(P.__all__)
    for name, expected in EXPECTED_MEMBERS.items():
        actual = typing.get_protocol_members(getattr(P, name))
        assert actual == expected, (
            f"{name} member set changed: added {sorted(actual - expected)}, "
            f"removed {sorted(expected - actual)}. Update EXPECTED_MEMBERS only "
            f"if the protocol surface change is intended.")


@pytest.fixture
def shell():
    sh = Shell(norc=True)
    try:
        yield sh
    finally:
        try:
            sh.close()
        except Exception:
            pass


def test_shell_satisfies_iocontext(shell):
    assert isinstance(shell, IOContext)


def test_state_satisfies_variableaccess(shell):
    assert isinstance(shell.state, VariableAccess)


def test_expansion_manager_satisfies_expansioncontext(shell):
    assert isinstance(shell.expansion_manager, ExpansionContext)


def test_job_manager_satisfies_jobruntime(shell):
    assert isinstance(shell.job_manager, JobRuntime)


def test_locale_satisfies_localecontext(shell):
    assert isinstance(shell.state.locale, LocaleContext)


class _StreamsOnly:
    """A minimal IOContext: the three streams and nothing else — deliberately
    NOT a Shell (no state, no managers)."""

    def __init__(self):
        self._in = io.StringIO("hello\n")
        self._out = io.StringIO()
        self._err = io.StringIO()

    @property
    def stdin(self):
        return self._in

    @property
    def stdout(self):
        return self._out

    @property
    def stderr(self):
        return self._err


def test_iocontext_is_a_real_narrowing():
    """A non-Shell object with only the streams satisfies IOContext AND drives
    the migrated reader — proof the boundary needs only the streams."""
    from psh.builtins.input_reader import make_reader

    ctx = _StreamsOnly()
    assert isinstance(ctx, IOContext)
    assert not hasattr(ctx, "state")  # emphatically not a Shell

    cursor = make_reader(ctx, fd=0)  # a StringIO stdin → stream-backed cursor
    assert cursor is not None
    assert cursor.fd is None          # stream-backed, not fd-backed
    assert cursor.read_all() == "hello\n"
