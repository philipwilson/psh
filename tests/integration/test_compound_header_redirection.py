"""Compound-command redirections cover HEADER expansion (executor F4).

Redirections on a compound command apply to the whole construct, including
the header that is expanded/evaluated before the body:

- `for`/`select` item-list expansion
- `case` subject expansion
- C-style `for` initializer

psh previously expanded these headers BEFORE installing the compound
redirection, so a command substitution in the header read the OUTER stdin
instead of the redirected one. `if`/`while`/`until` were already correct.

These use an input file redirected into the construct, so they run psh in a
subprocess in an isolated temp dir (the conftest PYTHONPATH points the
subprocess at this worktree).
"""

import subprocess
import sys


def _run(script: str, cwd):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15, cwd=str(cwd),
    )
    return result.stdout, result.stderr, result.returncode


def test_for_item_list_reads_redirected_stdin(tmp_path):
    (tmp_path / "input").write_text("item\n")
    out, _, rc = _run(
        'for x in $(cat); do printf "<%s>\\n" "$x"; done < input', tmp_path)
    assert out == "<item>\n"
    assert rc == 0


def test_for_item_list_multiple_words(tmp_path):
    (tmp_path / "input").write_text("a b\n")
    out, _, _ = _run(
        'for x in $(cat); do printf "<%s>\\n" "$x"; done < input', tmp_path)
    assert out == "<a>\n<b>\n"


def test_case_subject_reads_redirected_stdin(tmp_path):
    (tmp_path / "input").write_text("item\n")
    out, _, _ = _run(
        'case "$(cat)" in item) echo yes ;; *) echo no ;; esac < input',
        tmp_path)
    assert out == "yes\n"


def test_cstyle_for_init_reads_redirected_stdin(tmp_path):
    (tmp_path / "num").write_text("2\n")
    out, _, _ = _run(
        'for ((i=$(cat); i<4; i++)); do echo "$i"; done < num', tmp_path)
    assert out == "2\n3\n"


def test_while_header_still_correct(tmp_path):
    # Regression guard: if/while/until were already correct.
    (tmp_path / "two").write_text("a\nb\n")
    out, _, _ = _run(
        'while read x; do echo "got=$x"; done < two', tmp_path)
    assert out == "got=a\ngot=b\n"


def test_failed_redirect_skips_header_expansion(tmp_path):
    # If the compound redirect fails, the header substitution must NOT run
    # (bash installs redirects first). SHOULD_NOT must not appear.
    out, err, _ = _run(
        'for x in $(echo SHOULD_NOT >&2; echo a); do echo "$x"; done '
        '< /no/such/file; echo "rc=$?"', tmp_path)
    assert "SHOULD_NOT" not in out
    assert "SHOULD_NOT" not in err
    assert out == "rc=1\n"


def test_case_debug_trap_order(tmp_path):
    # DEBUG trap fires after the redirect is installed and covers the subject
    # eval (bash: D before the case command, D before echo -> two D's).
    (tmp_path / "input").write_text("item\n")
    out, err, _ = _run(
        'trap "echo D>&2" DEBUG; case "$(cat)" in item) echo yes ;; esac '
        '< input', tmp_path)
    assert out == "yes\n"
    assert err.count("D") == 2
