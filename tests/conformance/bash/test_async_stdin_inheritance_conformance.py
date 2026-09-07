"""Conformance: an async command inherits the fd 0 its frame was given (C022).

POSIX gives an asynchronous command ``/dev/null`` on fd 0 when job control is
off, so a background reader cannot steal the script's input. bash applies that
default only while the SHELL still owns fd 0: when a pipeline or an enclosing
COMPOUND command's redirect supplied the frame's fd 0, the background child
INHERITS it. psh applied the default unconditionally, so the reader in
``echo hello | { cat & wait; }`` read ``/dev/null`` and the pipe's bytes were
LOST (C022).

Owner of the rule: ``psh/core/stdin_binding.py#StdinBinding``, read by
``psh/executor/process_launcher.py#AsyncJobPolicy.for_launch``.

Every row runs in all three input modes (``-c``, script file, stdin) and
asserts the BYTES the background child actually read — through the child's own
stdout, and in the capture rows through a file the child wrote and the shell
read back. Payload shapes are varied deliberately (multi-line, spaces, glob
metacharacters, expansion-looking text, UTF-8, no trailing newline, empty,
4 KiB): a corpus that never varies the input cannot catch an input-shape bug.

Verified against bash 5.3.15 (empirical; the rule is bash's ``stdin_redir``
flag in ``execute_cmd.c``, not a documented CHANGES entry).
"""

import os

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

MODES = ("-c", "file", "stdin")

# The shell's OWN stdin for the control rows: a marker no frame ever supplies,
# so "the background child read this" is distinguishable from "it read the
# frame's input" and from "it read /dev/null".
OUTER = "OUTER-SHELL-STDIN\n"

PAYLOADS = {
    "plain": "hello\n",
    "multiline": "L1\nL2\nL3\n",
    "spaces": "  lead and trail  \n",
    "glob_meta": "a*b?c[d-f]\n",
    "expansion_text": "$HOME `id` ${x} \\n\n",
    "utf8": "\u00fcn\u00ef\u00e7\u00f8d\u00e9 \u2713\n",
    "no_trailing_newline": "tail-without-newline",
    "empty": "",
    "large": "z" * 4096 + "\n",
}


def _run(runner, script, mode, *, cwd=None, stdin_data=None, stdin_mode="file",
         env=None):
    """Run *script* through *runner* in one of the three input modes."""
    if mode == "-c":
        result = runner(["-c", script], cwd=cwd, stdin_data=stdin_data,
                        stdin_mode=stdin_mode, env=env)
    elif mode == "file":
        assert cwd is not None, "script-file mode needs a caller-pinned cwd"
        path = os.path.join(cwd, "case_script.sh")
        with open(path, "w") as fh:
            fh.write(script + "\n")
        result = runner([path], cwd=cwd, stdin_data=stdin_data,
                        stdin_mode=stdin_mode, env=env)
    else:  # the script itself arrives on fd 0
        result = runner([], cwd=cwd, stdin_data=script + "\n",
                        stdin_mode=stdin_mode, env=env)
    assert is_comparable(result), f"harness failure ({mode}): {result!r}"
    return result


def _both(script, mode, tmp_path, *, stdin_data=None, stdin_mode="file",
          env=None):
    """Run one row in both shells; returns (bash, psh) results."""
    bash_dir = str(tmp_path / f"bash-{mode}")
    psh_dir = str(tmp_path / f"psh-{mode}")
    os.makedirs(bash_dir, exist_ok=True)
    os.makedirs(psh_dir, exist_ok=True)
    b = _run(run_bash, script, mode, cwd=bash_dir, stdin_data=stdin_data,
             stdin_mode=stdin_mode, env=env)
    p = _run(run_psh, script, mode, cwd=psh_dir, stdin_data=stdin_data,
             stdin_mode=stdin_mode, env=env)
    return b, p


