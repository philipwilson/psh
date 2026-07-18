"""The WordExpansionPolicy table: every expansion context has a NAME.

Pins the three axes of each named policy in
``psh/expansion/word_expander.py`` and exercises the field engine
(``WordExpander.expand_to_word`` + ``materialize``) directly under each policy.
Also pins the DEATH of the old aliasing trap: ``expand_word_to_fields`` no
longer accepts ``suppress_split_glob`` (which silently aliased onto
``declaration_assignment`` and re-enabled assignment-tilde for assoc
initializer elements).
"""

import dataclasses

import pytest

from psh.ast_nodes import ExpansionPart, LiteralPart, VariableExpansion, Word
from psh.expansion.word_expansion_types import (
    ARRAY_INIT_ELEMENT,
    ASSOC_INIT_ELEMENT,
    COMMAND_ARGUMENT,
    DECLARATION_ASSIGNMENT,
    LOOP_ITEM,
    WordExpansionPolicy,
)


def _unquoted_var(name: str) -> Word:
    return Word(parts=[ExpansionPart(VariableExpansion(name))])


def _literal(text: str) -> Word:
    return Word(parts=[LiteralPart(text)])


def _shape(expander, word, policy):
    """Materialize *word* under *policy* to its observable argv shape.

    The engine returns an ``ExpandedWord`` that ``materialize`` flattens to
    ``List[str]`` fields; this collapses that to the shape these axis pins read
    — one field is the scalar string, zero or many is a list. The Word-type
    guard fires inside ``expand_to_word``, so a non-Word still raises here.
    """
    fields = expander.materialize(expander.expand_to_word(word, policy), policy)
    return fields[0] if len(fields) == 1 else fields


class TestPolicyTable:
    """The named policies' axes, pinned (verified against bash/psh probes
    on 2026-06-12 — see the instance docstrings in word_expander.py)."""

    def test_command_argument_axes(self):
        assert COMMAND_ARGUMENT == WordExpansionPolicy(
            split=True, glob=True, assignment_tilde=True)

    def test_loop_item_is_command_argument(self):
        # bash treats for/select items exactly like command arguments;
        # the alias is identity, not just equality.
        assert LOOP_ITEM is COMMAND_ARGUMENT

    def test_declaration_assignment_axes(self):
        assert DECLARATION_ASSIGNMENT == WordExpansionPolicy(
            split=False, glob=False, assignment_tilde=True)

    def test_array_init_element_axes(self):
        assert ARRAY_INIT_ELEMENT == WordExpansionPolicy(
            split=True, glob=True, assignment_tilde=False)

    def test_assoc_init_element_axes(self):
        # assignment_tilde=False is the bash-correct value (probed
        # 2026-06-13): bash keeps ``h=(P=~/x v)``'s tilde literal, like
        # indexed-array initializer elements. (Until v0.326 this was
        # True — a pinned historical accident from pre-policy code that
        # aliased suppress_split_glob onto declaration_assignment.)
        assert ASSOC_INIT_ELEMENT == WordExpansionPolicy(
            split=False, glob=False, assignment_tilde=False)

    def test_policies_are_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            COMMAND_ARGUMENT.split = False  # type: ignore[misc]

    def test_suppress_split_glob_parameter_is_dead(self, captured_shell):
        """The aliasing trap no longer exists as a parameter."""
        word = _literal('x')
        with pytest.raises(TypeError):
            captured_shell.expansion_manager.expand_word_to_fields(
                word, suppress_split_glob=True)


