"""Associative-array keys maintain separate values (declared arrays).

History: these tests originally exercised UNDECLARED names with quoted
subscripts (``h["Accept"]=...`` with no ``declare -A``), pinning psh's old
non-bash heuristic that a QUOTED subscript infers an associative array. bash
5.2 keys an undeclared name as an INDEXED array — the subscript is arithmetic
(``"Accept"`` evaluates to 0, so every such write collapses onto element 0, and
``"db.host"`` is a fatal arithmetic syntax error). Campaign W2's one subscript
authority made psh match bash (probed 2026-07-18: stdout and rc identical to
bash on all four old bodies), so the tests now declare their arrays first —
preserving their real intent (separate values per key) — and
``test_undeclared_name_with_quoted_subscript_is_indexed`` pins the bash
undeclared-name rule explicitly.
"""

import subprocess
import sys
from pathlib import Path

# Repo root (tests/integration/arrays/ -> three levels up), so `python -m psh`
# resolves regardless of where the checkout lives or what pytest's cwd is.
PSH_ROOT = Path(__file__).resolve().parents[3]


class TestAssociativeArrayBug:
    """Test that associative arrays correctly maintain separate values for different keys."""

    def run_psh(self, command):
        """Helper to run PSH command."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', command],
            capture_output=True,
            text=True,
            cwd=PSH_ROOT
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def test_multiple_keys_maintain_separate_values(self):
        """Test that setting multiple array keys maintains separate values."""
        # Set three different keys to different values
        code, output, _ = self.run_psh('''
declare -A h
h["Accept"]="text/html"
h["User-Agent"]="PSH/1.0"
h["Cache-Control"]="no-cache"
echo "${h[Accept]}"
echo "${h[User-Agent]}"
echo "${h[Cache-Control]}"
        ''')

        assert code == 0
        lines = output.strip().split('\n')
        assert len(lines) == 3

        # Each key should have its own value
        assert lines[0] == "text/html", f"Expected 'text/html' for Accept, got '{lines[0]}'"
        assert lines[1] == "PSH/1.0", f"Expected 'PSH/1.0' for User-Agent, got '{lines[1]}'"
        assert lines[2] == "no-cache", f"Expected 'no-cache' for Cache-Control, got '{lines[2]}'"

    def test_quoted_keys_with_dots_separate_values(self):
        """Test that keys with dots maintain separate values."""
        code, output, _ = self.run_psh('''
declare -A conf
conf["db.host"]="localhost"
conf["db.port"]="5432"
conf["api.key"]="secret123"
echo "${conf[db.host]}"
echo "${conf[db.port]}"
echo "${conf[api.key]}"
        ''')

        assert code == 0
        lines = output.strip().split('\n')
        assert len(lines) == 3

        # Each key should have its own value
        assert lines[0] == "localhost", f"Expected 'localhost' for db.host, got '{lines[0]}'"
        assert lines[1] == "5432", f"Expected '5432' for db.port, got '{lines[1]}'"
        assert lines[2] == "secret123", f"Expected 'secret123' for api.key, got '{lines[2]}'"

    def test_keys_with_spaces_separate_values(self):
        """Test that keys with spaces maintain separate values."""
        code, output, _ = self.run_psh('''
declare -A arr
arr["first key"]="first value"
arr["second key"]="second value"
arr["third key"]="third value"
echo "${arr[first key]}"
echo "${arr[second key]}"
echo "${arr[third key]}"
        ''')

        assert code == 0
        lines = output.strip().split('\n')
        assert len(lines) == 3

        assert lines[0] == "first value", f"Expected 'first value', got '{lines[0]}'"
        assert lines[1] == "second value", f"Expected 'second value', got '{lines[1]}'"
        assert lines[2] == "third value", f"Expected 'third value', got '{lines[2]}'"

    def test_special_chars_in_keys_separate_values(self):
        """Test array keys with special characters maintain separate values."""
        code, output, _ = self.run_psh('''
declare -A arr
arr["my-key"]=value1
arr["my.key"]=value2
arr["my key"]=value3
echo "${arr[my-key]}"
echo "${arr[my.key]}"
echo "${arr[my key]}"
        ''')

        assert code == 0
        lines = output.strip().split('\n')
        assert len(lines) == 3

        # Bug was showing all three as 'value3' (last value set)
        assert lines[0] == "value1", f"Expected 'value1' for my-key, got '{lines[0]}'"
        assert lines[1] == "value2", f"Expected 'value2' for my.key, got '{lines[1]}'"
        assert lines[2] == "value3", f"Expected 'value3' for my key, got '{lines[2]}'"

    def test_numeric_array_not_affected(self):
        """Test that numeric arrays still work correctly."""
        code, output, _ = self.run_psh('''
arr[0]="zero"
arr[1]="one"
arr[2]="two"
echo "${arr[0]}"
echo "${arr[1]}"
echo "${arr[2]}"
        ''')

        assert code == 0
        lines = output.strip().split('\n')
        assert len(lines) == 3

        assert lines[0] == "zero", f"Expected 'zero', got '{lines[0]}'"
        assert lines[1] == "one", f"Expected 'one', got '{lines[1]}'"
        assert lines[2] == "two", f"Expected 'two', got '{lines[2]}'"

    def test_undeclared_name_with_quoted_subscript_is_indexed(self):
        """bash: without declare -A, a quoted subscript is still ARITHMETIC.

        ``h["Accept"]=x`` on an undeclared ``h`` creates an INDEXED array —
        "Accept" evaluates to 0 (unset name), so successive quoted-key writes
        all target element 0 and the last one wins (bash 5.2, probed
        2026-07-18). Quoting does NOT infer an associative array.
        """
        code, output, _ = self.run_psh('''
h["Accept"]="text/html"
h["Cache-Control"]="no-cache"
echo "${h[0]}"
declare -p h
        ''')
        assert code == 0
        lines = output.strip().split('\n')
        assert lines[0] == "no-cache"
        # An indexed array, not associative: declare -p shows -a (bash prints
        # `declare -a h=([0]="no-cache")`; psh adds a space before `)`).
        assert lines[1].startswith('declare -a h=')

    def test_undeclared_name_dotted_subscript_is_arith_error(self):
        """bash: ``conf["db.host"]=x`` without declare -A is a fatal
        arithmetic syntax error (the dot is not an arithmetic operator)."""
        code, _, err = self.run_psh('conf["db.host"]=x')
        assert code == 1
        assert err != ""
