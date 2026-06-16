#!/usr/bin/env python3
"""Key binding modes for command line editing."""

from enum import Enum, auto
from typing import Dict, Optional


class EditMode(Enum):
    """Editing modes available."""
    EMACS = auto()
    VI_INSERT = auto()
    VI_NORMAL = auto()


class KeyBindings:
    """Base class for key binding implementations.

    The subclass-specific attribute annotations below are type-only (no
    assignment): EmacsKeyBindings provides ``meta_bindings``; ViKeyBindings
    provides ``mode``/``insert_bindings``/``normal_bindings``. Declaring them
    on the base lets the editor hold either binding type as a single
    ``KeyBindings`` and access the mode-appropriate attribute (the editor
    only ever reaches an attribute on the matching mode's binding object).
    """

    # Emacs-only (set by EmacsKeyBindings.setup_bindings)
    meta_bindings: Dict[str, str]
    # Vi-only (set by ViKeyBindings)
    mode: "EditMode"
    insert_bindings: Dict[str, str]
    normal_bindings: Dict[str, str]

    # Common control characters
    CTRL_A = '\x01'
    CTRL_B = '\x02'
    CTRL_C = '\x03'
    CTRL_D = '\x04'
    CTRL_E = '\x05'
    CTRL_F = '\x06'
    CTRL_G = '\x07'
    CTRL_H = '\x08'
    CTRL_K = '\x0b'
    CTRL_L = '\x0c'
    CTRL_N = '\x0e'
    CTRL_P = '\x10'
    CTRL_R = '\x12'
    CTRL_T = '\x14'
    CTRL_U = '\x15'
    CTRL_W = '\x17'
    CTRL_Y = '\x19'
    CTRL_UNDERSCORE = '\x1f'

    TAB = '\t'
    ENTER = '\r'
    BACKSPACE = '\x7f'
    ESCAPE = '\x1b'

    def __init__(self):
        self.bindings: Dict[str, str] = {}
        self.setup_bindings()

    def setup_bindings(self):
        """Setup key bindings - to be overridden by subclasses."""
        pass

    def get_action(self, key: str) -> Optional[str]:
        """Get the action name for a key, if any."""
        return self.bindings.get(key)


class EmacsKeyBindings(KeyBindings):
    """Emacs-style key bindings."""

    def setup_bindings(self):
        """Setup Emacs key bindings."""
        self.bindings = {
            # Movement
            self.CTRL_A: 'move_beginning_of_line',
            self.CTRL_E: 'move_end_of_line',
            self.CTRL_F: 'move_forward_char',
            self.CTRL_B: 'move_backward_char',

            # Editing
            self.CTRL_D: 'delete_char',
            self.CTRL_H: 'backward_delete_char',
            self.BACKSPACE: 'backward_delete_char',
            self.CTRL_K: 'kill_line',
            self.CTRL_U: 'kill_to_beginning',  # readline unix-line-discard
            self.CTRL_W: 'kill_word_backward',
            self.CTRL_Y: 'yank',
            self.CTRL_T: 'transpose_chars',

            # History
            self.CTRL_P: 'previous_history',
            self.CTRL_N: 'next_history',
            self.CTRL_R: 'reverse_search_history',

            # Other
            self.CTRL_L: 'clear_screen',
            self.CTRL_G: 'abort',
            self.CTRL_C: 'interrupt',
            self.TAB: 'complete',
            self.ENTER: 'accept_line',
        }

        # Meta (Alt) key bindings
        self.meta_bindings = {
            'b': 'move_word_backward',
            'f': 'move_word_forward',
            'd': 'kill_word_forward',
            self.BACKSPACE: 'kill_word_backward',
            '<': 'move_to_first_history',
            '>': 'move_to_last_history',
        }


class ViKeyBindings(KeyBindings):
    """Vi-style key bindings.

    Deliberately a SUBSET of vi: every binding listed here is implemented
    by LineEditor._execute_action. (Earlier versions bound ~30 more actions
    — registers, motions, visual mode, search — that silently did nothing.)
    """

    def __init__(self):
        super().__init__()
        # Kept in sync with LineEditor.mode by _enter_vi_*_mode()
        self.mode = EditMode.VI_INSERT

    def setup_bindings(self):
        """Setup Vi key bindings for both insert and normal modes."""
        # Insert mode bindings
        self.insert_bindings = {
            self.ESCAPE: 'enter_normal_mode',
            self.CTRL_C: 'interrupt',
            self.BACKSPACE: 'backward_delete_char',
            self.CTRL_H: 'backward_delete_char',
            self.CTRL_W: 'kill_word_backward',
            self.CTRL_U: 'kill_to_beginning',  # readline unix-line-discard
            self.TAB: 'complete',
            self.ENTER: 'accept_line',
        }

        # Normal mode bindings (implemented subset only)
        self.normal_bindings = {
            # Mode switching
            'i': 'enter_insert_mode',
            'I': 'enter_insert_mode_at_beginning',
            'a': 'append_mode',
            'A': 'append_mode_at_end',

            # Movement
            'h': 'move_backward_char',
            'l': 'move_forward_char',
            'j': 'next_history',
            'k': 'previous_history',
            'w': 'move_word_forward',
            'b': 'move_word_backward',
            '0': 'move_beginning_of_line',
            '$': 'move_end_of_line',
            'G': 'move_to_last_history',

            # Editing
            'x': 'delete_char',
            'X': 'backward_delete_char',
            'u': 'undo',
            self.CTRL_R: 'redo',

            # Other
            self.CTRL_L: 'clear_screen',
            self.CTRL_C: 'interrupt',
            self.ENTER: 'accept_line',
        }

    def get_action(self, key: str) -> Optional[str]:
        """Get the action for a key based on current mode."""
        if self.mode == EditMode.VI_NORMAL:
            return self.normal_bindings.get(key)
        return self.insert_bindings.get(key)
