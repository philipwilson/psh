"""Behavior tests for the analysis visitors and their shared traversal.

The metrics/security/linter visitors had essentially no direct coverage. These
tests pin their observable output and exercise the shared child-traversal
(`psh/visitor/traversal.py`) that all three now use for `generic_visit`.
"""

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import MetricsVisitor, SecurityVisitor
from psh.visitor.traversal import iter_child_nodes, visit_children


def _ast(src):
    return parse(tokenize(src))


def _metrics(src):
    v = MetricsVisitor()
    v.visit(_ast(src))
    return v.metrics


def _security_types(src):
    v = SecurityVisitor()
    v.visit(_ast(src))
    return {i.issue_type for i in v.issues}


class TestSharedTraversal:
    def test_iter_child_nodes_yields_ast_children(self):
        from psh.ast_nodes import ASTNode
        node = _ast("echo a | grep b")
        kids = list(iter_child_nodes(node))
        assert kids and all(isinstance(k, ASTNode) for k in kids)

    def test_iter_child_nodes_ignores_non_ast(self):
        # A leaf-ish node should yield no ASTNode children for scalar fields.
        cmd = _ast("echo hi")
        # Drill to the SimpleCommand and ensure scalars (strings) aren't yielded.
        from psh.ast_nodes import ASTNode
        for child in iter_child_nodes(cmd):
            assert isinstance(child, ASTNode)

    def test_visit_children_recurses(self):
        # A counting visitor using only generic_visit + visit_children should
        # reach a SimpleCommand nested several levels deep.
        from psh.visitor.base import ASTVisitor
        from psh.ast_nodes import SimpleCommand

        class Counter(ASTVisitor):
            def __init__(self):
                super().__init__()
                self.commands = 0

            def generic_visit(self, node):
                visit_children(self, node)

            def visit_SimpleCommand(self, node):
                self.commands += 1

        c = Counter()
        c.visit(_ast("if true; then for x in 1 2; do echo $x; done; fi"))
        # true, echo  (and the for-list values are not commands)
        assert c.commands >= 2


class TestMetrics:
    def test_pipeline_counts(self):
        m = _metrics("echo a | grep b")
        assert m.total_commands == 2
        assert m.total_pipelines == 1

    def test_while_loop_counts_condition_and_body(self):
        m = _metrics("while [ -e f ]; do sleep 1; done")
        assert m.total_commands == 2  # [ ... ]  and  sleep
        assert m.total_loops == 1

    def test_until_loop_condition_is_traversed(self):
        # Regression: UntilLoop has no dedicated visitor, so it reaches
        # generic_visit. The former under-traversing generic_visit skipped the
        # loop condition; the shared traversal now visits it, so the condition's
        # `[ -e f ]` command is counted (matching while-loop behavior).
        m = _metrics("until [ -e f ]; do sleep 1; done")
        assert m.total_commands == 2

    def test_conditional_counts(self):
        m = _metrics("if [ -f x ]; then echo y; fi")
        assert m.total_conditionals == 1


class TestSecurity:
    def test_eval_flagged(self):
        assert "DANGEROUS_COMMAND" in _security_types('eval "$x"')

    def test_world_writable_chmod_flagged(self):
        assert "WORLD_WRITABLE" in _security_types("chmod 777 file")

    def test_sensitive_command_flagged(self):
        assert "SENSITIVE_COMMAND" in _security_types("rm -rf $dir")

    def test_clean_command_no_issues(self):
        assert _security_types("echo hello") == set()
