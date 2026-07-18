"""The field-splicing algebra: ExpandedWord / ExpandedField / FieldRun.

Closes reappraisal #20 H5 (composite multi-field expansion lost shell field
boundaries) and H6 (glob protection was word-wide, not per-character). Every
behavioral row here was RED on the base SHA (b6f14c2b) and is pinned to bash
5.2 (see tmp/boundary-ledgers/W1-probes/). The IR-structure classes pin the
representation and its splicing algebra directly.

Glob rows use ``isolated_shell_with_temp_dir`` with a controlled file set; the
non-glob field-boundary rows use ``captured_shell``.
"""
import dataclasses
import os
import subprocess
import sys

import pytest

from psh.expansion.word_expander import _FieldBuilder
from psh.expansion.word_expansion_types import (
    ExpandedField,
    ExpandedWord,
    FieldRun,
    Protection,
    Split,
)

_ACTIVE = Protection.ACTIVE
_PROTECTED = Protection.PROTECTED
_NEVER = Split.NEVER
_ELIGIBLE = Split.IFS_ELIGIBLE


def _fields(shell, script):
    """Run *script* through captured_shell and return printf's <f1><f2>… text."""
    shell.clear_output()
    rc = shell.run_command(script)
    assert rc == 0, shell.get_stderr()
    return shell.get_stdout()


def _glob_fields(cwd, script, files):
    """Run *script* through psh in a fresh *cwd* with *files* present.

    Pathname-generation rows need a controlled directory, so they run psh in a
    subprocess (parallel-safe; no shared cwd). Returns printf's <f1><f2>… text.
    """
    for name in files:
        open(os.path.join(cwd, name), 'w').close()
    p = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                       capture_output=True, text=True, cwd=cwd, timeout=30)
    assert p.returncode == 0, p.stderr
    return p.stdout


# --------------------------------------------------------------------------
# H5 — field splicing: an unquoted fragment adjacent to a quoted $@/[@]
#       must undergo IFS field splitting (was concatenated into a seed).
# --------------------------------------------------------------------------

class TestH5FieldSplicing:
    def test_at_suffix_unquoted_splits(self, captured_shell):
        # "$@"$x with set -- a b, x="c d" -> a / bc / d  (bash)
        assert _fields(
            captured_shell,
            'set -- a b; x="c d"; printf "<%s>" "$@"$x') == "<a><bc><d>"

    def test_at_prefix_unquoted_splits(self, captured_shell):
        # $x"$@" -> c / da / b
        assert _fields(
            captured_shell,
            'set -- a b; x="c d"; printf "<%s>" $x"$@"') == "<c><da><b>"

    def test_at_both_sides_unquoted_split(self, captured_shell):
        assert _fields(
            captured_shell,
            'set -- a b; x="c d"; y="e f"; printf "<%s>" $y"$@"$x') \
            == "<e><fa><bc><d>"

    def test_array_at_suffix_unquoted_splits(self, captured_shell):
        assert _fields(
            captured_shell,
            'a=(a b); x="c d"; printf "<%s>" "${a[@]}"$x') == "<a><bc><d>"

    def test_multi_at_with_fragment_between(self, captured_shell):
        assert _fields(
            captured_shell,
            'set -- 1 2; x="c d"; printf "<%s>" "$@"$x"$@"') \
            == "<1><2c><d1><2>"

    def test_at_suffix_custom_ifs_splits(self, captured_shell):
        # IFS=: -> the suffix $x="c:d" splits on ':'
        assert _fields(
            captured_shell,
            'IFS=:; set -- a b; x="c:d"; printf "<%s>" "$@"$x') \
            == "<a><bc><d>"

    def test_empty_at_with_affixes_is_one_field(self, captured_shell):
        # Inertness anchor: empty $@ between affixes -> ONE field "prepost".
        assert _fields(
            captured_shell,
            'set --; printf "<%s>" pre"$@"post') == "<prepost>"


# --------------------------------------------------------------------------
# H6 — per-character glob protection: a protected metacharacter beside an
#      active one must not glob (was word-wide protection).
# --------------------------------------------------------------------------

_GLOB_FILES = ('fa', 'fb', '*lit', 'a*b', 'abc', 'aXb')


