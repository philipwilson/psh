"""IFS is seeded as a REAL shell variable at init (reappraisal #16, H3).

Before the fix, psh never seeded IFS: it only used ``' \\t\\n'`` as an
internal word-splitting fallback, so ``$IFS`` expanded empty, ``declare -p
IFS`` said "not found", ``${IFS+set}`` was empty, and the ubiquitous
``OLD=$IFS; IFS=,; ...; IFS=$OLD`` save/restore idiom silently restored IFS
to EMPTY (= no splitting). Seeding IFS to the default <space><tab><newline>
fixes all of that while keeping the UNSET fallback (``unset IFS`` still
splits on whitespace). All behaviors verified against bash 5.2.
"""

import subprocess
import sys

from psh.core.variables import VarAttributes

DEFAULT_IFS = " \t\n"


class TestIFSSeededVariable:
    def test_ifs_is_a_real_variable_with_default_value(self, captured_shell):
        assert captured_shell.state.get_variable("IFS") == DEFAULT_IFS

    def test_ifs_object_exists_and_is_not_exported(self, captured_shell):
        var = captured_shell.state.scope_manager.get_variable_object("IFS")
        assert var is not None
        # bash: a freshly-seeded IFS is a plain shell variable (declare --),
        # not exported (env has no IFS).
        assert not (var.attributes & VarAttributes.EXPORT)

    def test_ifs_plus_set_test_reports_set(self, captured_shell):
        captured_shell.run_command('echo "${IFS+set}"')
        assert captured_shell.get_stdout() == "set\n"

    def test_ifs_length_is_three(self, captured_shell):
        captured_shell.run_command("echo ${#IFS}")
        assert captured_shell.get_stdout() == "3\n"

    def test_declare_p_prints_ifs(self, captured_shell):
        rc = captured_shell.run_command("declare -p IFS")
        assert rc == 0
        # Value bytes are rendered by declare's (pre-existing) quoting; only
        # assert the stable prefix — the ANSI-C vs double-quote rendering of
        # control chars is a separate, general declare -p concern, not H3.
        assert captured_shell.get_stdout().startswith("declare -- IFS=")
        assert captured_shell.get_stderr() == ""


class TestIFSRoundTrip:
    def test_save_restore_idiom_restores_default_splitting(self, captured_shell):
        captured_shell.run_command(
            'OLD=$IFS; IFS=,; v="a,b,c"; set -- $v; echo $2; '
            'IFS=$OLD; x="p q r"; set -- $x; echo $#'
        )
        # $2 under IFS=, is "b"; after restore the whitespace split yields 3.
        assert captured_shell.get_stdout() == "b\n3\n"

    def test_unset_ifs_falls_back_to_whitespace_split(self, captured_shell):
        captured_shell.run_command('unset IFS; x="p q r"; set -- $x; echo $#')
        assert captured_shell.get_stdout() == "3\n"

    def test_empty_ifs_suppresses_splitting(self, captured_shell):
        captured_shell.run_command('IFS=; x="p q r"; set -- $x; echo $#')
        assert captured_shell.get_stdout() == "1\n"


class TestIFSFromEnvironment:
    """bash resets IFS's VALUE to the default at startup even when inherited
    exported, but keeps the export attribute (declare -x). Run in a subprocess
    so we control the child's environment."""

    def test_exported_ifs_value_reset_but_export_kept(self):
        # (declare -p's value bytes may span lines because IFS contains a
        # literal newline — a separate declare quoting matter — so assert on
        # the prefix and a marked length line, not on line indices.)
        result = subprocess.run(
            [sys.executable, "-m", "psh", "-c", 'declare -p IFS; echo "LEN=${#IFS}"'],
            env={"IFS": "XYZ", "PATH": "/usr/bin:/bin", "PSH_STRICT_ERRORS": "1"},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Export attribute preserved from the environment...
        assert result.stdout.startswith("declare -x IFS=")
        # ...but the value was reset to the 3-char default, not "XYZ".
        assert "LEN=3" in result.stdout