def _assert_row(script, expected_stdout, tmp_path, *, modes=MODES,
                stdin_data=None, stdin_mode="file", env=None,
                expected_stdout_stdin_mode=None):
    """psh must match bash AND produce the named bytes, in every mode."""
    for mode in modes:
        b, p = _both(script, mode, tmp_path, stdin_data=stdin_data,
                     stdin_mode=stdin_mode, env=env)
        want = expected_stdout
        if mode == "stdin" and expected_stdout_stdin_mode is not None:
            want = expected_stdout_stdin_mode
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (
            f"[{mode}] psh vs bash: {script!r}\n"
            f"  bash={b.stdout!r} rc={b.returncode}\n"
            f"  psh ={p.stdout!r} rc={p.returncode}")
        assert p.stdout == want, (
            f"[{mode}] psh read the wrong bytes: {script!r}\n"
            f"  expected={want!r}\n  got     ={p.stdout!r}")
        assert b.stdout == want, (
            f"[{mode}] the pin's expectation is stale vs bash: {script!r}\n"
            f"  expected={want!r}\n  bash    ={b.stdout!r}")


# --------------------------------------------------------------------------
# The four inventory shapes, across the payload corpus. The background reader
# must read exactly the bytes the pipe / the redirect supplied.
# --------------------------------------------------------------------------

WRITE_IN = 'printf %s "$DATA" > in; '


SHAPES = [
    ("pipe_into_brace", 'printf %s "$DATA" | { cat & wait; }'),
    ("pipe_into_subshell", 'printf %s "$DATA" | ( cat & wait )'),
    ("brace_redirect", WRITE_IN + '{ cat & wait; } < in'),
    ("subshell_redirect", WRITE_IN + '( cat & wait ) < in'),
]


@pytest.mark.parametrize("payload_id", ["plain", "multiline", "glob_meta",
                                        "utf8", "no_trailing_newline"])
@pytest.mark.parametrize("shape,script", SHAPES)
def test_async_reader_inherits_frame_stdin(shape, script, payload_id, tmp_path):
    """C022: the four inventory shapes, one payload shape per run.

    bash 5.3.15 prints the input in every one; psh printed nothing before the
    fd-0 binding gated the POSIX ``/dev/null``.
    """
    payload = PAYLOADS[payload_id]
    _assert_row(script, payload, tmp_path, env={"DATA": payload})


@pytest.mark.parametrize("payload_id", ["spaces", "expansion_text", "empty",
                                        "large"])
@pytest.mark.parametrize("shape,script", SHAPES[:1] + SHAPES[2:3])
def test_payload_shapes_survive_the_binding(shape, script, payload_id,
                                            tmp_path):
    """C022: the awkward payload shapes on a pipe and on a compound redirect.

    Whitespace that word-splitting would eat, text that looks like an
    expansion, an EMPTY input (a control: nothing to read is not the same
    bug as reading /dev/null, and both shells must agree), and 4 KiB.
    """
    payload = PAYLOADS[payload_id]
    _assert_row(script, payload, tmp_path, env={"DATA": payload})


@pytest.mark.parametrize("payload_id", ["multiline", "spaces", "glob_meta"])
def test_pipe_into_backgrounded_read_loop(payload_id, tmp_path):
    """C022 inventory row 2: the reader is a ``while read`` loop, not ``cat``.

    ``seq 1 3 | { while read l; do echo "L$l"; done & wait; }`` — the loop runs
    in the background child, so it reads whatever fd 0 the pipeline gave the
    member.
    """
    payload = PAYLOADS[payload_id]
    script = ('printf %s "$DATA" | '
              '{ while IFS= read -r l; do printf "[%s]\\n" "$l"; done & wait; }')
    expected = "".join(f"[{line}]\n" for line in payload.splitlines())
    _assert_row(script, expected, tmp_path, env={"DATA": payload})


