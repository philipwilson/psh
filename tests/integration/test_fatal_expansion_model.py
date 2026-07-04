"""bash's fatal expansion-error model (reappraisal #17 Tier-2 arith cluster).

Probe-verified against bash 5.2 (tmp/probes-r17t2-arith/truth_table.py —
error kinds x contexts x input modes, 440 cells, all matching). Three
families:

1. DISCARD-LINE — failed word arithmetic ($((1/0)), $((5%0)), arith syntax
   errors), bad-NAME substitution (${}), failglob no-match, substring /
   indirection errors: the rest of the current input line dies (killing
   &&/|| tails, if bodies, function/group bodies on that line) and
   execution resumes at the NEXT line with $? = 1 — in every input mode.
   Contained at subshell/cmdsub boundaries AND at eval/source/trap-action
   boundaries. Does not interact with set -e (except failglob, which
   under set -e exits a non-interactive shell).

2. ASSIGNMENT/SUBSCRIPT arith errors (declare -i v='1/0', v='1/0' with -i,
   ${a[1//]}, a[1//]=x, unset 'a[08]'): discard-line in every mode EXCEPT
   -c, where bash abandons the REST OF THE -c STRING (rc 1, passes through
   eval, contained at fork boundaries).

3. SHELL-EXIT — ${x:?msg}, unknown-@X-transform on a SET variable, and
   set -u violations: a non-interactive shell (script file, -c, piped
   stdin) EXITS — with the error's own status under -c (127 for these
   kinds), 1 otherwise. eval does NOT contain it. An interactive (or
   embedded) shell discards the line with status 1.

These are subprocess tests: the input-mode axis (-c vs script file vs
piped stdin vs -i) lives in __main__/source-processor paths that
in-process fixtures cannot exercise.
"""

import subprocess
import sys

import pytest

PSH = [sys.executable, '-m', 'psh']


def psh_c(cmd, cwd=None):
    return subprocess.run(PSH + ['-c', cmd], capture_output=True,
                          text=True, timeout=15, cwd=cwd)


def psh_stdin(script, cwd=None, flags=()):
    return subprocess.run(PSH + list(flags), input=script,
                          capture_output=True, text=True, timeout=15, cwd=cwd)


def psh_file(tmp_path, script):
    p = tmp_path / "case.sh"
    p.write_text(script)
    return subprocess.run(PSH + [str(p)], capture_output=True,
                          text=True, timeout=15)


class TestDiscardLineFamily:
    """Family 1: the line dies, the next line runs, $? = 1."""

    def test_c_one_line_kills_tail(self):
        r = psh_c('echo x$((1/0)); echo tail')
        assert r.stdout == ""
        assert "ivision by zero" in r.stderr
        assert r.returncode == 1

    def test_c_multi_line_resumes(self):
        r = psh_c('echo x$((1/0)); echo tail\necho next rc=$?')
        assert r.stdout == "next rc=1\n"
        assert r.returncode == 0

    def test_script_file_resumes(self, tmp_path):
        r = psh_file(tmp_path, 'echo x$((5%0)); echo tail\necho next rc=$?\n')
        assert r.stdout == "next rc=1\n"
        assert r.returncode == 0

    def test_piped_stdin_resumes(self):
        r = psh_stdin('echo x$((1+)); echo tail\necho next rc=$?\n')
        assert r.stdout == "next rc=1\n"
        assert r.returncode == 0

    def test_kills_and_or_tails_and_if_bodies(self, tmp_path):
        r = psh_file(tmp_path,
                     'echo x$((1/0)) || echo fallback\n'
                     'if echo y$((1/0)); then echo yes; else echo no; fi; echo t\n'
                     'echo next\n')
        assert r.stdout == "next\n"
        assert r.returncode == 0

    def test_kills_function_body_and_caller_line(self, tmp_path):
        r = psh_file(tmp_path,
                     'f() { echo x$((1/0)); echo infn; }\n'
                     'f; echo after\n'
                     'echo next rc=$?\n')
        assert r.stdout == "next rc=1\n"

    def test_contained_at_subshell_boundary(self, tmp_path):
        # The child discards ITS rest-of-list; the parent line continues.
        r = psh_file(tmp_path,
                     '( echo x$((1/0)); echo insub ); echo after rc=$?\n')
        assert r.stdout == "after rc=1\n"

    def test_contained_at_cmdsub_boundary(self, tmp_path):
        r = psh_file(tmp_path,
                     'v=$(echo a$((1/0)); echo insub); echo v=[$v] rc=$?\n')
        assert r.stdout == "v=[] rc=1\n"

    def test_contained_at_eval_boundary(self, tmp_path):
        # bash 5.2: eval CONTAINS the discard — the rest of the eval'd
        # string dies, eval returns 1, the SAME outer line continues.
        r = psh_file(tmp_path,
                     "eval 'echo x$((1/0)); echo ineval'; echo after=$?\n"
                     'echo next\n')
        assert r.stdout == "after=1\nnext\n"

    def test_contained_per_line_inside_source(self, tmp_path):
        inner = tmp_path / "inner.sh"
        inner.write_text('echo x$((1/0)); echo srcsame\necho srcnext\n')
        r = psh_file(tmp_path, f'. {inner}; echo after=$?\necho next\n')
        assert r.stdout == "srcnext\nafter=0\nnext\n"

    def test_contained_in_trap_action(self, tmp_path):
        r = psh_file(tmp_path,
                     "trap 'echo t$((1/0)); echo intrap' USR1\n"
                     'kill -USR1 $$\n'
                     'echo after=$?\n')
        assert r.stdout == "after=0\n"

    def test_contained_at_pipeline_member_boundary(self, tmp_path):
        r = psh_file(tmp_path, 'echo x$((1/0)) | cat; echo after=$?\n')
        assert r.stdout == "after=0\n"

    def test_errexit_immune(self, tmp_path):
        # Unlike failglob/readonly, an arith-expansion discard does not
        # trip set -e — bash resumes the next line (probe-verified).
        r = psh_file(tmp_path, 'set -e\necho x$((1/0)); echo tail\necho next\n')
        assert r.stdout == "next\n"
        assert r.returncode == 0

    def test_bad_name_substitution_is_discard(self, tmp_path):
        # ${} / ${1abc}: bash resumes at the next line in every mode
        # (only the unknown-@X-on-set form is fatal — see family 3).
        r = psh_file(tmp_path, 'echo ${}; echo tail\necho next rc=$?\n')
        assert r.stdout == "next rc=1\n"
        assert "bad substitution" in r.stderr
        assert r.returncode == 0

    def test_case_subject_discards(self, tmp_path):
        r = psh_file(tmp_path,
                     'case $((1/0)) in *) echo m;; esac; echo t\necho next\n')
        assert r.stdout == "next\n"

    def test_redirect_target_discards(self, tmp_path):
        r = psh_file(tmp_path, 'echo hi > f$((1/0)); echo t\necho next\n')
        assert r.stdout == "next\n"


