"""
Integration tests for while loops.

Tests cover:
- Basic while loops
- Break and continue
- Nested loops
- Complex conditions
"""



class TestWhileLoops:
    """Test while loop functionality."""

    def test_basic_while_loop(self, shell, capsys):
        """Test basic while loop."""
        cmd = '''
        count=0
        while [ $count -lt 3 ]; do
            echo "count: $count"
            count=$((count + 1))
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "count: 0" in captured.out
        assert "count: 1" in captured.out
        assert "count: 2" in captured.out
        assert "count: 3" not in captured.out

    def test_while_with_break(self, shell, capsys):
        """Test while loop with break."""
        cmd = '''
        count=0
        while true; do
            echo "count: $count"
            count=$((count + 1))
            if [ $count -eq 3 ]; then
                break
            fi
        done
        echo "after loop"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "count: 0" in captured.out
        assert "count: 1" in captured.out
        assert "count: 2" in captured.out
        assert "count: 3" not in captured.out
        assert "after loop" in captured.out

    def test_while_with_continue(self, shell, capsys):
        """Test while loop with continue."""
        cmd = '''
        count=0
        while [ $count -lt 5 ]; do
            count=$((count + 1))
            if [ $count -eq 3 ]; then
                continue
            fi
            echo "count: $count"
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "count: 1" in captured.out
        assert "count: 2" in captured.out
        assert "count: 3" not in captured.out  # Skipped by continue
        assert "count: 4" in captured.out
        assert "count: 5" in captured.out

    def test_nested_while_loops(self, shell, capsys):
        """Test nested while loops."""
        cmd = '''
        i=0
        while [ $i -lt 2 ]; do
            j=0
            while [ $j -lt 2 ]; do
                echo "i=$i j=$j"
                j=$((j + 1))
            done
            i=$((i + 1))
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "i=0 j=0" in captured.out
        assert "i=0 j=1" in captured.out
        assert "i=1 j=0" in captured.out
        assert "i=1 j=1" in captured.out

    def test_while_with_command_condition(self, tmp_path):
        """Test while with command as condition.

        Uses subprocess because 'read' from redirected stdin
        conflicts with pytest's output capture.
        """
        import subprocess
        import sys
        testfile = tmp_path / "testfile"
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             f'echo "line1" > {testfile}\n'
             f'echo "line2" >> {testfile}\n'
             f'echo "line3" >> {testfile}\n'
             f'while read line; do echo "Read: $line"; done < {testfile}'],
            capture_output=True, text=True
        )
        assert "Read: line1" in result.stdout
        assert "Read: line2" in result.stdout
        assert "Read: line3" in result.stdout

    def test_while_with_pipeline_condition(self, shell, capsys):
        """Test while with pipeline in condition."""
        cmd = '''
        count=0
        while echo "$count" | grep -q "^[012]$"; do
            echo "count is 0, 1, or 2: $count"
            count=$((count + 1))
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "count is 0, 1, or 2: 0" in captured.out
        assert "count is 0, 1, or 2: 1" in captured.out
        assert "count is 0, 1, or 2: 2" in captured.out

    def test_while_false_never_executes(self, shell, capsys):
        """Test while with false condition never executes."""
        cmd = '''
        echo "before"
        while false; do
            echo "should not print"
        done
        echo "after"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "before" in captured.out
        assert "after" in captured.out
        assert "should not print" not in captured.out

    def test_while_with_arithmetic_condition(self, shell, capsys):
        """Test while with arithmetic condition."""
        cmd = '''
        x=5
        while (( x > 0 )); do
            echo "x=$x"
            x=$((x - 1))
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "x=5" in captured.out
        assert "x=4" in captured.out
        assert "x=3" in captured.out
        assert "x=2" in captured.out
        assert "x=1" in captured.out
        assert "x=0" not in captured.out

    def test_while_with_multiple_breaks(self, shell, capsys):
        """Test while with break at different levels."""
        cmd = '''
        i=0
        while [ $i -lt 5 ]; do
            j=0
            while [ $j -lt 5 ]; do
                if [ $i -eq 2 ] && [ $j -eq 2 ]; then
                    break 2  # Break out of both loops
                fi
                echo "i=$i j=$j"
                j=$((j + 1))
            done
            i=$((i + 1))
        done
        echo "done"
        '''
        exit_code = shell.run_command(cmd)
        captured = capsys.readouterr()
        # `break 2` is supported and matches bash 5.2 (last output is
        # "i=2 j=1", then "done"). The checks used to hang off
        # `if exit_code == 0 and "done" in captured.out:`, so a psh that did
        # not support multi-level break passed by skipping them.
        assert exit_code == 0
        assert "done" in captured.out
        # Stopped at i=2 j=2 — nothing at or past that point ran.
        assert "i=2 j=2" not in captured.out
        assert "i=2 j=3" not in captured.out
        assert "i=3 j=0" not in captured.out

    def test_while_with_function(self, shell, capsys):
        """Test while loop calling function."""
        cmd = '''
        count=0
        should_continue() {
            [ $count -lt 3 ]
        }

        while should_continue; do
            echo "count: $count"
            count=$((count + 1))
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "count: 0" in captured.out
        assert "count: 1" in captured.out
        assert "count: 2" in captured.out
        assert "count: 3" not in captured.out

    def test_while_empty_body(self, shell, capsys):
        """Test while loop with empty body."""
        cmd = '''
        count=0
        while [ $count -lt 3 ]; do
            # Empty body except for increment
            count=$((count + 1))
        done
        echo "count after: $count"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "count after: 3" in captured.out

    def test_while_oneline(self, shell, capsys):
        """Test while loop on single line."""
        shell.run_command('x=0; while [ $x -lt 2 ]; do echo $x; x=$((x+1)); done')
        captured = capsys.readouterr()
        assert "0\n1" in captured.out
