"""
AST formatter visitor that pretty-prints AST nodes.

This visitor demonstrates how to traverse the AST and produce formatted output,
useful for debugging and understanding AST structure.
"""

from ..ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    # Word/expansion nodes
    ArithmeticExpansion,
    ArrayElementAssignment,
    # Array nodes
    ArrayInitialization,
    # Core nodes
    ASTNode,
    BinaryTestExpression,
    BraceGroup,
    CaseConditional,
    # Case statement components
    CaseItem,
    CasePattern,
    CommandSubstitution,
    CompoundTestExpression,
    CStyleForLoop,
    EnhancedTestStatement,
    ExpansionPart,
    ForLoop,
    # Function and test nodes
    FunctionDef,
    IfConditional,
    LiteralPart,
    NegatedTestExpression,
    ParameterExpansion,
    Pipeline,
    ProcessSubstitution,
    Program,
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    UnaryTestExpression,
    UntilLoop,
    VariableExpansion,
    # Control structures
    WhileLoop,
    Word,
)
from .base import ASTVisitor
from .formatter_quoting import (
    escape_ansi_c,
    escape_double_quoted,
    format_word_list_item,
    quote_scalar,
)


class FormatterVisitor(ASTVisitor[str]):
    """
    Visitor that formats AST nodes as readable text.

    This visitor can be used to:
    - Pretty-print AST structure for debugging
    - Generate shell script from AST
    - Display formatted command output
    """

    def __init__(self, indent: int = 2):
        """
        Initialize the formatter.

        Args:
            indent: Number of spaces per indentation level
        """
        super().__init__()
        self.indent = indent
        self.level = 0
        # Heredoc bodies queued for the current physical line. A command with
        # a ``<<DELIM`` registers its body+delimiter here (bash places them on
        # the lines AFTER the whole logical line, not inline); the line's
        # completing site flushes them via ``_flush_line`` — see J2.
        self._pending_heredocs: list = []

    def _indent(self) -> str:
        """Get current indentation string."""
        return ' ' * (self.level * self.indent)

    def _increase_indent(self):
        """Increase indentation level."""
        self.level += 1

    def _decrease_indent(self):
        """Decrease indentation level."""
        self.level = max(0, self.level - 1)

    def _format_inline(self, node) -> str:
        """Render a node on one line, with no leading indent.

        Used for control-structure headers, where the loop/conditional
        keyword, its condition list, and the following ``then``/``do``
        share a single line (``if cmd; then``, ``while cmd; do``). A
        multi-command condition (``if a; b; then``) renders its statements
        joined with ``; ``.
        """
        saved = self.level
        self.level = 0
        try:
            if isinstance(node, StatementList):
                parts = [self.visit(s).strip() for s in node.statements]
                return '; '.join(p for p in parts if p)
            return self.visit(node).strip()
        finally:
            self.level = saved

    @staticmethod
    def _needs_brace_disambiguation(part, next_part) -> bool:
        """Whether a bare ``$name`` must be written ``${name}`` to round-trip.

        ``$x`` immediately followed by an UNQUOTED name-continuation char
        (``${x}there`` parsed to VariableExpansion(x) + literal "there") would
        re-emit as ``$xthere`` — a different variable. A following QUOTE or
        ``$`` already delimits the name, so braces are needed only before an
        unquoted literal that starts with ``[A-Za-z0-9_]``.
        """
        if not (isinstance(part, ExpansionPart)
                and isinstance(part.expansion, VariableExpansion)):
            return False
        if not isinstance(next_part, LiteralPart) or getattr(next_part, 'quoted', False):
            return False
        return bool(next_part.text) and (next_part.text[0].isalnum()
                                         or next_part.text[0] == '_')

    @staticmethod
    def _format_word(word) -> str:
        """Format a Word by reconstructing from its parts with quoting.

        Groups consecutive parts that share the same quote context so
        that ``"$HOME/bin"`` is emitted as one quoted region rather than
        ``"$HOME""/bin"``. Preserves brace-disambiguation (``${x}there``) and
        re-escapes double-quoted literals so the output re-parses identically.
        """
        parts = word.parts
        # Group consecutive parts by their quote context, keeping each part so
        # literals can be re-escaped (only literals; an expansion is live text).
        groups: list = []  # [(quote_char_or_None, [(part, text), ...])]
        for i, part in enumerate(parts):
            qc = getattr(part, 'quote_char', None) if getattr(part, 'quoted', False) else None
            next_part = parts[i + 1] if i + 1 < len(parts) else None
            if FormatterVisitor._needs_brace_disambiguation(part, next_part):
                text = '${' + part.expansion.name + '}'
            else:
                text = str(part)
            if groups and groups[-1][0] == qc:
                groups[-1][1].append((part, text))
            else:
                groups.append((qc, [(part, text)]))

        result: list = []
        for qc, items in groups:
            if qc == '"':
                content = ''.join(
                    escape_double_quoted(text)
                    if isinstance(part, LiteralPart) else text
                    for part, text in items)
                result.append(f'"{content}"')
            elif qc == "$'":
                content = ''.join(
                    escape_ansi_c(text)
                    if isinstance(part, LiteralPart) else text
                    for part, text in items)
                result.append("$'" + content + "'")
            elif qc:  # single quote (literal content, no escaping)
                result.append(f"{qc}{''.join(t for _, t in items)}{qc}")
            else:
                result.append(''.join(t for _, t in items))
        return ''.join(result)

    # Top-level nodes

    def visit_Program(self, node: Program) -> str:
        """Format a program (the canonical root): one statement per line.

        Statements are joined by a single newline, with each statement's
        queued heredoc bodies flushed after its physical line (same mechanics
        as :meth:`visit_StatementList`). There is deliberately NO blank-line
        ("paragraph") separator between statements:

        A background ``&`` is the sole terminator that ends one statement
        without a ``;``/newline, so it is the only place a blank-line paragraph
        separator could ever have applied — but a blank line after ``&`` is
        non-idempotent (re-parsing ``a &\\n\\nb`` collapses it), so those
        adjacencies also render with a single newline. Every adjacency
        therefore renders with one ``\\n``. A statement's ``&`` still comes from
        its own background flag — rendered by
        ``visit_SimpleCommand``/``visit_AndOrList`` — never from the container
        shape. This keeps ``format(format(x)) == format(x)``.
        """
        parts = [self._flush_line(self.visit(stmt)) for stmt in node.statements]
        return '\n'.join(parts)

    def visit_StatementList(self, node: StatementList) -> str:
        """Format a list of statements.

        Each statement is a physical line: after rendering it, flush any
        heredoc bodies its commands queued, so `cat <<EOF && echo x` puts the
        body+delimiter after the WHOLE line (J2). Compound statements flush
        their own condition/body/trailer heredocs internally, leaving nothing
        pending here.
        """
        parts = []
        for stmt in node.statements:
            parts.append(self._flush_line(self.visit(stmt)))
        return '\n'.join(parts)

    # Command nodes

    def visit_SimpleCommand(self, node: SimpleCommand) -> str:
        """Format a simple command.

        Heredoc bodies are NOT emitted here: they are queued via
        ``_register_heredocs`` and flushed after the whole physical line
        (which may continue with ``&& …``, ``; then``, a pipe, …) by the
        enclosing statement/header site — see ``_flush_line`` (J2).
        """
        parts = []

        # Array assignments
        for assignment in node.array_assignments:
            parts.append(self.visit(assignment))

        # Command and arguments — reconstruct from Word parts to
        # preserve per-part quoting in composite words.
        words = node.words if node.words else []
        for i, arg in enumerate(node.args):
            word = words[i] if i < len(words) else None
            if word is not None and word.array_init is not None:
                # An argument-position array initializer (`declare -A m=(...)`).
                # Render from the structured element Words, not the word's flat
                # literal — the flat string re-serializes tokens and mangles a
                # `$'...'` element (J3/J6).
                parts.append(self.visit(word.array_init))
            elif word and word.parts:
                parts.append(self._format_word(word))
            else:
                parts.append(arg)

        # Redirections
        for redirect in node.redirects:
            parts.append(self.visit(redirect))

        # Background
        if node.background:
            parts.append('&')

        self._register_heredocs(node.redirects)
        return self._indent() + ' '.join(parts)

    def visit_Pipeline(self, node: Pipeline) -> str:
        """Format a pipeline.

        A single-command pipeline is the AST's transparent wrapper around
        every statement — including compound commands (``if``/``while``/
        ``case``/groups), which render across multiple lines. Delegate to
        the command so it keeps its own indentation; only a true multi-stage
        pipeline flattens its stages onto one line joined by ``' | '`` (which
        is why the inline path resets the indent level to 0). Heredoc bodies
        from any stage are queued and flushed after the whole line (J2).
        """
        prefix = self._pipeline_prefix(node)  # 'time '/'time -p '/'! '/…

        if not node.commands:
            # A bare `time` (no pipeline) parses to an empty timed Pipeline.
            return self._indent() + prefix.rstrip()

        if len(node.commands) == 1:
            result = self.visit(node.commands[0])
            if prefix:
                stripped = result.lstrip(' ')
                indent = result[:len(result) - len(stripped)]
                result = f"{indent}{prefix}{stripped}"
            return result

        saved_level = self.level
        self.level = 0
        headers = [self.visit(cmd).strip() for cmd in node.commands]
        self.level = saved_level

        # Join stages with ' | ' or ' |& ' (pipe_stderr[i] marks the |& between
        # commands[i] and commands[i+1]).
        pipe_stderr = node.pipe_stderr or []
        pieces = [headers[0]]
        for i in range(1, len(headers)):
            stderr_piped = (i - 1) < len(pipe_stderr) and pipe_stderr[i - 1]
            pieces.append(' |& ' if stderr_piped else ' | ')
            pieces.append(headers[i])

        return self._indent() + prefix + ''.join(pieces)

    @staticmethod
    def _pipeline_prefix(node: Pipeline) -> str:
        """The reserved-word prefix of a pipeline: ``time``/``time -p`` then
        ``!`` (bash grammar order ``[time [-p]] [!] pipeline``)."""
        prefix = ''
        if node.timed:
            prefix += 'time -p ' if node.time_posix else 'time '
        if node.negated:
            prefix += '! '
        return prefix

    def visit_AndOrList(self, node: AndOrList) -> str:
        """Format an and/or list."""
        if not node.pipelines:
            return ''

        parts = [self.visit(node.pipelines[0])]

        for i, op in enumerate(node.operators):
            if i + 1 < len(node.pipelines):
                parts.append(f' {op} ')
                parts.append(self.visit(node.pipelines[i + 1]).strip())

        result = ''.join(parts)
        if node.background:
            result += ' &'
        return result

    # Control structures

    def visit_WhileLoop(self, node: WhileLoop) -> str:
        """Format a while loop."""
        lines = []

        lines.append(self._flush_line(
            f"{self._indent()}while {self._format_inline(node.condition)}; do"))
        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_UntilLoop(self, node: UntilLoop) -> str:
        """Format an until loop."""
        lines = []

        lines.append(self._flush_line(
            f"{self._indent()}until {self._format_inline(node.condition)}; do"))
        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def _format_loop_items(self, node) -> str:
        """Render a for/select ``in`` list from the item Words.

        The item Words carry per-part quote context, so a quoted item
        round-trips faithfully (``'a b'`` stays single-quoted, ``"$z"`` keeps
        its quotes) and the ``in``-less form (``for x; do``) — whose parser
        stored the implicit ``"$@"`` Word — renders as ``for x in "$@"``
        rather than an unquoted ``$@`` that would word-split (J5). Falls back
        to the flat item strings only for hand-built ASTs with no item Words.
        """
        if node.item_words:
            return ' '.join(self._format_word(w) for w in node.item_words)
        return ' '.join(format_word_list_item(i) for i in node.items)

    def visit_ForLoop(self, node: ForLoop) -> str:
        """Format a for loop."""
        lines = []

        header = f"for {node.variable} in {self._format_loop_items(node)}".rstrip()
        lines.append(f"{self._indent()}{header}; do")

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> str:
        """Format a C-style for loop."""
        lines = []

        init = node.init_expr or ''
        cond = node.condition_expr or ''
        update = node.update_expr or ''

        lines.append(f"{self._indent()}for (({init}; {cond}; {update})); do")

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_IfConditional(self, node: IfConditional) -> str:
        """Format an if statement."""
        lines = []

        lines.append(self._flush_line(
            f"{self._indent()}if {self._format_inline(node.condition)}; then"))
        self._increase_indent()
        lines.append(self.visit(node.then_part))
        self._decrease_indent()

        # elif parts
        for condition, then_part in node.elif_parts:
            lines.append(self._flush_line(
                f"{self._indent()}elif {self._format_inline(condition)}; then"))
            self._increase_indent()
            lines.append(self.visit(then_part))
            self._decrease_indent()

        # else part
        if node.else_part:
            lines.append(self._indent() + 'else')
            self._increase_indent()
            lines.append(self.visit(node.else_part))
            self._decrease_indent()

        lines.append(self._indent() + 'fi')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_CaseConditional(self, node: CaseConditional) -> str:
        """Format a case statement."""
        lines = []

        # Format the subject from its Word (per-part quote context) so a
        # quoted subject re-quotes correctly — `case "a b" in`, `case "" in`,
        # `case 'a;b' in` all survive the round-trip. Fall back to the flat
        # string (re-quoting whitespace) for manually built ASTs with no Word.
        if node.subject_word is not None:
            subject = self._format_word(node.subject_word)
        else:
            subject = node.expr
            if any(c.isspace() for c in subject):
                subject = f'"{subject}"'
        lines.append(f"{self._indent()}case {subject} in")

        self._increase_indent()
        for item in node.items:
            lines.append(self.visit(item))
        self._decrease_indent()

        lines.append(self._indent() + 'esac')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_CaseItem(self, node: CaseItem) -> str:
        """Format a case item."""
        lines = []

        # Format patterns — use the quote-preserving Word path so a quoted
        # literal pattern (`"a b")`) keeps its quotes instead of degrading to
        # two glob words.
        patterns = [self._format_word(p.word) if p.word is not None else p.pattern
                    for p in node.patterns]
        lines.append(f"{self._indent()}{' | '.join(patterns)})")

        # Format commands
        self._increase_indent()
        if node.commands.statements:
            lines.append(self.visit(node.commands))
        self._decrease_indent()

        # Add terminator
        lines.append(f"{self._indent()}{node.terminator}")

        return '\n'.join(lines)

    def visit_SelectLoop(self, node: SelectLoop) -> str:
        """Format a select loop."""
        lines = []

        header = f"select {node.variable} in {self._format_loop_items(node)}".rstrip()
        lines.append(f"{self._indent()}{header}; do")

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    # Other statement types

    def visit_FunctionDef(self, node: FunctionDef) -> str:
        """Format a function definition."""
        lines = []
        lines.append(f"{self._indent()}{node.name}() {{")

        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + '}')

        # Redirections on the definition apply at each call: f() { ...; } > file
        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> str:
        """Format an arithmetic command.

        Redirects (including heredoc bodies) go through the shared
        ``_append_redirects`` seam rather than a hand-join, so
        ``(( 1 )) <<EOF ... EOF`` keeps its body (J2).
        """
        lines = [f"{self._indent()}(({node.expression}))"]
        self._append_redirects(lines, node.redirects)
        return '\n'.join(lines)

    def visit_SubshellGroup(self, node: SubshellGroup) -> str:
        """Format a subshell group ``( ... )``."""
        return self._format_group(node, '(', ')')

    def visit_BraceGroup(self, node: BraceGroup) -> str:
        """Format a brace group ``{ ...; }``."""
        return self._format_group(node, '{', '}')

    def _format_group(self, node, opener: str, closer: str) -> str:
        """Shared multi-line formatting for subshell / brace groups."""
        lines = [self._indent() + opener]
        self._increase_indent()
        lines.append(self.visit(node.statements))
        self._decrease_indent()
        lines.append(self._indent() + closer)
        if node.redirects:
            lines[-1] += ' ' + ' '.join(self.visit(r) for r in node.redirects)
        if node.background:
            lines[-1] += ' &'
        # Heredoc bodies follow the whole line, after any trailing `&`.
        self._register_heredocs(node.redirects)
        lines[-1] = self._flush_line(lines[-1])
        return '\n'.join(lines)

    # Test expressions

    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> str:
        """Format an enhanced test statement.

        Redirects (including heredoc bodies) go through the shared
        ``_append_redirects`` seam rather than a hand-join, so
        ``[[ -n x ]] <<EOF ... EOF`` keeps its body (J2).
        """
        expr_str = self.visit(node.expression)
        lines = [f"{self._indent()}[[ {expr_str} ]]"]
        self._append_redirects(lines, node.redirects)
        return '\n'.join(lines)

    def visit_BinaryTestExpression(self, node: BinaryTestExpression) -> str:
        """Format a binary test expression.

        Format the operand Words (which carry per-part quote context), NOT the
        derived ``.left``/``.right`` display strings — otherwise quoting is
        dropped and the meaning changes: ``[[ $x == "*.txt" ]]`` (literal
        compare) would become ``[[ $x == *.txt ]]`` (glob match), and
        ``[[ $x == "a b" ]]`` would no longer re-parse.
        """
        left = self._format_word(node.left_word)
        right = self._format_word(node.right_word)
        return f"{left} {node.operator} {right}"

    def visit_UnaryTestExpression(self, node: UnaryTestExpression) -> str:
        """Format a unary test expression.

        Format the operand Word (which carries per-part quote context), NOT
        the derived ``.operand`` display string — otherwise quotes are dropped
        and the meaning changes: ``[[ -n '$x' ]]`` (literal) would become
        ``[[ -n $x ]]`` (expanded), and ``[[ -z "" ]]`` would format to the
        unparseable ``[[ -z  ]]``.
        """
        return f"{node.operator} {self._format_word(node.operand_word)}"

    # Inside [[ ]], `&&` binds tighter than `||`, and `!` tighter than both.
    _TEST_OP_PREC = {'||': 1, '&&': 2}
    _NEG_PREC = 3

    def _format_test_operand(self, node, min_prec: int) -> str:
        """Format a test-expression operand, parenthesizing a compound child
        whose top operator binds looser than the context requires.

        Without this, ``[[ ( a || b ) && c ]]`` flattens to
        ``[[ a || b && c ]]`` — which re-parses as ``a || (b && c)`` and
        flips the result (J4). Only a strictly-lower-precedence compound
        child needs parens; equal precedence re-parses identically (``&&``
        and ``||`` are associative).
        """
        text = self.visit(node)
        if (isinstance(node, CompoundTestExpression)
                and self._TEST_OP_PREC.get(node.operator, 0) < min_prec):
            return f"( {text} )"
        return text

    def visit_CompoundTestExpression(self, node: CompoundTestExpression) -> str:
        """Format a compound test expression, re-emitting grouping parens
        where operator precedence would otherwise change the meaning (J4)."""
        prec = self._TEST_OP_PREC.get(node.operator, 0)
        left = self._format_test_operand(node.left, prec)
        right = self._format_test_operand(node.right, prec)
        return f"{left} {node.operator} {right}"

    def visit_NegatedTestExpression(self, node: NegatedTestExpression) -> str:
        """Format a negated test expression.

        ``!`` binds tighter than ``&&``/``||``, so a compound operand must be
        parenthesized: ``[[ ! ( a && b ) ]]`` must not flatten to
        ``[[ ! a && b ]]`` (which is ``(! a) && b`` — J4).
        """
        return f"! {self._format_test_operand(node.expression, self._NEG_PREC)}"

    # Array assignments

    def visit_ArrayInitialization(self, node: ArrayInitialization) -> str:
        """Format array initialization.

        Render each element from its Word (the required structural field),
        via ``_format_word``, so the ANSI-C / double-quote / composite
        re-escaping machinery applies. The legacy flat ``elements`` strings
        wrapped in the derived quote char corrupted values — ``a=($'x\\ty')``
        emitted a literal tab + a spurious ``$`` (J3).
        """
        elements = [self._format_word(w) for w in node.words]
        op = '+=' if node.is_append else '='
        return f"{node.name}{op}({' '.join(elements)})"

    def visit_ArrayElementAssignment(self, node: ArrayElementAssignment) -> str:
        """Format array element assignment.

        Render the value from ``value_word`` via ``_format_word`` (not the
        flat ``value`` string wrapped in the derived quote char): that path
        re-escapes so ``a[3]=$'x\\ty'`` round-trips as ``a[3]=$'x\\ty'``
        instead of injecting a raw tab that re-parses into a second word (J3).
        """
        op = '+=' if node.is_append else '='
        value_str = self._format_word(node.value_word)
        return f"{node.name}[{node.index}]{op}{value_str}"

    # Redirections

    def _register_heredocs(self, redirects) -> None:
        """Queue the body + closing delimiter of any heredocs on a command.

        Heredoc bodies and their closing delimiter sit at column 0 on the
        lines *after* the whole physical line (they cannot be indented — for
        ``<<`` an indented delimiter would not terminate the document), and
        that line may continue past the ``<<DELIM`` (``cat <<EOF && echo x``,
        ``if cat <<EOF; then``). So a command REGISTERS its bodies here and
        the line-completing site emits them via ``_flush_line`` — this is the
        single seam every heredoc-bearing construct funnels through (J2).
        """
        for r in redirects:
            if r.type in ('<<', '<<-') and r.heredoc_content is not None:
                body = r.heredoc_content
                if body and not body.endswith('\n'):
                    body += '\n'
                self._pending_heredocs.append(body + (r.target or ''))

    def _flush_line(self, line: str) -> str:
        """Append (and clear) any queued heredoc bodies after ``line``.

        Called at every physical-line boundary — after each statement, after
        a control-structure header (``if …; then``), and after a compound's
        trailing-redirect line. A no-op when nothing is queued.
        """
        if not self._pending_heredocs:
            return line
        trailer = '\n' + '\n'.join(self._pending_heredocs)
        self._pending_heredocs = []
        return line + trailer

    def _append_redirects(self, lines: list, redirects) -> None:
        """Append a compound command's redirects to its closing line.

        The inline operators (``>f``, ``<<EOF``) go on the last line; any
        heredoc bodies are queued and flushed after it. Shared by every
        compound formatter so ``done <<EOF`` / ``fi >out`` / ``[[ … ]] <<EOF``
        render uniformly (J2).
        """
        if not redirects:
            return
        lines[-1] += ' ' + ' '.join(self.visit(r) for r in redirects)
        self._register_heredocs(redirects)
        lines[-1] = self._flush_line(lines[-1])

    def visit_Redirect(self, node: Redirect) -> str:
        """Format a redirection (the inline operator + target).

        Heredoc *bodies* are emitted separately by ``_heredoc_trailer`` —
        this renders only the ``<<DELIM`` operator that stays on the
        command line.
        """
        # Operator with any explicit fd prefix. A named-fd redirect
        # (``{var}>file``) prefixes ``{var}``; '2>'-style types already encode
        # their fd; everything else prepends node.fd when present.
        if node.var_fd is not None:
            op = f"{{{node.var_fd}}}{node.type}"
        elif node.type.startswith('2') and node.fd == 2:
            op = node.type
        elif node.fd is not None:
            op = f"{node.fd}{node.type}"
        else:
            op = node.type

        # Here document: keep the delimiter's quoting so re-parsing keeps the
        # same expansion behavior (`<<'EOF'` must not become `<<EOF`).
        if node.type in ('<<', '<<-'):
            delim = node.target or ''
            if node.heredoc_quoted:
                delim = f"'{delim}'"
            return f"{op}{delim}"

        # Here string: format the Word (per-part quote context) so a composite
        # like `<<< foo$v"dq"` round-trips; fall back to re-quoting the flat
        # scalar for synthesized redirects with no Word.
        if node.type == '<<<':
            if node.target_word is not None:
                return f"{op}{self._format_word(node.target_word)}"
            return f"{op}{quote_scalar(node.target or '', node.quote_type)}"

        # fd duplication/close (2>&1, >&-). A move (`[n]>&m-`) keeps the
        # trailing '-' so it does not re-parse as a plain dup.
        if node.dup_fd is not None:
            return f"{op}{node.dup_fd}{'-' if node.move else ''}"

        # Filename target: format the Word to preserve quoting (`> "a b"`);
        # fall back to the bare target string for forms with no Word. A process
        # substitution target (`> >(cat)`, `< <(cmd)`) needs a space after the
        # operator, else `> >(...)` glues to `>>(...)` (append + parse error).
        if node.target_word is not None:
            target = self._format_word(node.target_word)
        elif node.target is not None:
            target = node.target
        else:
            return op
        sep = ' ' if target[:2] in ('<(', '>(') else ''
        return f"{op}{sep}{target}"

    def visit_ProcessSubstitution(self, node: ProcessSubstitution) -> str:
        """Format a process substitution."""
        return str(node)

    # Word-level nodes. In normal formatting these are reconstructed by
    # _format_word() (which preserves per-part quote context) rather than
    # dispatched through visit(), but explicit methods keep the formatter
    # total over every real AST node a parse can produce.

    def visit_Word(self, node: Word) -> str:
        """Format a word from its parts, preserving quoting."""
        return self._format_word(node)

    def visit_LiteralPart(self, node: LiteralPart) -> str:
        """Format a literal word part."""
        return node.text

    def visit_ExpansionPart(self, node: ExpansionPart) -> str:
        """Format an expansion word part."""
        return self.visit(node.expansion)

    def visit_VariableExpansion(self, node: VariableExpansion) -> str:
        """Format a simple variable expansion ($var)."""
        return str(node)

    def visit_ParameterExpansion(self, node: ParameterExpansion) -> str:
        """Format a parameter expansion (${...})."""
        return str(node)

    def visit_CommandSubstitution(self, node: CommandSubstitution) -> str:
        """Format a command substitution ($(...) or backticks)."""
        return str(node)

    def visit_ArithmeticExpansion(self, node: ArithmeticExpansion) -> str:
        """Format an arithmetic expansion ($((...)))."""
        return str(node)

    def visit_CasePattern(self, node: CasePattern) -> str:
        """Format a single case pattern."""
        return node.pattern

    def generic_visit(self, node: ASTNode) -> str:
        """Default formatting for unknown nodes.

        Kept as a defensive fallback for AST nodes added in the future;
        no node produced by parsing real source should reach it (enforced
        by tests/unit/visitor/test_ast_coverage_matrix.py).
        """
        return f"{self._indent()}# Unknown node: {node.__class__.__name__}"


