"""Unit pins for the S2 heredoc transaction (boundary campaign).

The canonical representations and chokepoints:

* ``HeredocSpec`` (ordinal identity, raw/cooked/quoted/strip_tabs/span) —
  sole constructor ``make_heredoc_spec``, cooked derived only through
  ``unquote_heredoc_delimiter``;
* ``PendingHeredocQueue.feed_line`` — THE head-of-queue close decision
  (red-on-base: both completeness oracles used to close ANY matching open
  delimiter, #20 H1 / #21 G1);
* ``CollectedHeredoc`` with typed ``HeredocTermination``;
* the immutable ``LexedUnit(tokens, heredocs)`` lexer/parser boundary with
  id-stamped operator tokens;
* both parsers take delimiter truth from the spec entry (``Redirect.target``
  is the RAW spelling — red-on-base: ``<<$X`` used to lose its ``$``);
* the formatter emits the raw spelling (red-on-base: ``<<$X`` formatted as
  ``<<X``) with the COOKED terminator line in the body trailer;
* a heredoc redirect executing without a collected body is a loud internal
  error, never a silent empty document.

All pins are order-independent (no shared state between tests).
"""

import contextlib
import io

import pytest

from psh.lexer import tokenize_with_heredocs
from psh.lexer.heredoc_collector import HeredocCollector
from psh.lexer.heredoc_lexer import HeredocLexer, LexedHeredoc, LexedUnit
from psh.lexer.token_types import TokenType
from psh.utils.heredoc_detection import (
    CollectedHeredoc,
    HeredocTermination,
    PendingHeredocQueue,
    make_heredoc_spec,
)


def _spec(ordinal, raw, strip_tabs=False):
    return make_heredoc_spec(ordinal, raw, strip_tabs)


class TestPendingHeredocQueue:
    """The head-of-queue close policy (sole close decision)."""

    def test_later_delimiter_line_is_body_not_close(self):
        # The H1/G1 pin: a line equal to a LATER pending delimiter must NOT
        # close it — only the head is ever compared.
        q = PendingHeredocQueue()
        q.push(_spec(0, 'A'))
        q.push(_spec(1, 'B'))
        assert q.feed_line('B') is None          # body of A
        assert len(q) == 2 and q.head.cooked == 'A'
        closed = q.feed_line('A')
        assert closed is not None and closed.id == 0
        assert q.head.cooked == 'B'
        closed = q.feed_line('B')
        assert closed is not None and closed.id == 1
        assert not q

    def test_strip_tabs_is_the_heads_own_policy(self):
        q = PendingHeredocQueue()
        q.push(_spec(0, 'A', strip_tabs=True))
        q.push(_spec(1, 'B'))
        assert q.feed_line('\tB') is None        # tab-stripped 'B' != 'A'
        assert q.feed_line('\tA').id == 0        # <<- strips head's tabs
        assert q.feed_line('\tB') is None        # B is NOT tab-stripping
        assert q.feed_line('B').id == 1

    def test_duplicate_delimiters_are_distinct_ordinals(self):
        q = PendingHeredocQueue()
        q.push(_spec(0, 'A'))
        q.push(_spec(1, 'A'))
        first = q.feed_line('A')
        second = q.feed_line('A')
        assert (first.id, second.id) == (0, 1)

    def test_drain_returns_remaining_in_order(self):
        q = PendingHeredocQueue()
        q.push(_spec(0, 'A'))
        q.push(_spec(1, 'B'))
        assert [s.id for s in q.drain()] == [0, 1]
        assert not q and q.head is None

    def test_empty_queue_feed_line_is_none(self):
        assert PendingHeredocQueue().feed_line('anything') is None


