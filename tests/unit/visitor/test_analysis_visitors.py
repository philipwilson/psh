"""Behavior tests for the analysis visitors and their shared traversal.

The metrics/security/linter visitors had essentially no direct coverage. These
tests pin their observable output and exercise the shared child-traversal
(`psh/visitor/traversal.py`) that all three now use for `generic_visit`.
"""

from psh.ast_nodes import Redirect
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import (
    EnhancedValidatorVisitor,
    LinterVisitor,
    MetricsVisitor,
    SecurityVisitor,
)
from psh.visitor.traversal import iter_child_nodes, visit_children


def _validator_messages(src):
    v = EnhancedValidatorVisitor()
    v.visit(parse(tokenize(src)))
    return [i.message for i in v.issues]


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

    def test_world_writable_non_777_modes_flagged(self):
        # R14.C: octal modes with the other-write bit set — not just 777/666 —
        # are world-writable. SecurityVisitor and the validator now share one
        # bit-check, so both catch 757/776/737/etc.
        for mode in ("757", "776", "737", "666"):
            assert "WORLD_WRITABLE" in _security_types(f"chmod {mode} f"), mode
            assert any("world-writable" in m for m in _validator_messages(f"chmod {mode} f")), mode
        for safe in ("755", "644", "640"):
            assert "WORLD_WRITABLE" not in _security_types(f"chmod {safe} f"), safe

    def test_sensitive_command_flagged(self):
        assert "SENSITIVE_COMMAND" in _security_types("rm -rf $dir")

    def test_clean_command_no_issues(self):
        assert _security_types("echo hello") == set()

    # R12.D: recursive+force rm on a sensitive dir is flagged for every flag
    # spelling, not just the literal -rf token.
    def test_dangerous_rm_rf(self):
        assert "DANGEROUS_RM" in _security_types("rm -rf /")

    def test_dangerous_rm_separate_flags(self):
        assert "DANGEROUS_RM" in _security_types("rm -r -f /etc")

    def test_dangerous_rm_fr_order(self):
        assert "DANGEROUS_RM" in _security_types("rm -fr /usr")

    def test_dangerous_rm_long_options(self):
        assert "DANGEROUS_RM" in _security_types("rm --recursive --force /home")

    def test_dangerous_rm_clustered_extra_flags(self):
        assert "DANGEROUS_RM" in _security_types("rm -rvf /var")

    def test_rm_recursive_force_safe_target_not_flagged(self):
        assert "DANGEROUS_RM" not in _security_types("rm -rf /tmp/scratch")

    def test_rm_without_force_not_flagged(self):
        # -r alone (no force) on / is not the DANGEROUS_RM pattern.
        assert "DANGEROUS_RM" not in _security_types("rm -r /")


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


class TestWordAnalysisStructuralFindings:
    """R8.4: the validator/linter/security now read variable references from the
    Word AST (`word_analysis`) instead of regexing rendered strings. These pin
    the false positives that removed and the genuinely-correct findings it added.
    """

    # --- removed false positives -------------------------------------------

    def test_single_quoted_dollar_not_a_variable_use_validator(self):
        # '$FOO' is a literal string; the old string scan flagged FOO.
        assert not any(
            "undefined variable '$FOO'" in m
            for m in _validator_messages("echo '$FOO'")
        )

    def test_single_quoted_dollar_not_a_variable_use_linter(self):
        assert not any(
            "'FOO' may be undefined" in m for m in _lint_messages("echo '$FOO'")
        )

    def test_for_over_command_sub_not_undefined_variable(self):
        # `for f in $(ls)`: $(ls) is a command sub, not a variable named "(ls)".
        assert not any(
            "in for loop items" in m
            for m in _validator_messages("for f in $(ls); do echo $f; done")
        )

    def test_for_over_backtick_not_undefined_variable(self):
        assert not any(
            "in for loop items" in m
            for m in _validator_messages("for f in `ls`; do echo $f; done")
        )

    def test_quoted_at_not_advised(self):
        # "$@" is already correctly quoted — no "Unquoted $@" advisory.
        assert not any(
            "Unquoted $@" in m for m in _validator_messages('echo "$@"')
        )

    # --- new, correct findings ---------------------------------------------

    def test_unquoted_backtick_substitution_is_word_split(self):
        # Consistent with $(date): an unquoted backtick sub undergoes splitting.
        assert any(
            "may cause word splitting" in m
            for m in _validator_messages("echo `date`")
        )

    def test_nested_default_word_reference_validator(self):
        # ${FOO:-${BAR}} references BAR inside the default; BAR is undefined.
        msgs = _validator_messages("FOO=bar\necho ${FOO:-${BAR}}")
        assert any("undefined variable '$BAR'" in m for m in msgs)

    def test_nested_default_word_reference_linter(self):
        msgs = _lint_messages("FOO=bar\necho ${FOO:-${BAR}}")
        assert any("'BAR' may be undefined" in m for m in msgs)

    # --- preserved correct behavior ----------------------------------------

    def test_array_subscript_name_clean(self):
        # ${arr[@]} on an undefined array reports the bare name 'arr' in the
        # undefined-variable warning (the subscript debris no longer leaks into
        # the name). The separate word-split advisory still echoes the rendered
        # argument, so we assert on the undefined-variable message specifically.
        undef = [
            m for m in _validator_messages("echo ${arr[@]}")
            if "undefined variable" in m
        ]
        assert undef == ["Possible use of undefined variable '$arr'"]

    def test_parameter_default_suppresses_undefined(self):
        assert not any(
            "undefined variable" in m
            for m in _validator_messages("echo ${UNSET:-fallback}")
        )

    def test_eval_of_variable_flagged(self):
        types = _security_types("eval $CMD")
        assert "UNQUOTED_EXPANSION" in types

    def test_eval_of_quoted_variable_still_flagged(self):
        # Existing behavior: any variable handed to eval is an injection risk.
        types = _security_types('eval "$CMD"')
        assert "UNQUOTED_EXPANSION" in types

    def test_for_over_command_sub_security_unquoted_substitution(self):
        types = _security_types("for f in $(ls); do echo $f; done")
        assert "UNQUOTED_SUBSTITUTION" in types


class TestAssignBuiltinsDefineVariables:
    """Assigning builtins (printf -v, mapfile/readarray, getopts) register the
    variables they define, so a later reference is not a false 'undefined
    variable' warning (reappraisal #16 Tier-2)."""

    def test_printf_v_defines_variable(self):
        assert not any(
            "undefined variable" in m
            for m in _validator_messages('printf -v myvar %s hi\necho "$myvar"')
        )

    def test_printf_without_v_does_not_suppress_others(self):
        assert any(
            "undefined variable '$other'" in m
            for m in _validator_messages('printf "%s" "$other"')
        )

    def test_mapfile_defines_array(self):
        assert not any(
            "undefined variable" in m
            for m in _validator_messages('mapfile arr < f\necho "${arr[@]}"')
        )

    def test_readarray_defines_array(self):
        assert not any(
            "undefined variable" in m
            for m in _validator_messages('readarray rows < f\necho "${rows[@]}"')
        )

    def test_getopts_defines_name_and_optarg(self):
        src = 'while getopts "ab:" opt; do echo "$opt $OPTARG"; done'
        assert not any(
            "undefined variable" in m for m in _validator_messages(src)
        )

    def test_getopts_still_flags_unrelated_undefined(self):
        src = 'while getopts "a" o; do echo "$other"; done'
        assert any(
            "undefined variable '$other'" in m for m in _validator_messages(src)
        )
