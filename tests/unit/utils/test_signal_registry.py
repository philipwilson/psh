"""Tests for SignalRegistry functionality."""
import signal

from psh.utils.signal_utils import SignalRegistry, get_signal_registry, set_signal_registry


class TestSignalNameRendering:
    """The registry renders signal names via the module's single source of
    truth (signal_number_to_name), NOT a private hand-rolled map."""

    def test_signals_builtin_renders_named_signal(self, captured_shell):
        """SIGUSR1 renders by name in the `signals` builtin, not Signal-<n>.

        Regression pin (reappraisal #19 D5 / ast-utils M3): the old
        SignalRegistry.SIGNAL_NAMES 9-entry hand map omitted SIGUSR1, so the
        builtin printed 'Signal-30' (macOS) / 'Signal-10' (Linux) while the
        module's own SIGNAL_NUMBER_TO_NAME[30] was 'USR1'. Red-on-base: pre-fix
        output contains 'Signal-<n>' and lacks 'SIGUSR1'.
        """
        prev_reg = get_signal_registry(create=False)
        prev_handler = signal.getsignal(signal.SIGUSR1)
        try:
            reg = SignalRegistry()
            reg.register(signal.SIGUSR1, signal.SIG_DFL, "test")
            set_signal_registry(reg)
            captured_shell.clear_output()
            rc = captured_shell.run_command("signals")
            out = captured_shell.get_stdout()
            assert rc == 0
            assert "SIGUSR1" in out
            assert f"Signal-{int(signal.SIGUSR1)}" not in out
        finally:
            signal.signal(signal.SIGUSR1, prev_handler)
            set_signal_registry(prev_reg)


class TestSignalRegistry:
    """Tests for the SignalRegistry class."""

    def test_registry_creation(self):
        """Test that registry can be created."""
        registry = SignalRegistry()
        assert registry is not None
        assert registry.get_handler(signal.SIGINT) is None

    def test_register_handler(self):
        """Test registering a signal handler."""
        registry = SignalRegistry()

        def handler(sig, frame):
            pass

        # Register handler
        registry.register(signal.SIGUSR1, handler, "test")

        # Verify it was registered
        record = registry.get_handler(signal.SIGUSR1)
        assert record is not None
        assert record.signal_num == signal.SIGUSR1
        # Signal name comes from the module's single source of truth, so a
        # real signal renders by name (not the Signal-N fallback).
        assert record.signal_name == "SIGUSR1"
        assert record.handler == handler
        assert record.component == "test"

    def test_register_sig_dfl(self):
        """Test registering SIG_DFL."""
        registry = SignalRegistry()

        registry.register(signal.SIGUSR1, signal.SIG_DFL, "test")

        record = registry.get_handler(signal.SIGUSR1)
        assert record is not None
        assert record.handler == signal.SIG_DFL

    def test_register_sig_ign(self):
        """Test registering SIG_IGN."""
        registry = SignalRegistry()

        registry.register(signal.SIGUSR1, signal.SIG_IGN, "test")

        record = registry.get_handler(signal.SIGUSR1)
        assert record is not None
        assert record.handler == signal.SIG_IGN

    def test_report_empty(self):
        """Test report with no handlers."""
        registry = SignalRegistry()

        report = registry.report()
        assert "No signal handlers registered" in report

    def test_report_with_handlers(self):
        """Test report with handlers."""
        registry = SignalRegistry()

        def handler(sig, frame):
            pass

        registry.register(signal.SIGUSR1, handler, "TestComponent")

        report = registry.report()
        assert "Signal Handler Registry Report" in report
        assert "TestComponent" in report
        assert "handler()" in report

    def test_report_verbose(self):
        """Test verbose report includes history."""
        registry = SignalRegistry()

        registry.register(signal.SIGUSR1, signal.SIG_DFL, "test1")
        registry.register(signal.SIGUSR1, signal.SIG_IGN, "test2")

        report = registry.report(verbose=True)
        assert "Signal Handler History" in report
        assert "test1" in report
        assert "test2" in report

    def test_format_handler_function(self):
        """Test handler formatting for functions."""
        registry = SignalRegistry()

        def my_handler(sig, frame):
            pass

        registry.register(signal.SIGUSR1, my_handler, "test")

        record = registry.get_handler(signal.SIGUSR1)
        formatted = registry._format_handler(record.handler)
        assert "my_handler()" in formatted

    def test_format_handler_sig_dfl(self):
        """Test handler formatting for SIG_DFL."""
        registry = SignalRegistry()

        registry.register(signal.SIGUSR1, signal.SIG_DFL, "test")

        record = registry.get_handler(signal.SIGUSR1)
        formatted = registry._format_handler(record.handler)
        assert "SIG_DFL" in formatted
        assert "default" in formatted

    def test_format_handler_sig_ign(self):
        """Test handler formatting for SIG_IGN."""
        registry = SignalRegistry()

        registry.register(signal.SIGUSR1, signal.SIG_IGN, "test")

        record = registry.get_handler(signal.SIGUSR1)
        formatted = registry._format_handler(record.handler)
        assert "SIG_IGN" in formatted
        assert "ignore" in formatted


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_signal_registry_creates(self):
        """Test that get_signal_registry creates registry."""
        # Clear global
        set_signal_registry(None)

        # Get should create
        registry = get_signal_registry(create=True)
        assert registry is not None

    def test_get_signal_registry_no_create(self):
        """Test get_signal_registry with create=False."""
        # Clear global
        set_signal_registry(None)

        # Get without create should return None
        registry = get_signal_registry(create=False)
        assert registry is None

    def test_set_signal_registry(self):
        """Test setting the global registry."""
        custom_registry = SignalRegistry()

        set_signal_registry(custom_registry)

        retrieved = get_signal_registry(create=False)
        assert retrieved is custom_registry

    def test_global_registry_persistence(self):
        """Test that global registry persists across calls."""
        set_signal_registry(None)

        # First call creates
        registry1 = get_signal_registry(create=True)

        # Second call returns same instance
        registry2 = get_signal_registry(create=True)

        assert registry1 is registry2


class TestSignalNames:
    """Tests for signal name mapping."""

    def test_names_from_single_source_of_truth(self):
        """Registered records get their name from signal_number_to_name, so
        every real signal renders by name (SIGUSR1, not Signal-N)."""
        registry = SignalRegistry()

        registry.register(signal.SIGINT, signal.SIG_DFL, "test")
        registry.register(signal.SIGUSR1, signal.SIG_DFL, "test")

        assert registry.get_handler(signal.SIGINT).signal_name == "SIGINT"
        # SIGUSR1 was absent from the retired hand-rolled map (Signal-N bug).
        assert registry.get_handler(signal.SIGUSR1).signal_name == "SIGUSR1"


class TestStackCapture:
    """Tests for stack trace capture."""

    def test_capture_stack_disabled_by_default(self):
        """Test that stack capture is disabled by default."""
        registry = SignalRegistry()

        registry.register(signal.SIGUSR1, signal.SIG_DFL, "test")

        record = registry.get_handler(signal.SIGUSR1)
        assert record.call_stack is None

    def test_capture_stack_enabled(self):
        """Test stack capture when enabled."""
        registry = SignalRegistry(capture_stack=True)

        registry.register(signal.SIGUSR1, signal.SIG_DFL, "test")

        record = registry.get_handler(signal.SIGUSR1)
        assert record.call_stack is not None
        # Stack should contain Python file references
        assert ".py" in record.call_stack
        # Should contain multiple frames
        assert "File" in record.call_stack
