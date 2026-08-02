"""Operand field IR conformance (remediation slot 3.3, HIGH-6).

A value operand (``${x:-W}``, ``${x:+W}``, ``${x:=W}``, ``${x:?W}`` and the
non-colon twins) expands to a FIELD VECTOR. This suite pins the four
properties that vector exists to carry, each measured against live bash:

* **field preservation** — the fields of a ``"$@"`` inside the operand stay
  apart (the HIGH-6 signature; the operator/quoting/shape matrix lives in
  ``test_subscript_keying_conformance.py::test_operand_at_preserves_fields``);
* **the empty-field representation** — "no fields" and "one empty field" are
  different values, distinguishable only because the IR is not a string;
* **terminal scalar projection** — the contexts where bash itself demands one
  string, and the SEPARATOR it uses there;
* **the untriggered conditional** — it yields the parameter's own view, never
  a synthesized empty scalar.

Field counts are observed with a counter function rather than
``printf '<%s>'``: ``printf`` renders zero fields and one empty field
IDENTICALLY (both produce ``<>``), which would make the representation pins
vacuous. Observability is an axis, and this suite picks the observer that can
tell the two apart.
"""
import pytest
from shell_oracle import is_comparable, run_bash, run_psh

#: Prints ``n=<count>`` then one ``[text]`` per field.
COUNT = ('count() { printf "n=%d" "$#"; for a in "$@"; do printf " [%s]" "$a"; '
         'done; printf "\\n"; }\n')


def _run(cmd):
    script = COUNT + cmd
    p = run_psh(['-c', script], timeout=15)
    b = run_bash(['-c', script], timeout=15)
    assert is_comparable(p) and is_comparable(b), (p, b)
    return p, b


def _agree(cmd, expected):
    """psh == bash, AND bash == the recorded literal (so a shared regression
    in both shells cannot pass silently)."""
    p, b = _run(cmd)
    assert b.stdout == expected, f"bash oracle moved: {b.stdout!r}"
    assert p.stdout == b.stdout
    assert p.returncode == b.returncode


# ---------------------------------------------------------------------------
# 1. The empty-field representation: "no fields" vs "one empty field"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    # THE PAIR. These two differ ONLY in the outer quoting, and they are the
    # reason the operand result cannot be a string: one must vanish, the other
    # must survive as an empty argument.
    ('unset x; set --; count ${x:-"$@"}', 'n=0\n'),
    ('unset x; set --; count "${x:-"$@"}"', 'n=1 []\n'),
    # An EXPLICIT empty operand is one empty field in both quote states — it
    # is not the same thing as an operand that expanded to nothing.
    ('unset x; count ${x:-""}', 'n=1 []\n'),
    ('unset x; count "${x:-""}"', 'n=1 []\n'),
    ("unset x; count ${x:-''}", 'n=1 []\n'),
    # An EMPTY operand word elides when unquoted, survives when quoted.
    ('unset x; count ${x:-}', 'n=0\n'),
    ('unset x; count "${x:-}"', 'n=1 []\n'),
    # An empty $@ is a no-op on field BOUNDARIES: adjacent literals join.
    ('unset x; set --; count pre"${x:-"$@"}"post', 'n=1 [prepost]\n'),
    ('unset x; set --; count "${x:+"$@"}"', 'n=1 []\n'),
    # An EMPTY POSITIONAL is a real field and must survive.
    ('unset x; set -- "" b; count "${x:-"$@"}"', 'n=2 [] [b]\n'),
    ('unset x; set -- "" ""; count "${x:-"$@"}"', 'n=2 [] []\n'),
])
def test_empty_field_representation(cmd, expected):
    _agree(cmd, expected)


