"""INTERACTIVE (real PTY) heredoc-vs-not detection (slot 2.5, #22 MEDIUM-3).

WHY THE ESCAPED SPELLING NEEDS A PTY PIN. For `echo \\<<EOF` SPECIFICALLY, the
defect is latent everywhere except a terminal: the session's completeness
oracle used a second, REGEX heredoc grammar that read the escaped `<` as
opening a heredoc on `EOF`, while the real lexer -- and bash -- see an escaped
`<` plus an ordinary input redirection. Non-interactively the flush path
re-lexes and that wrong answer never surfaces, so a `-c` pin for THAT SHAPE
would have been green on base and proven nothing. Only at a terminal is the
session's answer observable: psh dropped to PS2 and swallowed the next line as
a phantom body.

SCOPE OF THAT CLAIM -- it is about the escaped spelling and nothing else. Round
2 established that the slot's OTHER shapes do move non-interactively (exit
status, stdout and stderr all change for the unclosed-quote and
substitution-delimiter shapes, on both parsers and all three channels). Those
are pinned in tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py.
Do not read "latent non-interactively" as a slot-wide property; it was measured
for one spelling.

THE OBSERVABLE is the PROMPT the shell offers after the last shape line: PS1
means it considered the input complete, PS2 means it wants more. Each line's
prompt is consumed as it arrives (see `_drive`).

Rows may ALSO assert a MARKER: a follow-up `echo MARK""ER` whose execution is
checked. That matters because a prompt sequence alone cannot distinguish
"complete with a syntax error, next line runs" from "complete, next line runs"
-- and round-4 verification showed exactly that blind spot let a degenerate
regression through. The `""` is load-bearing: a terminal echoes the typed
bytes, so a literal `echo MARKER` would appear in the transcript even when
nothing ran; quote-splitting makes the typed echo and the executed output
textually distinct. Marker assertions are REQUIRED on the degenerate rows and
optional elsewhere -- extending them to every row would roughly double this
module's runtime for observables the prompt sequence already pins.

AXES (ruling R1-E). The corpus varies: SPELLING (escaped `\\<<`, escaped second
`<\\<`, escaped-escape `\\\\<<`), QUOTING (`'<<EOF'`, `"<<EOF"`, `<<'EOF'`),
OPERATOR ADJACENCY (`<<<`, `<<-`, digit-prefixed `0<<`, arithmetic `$((1<<2))`),
NESTING (`<<` inside an unclosed `$(`, and the defect's own spelling inside a
closed `$( )`), and OPTION STATE (`set -o posix` on the divergent spelling plus
two true-heredoc controls). Every row asserts BOTH shells, so an improvement on
either side fails this pin instead of passing unnoticed.

FOR A NIGHTLY READER (Linux): the bash-side expectations were measured against
bash 5.2.26 on macOS. Nothing here is platform-specific (no signals, no
/dev/fd, no locale collation), but a failure showing a DIFFERENT bash answer is
a bash-VERSION difference, not a psh regression -- check the oracle's version
first. This module resolves its oracle AT IMPORT and raises if bash is absent;
that loudness is deliberate and must not be converted into a skip to make a
nightly green.
"""

import os
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")

# The blessed bash oracle, through the ONE resolver — never a hardcoded path.
from shell_oracle import resolve_bash  # noqa: E402

# Module scope on purpose: a missing oracle must be LOUD at import, not a
# silent per-test skip that reports green while the comparison never runs.
_ORACLE = resolve_bash()

PSH_ROOT = str(Path(__file__).resolve().parents[3])

pytestmark = pytest.mark.serial

