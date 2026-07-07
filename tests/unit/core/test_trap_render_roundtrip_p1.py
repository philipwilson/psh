"""Core-state Phase 1: trap -p renders a reusable single-quoted action (H2/E3).

``trap -p`` must emit an action that re-parses to the same trap (bash uses
``sh_single_quote``: wrap in single quotes, render each embedded ``'`` as the
``'\\''`` close/escape/reopen). psh wrapped the raw action in bare single
quotes, so an action containing a single quote produced non-reusable input.

The round-trip test is the real proof: render ``trap -p``, feed it back to a
fresh shell, and assert the re-derived rendering is identical. INT is a
managed signal (no OS handler installed), so these are safe in-process. Fixed
in Commit 5 by rendering the action through the shared ``single_quote`` helper.
"""

import pytest

from psh.shell import Shell


def _render(action):
    """Set INT trap to *action*, return the `trap -p INT` line (no newline)."""
    sh = Shell(norc=True)
    try:
        sh.trap_manager.set_trap(action, ["INT"])
        display, _invalid = sh.trap_manager.show_traps(["INT"])
        return display
    finally:
        sh.close()


def _reparse_action(rendered_line):
    """Run a `trap -- 'action' SIGINT` line in a fresh shell and return the
    action string it stored (the round-trip target)."""
    sh = Shell(norc=True)
    try:
        rc = sh.run_command(rendered_line)
        assert rc == 0, f"re-parsing {rendered_line!r} failed"
        return sh.trap_manager.get_handler("INT")
    finally:
        sh.close()


def test_single_quote_action_roundtrips():
    action = "echo 'x'"
    rendered = _render(action)
    # bash: trap -- 'echo '\''x'\''' SIGINT
    assert rendered == "trap -- 'echo '\\''x'\\''' SIGINT"
    assert _reparse_action(rendered) == action


@pytest.mark.parametrize("action", [
    "echo 'x'",
    "echo 'a' 'b'",
    "printf '%s\\n' 'it'\\''s'",
])
def test_quote_heavy_actions_roundtrip(action):
    assert _reparse_action(_render(action)) == action


class TestTrapRenderRegression:
    """Actions without single quotes already round-trip — keep it so."""

    @pytest.mark.parametrize("action", [
        "echo hi",
        "echo $x",
        "echo a\\b",
        "echo one\necho two",
    ])
    def test_simple_actions_roundtrip(self, action):
        assert _reparse_action(_render(action)) == action

    def test_ignored_action_renders_empty_quotes(self):
        assert _render("") == "trap -- '' SIGINT"
