"""Invariants of the state-aware analysis session (remediation 2.6).

The CLI-visible behavior is pinned in
`tests/system/test_analysis_state_aware.py`. What lives here is what that
behavior RESTS on: that the session's summary of parse-relevant state cannot
fall behind the lexer, that its isolation classification is TOTAL over the AST
shapes it walks, and that going per-unit did not change what the visitors see
for input with no state change in it.
"""
import itertools
from pathlib import Path

import pytest

from psh.ast_nodes.commands import CompoundCommand
from psh.scripting.analysis_session import (
    ISOLATING_NODES,
    MONOTONE_OPTIONS,
    ORDERED_OPTIONS,
    PARSE_RELEVANT_OPTIONS,
    AnalysisSession,
    parse_for_analysis,
)
from psh.scripting.lex_parse import lex_and_parse
from psh.shell import Shell


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
    """PARSE_RELEVANT_OPTIONS must equal what THE PIPELINE reads. Derive both.

    The universe of this claim is "every option `lex_and_parse` consults", so
    the instrument has to be the PIPELINE. An earlier version of this guard
    scanned psh/lexer and psh/parser for literal option keys — which
    structurally could not see `expand_aliases`, because that one is read by
    `Shell.expand_aliases`, a third consumer in neither package. The guard
    passed while the constant was missing an option the slot's own census had
    already found: a guard whose universe is narrower than its claim certifies
    nothing.

    So: run a real parse with a RECORDING option mapping and compare the keys
    the pipeline actually looked up against the shipped constant, in BOTH
    directions.
    """

    # Spans the lexical and parse features an option could plausibly gate, so
    # the trace is not narrow by accident.
    CORPUS = [
        "echo hi", "case ab in +(a)b) echo M;; esac", "echo @(a|b)",
        "if true; then echo a; else echo b; fi", "for i in a b; do echo $i; done",
        "f() { echo hi; }", "function g { echo hi; }", "cat <<EOF\nbody\nEOF",
        "cat <<-EOF\n\tbody\nEOF", "cat <<<'here'", "echo $(echo nested)",
        "echo `echo bt`", "echo $((1+2))", "a=(1 2 3); echo ${a[1]}",
        "declare -A m; m[k]=v", "echo ${x:-d}", "echo {a,b}c", "echo a > f 2>&1",
        "exec {v}<file", "echo <(echo ps)", "[[ $x == a* ]]", "[ -f file ]",
        "echo 'sq' \"dq\" $'ansi'", "alias q='echo Q'; q", "x=1 y=2 env",
        "trap 'echo T' EXIT", "select s in a b; do break; done", "echo $äö",
        "a | b && c || d", "( sub ) ; { brace; }", "shopt -s extglob",
        "set -o posix", "shopt -u expand_aliases",
    ]

    class _Recorder(dict):
        """The option mapping, recording every key the pipeline looks up."""

        def __init__(self, base, log):
            super().__init__(base)
            self._log = log

        def get(self, key, default=None):
            self._log.add(key)
            return super().get(key, default)

        def __getitem__(self, key):
            self._log.add(key)
            return super().__getitem__(key)

        def __contains__(self, key):
            self._log.add(key)
            return super().__contains__(key)

    @classmethod
    def _keys_the_pipeline_reads(cls):
        """Every option key a real lex+parse looks up, transitively.

        The shell's own `state.options` is swapped for the recorder too, so
        consumers reached THROUGH the shell (`Shell.expand_aliases`) are seen
        — that is exactly the reach the previous static guard lacked.
        """
        log = set()
        shell = Shell(norc=True)
        shell.state.options = cls._Recorder(shell.state.options, log)
        for source in cls.CORPUS:
            for expand in (True, False):
                try:
                    lex_and_parse(source, shell, expand_aliases=expand,
                                  lexer_options=shell.state.options)
                except Exception:
                    pass          # a partial corpus line still records its reads
        return log

    def test_declared_set_equals_what_the_pipeline_reads(self):
        derived = self._keys_the_pipeline_reads()
        declared = set(PARSE_RELEVANT_OPTIONS)
        assert derived == declared, (
            "PARSE_RELEVANT_OPTIONS and the lex->parse pipeline disagree. "
            "Thread the missing option in AnalysisSession (with its measured "
            "monotone-vs-ordered semantics) and add it to the constant, or "
            "remove one the pipeline no longer reads. "
            f"pipeline={sorted(derived)} declared={sorted(declared)}")

    def test_every_declared_option_has_declared_semantics(self):
        """A threaded option with no combining rule would be silently dropped
        by _absorb_transitions, which is how a set can be 'complete' and still
        do nothing."""
        assert set(MONOTONE_OPTIONS) | set(ORDERED_OPTIONS) == set(
            PARSE_RELEVANT_OPTIONS)
        assert not (set(MONOTONE_OPTIONS) & set(ORDERED_OPTIONS))

    def test_the_trace_would_notice_a_new_option(self):
        """Mutation proof: a recorder that records nothing would make the
        comparison above vacuous, so prove the recorder records."""
        log = set()
        rec = self._Recorder({"newopt": True}, log)
        rec.get("newopt")
        rec.get("absent_key")
        assert log == {"newopt", "absent_key"}
        assert self._keys_the_pipeline_reads(), "the real trace found nothing"


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
    """The safety property the MONOTONE half of the transitions rule rests on.

    For `extglob` and `posix` the rule treats an unreached directive as live,
    which is only defensible because turning those options ON makes analysis
    accept MORE than the shell would, never REJECT what the shell accepts. If
    that failed, the rule would manufacture the false syntax errors this slot
    exists to remove.

    THE EXCEPTION, stated rather than implied: `expand_aliases` is NOT in this
    property's scope. It is an ORDERED option (see ORDERED_OPTIONS) because its
    measured execution semantics are not monotone, and an unreached conditional
    `shopt -u expand_aliases` therefore CAN narrow analysis. That cost is
    declared and separately pinned in
    tests/system/test_analysis_state_aware.py::TestExpandAliasesIsOrderedNotMonotone
    — it is not a hole in this test, it is the other half of the rule.

    GENERATED over a stated space rather than hand-picked (the campaign's
    generate-over-the-SPACE lesson): extglob operators x bodies x termination
    states x syntactic contexts, plus posix's identifier surface with
    non-portable, empty and metacharacter-bearing names. The domain is the
    product below; it is not the grammar, which is the honest residual.
    """

    OPS = ["@", "+", "?", "*", "!"]
    BODIES = ["a", "a|b", "a|b|c", "", "a)", "(a)", "a b", "'a'", '"a"', "$x",
              "$(echo a)", "a\\|b", "@(b)", "a*", "[a-z]"]
    TERMS = [")", "", "))", ") ", ")x"]
    CONTEXTS = [
        "echo {P}", "echo x{P}y", "case v in {P}) :;; esac",
        "case {P} in *) :;; esac", "[[ v == {P} ]]", "[[ {P} == v ]]",
        "for i in {P}; do :; done", "ls > {P}", "a={P}", "a=({P})",
        "declare -A m; m[{P}]=1", "f() {{ echo {P}; }}", "echo $({P})",
        "echo `echo {P}`", "{P}", "echo {P} | cat", "! echo {P}",
        "time echo {P}", "echo {P} && echo y", "cat <<EOF\n{P}\nEOF",
    ]
    POSIX_CASES = [
        "echo ${name}", "echo $name", "name=1", "exec {name}<f",
        "echo ${name:-d}", "echo ${name[0]}", "for name in a; do :; done",
        "read name", "declare name=1", "unset name", "let name=1",
        "echo ${!name}", "echo ${#name}", "printf %s ${name}",
    ]
    NAMES = ["x", "_x", "x1", "äö", "ünï", "x-y", "1x", "", "x y", "X_Y",
             "naïve", "日本", "x.y", "x$y"]

    @classmethod
    def _sources(cls):
        patterns = sorted({f"{op}({body}{term}" for op in cls.OPS
                           for body in cls.BODIES for term in cls.TERMS})
        out = [ctx.replace("{P}", pat) for pat in patterns
               for ctx in cls.CONTEXTS]
        out += [case.replace("name", name) for case in cls.POSIX_CASES
                for name in cls.NAMES]
        return out

    @staticmethod
    def _parses(shell, source, options):
        opts = dict(shell.state.options)
        opts.update(options)
        try:
            lex_and_parse(source, shell, expand_aliases=True,
                          lexer_options=opts)
            return True
        except Exception:
            return False

    def test_no_monotone_enable_turns_a_parsing_input_into_a_failing_one(self):
        """Monotonicity over the SUBSET LATTICE of the monotone options.

        Varying one option at a time against a fixed baseline would be the
        axis-quantification failure this campaign is named for: the session can
        hold ANY subset of these options live. So the property is checked on
        every lattice EDGE — for each state S and each option o not in S,
        adding o must not break a source that parsed under S.
        """
        shell = _shell("validate")
        sources = self._sources()
        options = list(MONOTONE_OPTIONS)
        edges = [(dict.fromkeys(subset, True), extra)
                 for size in range(len(options) + 1)
                 for subset in itertools.combinations(options, size)
                 for extra in options if extra not in subset]
        offenders = []
        for source in sources:
            for state, extra in edges:
                base = {name: False for name in options}
                base.update(state)
                after = dict(base)
                after[extra] = True
                if self._parses(shell, source, base) and not self._parses(
                        shell, source, after):
                    offenders.append((extra, sorted(base.items()), source))
        assert not offenders, (
            f"enabling a monotone option turned a parsing input into a failing "
            f"one — the transitions rule can invent a syntax error: "
            f"{offenders[:5]}")
        # The domain is only meaningful if it is the size it claims to be.
        assert len(sources) == 7496, len(sources)
        assert len(edges) == 4, len(edges)

    def test_the_search_detects_asymmetry_when_it_exists(self):
        """MUTATION PROOF: a hunt that finds nothing is worthless until shown
        capable of finding something. The OPPOSITE direction — inputs that
        parse with extglob ON and fail with it OFF — is exactly what extglob
        does, so it must be found in abundance over the same corpus."""
        shell = _shell("validate")
        found = 0
        for source in self._sources():
            if (self._parses(shell, source, {"extglob": True})
                    and not self._parses(shell, source, {"extglob": False})):
                found += 1
                if found >= 50:
                    break
        assert found >= 50, (
            f"the corpus detected only {found} cases in the direction extglob "
            "provably moves — the search itself is broken, so its zero in the "
            "unsafe direction means nothing")


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