# (id, lines to send before `echo MARK""ER`, line-1-is-COMPLETE)
# `complete=True`  -> the shell runs the follow-up: marker_ran, no PS2.
# `complete=False` -> the shell waits for a here-document body: PS2, no marker.
# (label, lines, line-1-is-COMPLETE, marker-ran or None)
_ROWS = [
    # THE DEFECT: `\<` is an escaped literal '<'; what is left is `<EOF`, an
    # ordinary input redirection, so the line is COMPLETE.
    ("escaped_lt", [r"echo \<<EOF"], True, None),
    # The escaped SECOND '<': `<` redirect whose target word unquotes to `<EOF`.
    ("escaped_second_lt", [r"echo <\<EOF"], True, None),
    # An escaped BACKSLASH followed by a REAL heredoc — must stay incomplete.
    ("double_backslash", ["echo \\\\<<EOF"], False, None),
    # QUOTING: text, not an operator.
    ("single_quoted", ["echo '<<EOF'"], True, None),
    ("double_quoted", ['echo "<<EOF"'], True, None),
    # OPERATOR ADJACENCY.
    ("here_string", ["cat <<<EOF"], True, None),
    ("arith_shift", ["echo $((1<<2))"], True, None),
    # TRUE heredoc controls: these must REMAIN incomplete-detected. Without
    # them a fix that simply stopped detecting heredocs would pass.
    ("true_heredoc", ["cat <<EOF"], False, None),
    ("true_heredoc_strip", ["cat <<-EOF"], False, None),
    ("true_heredoc_fd", ["cat 0<<EOF"], False, None),
    ("true_heredoc_quoted", ["cat <<'EOF'"], False, None),
    # NESTING: a heredoc inside an unclosed substitution stays incomplete...
    ("nested_cmdsub_heredoc", ["echo $(cat <<EOF"], False, None),
    # ... and the defect's spelling one level down is complete.
    ("nested_cmdsub_escaped", [r"echo $(echo \<<EOF)"], True, None),
    # OPTION STATE: the divergent spelling and two controls under POSIX mode.
    ("posix_escaped_lt", ["set -o posix", r"echo \<<EOF"], True, None),
    ("posix_true_heredoc", ["set -o posix", "cat <<EOF"], False, None),
    ("posix_true_heredoc_strip", ["set -o posix", "cat <<-EOF"], False, None),
    # OPERATOR ADJACENCY, `<&` family (the brief enumerates it; round-1
    # blocker R4-E caught its absence).
    # `echo` rather than `cat` IS DELIBERATE -- please do not "fix" it back.
    # `cat` with stdin dup'd from the terminal blocks reading the terminal, so
    # no prompt ever returns and the row TIMES OUT; that timeout would look
    # like a completeness answer while actually measuring nothing. `echo`
    # ignores its stdin, so the redirect is still exercised and the prompt
    # still arrives.
    ("fd_dup_in", ["echo x <&0"], True, None),
    ("fd_dup_numbered", ["echo x 0<&0"], True, None),

    # --- FD-KIND axis: NAMED fds (round-2 blocker R7-A) ---
    # THE REGRESSION THIS SLOT CAUSED, now pinned. The retired regex scanner
    # knew the `{v}<<` spelling; the LEXER did not, emitting `{v}<` plus a
    # second `<`. Once the regex stopped being consulted, nothing registered
    # the here-document, the session called the line COMPLETE, and the body
    # lines EXECUTED AS COMMANDS (`body: command not found`) where base and
    # bash both hold the line open. Neither corpus caught it because the
    # FD-KIND axis had only ever been varied by DIGIT (`0<<`).
    ("named_fd_heredoc", ["true {v}<<EOF"], False, None),
    ("named_fd_heredoc_strip", ["true {v}<<-EOF"], False, None),
    ("named_fd_heredoc_quoted", ["true {v}<<'EOF'"], False, None),
    ("named_fd_exec", ["exec {v}<<EOF"], False, None),
    # ... with the control that keeps those rows honest: a named fd with a
    # SINGLE `<` is an ordinary redirect and must stay COMPLETE, so a fix that
    # over-matched `{v}<` as a heredoc would fail here.
    ("named_fd_plain_redirect", ["echo x {v}</dev/null"], True, None),
    # The here-string spelling on a named fd (round-3 blocker R9-A): complete,
    # like every other here-string, and it parse-errored at base.
    ("named_fd_herestring", ["true {v}<<<hello"], True, None),

    # --- DEGENERATE axis: operator present, OPERAND ABSENT (blocker R10-A) ---
    # The fourth ring of one pattern. Round 3 taught the lexer `{v}<<`; nobody
    # sweept the corner where the operator has NO delimiter. More input can
    # never complete one of these (a newline ends the redirect), so bash
    # reports a syntax error and runs the next line -- and so did BASE. The
    # round-3 tip instead dropped to PS2 and swallowed the next physical line:
    # the exact MEDIUM-3 shape this slot exists to close, reintroduced on the
    # surface the slot itself created.
    #
    # These rows carry MARKER assertions because the prompt sequence alone
    # cannot tell "complete with a syntax error, follow-up runs" from
    # "complete, follow-up runs" -- and that blind spot is why it stayed
    # invisible through three rounds.
    ("degenerate_named_heredoc", ["cat {v}<<"], True, True),
    ("degenerate_named_strip", ["cat {v}<<-"], True, True),
    ("degenerate_named_herestring", ["cat {v}<<<"], True, True),

    # --- R10-B: `<<` inside an assignment subscript ---
    # Base's regex read `]=1` as a here-document delimiter and went to PS2
    # forever; tip reports the error and carries on, like bash. In-charter
    # (it is the second grammar misfiring) and declared as an improvement.
    ("subscript_shift_operator", ["a[<<]=1"], True, True),

    # --- The two DECLARED interactive improvements (round-1 blocker R4-B) ---
    # Both were RED ON BASE and both now match bash; measured at base
    # e36116c3 in a discriminator-verified probe worktree (ledger B18).
    #
    # (1) SUBSTITUTION-BEARING DELIMITER. A heredoc delimiter is taken
    # LITERALLY, so `cat <<$(x)` terminates on a line reading `$(x)`. The
    # retired regex scanner stopped at `(` and cooked the delimiter to `$`, so
    # base terminated on a line `$` and did NOT terminate on `$(x)` — both
    # backwards. The lexer's spec has always had it right; the one-grammar fix
    # simply inherits that.
    ("subst_delim_dollar", ["cat <<$(x)", "hi", "$"], False, None),
    ("subst_delim_full", ["cat <<$(x)", "hi", "$(x)"], True, None),
    # (2) HEREDOC + UNCLOSED QUOTE ON ONE LINE. `cat <<EOF "abc` leaves a
    # quote open, and bash keeps reading for the QUOTE, not the body. Deriving
    # the heredoc answer from the lex — which fails on the unclosed quote —
    # makes the quote outcome win, as in bash; base answered HEREDOC and
    # executed the buffer at line 3.
    ("heredoc_unclosed_dq", ['cat <<EOF "abc', "EOF", 'def"'], False, None),
]