class TestH6GlobProtection:
    def test_quoted_star_then_active_star(self, tmp_path):
        # "*"* -> matches names beginning with a LITERAL '*' -> '*lit'
        assert _glob_fields(tmp_path, 'printf "<%s>" "*"*', _GLOB_FILES) \
            == "<*lit>"

    def test_single_quoted_star_then_active_star(self, tmp_path):
        assert _glob_fields(tmp_path, "printf \"<%s>\" '*'*", _GLOB_FILES) \
            == "<*lit>"

    def test_escaped_star_beside_active_star(self, tmp_path):
        # a\*b* -> the escaped '*' is literal, the trailing '*' active -> 'a*b'
        assert _glob_fields(tmp_path, 'printf "<%s>" a\\*b*', _GLOB_FILES) \
            == "<a*b>"

    def test_quoted_var_glob_beside_active_star(self, tmp_path):
        # "$x"* with x="a*b" -> the whole "a*b" is protected -> only 'a*b'
        assert _glob_fields(tmp_path, 'x="a*b"; printf "<%s>" "$x"*',
                            _GLOB_FILES) == "<a*b>"

    def test_mixed_single_quote_star(self, tmp_path):
        assert _glob_fields(tmp_path, "printf \"<%s>\" a'*'b*", _GLOB_FILES) \
            == "<a*b>"

    def test_quoted_extglob_stays_literal(self, tmp_path):
        # shopt -s extglob; "f"a"?(X)"b -> the quoted ?(X) is literal, no glob.
        # 'faXb' is present so the OLD word-wide detection over-globs it (the
        # base-SHA bug); the per-run protection keeps the field literal.
        assert _glob_fields(
            tmp_path, 'shopt -s extglob; printf "<%s>" "f"a"?(X)"b',
            _GLOB_FILES + ('faXb',)) == "<fa?(X)b>"

    def test_active_star_still_globs(self, tmp_path):
        # Inertness: an unprotected '*' still globs.
        assert _glob_fields(tmp_path, 'printf "<%s>" fa*', _GLOB_FILES) \
            == "<fa>"


# --------------------------------------------------------------------------
# H5 + H6 combined — splice a field, THEN glob the resulting field.
# --------------------------------------------------------------------------

class TestH5H6Combined:
    def test_at_suffix_glob(self, tmp_path):
        # set -- fa fb; "$@"* -> the '*' attaches to the last field 'fb' and
        # globs -> fa / fb
        assert _glob_fields(tmp_path, 'set -- fa fb; printf "<%s>" "$@"*',
                            ('fa', 'fb', 'abc')) == "<fa><fb>"

    def test_at_suffix_var_glob(self, tmp_path):
        # set -- a; x="b*"; "$@"$x -> field 'ab*' globs -> abc
        assert _glob_fields(tmp_path, 'set -- a; x="b*"; printf "<%s>" "$@"$x',
                            ('fa', 'fb', 'abc')) == "<abc>"

    def test_array_at_suffix_glob(self, tmp_path):
        assert _glob_fields(tmp_path, 'a=(fa fb); printf "<%s>" "${a[@]}"*',
                            ('fa', 'fb', 'abc')) == "<fa><fb>"


# --------------------------------------------------------------------------
# IR structure and the splicing algebra, exercised directly.
# --------------------------------------------------------------------------

class TestFieldRunIR:
    def test_field_run_properties(self):
        r = FieldRun('*', _PROTECTED, _NEVER, 'quoted')
        assert r.is_protected is True
        assert r.is_splittable is False
        active = FieldRun('x', _ACTIVE, _ELIGIBLE, 'expansion')
        assert active.is_protected is False
        assert active.is_splittable is True

    def test_field_run_is_frozen(self):
        r = FieldRun('a', _ACTIVE, _NEVER)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.text = 'b'  # frozen dataclass

    def test_field_text_joins_runs(self):
        f = ExpandedField([
            FieldRun('a', _PROTECTED, _NEVER),
            FieldRun('b', _ACTIVE, _ELIGIBLE),
        ])
        assert f.text == 'ab'

    def test_empty_field_is_one_explicit_empty(self):
        # empty runs -> the field materializes to one empty string
        assert ExpandedField([]).text == ''

    def test_expanded_word_default_is_elision(self):
        assert ExpandedWord().fields == []


class TestSpliceAlgebra:
    def test_single_field_attaches_to_open(self):
        b = _FieldBuilder()
        b.add(FieldRun('pre', _PROTECTED, _NEVER))
        b.splice([ExpandedField([FieldRun('a', _PROTECTED, _NEVER)])])
        fields = b.finish()
        assert len(fields) == 1
        assert fields[0].text == 'prea'

    def test_multi_field_commits_middle_opens_last(self):
        b = _FieldBuilder()
        b.add(FieldRun('pre', _PROTECTED, _NEVER))
        b.splice([
            ExpandedField([FieldRun('a', _PROTECTED, _NEVER)]),
            ExpandedField([FieldRun('b', _PROTECTED, _NEVER)]),
            ExpandedField([FieldRun('c', _PROTECTED, _NEVER)]),
        ])
        b.add(FieldRun('post', _PROTECTED, _NEVER))
        fields = b.finish()
        assert [f.text for f in fields] == ['prea', 'b', 'cpost']

    def test_empty_splice_is_noop_on_boundaries(self):
        # pre"$@"post with empty $@ -> ONE field "prepost"
        b = _FieldBuilder()
        b.add(FieldRun('pre', _PROTECTED, _NEVER))
        b.splice([])
        b.add(FieldRun('post', _PROTECTED, _NEVER))
        fields = b.finish()
        assert len(fields) == 1
        assert fields[0].text == 'prepost'

    def test_empty_splice_alone_is_zero_fields(self):
        # "$@" alone with empty $@ -> word elision
        b = _FieldBuilder()
        b.splice([])
        assert b.finish() == []

    def test_has_content_tracks_open_field(self):
        b = _FieldBuilder()
        assert b.has_content is False
        b.splice([])           # empty $@ does not open a field
        assert b.has_content is False
        b.add(FieldRun('x', _ACTIVE, _NEVER))
        assert b.has_content is True
