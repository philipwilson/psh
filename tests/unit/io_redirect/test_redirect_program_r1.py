"""R1: the typed, source-ordered RedirectProgram and the C1 structural origin.

Representation invariants (campaign R1 triad, part a) plus the C1 structural
guard: expanded redirect text is NEVER reclassified as process-substitution
syntax — the procsub decision comes from the Word AST, not from sniffing an
expanded string.
"""
from psh.ast_nodes import Redirect
from psh.io_redirect.redirect_program import (
    RedirectOp,
    RedirectOpKind,
    RedirectProgram,
    classify_redirect,
)


def _r(type_, **kw):
    return Redirect(type=type_, target=kw.pop("target", None), **kw)


# ---- classify_redirect: one kind per operator, computed once ----

def test_classify_covers_every_operator():
    cases = {
        RedirectOpKind.OPEN_FILE: [_r("<", target="f"), _r("<>", target="f"),
                                   _r(">", target="f"), _r(">>", target="f"),
                                   _r(">|", target="f")],
        RedirectOpKind.HERE_INPUT: [_r("<<", target="E", heredoc_content=""),
                                    _r("<<-", target="E", heredoc_content=""),
                                    _r("<<<", target="w")],
        RedirectOpKind.DUP_FD: [_r(">&", fd=2, dup_fd=1),
                                _r("<&", fd=0, dup_fd=3),
                                _r(">&", fd=3, dup_fd=1, move=True)],
        RedirectOpKind.CLOSE_FD: [_r(">&-", fd=1), _r("<&-", fd=0)],
    }
    for kind, redirects in cases.items():
        for r in redirects:
            assert classify_redirect(r) is kind, (r.type, kind)


def test_classify_combined_and_var_fd():
    assert classify_redirect(_r("&>", target="f", combined=True)) \
        is RedirectOpKind.COMBINED
    # var_fd is orthogonal to the operator but dispatched as one op.
    assert classify_redirect(_r(">", target="f", var_fd="v")) \
        is RedirectOpKind.VAR_FD
    assert classify_redirect(_r(">&-", fd=None, var_fd="v")) \
        is RedirectOpKind.VAR_FD


# ---- RedirectProgram: source order + one immediate applicator ----

def test_plan_program_preserves_source_order():
    from psh.shell import Shell
    planner = Shell().io_manager.file_redirector.planner
    reds = [_r(">", target="a"), _r(">&", fd=2, dup_fd=1), _r(">&-", fd=1)]
    program = planner.plan_program(reds)
    assert [op.redirect for op in program.ops] == reds
    assert [op.kind for op in program.ops] == [
        RedirectOpKind.OPEN_FILE, RedirectOpKind.DUP_FD,
        RedirectOpKind.CLOSE_FD]


def test_apply_in_order_is_strictly_left_to_right():
    ops = [RedirectOp(RedirectOpKind.OPEN_FILE, _r(">", target=str(i)))
           for i in range(5)]
    program = RedirectProgram(ops)
    seen = []
    program.apply_in_order(lambda op: seen.append(op.redirect.target))
    assert seen == ["0", "1", "2", "3", "4"]


def test_apply_in_order_applies_each_before_the_next_no_deferral():
    # The no-deferral invariant (#20 H4): a CLOSE op's effect is visible to the
    # NEXT op's handler. A close-then-dup program must let the dup observe the
    # already-closed fd — never a batched-to-the-end close.
    fds = {3: "open"}
    observations = []
    program = RedirectProgram([
        RedirectOp(RedirectOpKind.CLOSE_FD, _r(">&-", fd=3)),
        RedirectOp(RedirectOpKind.DUP_FD, _r(">&", fd=4, dup_fd=3)),
    ])

    def handler(op):
        if op.kind is RedirectOpKind.CLOSE_FD:
            fds[op.redirect.fd] = "closed"
        elif op.kind is RedirectOpKind.DUP_FD:
            # By the time the dup runs, the earlier close is already applied.
            observations.append(fds[op.redirect.dup_fd])

    program.apply_in_order(handler)
    assert observations == ["closed"], (
        "the dup must see the prior close's effect — no deferral")


def test_a_deferring_applicator_would_reorder_proving_immediacy_matters():
    # Synthetic resurrection of the H4 deferral: batch CLOSE ops to the end.
    # It observes 'open' where apply_in_order observes 'closed' — this is
    # exactly the behavior difference the immediate applicator eliminates.
    fds = {3: "open"}
    observations = []
    ops = [
        RedirectOp(RedirectOpKind.CLOSE_FD, _r(">&-", fd=3)),
        RedirectOp(RedirectOpKind.DUP_FD, _r(">&", fd=4, dup_fd=3)),
    ]

    def deferring_apply(op):
        if op.kind is RedirectOpKind.DUP_FD:
            observations.append(fds[op.redirect.dup_fd])

    for op in ops:                       # opens/dups first
        if op.kind is not RedirectOpKind.CLOSE_FD:
            deferring_apply(op)
    for op in ops:                       # closes deferred to the end (the bug)
        if op.kind is RedirectOpKind.CLOSE_FD:
            fds[op.redirect.fd] = "closed"
    assert observations == ["open"], (
        "the deferral resurrection dups a still-open fd — the bug R1 removes")


# ---- C1: structural origin — expanded text is never procsub syntax ----

def _redirect_from(shell, script):
    from psh.ast_nodes import SimpleCommand
    from psh.lexer import tokenize
    from psh.parser import parse

    def find_simple(n):
        if isinstance(n, SimpleCommand):
            return n
        for attr in ("statements", "pipelines", "commands", "pipeline",
                     "and_or_list"):
            v = getattr(n, attr, None)
            if isinstance(v, list):
                for x in v:
                    r = find_simple(x)
                    if r:
                        return r
            elif v is not None:
                r = find_simple(v)
                if r:
                    return r
        return None

    sc = find_simple(parse(tokenize(script)))
    return sc.redirects[0]


def test_expanded_procsub_text_is_a_filename_not_syntax():
    # `cat > "$x"` with x='>(echo evil)': the target is a VARIABLE whose VALUE
    # looks like procsub syntax. The planner must NOT reclassify it (C1).
    # (Quoted so it stays one field — unquoted splits, an ambiguous redirect
    # in both shells, unrelated to C1.)
    from psh.shell import Shell
    shell = Shell()
    shell.run_command("x='>(echo evil)'")
    fr = shell.io_manager.file_redirector
    redirect = _redirect_from(shell, 'cat > "$x"')
    # Structural: the target Word is a variable expansion, not a procsub node.
    assert fr.redirect_procsub_node(redirect) is None
    plan = fr.planner.plan(redirect)
    assert plan.procsub_node is None
    assert plan.procsub is None
    assert plan.target == ">(echo evil)"  # a literal filename, not syntax


def test_structural_procsub_node_is_detected():
    from psh.shell import Shell
    shell = Shell()
    fr = shell.io_manager.file_redirector
    redirect = _redirect_from(shell, "cat < <(echo hi)")
    node = fr.redirect_procsub_node(redirect)
    assert node is not None
    assert node.direction == "in"


def test_plan_resource_iff_structural_node():
    # Invariant: a procsub RESOURCE exists ONLY when a structural node did —
    # a resource can never spring from an expanded string.
    from psh.shell import Shell
    shell = Shell()
    fr = shell.io_manager.file_redirector
    filename = _redirect_from(shell, "cat > /dev/null")
    plan = fr.planner.plan(filename)
    assert (plan.procsub is None) and (plan.procsub_node is None)