def _env():
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "dumb",
        "PS1": "P1> ", "PS2": "P2> ",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": PSH_ROOT,
    }


def _sync(child):
    """Leave the stream at a KNOWN point: just after a completed command.

    Prompt counting is only meaningful from a known baseline, and the shells
    do not offer one at spawn — psh's line editor redraws its prompt, so a
    plain `expect(PS1)` can consume a redraw and leave a real prompt queued,
    which shifts every later read by one and made `cat <<EOF` report PS1.
    Running a sentinel command and consuming ITS output plus the prompt that
    follows removes the ambiguity for both shells.
    """
    child.send('echo REA""DY\r')
    child.expect("READY")
    child.expect(r"P1> ")
    return child


def _spawn_psh(parser, cwd):
    child = pexpect.spawn(
        sys.executable,
        ["-u", "-m", "psh", "--norc", "--force-interactive",
         "--parser", parser],
        timeout=20, encoding="utf-8", env=_env(), cwd=cwd)
    child.expect(r"P1> ")
    return _sync(child)


def _spawn_bash(cwd):
    child = pexpect.spawn(_ORACLE.path, ["--norc", "-i"], timeout=20,
                          encoding="utf-8", env=_env(), cwd=cwd)
    child.expect(r"P1> ")
    return _sync(child)


def _drive(child, lines):
    """Send the shape line(s) one at a time, reading the PROMPT after each.

    The observable is the prompt the shell offers after the LAST shape line:
    PS1 means it considered the input complete, PS2 means it wants more. Each
    line's prompt is consumed as it arrives, which is what makes multi-line
    rows readable — during a 3-line heredoc the shell legitimately shows PS2
    for lines 1 and 2, so a detector that merely raced "MARKER vs any PS2"
    would call every multi-line row incomplete regardless of its outcome.

    Consuming prompts also keeps the module fast: no row waits out a timeout,
    because every line produces a prompt promptly. A TIMEOUT is a third,
    always-failing outcome, so a hung shell can never read as agreement.
    """
    prompts, transcript = [], ""
    try:
        for line in lines:
            child.send(line + "\r")
            index = child.expect([r"P1> ", r"P2> ", pexpect.TIMEOUT],
                                 timeout=15)
            transcript += (child.before or "") + (child.after or "")
            if index == 2:                                   # pragma: no cover
                return "timeout", prompts, transcript
            prompts.append("PS1" if index == 0 else "PS2")
    except pexpect.TIMEOUT:                                  # pragma: no cover
        return "timeout", prompts, transcript + (child.before or "")
    outcome = "complete" if prompts[-1] == "PS1" else "incomplete"
    return outcome, prompts, transcript