class TestFailglobDiscard:
    """failglob is discard-line family, plus a set -e special case."""

    def test_discards_line_and_resumes(self, tmp_path):
        r = psh_file(tmp_path,
                     'shopt -s failglob\n'
                     'echo /nonexistent_zzz_dir/*; echo tail\n'
                     'echo next rc=$?\n')
        assert r.stdout == "next rc=1\n"
        assert "no match" in r.stderr

    def test_for_words_discard(self, tmp_path):
        r = psh_file(tmp_path,
                     'shopt -s failglob\n'
                     'for i in /nonexistent_zzz_dir/*; do echo i=$i; done; echo t\n'
                     'echo next\n')
        assert r.stdout == "next\n"

    def test_array_init_discard(self, tmp_path):
        r = psh_file(tmp_path,
                     'shopt -s failglob\n'
                     'a=(/nonexistent_zzz_dir/*); echo n=${#a[@]}\n'
                     'echo next\n')
        assert r.stdout == "next\n"

    def test_errexit_exits_shell(self, tmp_path):
        # bash: failglob + set -e exits the shell — even from an
        # errexit-suppressed context like an if condition.
        r = psh_file(tmp_path,
                     'set -e\nshopt -s failglob\n'
                     'if echo /nonexistent_zzz_dir/*; then echo y; fi; echo t\n'
                     'echo next\n')
        assert r.stdout == ""
        assert r.returncode == 1


class TestAssignmentSubscriptFamily:
    """Family 2: discard-line, except -c abandons the rest of the string."""

    def test_declare_i_kills_rest_of_c_string(self):
        r = psh_c("declare -i v='1/0'; echo tail\necho next")
        assert r.stdout == ""
        assert r.returncode == 1

    def test_declare_i_resumes_in_script(self, tmp_path):
        r = psh_file(tmp_path, "declare -i v='1/0'; echo tail\necho next rc=$?\n")
        assert r.stdout == "next rc=1\n"
        assert r.returncode == 0

    def test_local_i_resumes_in_script(self, tmp_path):
        r = psh_file(tmp_path,
                     "f() { local -i w='1/0'; echo infn; }; f; echo t\n"
                     'echo next\n')
        assert r.stdout == "next\n"
        assert "local" in r.stderr

    def test_plain_i_assignment_family(self, tmp_path):
        r = psh_file(tmp_path, "declare -i v\nv='1/0'; echo tail\necho next\n")
        assert r.stdout == "next\n"

    def test_subscript_read_kills_rest_of_c_string(self):
        r = psh_c('a=(1 2); echo before; echo x${a[1/0]}; echo t\necho next')
        assert r.stdout == "before\n"
        assert r.returncode == 1

    def test_subscript_read_resumes_in_stdin(self):
        r = psh_stdin('a=(1 2); echo x${a[1/0]}; echo t\necho next rc=$?\n')
        assert r.stdout == "next rc=1\n"

    def test_subscript_write_discards(self, tmp_path):
        r = psh_file(tmp_path, 'a=(1 2); a[1/0]=5; echo t\necho next\n')
        assert r.stdout == "next\n"

    def test_unset_bad_subscript_same_family(self, tmp_path):
        r = psh_file(tmp_path, 'a=(1 2); unset "a[08]"; echo t\necho next\n')
        assert r.stdout == "next\n"

    def test_passes_through_eval_under_c(self):
        # Under -c the abandonment is NOT contained by eval (bash).
        r = psh_c("eval 'declare -i v=\"1/0\"; echo ineval'; echo after\necho next")
        assert r.stdout == ""
        assert r.returncode == 1

    def test_contained_at_cmdsub_under_c(self):
        r = psh_c('v=$(declare -i w="1/0"; echo insub); echo after=[$v] rc=$?\necho next')
        assert r.stdout == "after=[] rc=1\nnext\n"
        assert r.returncode == 0