# ---------------------------------------------------------------------------
# 2. Terminal scalar projection: where bash demands ONE string
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    ('unset x; set -- a b; v=${x:-"$@"}; count "$v"', 'n=1 [a b]\n'),
    ('unset x; set -- a b; v=pre; v+=${x:-"$@"}; count "$v"',
     'n=1 [prea b]\n'),
    ('unset x; set -- a b; declare v=${x:-"$@"}; count "$v"', 'n=1 [a b]\n'),
    ('unset x; set -- a b; export v=${x:-"$@"}; count "$v"', 'n=1 [a b]\n'),
    ('unset x; set -- a b; declare -a c; c[0]=${x:-"$@"}; count "${c[0]}"',
     'n=1 [a b]\n'),
    ('unset x; set -- a b; declare -A h; h[${x:-"$@"}]=v; count "${!h[@]}"',
     'n=1 [a b]\n'),
    ('unset x; set -- a b; cat <<< ${x:-"$@"}', 'a b\n'),
    ('unset x; set -- a b; [[ ${x:-"$@"} == "a b" ]] && echo eq || echo ne',
     'eq\n'),
    ('unset x; set -- a b; [[ "a b" == ${x:-"$@"} ]] && echo eq || echo ne',
     'eq\n'),
    ('unset x; set -- a b; v="a b c"; count "${v#${x:-"$@"}}"', 'n=1 [ c]\n'),
    ('unset x; set -- a b; v=Q; count "${v/Q/${x:-"$@"}}"', 'n=1 [a b]\n'),
    ('unset x; set -- 1 2; y=2; echo $(( ${x:-1} + y ))', '3\n'),
])
def test_terminal_scalar_consumers(cmd, expected):
    """Each context here needs ONE string in bash, so the field vector is
    projected. Every row is the bash measurement, not an assumption."""
    _agree(cmd, expected)


@pytest.mark.parametrize('ifs', ['', 'IFS=:;', 'IFS=;', 'IFS=XY;'])
def test_scalar_projection_separator_is_space_not_ifs(ifs):
    """The projection joins with a literal SPACE regardless of IFS.

    ``$*`` is the contrast and the control: it joins with IFS[0] BEFORE the
    operand IR sees it, so it yields one field whose separator DOES track IFS.
    Pinning both in one test keeps the two mechanisms from being conflated.
    """
    _agree(f'unset x; set -- a b; {ifs} v=${{x:-"$@"}}; count "$v"',
           'n=1 [a b]\n')


def test_star_operand_separator_does_track_ifs():
    """The contrast row for the test above (AXIS: which mechanism joins)."""
    _agree('unset x; set -- a b; IFS=:; v=${x:-"$*"}; count "$v"',
           'n=1 [a:b]\n')


# ---------------------------------------------------------------------------
# 3. ``:=`` / ``=``: the assignment is terminal in BASH, not just in psh
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    # EMIT face: quoted -> the stored scalar as one field; unquoted -> that
    # same scalar under ordinary value semantics, so it re-splits.
    ('unset x; set -- a b; count "${x:="$@"}"', 'n=1 [a b]\n'),
    ('unset x; set -- a b; count ${x:="$@"}', 'n=2 [a] [b]\n'),
    ('unset x; set -- a b; count "${x="$@"}"', 'n=1 [a b]\n'),
    ('unset x; set -- "a 1" b; count "${x:="$@"}"', 'n=1 [a 1 b]\n'),
    # STORE face: what actually landed in the variable.
    ('unset x; set -- a b; : "${x:="$@"}"; count "$x"', 'n=1 [a b]\n'),
    ('unset x; set -- "a 1" b; : "${x:="$@"}"; count "$x"', 'n=1 [a 1 b]\n'),
    ('unset a x; a=(p "q 2"); : "${x:="${a[@]}"}"; count "$x"',
     'n=1 [p q 2]\n'),
    # The operand's splitting PROTECTION does not survive the store either.
    ('unset x; count ${x:=a\\ b}', 'n=2 [a] [b]\n'),
    ('unset x; count ${x:-a\\ b}', 'n=1 [a b]\n'),
])
def test_assignment_operator_is_a_terminal_projection(cmd, expected):
    """``${x:=W}`` STORES a scalar and then expands to it.

    This is bash's own semantics, not a psh limitation: a shell variable holds
    a string. Making ``:=`` field-preserving would be a REGRESSION, and the
    ``${x:=a\\ b}`` / ``${x:-a\\ b}`` pair above is what detects it — the two
    differ ONLY in whether the value round-trips through the variable.
    """
    _agree(cmd, expected)


