"""Invariants of the state-aware analysis session (remediation 2.6).

The CLI-visible behavior is pinned in
`tests/system/test_analysis_state_aware.py`. What lives here is what that
behavior RESTS on: that the session's summary of parse-relevant state cannot
fall behind the lexer, that its isolation classification is TOTAL over the AST
shapes it walks, and that going per-unit did not change what the visitors see
for input with no state change in it.
"""
import ast as pyast
from pathlib import Path

import pytest

from psh.ast_nodes.commands import CompoundCommand
from psh.scripting.analysis_session import (
    ISOLATING_NODES,
    PARSE_RELEVANT_OPTIONS,
    AnalysisSession,
    parse_for_analysis,
)
from psh.scripting.lex_parse import lex_and_parse
from psh.shell import Shell

PSH_ROOT = Path(__file__).resolve().parents[3] / "psh"


def _shell(mode=None):
    shell = Shell(norc=True)
    shell.analysis_mode = mode
    return shell


def _whole_file_parse(shell, source, *, expand_aliases):
    """What analysis did BEFORE this slot: join continuations over the whole
    input, then parse it in ONE call. The reference the session must reproduce
    for input that changes no parse-relevant state."""
    from psh.scripting.input_preprocessing import process_line_continuations
    return lex_and_parse(process_line_continuations(source), shell,
                         expand_aliases=expand_aliases,
                         lexer_options=shell.state.options)


class TestParseRelevantOptionsIsDerived:
    """PARSE_RELEVANT_OPTIONS summarizes the lexer; re-derive it and compare.

    A hand-maintained list is exactly the thing that rots: if the lexer starts
    consulting a third option, the session would silently stop threading it and
    the MEDIUM-9 defect would come back for that option only. So the test does
    not restate the list — it SCANS psh/lexer and psh/parser for literal keys
    read from an options mapping and requires the two to agree.
    """

    @staticmethod
    def _keys_read_from_options():
        names = {"shell_options", "lexer_options", "options", "shell_opts"}
        found = set()
        for package in ("lexer", "parser"):
            for path in sorted((PSH_ROOT / package).rglob("*.py")):
                tree = pyast.parse(path.read_text(), filename=str(path))
                for node in pyast.walk(tree):
                    if (isinstance(node, pyast.Call)
                            and isinstance(node.func, pyast.Attribute)
                            and node.func.attr == "get"
                            and isinstance(node.func.value, pyast.Name)
                            and node.func.value.id in names
                            and node.args
                            and isinstance(node.args[0], pyast.Constant)
                            and isinstance(node.args[0].value, str)):
                        found.add(node.args[0].value)
                    elif (isinstance(node, pyast.Subscript)
                          and isinstance(node.value, pyast.Name)
                          and node.value.id in names
                          and isinstance(node.slice, pyast.Constant)
                          and isinstance(node.slice.value, str)):
                        found.add(node.slice.value)
        return found

    def test_declared_set_matches_what_the_lexer_reads(self):
        derived = self._keys_read_from_options()
        assert derived == set(PARSE_RELEVANT_OPTIONS), (
            "psh/lexer or psh/parser reads an option the analysis session does "
            "not thread (or vice versa). Thread it in AnalysisSession and add "
            f"it to PARSE_RELEVANT_OPTIONS. derived={sorted(derived)} "
            f"declared={sorted(PARSE_RELEVANT_OPTIONS)}")

    def test_the_scan_would_notice_a_new_option(self):
        """Mutation proof: the scan finds a key from a synthetic source, so a
        passing comparison above means agreement, not an empty scan."""
        source = "def f(shell_options):\n    return shell_options.get('newopt')\n"
        tree = pyast.parse(source)
        keys = {n.args[0].value for n in pyast.walk(tree)
                if isinstance(n, pyast.Call)
                and isinstance(n.func, pyast.Attribute)
                and n.func.attr == "get"
                and isinstance(n.func.value, pyast.Name)
                and n.func.value.id == "shell_options"}
        assert keys == {"newopt"}
        assert self._keys_read_from_options(), "the real scan found nothing"


class TestIsolationClassificationIsTotal:
    """Every compound shape is classified, so a new one cannot arrive unseen.

    The session treats an unclassified compound as STATE-PRESERVING, which is
    the safe default (more permissive, never a false syntax error) — but silent
    defaults are how coverage rots, so the classification is enumerated here
    and a new CompoundCommand subclass fails this test until it is placed.
    """

    STATE_PRESERVING = {
        "ArithmeticEvaluation", "BraceGroup", "CStyleForLoop",
        "CaseConditional", "EnhancedTestStatement", "ForLoop",
        "IfConditional", "SelectLoop", "UnifiedControlStructure",
        "UntilLoop", "WhileLoop",
    }

    @staticmethod
    def _all_compound_names():
        def descend(cls):
            for sub in cls.__subclasses__():
                yield sub.__name__
                yield from descend(sub)
        return set(descend(CompoundCommand))

    def test_every_compound_command_is_classified(self):
        classified = self.STATE_PRESERVING | set(ISOLATING_NODES)
        unclassified = self._all_compound_names() - classified
        assert not unclassified, (
            "new compound AST shape(s) not classified by the analysis "
            f"session's isolation rule: {sorted(unclassified)}")

    def test_isolating_and_preserving_do_not_overlap(self):
        assert not (self.STATE_PRESERVING & set(ISOLATING_NODES))