# --------------------------------------------------------------------------
# Every compound spelling that can supply fd 0 to its body.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape,script,expected", [
    ("if_redirect", WRITE_IN + 'if true; then cat & wait; fi < in', "IN"),
    ("for_redirect", WRITE_IN + 'for i in 1; do cat & wait; done < in', "IN"),
    ("while_redirect",
     WRITE_IN + 'while true; do cat & wait; break; done < in', "IN"),
    ("until_redirect",
     WRITE_IN + 'until false; do cat & wait; break; done < in', "IN"),
    ("case_redirect", WRITE_IN + 'case a in a) cat & wait;; esac < in', "IN"),
    ("cstyle_for_redirect",
     WRITE_IN + 'for ((i=0;i<1;i++)); do cat & wait; done < in', "IN"),
    ("nested_compound",
     WRITE_IN + '{ if true; then cat & wait; fi; } < in', "IN"),
    ("nested_brace_in_pipe",
     'printf %s "$DATA" | { { cat & wait; }; }', "IN"),
    ("explicit_fd_zero", WRITE_IN + '{ cat & wait; } 0< in', "IN"),
    ("dup_from_fd3", WRITE_IN + 'exec 3< in; { cat & wait; } <&3', "IN"),
    ("process_substitution",
     '{ cat & wait; } < <(printf %s "$DATA")', "IN"),
    ("function_definition_redirect",
     WRITE_IN + 'f() { cat & wait; } < in; f', "IN"),
    ("bg_subshell_inside_redirected_compound",
     WRITE_IN + '{ ( cat ) & wait; } < in', "IN"),
    ("bg_brace_inside_redirected_compound",
     WRITE_IN + '{ { cat; } & wait; } < in', "IN"),
    ("bg_function_inside_redirected_compound",
     WRITE_IN + 'g() { cat; }; { g & wait; } < in', "IN"),
    ("command_substitution_inside_redirected_compound",
     WRITE_IN + '{ printf "S[%s]" "$(cat & wait)"; } < in', "S[IN]"),
])
def test_compound_spellings_supply_fd0(shape, script, expected, tmp_path):
    """C022: every compound spelling whose redirect list supplies fd 0.

    ``IN`` is the payload; the command-substitution row wraps it because the
    reader's bytes travel back through ``$(...)``.
    """
    payload = "IN"
    _assert_row(script, expected, tmp_path, env={"DATA": payload})


def test_pipe_into_function_body(tmp_path):
    """C022: the pipeline member is a FUNCTION whose body backgrounds a reader."""
    _assert_row('f() { cat & wait; }; printf %s "$DATA" | f',
                "fn-payload\n", tmp_path, env={"DATA": "fn-payload\n"})


def test_here_string_supplies_fd0(tmp_path):
    """C022: a here-string on the compound is the frame's fd 0 (``<<<`` adds \\n)."""
    _assert_row('{ cat & wait; } <<< "$DATA"', "here string\n", tmp_path,
                env={"DATA": "here string"})


def test_heredoc_supplies_fd0(tmp_path):
    """C022: a heredoc on the compound is the frame's fd 0."""
    _assert_row('{ cat & wait; } <<EOF\nhd line 1\nhd line 2\nEOF',
                "hd line 1\nhd line 2\n", tmp_path)


# --------------------------------------------------------------------------
# D3: the bytes the background child WROTE, read back from the filesystem.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("payload_id", ["plain", "multiline", "utf8",
                                        "no_trailing_newline", "large"])
@pytest.mark.parametrize("shape,script", [
    ("pipe", 'printf %s "$DATA" | { cat > got & wait; }'),
    ("redirect", WRITE_IN + '{ cat > got & wait; } < in'),
])
def test_background_child_writes_what_it_read(shape, script, payload_id,
                                              tmp_path):
    """C022, D3: the background child's own bytes, taken off the disk.

    The reader writes to a file rather than to stdout, so the assertion is on
    what the CHILD consumed and stored — not on the shell's stdout plumbing.
    """
    payload = PAYLOADS[payload_id]
    for mode in MODES:
        b, p = _both(script, mode, tmp_path, env={"DATA": payload})
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (b, p)
        for label, cwd in (("oracle", tmp_path / f"bash-{mode}"),
                           ("psh", tmp_path / f"psh-{mode}")):
            got = (cwd / "got").read_text()
            assert got == payload, (
                f"[{mode}/{label}] background child stored {got!r}, "
                f"expected {payload!r}")


