"""for/select loop variable when the header comes from an alias (C010).

Improvement Program 2026-09, slot 1.7. A ``for``/``select`` header supplied by
an alias used to take its loop variable from a SOURCE SLICE of the pre-alias
line: the tokens carry alias-body positions while the parser's ``source_text``
is the line the user typed, so ``for i`` sliced ``e`` out of ``beg echo …`` and
the loop silently bound the WRONG NAME. Reproduce the closed defect with::

    shopt -s expand_aliases; alias beg='for i in 1 2; do'
    beg echo "i=[$i]"; done          # bash: i=[1] i=[2]

Empirical, bash 5.3.15: aliases in a non-interactive shell need
``shopt -s expand_aliases`` and the definition on its own line, so every script
here carries both. psh always expands and treats the shopt as a no-op gate (a
documented divergence), which the shared prologue keeps out of the comparison.

D3 — each row pins the variable ACTUALLY BOUND, not just a return code: the
body expands it, and ``declare -p`` after the loop shows what the parent shell
holds. Every row runs in all three input modes (-c, script file, stdin).
"""
import os
import tempfile

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

_PROLOGUE = "shopt -s expand_aliases\n"

# (id, script). Each script defines an alias whose body is a loop HEADER, uses
# it, and then reports the binding the loop left behind.
_CASES = [
    # --- the three inventory shapes ---
    ("for_body_expands_it",
     "alias beg='for i in 1 2; do'\n"
     'beg echo "i=[$i]"; done\n'
     "declare -p i"),
    ("for_colon_body_no_spurious_diagnostic",
     "alias beg='for i in 1 2; do'\n"
     "beg :; done\n"
     'echo "rc=$?"\n'
     "declare -p i"),
    ("select_binds_the_choice",
     "alias sel='select v in a b; do'\n"
     'sel echo "v=[$v]"; break; done <<< 1\n'
     "declare -p v"),
    # --- the alias body's length relative to the alias NAME ---
    # (the corrupting slice is taken at the token's offset in the OTHER string,
    #  so a longer expansion can even run off the end of the short line)
    ("expansion_longer_than_alias_name",
     "alias b='for longvariablename in 1 2; do'\n"
     'b echo "[$longvariablename]"; done\n'
     "declare -p longvariablename"),
    ("expansion_shorter_than_alias_name",
     "alias averyveryverylongaliasname='for q in 1; do'\n"
     'averyveryverylongaliasname echo "[$q]"; done\n'
     "declare -p q"),
    ("alias_body_ends_in_a_newline",
     "alias beg='for i in 1 2; do\n'\n"
     'beg echo "[$i]"; done\n'
     "declare -p i"),
    ("nested_alias_supplies_the_for_keyword",
     "alias a1='for'\n"
     "alias a2='a1 x in 1 2; do'\n"
     'a2 echo "[$x]"; done\n'
     "declare -p x"),
    ("for_without_in_iterates_positionals",
     "set -- p q\n"
     "alias beg='for i; do'\n"
     'beg echo "[$i]"; done\n'
     "declare -p i"),
    ("alias_header_names_an_invalid_identifier",
     # bash rejects the NAME at execution and continues; the diagnostic must
     # name `1x', the alias body's word, not a slice of the using line.
     "alias bad='for 1x in a; do'\n"
     "bad :; done\n"
     'echo "rc=$?"'),
    # --- controls: constructs that never took a name from a slice ---
    ("control_c_style_for_via_alias",
     "alias cst='for ((n=0; n<2; n++)); do'\n"
     'cst echo "[$n]"; done\n'
     "declare -p n"),
    ("control_case_subject_via_alias",
     "alias cs='case abc in'\n"
     "cs a*) echo MATCH;; *) echo OTHER;; esac"),
    ("control_plain_for_no_alias",
     'for i in 1 2; do echo "i=[$i]"; done\n'
     "declare -p i"),
    ("control_plain_select_no_alias",
     'select v in a b; do echo "v=[$v]"; break; done <<< 1\n'
     "declare -p v"),
]

_MODES = ["-c", "file", "stdin"]


def _run(runner, script, mode, cwd):
    if mode == "-c":
        r = runner(["-c", script], timeout=30, cwd=cwd)
    elif mode == "stdin":
        r = runner([], stdin_data=script + "\n", stdin_mode="pipe",
                   timeout=30, cwd=cwd)
    else:  # file
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         dir=cwd) as f:
            f.write(script + "\n")
            path = f.name
        try:
            r = runner([path], timeout=30, cwd=cwd)
        finally:
            os.unlink(path)
    assert is_comparable(r), r
    return r


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("case_id,body", _CASES, ids=[c[0] for c in _CASES])
def test_alias_loop_variable_matches_bash(case_id, body, mode):
    """psh binds the loop variable bash binds, and reports it the same way."""
    script = _PROLOGUE + body
    with tempfile.TemporaryDirectory() as bd, tempfile.TemporaryDirectory() as pd:
        bash = _run(run_bash, script, mode, bd)
        psh = _run(run_psh, script, mode, pd)

    assert psh.stdout == bash.stdout, (
        f"[{case_id}/{mode}] stdout divergence\n"
        f"  script: {script!r}\n  bash: {bash.stdout!r}\n  psh:  {psh.stdout!r}")
    assert psh.returncode == bash.returncode, (
        f"[{case_id}/{mode}] exit status: bash={bash.returncode} psh={psh.returncode}")
    # The diagnostic-bearing row must diagnose in BOTH shells, naming the same
    # subject. A `select` row's stderr is the numbered MENU plus the `#?`
    # prompt, which both shells write there and which must agree character for
    # character. Every other row must stay silent in both (a dropped `[Errno 1]
    # Operation not permitted` host flake identifies itself here instead of
    # looking like a regression).
    if case_id == "alias_header_names_an_invalid_identifier":
        assert "`1x': not a valid identifier" in bash.stderr, bash.stderr
        assert "`1x': not a valid identifier" in psh.stderr, psh.stderr
    elif "select" in case_id:
        assert psh.stderr == bash.stderr, (
            f"[{case_id}/{mode}] select menu divergence\n"
            f"  bash: {bash.stderr!r}\n  psh:  {psh.stderr!r}")
        assert bash.stderr != "", "the select menu should have reached stderr"
    else:
        assert bash.stderr == "", bash.stderr
        assert psh.stderr == "", psh.stderr


@pytest.mark.parametrize("mode", _MODES)
def test_alias_for_loop_variable_is_i_in_the_ast(mode):
    """--debug-ast names the loop variable ``i``, not a slice of the using line.

    The AST is the field the executor reads (``set_variable(node.variable,
    item)``), so this pins the corrupted value at its source: base printed
    ``variable: "e"``.
    """
    script = (_PROLOGUE + "alias beg='for i in 1 2; do'\n"
              "beg :; done")
    with tempfile.TemporaryDirectory() as pd:
        if mode == "-c":
            r = run_psh(["--debug-ast", "-c", script], timeout=30, cwd=pd)
        elif mode == "stdin":
            r = run_psh(["--debug-ast"], stdin_data=script + "\n",
                        stdin_mode="pipe", timeout=30, cwd=pd)
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                             dir=pd) as f:
                f.write(script + "\n")
                path = f.name
            r = run_psh(["--debug-ast", path], timeout=30, cwd=pd)
    assert is_comparable(r), r
    dump = r.stdout + r.stderr
    assert "ForLoop" in dump, dump
    assert 'variable: "i"' in dump, dump