class TestUserGuideMatchesTheRule:
    """R9-B: the user-facing declaration must not contradict the pins.

    The user guide's limits bullets described ALL options as monotone, which
    stopped being true when expand_aliases became ordered — and the branch's
    own declared-cost pin asserted the opposite. "Declared + pinned + doc'd"
    means the doc is part of the claim, so a contradiction there is a defect
    even when every test passes.
    """

    GUIDE = (Path(__file__).resolve().parents[3]
             / "docs/user_guide/17_differences_from_bash.md")

    def test_the_monotone_claim_is_scoped_to_the_monotone_options(self):
        text = self.GUIDE.read_text()
        section = text[text.index("**Analysis follows the script's own settings.**"):]
        section = section[:section.index("### Parser Selection")]
        # The unqualified "turning an option back off does not narrow" claim
        # must no longer stand on its own.
        assert "For `extglob` and `posix`" in section, (
            "the monotone bullets are not scoped to the options they describe")
        assert "expand_aliases" in section, (
            "the ordered option is not mentioned where its rule differs")

    def test_the_declared_cost_is_stated_in_user_facing_words(self):
        text = self.GUIDE.read_text()
        section = text[text.index("**Analysis follows the script's own settings.**"):]
        section = section[:section.index("### Parser Selection")]
        # The cost the branch pins must be findable by a reader who hit it.
        assert "shopt -u expand_aliases" in section
        assert "fails `--validate`" in section, (
            "the guide states the rule but not the consequence a user meets")
