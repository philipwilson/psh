"""Behavior tests for the analysis visitors and their shared traversal.

The metrics/security/linter visitors had essentially no direct coverage. These
tests pin their observable output and exercise the shared child-traversal
(`psh/visitor/traversal.py`) that all three now use for `generic_visit`.
"""

from psh.ast_nodes import Redirect
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import LinterVisitor, MetricsVisitor, SecurityVisitor
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


def _lint_messages(src):
    v = LinterVisitor()
    v.visit(_ast(src))
    return [i.message for i in v.issues]


def _lint_used_vars(src):
    v = LinterVisitor()
    v.visit(_ast(src))
    return v.used_vars


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

    def test_single_command_is_not_a_pipeline(self):
        # psh wraps every command in a single-element Pipeline node; the
        # metrics must only count genuine `|` pipelines, not those wrappers.
        m = _metrics("echo a; echo b; echo c")
        assert m.total_pipelines == 0
        assert m.max_pipeline_length == 0

    def test_while_loop_counts_condition_and_body(self):
        m = _metrics("while [ -e f ]; do sleep 1; done")
        assert m.total_commands == 2  # [ ... ]  and  sleep
        assert m.total_loops == 1

    def test_until_loop_counted_and_condition_traversed(self):
        # Regression for two fixes: until loops are now counted in total_loops
        # (a dedicated visit_UntilLoop was added, mirroring while), and their
        # condition is traversed so its `[ -e f ]` command is counted.
        m = _metrics("until [ -e f ]; do sleep 1; done")
        assert m.total_loops == 1
        assert m.loop_types['until'] == 1
        assert m.total_commands == 2  # [ ... ]  and  sleep

    def test_until_and_while_counted_equivalently(self):
        until = _metrics("until false; do :; done")
        while_ = _metrics("while true; do :; done")
        assert until.total_loops == while_.total_loops == 1

    def test_conditional_counts(self):
        m = _metrics("if [ -f x ]; then echo y; fi")
        assert m.total_conditionals == 1


class TestBraceGroupPipeline:
    """Regression: analysis visitors used to crash on a brace group in a
    pipeline ('StatementList' object is not iterable) because the under-walking
    generic_visit mishandled the group body. The shared traversal fixed it.
    """

    SCRIPTS = [
        "{ echo a; } | tee log",
        "{ echo a; echo b; } | tee log 2>&1",
        "{ ls; } | { grep x; } | wc -l",
        "( echo a; echo b ) | cat",
    ]

    def test_metrics_does_not_crash(self):
        for src in self.SCRIPTS:
            _metrics(src)  # must not raise

    def test_security_does_not_crash(self):
        for src in self.SCRIPTS:
            _security_types(src)  # must not raise

    def test_brace_group_inner_commands_counted(self):
        # The two echoes inside the group plus the downstream tee.
        m = _metrics("{ echo a; echo b; } | tee log")
        assert m.total_commands == 3


class TestSecurity:
    def test_eval_flagged(self):
        assert "DANGEROUS_COMMAND" in _security_types('eval "$x"')

    def test_world_writable_chmod_flagged(self):
        assert "WORLD_WRITABLE" in _security_types("chmod 777 file")

    def test_sensitive_command_flagged(self):
        assert "SENSITIVE_COMMAND" in _security_types("rm -rf $dir")

    def test_clean_command_no_issues(self):
        assert _security_types("echo hello") == set()


class TestLinterRedirectTargets:
    """The linter now analyzes redirect targets like ordinary command words.

    Previously its explicit handlers never traversed `node.redirects`, so an
    expansion inside a redirect target (`cmd > $x`) was invisible to every
    lint check. These pin the new, correct findings and guard against false
    positives.
    """

    def test_undefined_var_in_redirect_target_flagged(self):
        msgs = _lint_messages("echo hi > $undefined.log")
        assert any("'undefined' may be undefined" in m for m in msgs)

    def test_redirect_target_var_counts_as_used(self):
        # A var used only in a redirect target must not be reported unused.
        assert "outdir" in _lint_used_vars("outdir=/tmp; echo hi > $outdir/out")
        assert not any(
            "'outdir' is defined but never used" in m
            for m in _lint_messages("outdir=/tmp; echo hi > $outdir/out")
        )

    def test_literal_redirect_target_not_flagged(self):
        # A plain filename target is not a variable and not a command.
        msgs = _lint_messages("echo hi > result.txt")
        assert not any("undefined" in m for m in msgs)
        assert not any("result.txt" in m for m in msgs)

    def test_dup_fd_redirect_not_flagged(self):
        # `2>&1` carries a synthetic "&1" target — no expansion, no finding.
        msgs = _lint_messages("echo hi > out.log 2>&1")
        assert not any("may be undefined" in m for m in msgs)

    def test_undefined_var_in_compound_redirect_flagged(self):
        # A loop's own redirect (`done > $x`) reaches visit_Redirect via the
        # shared generic_visit traversal.
        msgs = _lint_messages(
            "while read line; do echo x; done > $outfile"
        )
        assert any("'outfile' may be undefined" in m for m in msgs)

    def test_heredoc_body_expansion_flagged(self):
        # Heredoc bodies undergo expansion; an undefined var in the body is a
        # variable usage. (Built directly: the CLI tokenizer doesn't always
        # populate heredoc_content, but in-process parses do.)
        r = Redirect(type="<<", target="END",
                     heredoc_content="value is $missing\n",
                     heredoc_quoted=False)
        v = LinterVisitor()
        v.visit(r)
        assert any("'missing' may be undefined" in i.message for i in v.issues)

    def test_quoted_heredoc_body_not_expanded(self):
        # A quoted delimiter disables expansion — no variable-usage finding.
        r = Redirect(type="<<", target="END",
                     heredoc_content="value is $missing\n",
                     heredoc_quoted=True)
        v = LinterVisitor()
        v.visit(r)
        assert not any("may be undefined" in i.message for i in v.issues)
