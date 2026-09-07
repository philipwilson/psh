"""The executable round-trip corpus (C033, C231) — shared by two suites.

A shell that can print a program back (``declare -f``, ``--format``) owes an
EXECUTABLE round-trip contract: the printed text must re-parse to a program
that behaves the same. This module holds the corpus that contract is pinned
with, plus the script builders that run it, so the psh-only guard
(``tests/unit/visitor/test_executable_roundtrip.py``) and the bash
differential (``tests/conformance/bash/test_executable_roundtrip_conformance.py``)
agree on one list of rows instead of drifting apart.

The corpus is built around the spelling of a variable reference, because that
is where the contract was broken: brace expansion runs BEFORE parameter
expansion, so a bare ``$v{1,2}`` re-forms the names ``v1``/``v2`` while a
delimited ``${v}{1,2}`` stays ``${v}1``/``${v}2``. Rows therefore come in
pairs — a braced form and its bare twin — and the setup gives BOTH readings a
distinct value, so a serialization that picks the wrong one prints the wrong
answer instead of an empty string.

Rows are executed in BATCHES: one script defines every ``fN``, a driver runs
each and prints a marker plus its status, and :func:`split_rows` slices the
result back apart. That keeps the whole corpus to a handful of process spawns
while each row is still an individually named test.
"""

# Setup shared by every row.
SETUP = (
    "v=1; v1=A; v2=B; v3=C; va=P; vb=Q; x=X; x1=Q1; xb=BAD; xy=BADXY; "
    "vx=BADVX; v9=BAD9; v_z=BADUZ; vxy=BADVXY; vdq=BADDQ; "
    "y=Y; n=3; i=2; i1=BADI1; arr=(e0 e1 e2)"
)

# (row id, function body). Each body is placed in `fN() { ... }`.
CORPUS = [
    # --- the brace-expansion suffixes: the three shapes that fuse ---
    ("brace_num", "echo ${v}{1,2}"),
    ("brace_alpha", "echo ${v}{a,b}"),
    ("brace_range", "echo ${v}{1..3}"),
    # NEGATIVE CONTROL: a source-bare `$v{1,2}` must STAY bare. Re-bracing it
    # is the same defect with the sign flipped (v1/v2 would become 11/12).
    ("brace_bare", "echo $v{1,2}"),
    # --- name-char and digit suffixes ---
    ("name_char", "echo ${x}b"),
    ("name_bare", "echo $xb"),                       # negative control
    ("digit_after", "echo ${x}1"),
    ("subscript_suffix_braced", "echo ${x}[0]"),
    ("subscript_suffix_bare", "echo $x[0]"),
    # --- forms that are already brace-delimited by construction ---
    ("length", "echo ${#x}"),
    ("default", "echo ${x:-d}"),
    ("default_unset", "echo ${nosuch:-d}"),
    ("nested_default", "echo ${x:-${y}}"),
    ("suffix_strip", "echo ${x%X}${v}{1,2}"),
    # --- positional / special parameters ---
    ("pos_bare", "echo $1x"),
    ("pos_braced", "echo ${1}x"),
    ("at_braced", "echo ${@}"),
    ("at_bare", "echo $@"),
    ("star_quoted", 'echo "${*}"'),
    # --- QUOTED adjacency: the renderers close the gap the quotes left,
    #     either by merging same-quote regions or by dropping quotes, so the
    #     spelling has to anticipate a fusion the SOURCE was protected from ---
    ("dq_adjacent", 'echo "$v""x"'),
    ("dq_adjacent_digit", 'echo "$v""9"'),
    ("dq_adjacent_underscore", 'echo "$v""_z"'),
    ("dq_adjacent_chain", 'echo "$v""x""y"'),
    ("dq_adjacent_prefix", 'echo "a$v""x"'),
    ("dq_adjacent_mixed_quote", 'echo "$v""x"\'y\''),
    ("dq_adjacent_assign", 'z="$v""x"; echo "$z"'),
    ("dq_then_sq_literal", 'echo $v"dq"'),
    ("dq_adjacent_for", 'for k in "$v""x"; do echo "[$k]"; done'),
    ("dq_adjacent_case", 'case "$v""x" in 1x) echo m;; *) echo n;; esac'),
    ("dq_adjacent_dbl_bracket", '[[ "$v""x" == 1x ]] && echo yes || echo no'),
    ("dq_adjacent_array", 'a3=("$v""x"); echo "${a3[@]}"'),
    ("dq_adjacent_local", 'local w2="$v""x"; echo "$w2"'),
    ("dq_adjacent_redirect", 'echo hi > "$v""x"; cat 1x; rm -f 1x'),
    ("dq_adjacent_herestring", 'cat <<< "$v""x"'),
    # controls: adjacency that must NOT gain braces / must stay correct
    ("dq_adjacent_braced", 'echo "${v}""x"'),
    ("dq_adjacent_space", 'echo "$v"" x"'),
    ("dq_adjacent_dot", 'echo "$v"".txt"'),
    ("dq_then_bare", 'echo "$v"x'),
    ("dq_adjacent_param_op", 'echo "${x:-d}""b"'),
    ("dq_adjacent_cmdsub", 'echo "$(echo q)""b"'),
    ("dq_adjacent_arith", 'echo "$((1+1))""2"'),
    ("dq_adjacent_length", 'echo "${#x}""b"'),
    ("dq_adjacent_brace_suffix", 'echo "$v"{1,2}'),
    # --- quoting contexts ---
    ("dq_braced", 'echo "${x}"'),
    ("dq_braced_cat", 'echo "${x}"b'),
    ("sq_literal", "echo '${v}{1,2}'"),
    ("quoted_brace", 'echo ${v}"{1,2}"'),
    # --- adjacency ---
    ("two_bare", "echo $x$y"),
    ("two_braced", "echo ${x}${y}"),
    ("concat_around", "echo pre${v}{1,2}post"),
    ("brace_then_name", "echo ${v}{1,2}z"),
    # --- arithmetic ---
    ("arith", "echo $((n+1))"),
    ("arith_braced", "echo $(( ${n} + 1 ))"),
    # --- assignment, arrays ---
    ("assign_rhs", 'z=${v}{1,2}; echo "$z"'),
    ("local_var", 'local w=${v}{1,2}; echo "$w"'),
    ("array_elem", "echo ${arr[0]} ${arr[@]}"),
    ("array_init", 'a2=(${v}{1,2}); echo "${a2[@]}"'),
    # --- compound commands whose operands are Words ---
    ("for_list", 'for i in ${v}{1,2}; do echo "[$i]"; done'),
    ("case_subject", "case ${x}b in Xb) echo m;; *) echo n;; esac"),
    ("case_pattern", "case Xb in ${x}b) echo m;; *) echo n;; esac"),
    ("dbl_bracket", "[[ ${x}b == Xb ]] && echo yes || echo no"),
    ("dbl_bracket_brace", "[[ ${v}1 == 11 ]] && echo yes || echo no"),
    # --- heredoc / here-string bodies ---
    ("heredoc", "cat <<EOF\n${v}{1,2}\nEOF"),
    ("heredoc_quoted", "cat <<'EOF'\n${v}{1,2}\nEOF"),
    ("herestring", "cat <<< ${v}{1,2}"),
    # --- a function whose body defines a function ---
    ("nested_func", "g() { echo ${v}{1,2}; }; g"),
    # --- redirect target, pipeline, command substitution ---
    ("redirect_target", "echo hi > ${v}f; cat 1f; rm -f 1f"),
    ("pipeline", "echo ${v}{1,2} | cat"),
    ("cmdsub", "echo $(echo ${v}{1,2})"),
]

