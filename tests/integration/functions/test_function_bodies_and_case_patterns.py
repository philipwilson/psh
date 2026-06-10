"""Parser correctness sweep (v0.269.0) — bash-pinned.

Function subshell bodies, definition-attached redirects, quoted case
patterns (Word AST), and select's EOF exit status.
"""

import subprocess
import sys


def run_psh(script):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=15)


class TestSubshellFunctionBodies:
    """f() ( ... ) runs the body in a subshell at each call (bash)."""

    def test_variable_isolation(self):
        r = run_psh('f() ( x=2; echo "in:$x" ); x=1; f; echo "out:$x"')
        assert r.stdout == "in:2\nout:1\n"

    def test_cd_isolation(self, tmp_path):
        r = run_psh('f() ( cd /; pwd ); f; pwd')
        lines = r.stdout.splitlines()
        assert lines[0] == "/"
        assert lines[1] != "/"

    def test_exit_only_leaves_subshell(self):
        r = run_psh('f() ( exit 3 ); f; echo "rc=$?"')
        assert r.stdout == "rc=3\n"
        assert r.returncode == 0

    def test_simple_subshell_body(self, captured_shell):
        # In-process: a non-forking sanity check of definition + call
        rc = captured_shell.run_command('f() ( echo sub ); f')
        assert rc == 0


class TestFunctionDefinitionRedirects:
    """f() { ...; } > file applies the redirect at each CALL (bash)."""

    def test_not_applied_at_definition(self, tmp_path):
        out = tmp_path / "def.txt"
        r = run_psh(f'f() {{ echo hello; }} > {out}; '
                    f'ls {out} 2>/dev/null; echo "after-def:$?"')
        assert "after-def:1" in r.stdout
        assert not out.exists()

    def test_applied_per_call_truncating(self, tmp_path):
        out = tmp_path / "calls.txt"
        r = run_psh(f'f() {{ echo hello; }} > {out}; f; f; wc -l < {out}')
        assert r.stdout.strip() == "1"
        assert out.read_text() == "hello\n"

    def test_appending_redirect_accumulates(self, tmp_path):
        out = tmp_path / "appends.txt"
        run_psh(f'f() {{ echo line; }} >> {out}; f; f; f')
        assert out.read_text() == "line\nline\nline\n"

    def test_call_site_redirect_still_works(self, tmp_path):
        out = tmp_path / "site.txt"
        r = run_psh(f'f() {{ echo run; }}; f > {out}')
        assert r.returncode == 0
        assert out.read_text() == "run\n"

    def test_stderr_dup_on_definition(self):
        r = run_psh('f() { echo to_out; } 2>&1; f >/dev/null; echo done')
        assert r.stdout == "done\n"


class TestQuotedCasePatterns:
    """Quoted case-pattern text matches literally (Word AST quote context)."""

    def test_quoted_glob_is_literal_no_match(self, captured_shell):
        captured_shell.run_command("case ab in 'a*') echo lit;; *) echo other;; esac")
        assert captured_shell.get_stdout() == "other\n"

    def test_quoted_glob_matches_literal_star(self, captured_shell):
        captured_shell.run_command("case 'a*' in 'a*') echo lit;; *) echo glob;; esac")
        assert captured_shell.get_stdout() == "lit\n"

    def test_backslash_escaped_glob(self, captured_shell):
        captured_shell.run_command(r"case ab in a\*) echo lit;; *) echo other;; esac")
        assert captured_shell.get_stdout() == "other\n"

    def test_unquoted_glob_still_active(self, captured_shell):
        captured_shell.run_command("case ab in a*) echo glob;; esac")
        assert captured_shell.get_stdout() == "glob\n"

    def test_quoted_variable_is_literal(self, captured_shell):
        captured_shell.run_command(
            'p="a*"; case abc in "$p") echo lit;; *) echo noglob;; esac')
        assert captured_shell.get_stdout() == "noglob\n"

    def test_unquoted_variable_is_glob_active(self, captured_shell):
        captured_shell.run_command('p="a*"; case abc in $p) echo varglob;; esac')
        assert captured_shell.get_stdout() == "varglob\n"

    def test_quoted_variable_matches_literal_text(self, captured_shell):
        captured_shell.run_command(
            'v="x y"; case "x y" in "$v") echo vq;; esac')
        assert captured_shell.get_stdout() == "vq\n"

    def test_mixed_quoted_unquoted_parts(self, captured_shell):
        captured_shell.run_command('case hello in h"ell"o) echo mixed;; esac')
        assert captured_shell.get_stdout() == "mixed\n"

    def test_quoted_star_part_in_composite(self, captured_shell):
        captured_shell.run_command(
            "case 'h*llo' in h\"*\"llo) echo qstar;; *) echo no;; esac")
        assert captured_shell.get_stdout() == "qstar\n"

    def test_command_sub_in_pattern(self, captured_shell):
        captured_shell.run_command('case abc in $(echo abc)) echo cmdsub;; esac')
        assert captured_shell.get_stdout() == "cmdsub\n"

    def test_alternation_with_quotes(self, captured_shell):
        captured_shell.run_command('case x in \'a\'|"x") echo qalt;; esac')
        assert captured_shell.get_stdout() == "qalt\n"

    def test_bracket_class_still_works(self, captured_shell):
        captured_shell.run_command('case 5 in [0-9]) echo digit;; esac')
        assert captured_shell.get_stdout() == "digit\n"

    def test_keyword_pattern(self, captured_shell):
        captured_shell.run_command('case if in if) echo kw;; esac')
        assert captured_shell.get_stdout() == "kw\n"

    def test_quoted_question_mark(self, captured_shell):
        captured_shell.run_command(
            'case "?bc" in "?"bc) echo qq;; *) echo no;; esac')
        assert captured_shell.get_stdout() == "qq\n"
        captured_shell.clear_output()
        captured_shell.run_command(
            'case abc in "?"bc) echo qq;; *) echo no;; esac')
        assert captured_shell.get_stdout() == "no\n"


class TestSelectEofStatus:
    def test_select_eof_returns_one(self):
        r = run_psh('select x in a b; do break; done < /dev/null')
        assert r.returncode == 1

    def test_select_pick_returns_zero(self):
        r = run_psh('echo 1 | { select x in a b; do echo "picked:$x"; break; done; }; echo "rc=$?"')
        assert "picked:a" in r.stdout
        assert "rc=0" in r.stdout
