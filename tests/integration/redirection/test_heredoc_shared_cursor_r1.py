"""R1: one here-input open description shared by builtin and child (#20 H8).

Base defect (5989ed9e): ``IOManager._builtin_redirect_stdin`` fed a builtin's
``sys.stdin`` a fresh ``io.StringIO(content)`` for ``<<``/``<<-``/``<<<`` while
the fd-level half materialized the SAME body onto fd 0 in a temp file.  Two
independent cursors: a builtin ``read`` consuming the StringIO did not advance
fd 0, so a following external ``cat`` (or another fd-0 reader) replayed content
the builtin already consumed.

Bash uses one open file description; ``read`` then ``cat`` under one heredoc
share the offset.  psh's ``<`` path already shares fd 0 via
``dup_sharing_stream(0, 'r')`` (proven: ``eval 'read x; cat' < file`` works at
base), so the fix routes heredocs/here-strings through the same shared cursor.

Bash-5.2 verified (tmp/boundary-ledgers/R1-probes/probe2-base-5989ed9e.txt).
"""
import os
import subprocess
import sys

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def run_psh(script):
    env = dict(os.environ)
    env["PYTHONPATH"] = TREE
    env["PSH_STRICT_ERRORS"] = "0"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       cwd=TREE, env=env, capture_output=True, text=True,
                       timeout=60)
    return p.stdout, p.stderr, p.returncode


def test_heredoc_read_then_cat_shares_offset():
    # read consumes AAA from fd 0; cat (external) must resume at BBB, not replay.
    out, err, rc = run_psh("eval 'read x; cat' <<EOF\nAAA\nBBB\nCCC\nEOF\n")
    assert out == "BBB\nCCC\n", (out, err)


def test_heredoc_read_echo_var_then_cat():
    out, err, rc = run_psh(
        "eval 'read x; echo GOT:$x; cat' <<EOF\nAAA\nBBB\nEOF\n")
    assert out == "GOT:AAA\nBBB\n", (out, err)


def test_herestring_partial_read_then_cat_shares_offset():
    # read -n1 consumes 'H'; cat must resume at 'ELLO', not replay HELLO.
    out, err, rc = run_psh("eval 'read -n1 x; echo x=$x; cat' <<<'HELLO'")
    assert out == "x=H\nELLO\n", (out, err)


def test_heredoc_strip_tabs_shared_cursor():
    # <<- variant shares the cursor too.
    out, err, rc = run_psh(
        "eval 'read x; cat' <<-EOF\n\tAAA\n\tBBB\nEOF\n")
    assert out == "BBB\n", (out, err)


def test_heredoc_two_builtins_read_then_read_still_ok():
    # Control: two builtin reads under one heredoc (both consume fd 0 in order).
    out, err, rc = run_psh(
        "eval 'read a; read b; echo a=$a b=$b' <<EOF\none\ntwo\nEOF\n")
    assert out == "a=one b=two\n", (out, err)


def test_heredoc_quoted_delim_shared_cursor_no_expansion():
    # Quoted delimiter: no expansion, still one shared cursor.
    out, err, rc = run_psh(
        "eval 'read x; cat' <<'EOF'\n$HOME\nkeep\nEOF\n")
    assert out == "keep\n", (out, err)
    assert "$HOME" not in out  # first line consumed literally by read