def _drive_marker(child):
    """Send `echo MARK""ER` and report whether it EXECUTED.

    Distinguishes "complete with a syntax error, follow-up runs" from
    "incomplete, follow-up swallowed" -- which the prompt sequence alone
    cannot, and which is why the degenerate regression stayed invisible.
    """
    child.send('echo MARK""ER\r')
    return child.expect(["MARKER", pexpect.TIMEOUT], timeout=8) == 0


@pytest.mark.parametrize("label,lines,complete,marker", _ROWS,
                         ids=[r[0] for r in _ROWS])
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_interactive_heredoc_detection_matches_bash(label, lines, complete,
                                                    marker, parser, tmp_path):
    cwd = str(tmp_path)
    expected = "complete" if complete else "incomplete"

    bash_child = _spawn_bash(cwd)
    try:
        b_outcome, b_prompts, b_transcript = _drive(bash_child, lines)
    finally:
        bash_child.close(force=True)

    psh_child = _spawn_psh(parser, cwd)
    try:
        p_outcome, p_prompts, p_transcript = _drive(psh_child, lines)
    finally:
        psh_child.close(force=True)

    assert "Traceback (most recent call last)" not in p_transcript, \
        p_transcript[-400:]

    # BOTH shells are asserted against the declared expectation, so a bash
    # change is as loud as a psh change. `timeout` is a third, always-failing
    # outcome, so a hung shell can never read as agreement.
    # (The failure labels deliberately avoid a bare "bash" as the first tuple
    # element: the oracle-resolution ratchet reads `("bash", ...)` as an argv
    # head. Renaming the label is the honest fix; an allowlist entry for an
    # assertion message would have blunted a guard that is doing its job.)
    assert b_outcome == expected, ("bash-side", label, b_prompts,
                                   b_transcript[-400:])
    assert p_outcome == expected, ("psh-side", label, parser, p_prompts,
                                   p_transcript[-400:])

    # The full prompt SEQUENCE must agree too, not just the final answer: two
    # shells can reach the same end state by different routes, and for the
    # multi-line rows that route is the behaviour under test.
    assert b_prompts == p_prompts, (label, parser, b_prompts, p_prompts)

    if marker is not None:
        # Re-drive both shells: the marker leg needs a live child, and the
        # comparison shells above were closed to keep the fixture hygienic.
        b2 = _spawn_bash(cwd)
        try:
            _drive(b2, lines)
            b_marker = _drive_marker(b2)
        finally:
            b2.close(force=True)
        p2 = _spawn_psh(parser, cwd)
        try:
            _drive(p2, lines)
            p_marker = _drive_marker(p2)
        finally:
            p2.close(force=True)
        assert b_marker is marker, ("bash-side marker", label, b_marker)
        assert p_marker is marker, ("psh-side marker", label, parser, p_marker)


# --- The FENCED pre-existing divergence (ruling R10-A(4)) ---------------------

_PREEXISTING_DEGENERATE = ["cat <<", "cat 0<<", "cat <<<", "cat 0<<<"]


@pytest.mark.parametrize("line", _PREEXISTING_DEGENERATE)
@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_divergence_plain_and_digit_degenerate_forms(line, parser,
                                                            tmp_path):
    """A DIVERGENCE row, pinned as a divergence rather than hidden.

    Named `test_divergence_*` to the campaign convention so the FLIP-PINS
    enumeration finds it: an invisible divergence pin defeats its own purpose
    (round-5 nit 1). When the successor closes this row, THIS test is the one
    that must be consciously flipped.

    For the PLAIN and DIGIT spellings with no operand, bash reports a syntax
    error and returns to PS1 while psh waits at PS2. This is PRE-EXISTING and
    base-identical -- it predates slot 2.5 and the round-4 controls measured it
    at both SHAs -- so ruling R10-A(4) fences it: it is a SUCCESSOR row, not
    something to fix under cover of a regression repair. The named-fd spellings
    ARE fixed (see the degenerate_named_* rows above) because the slot itself
    broke those.

    Pinned in the divergent direction so that closing it later is a DELIBERATE,
    visible flip rather than a silent one. It cannot live in the table above,
    whose rows assert both shells against ONE expectation.
    """
    cwd = str(tmp_path)
    bash_child = _spawn_bash(cwd)
    try:
        b_outcome, _, _ = _drive(bash_child, [line])
    finally:
        bash_child.close(force=True)
    psh_child = _spawn_psh(parser, cwd)
    try:
        p_outcome, _, p_transcript = _drive(psh_child, [line])
    finally:
        psh_child.close(force=True)

    assert b_outcome == "complete", (line, b_outcome)
    assert p_outcome == "incomplete", (line, parser, p_outcome,
                                       p_transcript[-200:])