# --------------------------------------------------------------------------
# Controls: the POSIX /dev/null still applies. The shell's own stdin carries
# OUTER, so a row that wrongly kept it is visible as the marker rather than as
# an empty string.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape,script,expected", [
    # A top-level background reader must NOT steal the shell's stdin.
    ("toplevel_background", 'cat & wait', ""),
    # `exec < file` rebinds the SHELL's own stdin; bash still sends the async
    # child to /dev/null (fd 0 was not supplied to a frame).
    ("exec_then_background",
     'printf %s "$DATA" > in; exec < in; cat & wait', ""),
    # A function CALL's redirect is a SIMPLE command's list: no reach.
    ("function_call_redirect",
     'printf %s "$DATA" > in; f() { cat & wait; }; f < in', ""),
    # A simple command's own redirect does not outlive it.
    ("simple_redirect_then_background",
     'printf %s "$DATA" > in; cat < in > /dev/null; cat & wait', ""),
    # A compound that redirects only an OUTPUT fd supplies no fd 0.
    ("compound_output_redirect_only",
     '{ cat & wait; } > out; printf "OUT["; cat out; printf "]"', "OUT[]"),
    # An explicit redirect on the background command itself still wins fd 0
    # (the async policy runs before the child's own redirects).
    ("explicit_background_redirect",
     'printf %s "$DATA" > in; cat < in & wait', "control-input\n"),
])
def test_devnull_default_still_applies(shape, script, expected, tmp_path):
    """C022 controls: the shapes where bash keeps the POSIX ``/dev/null``.

    Each runs with the shell's own stdin holding a marker, so a regression that
    dropped the default would print ``OUTER-SHELL-STDIN`` instead of nothing.
    In stdin mode the script itself occupies fd 0, so the marker cannot be
    supplied and the expectation is the empty read both shells produce.
    """
    payload = "control-input\n"
    _assert_row(script, expected, tmp_path, env={"DATA": payload},
                stdin_data=OUTER)


# --------------------------------------------------------------------------
# DIRECTION: an OUTPUT redirect that lands on fd 0 supplies no input, so the
# POSIX default still applies. Counting it handed the background reader a
# write-only fd 0 — `{ cat & wait; } 0>&1` then blocked forever at a terminal
# (round-1 blocker B1). A CLOSE of fd 0 does count, in both shells.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape,script,expected_stdout,expect_stderr", [
    ("output_to_file_on_fd0",
     '{ cat & wait; } 0> out; echo DONE', "DONE\n", False),
    ("dup_stdout_onto_fd0",
     '{ cat & wait; } 0>&1; echo DONE', "DONE\n", False),
    ("append_to_file_on_fd0",
     '{ cat & wait; } 0>> out; echo DONE', "DONE\n", False),
    ("output_redirect_elsewhere",
     '{ cat & wait; } > out 2>&1; echo DONE', "DONE\n", False),
    # A close of fd 0 IS a stdin redirection in both shells: the child inherits
    # the closed descriptor and says so.
    ("close_fd0_output_spelling",
     '{ cat & wait; } 0>&-; echo DONE', "DONE\n", True),
    ("close_fd0_input_spelling",
     '{ cat & wait; } <&-; echo DONE', "DONE\n", True),
    # Mixed lists: an input on fd 0 anywhere in the list supplies it, and the
    # LAST redirect still decides what fd 0 ends up being.
    ("input_then_output_on_fd0",
     'printf %s "$DATA" > in; { cat & wait; } < in 0>&1; echo DONE',
     "DONE\n", True),
    ("output_then_input_on_fd0",
     'printf %s "$DATA" > in; { cat & wait; } 0> out < in', "IN", False),
])
def test_output_redirect_on_fd0_does_not_supply_input(shape, script,
                                                      expected_stdout,
                                                      expect_stderr, tmp_path):
    """C022/B1: direction matters as much as the fd number.

    Bounded by the runner's own timeout, so the regression this closes (the
    reader blocking forever on a write-only fd 0) fails as a harness mismatch
    instead of hanging the suite. The terminal spelling of the same hang is
    pinned in ``tests/system/interactive/test_pty_async_stdin_c022.py``.
    """
    for mode in MODES:
        b, p = _both(script, mode, tmp_path, env={"DATA": "IN"})
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (
            f"[{mode}] {script!r}: bash={b.stdout!r}/{b.returncode} "
            f"psh={p.stdout!r}/{p.returncode}")
        assert p.stdout == expected_stdout, (mode, p.stdout)
        # bash and psh both report the unreadable descriptor, or both stay
        # silent — the diagnostic comes from `cat`, so the text is identical.
        assert bool(p.stderr) is expect_stderr, (mode, p.stderr)
        assert p.stderr == b.stderr, (mode, p.stderr, b.stderr)


