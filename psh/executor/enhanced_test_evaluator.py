"""Test expression evaluator for [[ ]] constructs."""
import re
from typing import TYPE_CHECKING

from ..ast_nodes import (
    BinaryTestExpression,
    CompoundTestExpression,
    ExpansionPart,
    LiteralPart,
    NegatedTestExpression,
    TestExpression,
    UnaryTestExpression,
)
from ..builtins.test_command import TestBuiltin, variable_is_set
from ..core import IndexedArray, TestExpressionError, VarAttributes
from ..expansion.arithmetic import evaluate_arithmetic
from ..expansion.glob import translate_posix_classes
from ..expansion.operands import DQ_STRING, OperandValue
from ..expansion.pattern import match_shell_pattern
from ..expansion.pattern_words import expand_pattern_word
from ..expansion.word_expander import WordExpander
from ..utils.file_tests import file_newer_than, file_older_than, files_same

if TYPE_CHECKING:
    from ..protocols import LocaleAccess
    from ..shell import Shell


class TestExpressionEvaluator:
    """Evaluates [[ ]] test expressions using shell state for expansions."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.expansion_manager = shell.expansion_manager
        self.state = shell.state

    def _set_bash_rematch(self, match) -> None:
        """Set BASH_REMATCH from an `re` match (full match + capture groups)."""

        arr = IndexedArray()
        if match is not None:
            arr.set(0, match.group(0))
            for i, group in enumerate(match.groups(), start=1):
                arr.set(i, group if group is not None else '')
        self.state.scope_manager.set_variable(
            'BASH_REMATCH', arr, attributes=VarAttributes.ARRAY,
        )

    def evaluate(self, expr: TestExpression) -> bool:
        """Evaluate a test expression to boolean."""
        if isinstance(expr, BinaryTestExpression):
            return self._evaluate_binary_test(expr)
        elif isinstance(expr, UnaryTestExpression):
            return self.evaluate_unary_test(expr)
        elif isinstance(expr, CompoundTestExpression):
            return self._evaluate_compound_test(expr)
        elif isinstance(expr, NegatedTestExpression):
            return not self.evaluate(expr.expression)
        else:
            # Can't-happen: the parser only builds the node types handled
            # above. An INTERNAL DEFECT, not a user error — RuntimeError so
            # strict-errors surfaces it instead of the old `[[` VT net
            # reporting it as a user syntax error (MEDIUM-12b).
            raise RuntimeError(
                f"Unknown test expression type: {type(expr).__name__}")

    def _operand_string(self, word) -> str:
        """Expand a [[ ]] operand Word to its subject/literal string,
        QUOTE-AWARE per part (no word-splitting, no globbing). Shared by the
        binary operands and (G1, 2026-07-02) the unary operators, so a
        single-quoted operand (`[[ -n '$x' ]]`) stays literal in both.

        Backslash escapes are removed only from UNQUOTED parts (``ab\\?`` ->
        ``ab?``); a quoted part's text is already quote-removed by the lexer
        and is kept verbatim (so ``"a\\.c"`` stays the 4-char ``a\\.c``,
        bash). Tilde expands only on a leading unquoted literal. Variables
        are expanded per part (single-quoted ``$x`` is literal because the
        lexer made it a literal part). This replaces the former
        flatten-then-strip-all-backslashes path, which corrupted both quoted
        backslashes and pattern escapes."""

        out = []
        for i, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                out.append(self._literal_part_text(part, leading=(i == 0)))
            elif isinstance(part, ExpansionPart):
                # RULED TERMINAL CONSUMER: a [[ ]] operand is ONE string
                # (bash: `[[ ${x:-"$@"} == "a b" ]]` is true), so a value
                # operand's field vector is projected here by name.
                expanded = self.expansion_manager.expand_expansion(part.expansion)
                out.append(expanded.as_scalar()
                           if isinstance(expanded, OperandValue) else expanded)
        return ''.join(out)

    def _literal_part_text(self, part, leading: bool) -> str:
        """Expand one LiteralPart of a [[ ]] operand to its subject text.

        Double-quoted (and unquoted) parts still undergo variable expansion
        — the lexer stores ``$x`` as literal text inside a STRING token, so a
        quoted operand carries ``$x`` in a LiteralPart, not an ExpansionPart.
        Single-quoted parts are literal. Unquoted parts get tilde (leading)
        and backslash-escape removal; quoted-part text is otherwise verbatim
        (already quote-removed by the lexer)."""
        text = part.text
        if part.quote_char == "'":
            return text  # single-quoted: fully literal
        if part.quoted:
            # double-quoted literal (e.g. "$x" arrives as the literal text
            # $x): expand vars, then strip ONLY the double-quote escapes.
            return self._expand_dquote_literal(text)
        # unquoted literal: no embedded $ (expansions are separate
        # ExpansionParts); tilde on a leading literal, then escape removal.
        if leading and text.startswith('~'):
            text = self.expansion_manager.expand_tilde(text)
        return self._process_escape_sequences(text)

    def _expand_dquote_literal(self, text: str) -> str:
        """Expand one double-quoted [[ ]] literal part to its subject text.

        A double-quoted LiteralPart carries the lexer-decoded text with
        ``$var`` kept raw (``"$x"`` arrives as the literal text ``$x``).
        Expand its variables with SINGLE-decode (``lexed=True``, so a
        ``\\``-run is not collapsed a second time), then remove ONLY the
        double-quote escapes (``\\$ \\\\ \\" \\```); a backslash before
        anything else stays literal (so ``"a\\.c"`` keeps its backslash —
        bash). Shared by the operand-subject path (``_literal_part_text``)
        and the ``==``/``!=``/``=~`` RHS builders (``_rhs_walk``) so the
        ``[[ ]]`` double-quote recipe lives in one place and cannot drift.
        """
        expanded = self.expansion_manager.expand_string_variables(
            text, quote_ctx=DQ_STRING, lexed=True)
        return WordExpander.process_dquote_escapes(expanded)

    def _evaluate_binary_test(self, expr: BinaryTestExpression) -> bool:
        """Evaluate binary test expression."""
        # The LHS is always the subject string (no word-splitting, no
        # globbing of the operand itself); expand tilde + variables and
        # remove backslash escapes from unquoted parts (quote removal), like
        # bash — quote-aware so a quoted backslash stays literal.
        left = self._operand_string(expr.left_word)

        # For literal comparisons (=, <, >, numeric, file) the RHS is also a
        # plain expanded string. For pattern/regex operators (==, !=, =~) the
        # RHS pattern is built PER-PART from the Word so quoting is honored
        # segment by segment (quoted parts are literal, unquoted parts keep
        # their glob/regex power) — bash semantics a whole-operand flag could
        # not express.
        # ``right`` is the plain expanded RHS for literal/numeric/file
        # operators. The pattern/regex operators (==, !=, =~) build their RHS
        # per-part below and never read ``right``; default it to "" so it stays
        # typed ``str`` (those branches return before using it).
        if expr.operator in ('==', '!=', '=~'):
            right = ""  # built per-operator below; unused by these branches
        else:
            right = self._operand_string(expr.right_word)

        # Handle different operators
        if expr.operator == '=':
            return left == right
        elif expr.operator == '==':
            return self._pattern_match(left, self._rhs_pattern(expr.right_word))
        elif expr.operator == '!=':
            return not self._pattern_match(
                left, self._rhs_pattern(expr.right_word))
        elif expr.operator == '<':
            # bash's `[[ < ]]` honours LC_COLLATE; the locale service compares
            # by codepoint in the C locale (byte order) and by locale.strcoll
            # in a UTF-8/OTHER locale (so `[[ a < B ]]` is true under en_US.UTF-8,
            # matching bash).
            loc: 'LocaleAccess' = self.state.locale
            return loc.compare(left, right) < 0
        elif expr.operator == '>':
            loc = self.state.locale
            return loc.compare(left, right) > 0
        elif expr.operator == '=~':
            # Regex matching; populate BASH_REMATCH with the full match and
            # capture groups (cleared to an empty array on no match), like bash.
            # Quoted sub-parts are matched LITERALLY, unquoted parts are live
            # regex source (bash) — built per-part from the operand Word.
            # bash's ERE accepts POSIX classes ([[:punct:]]); Python's re does
            # not (and warns "Possible nested set"), so translate them via the
            # shared glob-engine table. Only the classes are shared — =~ is a
            # regex, not a glob, so no glob metacharacter handling is applied.
            # Under nocasematch bash uses REG_ICASE, which folds [[:upper:]]/
            # [[:lower:]] too (unlike ==/case), so no case protection here.
            regex_src = translate_posix_classes(self._rhs_regex(expr.right_word))
            flags = (re.IGNORECASE
                     if self.state.options.get('nocasematch', False) else 0)
            try:
                pattern = re.compile(regex_src, flags)
            except re.error as e:
                # USER-reachable ([[ x =~ [ ]]): typed at its detection point
                # so visit_EnhancedTestStatement can catch the user error
                # without a raw VT net (MEDIUM-12b). Message and status 2 are
                # unchanged (bash parity, probe-pinned).
                raise TestExpressionError(f"invalid regex: {e}") from e
            match = pattern.search(left)
            self._set_bash_rematch(match)
            return bool(match)
        elif expr.operator == '-eq':
            return self._arith_operand(left) == self._arith_operand(right)
        elif expr.operator == '-ne':
            return self._arith_operand(left) != self._arith_operand(right)
        elif expr.operator == '-lt':
            return self._arith_operand(left) < self._arith_operand(right)
        elif expr.operator == '-le':
            return self._arith_operand(left) <= self._arith_operand(right)
        elif expr.operator == '-gt':
            return self._arith_operand(left) > self._arith_operand(right)
        elif expr.operator == '-ge':
            return self._arith_operand(left) >= self._arith_operand(right)
        elif expr.operator == '-nt':
            return file_newer_than(left, right)
        elif expr.operator == '-ot':
            return file_older_than(left, right)
        elif expr.operator == '-ef':
            return files_same(left, right)
        else:
            # Can't-happen (the parser validates the operator set): an
            # INTERNAL DEFECT, see the note on `evaluate` above.
            raise RuntimeError(f"unknown binary operator: {expr.operator}")

    def _arith_operand(self, value: str) -> int:
        """Arithmetic-evaluate a ``-eq``/``-lt``/... operand.

        bash runs FULL arithmetic on numeric-operator operands —
        ``[[ 1+1 -eq 2 ]]``, ``x=3+4; [[ $x -eq 7 ]]``, recursive name
        resolution (``x=y; y=5; [[ x -eq 5 ]]``), base literals, array
        elements, even assignment side effects. The operand string is
        already $-expanded, so no rescan (``expand=False``): a residual
        literal ``$`` is a syntax error, like bash. Evaluation failures
        (``ShellArithmeticError``) surface as status 1 with a message —
        see ``visit_EnhancedTestStatement``.

        ``arith_source_quotes=False``: a ``[[`` numeric operand is a shell WORD
        that was already quote-processed by the shell (exactly like a ``let``
        arg), so an associative subscript inside it gets NO extra ``(( ))``
        round-1 dquote pass — ``h[q]=7; [[ h[\"q\"] -eq 7 ]]`` keys ``"q"`` (bash
        no), not ``q`` (CV1 B1 R1).
        """
        return evaluate_arithmetic(value, self.shell, expand=False,
                                   arith_source_quotes=False)

    def _rhs_pattern(self, word) -> str:
        """Glob pattern for a ``==``/``!=`` RHS.

        Delegates to the ONE pattern-word owner
        (``expansion/pattern_words.expand_pattern_word``), shared with
        ``case`` patterns: quoted parts are glob-escaped so they match
        literally, unquoted parts keep their live glob power, and the tilde
        rule is the command-word one — including the assignment-shaped value
        tilde bash applies here (C042)::

            env HOME=/h/me psh -c '[[ x=$HOME == x=~ ]] && echo eq'   # eq

        Feeds the canonical pattern engine (``_pattern_match``).
        """
        return self._rhs_word(
            word, escape=self.expansion_manager.variable_expander.glob_escape)

    def _rhs_regex(self, word) -> str:
        """Regex source for a ``=~`` RHS.

        The same owner as ``_rhs_pattern`` with ``re.escape`` in place of
        ``glob_escape``: quoted parts become literal regex text, unquoted
        parts stay live regex. bash expands a word-leading tilde in the regex
        operand too — probed against bash 5.3.15, which contradicts the
        docstring this method carried before v0.787.0 (C042)::

            env HOME=abc psh -c '[[ abc =~ ~ ]] && echo eq'    # eq
            env HOME=/h/me psh -c "[[ '~' =~ ~ ]] || echo ne"  # ne
        """
        return self._rhs_word(word, escape=re.escape)

    def _rhs_word(self, word, *, escape) -> str:
        """Run a ``[[ ]]`` RHS through the pattern-word owner.

        ``[[ ]]``'s lexer keeps ``$x`` as literal text inside a double-quoted
        LiteralPart (unlike ``case``, whose parser emits an ExpansionPart), so
        the owner is handed this evaluator's double-quote recipe
        (``_expand_dquote_literal``) for those parts.
        """
        return expand_pattern_word(
            word,
            manager=self.expansion_manager,
            escape=escape,
            dquote_literal=self._expand_dquote_literal)

    def _process_escape_sequences(self, text: str) -> str:
        """Process escape sequences in test expression operands."""
        if not text or '\\' not in text:
            return text

        result = []
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
            else:
                result.append(text[i])
                i += 1

        return ''.join(result)

    def _pattern_match(self, string: str, pattern: str) -> bool:
        """Match string against a shell pattern.

        Delegates to the canonical engine (expansion/pattern.py) so
        [[ == ]] cannot drift from case patterns and ${var#pat}.

        Extended-glob patterns (``a@(b|x)c``) are always honoured here:
        bash interprets ``?(``/``*(``/``+(``/``@(``/``!(`` in a ``[[ ]]``
        ``==``/``!=`` pattern operand independent of the ``extglob`` shopt
        (verified against bash with the option both on and off). The lexer
        likewise parses these groups unconditionally inside ``[[ ]]``
        (see ``recognizers/literal.extglob_active``).
        """
        return match_shell_pattern(
            string, pattern, extglob_enabled=True,
            ignorecase=self.state.options.get('nocasematch', False))

    def evaluate_unary_test(self, expr: UnaryTestExpression) -> bool:
        """Evaluate unary test expression."""
        # Handle -v operator specially since it needs shell state
        if expr.operator == '-v':
            operand = expr.operand  # Don't expand for -v, we want the variable name
            return self._is_variable_set(operand)

        # Expand the operand quote-aware from its Word (per-part quoting), the
        # SAME path as a binary operand's subject string: tilde/variables/
        # command/arithmetic, no splitting, no globbing — so a single-quoted
        # operand (`[[ -n '$x' ]]`) stays literal instead of being re-expanded.
        operand = self._operand_string(expr.operand_word)

        # Import test command's unary operators
        test_cmd = TestBuiltin()

        # Reuse the existing unary operator implementation
        # Note: evaluate_unary returns 0 for true, 1 for false (shell convention)
        result = test_cmd.evaluate_unary(expr.operator, operand, self.shell)
        return result == 0

    def _evaluate_compound_test(self, expr: CompoundTestExpression) -> bool:
        """Evaluate compound test expression with && or ||."""
        left_result = self.evaluate(expr.left)

        if expr.operator == '&&':
            if not left_result:
                return False
            return self.evaluate(expr.right)
        elif expr.operator == '||':
            if left_result:
                return True
            return self.evaluate(expr.right)
        else:
            # Can't-happen (only && and || are built here): an INTERNAL
            # DEFECT, see the note on `evaluate` above.
            raise RuntimeError(f"unknown compound operator: {expr.operator}")

    def _is_variable_set(self, var_ref: str) -> bool:
        """Check if a variable (or array element) is set — shared with the
        ``test``/``[`` builtin's ``-v`` operator."""
        return variable_is_set(self.shell, var_ref)