# ---------------------------------------------------------------------------
# 4. The untriggered conditional yields the VIEW, not an empty scalar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    # THE cell: an array holding ONE EMPTY element. Unset and empty arrays
    # cannot distinguish "the view" from "a synthesized empty" (both are zero
    # fields); this one can.
    ('unset a; count "${a[@]:+X}"', 'n=0\n'),
    ('a=(); count "${a[@]:+X}"', 'n=0\n'),
    ('a=(""); count "${a[@]:+X}"', 'n=1 []\n'),
    # The NON-COLON twin tests SET-ness, not null-ness: a=("") IS set, so the
    # alternate fires. Same array, opposite outcome — the row that keeps the
    # colon/non-colon axis honest.
    ('a=(""); count "${a[@]+X}"', 'n=1 [X]\n'),
    ('unset a; count "${a[@]+X}"', 'n=0\n'),
    # Trigger LOGIC is unchanged: the JOINED view is what is tested for null,
    # so two empty elements join to " ", are non-null, and DO fire.
    ('a=("" ""); count "${a[@]:+X}"', 'n=1 [X]\n'),
    ('a=(z w); count "${a[@]:+X}"', 'n=1 [X]\n'),
    # The positional twin of a=("").
    ('set -- ""; count "${@:+X}"', 'n=1 []\n'),
    ('set --; count "${@:+X}"', 'n=0\n'),
    ('set -- "" ""; count "${@:+X}"', 'n=1 [X]\n'),
    # The [*] view stays scalar-like.
    ('a=(""); count "${a[*]:+X}"', 'n=1 []\n'),
    # Scalar controls: unchanged by this rule.
    ('unset x; count "${x:+X}"', 'n=1 []\n'),
    ('x=; count "${x:+X}"', 'n=1 []\n'),
    ('x=S; count "${x:+X}"', 'n=1 [X]\n'),
])
def test_untriggered_conditional_returns_the_view(cmd, expected):
    _agree(cmd, expected)


# ---------------------------------------------------------------------------
# 4b. The ARRAY-VIEW operand-content family (round-1 blocker B2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    ('unset x; a=("m n" o); count "${x:-"${a[@]}"}"', 'n=2 [m n] [o]\n'),
    ('unset x; a=("m n" o); count ${x:-"${a[@]}"}', 'n=2 [m n] [o]\n'),
    ('unset x; a=("m n" o); count "${x:-${a[@]}}"', 'n=2 [m n] [o]\n'),
    ('x=S; a=("m n" o); count "${x:+"${a[@]}"}"', 'n=2 [m n] [o]\n'),
    ('unset x; a=("m n" o); count "${x-"${a[@]}"}"', 'n=2 [m n] [o]\n'),
    # Associative KEYS are a view too.
    ('unset x; declare -A h; h[k1]=1; h["k 2"]=2; count "${x:-"${!h[@]}"}"',
     'n=2 [k1] [k 2]\n'),
    # A SLICED view keeps its own field boundaries.
    ('unset x; a=(p "q r" s); count "${x:-"${a[@]:1}"}"', 'n=2 [q r] [s]\n'),
    # Boundaries land correctly when the view is flanked by literals.
    ('unset x; a=("m n" o); count "A${x:-"${a[@]}"}Z"', 'n=2 [Am n] [oZ]\n'),
])
def test_array_view_as_operand_content_keeps_fields(cmd, expected):
    """An array VIEW inside a value operand produces fields, like ``"$@"``.

    Round-1 B2: this whole family moved base -> tip (one joined field -> the
    field vector, matching bash) with NO pin detecting it, and a mutation
    disabling the view branch left every relevant test green. These rows close
    that gap; ``test_m8_lock_view_operand_content_is_a_producer`` is the
    matching mutation lock.
    """
    _agree(cmd, expected)


def test_star_view_as_operand_content_stays_one_field():
    """CONTROL for the family above: a ``[*]`` view joins its OWN elements
    before the operand ever sees it, so it is ONE field in bash, at base and
    at tip alike. Without this row the family could be satisfied by "make
    every view produce fields", which would be wrong."""
    _agree('unset x; a=("m n" o); count "${x:-"${a[*]}"}"', 'n=1 [m n o]\n')


