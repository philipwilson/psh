"""Parser configuration control commands."""

from typing import List

from .base import Builtin
from .registry import builtin


@builtin
class ParserConfigBuiltin(Builtin):
    """Control parser configuration settings."""

    name = "parser-config"

    # Map user-facing parser feature names to the underlying shell option.
    _FEATURE_MAP = {
        'arithmetic': 'no_arithmetic',
        'arrays': 'no_arrays',
        'functions': 'no_functions',
        'aliases': 'no_aliases',
        'brace_expand': 'braceexpand',
        'brace_expansion': 'braceexpand',
        'history_expand': 'histexpand',
        'history_expansion': 'histexpand',
        'process_subst': 'process_substitution',
        'process_substitution': 'process_substitution',
    }

    # Options whose truthiness means "enabled"; the rest are ``no_*`` options
    # whose truthiness means "disabled" (so enabling them sets False).
    _POSITIVE_OPTIONS = ('braceexpand', 'histexpand', 'process_substitution')

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
      mode MODE         Set parsing mode (posix|bash|permissive|educational)
      strict            Enable strict POSIX mode
      permissive        Enable permissive mode
      enable FEATURE    Enable a parser feature
      disable FEATURE   Disable a parser feature

    Features:
      arithmetic        Arithmetic evaluation (( ))
      arrays            Array support
      functions         Function definitions
      aliases           Alias expansion
      process-subst     Process substitution
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
            return self._set_mode(args[2], shell)
        elif command == "strict":
            return self._set_mode("posix", shell)
        elif command == "permissive":
            return self._set_mode("permissive", shell)
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
        print("Parser Configuration:", file=shell.stdout)

        # Show parsing mode
        posix_mode = shell.state.options.get('posix', False)
        collect_errors = shell.state.options.get('collect_errors', False)
        debug_parser = shell.state.options.get('debug-parser', False)

        if posix_mode:
            mode = "strict POSIX"
        elif collect_errors:
            mode = "permissive"
        else:
            mode = "bash compatible"

        print(f"  Mode:            {mode}", file=shell.stdout)
        print(f"  POSIX strict:    {'on' if posix_mode else 'off'}", file=shell.stdout)
        print(f"  Collect errors:  {'on' if collect_errors else 'off'}", file=shell.stdout)
        print(f"  Debug parser:    {'on' if debug_parser else 'off'}", file=shell.stdout)

        # Show feature status (based on shell options)
        print("\nFeatures:", file=shell.stdout)
        print(f"  Arithmetic:      {'on' if not shell.state.options.get('no_arithmetic', False) else 'off'}", file=shell.stdout)
        print(f"  Arrays:          {'on' if not shell.state.options.get('no_arrays', False) else 'off'}", file=shell.stdout)
        print(f"  Functions:       {'on' if not shell.state.options.get('no_functions', False) else 'off'}", file=shell.stdout)
        print(f"  Aliases:         {'on' if not shell.state.options.get('no_aliases', False) else 'off'}", file=shell.stdout)
        print(f"  Brace expansion: {'on' if shell.state.options.get('braceexpand', True) else 'off'}", file=shell.stdout)
        print(f"  History expand:  {'on' if shell.state.options.get('histexpand', True) else 'off'}", file=shell.stdout)

        return 0

    def _set_mode(self, mode: str, shell) -> int:
        """Set parsing mode."""
        mode = mode.lower()

        if mode in ('posix', 'strict'):
            shell.state.options['posix'] = True
            shell.state.options['collect_errors'] = False
            # Disable non-POSIX features
            shell.state.options['braceexpand'] = False
            shell.state.options['histexpand'] = False
            print("Parser mode set to strict POSIX", file=shell.stdout)

        elif mode in ('bash', 'compatible'):
            shell.state.options['posix'] = False
            shell.state.options['collect_errors'] = False
            # Enable bash features
            shell.state.options['braceexpand'] = True
            shell.state.options['histexpand'] = True
            print("Parser mode set to Bash compatible", file=shell.stdout)

        elif mode == 'permissive':
            shell.state.options['posix'] = False
            shell.state.options['collect_errors'] = True
            # Enable all features
            shell.state.options['braceexpand'] = True
            shell.state.options['histexpand'] = True
            print("Parser mode set to permissive", file=shell.stdout)

        elif mode == 'educational':
            shell.state.options['posix'] = False
            shell.state.options['collect_errors'] = True
            shell.state.options['debug-parser'] = True
            # Enable features but with debugging
            shell.state.options['braceexpand'] = True
            shell.state.options['histexpand'] = True
            print("Parser mode set to educational (with debugging)", file=shell.stdout)

        else:
            self.error(f"unknown mode: {mode}", shell)
            self.error("Valid modes: posix, bash, permissive, educational", shell)
            return 1

        return 0

    def _set_feature(self, feature: str, shell, *, enable: bool) -> int:
        """Enable or disable a parser feature (shared by the two public ops).

        ``_POSITIVE_OPTIONS`` are stored truthy-means-enabled; the remaining
        ``no_*`` options are stored truthy-means-disabled, so enabling them
        sets the option False.
        """
        feature = feature.lower().replace('-', '_')

        if feature not in self._FEATURE_MAP:
            self.error(f"unknown feature: {feature}", shell)
            self.error("Valid features: arithmetic, arrays, functions, aliases, brace-expand, history-expand", shell)
            return 1

        option_name = self._FEATURE_MAP[feature]
        positive = option_name in self._POSITIVE_OPTIONS
        # Positive option: stored value == desired enabled state.
        # Negative (no_*) option: stored value == inverse of enabled state.
        shell.state.options[option_name] = enable if positive else not enable
        print(f"Parser feature '{feature}' {'enabled' if enable else 'disabled'}", file=shell.stdout)
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
      permissive     Permissive mode with error collection
      educational    Educational mode with debugging

    Exit Status:
    Returns success unless an unknown mode is given."""

    def execute(self, args: List[str], shell) -> int:
        """Execute the parser-mode builtin."""
        if len(args) == 1:
            # Show current mode
            posix_mode = shell.state.options.get('posix', False)
            collect_errors = shell.state.options.get('collect_errors', False)
            debug_parser = shell.state.options.get('debug-parser', False)

            if posix_mode:
                mode = "posix"
            elif debug_parser:
                mode = "educational"
            elif collect_errors:
                mode = "permissive"
            else:
                mode = "bash"

            print(f"Parser mode: {mode}", file=shell.stdout)
            return 0

        mode = args[1].lower()

        # Delegate to parser-config builtin
        config_builtin = ParserConfigBuiltin()
        return config_builtin._set_mode(mode, shell)
