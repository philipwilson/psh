"""Pattern-substitution fixes from reappraisal #16 (same H6 cluster).

1. nocasematch in patsub — ``shopt -s nocasematch`` is honored by ``case`` and
   ``[[`` but was never threaded into ``${v/pat/r}`` (and its ``/#`` / ``/%``
   forms). bash applies it to substitution but NOT to prefix/suffix *removal*
   (``#``/``%``) or case modification, so the fix is scoped to substitute_*.

2. front-anchored patsub with extglob — ``${v/#pat/r}`` routed the extglob
   pattern through a regex that was ALSO end-anchored, so ``/#`` behaved like a
   whole-value match and never replaced a real prefix. bash 5.2 probes:
   ``v=aaXaa; ${v/#+(a)/Z}`` -> ``ZXaa``; ``v=aabb; ${v/#@(aa)/Z}`` -> ``Zbb``.
"""


class TestNocasematchPatsub:
    def test_replace_all_ignorecase(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=ABC; echo "${v//a/X}"')
        assert captured_shell.get_stdout() == "XBC\n"

    def test_replace_first_ignorecase(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=ABC; echo "${v/a/X}"')
        assert captured_shell.get_stdout() == "XBC\n"

    def test_replace_prefix_ignorecase(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=ABC; echo "${v/#a/X}"')
        assert captured_shell.get_stdout() == "XBC\n"

    def test_replace_suffix_ignorecase(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=ABC; echo "${v/%c/X}"')
        assert captured_shell.get_stdout() == "ABX\n"

    def test_removal_is_not_ignorecase(self, captured_shell):
        # bash does NOT apply nocasematch to # / % removal.
        captured_shell.run_command(
            'shopt -s nocasematch; v=ABC; echo "${v#a}::${v%c}"')
        assert captured_shell.get_stdout() == "ABC::ABC\n"

    def test_off_by_default(self, captured_shell):
        captured_shell.run_command('v=ABC; echo "${v//a/X}"')
        assert captured_shell.get_stdout() == "ABC\n"

    def test_extglob_nonneg_ignorecase(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch extglob; v=aXa; echo "${v//@(A)/-}"')
        assert captured_shell.get_stdout() == "-X-\n"

    def test_extglob_negation_ignorecase(self, captured_shell):
        # !(a) with nocase treats 'A' as 'a' -> the single 'A' is NOT matched,
        # so only the empty span at pos 0 replaces (bash: "-A").
        captured_shell.run_command(
            'shopt -s nocasematch extglob; v=A; echo "${v//!(a)/-}"')
        assert captured_shell.get_stdout() == "-A\n"


class TestFrontAnchoredExtglobPatsub:
    def setup_shell(self, captured_shell):
        captured_shell.run_command('shopt -s extglob')

    def test_plus_paren_prefix(self, captured_shell):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command('v=aaXaa; echo "${v/#+(a)/Z}"')
        assert captured_shell.get_stdout() == "ZXaa\n"

    def test_at_paren_prefix(self, captured_shell):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command('v=aabb; echo "${v/#@(aa)/Z}"')
        assert captured_shell.get_stdout() == "Zbb\n"

    def test_star_paren_prefix(self, captured_shell):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command('v=aaXaa; echo "${v/#*(a)/Z}"')
        assert captured_shell.get_stdout() == "ZXaa\n"

    def test_question_paren_prefix(self, captured_shell):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command('v=aaXaa; echo "${v/#?(a)/Z}"')
        assert captured_shell.get_stdout() == "ZaXaa\n"

    def test_plain_prefix_still_works(self, captured_shell):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command('v=aaXaa; echo "${v/#aa/Z}"')
        assert captured_shell.get_stdout() == "ZXaa\n"

    def test_suffix_extglob_unaffected(self, captured_shell):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command('v=aaXaa; echo "${v/%+(a)/Z}"')
        assert captured_shell.get_stdout() == "aaXZ\n"
