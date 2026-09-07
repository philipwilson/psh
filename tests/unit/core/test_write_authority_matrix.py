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

**Flipping a cell**, when the owning slot lands, is two edits and only two:
delete ``owner=``, and strip the ``-C0xx-slotN.M`` token from the label (the
helper-built cells drop the token on their own; a hand-written label must be
edited, or ``test_a_green_cell_never_claims_a_slot`` goes red).  Never touch what
the cell DEMANDS — the expectation states bash 5.3.15's behavior and is the
reason the cell exists.  ``test_flipping_a_cell_never_rewrites_its_expectation``
holds the helpers to that, and grepping the label token finds a slot's cells (see
the flip table in the slot handoff, since some cells are helper-generated and a
source grep undercounts them).

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
    # The SCALAR route applies the integer attribute, which is what makes W1-N27
    # a per-element gap rather than a missing attribute.
    Cell("printf-v", "value", "integer-attribute-on-scalar-target",
         "declare -i n; printf -v n '%s' '2+3'; declare -p n",
         'declare -i n="5"\n'),
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
    # The binding and the EXPANSION read through an element reference are both
    # correct.  That is what makes W1-N25 a resolution bug in the store's
    # nameref walk rather than a binding bug: everything that goes through
    # expansion works, everything else sees an unresolved `arr[1]`.
    Cell("nameref", "lookup", "read-through-to-element-reference",
         "arr=(a b c); declare -n r='arr[1]'; echo \"[$r]\"", '[b]\n'),
    Cell("nameref", "value", "plain-write-through-element-reference",
         "arr=(a b c); declare -n r='arr[1]'; r=Z; declare -p arr",
         'declare -a arr=([0]="a" [1]="Z" [2]="c")\n'),
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

    # W1-N7 — a `for` whose control variable is a NAMEREF rebinds the reference
    # to each word in turn (bash 5.3.15 man page, `declare -n`: "a name
    # reference is established for each word in the list, in turn"), so the body
    # writes a DIFFERENT variable each iteration.  psh never rebinds and writes
    # every word into the original target, so the second variable is never
    # touched — the loop variable is a where-does-data-go fact, decided wrong.
    #   x=0; y=0; declare -n r=x; for r in x y; do r=5; done; declare -p r x y
    Cell("for", "value", "nameref-loop-variable-rebinds-per-word-W1-N7-slot1.18",
         'x=0; y=0; declare -n r=x; for r in x y; do r=5; done; declare -p r x y',
         'declare -n r="y"\ndeclare -- x="5"\ndeclare -- y="5"\n',
         owner="W1-N7 → slot 1.18"),
    # Same rule's refusal half: a word that is not a name cannot be bound, so
    # the body never runs and nothing is written.
    Cell("for", "value", "nameref-loop-invalid-word-writes-nothing-W1-N7-slot1.18",
         'x=0; declare -n r=x; for r in 1 2; do echo body; done; echo "rc=$? [$x]"',
         'rc=1 [0]\n', err="not a valid identifier", owner="W1-N7 → slot 1.18"),

    # W1-N25 — a nameref may be bound to an array or assoc ELEMENT.  The store's
    # nameref walk hands back the target NAME (`arr[1]`) without resolving the
    # subscript, and only the EXPANSION path parses it.  So `$r` is right while
    # every other reader sees an empty (arithmetic: zero) value: a compound
    # assignment destroys the element instead of extending it, and a plain
    # arithmetic read of it is 0 with no write involved at all.
    #   arr=(a b c); declare -n r='arr[1]'; r+=X; declare -p arr
    Cell("nameref", "value", "compound-append-through-element-reference-W1-N25-slot1.18",
         "arr=(a b c); declare -n r='arr[1]'; r+=X; declare -p arr",
         'declare -a arr=([0]="a" [1]="bX" [2]="c")\n',
         owner="W1-N25 → slot 1.18"),
    Cell("arith", "value", "compound-add-through-element-reference-W1-N25-slot1.18",
         "arr=(1 2 3); declare -n r='arr[1]'; (( r += 10 )); declare -p arr",
         'declare -a arr=([0]="1" [1]="12" [2]="3")\n',
         owner="W1-N25 → slot 1.18"),
    Cell("nameref", "value", "compound-append-through-assoc-element-reference-W1-N25-slot1.18",
         "declare -A m=([k]=b); declare -n r='m[k]'; r+=X; declare -p m",
         'declare -A m=([k]="bX" )\n', owner="W1-N25 → slot 1.18"),
    # No write at all: an arithmetic READ of the same reference is 0.
    Cell("arith", "lookup", "read-through-element-reference-W1-N25-slot1.18",
         "arr=(1 2 3); declare -n r='arr[1]'; echo $(( r ));"
         " if (( r > 1 )); then echo big; else echo small; fi",
         '2\nbig\n', owner="W1-N25 → slot 1.18"),
    # And the same read under `set -u`, where psh calls the element unbound.
    Cell("arith", "lookup", "read-through-element-reference-under-nounset-W1-N25-slot1.18",
         "set -u; arr=(1 2 3); declare -n r='arr[1]'; echo $(( r ))",
         '2\n', owner="W1-N25 → slot 1.18"),
    # Three more routes into the same unresolved name: a different evaluator
    # node, a different binding statement, and a subscript that must be
    # normalised before it can be read.
    Cell("arith", "value", "post-increment-through-element-reference-W1-N25-slot1.18",
         "arr=(1 2 3); declare -n r='arr[1]'; (( r++ )); declare -p arr",
         'declare -a arr=([0]="1" [1]="3" [2]="3")\n',
         owner="W1-N25 → slot 1.18"),
    Cell("nameref", "value", "compound-append-through-local-element-reference-W1-N25-slot1.18",
         "arr=(a b c); f(){ local -n r='arr[1]'; r+=X; }; f; declare -p arr",
         'declare -a arr=([0]="a" [1]="bX" [2]="c")\n',
         owner="W1-N25 → slot 1.18"),
    Cell("nameref", "value", "compound-append-through-negative-index-reference-W1-N25-slot1.18",
         "arr=(a b c); declare -n r='arr[-1]'; r+=X; declare -p arr",
         'declare -a arr=([0]="a" [1]="b" [2]="cX")\n',
         owner="W1-N25 → slot 1.18"),

    # W1-N28 — an ATTRIBUTE-ONLY declaration through an element-bound reference
    # is the same unresolved name arriving at the declaration builtins.  bash
    # applies the attribute to the containing array and leaves the element
    # alone; psh overwrites the element with "" and applies no attribute, and on
    # an unset element it CREATES one.  `readonly`/`export` clear it where bash
    # refuses the subscripted name outright.
    #   arr=(1 2 3); declare -n r='arr[1]'; declare -i r; declare -p arr
    #
    # Two neighbouring rows are deliberately NOT pinned, both bash-side quirks:
    # bare `declare r` through an element reference empties the WHOLE array in
    # bash 5.3.15, and `[[ -v r ]]` reports unset for an element that is set.
    # Pinning either would make psh copy a bash bug.
    Cell("declare", "flags", "integer-attribute-through-element-reference-keeps-the-element-W1-N28-slot1.18",
         "arr=(1 2 3); declare -n r='arr[1]'; declare -i r; declare -p arr",
         'declare -ai arr=([0]="1" [1]="2" [2]="3")\n',
         owner="W1-N28 → slot 1.18"),
    Cell("declare", "flags", "export-attribute-through-element-reference-keeps-the-element-W1-N28-slot1.18",
         "arr=(1 2 3); declare -n r='arr[1]'; declare -x r; declare -p arr",
         'declare -ax arr=([0]="1" [1]="2" [2]="3")\n',
         owner="W1-N28 → slot 1.18"),
    Cell("declare", "flags", "integer-attribute-through-assoc-element-reference-keeps-the-element-W1-N28-slot1.18",
         "declare -A m=([k]=2); declare -n r='m[k]'; declare -i r; declare -p m",
         'declare -Ai m=([k]="2" )\n', owner="W1-N28 → slot 1.18"),
    Cell("declare", "value", "attribute-through-reference-to-unset-element-creates-nothing-W1-N28-slot1.18",
         "arr=(1 2 3); declare -n r='arr[7]'; declare -i r; declare -p arr",
         'declare -ai arr=([0]="1" [1]="2" [2]="3")\n',
         owner="W1-N28 → slot 1.18"),
    Cell("declare", "value", "readonly-through-element-reference-refused-and-element-kept-W1-N28-slot1.18",
         "arr=(1 2 3); declare -n r='arr[1]'; readonly r; declare -p arr",
         'declare -a arr=([0]="1" [1]="2" [2]="3")\n',
         err="not a valid identifier", owner="W1-N28 → slot 1.18"),

    # W1-N27 — the integer and case attributes are applied on the SCALAR write
    # path only, so a builtin writing an ELEMENT stores the raw word: an `-ai`
    # array keeps `2+3` instead of 5, an `-Au` assoc keeps `abc` instead of ABC.
    #   declare -ai a; printf -v 'a[0]' '%s' '2+3'; declare -p a
    Cell("printf-v", "flags", "integer-attribute-on-element-write-W1-N27-slot1.18",
         "declare -ai a; printf -v 'a[0]' '%s' '2+3'; declare -p a",
         'declare -ai a=([0]="5")\n', owner="W1-N27 → slot 1.18"),
    Cell("printf-v", "flags", "uppercase-attribute-on-assoc-element-write-W1-N27-slot1.18",
         "declare -Au m; printf -v 'm[k]' abc; declare -p m",
         'declare -Au m=([k]="ABC" )\n', owner="W1-N27 → slot 1.18"),
    Cell("read", "flags", "integer-attribute-on-read-a-elements-W1-N27-slot1.18",
         "declare -ai a; read -a a <<< '2+3 4*2'; declare -p a",
         'declare -ai a=([0]="5" [1]="8")\n', owner="W1-N27 → slot 1.18"),
    Cell("mapfile", "flags", "integer-attribute-on-mapfile-elements-W1-N27-slot1.18",
         "declare -ai a; mapfile -t a <<< '2+3'; declare -p a",
         'declare -ai a=([0]="5")\n', owner="W1-N27 → slot 1.18"),

    # C093 — promotion drops the scalar on EVERY route, not only the arithmetic
    # one the finding was first written from.
    Cell("assign", "value", "promotion-keeps-scalar-on-plain-route-C093-slot1.18",
         'a=sc; a[2]=p; declare -p a', 'declare -a a=([0]="sc" [2]="p")\n',
         owner="C093 → slot 1.18"),

    # W1-N8 — three write sites accept a target that is not a name at all, so a
    # variable bash refuses to create is created, or an array element bash
    # refuses to touch is written.  The store's naming rule is the same rule at
    # every entry point; these three reach past it.
    #   getopts a bad-name -a; declare -p bad-name
    Cell("getopts", "value", "invalid-name-is-not-created-W1-N8-slot1.18",
         'getopts a bad-name -a; echo "rc=$?"; declare -p bad-name',
         'rc=1\n', 1, err="not a valid identifier", owner="W1-N8 → slot 1.18"),
    # A subscripted word is not a name either, and the array must be untouched.
    # This is the row the C194 getopts cell CANNOT reach: there the readonly
    # guard answers first, so name validation is never exercised.
    Cell("getopts", "value", "subscript-is-not-a-name-W1-N8-slot1.18",
         "a=(1); getopts a 'a[0]' -a; echo \"rc=$?\"; declare -p a",
         'rc=1\ndeclare -a a=([0]="1")\n', err="not a valid identifier",
         owner="W1-N8 → slot 1.18"),
    Cell("printf-v", "value", "invalid-name-is-not-created-W1-N8-slot1.18",
         "printf -v 'bad-name' x; echo \"rc=$?\"; declare -p bad-name",
         'rc=2\n', 1, err="not a valid identifier", owner="W1-N8 → slot 1.18"),
    # An unbound nameref takes its target from the next assignment, and that
    # target has to be a name; bash refuses and aborts the input.
    Cell("nameref", "value", "invalid-target-refused-at-assignment-W1-N8-slot1.18",
         'declare -n r; r=bad-name; echo "rc=$?"; declare -p r', '', NONZERO,
         err="not a valid identifier", owner="W1-N8 → slot 1.18"),
    # An empty subscript is not a name either; psh silently treats it as [0].
    Cell("printf-v", "value", "empty-subscript-is-not-a-name-W1-N8-slot1.18",
         "a=(z); printf -v 'a[]' v; echo \"rc=$?\"; declare -p a",
         'rc=2\ndeclare -a a=([0]="z")\n', err="not a valid identifier",
         owner="W1-N8 → slot 1.18"),
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
    # This cell proves ONLY that a readonly array is not written through
    # `getopts`; it does not prove that `a[0]` was rejected as a name, because
    # psh does not check the name here at all — on a NON-readonly array it
    # writes the element, which is W1-N8's subject.  The two shells therefore
    # refuse for different reasons (bash: not a valid identifier; psh: readonly
    # variable), so the wording is deliberately not asserted.
    _survives("getopts", "readonly-getopts-target-refused-C194",
              'getopts x a[0]', err=""),
)