class TestHeredocSpec:
    """The sole spec constructor derives cooked/quoted through the one rule."""

    def test_frozen(self):
        import dataclasses
        spec = _spec(0, "'EOF'")
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.raw = 'other'  # type: ignore[misc]

    @pytest.mark.parametrize("raw,cooked,quoted", [
        ("EOF", "EOF", False),
        ("'EOF'", "EOF", True),
        ("$'EOF'", "EOF", True),
        ("$'E\\tF'", "E\tF", True),
        ('$"EOF"', "EOF", True),
        ("$X", "$X", False),
        ("<(x)", "<(x)", False),
        ('E"O"F', "EOF", True),
    ])
    def test_cooked_via_one_rule(self, raw, cooked, quoted):
        spec = make_heredoc_spec(3, raw, True, (10, 10 + len(raw)))
        assert (spec.id, spec.raw, spec.cooked, spec.quoted,
                spec.strip_tabs, spec.span) == \
            (3, raw, cooked, quoted, True, (10, 10 + len(raw)))


class TestHeredocCollector:
    """The FIFO collector: typed termination, ordinal routing, EOF policy."""

    def test_delimiter_termination(self):
        c = HeredocCollector()
        c.register_heredoc('EOF', False, line=1)
        assert c.collect_line('hello', 2) is None
        assert c.collect_line('EOF', 3) == 0
        got = c.collected[0]
        assert isinstance(got, CollectedHeredoc)
        assert got.body == 'hello\n'
        assert got.termination is HeredocTermination.DELIMITER
        assert got.span == (1, 2)

    def test_duplicate_delimiters_route_by_ordinal(self):
        # The retired string keys embedded the delimiter TEXT; two heredocs
        # sharing a delimiter misfiled content. Ordinal identity cannot.
        c = HeredocCollector()
        c.register_heredoc('A', False, line=1)
        c.register_heredoc('A', False, line=1)
        c.collect_line('first', 2)
        assert c.collect_line('A', 3) == 0
        c.collect_line('second', 4)
        assert c.collect_line('A', 5) == 1
        assert c.collected[0].body == 'first\n'
        assert c.collected[1].body == 'second\n'

    def test_eof_termination_and_body_routing(self):
        # bash: the FIRST pending heredoc keeps everything gathered; later
        # pending heredocs get empty bodies. The typed EOF outcome is
        # recorded on both.
        c = HeredocCollector()
        c.register_heredoc('A', False, line=1)
        c.register_heredoc('B', False, line=1)
        c.collect_line('gathered', 2)
        warnings = c.finalize_at_eof(2)
        assert [(spec.cooked, line) for spec, line in warnings] == \
            [('A', 1), ('B', 2)]
        assert c.collected[0].termination is HeredocTermination.EOF
        assert c.collected[0].body == 'gathered\n'
        assert c.collected[1].termination is HeredocTermination.EOF
        assert c.collected[1].body == ''

    def test_strip_tabs_strips_body_lines(self):
        c = HeredocCollector()
        c.register_heredoc('EOF', True, line=1)
        c.collect_line('\tindented', 2)
        c.collect_line('\tEOF', 3)
        assert c.collected[0].body == 'indented\n'


