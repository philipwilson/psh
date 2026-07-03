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


class TestNocasematchPosixClasses:
    """nocasematch in patsub must fold literals/ranges/sets but LEAVE the
    ``[:upper:]`` / ``[:lower:]`` classes case-sensitive.

    Regression guard (reappraisal #16 verifier): the first cut applied a
    blanket ``re.IGNORECASE`` which over-folded ``[:upper:]`` -> ``A-Z`` so
    ``${v//[[:upper:]]/x}`` on ``Hello`` wrongly returned ``xxxxx``. bash
    5.2.26 keeps the two case-classes case-sensitive (-> ``xello``) while
    still folding ranges and sets. Every expected value below is pinned to
    bash 5.2.26 in the C locale.
    """

    def test_upper_class_stays_case_sensitive(self, captured_shell):
        # THE regression: only the uppercase H matches, not the whole word.
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello; echo "${v//[[:upper:]]/x}"')
        assert captured_shell.get_stdout() == "xello\n"

    def test_lower_class_stays_case_sensitive(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello; echo "${v//[[:lower:]]/X}"')
        assert captured_shell.get_stdout() == "HXXXX\n"

    def test_lower_class_no_match_on_all_upper(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=HELLO; echo "${v//[[:lower:]]/x}"')
        assert captured_shell.get_stdout() == "HELLO\n"

    def test_explicit_range_still_folds(self, captured_shell):
        # bash DOES fold explicit ranges under nocasematch (unlike the classes).
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello; echo "${v//[A-Z]/x}"')
        assert captured_shell.get_stdout() == "xxxxx\n"

    def test_char_set_still_folds(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=aAbBcC; echo "${v//[abc]/_}"')
        assert captured_shell.get_stdout() == "______\n"

    def test_composite_bracket_class_plus_range(self, captured_shell):
        # [[:upper:]0-9]: uppercase stays upper-only, digits match.
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello9; echo "${v//[[:upper:]0-9]/_}"')
        assert captured_shell.get_stdout() == "_ello_\n"

    def test_negated_upper_class(self, captured_shell):
        # [^[:upper:]]: matches everything that is NOT uppercase.
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello; echo "${v//[^[:upper:]]/_}"')
        assert captured_shell.get_stdout() == "H____\n"

    def test_anchored_prefix_class_case_sensitive(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello; echo "${v/#[[:upper:]]/x}"')
        assert captured_shell.get_stdout() == "xello\n"

    def test_anchored_suffix_class_case_sensitive(self, captured_shell):
        # /% [[:lower:]] matches the trailing lowercase 'o'.
        captured_shell.run_command(
            'shopt -s nocasematch; v=Hello; echo "${v/%[[:lower:]]/X}"')
        assert captured_shell.get_stdout() == "HellX\n"


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


class TestExtglobAlternationLeftmostLongest:
    """Extglob alternation matches leftmost-LONGEST (POSIX), not leftmost-match.

    Reappraisal #16 follow-up (f): the unanchored substitution operators
    ``${v/pat/r}`` / ``${v//pat/r}`` / ``${v/#pat/r}`` routed non-negation
    extglob through a Python ``re``, whose alternation is leftmost-*match* — it
    commits to the first alternative that lets the regex succeed rather than the
    longest. So ``${v/#@(a|aa)/Z}`` on ``aaX`` gave ``ZaX`` (matched ``a``)
    instead of bash's ``ZX`` (matched ``aa``). These now route through the
    backtracking matcher, which enumerates every reachable end and takes the max.
    All expected values pinned to bash 5.2.
    """

    def setup_shell(self, captured_shell):
        captured_shell.run_command('shopt -s extglob')

    def _check(self, captured_shell, command, expected):
        self.setup_shell(captured_shell)
        captured_shell.clear_output()
        captured_shell.run_command(command)
        assert captured_shell.get_stdout() == expected

    def test_prefix_longest_alternative(self, captured_shell):
        self._check(captured_shell, 'v=aaX; echo "${v/#@(a|aa)/Z}"', "ZX\n")

    def test_prefix_order_independent(self, captured_shell):
        # Leftmost-longest is order-independent: @(aa|a) == @(a|aa).
        self._check(captured_shell, 'v=aaX; echo "${v/#@(aa|a)/Z}"', "ZX\n")

    def test_first_longest_alternative(self, captured_shell):
        self._check(captured_shell, 'v=aaX; echo "${v/@(a|aa)/Z}"', "ZX\n")

    def test_first_longest_at_interior_position(self, captured_shell):
        self._check(captured_shell, 'v=XaaY; echo "${v/@(a|aa)/Z}"', "XZY\n")

    def test_first_shorter_alt_when_longer_cannot_complete(self, captured_shell):
        # @(a|ab) on 'abb': 'ab' can't be followed by the rest as a longer
        # prefix, so the leftmost-longest match at pos 0 is 'ab'.
        self._check(captured_shell, 'v=abb; echo "${v/@(a|ab)/Z}"', "Zb\n")

    def test_first_backtrack_forced_by_trailing_literal(self, captured_shell):
        # @(a|ab)b on 'abb': re would commit to 'a'+'b' (stop at first success);
        # leftmost-longest extends the group to 'ab' so 'abb' matches whole.
        self._check(captured_shell, 'v=abb; echo "${v/#@(a|ab)b/Z}"', "Z\n")

    def test_all_longest_each_position(self, captured_shell):
        self._check(captured_shell, 'v=aaXaa; echo "${v//@(a|aa)/Z}"', "ZXZ\n")

    def test_all_longest_consumes_pairs(self, captured_shell):
        self._check(captured_shell, 'v=aaa; echo "${v//@(a|aa)/Z}"', "ZZ\n")

    def test_all_longest_mixed(self, captured_shell):
        self._check(captured_shell, 'v=aabb; echo "${v//@(a|aa)/-}"', "-bb\n")

    def test_optional_alternation_longest_first(self, captured_shell):
        # ?(a|aa) is empty-capable AND alternating: longest wins ('aa').
        self._check(captured_shell, 'v=aaX; echo "${v/?(a|aa)/Z}"', "ZX\n")

    def test_optional_alternation_longest_prefix(self, captured_shell):
        self._check(captured_shell, 'v=aaX; echo "${v/#?(a|aa)/Z}"', "ZX\n")

    def test_optional_alternation_longest_all(self, captured_shell):
        self._check(captured_shell, 'v=aaa; echo "${v//?(a|aa)/Z}"', "ZZ\n")

    def test_nested_alternation_first(self, captured_shell):
        self._check(captured_shell, 'v=bbX; echo "${v/@(a|@(b|bb))/Z}"', "ZX\n")

    def test_nested_alternation_prefix(self, captured_shell):
        self._check(captured_shell, 'v=bbX; echo "${v/#@(a|@(b|bb))/Z}"', "ZX\n")

    def test_empty_capable_closure_still_emits_empty_match(self, captured_shell):
        # Regression guard: *(a)/plain * on an EMPTY value still substitute the
        # empty match (bash), unlike the negation/optional forms — the matcher
        # scan must not over-suppress.
        self._check(captured_shell, 'v=; echo "${v/*(a)/-}"', "-\n")
        self._check(captured_shell, 'v=; echo "${v//*(a)/-}"', "-\n")
        self._check(captured_shell, 'v=; echo "${v/#*(a)/-}"', "-\n")

    def test_negation_empty_value_suppressed(self, captured_shell):
        # Negation !(x) on an empty value yields no substitution (bash).
        self._check(captured_shell, 'v=; echo "[${v/!(x)/-}]"', "[]\n")
        self._check(captured_shell, 'v=; echo "[${v//!(x)/-}]"', "[]\n")