# ---------------------------------------------------------------------------
# 4c. The REDIRECT TARGET (round-1 blockers B1/B6): CLOSED IN SLOT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('script', [
    'unset x; set -- f1 f2; echo hi > ${x:-"$@"}',
    'unset x; set -- f1 f2; echo hi > "${x:-"$@"}"',
    'unset x; a=(f1 f2); echo hi > ${x:-"${a[@]}"}',
    'unset x; set -- f1 f2; cat < ${x:-"$@"}',
])
def test_multifield_redirect_target_is_ambiguous(script, tmp_path):
    """A multi-field operand as a redirect target is an AMBIGUOUS REDIRECT.

    Round-1 B1/B6. At base psh silently created ONE file literally named
    ``f1 f2`` and exited 0; at tip the operand is a field vector, the redirect
    sees two fields, and psh reports bash's own diagnostic and fails —
    matching bash in message form AND exit status. This consumer was CLOSED
    IN SLOT; the ledger's earlier "pre-existing, unchanged" record of it was
    wrong on both counts and is corrected.

    Compared with the program-name prefix normalised, since that legitimately
    differs between the two shells.
    """
    import re as _re
    p = run_psh(['-c', script], cwd=str(tmp_path), timeout=15)
    b = run_bash(['-c', script], cwd=str(tmp_path), timeout=15)
    assert is_comparable(p) and is_comparable(b), (p, b)

    def norm(text):
        return _re.sub(r'^[^:]*: line \d+: ', '', text.strip())

    assert 'ambiguous redirect' in norm(b.stderr), \
        f"bash oracle moved: {b.stderr!r}"
    assert norm(p.stderr) == norm(b.stderr)
    assert p.returncode == b.returncode != 0
    assert sorted(q.name for q in tmp_path.iterdir()) == []


def test_single_field_redirect_target_still_works(tmp_path):
    """AGREEMENT CONTROL for the rows above: a ONE-field operand target is an
    ordinary redirect and must keep working. Without this, those rows could be
    satisfied by making every operand target ambiguous."""
    script = 'unset x; set -- solo; echo hi > ${x:-"$@"}; echo "rc=$?"'
    p = run_psh(['-c', script], cwd=str(tmp_path), timeout=15)
    b = run_bash(['-c', script], cwd=str(tmp_path), timeout=15)
    assert is_comparable(p) and is_comparable(b), (p, b)
    assert p.stdout == b.stdout == 'rc=0\n'
    assert (tmp_path / 'solo').read_text() == 'hi\n'


# ---------------------------------------------------------------------------
# 5. NESTED operands — a field vector inside a field vector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cmd,expected', [
    # THE cell the static guard caught red-handed: an unruled projection while
    # mapping view members re-flattened a nested TRIGGERED operand. The inner
    # ${a[@]:-"$@"} is itself a field vector, and its fields must survive
    # being spliced into the outer one.
    ('unset x a; set -- p "q 2"; count "${x:-${a[@]:-"$@"}}"',
     'n=2 [p] [q 2]\n'),
    ('unset x a; set -- p "q 2"; count ${x:-${a[@]:-"$@"}}',
     'n=2 [p] [q 2]\n'),
    # Plain nesting through a scalar default.
    ('unset x y; set -- "a 1" b; count "${x:-${y:-"$@"}}"', 'n=2 [a 1] [b]\n'),
    ('unset x y; set -- "a 1" b; count ${x:-${y:-"$@"}}', 'n=2 [a 1] [b]\n'),
    # THREE levels deep.
    ('unset x y z; set -- "a 1" b; count "${x:-${y:-${z:-"$@"}}}"',
     'n=2 [a 1] [b]\n'),
    # Nested operand whose own quoting must survive the outer level.
    # In QUOTED outer context the nested single quotes are LITERAL characters
    # (DQ rules propagate into the nested operand); unquoted they are removed.
    # One field either way — the quoting differs, the field count does not.
    ("unset x z; count \"${x:-${z:-'p q'}}\"", "n=1 ['p q']\n"),
    ("unset x z; count ${x:-${z:-'p q'}}", 'n=1 [p q]\n'),
    # Nested alternate, and a nested [*] view (which joins its OWN elements
    # but must not join a triggered operand's fields).
    ('y=set; set -- "a 1" b; unset x; count "${x:-${y:+"$@"}}"',
     'n=2 [a 1] [b]\n'),
    ('unset x a; set -- p "q 2"; count "${x:-${a[*]:-"$@"}}"',
     'n=2 [p] [q 2]\n'),
    # Nested inside a MIXED operand: boundaries land where bash puts them.
    ('unset x y; set -- a b; count "${x:-pre${y:-"$@"}post}"',
     'n=2 [prea] [bpost]\n'),
])
def test_nested_operand_fields_survive(cmd, expected):
    """A nested value operand contributes its OWN field vector.

    Required by R3.3: this family is where the projection guard caught a real
    re-flatten in the change that introduced it, so it is pinned as equality
    rows rather than left to the guard alone.
    """
    _agree(cmd, expected)


