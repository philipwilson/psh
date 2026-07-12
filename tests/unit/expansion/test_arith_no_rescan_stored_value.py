"""A STORED value reached via variable resolution is NOT re-$-expanded.

T8 item 5. bash never rescans a substituted value: a variable/array element
whose value literally contains a ``$`` is a syntax error inside ``$(( ))``, not
the value of the referenced variable. Before this fix psh re-expanded such a
value (``y=5; x='$y'; echo $((x))`` printed ``5``); now it errors like bash,
restoring the package's own never-rescan invariant.

The name-chain / expression-value resolutions (``a=b b=c c=3; echo $((a))``,
``a="2*3"; echo $((a))``) are a SEPARATE mechanism (ARITH-VALUE recursion, not
$-expansion) and MUST keep working — pinned here as the escalation guard.

Every expectation probe-verified against bash 5.2.
"""

import subprocess
import sys

import pytest


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=30)


class TestStoredValueNotReExpanded:
    """RED-ON-BASE: base psh re-$-expanded and printed the referenced value."""

    @pytest.mark.parametrize("cmd", [
        "y=5; x='$y'; echo $((x))",                    # bare name -> $y value
        "y=5; x='1+$y'; echo $((x))",                  # expr value with a $var
        "y=5; arr=('$y'); echo $((arr[0]))",           # indexed elt (_string_to_int)
        "declare -A h; y=5; h[k]='$y'; echo $((h[k]))",  # assoc elt (_string_to_int)
    ])
    def test_dollar_in_stored_value_is_error(self, cmd):
        r = _psh(cmd)
        assert r.returncode == 1, r
        assert r.stdout == "", r
        # psh renders arithmetic syntax errors with its own wording; bash's is
        # "syntax error: operand expected". Only rc + empty stdout are pinned
        # against bash (the compare-bash goldens); the message shape is psh's.
        assert "arithmetic error" in r.stderr

    def test_line_is_discarded_then_resumes(self):
        # $(( )) expansion error drops the rest of the current line (bash).
        r = _psh("y=5; x='$y'; echo $((x)) tail; echo alive")
        assert r.returncode == 1
        assert r.stdout == ""

    def test_double_paren_command_continues(self):
        # (( )) is a command, not word expansion: status 1, line continues.
        r = _psh("y=5; x='$y'; (( x )); echo rc=$?; echo alive")
        assert r.stdout == "rc=1\nalive\n"
        assert r.returncode == 0


class TestArithValueRecursionStillWorks:
    """Escalation guard: legitimate value-as-expression resolution is intact."""

    @pytest.mark.parametrize("cmd,expected", [
        ('a=b; b=c; c=3; echo $((a))', '3\n'),        # bare-name chain
        ('a="2*3"; echo $((a))', '6\n'),               # expression value
        ('a="2+3"; echo $((a + 1))', '6\n'),           # expr value in larger expr
        ('a="2*3"; b=a; echo $((b))', '6\n'),          # chained expression ref
        ('a=b; b=42; echo $((a))', '42\n'),            # bare-id indirection
        ('x=0x10; echo $((x))', '16\n'),               # hex value
        ('x=010; echo $((x))', '8\n'),                 # octal value
        ('x=2#101; echo $((x))', '5\n'),               # base#n value
        ('x="1+2*3"; echo $((x))', '7\n'),             # precedence in value
        ('a="b+1"; b=5; echo $((a))', '6\n'),          # expr value referencing var
        ('arr=(2 3); echo $((arr[0]+arr[1]))', '5\n'),  # array ints
        ('arr=("1+1"); echo $((arr[0]))', '2\n'),      # array elt is an expression
    ])
    def test_value_as_expression_resolves(self, cmd, expected):
        r = _psh(cmd)
        assert r.returncode == 0, r
        assert r.stdout == expected, r
