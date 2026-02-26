"""Interactive shell components.

Submodules:
    base             - InteractiveComponent ABC and InteractiveManager orchestrator
    repl_loop        - REPLLoop: main Read-Eval-Print Loop
    history_manager  - HistoryManager: command history load/save/add
    completion_manager - CompletionManager: tab completion via readline
    prompt_manager   - PromptManager: PS1/PS2 prompt expansion
    signal_manager   - SignalManager: signal handling, SIGCHLD/SIGWINCH self-pipe
    rc_loader        - load_rc_file / is_safe_rc_file: startup RC file loading
    title            - Terminal window title updates (OSC 0)
"""
from .base import InteractiveComponent, InteractiveManager
from .completion_manager import CompletionManager
from .history_manager import HistoryManager
from .prompt_manager import PromptManager
from .rc_loader import is_safe_rc_file, load_rc_file
from .repl_loop import REPLLoop
from .signal_manager import SignalManager
from .title import command_title, idle_title, set_terminal_title

__all__ = [
    'InteractiveManager',
    'load_rc_file',
    'set_terminal_title',
    'idle_title',
    'command_title',
]
