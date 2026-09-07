"""Invariants of the state-aware analysis session (remediation 2.6).

The CLI-visible behavior is pinned in
`tests/system/test_analysis_state_aware.py`. What lives here is what that
behavior RESTS on: that the session's summary of parse-relevant state cannot
fall behind the lexer, that its isolation classification is TOTAL over the AST
shapes it walks, and that going per-unit did not change what the visitors see
for input with no state change in it.
"""
import ast as pyast
import itertools
from pathlib import Path

import pytest

from psh.ast_nodes.commands import CompoundCommand
from psh.scripting.analysis_session import (
    DEBUG_OPTIONS,
    ISOLATING_NODES,
    MONOTONE_OPTIONS,
    ORDERED_OPTIONS,
    PARSE_RELEVANT_OPTIONS,
    SET_O_TABLE_OPTIONS,
    SHOPT_TABLE_OPTIONS,
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


class TestAbandoningTheSharedChunkerIsSafe:
    """"Execution behavior UNTOUCHED", given a structural argument at last.

    Execution's line-gathering loop became a GENERATOR shared with the
    analysis session. The claim that this changed nothing rested entirely on
    the gate and compare-bash being green — never on a reason (R16, adopting
    the stand-down note's re-verify list, which named the generator's
    early-return paths as the place to look).

    The reason is that the generator owns NOTHING. `_run_from_source` returns
    early from inside the for-loop on two paths — the POSIX syntax abort and
    the errexit exit — abandoning the generator mid-iteration. That is
    equivalent to the old `while` loop's `return` precisely because there is
    no `try`/`finally`, no `with`, and no acquired resource in the generator
    body: the input source belongs to the caller, exactly as it did before.
    Both halves are asserted, because either alone could stop being true.
    """

    def test_the_generator_body_acquires_nothing(self):
        """If a `try`/`finally` or `with` ever appears here, abandonment stops
        being free and the early-return paths need revisiting."""
        import inspect
        import textwrap

        from psh.scripting.source_processor import iter_command_units

        tree = pyast.parse(textwrap.dedent(inspect.getsource(iter_command_units)))
        kinds = {type(node).__name__ for node in pyast.walk(tree)}
        assert not kinds & {"Try", "With", "AsyncWith", "TryStar"}, (
            "the shared chunker now has cleanup semantics, so abandoning it on "
            "the errexit / POSIX-abort paths is no longer equivalent to the "
            f"old loop's return: found {sorted(kinds & {'Try', 'With'})}")

    def test_abandoning_it_midway_raises_nothing_and_leaves_the_source_usable(self):
        """The behavioral half: stop consuming after one unit, close the
        generator explicitly (what garbage collection does anyway), and the
        input source is still readable — no state was torn down with it."""
        from psh.scripting.program_source import ProgramSource
        from psh.scripting.source_processor import iter_command_units

        shell = Shell(norc=True)
        source = ProgramSource.command_string(
            "echo one\necho two\necho three\n").make_input_source()
        units = iter_command_units(shell, source, trace=False)
        first = next(units)
        assert "one" in first[1].text
        units.close()                      # the abort paths' effect, forced
        assert source.read_line() is not None, (
            "the input source was consumed or closed with the generator")


class TestAnalysisModesAreInvocationOnly:
    """The interactive-leg conclusion, as a GUARD rather than as prose.

    The brief's rule is "interactive-only is a conclusion, never a starting
    point — and so is CLI-only". Slot 2.6 censused this and concluded the five
    analysis modes are reachable only through their invocation flags, so no
    PTY pin is owed. That conclusion was a substantive deliverable that
    existed only as a ledger sentence, with nothing in the tree asserting it
    (R16, adopting the stand-down note's re-verify list).

    Re-derived here, and now pinned: if a later change gives an analysis mode
    a runtime spelling, this fails and the PTY-pin question reopens instead of
    a stale sentence continuing to say it was settled.
    """

    def test_no_analysis_mode_is_reachable_as_a_shell_option(self):
        """C1: no `set -o validate` / `shopt -s lint` spelling exists."""
        from psh.core.option_registry import OPTION_REGISTRY
        from psh.invocation import ANALYSIS_MODES

        assert len(OPTION_REGISTRY) > 40, "registry looks wrong; guard is blind"
        overlap = [m for m in ANALYSIS_MODES if m in OPTION_REGISTRY]
        assert not overlap, (
            f"analysis mode(s) {overlap} now have a shell-option spelling, so "
            "they are reachable at runtime — the invocation-only conclusion no "
            "longer holds and an interactive/PTY pin is owed")

    def test_analysis_mode_is_written_in_exactly_one_place(self):
        """C2: nothing mutates the mode after construction, so it cannot be
        switched on from inside a running shell."""
        import re

        sites = []
        for path in (Path(__file__).resolve().parents[3] / "psh").rglob("*.py"):
            for i, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(r"\banalysis_mode\s*=(?!=)", line):
                    sites.append(f"{path.name}:{i}")
        assert len(sites) == 1, (
            f"analysis_mode is assigned in {len(sites)} places: {sites}. "
            "More than one means it can be mutated after construction, which "
            "is a runtime path into analysis.")
        assert sites[0].startswith("shell.py:"), sites

    def test_the_analysis_entry_points_are_called_only_from_main(self):
        """C3: the only callers are the three invocation branches in
        __main__.py (plus visitor_modes delegating to itself)."""
        import re

        root = Path(__file__).resolve().parents[3] / "psh"
        callers = set()
        pattern = re.compile(r"(handle_visitor_mode_for_\w+|apply_visitor_mode)\s*\(")
        for path in root.rglob("*.py"):
            for line in path.read_text().splitlines():
                if pattern.search(line) and not line.strip().startswith("def "):
                    callers.add(path.relative_to(root).as_posix())
        assert callers <= {"__main__.py", "scripting/visitor_modes.py"}, (
            f"analysis entry points are now called from {sorted(callers)} — a "
            "new caller may be a runtime path into analysis")


class TestEveryPerUnitFailureReachesTheEnvelope:
    """R15-B-G: a failure anywhere in a unit's handling carries the unit's line.

    The envelope exists so a per-unit failure is reported the way execution
    reports one — `psh: <source>:<line>:`. Lexing and parsing were inside it;
    the state-absorption pass, which walks the SAME unit's AST and tokens, ran
    outside it, so an exception there would have escaped as a bare traceback
    with no location. Pinned by making absorption fail on purpose, because the
    structural fact ("the call is inside the try") is not observable from
    outside and an indentation check is not a behavior claim.
    """

    def test_an_absorption_failure_is_wrapped_with_the_units_line(self,
                                                                  monkeypatch):
        from psh.scripting.analysis_session import AnalysisSyntaxError

        session = AnalysisSession(_shell("validate"))

        def explode(self, ast, tokens):
            raise RuntimeError("absorption blew up")

        monkeypatch.setattr(AnalysisSession, "_absorb_transitions", explode)
        with pytest.raises(AnalysisSyntaxError) as caught:
            session.analyze("echo one\necho two\necho three\n")
        # The FIRST unit is on line 1, so that is the line reported.
        assert caught.value.start_line == 1
        assert isinstance(caught.value.error, RuntimeError)

    def test_the_line_is_the_failing_units_line_not_always_one(self,
                                                               monkeypatch):
        """The control: a wrapper that always said line 1 would pass the test
        above while telling the user nothing."""
        from psh.scripting.analysis_session import AnalysisSyntaxError

        session = AnalysisSession(_shell("validate"))
        seen = {"units": 0}
        original = AnalysisSession._absorb_transitions

        def explode_on_third(self, ast, tokens):
            seen["units"] += 1
            if seen["units"] == 3:
                raise RuntimeError("absorption blew up on unit 3")
            return original(self, ast, tokens)

        monkeypatch.setattr(AnalysisSession, "_absorb_transitions",
                            explode_on_third)
        with pytest.raises(AnalysisSyntaxError) as caught:
            session.analyze("echo one\necho two\necho three\n")
        assert caught.value.start_line == 3


class TestCarrierDoesNotInheritDebugOptions:
    """R15-B-C, code half: the carrier is built with every debug option OFF.

    Analysis executes nothing, so an execution trace on an analysis run
    describes work that never happened. One line escaped even before any
    analysis ran — a child state re-detects the terminal and reports it under
    `debug-exec` — which is why the clearing happens ACROSS the construction
    rather than after it.
    """

    def test_debug_options_are_derived_from_the_registry(self):
        """A typed list would silently miss a new debug-* option; this one
        cannot, so the guard is the derivation itself."""
        from psh.core.option_registry import OPTION_REGISTRY

        assert set(DEBUG_OPTIONS) == {name for name in OPTION_REGISTRY
                                      if name.startswith('debug')}
        assert 'debug-exec' in DEBUG_OPTIONS

    def test_carrier_has_every_debug_option_off(self):
        shell = Shell(norc=True)
        for name in DEBUG_OPTIONS:
            shell.state.options[name] = True
        session = AnalysisSession(shell)
        for name in DEBUG_OPTIONS:
            assert session.carrier.state.options[name] is False, name

    def test_the_parent_shells_debug_options_are_restored(self):
        """The clearing is a window around construction, not a mutation the
        caller keeps: the parent is left exactly as it was found."""
        shell = Shell(norc=True)
        for name in DEBUG_OPTIONS:
            shell.state.options[name] = True
        AnalysisSession(shell)
        for name in DEBUG_OPTIONS:
            assert shell.state.options[name] is True, name

    def test_the_parent_is_restored_even_when_construction_raises(self):
        """The window is closed by `finally`, so a failed construction cannot
        leave the caller's shell with its debug options silently off."""
        shell = Shell(norc=True)
        shell.state.options['debug-exec'] = True

        class _Exploding(type(shell)):          # type: ignore[misc]
            def __init__(self, *args, **kwargs):
                raise RuntimeError("construction failed")

        shell.__class__ = _Exploding
        with pytest.raises(RuntimeError):
            AnalysisSession(shell)
        assert shell.state.options['debug-exec'] is True

    def test_constructing_the_carrier_writes_nothing_to_stderr(self):
        """The leak was a PRINT, so the pin is about output, not about a flag:
        a future line emitted under some other debug option fails here too."""
        import contextlib
        import io

        shell = Shell(norc=True)
        for name in DEBUG_OPTIONS:
            shell.state.options[name] = True
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            AnalysisSession(shell)
        assert err.getvalue() == ""


class TestShoptTableRoutingIsDerived:
    """R15-B-B: `-o` decides WHICH option table a `shopt` operand names, and
    for the options this session threads the two tables are disjoint.

    Measured in psh and bash 5.2.26: `shopt -s posix` is refused ("invalid
    shell option name") while `shopt -so posix` sets it; `shopt -so extglob`
    is refused ("invalid option name") while `shopt -s extglob` sets it. A
    recognizer that read the flags but not the table would invent both of
    those state changes.

    DERIVED, not curated — the same lesson as PARSE_RELEVANT_OPTIONS above:
    the truth is the builtin's own tables, so this compares against them in
    both directions instead of freezing a list somebody typed. `psh.scripting`
    cannot import `psh.builtins` at module level (a documented cycle), so the
    constants live in the session and the derivation lives here.
    """

    def test_routing_constants_match_the_builtins_own_tables(self):
        from psh.builtins.shell_options import _SET_O_NAMES, _SHOPT_NAMES

        for name in PARSE_RELEVANT_OPTIONS:
            in_shopt = name in _SHOPT_NAMES
            in_set_o = name in _SET_O_NAMES
            assert (name in SHOPT_TABLE_OPTIONS) == in_shopt, (
                f"{name}: SHOPT_TABLE_OPTIONS disagrees with the shopt "
                f"builtin's own _SHOPT_NAMES (builtin says {in_shopt})")
            assert (name in SET_O_TABLE_OPTIONS) == in_set_o, (
                f"{name}: SET_O_TABLE_OPTIONS disagrees with the shopt "
                f"builtin's own _SET_O_NAMES (builtin says {in_set_o})")

    @pytest.mark.parametrize("o_flag", [False, True])
    @pytest.mark.parametrize("option", PARSE_RELEVANT_OPTIONS)
    def test_the_constants_predict_the_builtins_measured_behavior(self, option,
                                                                  o_flag):
        """R17-A: anchor the constants to what the builtin DOES, not to what
        its tables say.

        Comparing the constants against `_SHOPT_NAMES`/`_SET_O_NAMES` catches
        drift in the tables, but both sides could agree and both be wrong
        about the resulting behavior — the cited-copy drift class. So each
        cell RUNS the real builtin from a known state and checks the option
        moved exactly when the constants predict it.

        The six cells reproduce the measurements the constants were written
        from: `shopt -s posix` is refused while `shopt -so posix` sets it, and
        the extglob mirror (psh and bash 5.2.26 agreeing on all six).
        """
        table = SET_O_TABLE_OPTIONS if o_flag else SHOPT_TABLE_OPTIONS
        predicted = option in table

        shell = Shell(norc=True)
        shell.state.options[option] = False
        shell.run_command(f"shopt -s{'o' if o_flag else ''} {option}")
        actual = bool(shell.state.options.get(option))

        assert actual == predicted, (
            f"`shopt -s{'o' if o_flag else ''} {option}` "
            f"{'set' if actual else 'did NOT set'} the option, but the "
            f"routing constants predict it "
            f"{'would' if predicted else 'would not'}. The constants no "
            "longer describe the builtin's behavior.")

    def test_the_two_routings_are_disjoint_for_threaded_options(self):
        """Stated as its own fact because the branch relies on it: an operand
        names one table or the other, never both."""
        assert not set(SHOPT_TABLE_OPTIONS) & set(SET_O_TABLE_OPTIONS)
        assert set(SHOPT_TABLE_OPTIONS) | set(SET_O_TABLE_OPTIONS) == set(
            PARSE_RELEVANT_OPTIONS)


class TestIsolationClassificationIsTotal:
    """Every node shape the walk can reach is classified, so a new one cannot
    arrive unseen.

    The session treats an unclassified node as STATE-PRESERVING, which is the
    safe default (more permissive, never a false syntax error) — but silent
    defaults are how coverage rots, so the classification is enumerated here.

    R15-B-G, the guard's UNIVERSE. This used to enumerate `CompoundCommand`
    subclasses, while `_directive_commands` classifies by TYPE NAME over every
    node `walk_ast` descends into. Two of the three isolating shapes
    (CommandSubstitution, ProcessSubstitution) are not CompoundCommands at
    all, so the universe did not even contain the answers the code was giving
    — and a NEW isolating shape outside the CompoundCommand tree would have
    arrived silently. The universe is now the traversal schema itself, which
    is exactly what the code walks.

    Two isolation rules are CONDITIONAL and so are not node-type facts: a
    Pipeline isolates only when it has more than one member, and any node
    isolates when it carries `background`. Both are asserted separately below.
    """

    #: Every schema node type that does NOT isolate state. Reviewed one by
    #: one: none of these runs its interior in a separate process or a
    #: throwaway copy of the shell state.
    STATE_PRESERVING = {
        "AndOrList", "ArithmeticEvaluation", "ArithmeticExpansion",
        "ArrayAssignment", "ArrayElementAssignment", "ArrayInitialization",
        "BinaryTestExpression", "BraceGroup", "CStyleForLoop",
        "CaseConditional", "CaseItem", "CasePattern",
        "CompoundTestExpression", "EnhancedTestStatement", "ExpansionPart",
        "ForLoop", "FunctionDef", "HeredocRedirect", "IfConditional",
        "LiteralPart", "NegatedTestExpression", "ParameterExpansion",
        "Pipeline", "Program", "Redirect", "SelectLoop", "SimpleCommand",
        "StatementList", "UnaryTestExpression", "UntilLoop",
        "VariableExpansion", "WhileLoop", "Word", "WordPart",
        # Not in the traversal schema, but a CompoundCommand subclass, so it
        # is classified here too rather than falling through the wider check.
        "UnifiedControlStructure",
    }

    @staticmethod
    def _all_compound_names():
        def descend(cls):
            for sub in cls.__subclasses__():
                yield sub.__name__
                yield from descend(sub)
        return set(descend(CompoundCommand))

    @staticmethod
    def _schema_node_names():
        from psh.visitor.traversal import AstChildSchema
        return set(AstChildSchema)

    def test_every_walkable_node_type_is_classified(self):
        """THE universe: what `walk_ast` descends into is what
        `_directive_commands` type-name-checks, so that is what must be
        classified."""
        classified = self.STATE_PRESERVING | set(ISOLATING_NODES)
        unclassified = self._schema_node_names() - classified
        assert not unclassified, (
            "new AST shape(s) reachable by the traversal but not classified "
            f"by the analysis session's isolation rule: {sorted(unclassified)}")

    def test_every_compound_command_is_classified(self):
        """The narrower universe is kept as well: a CompoundCommand subclass
        that never joined the traversal schema is still a shape the session
        can meet."""
        classified = self.STATE_PRESERVING | set(ISOLATING_NODES)
        unclassified = self._all_compound_names() - classified
        assert not unclassified, (
            "new compound AST shape(s) not classified by the analysis "
            f"session's isolation rule: {sorted(unclassified)}")

    def test_every_isolating_name_is_a_real_node_type(self):
        """A classification naming something that does not exist is a dead
        allowance — the stale-entry fault the string-surgery guard rejects,
        in the other direction."""
        known = self._schema_node_names() | self._all_compound_names()
        unknown = set(ISOLATING_NODES) - known
        assert not unknown, (
            f"ISOLATING_NODES names non-existent node type(s): {sorted(unknown)}")

    def test_isolating_and_preserving_do_not_overlap(self):
        assert not (self.STATE_PRESERVING & set(ISOLATING_NODES))

    def test_the_conditional_isolation_rules_hold(self):
        """The two rules that are not node-type facts: a multi-member pipeline
        isolates, a one-member pipeline does not, and `background` isolates."""
        shell = _shell("validate")
        # A directive inside a MULTI-member pipeline runs in its own process.
        session = AnalysisSession(shell)
        session.analyze("shopt -s extglob | cat\n")
        assert session.carrier.state.options.get("extglob") is not True
        # A ONE-member pipeline is just a command: its effect survives.
        session = AnalysisSession(_shell("validate"))
        session.analyze("shopt -s extglob\n")
        assert session.carrier.state.options.get("extglob") is True
        # Background isolates too.
        session = AnalysisSession(_shell("validate"))
        session.analyze("shopt -s extglob &\n")
        assert session.carrier.state.options.get("extglob") is not True


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

    #: R13-E9/R15-B-D: a wider no-option-change corpus for the FIVE-mode
    #: byte-identical claim. The F7 shape — a heredoc body followed by later
    #: commands — used to be EXCLUDED here, because the whole-file parse got
    #: the words after the body wrong. That was the C010 mechanism (a name
    #: taken from a source slice at a position the heredoc collection had
    #: already moved), closed in slot 1.7 of Improvement Program 2026-09, so
    #: the shape now belongs in the corpus as a positive row.
    PARITY_CORPUS = CORPUS + [
        "while read -r line; do\n  echo \"$line\"\ndone < f\n",
        "a=1\nb=$((a + 1))\necho \"$a $b\"\n",
        "( cd /tmp && echo sub )\n{ echo brace; }\n",
        "echo \"${x:-default}\"\necho 'literal $x'\n",
        "trap 'echo bye' EXIT\necho body\n",
        "usage() {\n    cat <<EOF\nabc\nEOF\n}\n"
        "for file in a b; do echo $file; done\n",
    ]

    @staticmethod
    def _render(shell, program):
        """Run the REAL mode runner and return (stdout, stderr, status).

        `contextlib.redirect_*` rather than pytest's capture fixture: the
        project's Output Capture Rules reserve that fixture for cases these
        visitors are not (they `print` at the Python level and touch no fds),
        and the fixture ratchet caps how many files may request it.
        """
        import contextlib
        import io

        from psh.scripting.visitor_modes import apply_visitor_mode

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = apply_visitor_mode(shell, program)
        return out.getvalue(), err.getvalue(), status

    @pytest.mark.parametrize("mode", ["validate", "format", "metrics",
                                      "security", "lint"])
    @pytest.mark.parametrize("source", PARITY_CORPUS)
    def test_every_mode_renders_byte_identically(self, mode, source):
        """The exit-code contract's other half: for input that changes no
        parse-relevant state, going per-unit must not move what ANY mode
        prints, byte for byte, nor the status it returns.

        The comparison drives the REAL mode runner over both programs rather
        than re-deriving each mode's rendering — the same reuse rule the code
        under test is held to.
        """
        shell = _shell(mode)
        expand = mode != "format"
        session = parse_for_analysis(shell, source)
        whole = _whole_file_parse(shell, source, expand_aliases=expand)

        session_out, session_err, session_status = self._render(shell, session)
        whole_out, whole_err, whole_status = self._render(shell, whole)

        assert session_out == whole_out, (
            f"{mode} stdout moved for a no-option-change script")
        assert session_err == whole_err, (
            f"{mode} stderr moved for a no-option-change script")
        assert session_status == whole_status

    def test_the_parity_comparison_can_actually_fail(self):
        """MUTATION PROOF: a comparison that never differs proves nothing.

        The discriminator is an ORDERED option change, the one thing the
        whole-file parse structurally cannot follow: it decides
        ``expand_aliases`` once for the whole input, while the shell really
        does stop expanding after ``shopt -u expand_aliases`` (bash 5.3.15,
        script mode: ``g`` after the unset reports ``g: command not found``,
        rc 127). So the two programs must DIFFER here, and the session's
        answer — the UNexpanded ``g`` — must be the correct one.

        This used to discriminate on the F7 shape (a heredoc body followed by
        later commands), which the whole-file parse got WRONG. That corruption
        was the C010 mechanism — a name read out of a source slice at a
        position heredoc collection had already moved — and it is gone as of
        slot 1.7 of Improvement Program 2026-09, so F7 no longer distinguishes
        anything and is a positive row in PARITY_CORPUS instead.
        """
        from psh.visitor import FormatterVisitor

        source = "alias g='echo G'\nshopt -u expand_aliases\ng\n"
        shell = _shell("format")
        session = parse_for_analysis(shell, source)
        # expand_aliases=True is what every non-format mode passes: the
        # whole-file parse commits to it before it can read the `shopt -u`.
        whole = _whole_file_parse(shell, source, expand_aliases=True)

        session_text = FormatterVisitor().visit(session)
        whole_text = FormatterVisitor().visit(whole)
        assert session_text != whole_text, (
            "the parity comparison cannot distinguish two programs")
        assert session_text.rstrip().endswith("\ng"), session_text
        assert whole_text.rstrip().endswith("\necho G"), whole_text


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

    def test_the_session_does_not_retain_the_analyzed_shell(self):
        """The session reads the parent shell only in ``__init__`` — to build
        the carrier and settle ``expand_aliases`` — and keeps no reference.

        It used to store ``self.shell`` and never read it back: a field handing
        every later method the whole shell the session deliberately does not
        use. Removed in remediation 5B.1; this pin keeps it removed, because
        the natural way to reach for the shell from a NEW method is to
        reintroduce exactly that field.
        """
        session = AnalysisSession(_shell("validate"))
        assert not hasattr(session, "shell"), (
            "AnalysisSession is holding the analyzed shell again — the carrier "
            "is the state the pipeline is meant to read")


class TestSingleAnalysisMode:
    """MEDIUM-9(b) at the constructor: the ambiguous state is unrepresentable."""

    def test_two_modes_is_a_construction_error(self):
        with pytest.raises(ValueError) as caught:
            Shell(norc=True, validate_only=True, lint_only=True)
        assert "validate_only" in str(caught.value)
        assert "lint_only" in str(caught.value)

    def test_the_construction_error_is_typed(self):
        """R15-B-G: a bare ValueError says only "something was wrong". The
        CLI spelling of this mistake already raises a named InvocationError;
        the keyword spelling now raises a named error too, so an embedder can
        catch exactly this and nothing else.

        It still SUBCLASSES ValueError, so an embedder's existing
        `except ValueError` keeps working — asserted here so that
        compatibility is a pinned property rather than a happy accident.
        """
        from psh.invocation import AnalysisModeConflictError

        with pytest.raises(AnalysisModeConflictError):
            Shell(norc=True, validate_only=True, lint_only=True)
        assert issubclass(AnalysisModeConflictError, ValueError)

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
        # N14: the superseded unqualified sentence must not come BACK. Only
        # certify.py asserted this absence, and certify.py is not part of the
        # suite — a resurrection would have shipped green.
        assert "Turning an option back off does not narrow the analysis" \
            not in text, (
                "the unqualified all-options-monotone sentence has returned; "
                "it is false for expand_aliases")

    def test_the_declared_cost_is_stated_in_user_facing_words(self):
        text = self.GUIDE.read_text()
        section = text[text.index("**Analysis follows the script's own settings.**"):]
        section = section[:section.index("### Parser Selection")]
        # The cost the branch pins must be findable by a reader who hit it.
        assert "shopt -u expand_aliases" in section
        assert "fails `--validate`" in section, (
            "the guide states the rule but not the consequence a user meets")


class TestNoUnsanctionedStringSurgery:
    """R11-A(2), the CLASS guard: after three instances, make a fourth fail.

    Three of this slot's seven verifier-found defects were the same fault —
    re-deriving, from raw text, something the pipeline already knew:

    * R8-A lexed heredoc bodies the lexer had already set aside;
    * R9-A re-walked tokens the alias decider already walks, losing its
      command-position guard;
    * R11-A stripped backslashes the LEXER had already classified as quoted or
      not, inventing directives out of `'sh\\opt'`.

    Every one passed review and passed a gate. What they have in common is
    string surgery on a value the lexer had already resolved, so this guard
    freezes the list of places this module is allowed to do that. Each entry
    names WHY the surgery is legitimate. A new site fails here until it is
    either replaced by a lexer-provided fact or justified in writing.

    This is a SANCTIONED-SITES guard, not a ban: some string handling is
    correct and unavoidable. The point is that adding one must be a decision
    somebody records, not a reflex nobody notices.
    """

    MODULE = "psh/scripting/analysis_session.py"

    #: (function, operation, COUNT) -> why this site is not a re-derivation.
    #:
    #: The count is part of the key (R13-E-5): keying on (function, operation)
    #: alone let a SECOND site of an already-sanctioned shape appear inside a
    #: sanctioned function without the guard noticing — the universe lesson
    #: again, one level down.
    #:
    #: Each justification must open with one of two TAGS (R13-E-6), because
    #: prose alone is satisfiable by boilerplate:
    #:   consumes-lexer-fact: <which fact>
    #:   no-fact-because:     <why the lexer cannot know it>
    SANCTIONED = {
        ('_effective_words', '.sub()', 1):
            "consumes-lexer-fact: part.quoted. APPLIES the lexer's verdict "
            "rather than replacing it: the "
            "backslash-escape substitution runs ONLY on parts the lexer marked "
            "unquoted (part.quoted is False). This is the one place the "
            "quoting fact is consumed, and everything downstream reads its "
            "output instead of raw token text.",
        ('_normalize_head', '.match()', 1):
            "consumes-lexer-fact: _effective_words output. "
            "Recognizes a NAME=value assignment prefix on an ALREADY "
            "quote-resolved word from _effective_words — a shape test on a "
            "resolved value, not a re-derivation of quoting.",
        ('<module>', '.startswith()', 1):
            "no-fact-because: there is no token here at all. Selects the "
            "`debug-*` entries out of OPTION_REGISTRY at import time — the "
            "operand is an option-registry KEY from a fixed internal "
            "vocabulary, never shell input, so no lexer fact exists or could "
            "apply. Deriving the family this way is what stops a new debug "
            "option from being missed by a hand-typed list.",
        ('_option_changes', 'slice', 2):
            "consumes-lexer-fact: _effective_words output. "
            "Drops the head word, and reads the LETTERS of an already "
            "quote-resolved `set -o`/`set +o` flag. Both operate on values "
            "whose spelling is fully determined once quoting is resolved.",
        ('_shopt_split', '.startswith()', 1):
            "consumes-lexer-fact: _effective_words output. "
            "Distinguishes a flag word from an operand on an already "
            "quote-resolved word. `-` is not quotable into or out of "
            "existence by anything the lexer hides: `\\-s` resolves to `-s` "
            "in _effective_words first (pinned).",
        ('_shopt_split', 'slice', 4):
            "consumes-lexer-fact: _effective_words output. "
            "Reads the LETTERS of an already quote-resolved cluster flag "
            "(`-sq` -> `sq`) and splits the argument list at the first "
            "operand. The split MIRRORS the builtin's own argument loop "
            "(psh/builtins/shell_options.py#ShoptBuiltin.execute), which is "
            "the decider for this grammar; what is tested is the shape of an "
            "already-resolved value, not a re-derivation of quoting.",
        ('analyze', '.strip()', 3):
            "no-fact-because: the decision happens BEFORE lexing, so there is "
            "no token yet. Operates on the UNIT'S RAW SOURCE TEXT, not on a token value — "
            "the blank/comment-only skip, mirroring the identical test in "
            "source_processor.iter_command_units. There is no lexer fact to "
            "consume here: the decision happens before lexing, by design.",
        ('analyze', '.startswith()', 1):
            "no-fact-because: same pre-lexing decision as the .strip() above. "
            "Same site as the .strip() above: the whole-line comment skip on "
            "raw source text, mirroring the execution path.",
    }

    TYPING_NAMES = {'List', 'Optional', 'Tuple', 'Sequence', 'Dict', 'Any',
                    'Mapping', 'Union', 'Set'}
    STR_METHODS = {'replace', 'strip', 'lstrip', 'rstrip', 'split',
                   'startswith', 'endswith', 'sub', 'match', 'find',
                   'partition', 'rpartition', 'removeprefix', 'removesuffix'}

    @classmethod
    def _sites(cls, source: str):
        tree = pyast.parse(source)
        funcs = [n for n in pyast.walk(tree)
                 if isinstance(n, (pyast.FunctionDef, pyast.AsyncFunctionDef))]

        def where(node):
            best = None
            for f in funcs:
                if f.lineno <= node.lineno <= (f.end_lineno or f.lineno):
                    if best is None or f.lineno > best.lineno:
                        best = f
            return best.name if best else '<module>'

        counts: dict = {}
        for node in pyast.walk(tree):
            key = None
            if (isinstance(node, pyast.Call)
                    and isinstance(node.func, pyast.Attribute)
                    and node.func.attr in cls.STR_METHODS):
                key = (where(node), f".{node.func.attr}()")
            elif (isinstance(node, pyast.Subscript)
                  and isinstance(node.slice, pyast.Slice)
                  and not (isinstance(node.value, pyast.Name)
                           and node.value.id in cls.TYPING_NAMES)):
                key = (where(node), "slice")
            if key is not None:
                counts[key] = counts.get(key, 0) + 1
        return {(fn, op, n) for (fn, op), n in counts.items()}

    def test_every_string_surgery_site_is_sanctioned(self):
        source = (Path(__file__).resolve().parents[3] / self.MODULE).read_text()
        found = self._sites(source)
        unsanctioned = found - set(self.SANCTIONED)
        assert not unsanctioned, (
            "new string-surgery site(s) in the analysis session: "
            f"{sorted(unsanctioned)}.\nThree of this slot's defects came from "
            "re-deriving what the lexer already knew. Either consume the "
            "lexer-provided fact instead, or add the site to SANCTIONED with "
            "a written justification.")

    def test_no_sanctioned_entry_has_gone_stale(self):
        """The list must not accumulate entries for code that is gone — a
        stale allowance is how a guard quietly stops guarding."""
        source = (Path(__file__).resolve().parents[3] / self.MODULE).read_text()
        found = self._sites(source)
        stale = set(self.SANCTIONED) - found
        assert not stale, f"SANCTIONED lists sites that no longer exist: {sorted(stale)}"

    def test_every_justification_is_substantive_and_tagged(self):
        """A one-word justification would satisfy the letter of the rule and
        none of its purpose; an untagged one lets prose stand in for a
        decision. Both are structurally rejected (R13-E-6)."""
        for site, why in self.SANCTIONED.items():
            assert len(why) >= 80, f"{site} justification is too thin: {why!r}"
            assert why.startswith(("consumes-lexer-fact:", "no-fact-because:")), (
                f"{site} justification must open with one of the two tagged "
                f"forms, got: {why[:40]!r}")

    def test_the_scan_detects_a_planted_site(self):
        """MUTATION PROOF: the guard must SEE a new site, not just pass."""
        planted = "def _sneaky(word):\n    return word.replace('\\\\', '')\n"
        found = self._sites(planted)
        assert ('_sneaky', '.replace()', 1) in found, found

    def test_a_second_site_of_a_sanctioned_shape_is_visible(self):
        """R13-E-5: the count is what makes a SECOND site of an already-allowed
        shape visible. Keyed on (function, operation) alone this would pass."""
        one = "def f(w):\n    return w.strip()\n"
        two = "def f(w):\n    return w.strip().strip()\n"
        assert self._sites(one) == {('f', '.strip()', 1)}
        assert self._sites(two) == {('f', '.strip()', 2)}

    def test_the_mirrored_line_is_not_inside_a_code_fence(self):
        """R13-E-1: the mutual-exclusion sentence mirrored into the second
        guide copy first landed INSIDE a fenced code block, where it renders
        as shell input rather than prose. Asserted structurally (fence parity
        before the line) because that is a property of the document, not of
        the edit that produced it."""
        guide = (Path(__file__).resolve().parents[3]
                 / "docs/user_guide/13_shell_scripts.md")
        lines = guide.read_text().splitlines()
        target = next(i for i, line in enumerate(lines)
                      if line.startswith("Only one analysis mode may be given"))
        fences = sum(1 for line in lines[:target] if line.startswith("```"))
        assert fences % 2 == 0, (
            "the mirrored line sits inside a fenced code block "
            f"({fences} fences open before line {target + 1})")
