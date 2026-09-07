"""Write-authority matrix — every write site × every observer, in one table.

The invariant this module exists to hold, for a shell variable, the working
directory, and the executable a name resolves to::

    the write happened ONCE, by its owner, and every observer agrees.

A write site (an assignment, an arithmetic store, a declaration builtin, a
nameref, ``read``/``mapfile``, a scope exit, ``cd``) decides a fact.  Several
independent observers can then be asked what that fact is: the stored value and
its attribute flags (``declare -p``), the effective lookup (``${x}``,
``${x-unset}``, ``set -u``), the environment a real CHILD PROCESS receives, the
executable actually dispatched by the next command, the read position of an
input descriptor, and the process's actual working directory.  A wrong-target
defect is exactly the case where two observers disagree, so the matrix asks all
of them about every entry point rather than trusting one.

Two kinds of cell live here.

**Green cells** are the regression net: behavior that is already correct is
pinned so a later slot's refactor cannot silently break it.

**Strict-xfail cells** are the flip mechanism.  Each carries an ``owner`` naming
the finding it records and the slot that closes it, and each states the CORRECT
(bash-verified) observation, so it fails today.  ``strict=True`` means a cell
that starts PASSING fails the suite: the owning slot cannot land its fix without
coming back here and deleting the mark.  That is also the red-on-base proof —
every xfail cell is red at this module's base by construction.

Expectations are empirical against bash 5.3.15 (the resolved oracle), probed in
``-c``, script-file and stdin modes before being written down; none of them
follows a bash 5.3 behavior change, so no CHANGES item is cited.  The matrix
asserts psh's OWN invariant, so the expectation is a literal here rather than a
live comparison; the owning slot ships the bash-differential conformance rows.

Reproduce any cell by hand with::

    cd "$(mktemp -d)"
    env -u PWD -u OLDPWD /opt/homebrew/bin/bash -c '<script>'
    env -u PWD -u OLDPWD python -m psh -c '<script>'

Improvement Program 2026-09 slot 1.0 (finding C226; C244 instances).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Union

import pytest
from shell_oracle import hermetic_shell_env, is_comparable, run_psh

#: Sentinel for ``Cell.rc`` when the exact status is not the subject of the cell
#: (bash's own status for an aborting error differs between ``-c`` and script
#: mode, which is a bash property, not a psh invariant).
NONZERO = "nonzero"


@dataclass(frozen=True)
class Cell:
    """One (entry point × observation) square of the matrix.

    ``script`` is run by psh; ``out``/``rc``/``err`` are what a correct psh
    produces, taken from bash 5.3.15.  ``owner`` is ``None`` for a green cell
    and ``"C0xx → slot N.M"`` for a cell a later slot closes.
    """

    entry: str
    obs: str
    label: str
    script: str
    out: str
    rc: Union[int, str] = 0
    err: str = ""
    owner: Union[str, None] = None
    #: For ``cwd`` cells: directories (relative to the run root) that the cell's
    #: marker file might land in.  The observation names the one it reached.
    landing: Tuple[str, ...] = field(default=())

    @property
    def id(self) -> str:
        """``entry.observation.label`` — the label names the C-id and slot for
        an xfail cell, so a failure report identifies the square directly."""
        return f"{self.entry}.{self.obs}.{self.label}"


def _param(cell: Cell) -> "pytest.ParameterSet":
    """Wrap ``cell`` for ``parametrize``, applying the strict xfail it owns."""
    marks = ()
    if cell.owner is not None:
        marks = (pytest.mark.xfail(strict=True, reason=cell.owner),)
    return pytest.param(cell, id=cell.id, marks=marks)


# ---------------------------------------------------------------------------
# VALUE cells — stored value, attribute flags and effective lookup.
# Observed in-process (``captured_shell``): no child process is involved, so the
# shell's own stdout/stderr is the whole observation.
# ---------------------------------------------------------------------------

_GREEN_VALUE_CELLS: Tuple[Cell, ...] = (
    # --- ordinary assignment -------------------------------------------------
    Cell("assign", "value", "scalar",
         'x=v; declare -p x', 'declare -- x="v"\n'),
    Cell("assign", "value", "append-operator",
         'x=a; x+=b; declare -p x', 'declare -- x="ab"\n'),
    Cell("assign", "lookup", "empty-string-is-set",
         'x=; echo "[${x-unset}]"; echo "[${x:-null}]"', '[]\n[null]\n'),
    Cell("assign", "flags", "plain-assignment-is-not-exported",
         'x=1; declare -p x', 'declare -- x="1"\n'),

    # --- arithmetic ----------------------------------------------------------
    Cell("arith", "value", "assignment-operator",
         '(( x = 5 )); declare -p x', 'declare -- x="5"\n'),
    Cell("arith", "value", "let-builtin",
         "let 'x=6'; declare -p x", 'declare -- x="6"\n'),
    Cell("arith", "value", "element-of-existing-array",
         'a=(1 2); (( a[1]=9 )); declare -p a',
         'declare -a a=([0]="1" [1]="9")\n'),
    Cell("arith", "value", "element-of-assoc-array",
         'declare -A m; (( m[k]=5 )); declare -p m',
         'declare -A m=([k]="5" )\n'),
    Cell("arith", "flags", "integer-attribute-evaluates-rhs",
         'declare -i n; n=3+4; declare -p n', 'declare -i n="7"\n'),

    # --- declaration builtins ------------------------------------------------
    Cell("declare", "value", "integer-attribute",
         'declare -i n=2+3; declare -p n', 'declare -i n="5"\n'),
    Cell("declare", "value", "indexed-array",
         'declare -a v=(1 2); declare -p v',
         'declare -a v=([0]="1" [1]="2")\n'),
    Cell("declare", "value", "assoc-array",
         'declare -A h=([k]=v); declare -p h', 'declare -A h=([k]="v" )\n'),
    Cell("declare", "flags", "export-marks-x",
         'export E=1; declare -p E', 'declare -x E="1"\n'),
    Cell("declare", "value", "local-shadows-then-restores",
         'x=outer; f(){ local x=inner; echo "[$x]"; }; f; echo "[$x]"',
         '[inner]\n[outer]\n'),
    Cell("declare", "lookup", "local-without-value-shadows-as-unset",
         'x=outer; f(){ local x; echo "[${x-unset}]"; }; f; echo "[$x]"',
         '[unset]\n[outer]\n'),
    Cell("declare", "flags", "local-restores-outer-attributes",
         'declare -i n=1; f(){ local n=2; declare -p n; }; f; declare -p n',
         'declare -- n="2"\ndeclare -i n="1"\n'),

    # --- nameref -------------------------------------------------------------
    Cell("nameref", "value", "write-reaches-target",
         'x=1; declare -n r=x; r=2; declare -p x', 'declare -- x="2"\n'),
    Cell("nameref", "value", "element-write-reaches-target",
         'a=(1 2); declare -n r=a; r[0]=9; declare -p a',
         'declare -a a=([0]="9" [1]="2")\n'),
    Cell("nameref", "lookup", "read-through-to-target",
         'x=1; declare -n r=x; echo "[$r]"', '[1]\n'),
    Cell("nameref", "value", "readonly-scalar-target-refused",
         'declare -r S=1; declare -n r=S; r=9', '', NONZERO,
         err="S: readonly variable"),

    # --- read / mapfile ------------------------------------------------------
    Cell("read", "value", "splits-into-named-fields",
         "read a b <<< 'x y'; declare -p a; declare -p b",
         'declare -- a="x"\ndeclare -- b="y"\n'),
    Cell("read", "value", "array-target",
         "read -a arr <<< 'x y'; declare -p arr",
         'declare -a arr=([0]="x" [1]="y")\n'),
    Cell("read", "value", "readonly-target-refused",
         "readonly x=1; read x <<< 'new'; echo \"rc=$?\"; declare -p x",
         'rc=1\ndeclare -r x="1"\n', err="x: readonly variable"),
    Cell("read", "flags", "allexport-applies-to-read",
         "set -a; read v <<< 'x'; declare -p v", 'declare -x v="x"\n'),
    Cell("mapfile", "value", "indexed-target",
         "mapfile -t m <<< $'a\\nb'; declare -p m",
         'declare -a m=([0]="a" [1]="b")\n'),

    # --- scope exit ----------------------------------------------------------
    Cell("scope-exit", "lookup", "local-is-gone-after-return",
         'f(){ local L=1; }; f; echo "[${L-unset}]"', '[unset]\n'),
    Cell("scope-exit", "value", "temp-env-restores-outer-value",
         'X=outer; f(){ echo "[$X]"; }; X=inner f; echo "[$X]"',
         '[inner]\n[outer]\n'),
    Cell("scope-exit", "lookup", "temp-env-leaves-name-unset",
         'f(){ echo "[$X]"; }; X=inner f; echo "[${X-unset}]"',
         '[inner]\n[unset]\n'),
)


# ---------------------------------------------------------------------------
# VALUE cells a later slot closes.  Each states the bash 5.3.15 observation, so
# it is red until its owner lands; ``strict=True`` then forces the owner to
# delete the mark rather than leave a stale xfail behind.
# ---------------------------------------------------------------------------

_FLIP_VALUE_CELLS: Tuple[Cell, ...] = (
    # C027 — `set -u` asks state.env, so a `local` shadowing an EXPORTED name
    # reads as set.  Exported-ness must not decide set-ness.
    Cell("declare", "lookup", "local-shadowing-export-is-unset-C027-slot1.15",
         'export FOO=outer; f(){ local FOO; echo "[${FOO}]"; }; set -u; f',
         '', NONZERO, err="FOO: unbound variable", owner="C027 → slot 1.15"),
    Cell("declare", "lookup", "shadowed-export-in-arithmetic-C027-slot1.15",
         'export FOO=outer; f(){ local FOO; echo $((FOO+1)); }; set -u; f',
         '', NONZERO, err="FOO: unbound variable", owner="C027 → slot 1.15"),
    Cell("declare", "lookup", "shadowed-export-seen-by-callee-C027-slot1.15",
         'export FOO=outer; g(){ echo "[${FOO}]"; }; f(){ local FOO; g; };'
         ' set -u; f',
         '', NONZERO, err="FOO: unbound variable", owner="C027 → slot 1.15"),

    # C028 — allexport is consumed at ONE site that only plain assignment
    # reaches, so the four declaration builtins never mark the export flag.
    Cell("declare", "flags", "allexport-marks-local-C028-slot1.16",
         'set -a; f(){ local L=1; declare -p L; }; f', 'declare -x L="1"\n',
         owner="C028 → slot 1.16"),
    Cell("declare", "flags", "allexport-marks-declare-C028-slot1.16",
         'set -a; f(){ declare L=1; declare -p L; }; f', 'declare -x L="1"\n',
         owner="C028 → slot 1.16"),
    Cell("declare", "flags", "allexport-marks-readonly-C028-slot1.16",
         'set -a; readonly R=1; declare -p R', 'declare -rx R="1"\n',
         owner="C028 → slot 1.16"),
    Cell("declare", "flags", "allexport-marks-declare-i-C028-slot1.16",
         'set -a; declare -i n=5; declare -p n', 'declare -ix n="5"\n',
         owner="C028 → slot 1.16"),
    Cell("declare", "flags", "allexport-marks-typeset-C028-slot1.16",
         'set -a; typeset T=1; declare -p T', 'declare -x T="1"\n',
         owner="C028 → slot 1.16"),

    # C090 — mapfile writes before validating its destination, so an assoc
    # target is replaced and ends up carrying both array attributes.
    Cell("mapfile", "value", "assoc-target-left-intact-C090-slot1.17",
         'declare -A a=([x]=old); mapfile -t a <<< new; declare -p a',
         'declare -A a=([x]="old" )\n', err="a: not an indexed array",
         owner="C090 → slot 1.17"),
    Cell("mapfile", "flags", "rejected-target-keeps-its-attributes-C090-slot1.17",
         'declare -A a=([x]=old); mapfile -t a <<< new;'
         ' case "$(declare -p a)" in *"declare -aA"*) echo BOTH;;'
         ' *) echo SINGLE;; esac',
         'SINGLE\n', owner="C090 → slot 1.17"),

    # C093 — promoting a scalar to an array must keep the scalar as element 0.
    Cell("arith", "value", "promotion-keeps-scalar-as-element-0-C093-slot1.18",
         'a=7; (( a[2]=9 )); declare -p a',
         'declare -a a=([0]="7" [2]="9")\n', owner="C093 → slot 1.18"),

    # C094 — an explicit subscript must not move the append cursor.
    Cell("assign", "value", "initializer-index-sets-no-high-water-mark-C094-slot1.18",
         'a=([5]=five [1]=one next); declare -p a',
         'declare -a a=([1]="one" [2]="next" [5]="five")\n',
         owner="C094 → slot 1.18"),
    Cell("assign", "value", "append-index-sets-no-high-water-mark-C094-slot1.18",
         'a=([5]=five); a+=([1]=one next); declare -p a',
         'declare -a a=([1]="one" [2]="next" [5]="five")\n',
         owner="C094 → slot 1.18"),

    # C095 — the integer attribute is applied at COMMIT, so an element's
    # expression sees the elements committed before it.
    Cell("arith", "value", "integer-element-sees-prior-commit-C095-slot1.18",
         "declare -ia a; a=(1 'a[0]+1'); declare -p a",
         'declare -ai a=([0]="1" [1]="2")\n', owner="C095 → slot 1.18"),
    Cell("arith", "value", "integer-append-converts-before-adding-C095-slot1.18",
         'declare -ia b=(1); b+=([0]+=2); declare -p b',
         'declare -ai b=([0]="3")\n', owner="C095 → slot 1.18"),

    # C096 — key validation belongs before the commit, not after it.
    Cell("assign", "value", "assoc-empty-key-rejected-C096-slot1.18",
         'declare -A a; a=([""]=bad); declare -p a; echo survived',
         '', 1, owner="C096 → slot 1.18"),
    Cell("assign", "value", "assoc-mixed-initializer-forms-rejected-C096-slot1.18",
         'declare -A b=([x]=one two three); declare -p b', '', 1,
         owner="C096 → slot 1.18"),

    # C136 — a declared-but-never-assigned array has no value to print.
    Cell("declare", "value", "indexed-never-assigned-prints-no-value-C136-slot1.18",
         'declare -a x; declare -p x', 'declare -a x\n',
         owner="C136 → slot 1.18"),
    Cell("declare", "value", "assoc-never-assigned-prints-no-value-C136-slot1.18",
         'declare -A y; declare -p y', 'declare -A y\n',
         owner="C136 → slot 1.18"),

    # C130 — the diagnostic must name the reference the user wrote.
    Cell("nameref", "value", "readonly-element-names-the-reference-C130-slot4.5",
         'declare -ra A=(1 2); declare -n r=A; r[0]=9', '', NONZERO,
         err="r: readonly variable", owner="C130 → slot 4.5"),

    # C071 — `export -n` through a nameref must clear the TARGET's flag.
    Cell("nameref", "flags", "export-n-clears-target-C071-slot4.9",
         'x=1; export x; declare -n r=x; export -n r; declare -p x',
         'declare -- x="1"\n', owner="C071 → slot 4.9"),
)


# ---------------------------------------------------------------------------
# C194 readonly-guard battery — GREEN, and deliberately so.
#
# C194 is a STRUCTURAL coverage note, not a divergence: ``executor/array.py``
# mutates an existing array through a local alias that the textual write-ban
# cannot see, yet all thirteen element-mutation routes below are already guarded
# exactly as bash 5.3.15 guards them (probed, three modes).  There is therefore
# no red-on-base behavior to xfail.  Slot 1.18 reroutes those writes through the
# store; these cells are the net that says the reroute changed nothing.
# ---------------------------------------------------------------------------

_RO = 'a=(1 2); readonly a; '
_SURVIVES = '; echo "rc=$?"; echo "${a[@]}"'


def _refused(entry: str, label: str, route: str) -> Cell:
    """A route that ABORTS the input: bash refuses before running anything more."""
    return Cell(entry, "value", label, _RO + route, '', NONZERO,
                err="a: readonly variable")


def _survives(entry: str, label: str, route: str,
              err: str = "readonly variable") -> Cell:
    """A route that reports rc 1 and leaves the array untouched."""
    return Cell(entry, "value", label, _RO + route + _SURVIVES, 'rc=1\n1 2\n',
                err=err)


_READONLY_ARRAY_CELLS: Tuple[Cell, ...] = (
    _refused("assign", "readonly-element-write-refused-C194", 'a[0]=x'),
    _refused("assign", "readonly-append-refused-C194", 'a+=(3)'),
    _refused("assign", "readonly-reassign-by-index-refused-C194", 'a=([0]=9)'),
    _refused("assign", "readonly-element-append-refused-C194", 'a[0]+=z'),
    _refused("assign", "readonly-append-explicit-index-refused-C194",
             'a+=([5]=z)'),
    _survives("arith", "readonly-increment-refused-C194", '(( a[0]++ ))'),
    _survives("arith", "readonly-let-refused-C194", "let 'a[0]=5'"),
    _survives("read", "readonly-read-a-refused-C194", "read -a a <<< 'x y'"),
    _survives("mapfile", "readonly-mapfile-refused-C194", 'mapfile -t a <<< x'),
    _survives("printf-v", "readonly-printf-v-refused-C194",
              "printf -v 'a[0]' x"),
    _survives("unset", "readonly-unset-element-refused-C194", 'unset a[0]',
              err="cannot unset: readonly variable"),
    # `a[0]` is not a name, and both shells say so before they say readonly.
    _survives("for", "readonly-loop-variable-refused-C194",
              'for a[0] in x; do :; done', err="not a valid identifier"),
    # Same square, but the two shells order the two complaints differently
    # (bash: not a valid identifier; psh: readonly variable).  rc and the array
    # agree, which is the invariant; the wording is an unowned divergence, so
    # asserting it here would pin psh's side of an open question.
    _survives("getopts", "readonly-getopts-target-refused-C194",
              'getopts x a[0]', err=""),
)

VALUE_CELLS: Tuple[Cell, ...] = (
    _GREEN_VALUE_CELLS + _READONLY_ARRAY_CELLS + _FLIP_VALUE_CELLS
)


# ---------------------------------------------------------------------------
# CHILD cells — the environment a real child process receives, and the
# executable the next command actually dispatches.
#
# Both observations require a fork, so the cell's script is wrapped in a brace
# group redirected to a file and the test reads the BYTES THAT REACHED THE FD
# (D3): a return code cannot tell "A ran" from "B ran".
# ---------------------------------------------------------------------------

#: Two same-named executables on two PATH entries.  Which one runs is the whole
#: observation, so each prints its own directory's letter.
_TWO_PROBES = (
    'mkdir -p a b\n'
    "printf '#!/bin/sh\\necho A\\n' > a/probe\n"
    "printf '#!/bin/sh\\necho B\\n' > b/probe\n"
    'chmod +x a/probe b/probe\n'
    'PATH=$PWD/a\n'
)

_GREEN_CHILD_CELLS: Tuple[Cell, ...] = (
    # --- child environment ---------------------------------------------------
    Cell("declare", "child-env", "export-reaches-the-child",
         'export E=1; printenv E; echo "rc=$?"', '1\nrc=0\n'),
    Cell("declare", "child-env", "declare-x-reaches-the-child",
         'declare -x E=1; printenv E; echo "rc=$?"', '1\nrc=0\n'),
    Cell("assign", "child-env", "plain-assignment-does-not-reach-the-child",
         'E=1; printenv E; echo "rc=$?"', 'rc=1\n'),
    Cell("assign", "child-env", "allexport-plain-assignment-reaches-the-child",
         'set -a; E=1; printenv E; echo "rc=$?"', '1\nrc=0\n'),
    Cell("nameref", "child-env", "write-through-nameref-reaches-the-child",
         'export x=1; declare -n r=x; r=2; printenv x', '2\n'),
    Cell("declare", "child-env", "local-shadow-is-what-the-child-sees",
         'export E=outer; f(){ local E=inner; printenv E; }; f; printenv E',
         'inner\nouter\n'),
    Cell("scope-exit", "child-env", "return-restores-what-the-child-sees",
         'export E=outer; f(){ local E=inner; }; f; printenv E', 'outer\n'),
    Cell("scope-exit", "child-env", "temp-env-is-gone-after-the-command",
         'f(){ printenv X; }; X=inner f; printenv X; echo "rc=$?"',
         'inner\nrc=1\n'),
    Cell("unset", "child-env", "unset-removes-it-from-the-child",
         'export E=1; unset E; printenv E; echo "rc=$?"', 'rc=1\n'),
    Cell("declare", "child-env", "export-n-removes-it-from-the-child",
         'export E=1; export -n E; printenv E; echo "rc=$?"', 'rc=1\n'),

    # --- executable dispatch -------------------------------------------------
    Cell("assign", "dispatch", "plain-PATH-write-changes-the-executable",
         _TWO_PROBES + 'probe\nPATH=$PWD/b\nprobe\n', 'A\nB\n'),
    Cell("declare", "dispatch", "export-PATH-changes-the-executable",
         _TWO_PROBES + 'export PATH=$PWD/b\nprobe\n', 'B\n'),
    Cell("declare", "dispatch", "declare-x-PATH-changes-the-executable",
         _TWO_PROBES + 'declare -x PATH=$PWD/b\nprobe\n', 'B\n'),
    Cell("nameref", "dispatch", "PATH-write-through-nameref-changes-it",
         _TWO_PROBES + 'declare -n r=PATH\nr=$PWD/b\nprobe\n', 'B\n'),
    Cell("read", "dispatch", "read-into-PATH-changes-the-executable",
         _TWO_PROBES + 'read PATH <<< "$PWD/b"\nprobe\n', 'B\n'),
    Cell("scope-exit", "dispatch", "local-PATH-never-dispatched-is-restored",
         _TWO_PROBES + 'f(){ local PATH=$PWD/b; return 0; }\nf\nprobe\n',
         'A\n'),
)

_FLIP_CHILD_CELLS: Tuple[Cell, ...] = (
    # C028 — the declaration builtins skip allexport, so the child genuinely
    # never receives the variable (printenv exits 1 and prints nothing).
    Cell("declare", "child-env", "allexport-local-reaches-the-child-C028-slot1.16",
         'set -a; f(){ local L=1; printenv L; }; f; echo "rc=$?"',
         '1\nrc=0\n', owner="C028 → slot 1.16"),
    Cell("declare", "child-env", "allexport-declare-reaches-the-child-C028-slot1.16",
         'set -a; declare D=1; printenv D; echo "rc=$?"', '1\nrc=0\n',
         owner="C028 → slot 1.16"),
    Cell("declare", "child-env", "allexport-readonly-reaches-the-child-C028-slot1.16",
         'set -a; readonly R=1; printenv R; echo "rc=$?"', '1\nrc=0\n',
         owner="C028 → slot 1.16"),

    # C044 — the effective PATH binding changes when the function scope pops,
    # but nothing tells the command hash table, so the NEXT dispatch still runs
    # the function's executable.
    Cell("scope-exit", "dispatch", "local-PATH-restored-on-return-C044-slot1.5",
         _TWO_PROBES + 'f(){ local PATH=$PWD/b; probe; }\nf\nprobe\n',
         'B\nA\n', owner="C044 → slot 1.5"),
    Cell("scope-exit", "dispatch", "temp-env-PATH-restored-after-command-C044-slot1.5",
         _TWO_PROBES + 'f(){ probe; }\nPATH=$PWD/b f\nprobe\n', 'B\nA\n',
         owner="C044 → slot 1.5"),
    Cell("scope-exit", "dispatch", "nested-local-PATH-restored-C044-slot1.5",
         _TWO_PROBES + 'g(){ local PATH=$PWD/b; probe; }\n'
         'f(){ g; probe; }\nf\nprobe\n', 'B\nA\nA\n',
         owner="C044 → slot 1.5"),
)

CHILD_CELLS: Tuple[Cell, ...] = _GREEN_CHILD_CELLS + _FLIP_CHILD_CELLS


# ---------------------------------------------------------------------------
# CWD cells — `cd` writes two things that must agree: the logical path it
# REPORTS in `$PWD`, and the directory the process is actually IN.  The cell
# creates a marker file afterwards, so the observation names the directory the
# write really reached rather than a status or a string (D3).
# ---------------------------------------------------------------------------

#: Physical directories a marker may land in.  `logical/link` is deliberately
#: absent: it is `real/child` under another name, and naming both would report
#: one file twice.
_LANDINGS = ("real/child", "real", "logical", "one/two", "one")

_CWD_LAYOUT = (
    'ROOT=$(pwd -P)\n'
    'mkdir -p real/child logical one/two\n'
    'ln -s ../real/child logical/link\n'
)

#: The cell's last act: drop a file in whatever directory the shell is really
#: in.  A status or a `$PWD` readback cannot tell a right cwd from a wrong one.
_CWD_MARKER = '\n: > marker\n'


def _cwd_cell(label: str, body: str, out: str, owner=None) -> Cell:
    return Cell("cd", "cwd", label, _CWD_LAYOUT + body + _CWD_MARKER, out,
                owner=owner, landing=_LANDINGS)


CWD_CELLS: Tuple[Cell, ...] = (
    # Green: `cd -P` commits to the physical path, and every observer follows.
    _cwd_cell("physical-parent-of-symlink",
              'cd -P logical/link\ncd ..',
              'PWD=real\ngetcwd=real\nmarker=real\n'),
    # Green: no symlink involved, so logical and physical cannot disagree.
    _cwd_cell("plain-nested-parent", 'cd one/two\ncd ..',
              'PWD=one\ngetcwd=one\nmarker=one\n'),
    # Green: standing ON the symlink, `$PWD` keeps the path the user typed
    # while the process is in the target — the two are SUPPOSED to differ here.
    _cwd_cell("symlink-target-reports-the-link",
              'cd logical/link',
              'PWD=link\ngetcwd=child\nmarker=real/child\n'),
    _cwd_cell("absolute-path", 'cd "$ROOT/one/two"',
              'PWD=two\ngetcwd=two\nmarker=one/two\n'),

    # C043 — `cd -L ..` resolves the parent PHYSICALLY while reporting the
    # LOGICAL path, so the shell ends up in a directory it is not naming, and
    # the next file lands there.  Repro:
    #   mkdir -p real/child logical; ln -s ../real/child logical/link
    #   cd logical/link; cd ..; pwd -P
    _cwd_cell("logical-parent-of-symlink-C043-slot1.4",
              'cd logical/link\ncd ..',
              'PWD=logical\ngetcwd=logical\nmarker=logical\n',
              owner="C043 → slot 1.4"),
)


# ---------------------------------------------------------------------------
# SPAWN cells — run through `run_psh` in all three input modes (`-c`, script
# file, stdin).  Two reasons a cell belongs here rather than in-process:
# a permanent fd redirection (`exec 3<`) must never run in the test process,
# and the mode axis is itself the subject for the cwd/lookup/environment
# families, whose seeding differs between `-c`, a script and stdin (D6).
# ---------------------------------------------------------------------------

_FD_DATA = "printf 'one\\ntwo\\nthree\\n' > data\nexec 3<data\n"

SPAWN_CELLS: Tuple[Cell, ...] = (
    # Green: the fd position is a shared fact — each reader resumes where the
    # last one stopped.
    Cell("read", "input", "sequential-reads-advance-the-fd",
         _FD_DATA + 'read -u 3 x\nread -u 3 y\nprintf "%s %s\\n" "$x" "$y"\n',
         'one two\n'),
    Cell("mapfile", "input", "accepted-target-consumes-the-input",
         _FD_DATA + 'mapfile -u 3 a\nread -u 3 line\n'
         'printf "<%s>[%s]\\n" "$line" "${a[0]}"\n',
         '<>[one\n]\n'),
    Cell("mapfile", "input", "count-limit-leaves-the-rest",
         _FD_DATA + 'mapfile -n 1 -u 3 a\nread -u 3 line\n'
         'printf "<%s>[%s]\\n" "$line" "${a[0]}"\n',
         '<two>[one\n]\n'),

    # C090 — the read happens before the destination is validated, so a
    # REJECTED mapfile still swallows the input the next reader needed.
    Cell("mapfile", "input", "rejected-target-consumes-nothing-C090-slot1.17",
         _FD_DATA + 'readonly a\nmapfile -u 3 a\nread -u 3 line\n'
         'printf "<%s>\\n" "$line"\n',
         '<one>\n', err="a: readonly variable", owner="C090 → slot 1.17"),

    # C043 in every input mode: `$PWD` and the real cwd must name one place.
    Cell("cd", "cwd", "logical-parent-agrees-with-pwd-P-C043-slot1.4",
         'mkdir -p real/child logical\nln -s ../real/child logical/link\n'
         'cd logical/link\ncd ..\np=$(pwd -P)\n'
         'printf "%s %s\\n" "${PWD##*/}" "${p##*/}"\n',
         'logical logical\n', owner="C043 → slot 1.4"),

    # C044 in every input mode: the executable dispatched after the scope pops.
    Cell("scope-exit", "dispatch", "restored-PATH-dispatches-C044-slot1.5",
         _TWO_PROBES + 'f(){ local PATH=$PWD/b; probe; }\nf\nprobe\n',
         'B\nA\n', owner="C044 → slot 1.5"),

    # C027 in every input mode.  bash's own status for an unbound variable
    # differs between `-c` (127) and a script (1) — a bash property, not a psh
    # invariant — so the cell pins the refusal, not the number.
    Cell("declare", "lookup", "shadowed-export-is-unbound-C027-slot1.15",
         'export FOO=outer; f(){ local FOO; echo "[${FOO}]"; }; set -u; f',
         '', NONZERO, err="FOO: unbound variable", owner="C027 → slot 1.15"),

    # C028 in every input mode: what the child actually receives.
    Cell("declare", "child-env", "allexport-local-reaches-child-C028-slot1.16",
         'set -a; f(){ local L=1; printenv L; }; f; echo "rc=$?"',
         '1\nrc=0\n', owner="C028 → slot 1.16"),
)

#: The input modes every SPAWN cell runs in (D6).
MODES = ("-c", "script", "stdin")


# ---------------------------------------------------------------------------
# Running a cell
# ---------------------------------------------------------------------------

def _check(cell: Cell, rc: int, out: str, err: str) -> None:
    """Compare all of a cell's observations at once, so a failure report shows
    which observer disagreed rather than only the first."""
    observed = {"stdout": out}
    expected = {"stdout": cell.out}
    if cell.rc == NONZERO:
        observed["refused"] = rc != 0
        expected["refused"] = True
    else:
        observed["status"] = rc
        expected["status"] = cell.rc
    if cell.err:
        observed["stderr names"] = cell.err in err
        expected["stderr names"] = True
    assert observed == expected, (
        f"cell {cell.id}\nscript:\n{cell.script}\nstderr was: {err!r}"
    )


def _run_case(script: str, cwd: str, mode: str = "-c"):
    """Run ``script`` through the hermetic runner, in one of the three modes.

    Out of process on purpose wherever a CHILD is part of the observation: the
    child writes at fd level, which the in-process capture fixtures cannot see,
    and pytest's own capture would decide whether they could — an observation
    must not depend on how the test session was launched.
    """
    env = hermetic_shell_env()
    if mode == "-c":
        return run_psh(["-c", script], cwd=cwd, env=env)
    if mode == "script":
        path = os.path.join(cwd, "case.sh")
        with open(path, "w") as fh:
            fh.write(script + "\n")
        return run_psh([path], cwd=cwd, env=env)
    return run_psh([], stdin_data=script + "\n", cwd=cwd, env=env)


@pytest.mark.parametrize("cell", [_param(c) for c in VALUE_CELLS])
def test_value_cell(captured_shell, cell: Cell) -> None:
    """Stored value, attribute flags and effective lookup after one write.

    Closes C226 instances for the in-process observers; the flip cells record
    C027, C028, C071, C090, C093, C094, C095, C096, C130 and C136.
    """
    rc = captured_shell.run_command(cell.script)
    _check(cell, rc, captured_shell.get_stdout(), captured_shell.get_stderr())


@pytest.mark.parametrize("cell", [_param(c) for c in CHILD_CELLS])
def test_child_cell(tmp_path, cell: Cell) -> None:
    """What a real child process receives, and which executable is dispatched.

    Closes C226 instances for the cross-process observers; the flip cells
    record C028 and C044.
    """
    result = _run_case(cell.script, str(tmp_path))
    assert is_comparable(result), f"cell {cell.id}: {result!r}"
    _check(cell, result.returncode, result.stdout, result.stderr)


@pytest.mark.parametrize("cell", [_param(c) for c in CWD_CELLS])
def test_cwd_cell(isolated_shell_with_temp_dir, cell: Cell) -> None:
    """Where `cd` says it went, where the process actually IS, and where the
    next file lands.

    Deliberately in-process: ``os.getcwd()`` is then a direct reading of the
    shell's own working directory rather than a report the shell wrote about
    itself, which is the whole point of a wrong-cwd pin (D3).  Every observation
    is read from Python or the filesystem, so nothing here depends on capture.
    Closes C226 instances; the flip cell records C043.
    """
    root = os.getcwd()
    rc = isolated_shell_with_temp_dir.run_command(cell.script)
    observed = "PWD={}\ngetcwd={}\n".format(
        os.path.basename(isolated_shell_with_temp_dir.state.get_variable("PWD") or ""),
        os.path.basename(os.getcwd()),
    )
    for candidate in cell.landing:
        if os.path.exists(os.path.join(root, candidate, "marker")):
            observed += f"marker={candidate}\n"
    _check(cell, rc, observed, "")


@pytest.mark.parametrize(
    "cell,mode",
    [pytest.param(c, m, id=f"{c.id}-{m}",
                  marks=((pytest.mark.xfail(strict=True, reason=c.owner),)
                         if c.owner else ()))
     for c in SPAWN_CELLS for m in MODES],
)
def test_spawn_cell(tmp_path, cell: Cell, mode: str) -> None:
    """The same square in `-c`, script-file and stdin mode (D6).

    Lives out of process because a permanent fd redirection must not run in the
    test runner, and because input mode is itself the variable for the cwd,
    lookup and environment families.  Closes C226 instances; the flip cells
    record C027, C028, C043, C044 and C090.
    """
    result = _run_case(cell.script, str(tmp_path), mode)
    assert is_comparable(result), f"cell {cell.id} in {mode}: {result!r}"
    _check(cell, result.returncode, result.stdout, result.stderr)


# ---------------------------------------------------------------------------
# The matrix IS the guard, so what guards the matrix is this: a flip cell must
# name a finding that exists and a slot that exists.  Without it a cell could
# carry a plausible-looking reason for a slot nobody will ever run, and quietly
# never be flipped.
# ---------------------------------------------------------------------------

ALL_CELLS: Tuple[Cell, ...] = (
    VALUE_CELLS + CHILD_CELLS + CWD_CELLS + SPAWN_CELLS
)

#: The one shape an xfail reason may take: the finding(s), then the owning slot.
OWNER_RE = re.compile(r"^C\d{3}( ?, ?C\d{3})* → slot \d\.\d+$")

_EVIDENCE = (Path(__file__).resolve().parents[3] / "docs" / "reviews" /
             "evidence" / "improvement_program_2026_09")
_CID_RE = re.compile(r"C\d{3}")


def _load(name: str):
    path = _EVIDENCE / name
    assert path.is_file(), (
        f"{path} is missing: the matrix validates its flip cells against the "
        f"campaign's own registries, so it cannot run without them."
    )
    return json.loads(path.read_text())


def known_slots() -> frozenset:
    """Every slot id the program declares, from the campaign's wave manifest."""
    return frozenset(
        slot["id"]
        for wave in _load("wave-manifest.json")["waves"]
        for slot in wave.get("slots", ())
    )


