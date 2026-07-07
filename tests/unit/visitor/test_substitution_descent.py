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
        return [i.message for i in v.issues]

    # The dangerous-command warning is emitted ONLY when the linter visits the
    # inner ``eval`` SimpleCommand, i.e. only when descent happens. (Assert the
    # exact message — the outer word ``x=$(eval "$y")`` otherwise appears
    # verbatim in an unrelated "Function ... is called but not defined" message,
    # so a loose ``"eval" in msg`` substring check would pass WITHOUT descent.)
    _DANGEROUS_EVAL = "Use of potentially dangerous command 'eval'"

    def test_dangerous_command_inside_cmdsub_is_linted(self):
        msgs = self._lint_messages('x=$(eval "$y")')
        assert self._DANGEROUS_EVAL in msgs, msgs

    def test_no_double_lint_of_program_level_checks(self):
        # Descending into the body visits its STATEMENTS, not its Program, so
        # the root-level "no error handling" info fires exactly once.
        msgs = self._lint_messages('x=$(eval "$y"); z=$(eval "$w")')
        no_err = [m for m in msgs if "no explicit error handling" in m]
        assert len(no_err) <= 1, msgs

    def test_backtick_body_not_linted_for_danger(self):
        # Backticks carry program=None: no descent, so the inner eval is not
        # flagged as a dangerous command (this is the negative control that
        # proves the previous assertion is gated on descent, not a substring).
        assert self._DANGEROUS_EVAL not in self._lint_messages('x=`eval "$y"`')
