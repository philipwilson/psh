"""Parser configuration control commands.

These builtins are a thin, HONEST front-end over the shell options that
genuinely affect how input is lexed, parsed, and expanded:

* ``posix``      — POSIX tokenize/runtime mode (also ``set -o posix``)
* ``braceexpand``— brace expansion (also ``set -o braceexpand``)
* ``histexpand`` — history expansion (also ``set -o histexpand``)

They deliberately do NOT expose "parser feature gates" (arithmetic/arrays/
functions/aliases/process-subst) or an error-collection "permissive" mode:
the production grammar is not feature-configurable — those toggles set options
no code reads. Only options that have a real effect are advertised.
"""

from typing import List

from .base import Builtin
from .registry import builtin


@builtin
class ParserConfigBuiltin(Builtin):
    """Control parser configuration settings."""

    name = "parser-config"

    # User-facing feature name -> underlying shell option. Only options that
    # actually change parsing/expansion behavior are listed.
    _FEATURE_MAP = {
        'brace_expand': 'braceexpand',
        'brace_expansion': 'braceexpand',
        'history_expand': 'histexpand',
        'history_expansion': 'histexpand',
    }

    @property
    def synopsis(self) -> str:
        return "parser-config [COMMAND] [ARG]"

    @property
    def help(self) -> str:
        return """parser-config: parser-config [COMMAND] [ARG]
    Control parser configuration settings.

    With no arguments, shows current parser configuration (same as 'show').

    Commands:
      show              Show current parser configuration
      mode MODE         Set parsing mode (posix|bash)
      strict            Enable strict POSIX mode
      enable FEATURE    Enable a parser feature
      disable FEATURE   Disable a parser feature

    Features:
      brace-expand      Brace expansion
      history-expand    History expansion

    Exit Status:
    Returns success unless an unknown command or feature is given."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the parser-config builtin."""
        if len(args) == 1:
            # No arguments - show current configuration
            return self._show_config(shell)

        command = args[1].lower()

        if command == "show":
            return self._show_config(shell)
        elif command == "mode":
            if len(args) < 3:
                self.error("mode requires an argument", shell)
                return 2
            return self.set_mode(args[2], shell)
        elif command == "strict":
            return self.set_mode("posix", shell)
        elif command == "enable":
            if len(args) < 3:
                self.error("enable requires a feature name", shell)
                return 2
            return self._enable_feature(args[2], shell)
        elif command == "disable":
            if len(args) < 3:
                self.error("disable requires a feature name", shell)
                return 2
            return self._disable_feature(args[2], shell)
        else:
            self.error(f"unknown command: {command}", shell)
            return 1

    def _show_config(self, shell) -> int:
        """Show current parser configuration."""
        self.write_line("Parser Configuration:", shell)

        posix_mode = shell.state.options.get('posix', False)
        mode = "strict POSIX" if posix_mode else "bash compatible"

        self.write_line(f"  Mode:            {mode}", shell)
        self.write_line(f"  POSIX strict:    {'on' if posix_mode else 'off'}", shell)

        # Show feature status (based on shell options)
        self.write_line("\nFeatures:", shell)
        self.write_line(f"  Brace expansion: {'on' if shell.state.options.get('braceexpand', True) else 'off'}", shell)
        self.write_line(f"  History expand:  {'on' if shell.state.options.get('histexpand', True) else 'off'}", shell)

        return 0

    def set_mode(self, mode: str, shell) -> int:
        """Set parsing mode."""
        mode = mode.lower()

        if mode in ('posix', 'strict'):
            shell.state.options['posix'] = True
            # Disable non-POSIX features
            shell.state.options['braceexpand'] = False
            shell.state.options['histexpand'] = False
            self.write_line("Parser mode set to strict POSIX", shell)

        elif mode in ('bash', 'compatible'):
            shell.state.options['posix'] = False
            # Enable bash features
            shell.state.options['braceexpand'] = True
            shell.state.options['histexpand'] = True
            self.write_line("Parser mode set to Bash compatible", shell)

        else:
            self.error(f"unknown mode: {mode}", shell)
            self.error("Valid modes: posix, bash", shell)
            return 1

        return 0

    def _set_feature(self, feature: str, shell, *, enable: bool) -> int:
        """Enable or disable a parser feature (shared by the two public ops)."""
        feature = feature.lower().replace('-', '_')

        if feature not in self._FEATURE_MAP:
            self.error(f"unknown feature: {feature}", shell)
            self.error("Valid features: brace-expand, history-expand", shell)
            return 1

        option_name = self._FEATURE_MAP[feature]
        shell.state.options[option_name] = enable
        self.write_line(f"Parser feature '{feature}' {'enabled' if enable else 'disabled'}", shell)
        return 0

    def _enable_feature(self, feature: str, shell) -> int:
        """Enable a parser feature."""
        return self._set_feature(feature, shell, enable=True)

    def _disable_feature(self, feature: str, shell) -> int:
        """Disable a parser feature."""
        return self._set_feature(feature, shell, enable=False)


@builtin
class ParserModeBuiltin(Builtin):
    """Quick parser mode switching command."""

    name = "parser-mode"

    @property
    def synopsis(self) -> str:
        return "parser-mode [MODE]"

    @property
    def help(self) -> str:
        return """parser-mode: parser-mode [MODE]
    Quick parser mode switching command.

    With no arguments, shows the current parser mode.
    Shorthand for 'parser-config mode MODE'.

    Modes:
      posix          Strict POSIX compliance mode
      bash           Bash-compatible mode (default)

    Exit Status:
    Returns success unless an unknown mode is given."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the parser-mode builtin."""
        if len(args) == 1:
            # Show current mode
            posix_mode = shell.state.options.get('posix', False)
            mode = "posix" if posix_mode else "bash"
            self.write_line(f"Parser mode: {mode}", shell)
            return 0

        mode = args[1].lower()

        # Delegate to parser-config builtin
        config_builtin = ParserConfigBuiltin()
        return config_builtin.set_mode(mode, shell)