# ---------------------------------------------------------------------------
# 6. M8 regression locks — the fixed blocker must not be re-introducible
# ---------------------------------------------------------------------------

def test_m8_lock_operand_at_is_not_flattened():
    """M8 LOCK #1 — restoring the join-at-operand-expansion must fail HERE.

    The subject shape is deliberate: with ``set -- a b`` in unquoted outer
    context a space-join is undone by re-splitting and the flatten is
    INVISIBLE. A positional containing a space makes the join observable, so
    this row detects the defect's actual mechanism rather than its shadow.
    """
    _agree('unset x; set -- "a 1" "b 2"; count "${x:-"$@"}"',
           'n=2 [a 1] [b 2]\n')
    _agree('unset x; set -- "a 1" "b 2"; count ${x:-"$@"}',
           'n=2 [a 1] [b 2]\n')


def test_m8_lock_assignment_still_projects():
    """M8 LOCK #2 — making ``:=`` field-preserving must fail HERE.

    The mirror of lock #1: that one fails if the fields are LOST, this one
    fails if they are WRONGLY KEPT. A change that simply routes every operand
    through the field vector trips this immediately.
    """
    _agree('unset x; set -- "a 1" b; count "${x:="$@"}"', 'n=1 [a 1 b]\n')
    _agree('unset x; set -- "a 1" b; : "${x:="$@"}"; count "$x"',
           'n=1 [a 1 b]\n')


def test_m8_lock_view_operand_content_is_a_producer():
    """M8 LOCK #4 (round-1 B2) — disabling the operator-less array-VIEW branch
    of ``_operand_dollar_fields`` must fail HERE.

    The verifier's isolating mutation did exactly that and left every relevant
    test green: the view family had moved to bash with nothing watching it.
    The subject carries an embedded space so the join is observable, and the
    ``[*]`` control is asserted in the same test so a mutation that makes ALL
    views produce fields fails too — the lock bites in BOTH directions.
    """
    _agree('unset x; a=("m n" o); count "${x:-"${a[@]}"}"', 'n=2 [m n] [o]\n')
    _agree('unset x; a=("m n" o); count "${x:-"${a[*]}"}"', 'n=1 [m n o]\n')


def test_m8_lock_redirect_target_arity(tmp_path):
    """M8 LOCK #5 (round-1 B1/B6) — losing the field vector at the redirect
    target must fail HERE.

    If the operand flattens again, the target becomes ONE field named
    ``f1 f2``, the redirect succeeds, and a file appears. Both halves are
    asserted: the diagnostic AND the absence of the file.
    """
    import re as _re
    script = 'unset x; set -- f1 f2; echo hi > ${x:-"$@"}'
    p = run_psh(['-c', script], cwd=str(tmp_path), timeout=15)
    assert p.returncode != 0
    assert 'ambiguous redirect' in _re.sub(r'^[^:]*: line \d+: ', '',
                                          p.stderr.strip())
    assert sorted(q.name for q in tmp_path.iterdir()) == []


def test_m8_lock_empty_field_distinction_survives():
    """M8 LOCK #3 — collapsing "no fields" into "one empty field" (or the
    reverse) must fail HERE. Both directions in one test so neither
    simplification can pass."""
    _agree('unset x; set --; count ${x:-"$@"}', 'n=0\n')
    _agree('unset x; set --; count "${x:-"$@"}"', 'n=1 []\n')