def known_findings() -> frozenset:
    """Every finding id the campaign inventory carries."""
    return frozenset(row["cid"] for row in _load("INVENTORY.json"))


def owner_problem(reason: str, slots: frozenset, findings: frozenset):
    """Why ``reason`` is unusable as a flip-cell owner, or ``None`` if it is.

    Split out so the rule has exactly one implementation and can be aimed at a
    synthetic offender.
    """
    if not OWNER_RE.match(reason):
        return f"reason {reason!r} does not match {OWNER_RE.pattern!r}"
    slot = reason.rsplit(" ", 1)[-1]
    if slot not in slots:
        return f"reason {reason!r} names slot {slot}, which the program has no brief for"
    unknown = sorted(set(_CID_RE.findall(reason)) - findings)
    if unknown:
        return f"reason {reason!r} names {unknown}, absent from the inventory"
    return None


def test_every_flip_cell_names_a_real_finding_and_a_real_slot() -> None:
    """A cell that no slot will ever flip is a cell that hides forever."""
    slots, findings = known_slots(), known_findings()
    problems = [owner_problem(c.owner, slots, findings)
                for c in ALL_CELLS if c.owner is not None]
    assert [p for p in problems if p] == []


def test_every_flip_cell_id_repeats_its_finding_and_slot() -> None:
    """The failure report must identify the square without the reason string:
    pytest prints the id, not the xfail reason, when a strict xfail passes."""
    mismatched = []
    for cell in ALL_CELLS:
        if cell.owner is None:
            continue
        slot = cell.owner.rsplit(" ", 1)[-1]
        wanted = _CID_RE.findall(cell.owner) + [f"slot{slot}"]
        missing = [token for token in wanted if token not in cell.label]
        if missing:
            mismatched.append((cell.id, missing))
    assert mismatched == []


