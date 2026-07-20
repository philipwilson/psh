"""Drift-lock guards for the ordered RedirectProgram (campaign R1 triad, part c).

Two invariants, each with a synthetic offender this file RUNS:

1. **Sole ordered chokepoint.** Every io_redirect dispatch site that applies a
   command's redirects walks one `RedirectProgram` via `apply_in_order`; the
   program is produced only by `RedirectPlanner.plan_program`. No site
   re-implements an ordered loop (that is where the #20 H4 deferral lived).

2. **C1 structural origin.** No code in `psh/io_redirect/` sniffs an expanded
   target STRING for process-substitution syntax (`<(` / `>(`).  Process
   substitution is created only from a structural `ProcessSubstitution` AST
   node, so expanded redirect text can never be reclassified as syntax.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
IOREDIR = REPO_ROOT / "psh" / "io_redirect"

#: The dispatch functions that apply a command's redirects — each must walk a
#: RedirectProgram via apply_in_order (the one ordered, immediate applicator).
DISPATCH_SITES = {
    "psh/io_redirect/manager.py": {
        "setup_builtin_redirections", "setup_child_redirections"},
    "psh/io_redirect/file_redirect.py": {
        "_apply_redirections", "apply_permanent_redirections"},
}


def _funcdef(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls_attr(node, attr):
    """True if *node*'s subtree calls ``<x>.<attr>(...)`` (closures included)."""
    for n in ast.walk(node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == attr):
            return True
    return False


def test_every_dispatch_site_walks_apply_in_order():
    missing = []
    for rel, funcs in DISPATCH_SITES.items():
        tree = ast.parse((REPO_ROOT / rel).read_text(), filename=rel)
        for fname in funcs:
            fn = _funcdef(tree, fname)
            assert fn is not None, f"{rel}: {fname} not found (renamed?)"
            if not _calls_attr(fn, "apply_in_order"):
                missing.append(f"{rel}:{fname}")
    assert not missing, (
        "these redirect-dispatch sites no longer walk a RedirectProgram via "
        "apply_in_order — an ad-hoc ordered loop can reintroduce the H4 "
        "deferral:\n" + "\n".join(missing))


def test_scanner_fires_on_a_site_that_skips_apply_in_order():
    # Synthetic offender: a dispatch function with a bare apply loop.
    src = (
        "def setup_builtin_redirections(self, command):\n"
        "    for r in command.redirects:\n"
        "        self.file_redirector.apply_fd_plan(r)\n")
    fn = _funcdef(ast.parse(src), "setup_builtin_redirections")
    assert not _calls_attr(fn, "apply_in_order"), (
        "the scanner must flag a dispatch function that omits apply_in_order")


def test_redirect_program_has_one_producer():
    """`RedirectProgram(...)` / `RedirectOp(...)` are constructed in production
    only by `plan_program` (planner.py) — plus the type module itself."""
    prod = {"psh/io_redirect/planner.py", "psh/io_redirect/redirect_program.py"}
    offenders = []
    for path in sorted((REPO_ROOT / "psh").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in prod:
            continue
        tree = ast.parse(path.read_text(), filename=rel)
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ("RedirectProgram", "RedirectOp")):
                offenders.append(f"{rel}:{n.lineno}: {n.func.id}(...)")
    assert not offenders, (
        "RedirectProgram/RedirectOp constructed outside the planner — "
        "plan_program is the sole producer:\n" + "\n".join(offenders))


# ---- C1: no expanded string is re-parsed as process-substitution syntax ----

PROCSUB_PREFIXES = ("<(", ">(")


def _sniffs_procsub_prefix(tree):
    """[(lineno, snippet)] for `<expr>.startswith('<('|'>(')` or `'<('|'>(' in
    <expr>` — the resurrected C1 string-reinterpretation shape."""
    hits = []
    for n in ast.walk(tree):
        # x.startswith('<(') / x.startswith('>(')
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "startswith"):
            for a in n.args:
                if isinstance(a, ast.Constant) and a.value in PROCSUB_PREFIXES:
                    hits.append((n.lineno, f"startswith({a.value!r})"))
        # '<(' in x / '>(' in x
        if isinstance(n, ast.Compare) and len(n.ops) == 1 \
                and isinstance(n.ops[0], ast.In) \
                and isinstance(n.left, ast.Constant) \
                and n.left.value in PROCSUB_PREFIXES:
            hits.append((n.lineno, f"{n.left.value!r} in ..."))
    return hits