# ---------------------------------------------------------------------------
# Attribute changes on a READONLY variable.
#
# `readonly` freezes the value; bash 5.3.15 also refuses the attributes that
# decide how a FUTURE value would be stored (`-i`, `-l`, `-u`), while still
# allowing `-x`, which changes only who can see it.  The refusal half was the
# gate-triage row G17 (`test_declare_i_on_readonly_succeeds`); slot 2.4 landed
# it, so both halves are green and neither claims a slot.  The `-x` half is the
# boundary the refusal must not cross.
#
#   x=ab; readonly x; declare -i x; echo "rc=$?"; declare -p x
#   bash -> rc=1, `declare -r x="ab"`    psh -> rc=0, `declare -ir x="ab"`
# ---------------------------------------------------------------------------

#: name, setup, variable, `declare -p` after a REFUSED attribute, after `-x`
#: (the two printed forms are bash 5.3.15's, and neither depends on `owner`)
_RO_TARGETS = (
    ("scalar", 'x=ab; readonly x; ', 'x',
     'declare -r x="ab"', 'declare -rx x="ab"'),
    ("indexed", 'a=(ab); readonly a; ', 'a',
     'declare -ar a=([0]="ab")', 'declare -arx a=([0]="ab")'),
    ("assoc", 'declare -A m=([k]=ab); readonly m; ', 'm',
     'declare -Ar m=([k]="ab" )', 'declare -Arx m=([k]="ab" )'),
)

