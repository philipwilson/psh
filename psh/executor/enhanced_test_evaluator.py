"""Test expression evaluator for [[ ]] constructs."""
import re
from typing import TYPE_CHECKING

from ..ast_nodes import (
    BinaryTestExpression,
    CompoundTestExpression,
    NegatedTestExpression,
    TestExpression,
    UnaryTestExpression,
)

if TYPE_CHECKING:
    from ..shell import Shell


class TestExpressionEvaluator:
    """Evaluates [[ ]] test expressions using shell state for expansions."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.expansion_manager = shell.expansion_manager
        self.state = shell.state

    def _set_bash_rematch(self, match) -> None:
        """Set BASH_REMATCH from an `re` match (full match + capture groups)."""
        from ..core import IndexedArray, VarAttributes

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
            raise ValueError(f"Unknown test expression type: {type(expr).__name__}")

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
        from ..ast_nodes import ExpansionPart, LiteralPart

        out = []
        for i, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                out.append(self._literal_part_text(part, leading=(i == 0)))
            elif isinstance(part, ExpansionPart):
                out.append(self.expansion_manager.expand_expansion(part.expansion))
        return ''.join(out)

    def _literal_part_text(self, part, leading: bool) -> str:
        """Expand one LiteralPart of a [[ ]] operand to its subject text.

        Double-quoted (and unquoted) parts still undergo variable expansion
        — the lexer stores ``$x`` as literal text inside a STRING token, so a
        quoted operand carries ``$x`` in a LiteralPart, not an ExpansionPart.
        Single-quoted parts are literal. Unquoted parts get tilde (leading)
        and backslash-escape removal; quoted-part text is otherwise verbatim
        (already quote-removed by the lexer)."""
        from ..expansion.word_expander import WordExpander

        text = part.text
        if part.quote_char == "'":
            return text  # single-quoted: fully literal
        if part.quoted:
            # double-quoted literal text (e.g. "$x" arrives as the literal
            # text "$x"): expand variables, then remove ONLY the double-quote
            # escapes (\$ \\ \" \`); a backslash before anything else stays
            # literal (so "a\.c" keeps its backslash — bash).
            from ..expansion.operands import DQ_STRING
            expanded = self.expansion_manager.expand_string_variables(
                text, quote_ctx=DQ_STRING)
            return WordExpander.process_dquote_escapes(expanded)
        # unquoted literal: no embedded $ (expansions are separate
        # ExpansionParts); tilde on a leading literal, then escape removal.
        if leading and text.startswith('~'):
            text = self.expansion_manager.expand_tilde(text)
        return self._process_escape_sequences(text)

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
            # Unicode codepoint order. bash's `[[ < ]]` honours LC_COLLATE, so
            # this diverges from bash in a non-C locale (a known limitation —
            # `[ < ]`/test uses codepoint order too; see builtins/test_command.py).
            return left < right
        elif expr.operator == '>':
            return left > right
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
            from ..expansion.glob import translate_posix_classes
            regex_src = translate_posix_classes(self._rhs_regex(expr.right_word))
            flags = (re.IGNORECASE
                     if self.state.options.get('nocasematch', False) else 0)
            try:
                pattern = re.compile(regex_src, flags)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}") from e
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
            from ..utils.file_tests import file_newer_than
            return file_newer_than(left, right)
        elif expr.operator == '-ot':
            from ..utils.file_tests import file_older_than
            return file_older_than(left, right)
        elif expr.operator == '-ef':
            from ..utils.file_tests import files_same
            return files_same(left, right)
        else:
            raise ValueError(f"unknown binary operator: {expr.operator}")

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
        """
        from ..expansion.arithmetic import evaluate_arithmetic
        return evaluate_arithmetic(value, self.shell, expand=False)

    def _rhs_pattern(self, word) -> str:
        """Build the glob pattern for a ``==``/``!=`` RHS from its Word parts.

        Per-part quoting (bash): a quoted part contributes LITERAL text
        (glob-escaped so its metacharacters match themselves), an unquoted
        part keeps its glob power. Variables are expanded per part — an
        unquoted variable's value is a live glob (``p='a*'; [[ x == $p ]]``),
        a quoted one is literal (``[[ x == "$p" ]]``). The result feeds the
        canonical pattern engine (``_pattern_match``) so ``[[ == ]]`` cannot
        drift from case patterns / ``${var#pat}``."""
        from ..ast_nodes import ExpansionPart, LiteralPart
        from ..expansion.word_expander import WordExpander

        ve = self.expansion_manager.variable_expander
        out = []
        for i, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                if part.quote_char == "'":
                    out.append(ve.glob_escape(part.text))
                elif part.quoted:
                    # double-quoted literal: expand vars, strip dquote
                    # escapes, then glob-escape (literal).
                    from ..expansion.operands import DQ_STRING
                    expanded = WordExpander.process_dquote_escapes(
                        self.expansion_manager.expand_string_variables(
                            part.text, quote_ctx=DQ_STRING))
                    out.append(ve.glob_escape(expanded))
                else:
                    # unquoted literal: no embedded $; keep raw text so the
                    # pattern engine sees its glob metacharacters and any
                    # user backslash escapes (\*). Tilde on a leading literal.
                    text = part.text
                    if i == 0 and text.startswith('~'):
                        text = self.expansion_manager.expand_tilde(text)
                    out.append(text)
            elif isinstance(part, ExpansionPart):
                from ..expansion.operands import DQ_WORD
                expanded = self.expansion_manager.expand_expansion(
                    part.expansion,
                    quote_ctx=DQ_WORD if part.quoted else None)
                out.append(ve.glob_escape(expanded) if part.quoted else expanded)
        return ''.join(out)

    def _rhs_regex(self, word) -> str:
        """Build the regex source for a ``=~`` RHS from its Word parts.

        Per-part (bash): a quoted part is matched literally (``re.escape``);
        an unquoted part is live regex source. Variables are expanded; an
        unquoted variable's value is live regex, a quoted one is literal."""
        from ..ast_nodes import ExpansionPart, LiteralPart
        from ..expansion.word_expander import WordExpander

        out = []
        for part in word.parts:
            if isinstance(part, LiteralPart):
                if part.quote_char == "'":
                    out.append(re.escape(part.text))
                elif part.quoted:
                    from ..expansion.operands import DQ_STRING
                    expanded = WordExpander.process_dquote_escapes(
                        self.expansion_manager.expand_string_variables(
                            part.text, quote_ctx=DQ_STRING))
                    out.append(re.escape(expanded))
                else:
                    # unquoted literal: no embedded $; live regex source. A
                    # backslash escape (\.) keeps quoting the next char (re).
                    out.append(part.text)
            elif isinstance(part, ExpansionPart):
                from ..expansion.operands import DQ_WORD
                expanded = self.expansion_manager.expand_expansion(
                    part.expansion,
                    quote_ctx=DQ_WORD if part.quoted else None)
                out.append(re.escape(expanded) if part.quoted else expanded)
        return ''.join(out)

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
        from ..expansion.pattern import match_shell_pattern
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
        from ..builtins.test_command import TestBuiltin
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
            raise ValueError(f"unknown compound operator: {expr.operator}")

    def _is_variable_set(self, var_ref: str) -> bool:
        """Check if a variable (or array element) is set — shared with the
        ``test``/``[`` builtin's ``-v`` operator."""
        from ..builtins.test_command import variable_is_set
        return variable_is_set(self.shell, var_ref)