ROW_IDS = [row_id for row_id, _ in CORPUS]

# Markers the driver prints around each row. `@@ROW` cannot occur inside the
# status marker, so the split on it is unambiguous.
_ROW = "@@ROW"
_RC = "@@RC="
_END = "@@"


def _driver() -> str:
    """Print a row marker, run each function, print its status marker."""
    lines = []
    for i in range(len(CORPUS)):
        lines.append(f"printf '\\n{_ROW}%s{_END}\\n' {i}")
        lines.append(f"f{i}")
        lines.append(f"printf '{_RC}%s{_END}\\n' \"$?\"")
    return "\n".join(lines)


def _definitions() -> str:
    return "\n".join(f"f{i}() {{ {body}\n}}" for i, (_, body) in enumerate(CORPUS))


def direct_script() -> str:
    """Define every row's function and run it — the behavior reference."""
    return "\n".join([SETUP, "set -- posarg", _definitions(), _driver(), ""])


def roundtrip_script() -> str:
    """Redefine every function from its own ``declare -f`` text, then run it.

    This is the contract under test: ``eval "$(declare -f f)"`` must leave a
    function that does what the original did.
    """
    redefine = "\n".join(
        f'src{i}=$(declare -f f{i})\nunset -f f{i}\neval "$src{i}"'
        for i in range(len(CORPUS)))
    return "\n".join([SETUP, "set -- posarg", _definitions(), redefine,
                      _driver(), ""])


def split_rows(stdout: str):
    """Marker-split a batched pass into ``{row_id: (output, status)}``."""
    rows = {}
    for chunk in stdout.split(f"\n{_ROW}")[1:]:
        index, _, rest = chunk.partition(f"{_END}\n")
        body, _, tail = rest.rpartition(_RC)
        rows[CORPUS[int(index)][0]] = (body, tail.split(_END)[0])
    return rows
