"""Drift-lock guards for the field IR (W1 boundary campaign).

Three guards protect the ``ExpandedWord`` boundary:

1. **Sole materialization chokepoint** (static): only ``WordExpander`` produces
   the field IR and only the three sanctioned ``manager.py`` sites turn it back
   into strings. A fourth ``.expand_to_word(``/``.materialize(`` caller — or an
   ``ExpandedWord(`` built outside the engine — fails the grep.
2. **No ``str | list[str]`` walker** (static): the field engine's public
   producer returns ``ExpandedWord``, never a str/list union.
3. **Per-run protection is honored** (behavioral, with a synthetic offender):
   a PROTECTED metacharacter run is bracket-escaped in the pathname pattern and
   an ACTIVE one is not — and a synthetic offender that ignores protection is
   demonstrably caught.

Each behavioral guard runs its synthetic offender inline (the offender IS the
regression), so the guard proves it bites without a code mutation.
"""
import pathlib
import re

from psh.expansion.word_expander import _FieldBuilder
from psh.expansion.word_expansion_types import (
    ExpandedField,
    FieldRun,
    Protection,
    Split,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

_ACTIVE = Protection.ACTIVE
_PROTECTED = Protection.PROTECTED
_NEVER = Split.NEVER
_ELIGIBLE = Split.IFS_ELIGIBLE


def _psh_sources():
    for py in sorted(PSH.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        yield py, py.read_text()


# --------------------------------------------------------------------------
# 1. Sole materialization chokepoint (static)
# --------------------------------------------------------------------------

class TestSoleChokepoint:
    def test_expand_to_word_only_called_from_manager(self):
        """``expand_to_word`` is the field engine; only ExpansionManager drives
        it (its three public funnels) plus its own definition."""
        allowed = {"psh/expansion/word_expander.py", "psh/expansion/manager.py"}
        offenders = []
        for py, src in _psh_sources():
            rel = py.relative_to(ROOT).as_posix()
            if rel in allowed:
                continue
            if ".expand_to_word(" in src:
                offenders.append(rel)
        assert not offenders, (
            "expand_to_word() must be reached through ExpansionManager, not "
            f"called directly: {offenders}")

    def test_materialize_is_the_sole_ir_to_strings_boundary(self):
        """Only ``manager.py`` flattens an ExpandedWord back to strings; no
        other module may call ``.materialize(`` or index ``.fields``."""
        allowed = {"psh/expansion/word_expander.py", "psh/expansion/manager.py"}
        offenders = []
        for py, src in _psh_sources():
            rel = py.relative_to(ROOT).as_posix()
            if rel in allowed:
                continue
            if ".materialize(" in src or ".fields" in src and "ExpandedWord" in src:
                offenders.append(rel)
        assert not offenders, (
            "ExpandedWord -> strings must go through WordExpander.materialize, "
            f"the sole terminal boundary: {offenders}")

    def test_expanded_word_constructed_only_in_engine(self):
        """The field IR is produced only by the engine (word_expander.py)."""
        offenders = []
        for py, src in _psh_sources():
            rel = py.relative_to(ROOT).as_posix()
            if rel == "psh/expansion/word_expander.py":
                continue
            # Constructing the IR outside the engine would be a second producer.
            if re.search(r"\bExpandedWord\(", src) or re.search(
                    r"\bExpandedField\(", src):
                offenders.append(rel)
        assert not offenders, (
            "ExpandedWord/ExpandedField are built only by WordExpander "
            f"(one producer): {offenders}")


# --------------------------------------------------------------------------
# 2. No str | list[str] walker (static)
# --------------------------------------------------------------------------

class TestNoUnionWalker:
    def test_engine_producer_returns_expanded_word(self):
        src = (PSH / "expansion" / "word_expander.py").read_text()
        assert "def expand_to_word(self, word: Word,\n" in src
        assert "-> ExpandedWord:" in src

    def test_no_str_list_union_return_in_word_expander(self):
        """The field engine must not reintroduce a str/list union return."""
        src = (PSH / "expansion" / "word_expander.py").read_text()
        assert "Union[str, List[str]]" not in src
        assert "Union[str, list[str]]" not in src
        # The manager collapses to List[str] at the terminal boundary; the
        # engine never hands a bare "str or list" back to a walker.
        assert "str | List[str]" not in src
        assert "str | list[str]" not in src


# --------------------------------------------------------------------------
# 3. Per-run protection is honored (behavioral, synthetic offender inline)
# --------------------------------------------------------------------------

class TestProtectionHonored:
    def _expander(self, captured_shell):
        return captured_shell.expansion_manager.word_expander

    def test_protected_metachar_is_bracket_escaped(self, captured_shell):
        we = self._expander(captured_shell)
        field = ExpandedField([
            FieldRun('*', _PROTECTED, _NEVER),   # quoted star -> literal
            FieldRun('*', _ACTIVE, _NEVER),      # unquoted star -> pattern
        ])
        # The protected star becomes [*]; the active star stays a wildcard.
        assert we._pattern_from_runs(field.runs) == '[*]*'

    def test_active_only_pattern_is_raw(self, captured_shell):
        we = self._expander(captured_shell)
        field = ExpandedField([FieldRun('a*', _ACTIVE, _NEVER)])
        assert we._pattern_from_runs(field.runs) == 'a*'

    def test_all_extglob_metachars_neutralized(self, captured_shell):
        we = self._expander(captured_shell)
        field = ExpandedField([FieldRun('?(X)[a]', _PROTECTED, _NEVER)])
        # ? ( [ escaped; ] -> []]; the group can no longer form.
        assert we._pattern_from_runs(field.runs) == '[?][(]X)[[]a[]]'

    def test_synthetic_offender_that_ignores_protection_is_caught(
            self, captured_shell):
        """A drift that treats every run as ACTIVE (the pre-W1 word-wide
        behavior) produces a pattern where the protected ``*`` acts — the guard
        above would fail for it. This inline offender proves the guard bites."""
        field = ExpandedField([
            FieldRun('*', _PROTECTED, _NEVER),
            FieldRun('*', _ACTIVE, _NEVER),
        ])

        def offender_pattern(runs):
            # BUG: ignore protection, pass every run raw (H6 regression).
            return ''.join(r.text for r in runs)

        assert offender_pattern(field.runs) == '**'   # both stars active — WRONG
        # The correct engine keeps the first star literal:
        we = self._expander(captured_shell)
        assert we._pattern_from_runs(field.runs) == '[*]*'
        assert offender_pattern(field.runs) != we._pattern_from_runs(field.runs)


class TestSpliceBoundaryHonored:
    def test_splice_keeps_field_boundaries(self):
        b = _FieldBuilder()
        b.add(FieldRun('pre', _PROTECTED, _NEVER))
        b.splice([
            ExpandedField([FieldRun('a', _PROTECTED, _NEVER)]),
            ExpandedField([FieldRun('b', _PROTECTED, _NEVER)]),
        ])
        b.add(FieldRun('post', _ACTIVE, _ELIGIBLE))
        assert [f.text for f in b.finish()] == ['prea', 'bpost']

    def test_synthetic_offender_that_concatenates_is_caught(self):
        """A drift that concatenates $@ fields into a seed (the pre-W1 H5
        shortcut) collapses boundaries; the guard above would fail for it."""
        fields = [
            ExpandedField([FieldRun('a', _PROTECTED, _NEVER)]),
            ExpandedField([FieldRun('b', _PROTECTED, _NEVER)]),
        ]

        def offender_concat(seed, fs, suffix):
            # BUG: join all fields into the seed (H5 regression).
            return [seed + ''.join(f.text for f in fs) + suffix]

        assert offender_concat('pre', fields, 'post') == ['preabpost']  # WRONG

        b = _FieldBuilder()
        b.add(FieldRun('pre', _PROTECTED, _NEVER))
        b.splice(fields)
        b.add(FieldRun('post', _PROTECTED, _NEVER))
        correct = [f.text for f in b.finish()]
        assert correct == ['prea', 'bpost']
        assert correct != offender_concat('pre', fields, 'post')