class TestPerUnitParseMatchesWholeFileWhenNothingChanges:
    """Going incremental must not move analysis for ordinary scripts."""

    CORPUS = [
        "echo one\necho two\n",
        "x=1\nif [ \"$x\" = 1 ]; then\n  echo one\nfi\n",
        "f() {\n  echo hi\n}\nf\n",
        "case $1 in\n  a) echo A;;\n  *) echo B;;\nesac\n",
        "# lead\n\necho a\n\n# mid\necho b\n",
        "echo one \\\n  two\necho three\n",
        "echo a |\n  grep a\necho done\n",
        "for i in a b; do\n  echo $i\ndone\n",
    ]

    @pytest.mark.parametrize("source", CORPUS)
    def test_same_statements_as_a_whole_file_parse(self, source):
        shell = _shell("validate")
        session = parse_for_analysis(shell, source)
        whole = _whole_file_parse(shell, source, expand_aliases=True)
        assert len(session.statements) == len(whole.statements)

    @pytest.mark.parametrize("source", CORPUS)
    def test_formatter_output_is_unchanged(self, source):
        from psh.visitor import FormatterVisitor
        shell = _shell("format")
        session = parse_for_analysis(shell, source)
        whole = _whole_file_parse(shell, source, expand_aliases=False)
        assert FormatterVisitor().visit(session) == FormatterVisitor().visit(whole)


class TestMonotoneEnablesCannotInventAnError:
    """The safety property the whole transitions rule rests on.

    The rule treats an unreached directive as live, which is only defensible
    because turning a parse-relevant option ON can make analysis accept MORE
    than the shell would, never make it REJECT what the shell accepts. If some
    input parsed with an option off and failed with it on, the rule would
    manufacture exactly the false syntax errors this slot exists to remove.

    This is EVIDENCE over a STATED DOMAIN, not a proof: an adversarial corpus
    built to break the property — truncated and malformed extglob openers,
    extglob syntax in the positions the parser treats specially, and
    non-portable identifiers, which is where posix mode narrows what counts as
    a name.
    """

    CORPUS = [
        "echo @(a", "echo +(", "echo ?(a|b", "echo !(a))", "echo *(a)b)",
        "case x in @(a) esac", "echo a@(", "echo @()", "echo @(a|b)c(d)",
        "[[ a == @(a ]]", "echo $((1+2))", "echo ${x@Q}", "f() { :; }",
        "echo @( a )", "echo x@(y)z", "echo '@(a'", 'echo "@(a"',
        "echo $äö", "echo ${äö}", "äö=1", "exec {äö}<f", "echo {a,b}",
        "declare -A m; m[@(k)]=v", "echo a>@(b)", "case @(x) in *) :;; esac",
        "for i in @(a|b); do :; done", "echo \\@(a", "echo @(a\\|b)",
        "time @(a)", "! @(a)", "echo @(a)$(echo @(b))",
    ]

    @staticmethod
    def _parses(shell, source, **options):
        opts = dict(shell.state.options)
        opts.update(options)
        try:
            lex_and_parse(source, shell, expand_aliases=True,
                          lexer_options=opts)
            return True
        except Exception:
            return False

    @pytest.mark.parametrize("option", PARSE_RELEVANT_OPTIONS)
    @pytest.mark.parametrize("source", CORPUS)
    def test_enabling_an_option_never_rejects_what_it_accepted(self, option,
                                                               source):
        shell = _shell("validate")
        off = self._parses(shell, source, **{option: False})
        on = self._parses(shell, source, **{option: True})
        assert not (off and not on), (
            f"enabling {option!r} turned a parsing input into a failing one: "
            f"{source!r} — the monotone-enable rule can invent a syntax error, "
            "so the transitions rule's safety property does not hold")


class TestSessionStateIsIsolatedFromTheShell:
    """The session must not mutate the shell it was asked to analyze FOR."""

    def test_analysis_does_not_leak_state_into_the_caller(self):
        shell = _shell("validate")
        shell.state.options["extglob"] = False
        shell.alias_manager.aliases.clear()
        before_parser = shell.active_parser
        parse_for_analysis(
            shell,
            "shopt -s extglob\nalias zz='echo Z'\nparser-select combinator\n"
            "echo @(a|b)\n")
        assert shell.state.options.get("extglob") is False
        assert "zz" not in shell.alias_manager.aliases
        assert shell.active_parser == before_parser

    def test_the_carrier_did_receive_the_state(self):
        """The control for the test above: a leak check that can only pass
        because nothing was threaded would be worthless."""
        session = AnalysisSession(_shell("validate"))
        session.analyze("shopt -s extglob\nalias zz='echo Z'\necho @(a|b)\n")
        assert session.carrier.state.options.get("extglob") is True
        assert "zz" in session.carrier.alias_manager.aliases

    def test_carrier_keeps_an_embedders_shell_subclass(self):
        """The carrier is built through the shell's own type, so an embedder
        that subclasses Shell is analyzed by its own class rather than being
        silently downgraded to the base one."""
        class EmbedderShell(Shell):
            pass

        session = AnalysisSession(EmbedderShell(norc=True))
        assert type(session.carrier) is EmbedderShell


class TestSingleAnalysisMode:
    """MEDIUM-9(b) at the constructor: the ambiguous state is unrepresentable."""

    def test_two_modes_is_a_construction_error(self):
        with pytest.raises(ValueError) as caught:
            Shell(norc=True, validate_only=True, lint_only=True)
        assert "validate_only" in str(caught.value)
        assert "lint_only" in str(caught.value)

    @pytest.mark.parametrize("mode", ["validate", "format", "metrics",
                                      "security", "lint"])
    def test_one_mode_sets_the_single_name(self, mode):
        shell = Shell(norc=True, **{f"{mode}_only": True})
        assert shell.analysis_mode == mode

    def test_no_mode_is_none(self):
        assert Shell(norc=True).analysis_mode is None
