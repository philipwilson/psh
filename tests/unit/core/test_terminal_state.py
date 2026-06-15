"""Unit tests for the TerminalState decomposition (R9.B1)."""

import os
from unittest import mock

from psh.core.terminal_state import TerminalState


def test_defaults_are_non_terminal():
    ts = TerminalState()
    assert ts.is_terminal is False
    assert ts.terminal_fd is None
    assert ts.supports_job_control is False


def test_detect_non_tty_leaves_all_false():
    ts = TerminalState()
    with mock.patch.object(os, "isatty", return_value=False):
        ts.detect()
    assert ts.is_terminal is False
    assert ts.terminal_fd is None
    assert ts.supports_job_control is False


def test_detect_tty_with_job_control():
    ts = TerminalState()
    with mock.patch.object(os, "isatty", return_value=True), \
         mock.patch.object(os, "tcgetpgrp", return_value=4321):
        ts.detect()
    assert ts.is_terminal is True
    assert ts.terminal_fd == 0
    assert ts.supports_job_control is True


def test_detect_tty_without_job_control():
    ts = TerminalState()
    with mock.patch.object(os, "isatty", return_value=True), \
         mock.patch.object(os, "tcgetpgrp", side_effect=OSError("no job control")):
        ts.detect()
    assert ts.is_terminal is True
    assert ts.terminal_fd == 0
    assert ts.supports_job_control is False


def test_state_properties_delegate_to_terminal_object():
    """ShellState exposes the three attrs as properties over self.terminal."""
    from psh.core.state import ShellState

    state = ShellState()
    assert state.is_terminal is state.terminal.is_terminal
    # setter path writes through to the object
    state.supports_job_control = True
    assert state.terminal.supports_job_control is True
    state.terminal_fd = 0
    assert state.terminal.terminal_fd == 0