class TestExpandUnderPolicies:
    """Direct field-engine calls (expand_to_word + materialize via _shape),
    two-three per policy."""

    @pytest.fixture
    def expander(self, captured_shell):
        return captured_shell.expansion_manager.word_expander

    # --- split axis -----------------------------------------------------

    def test_command_argument_splits(self, captured_shell, expander):
        captured_shell.run_command("x='1 2'")
        assert _shape(expander, _unquoted_var('x'), COMMAND_ARGUMENT) \
            == ['1', '2']

    def test_command_argument_zero_field_rule(self, captured_shell, expander):
        captured_shell.run_command('unset novar')
        assert _shape(expander, _unquoted_var('novar'), COMMAND_ARGUMENT) == []

    def test_declaration_assignment_keeps_value_whole(
            self, captured_shell, expander):
        captured_shell.run_command("x='1 2'")
        assert _shape(expander, _unquoted_var('x'), DECLARATION_ASSIGNMENT) \
            == '1 2'

    def test_assoc_init_element_keeps_value_whole(
            self, captured_shell, expander):
        captured_shell.run_command("x='k v'")
        assert _shape(expander, _unquoted_var('x'), ASSOC_INIT_ELEMENT) \
            == 'k v'

    def test_array_init_element_splits(self, captured_shell, expander):
        captured_shell.run_command("x='p q'")
        assert _shape(expander, _unquoted_var('x'), ARRAY_INIT_ELEMENT) \
            == ['p', 'q']

    # --- glob axis (made observable via nullglob: a matchless pattern
    #     vanishes when globbed, survives literally when not) -----------

    def test_command_argument_globs(self, captured_shell, expander):
        captured_shell.run_command('shopt -s nullglob')
        assert _shape(expander,
            _literal('zz-no-such-file-*'), COMMAND_ARGUMENT) == []

    def test_declaration_assignment_does_not_glob(
            self, captured_shell, expander):
        captured_shell.run_command('shopt -s nullglob')
        assert _shape(expander,
            _literal('zz-no-such-file-*'), DECLARATION_ASSIGNMENT) \
            == 'zz-no-such-file-*'

    def test_assoc_init_element_does_not_glob(self, captured_shell, expander):
        captured_shell.run_command('shopt -s nullglob')
        assert _shape(expander,
            _literal('zz-no-such-file-*'), ASSOC_INIT_ELEMENT) \
            == 'zz-no-such-file-*'

    # --- assignment_tilde axis ------------------------------------------

    def test_command_argument_value_tilde(self, captured_shell, expander):
        captured_shell.run_command('HOME=/H')
        assert _shape(expander, _literal('P=~/x'), COMMAND_ARGUMENT) == 'P=/H/x'

    def test_declaration_assignment_value_tilde(
            self, captured_shell, expander):
        captured_shell.run_command('HOME=/H')
        assert _shape(expander, _literal('P=~/x'), DECLARATION_ASSIGNMENT) \
            == 'P=/H/x'

    def test_array_init_element_no_value_tilde(self, captured_shell, expander):
        captured_shell.run_command('HOME=/H')
        assert _shape(expander, _literal('P=~/x'), ARRAY_INIT_ELEMENT) \
            == 'P=~/x'

    def test_assoc_init_element_no_value_tilde(
            self, captured_shell, expander):
        # bash 5.2 keeps the tilde literal (the historical accident that
        # expanded it was fixed 2026-06-13; see TestPolicyTable).
        captured_shell.run_command('HOME=/H')
        assert _shape(expander, _literal('P=~/x'), ASSOC_INIT_ELEMENT) \
            == 'P=~/x'

    def test_assoc_init_element_leading_tilde_still_expands(
            self, captured_shell, expander):
        # bash: a BARE leading tilde in an assoc initializer element does
        # expand (h=(~ v) keys on $HOME) — only the assignment-shaped
        # value-tilde is off.
        captured_shell.run_command('HOME=/H')
        assert _shape(expander, _literal('~/x'), ASSOC_INIT_ELEMENT) == '/H/x'

    # --- field expansions under no-split policies (bash joins) ----------

    def test_assoc_init_unquoted_at_joins_with_spaces(
            self, captured_shell, expander):
        # bash: `h=($@)` with params ("a b", c) creates the SINGLE key
        # "a b c" — fields join with spaces, no IFS splitting, no
        # globbing. (Until v0.326 this path ignored the policy and
        # split/globbed — the pinned probe-P22 accident, now fixed.)
        captured_shell.run_command('set -- "a b" c')
        word = Word(parts=[ExpansionPart(VariableExpansion('@'),
                                         quoted=False)])
        assert _shape(expander, word, ASSOC_INIT_ELEMENT) == 'a b c'

    def test_assoc_init_quoted_at_joins_with_spaces(
            self, captured_shell, expander):
        # bash: quoted "$@" joins identically in assoc-init context.
        captured_shell.run_command('set -- "a b" c')
        word = Word(parts=[ExpansionPart(VariableExpansion('@'),
                                         quoted=True, quote_char='"')])
        assert _shape(expander, word, ASSOC_INIT_ELEMENT) == 'a b c'

    def test_assoc_init_at_join_ignores_ifs(self, captured_shell, expander):
        # bash joins with SPACES even when IFS is ':' (unlike "$*").
        captured_shell.run_command('set -- x y; IFS=:')
        word = Word(parts=[ExpansionPart(VariableExpansion('@'),
                                         quoted=False)])
        assert _shape(expander, word, ASSOC_INIT_ELEMENT) == 'x y'

    def test_command_argument_at_still_produces_fields(
            self, captured_shell, expander):
        # The splitting contexts are untouched: unquoted $@ still
        # field-splits per parameter.
        captured_shell.run_command('set -- "a b" c')
        word = Word(parts=[ExpansionPart(VariableExpansion('@'),
                                         quoted=False)])
        assert _shape(expander, word, COMMAND_ARGUMENT) == ['a', 'b', 'c']

    # --- engine type discipline ------------------------------------------

    def test_expand_rejects_non_word(self, expander):
        with pytest.raises(TypeError, match='expects a Word'):
            _shape(expander, 'not a word', COMMAND_ARGUMENT)
