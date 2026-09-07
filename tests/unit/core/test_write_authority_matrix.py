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

import os
from dataclasses import dataclass, field
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


def _survives(entry: str, label: str, route: str) -> Cell:
    """A route that reports rc 1 and leaves the array untouched."""
    return Cell(entry, "value", label, _RO + route + _SURVIVES, 'rc=1\n1 2\n',
                err="readonly variable")


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
    _survives("unset", "readonly-unset-element-refused-C194", 'unset a[0]'),
    _survives("for", "readonly-loop-variable-refused-C194",
              'for a[0] in x; do :; done'),
    _survives("getopts", "readonly-getopts-target-refused-C194",
              'getopts x a[0]'),
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