class TestShellExitFamily:
    """Family 3: ${x:?}, @X-on-set, set -u exit a non-interactive shell."""

    @pytest.mark.parametrize("snippet,needle", [
        ('echo x${nope:?msg}; echo tail', 'nope: msg'),
        ('set -u; echo x$nope; echo tail', 'unbound variable'),
        ('x=1; echo a${x@Z}; echo tail', 'bad substitution'),
    ])
    def test_c_mode_exits_127(self, snippet, needle):
        r = psh_c(snippet + '\necho next')
        assert r.stdout == ""
        assert needle in r.stderr
        assert r.returncode == 127

    @pytest.mark.parametrize("script", [
        'echo x${nope:?msg}; echo tail\necho next\n',
        'set -u\necho x$nope; echo tail\necho next\n',
        'x=1\necho a${x@Z}; echo tail\necho next\n',
    ])
    def test_script_file_exits_1(self, tmp_path, script):
        r = psh_file(tmp_path, script)
        assert r.stdout == ""
        assert r.returncode == 1

    def test_piped_stdin_exits_1(self):
        r = psh_stdin('echo x${nope:?msg}; echo tail\necho next\n')
        assert r.stdout == ""
        assert r.returncode == 1

    def test_nounset_in_arithmetic_exits(self, tmp_path):
        r = psh_file(tmp_path, 'set -u\necho x$((nope+1))\necho next\n')
        assert r.stdout == ""
        assert r.returncode == 1

    def test_eval_does_not_contain_it(self, tmp_path):
        r = psh_file(tmp_path,
                     "eval 'echo x${nope:?msg}; echo ineval'; echo after\n"
                     'echo next\n')
        assert r.stdout == ""
        assert r.returncode == 1

    def test_contained_at_cmdsub_boundary(self, tmp_path):
        # The cmdsub child exits; the parent continues (bash).
        r = psh_file(tmp_path,
                     'v=$(echo x${nope:?msg}; echo insub); echo v=[$v] rc=$?\n'
                     'echo next\n')
        assert r.stdout == "v=[] rc=1\nnext\n"
        assert r.returncode == 0

    def test_interactive_discards_line_status_1(self):
        # bash -i: $? is 1 (not 127) and the shell survives to the next
        # line — the interactive form of the model.
        r = psh_stdin('echo x${nope:?msg}; echo tail\necho rc=$?\n',
                      flags=['-i', '--norc'])
        assert "rc=1" in r.stdout
        assert "tail" not in r.stdout

    def test_unknown_transform_on_unset_is_silently_empty(self, tmp_path):
        # bash quirk: ${unset@Z} is NOT an error — only a SET variable
        # makes the unknown transform a fatal bad substitution.
        r = psh_file(tmp_path, 'echo a${x@Z}; echo tail\n')
        assert r.stdout == "a\ntail\n"
        assert r.stderr == ""
        assert r.returncode == 0


class TestEmbeddedShellDiscard:
    """The in-process API: run_command returns the discard status and the
    shell object survives (the interactive/embedded form of the model)."""

    def test_discard_returns_1_and_survives(self, captured_shell):
        rc = captured_shell.run_command('echo x$((1/0)); echo tail')
        assert rc == 1
        assert captured_shell.get_stdout() == ""
        captured_shell.clear_output()
        assert captured_shell.run_command('echo alive') == 0
        assert captured_shell.get_stdout() == "alive\n"

    def test_fatal_family_returns_1_and_survives(self, captured_shell):
        rc = captured_shell.run_command('echo x${nope:?msg}; echo tail')
        assert rc == 1
        assert "nope: msg" in captured_shell.get_stderr()
        captured_shell.clear_output()
        assert captured_shell.run_command('echo alive') == 0