#: the three attributes bash refuses to add to a readonly variable
_RO_ATTRS = (("i", "integer"), ("l", "lowercase"), ("u", "uppercase"))


def _attr_cell(flag, name, target, setup, var, printed, *, refused: bool,
               owner=None) -> Cell:
    """One (attribute × target) square.

    ``refused`` says what bash 5.3.15 does and fixes the WHOLE expectation;
    ``owner`` says only who flips the cell.  They are separate parameters on
    purpose.  Deriving the expectation from ``owner`` — as this helper first did
    — means that deleting the mark also rewrites the cell to demand psh's
    current behavior, so slot 2.4 would flip nine cells into pinning the very
    defect they exist to catch, and a correct fix would turn them red.  Only the
    label's owner token may depend on ``owner``, because a flipped cell must
    stop claiming a slot (``test_a_green_cell_never_claims_a_slot``).

    ``refused`` is keyword-only so the parameter whose entire purpose is to be
    independent of ``owner`` cannot be supplied by position and drift back into
    looking like part of the ownership argument list.
    """
    token = "-G17-slot2.4" if owner else ""
    verdict = "refused" if refused else "allowed"
    return Cell(
        "declare", "flags",
        f"{name}-attribute-on-readonly-{target}-{verdict}{token}",
        setup + f'declare -{flag} {var}; echo "rc=$?"; declare -p {var}',
        "rc={}\n{}\n".format(1 if refused else 0, printed),
        err="readonly variable" if refused else "",
        owner=owner,
    )