def test_shell_own_piped_stdin_is_not_a_frame_input(tmp_path):
    """C022: the SHELL's own stdin being a pipe does not count as inherited.

    With the shell's OWN stdin a pipe (``printf ... | <shell> -c 'cat & wait'``)
    fd 0 is a pipe, but no frame INSIDE the shell supplied it, so bash 5.3.15
    still applies the POSIX ``/dev/null`` and the background reader prints
    nothing. This is the case the rule's name could mislead on: it is "no frame
    supplied fd 0", not "fd 0 is a pipe".
    """
    for mode in ("-c", "file"):
        b, p = _both('cat & wait', mode, tmp_path, stdin_data=OUTER,
                     stdin_mode="pipe")
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (b, p)
        assert p.stdout == "", p.stdout


def test_set_m_disables_the_posix_default(tmp_path):
    """C022 axis: with job control ON (``set -m``) there is no ``/dev/null``.

    The reader keeps the shell's own stdin in both shells, which is what makes
    the fd-0 binding an INDEPENDENT input rather than a re-spelling of the
    job-control test.
    """
    for mode in ("-c", "file"):
        b, p = _both('set -m; cat & wait', mode, tmp_path, stdin_data=OUTER)
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (b, p)
        assert p.stdout == OUTER, p.stdout


def test_binding_ends_with_the_compound_in_separate_commands(tmp_path):
    """C022: the binding belongs to the compound, not to the rest of the script.

    Two SEPARATE top-level commands: the second ``cat &`` runs after the brace
    group's redirect is undone, so the POSIX default applies again in both
    shells. (Within ONE top-level command bash keeps suppressing — its
    ``stdin_redir`` is a single global reset per command; that divergence is a
    registered N-row, not this pin's subject.)
    """
    script = 'printf %s "$DATA" > in\n{ cat & wait; } < in\ncat & wait'
    _assert_row(script, "sep\n", tmp_path, env={"DATA": "sep\n"},
                modes=("file", "stdin"), stdin_data=OUTER,
                expected_stdout_stdin_mode="sep\n")


# --------------------------------------------------------------------------
# DECLARED DIVERGENCES (W1-N80, ruled 2026-09-07): bash tracks "did a frame
# supply fd 0" in ONE GLOBAL flag (execute_cmd.c 199/828/1733/1739/4570),
# cleared once per top-level command (eval.c:181) and never under `-c`, so it
# forgets an inherited binding a nested frame reassigns, never sets one for a
# construct that forked before the assignment, and keeps a stale one after the
# compound ends. psh scopes the binding to the frame that established it.
#
# BOTH sides are asserted here, per face, so the declaration is testable: if
# bash ever changes, these rows fail loudly (that is the flip signal), and the
# claim that psh is the SAFE side in every face is checked rather than
# summarised. A face where psh lost data bash delivers would be a DEFECT.
# --------------------------------------------------------------------------

