"""Analysis visitors descend into modern command/process substitution bodies.

Now that ``$(...)``/``<(...)``/``>(...)`` carry a parsed ``Program`` (nested-
program campaign), the security and lint analyses run on the commands *inside*
substitutions, not just the outer command. Backtick bodies carry no program and
are not descended into.
"""

from psh.lexer import tokenize
from psh.parser import Parser
from psh.visitor.linter_visitor import LinterVisitor
from psh.visitor.security_visitor import SecurityVisitor


def _ast(src):
    return Parser(tokenize(src)).parse()


def _security_issue_types(src):
    v = SecurityVisitor()
    v.visit(_ast(src))
    return {getattr(i, "issue_type", str(i)) for i in getattr(v, "issues", [])}


class TestSecurityDescendsIntoSubstitutions:
    def test_eval_inside_command_substitution_is_flagged(self):
        # The dangerous `eval` lives only inside $(...); it must still be seen.
        top = _security_issue_types('eval "$x"')
        nested = _security_issue_types('echo $(eval "$x")')
        assert top, "sanity: top-level eval should be flagged"
        # The same danger classes surface for the nested eval.
        assert top.issubset(nested) or (top & nested), (top, nested)

    def test_eval_inside_process_substitution_is_flagged(self):
        nested = _security_issue_types('cat <(eval "$x")')
        assert nested, "eval inside <(...) should be analysed"

    def test_backtick_body_not_descended(self):
        # Backticks carry program=None, so their body is not analysed here.
        nested = _security_issue_types('echo `eval "$x"`')
        assert nested == set()


class TestLinterDescendsIntoSubstitutions:
    def _lint_messages(self, src):
        v = LinterVisitor()
        v.visit(_ast(src))
        return [str(i) for i in v.issues]

    def test_dangerous_command_inside_cmdsub_is_linted(self):
        # A dangerous command used only inside $(...) is still linted; visiting
        # the body's statements must not duplicate the root-level checks.
        msgs = self._lint_messages('x=$(eval "$y")')
        assert any("eval" in m for m in msgs), msgs
