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


# ---- documented deliberate loss: heredoc backing substrate (R1 bounce nit 2)
#
# psh materializes EVERY heredoc/here-string in an anonymous temp file
# (`_content_to_fd` — a pipe would deadlock for bodies over the kernel pipe
# buffer, and one seekable description is what lets builtin and child share
# the H8 cursor).  bash 5.2 uses a PIPE for small heredocs and a temp file
# only for large ones.  Consequence: a consumer that exploits seekability —
# lseek(0), or a POSIX-conforming filter that reads ahead and repositions
# stdin (GNU head; BSD head does not, so macOS shows no divergence for the
# head-then-read composition) — can observe the substrate.  This is a
# DELIBERATE, documented divergence: one open description is the H8 contract;
# matching bash's small-heredoc pipe would re-split the cursor or deadlock.

def test_substrate_small_heredoc_is_seekable_documented_divergence():
    # CURRENT psh behavior pinned: lseek(0) on a small-heredoc stdin succeeds
    # (temp file).  bash's pipe-backed small heredoc fails ESPIPE (rc 1) —
    # deliberately NOT matched (see note above).
    out, err, rc = run_psh(
        'python3 -c "import os; os.lseek(0,0,0)" <<EOF\ntiny\nEOF\n'
        "echo rc=$?")
    assert out == "rc=0\n", (out, err)


def test_substrate_external_consumer_first_matches_bash_on_this_host():
    # External-consumer-first composition (bounce nit 2's row): BSD head
    # consumes the whole small body on either substrate, so psh matches
    # bash here on macOS; pinned so any substrate change surfaces visibly.
    out, err, rc = run_psh(
        'eval "head -n1 >/dev/null; read x; echo x=[$x]" <<EOF\n'
        "line1\nline2\nline3\nEOF\n")
    assert out == "x=[]\n", (out, err)