def format_function_definition(name: str, func) -> str:
    """Render a stored function as re-executable source.

    The single chokepoint behind ``declare -f``, ``type``, and
    ``command -V``: wraps a runtime ``Function`` (duck-typed: ``.body``,
    ``.redirects``) back into a FunctionDef node and formats it. The text
    is FormatterVisitor's canonical style rather than bash's, but it must
    re-parse to the same program — ``src=$(declare -f f); eval "$src"``
    is the contract.
    """
    node = FunctionDef(name=name, body=func.body, redirects=func.redirects)
    return FormatterVisitor().visit(node)


# ---------------------------------------------------------------------------
# $BASH_COMMAND text
#
# bash reports the PRE-expansion text of the dispatched command (its own
# reconstruction from the parsed command, not the raw source bytes):
# `echo $x` stays `echo $x`, quotes survive, redirects are included, and
# compound constructs report a HEADER (`for i in $v`, `case $x in `) while
# their bodies' simple commands report themselves. These helpers reuse the
# formatter's single-node rendering for that. Truth table:
# tmp/probes-r17t2-trap/cases_b_bashcmd.sh (bash 5.2).
# ---------------------------------------------------------------------------

def format_bash_command(node) -> str:
    """One command's $BASH_COMMAND text (SimpleCommand, [[ ]], (( )), ...)."""
    return FormatterVisitor().visit(node)


def format_for_header(node) -> str:
    """A for loop's $BASH_COMMAND header: ``for i in $v`` (pre-expansion)."""
    formatter = FormatterVisitor()
    return f"for {node.variable} in {formatter._format_loop_items(node)}".rstrip()


def format_case_header(node) -> str:
    """A case statement's $BASH_COMMAND header: ``case $x in `` (bash keeps
    the trailing space before where the patterns would start)."""
    if node.subject_word is not None:
        subject = FormatterVisitor._format_word(node.subject_word)
    else:
        subject = node.expr
    return f"case {subject} in "