def test_every_finding_named_in_a_label_exists() -> None:
    """Green cells name findings too (C194's readonly battery); a typo there
    would point a later reader at nothing."""
    findings = known_findings()
    unknown = sorted({
        cid for cell in ALL_CELLS for cid in _CID_RE.findall(cell.label)
    } - findings)
    assert unknown == []


def test_cell_ids_are_unique() -> None:
    """Two cells sharing an id would let one shadow the other in the report."""
    ids = [c.id for c in ALL_CELLS]
    assert sorted(ids) == sorted(set(ids))


@pytest.mark.parametrize("reason,why", [
    ("C043 -> slot 1.4", "ASCII arrow instead of the separator the rule states"),
    ("C043 → slot 1.99", "a slot the program has no brief for"),
    ("C999 → slot 1.4", "a finding absent from the inventory"),
    ("slot 1.4", "no finding at all"),
    ("C043 → 1.4", "no slot keyword"),
    ("C43 → slot 1.4", "a malformed finding id"),
    ("C043 → slot 1.4 (pending)", "trailing prose that hides the real target"),
])
def test_owner_validator_rejects_synthetic_offenders(reason: str, why: str) -> None:
    """Mutation check for the guard above: each of these MUST be refused."""
    assert owner_problem(reason, known_slots(), known_findings()) is not None, why


@pytest.mark.parametrize("reason", [
    "C043 → slot 1.4",
    "C093, C094 → slot 1.18",
    "C093,C094 → slot 1.18",
])
def test_owner_validator_accepts_the_declared_shapes(reason: str) -> None:
    """The offender test is only meaningful if the rule accepts real reasons."""
    assert owner_problem(reason, known_slots(), known_findings()) is None