class TestDeclaredDivergences:
    """The eight probed faces of W1-N80, each with both shells' side."""

    def _rows(self, script, tmp_path, *, modes=MODES, stdin_data=None,
              env=None):
        out = []
        for mode in modes:
            b, p = _both(script, mode, tmp_path, stdin_data=stdin_data, env=env)
            out.append((mode, b.stdout, p.stdout))
        return out

    # --- psh DELIVERS bytes bash drops (nobody reads them in bash) ---------

    @pytest.mark.parametrize("face,script,psh_out", [
        ("b_redirected_compound_is_pipeline_leader",
         WRITE_IN + '{ cat & wait; } < in | cat', "IN"),
        ("c_inner_subshell_reassigns_the_global",
         WRITE_IN + '( ( cat & wait ) ) < in', "IN"),
        ("d_inner_subshell_kills_a_pipe_binding",
         'printf %s "$DATA" | ( ( cat & wait ) )', "IN"),
        # the reader's output lands in `out`, so the row reads it back
        ("e_inner_compound_redirects_only_output",
         WRITE_IN + '{ { cat & wait; } > out; } < in; cat out', "IN"),
        ("g_the_redirected_compound_is_itself_backgrounded",
         WRITE_IN + '{ cat & wait; } < in & wait', "IN"),
        ("g_loop_spelling",
         WRITE_IN + 'for i in 1; do cat & wait; done < in & wait', "IN"),
        ("h_move_form_supplies_fd0",
         WRITE_IN + 'exec 3< in; { cat & wait; } 0<&3-', "IN"),
    ])
    def test_psh_delivers_bytes_bash_drops(self, face, script, psh_out,
                                           tmp_path):
        """bash reads the input with NOBODY: its flag was never set or was
        reassigned to 0 by an inner frame. psh delivers it to the reader."""
        for mode, bash_out, got in self._rows(script, tmp_path,
                                              env={"DATA": "IN"}):
            assert bash_out == "", (
                f"[{mode}] {face}: bash 5.3.15 no longer drops the input "
                f"({bash_out!r}) — the declared divergence may be flippable")
            assert got == psh_out, f"[{mode}] {face}: psh gave {got!r}"

    def test_g_subshell_spelling_is_NOT_a_divergence(self, tmp_path):
        """CONTROL for face g: `( ) < f &` matches, because a user subshell
        DOES set bash's flag from its own redirects (execute_cmd.c:1733)."""
        for mode, bash_out, got in self._rows(
                WRITE_IN + '( cat & wait ) < in & wait', tmp_path,
                env={"DATA": "IN"}):
            assert (bash_out, got) == ("IN", "IN"), (mode, bash_out, got)

    # --- psh WITHHOLDS the shell's own stdin from the async reader ---------
    # Nothing is destroyed: the bytes stay on the shell's stdin, which the
    # row proves by reading them back AFTER the background command.

    @pytest.mark.parametrize("face,script", [
        ("a_binding_outlives_its_compound",
         '{ true; } < in; cat & wait; read x; echo "[$x]"'),
        ("f_bash_classifier_is_fd_blind",
         '{ cat & wait; } 3< in; read x; echo "[$x]"'),
    ])
    def test_psh_withholds_the_shells_own_stdin(self, face, script, tmp_path):
        """bash hands the shell's own input to the async reader, so the shell's
        own ``read`` gets EOF; psh keeps it for the shell.

        Stdin mode is excluded: there the script itself occupies fd 0, so the
        marker cannot be supplied (the shape is not expressible, not skipped
        for convenience).
        """
        script = 'printf %s "$DATA" > in; ' + script
        for mode, bash_out, got in self._rows(
                script, tmp_path, modes=("-c", "file"),
                stdin_data="A\nB\n", env={"DATA": "IN"}):
            assert bash_out == "A\nB\n[]\n", (
                f"[{mode}] {face}: bash 5.3.15 side changed: {bash_out!r}")
            assert got == "[A]\n", (
                f"[{mode}] {face}: psh should have left the shell's stdin "
                f"alone, got {got!r}")