class TestLexedUnitBoundary:
    """The immutable lexer/parser boundary."""

    def test_shape_and_id_stamping(self):
        unit = tokenize_with_heredocs('cat <<A <<A\nx\nA\ny\nA\n')
        assert isinstance(unit, LexedUnit)
        assert isinstance(unit.tokens, tuple)
        ops = [t for t in unit.tokens
               if t.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP)]
        assert [t.heredoc_id for t in ops] == [0, 1]
        assert sorted(unit.heredocs) == [0, 1]
        assert all(isinstance(e, LexedHeredoc) for e in unit.heredocs.values())
        assert unit.heredocs[0].collected.body == 'x\n'
        assert unit.heredocs[1].collected.body == 'y\n'
        with pytest.raises(TypeError):
            unit.heredocs[0] = None  # type: ignore[index]

    def test_trial_records_typed_eof_without_warning(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            lexer = HeredocLexer('cat <<EOF\nbody\n', warn_unterminated=False)
            unit = lexer.tokenize_with_heredocs()
        entry = unit.heredocs[0]
        assert entry.collected.termination is HeredocTermination.EOF
        assert entry.collected.body == 'body\n'
        assert err.getvalue() == ''

    def test_post_lex_fuses_against_stripped_command_text(self):
        # Red-on-base: fusion sliced the BODY-BEARING input at stripped-text
        # offsets, so a fused word after a heredoc body got a corrupted
        # value ('hen e'). The LexedUnit's post-lex source is the command
        # text the spans index.
        src = 'if cat <<EOF\nbody\nEOF\nthen echo a"b"c; fi'
        tokens, _ = tokenize_with_heredocs(src)
        fused = [t for t in tokens if t.value == 'a"b"c']
        assert len(fused) == 1, [t.value for t in tokens]

    def test_spec_raw_from_source_span(self):
        unit = tokenize_with_heredocs("cat <<$'EOF' <<E$X\na\nEOF\nb\nE$X\n")
        assert unit.heredocs[0].spec.raw == "$'EOF'"
        assert unit.heredocs[0].spec.cooked == 'EOF'
        assert unit.heredocs[0].spec.quoted is True
        assert unit.heredocs[1].spec.raw == 'E$X'
        assert unit.heredocs[1].spec.cooked == 'E$X'
        assert unit.heredocs[1].spec.quoted is False


class TestParserSpecTruth:
    """Both parsers take raw/quoted/body from the spec entry by id."""

    @staticmethod
    def _heredoc_redirects(ast):
        from psh.ast_nodes import Redirect
        found = []

        def walk(node):
            if isinstance(node, Redirect) and node.type in ('<<', '<<-'):
                found.append(node)
            for attr in vars(node).values() if hasattr(node, '__dict__') else ():
                if isinstance(attr, list):
                    for item in attr:
                        if hasattr(item, '__dict__'):
                            walk(item)
                elif hasattr(attr, '__dict__'):
                    walk(attr)
        walk(ast)
        return found

    @pytest.mark.parametrize("active", ['rd', 'combinator'])
    def test_raw_target_and_spec_quoted(self, active):
        from psh.parser import parse_with_heredocs
        tokens, heredocs = tokenize_with_heredocs("cat <<$X\nbody\n$X\n")
        ast = parse_with_heredocs(tokens, heredocs, active_parser=active)
        red = self._heredoc_redirects(ast)[0]
        assert red.target == '$X'          # RAW spelling (was 'X' on base)
        assert red.heredoc_quoted is False
        assert red.heredoc_content == 'body\n'
        assert red.heredoc_id == 0

    @pytest.mark.parametrize("active", ['rd', 'combinator'])
    def test_quoted_raw_target(self, active):
        from psh.parser import parse_with_heredocs
        tokens, heredocs = tokenize_with_heredocs("cat <<$'EOF'\nb\nEOF\n")
        ast = parse_with_heredocs(tokens, heredocs, active_parser=active)
        red = self._heredoc_redirects(ast)[0]
        assert red.target == "$'EOF'"
        assert red.heredoc_quoted is True
        assert red.heredoc_content == 'b\n'

    def test_bare_parse_derives_quoted_via_one_rule(self):
        # No collected map: raw from source_text span; quoted via unquote —
        # not the retired STRING-or-backslash token heuristic.
        from psh.lexer import tokenize
        from psh.parser import Parser
        src = "cat <<'EOF'"
        ast = Parser(tokenize(src), source_text=src).parse()
        red = self._heredoc_redirects(ast)[0]
        assert red.target == "'EOF'"
        assert red.heredoc_quoted is True
        assert red.heredoc_content is None  # bare parse: nothing collected


class TestFormatterRawEmission:
    """The formatter emits the RAW delimiter; trailer uses the cooked one."""

    @staticmethod
    def _format(src):
        from psh.parser import parse_with_heredocs
        from psh.visitor.formatter_visitor import FormatterVisitor
        tokens, heredocs = tokenize_with_heredocs(src)
        return FormatterVisitor().visit(
            parse_with_heredocs(tokens, heredocs))

    def test_dollar_delimiter_round_trips(self):
        # Red-on-base: `<<$X` formatted as `<<X` (H3's formatter half).
        out = self._format('cat <<$X\nbody\n$X\n')
        assert '<<$X' in out
        assert out.splitlines()[-1] == '$X'

    def test_ansi_c_raw_kept_with_cooked_terminator(self):
        out = self._format("cat <<$'EOF'\nbody\nEOF\n")
        assert "<<$'EOF'" in out
        assert out.splitlines()[-1] == 'EOF'   # trailer is COOKED

    def test_quoted_suppression_preserved_via_raw(self):
        out = self._format("cat <<'EOF'\n$x\nEOF\n")
        assert "<<'EOF'" in out
        assert out.splitlines()[-1] == 'EOF'

    def test_strip_tabs_operator_preserved(self):
        out = self._format('cat <<-EOF\n\tbody\n\tEOF\n')
        assert '<<-EOF' in out

    @pytest.mark.parametrize("raw", [
        '$X', "$'EOF'", '"EOF"', 'E"O"F', "'EOF'", '<(x)',
    ])
    def test_raw_spelling_preserved_verbatim(self, raw):
        # Every delimiter spelling re-emits VERBATIM — no cooked emission,
        # no re-quote approximation (a single-quote re-wrap of the cooked
        # terminator loses `$'…'`/`"…"`/composite spellings).
        cooked_line = {'$X': '$X', "$'EOF'": 'EOF', '"EOF"': 'EOF',
                       'E"O"F': 'EOF', "'EOF'": 'EOF', '<(x)': '<(x)'}[raw]
        # A procsub-shaped delimiter needs the space (`<<<(x)` would be a
        # here-string); other spellings glue directly to the operator.
        sep = ' ' if raw.startswith('<') else ''
        out = self._format(f'cat <<{sep}{raw}\nbody\n{cooked_line}\n')
        assert f'<<{sep}{raw}' in out

    def test_format_reparse_fixpoint(self):
        for src in ('cat <<$X\nbody\n$X\n',
                    "cat <<$'EOF'\nb $y\nEOF\n",
                    "cat <<'EOF'\n$x\nEOF\n",
                    'cat <<-EOF\n\tb\n\tEOF\n',
                    'cat <<E"O"F\nb\nEOF\n'):
            once = self._format(src)
            twice = self._format(once + '\n')
            assert once == twice, src


class TestExecutableBodyPresence:
    """A heredoc redirect with no collected body is a loud internal error."""

    def test_executor_raises_on_missing_body(self, captured_shell):
        from psh.ast_nodes import Redirect
        redirect = Redirect(type='<<', target='EOF', heredoc_content=None)
        with pytest.raises(RuntimeError, match='without a collected body'):
            captured_shell.io_manager.file_redirector.redirect_heredoc(
                redirect)

    def test_empty_body_is_not_an_error(self, captured_shell):
        rc = captured_shell.run_command('cat <<EOF\nEOF\necho ok')
        assert rc == 0
        assert captured_shell.get_stdout() == 'ok\n'


class TestAccumulatorQueueDelegation:
    """The completeness oracle routes body lines through the queue head."""

    def test_feed_sequence_head_only(self, captured_shell):
        from psh.scripting.command_accumulator import (
            CommandAccumulator,
            Complete,
            HintKind,
            NeedMore,
        )
        acc = CommandAccumulator(captured_shell)
        r = acc.feed('cat <<A <<B')
        assert isinstance(r, NeedMore) and r.hint.kind is HintKind.HEREDOC
        assert r.hint.detail == 'A'
        r = acc.feed('B')                      # body of A, not a close of B
        assert isinstance(r, NeedMore) and r.hint.detail == 'A'
        r = acc.feed('A')                      # closes A; B now the head
        assert isinstance(r, NeedMore) and r.hint.detail == 'B'
        r = acc.feed('B')                      # closes B -> complete
        assert isinstance(r, Complete)

    def test_hint_detail_is_cooked_terminator(self, captured_shell):
        from psh.scripting.command_accumulator import (
            CommandAccumulator,
            HintKind,
            NeedMore,
        )
        acc = CommandAccumulator(captured_shell)
        r = acc.feed("cat <<$'EOF'")
        assert isinstance(r, NeedMore) and r.hint.kind is HintKind.HEREDOC
        assert r.hint.detail == 'EOF'          # cooked, not $'EOF'
