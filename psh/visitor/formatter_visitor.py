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
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    TopLevel,
    UnaryTestExpression,
    UntilLoop,
    VariableExpansion,
    # Control structures
    WhileLoop,
    Word,
)
from .base import ASTVisitor


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
    def _escape_double_quoted(text: str) -> str:
        """Re-escape a stored literal that will be re-wrapped in double quotes.

        Inside ``"..."`` the lexer unescapes only ``\\"``, ``\\``` and ``\\\\``
        (storing ``"``, `` ` ``, ``\\``); it KEEPS the backslash before ``$``
        (``"a\\$b"`` stores ``a\\$b``) so the expansion phase can treat it as a
        literal ``$``. So the stored text is essentially source-form, and the
        OLD blanket ``\\`` -> ``\\\\`` doubling corrupted ``\\$`` into a live
        ``\\`` + ``$expansion``. Re-emit so re-lexing yields the SAME stored
        text: escape a bare ``"`` and `` ` ``, and double a backslash only when
        it would otherwise pair with the following emitted char (another
        backslash, a `` ` ``/``"`` we are escaping, or the closing quote) into
        an unintended escape. A backslash before ``$`` (or any ordinary char)
        stays single — the lexer keeps it verbatim.
        """
        out = []
        n = len(text)
        for i, ch in enumerate(text):
            if ch == '"':
                out.append('\\"')
            elif ch == '`':
                out.append('\\`')
            elif ch == '\\':
                nxt = text[i + 1] if i + 1 < n else ''
                if nxt in ('`', '"', '\\', ''):
                    out.append('\\\\')   # would form an escape with what follows
                else:
                    out.append('\\')     # \$ , \n , ... kept verbatim by the lexer
            else:
                out.append(ch)
        return ''.join(out)

    @staticmethod
    def _escape_ansi_c(text: str) -> str:
        """Re-escape a decoded ``$'...'`` value for re-emission as ``$'...'``.

        The lexer DECODES the ANSI-C escapes into the stored value (``$'a\\tb'``
        -> ``a<TAB>b``; ``$'q\\'x'`` -> ``q'x``), so re-wrapping the raw value in
        ``$'...'`` would change it (a literal tab happens to survive, but a
        literal ``'`` closes the quote early). Re-encode backslash, single quote
        and control characters.
        """
        simple = {'\\': '\\\\', "'": "\\'", '\t': '\\t', '\n': '\\n',
                  '\r': '\\r', '\a': '\\a', '\b': '\\b', '\f': '\\f',
                  '\v': '\\v', '\x1b': '\\E'}
        out = []
        for ch in text:
            if ch in simple:
                out.append(simple[ch])
            elif ord(ch) < 32 or ord(ch) == 127:
                out.append(f'\\x{ord(ch):02x}')
            else:
                out.append(ch)
        return ''.join(out)

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
                    FormatterVisitor._escape_double_quoted(text)
                    if isinstance(part, LiteralPart) else text
                    for part, text in items)
                result.append(f'"{content}"')
            elif qc == "$'":
                content = ''.join(
                    FormatterVisitor._escape_ansi_c(text)
                    if isinstance(part, LiteralPart) else text
                    for part, text in items)
                result.append("$'" + content + "'")
            elif qc:  # single quote (literal content, no escaping)
                result.append(f"{qc}{''.join(t for _, t in items)}{qc}")
            else:
                result.append(''.join(t for _, t in items))
        return ''.join(result)

    # Top-level nodes

    def visit_TopLevel(self, node: TopLevel) -> str:
        """Format top-level script."""
        parts = []
        for item in node.items:
            parts.append(self.visit(item))
        return '\n\n'.join(parts)

    def visit_StatementList(self, node: StatementList) -> str:
        """Format a list of statements."""
        parts = []
        for stmt in node.statements:
            parts.append(self.visit(stmt))
        return '\n'.join(parts)

    # Command nodes

    def visit_SimpleCommand(self, node: SimpleCommand) -> str:
        """Format a simple command."""
        parts = []

        # Array assignments
        for assignment in node.array_assignments:
            parts.append(self.visit(assignment))

        # Command and arguments — reconstruct from Word parts to
        # preserve per-part quoting in composite words.
        words = node.words if node.words else []
        for i, arg in enumerate(node.args):
            word = words[i] if i < len(words) else None
            if word and word.parts:
                parts.append(self._format_word(word))
            else:
                parts.append(arg)

        # Redirections
        for redirect in node.redirects:
            parts.append(self.visit(redirect))

        # Background
        if node.background:
            parts.append('&')

        return self._indent() + ' '.join(parts) + self._heredoc_trailer(node.redirects)

    def visit_Pipeline(self, node: Pipeline) -> str:
        """Format a pipeline.

        A single-command pipeline is the AST's transparent wrapper around
        every statement — including compound commands (``if``/``while``/
        ``case``/groups), which render across multiple lines. Delegate to
        the command so it keeps its own indentation; only a true multi-stage
        pipeline flattens its stages onto one line joined by ``' | '`` (which
        is why the inline path resets the indent level to 0).
        """
        if len(node.commands) == 1:
            result = self.visit(node.commands[0])
            if node.negated:
                stripped = result.lstrip(' ')
                indent = result[:len(result) - len(stripped)]
                result = f"{indent}! {stripped}"
            return result

        saved_level = self.level
        self.level = 0
        # Render each stage's command LINE, separating any heredoc body+delim
        # so the whole pipeline header stays on one line and the heredoc bodies
        # follow it — otherwise `cat <<EOF | grep h` formats the `| grep h` onto
        # the EOF terminator line, which breaks heredoc termination on re-parse.
        headers = []
        trailers = []
        for cmd in node.commands:
            rendered = self.visit(cmd)
            trailer = self._heredoc_trailer(getattr(cmd, 'redirects', []) or [])
            if trailer and rendered.endswith(trailer):
                rendered = rendered[:-len(trailer)]
                trailers.append(trailer)
            headers.append(rendered.strip())
        self.level = saved_level

        # Join stages with ' | ' or ' |& ' (pipe_stderr[i] marks the |& between
        # commands[i] and commands[i+1]).
        pipe_stderr = node.pipe_stderr or []
        pieces = [headers[0]]
        for i in range(1, len(headers)):
            stderr_piped = (i - 1) < len(pipe_stderr) and pipe_stderr[i - 1]
            pieces.append(' |& ' if stderr_piped else ' | ')
            pieces.append(headers[i])
        result = ''.join(pieces)
        if node.negated:
            result = '! ' + result

        return self._indent() + result + ''.join(trailers)

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

        lines.append(f"{self._indent()}while {self._format_inline(node.condition)}; do")
        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    def visit_UntilLoop(self, node: UntilLoop) -> str:
        """Format an until loop."""
        lines = []

        lines.append(f"{self._indent()}until {self._format_inline(node.condition)}; do")
        self._increase_indent()
        lines.append(self.visit(node.body))
        self._decrease_indent()

        lines.append(self._indent() + 'done')

        self._append_redirects(lines, node.redirects)

        return '\n'.join(lines)

    # Chars that force-quote a for/select list item: whitespace and the
    # operators/quotes that would otherwise re-parse as syntax. Glob chars
    # (`*?[]`), braces and `$` are deliberately NOT here — quoting them would
    # suppress the globbing / brace / expansion the unquoted form performs.
    _WORD_LIST_FORCE_QUOTE = set(" \t\n;|&<>()'\"`")

    @classmethod
    def _format_word_list_item(cls, item: str) -> str:
        """Quote a for/select ``in`` list item only when needed (bash)."""
        if item == '':
            return '""'
        if any(c in cls._WORD_LIST_FORCE_QUOTE for c in item):
            return '"' + cls._escape_double_quoted(item) + '"'
        return item

    def visit_ForLoop(self, node: ForLoop) -> str:
        """Format a for loop."""
        lines = []

        items = [self._format_word_list_item(item) for item in node.items]
        header = f"for {node.variable} in {' '.join(items)}".rstrip()
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

        lines.append(f"{self._indent()}if {self._format_inline(node.condition)}; then")
        self._increase_indent()
        lines.append(self.visit(node.then_part))
        self._decrease_indent()

        # elif parts
        for condition, then_part in node.elif_parts:
            lines.append(f"{self._indent()}elif {self._format_inline(condition)}; then")
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

        items = ' '.join(self._format_word_list_item(item) for item in node.items)
        header = f"select {node.variable} in {items}".rstrip()
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
        """Format an arithmetic command."""
        result = f"{self._indent()}(({node.expression}))"

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            result += ' ' + redirect_str

        return result

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
        if node.redirects:
            lines[-1] += self._heredoc_trailer(node.redirects)
        return '\n'.join(lines)

    # Test expressions

    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> str:
        """Format an enhanced test statement."""
        expr_str = self.visit(node.expression)
        result = f"{self._indent()}[[ {expr_str} ]]"

        # Add redirections
        if node.redirects:
            redirect_str = ' '.join(self.visit(r) for r in node.redirects)
            result += ' ' + redirect_str

        return result

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

    def visit_CompoundTestExpression(self, node: CompoundTestExpression) -> str:
        """Format a compound test expression."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        return f"{left} {node.operator} {right}"

    def visit_NegatedTestExpression(self, node: NegatedTestExpression) -> str:
        """Format a negated test expression."""
        expr = self.visit(node.expression)
        return f"! {expr}"

    # Array assignments

    def visit_ArrayInitialization(self, node: ArrayInitialization) -> str:
        """Format array initialization."""
        elements = []
        for i, elem in enumerate(node.elements):
            if i < len(node.element_types) and node.element_types[i] == 'STRING':
                quote = node.element_quote_types[i] if i < len(node.element_quote_types) else '"'
                if quote is None:
                    quote = '"'
                elements.append(f'{quote}{elem}{quote}')
            else:
                elements.append(elem)

        op = '+=' if node.is_append else '='
        return f"{node.name}{op}({' '.join(elements)})"

    def visit_ArrayElementAssignment(self, node: ArrayElementAssignment) -> str:
        """Format array element assignment."""
        # Handle both string and token list indices
        if isinstance(node.index, str):
            index_str = node.index
        else:
            # Token list - reconstruct the expression
            index_str = ''.join(token.value for token in node.index)

        op = '+=' if node.is_append else '='

        if node.value_type == 'STRING' and node.value_quote_type:
            value_str = f'{node.value_quote_type}{node.value}{node.value_quote_type}'
        else:
            value_str = node.value

        return f"{node.name}[{index_str}]{op}{value_str}"

    # Redirections

    @staticmethod
    def _quote_scalar(text: str, quote_type) -> str:
        """Re-wrap a scalar (here-string word) in its original quotes."""
        if not quote_type:
            return text
        if quote_type == "$'":
            return f"$'{text}'"
        return f"{quote_type}{text}{quote_type}"

    @staticmethod
    def _heredoc_trailer(redirects) -> str:
        """Body + closing delimiter for any heredocs on a command.

        Heredoc bodies and their closing delimiter sit at column 0 on the
        lines *after* the command (they cannot be indented — for ``<<`` an
        indented delimiter would not terminate the document), so they are
        appended by the command formatter rather than emitted inline by
        ``visit_Redirect``. Returns '' when the command has no heredocs.
        """
        out = []
        for r in redirects:
            if r.type in ('<<', '<<-') and r.heredoc_content is not None:
                body = r.heredoc_content
                if body and not body.endswith('\n'):
                    body += '\n'
                out.append('\n' + body + (r.target or ''))
        return ''.join(out)

    def _append_redirects(self, lines: list, redirects) -> None:
        """Append a compound command's redirects to its closing line.

        The inline operators (``>f``, ``<<EOF``) go on the last line; any
        heredoc bodies follow it (see ``_heredoc_trailer``). Shared by every
        compound formatter so ``done <<EOF`` / ``fi >out`` render uniformly.
        """
        if not redirects:
            return
        lines[-1] += ' ' + ' '.join(self.visit(r) for r in redirects)
        lines[-1] += self._heredoc_trailer(redirects)

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
            return f"{op}{self._quote_scalar(node.target or '', node.quote_type)}"

        # fd duplication/close (2>&1, >&-).
        if node.dup_fd is not None:
            return f"{op}{node.dup_fd}"

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