_READONLY_ATTRIBUTE_CELLS: Tuple[Cell, ...] = tuple(
    # Slot 2.4 landed the refusal, so these nine are green and carry no owner;
    # `refused=True` still states what bash 5.3.15 does and is what fixes the
    # expectation (see _attr_cell: the verdict never depended on `owner`).
    _attr_cell(flag, name, target, setup, var, p_refused, refused=True)
    for target, setup, var, p_refused, _p_allowed in _RO_TARGETS
    for flag, name in _RO_ATTRS
) + tuple(
    _attr_cell("x", "export", target, setup, var, p_allowed, refused=False)
    for target, setup, var, _p_refused, p_allowed in _RO_TARGETS
) + (
    # W1-N2 — a subscripted `declare` assignment is an ordinary element write in
    # bash; psh rejects the whole word as a name and the element keeps its value.
    #   a=(1 2); declare a[1]=q; declare -p a
    #   bash -> rc=0, [1]="q"    psh -> rc=1, not a valid identifier, unchanged
    Cell("declare", "value",
         "subscripted-assignment-writes-the-element-W1-N2-slot1.18",
         'a=(1 2); declare a[1]=q; echo "rc=$?"; declare -p a',
         'rc=0\ndeclare -a a=([0]="1" [1]="q")\n',
         owner="W1-N2 → slot 1.18"),
)