def test_no_procsub_prefix_sniffing_in_io_redirect():
    offenders = []
    for path in sorted(IOREDIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, snippet in _sniffs_procsub_prefix(
                ast.parse(path.read_text(), filename=rel)):
            offenders.append(f"{rel}:{lineno}: {snippet}")
    assert not offenders, (
        "expanded text is being sniffed for process-substitution syntax "
        "(#20 C1 resurrection) — procsub must come from a structural AST "
        "node only:\n" + "\n".join(offenders))


def test_scanner_fires_on_procsub_string_reinterpretation():
    # Synthetic offender: the exact resurrected bug shape (both spellings).
    off1 = "def plan(self, r):\n    if target.startswith('>('):\n        make_procsub(target)\n"
    assert _sniffs_procsub_prefix(ast.parse(off1)), \
        "must flag startswith('>(')"
    off2 = "x = '<(' in expanded_target\n"
    assert _sniffs_procsub_prefix(ast.parse(off2)), "must flag \"'<(' in ...\""


def test_planner_procsub_branch_is_gated_on_the_structural_node():
    """`plan` resolves a procsub resource ONLY inside the
    `redirect_procsub_node(...) is not None` branch (the structural gate)."""
    tree = ast.parse((REPO_ROOT / "psh/io_redirect/planner.py").read_text())
    plan = _funcdef(tree, "plan")
    assert plan is not None
    src = ast.get_source_segment(
        (REPO_ROOT / "psh/io_redirect/planner.py").read_text(), plan)
    assert "redirect_procsub_node" in src
    assert "resolve_procsub_resource" in src
    # The resource resolution must be reachable only under the structural gate:
    assert not _sniffs_procsub_prefix(plan), (
        "planner.plan sniffs an expanded string for procsub syntax")


# === Q2 family 5: redirect target/flag re-derivation ==========================
#
# Two single-authority redirect facts, widened / added by Q2:
#
#  (A) TARGET re-derivation from a string — C1, tree-wide. Process substitution
#      is created ONLY from a structural `ProcessSubstitution` AST node; no code
#      ANYWHERE re-reads an expanded target string for `<(` / `>(` syntax. R1
#      already guarded this inside psh/io_redirect/; Q2 widens the same scan to
#      the WHOLE tree (a resurrection could hide in expansion/ or executor/).
#
#  (B) FLAG re-derivation of the self-dup rule. bash's `n>&n` leniency (a dup
#      whose source and target fd coincide POST-RESOLUTION is an unconditional
#      success no-op) is a subtle fd-flag rule the R1 bounce proved dangerous
#      when re-derived. It lives in ONE predicate, `redirect_program.is_self_dup`;
#      the `<x>.dup_fd == <y>.fd` comparison shape must appear nowhere else.

PSH = REPO_ROOT / "psh"


def _sniffs_procsub_prefix_tree_wide():
    offenders = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, snippet in _sniffs_procsub_prefix(
                ast.parse(path.read_text(), filename=rel)):
            offenders.append(f"{rel}:{lineno}: {snippet}")
    return offenders


def test_no_procsub_prefix_sniffing_anywhere():
    """No production module re-reads an expanded string for process-sub syntax
    (C1 structural-origin, widened tree-wide by Q2)."""
    offenders = _sniffs_procsub_prefix_tree_wide()
    assert not offenders, (
        "expanded text sniffed for process-substitution syntax (#20 C1) OUTSIDE "
        "io_redirect — procsub must come from a structural ProcessSubstitution "
        "AST node only:\n" + "\n".join(offenders))


# --- (B) self-dup single authority ------------------------------------------

SELF_DUP_AUTHORITY = "psh/io_redirect/redirect_program.py"  # owns is_self_dup


def _finds_self_dup_comparison(tree):
    """[(lineno, snippet)] for the `<x>.dup_fd == <y>.fd` self-dup rule shape
    (either operand order), the fd-flag rule re-derivation to detect."""
    hits = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Compare) and len(n.ops) == 1
                and isinstance(n.ops[0], ast.Eq)):
            continue
        sides = [n.left] + n.comparators
        attrs = {s.attr for s in sides if isinstance(s, ast.Attribute)}
        if "dup_fd" in attrs and "fd" in attrs:
            hits.append((n.lineno, ast.unparse(n)))
    return hits


def test_self_dup_rule_has_one_authority():
    """The `n>&n` self-dup comparison exists ONLY in redirect_program.is_self_dup;
    every dup path consults `is_self_dup`, never re-derives the rule."""
    offenders = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == SELF_DUP_AUTHORITY:
            continue
        for lineno, snippet in _finds_self_dup_comparison(
                ast.parse(path.read_text(), filename=rel)):
            offenders.append(f"{rel}:{lineno}: {snippet}")
    assert not offenders, (
        "the self-dup (n>&n) fd rule is re-derived outside redirect_program."
        "is_self_dup — call is_self_dup(redirect) instead:\n" + "\n".join(offenders))


def test_self_dup_authority_still_owns_the_rule():
    """Shrink-only sanity: the authority file still contains the rule (so the
    guard is not silently vacuous)."""
    tree = ast.parse((REPO_ROOT / SELF_DUP_AUTHORITY).read_text())
    assert _finds_self_dup_comparison(tree), (
        "is_self_dup no longer contains the dup_fd==fd rule — the authority "
        "moved; update SELF_DUP_AUTHORITY")


def test_offender_self_dup_reimplementation_is_flagged():
    """SYNTHETIC OFFENDER: re-deriving the self-dup rule elsewhere is caught
    (both operand orders)."""
    off1 = "def apply(r):\n    if r.dup_fd == r.fd:\n        return\n"
    off2 = "def apply(r):\n    if redirect.fd == redirect.dup_fd:\n        return\n"
    assert _finds_self_dup_comparison(ast.parse(off1))
    assert _finds_self_dup_comparison(ast.parse(off2))


def test_offender_procsub_sniff_flagged_tree_wide():
    """SYNTHETIC OFFENDER: procsub string sniffing anywhere is caught by the
    tree-wide scan predicate."""
    off = "def resolve(t):\n    if t.startswith('<('):\n        return make(t)\n"
    assert _sniffs_procsub_prefix(ast.parse(off))