VALUE_CELLS: Tuple[Cell, ...] = (
    _GREEN_VALUE_CELLS + _READONLY_ARRAY_CELLS + _READONLY_ATTRIBUTE_CELLS
    + _FLIP_VALUE_CELLS
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
    # Declaring the local and assigning it are two statements, so the effective
    # binding changes at the assignment rather than at the declaration.
    Cell("scope-exit", "dispatch", "local-PATH-without-value-then-assigned-C044-slot1.5",
         _TWO_PROBES + 'f(){ local PATH; PATH=$PWD/b; probe; }\nf\nprobe\n',
         'B\nA\n', owner="C044 → slot 1.5"),
    # `declare -g` writes the GLOBAL while the local still shadows it, so the
    # effective binding does not change here — the value the next dispatch must
    # resolve through is the one `declare -g` left behind.  The case slot 1.5's
    # observer counter must NOT count as an effective-binding change.
    Cell("scope-exit", "dispatch", "declare-g-PATH-under-local-C044-slot1.5",
         _TWO_PROBES + 'f(){ local PATH=$PWD/b; declare -g PATH=$PWD/a; probe; }\n'
         'f\nprobe\n', 'B\nA\n', owner="C044 → slot 1.5"),
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

    # W1-N29 — the same preflight hole as C090, reached through an element-bound
    # nameref: the destination is refused (bash: not a valid identifier) but the
    # input is swallowed first, so the next reader gets nothing.
    Cell("mapfile", "input", "element-reference-target-consumes-nothing-W1-N29-slot1.17",
         _FD_DATA + "arr=(a)\ndeclare -n r='arr[0]'\nmapfile -u 3 r\n"
         'read -u 3 line\nprintf "<%s>\\n" "$line"\ndeclare -p arr\n',
         '<one>\ndeclare -a arr=([0]="a")\n', err="not a valid identifier",
         owner="W1-N29 → slot 1.17"),

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

    # In every input mode: a readonly variable refuses an attribute that would
    # change how a future value is stored (was G17, closed by slot 2.4).
    Cell("declare", "flags", "integer-attribute-on-readonly-refused",
         'x=ab; readonly x; declare -i x; echo "rc=$?"; declare -p x',
         'rc=1\ndeclare -r x="ab"\n', err="readonly variable"),

    # W1-N7 in every input mode: which variable the loop body writes.
    Cell("for", "value",
         "nameref-loop-rebinds-per-word-across-input-modes-W1-N7-slot1.18",
         'x=0; y=0; declare -n r=x; for r in x y; do r=5; done; declare -p r x y',
         'declare -n r="y"\ndeclare -- x="5"\ndeclare -- y="5"\n',
         owner="W1-N7 → slot 1.18"),

    # W1-N25 in every input mode: whether the read half of a read-modify-write
    # through an element reference sees the element.
    Cell("nameref", "value",
         "compound-append-through-element-across-input-modes-W1-N25-slot1.18",
         "arr=(a b c); declare -n r='arr[1]'; r+=X; declare -p arr",
         'declare -a arr=([0]="a" [1]="bX" [2]="c")\n',
         owner="W1-N25 → slot 1.18"),

    # W1-N8 in every input mode: whether a name bash refuses gets created.
    Cell("getopts", "value",
         "invalid-name-not-created-across-input-modes-W1-N8-slot1.18",
         'getopts a bad-name -a; echo "rc=$?"; declare -p bad-name',
         'rc=1\n', 1, err="not a valid identifier", owner="W1-N8 → slot 1.18"),
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


#: Built once, at module level, so the strictness guard can inspect the very
#: parameter sets the runner uses rather than a rebuilt copy of them.
SPAWN_PARAMS = [
    pytest.param(c, m, id=f"{c.id}-{m}",
                 marks=((pytest.mark.xfail(strict=True, reason=c.owner),)
                        if c.owner else ()))
    for c in SPAWN_CELLS for m in MODES
]


@pytest.mark.parametrize("cell,mode", SPAWN_PARAMS)
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

#: A finding token is one of three kinds, because the campaign registers
#: findings in three places: ``C043`` is an inventory row, ``G17`` a gate-triage
#: row, and ``W1-N2`` a wave N-row.  Only C-ids can be checked against a registry
#: from here — the integrator writes G and W rows into ``LEDGER.md`` on the day,
#: so for those the shape is the whole of what this can honestly verify.
_TOKEN = r"(?:C\d{3}|G\d{2}|W\d-N\d+)"

#: The one shape an xfail reason may take: the finding(s), then the owning slot.
OWNER_RE = re.compile(rf"^{_TOKEN}( ?, ?{_TOKEN})* → slot \d\.\d+$")

_EVIDENCE = (Path(__file__).resolve().parents[3] / "docs" / "reviews" /
             "evidence" / "improvement_program_2026_09")
_CID_RE = re.compile(r"C\d{3}")
_TOKEN_RE = re.compile(_TOKEN)


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
        wanted = _TOKEN_RE.findall(cell.owner) + [f"slot{slot}"]
        missing = [token for token in wanted if token not in cell.label]
        if missing:
            mismatched.append((cell.id, missing))
    assert mismatched == []


def test_every_finding_named_in_a_label_exists() -> None:
    """Green cells name findings too (C194's readonly battery); a typo there
    would point a later reader at nothing.  Inventory C-ids only: a G-row or an
    N-row is registered in LEDGER.md, which this deliberately does not read."""
    findings = known_findings()
    unknown = sorted({
        cid for cell in ALL_CELLS for cid in _CID_RE.findall(cell.label)
    } - findings)
    assert unknown == []


def test_every_owned_cell_is_a_strict_xfail() -> None:
    """``strict=True`` is what makes a flip cell a flip cell.

    A non-strict xfail whose expectation drifts to psh's behavior passes
    SILENTLY as an xpass: the cell still looks owned, still reads as red in the
    summary, and pins the defect. Nothing else in this module can see that, so
    it is checked against the parameter sets the runners actually receive: every
    owned cell carries exactly one xfail, it is strict, and its reason is the
    owner verbatim; a green cell carries none.
    """
    params = ([_param(c) for c in VALUE_CELLS + CHILD_CELLS + CWD_CELLS]
              + SPAWN_PARAMS)
    problems = []
    for param in params:
        cell = param.values[0]
        marks = [m for m in param.marks if m.name == "xfail"]
        if cell.owner is None:
            if marks:
                problems.append((cell.id, "green cell carries an xfail mark"))
            continue
        if len(marks) != 1:
            problems.append((cell.id, f"{len(marks)} xfail marks, expected 1"))
            continue
        if marks[0].kwargs.get("strict") is not True:
            problems.append((cell.id, "xfail is not strict"))
        if marks[0].kwargs.get("reason") != cell.owner:
            problems.append((cell.id, "xfail reason is not the owner"))
    assert problems == []


def test_flipping_a_cell_never_rewrites_its_expectation() -> None:
    """Deleting ``owner=`` is HOW a slot flips its cells, so it must change only
    the mark and the label's token — never what the cell demands.

    This helper once derived the verdict, the expected status and the expected
    diagnostic from ``owner``.  Flipping the nine G17 cells would then have
    rewritten them to demand psh's current WRONG behavior (rc 0, no diagnostic):
    they would have gone red at the flip like a normal cell, and the natural
    repair would have pinned the defect green while a correct slot 2.4 turned
    them red.  Every expectation-bearing helper that takes ``owner`` is checked
    here, because the failure is invisible in the cell table itself.
    """
    target, setup, var, p_refused, _p_allowed = _RO_TARGETS[0]

    def attr(owner):
        return _attr_cell("i", "integer", target, setup, var, p_refused,
                          refused=True, owner=owner)

    def cwd(owner):
        return _cwd_cell("probe", 'cd .', 'PWD=x\ngetcwd=x\n', owner=owner)

    for build, name in ((attr, "_attr_cell"), (cwd, "_cwd_cell")):
        owned, flipped = build("C043 → slot 1.4"), build(None)
        assert ((owned.script, owned.out, owned.rc, owned.err)
                == (flipped.script, flipped.out, flipped.rc, flipped.err)), (
            f"{name} derives part of its expectation from `owner`: flipping a "
            f"cell would change what it demands, not just who owns it"
        )


def test_a_green_cell_never_claims_a_slot() -> None:
    """A label carrying a `-slotN.M` token but no ``owner=`` reads like a flip
    cell in the report while running as an ordinary pass — the one way a cell
    could look owned and be flipped by nobody.  (The converse, an owner whose
    label omits its slot, is covered above.)"""
    claimed = [c.id for c in ALL_CELLS
               if c.owner is None and re.search(r"-slot\d\.\d+", c.label)]
    assert claimed == []


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
    ("G1 → slot 2.4", "a gate-triage row short a digit"),
    ("G170 → slot 2.4", "a gate-triage row with a digit too many"),
    ("g17 → slot 2.4", "a lowercased gate-triage row"),
    ("W1N2 → slot 1.18", "an N-row missing its hyphen"),
    ("W-N2 → slot 1.18", "an N-row missing its wave number"),
    ("W1-N → slot 1.18", "an N-row missing its number"),
    ("N2 → slot 1.18", "an N-row missing its wave prefix"),
])
def test_owner_validator_rejects_synthetic_offenders(reason: str, why: str) -> None:
    """Mutation check for the guard above: each of these MUST be refused."""
    assert owner_problem(reason, known_slots(), known_findings()) is not None, why


@pytest.mark.parametrize("reason", [
    "C043 → slot 1.4",
    "C093, C094 → slot 1.18",
    "C093,C094 → slot 1.18",
    "G17 → slot 2.4",
    "W1-N2 → slot 1.18",
    "C093, W1-N2 → slot 1.18",
])
def test_owner_validator_accepts_the_declared_shapes(reason: str) -> None:
    """The offender test is only meaningful if the rule accepts real reasons."""
    assert owner_problem(reason, known_slots(), known_findings()) is None
