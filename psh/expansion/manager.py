"""Central expansion manager that orchestrates all shell expansions."""
from typing import TYPE_CHECKING, List, Optional, Union

from ..ast_nodes import SimpleCommand
from ..core import ExpansionError
from .command_sub import CommandSubstitution
from .glob import GlobExpander
from .tilde import TildeExpander
from .variable import VariableExpander
from .word_splitter import WordSplitter

if TYPE_CHECKING:
    from ..shell import Shell


class ExpansionManager:
    """Orchestrates all shell expansions in the correct order."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Initialize individual expanders
        self.variable_expander = VariableExpander(shell)
        self.command_sub = CommandSubstitution(shell)
        self.tilde_expander = TildeExpander(shell)
        self.glob_expander = GlobExpander(shell)
        self.word_splitter = WordSplitter()

        # Initialize expansion evaluator (lazy import to avoid circular dependencies)
        self._evaluator = None

    @property
    def evaluator(self):
        """Get expansion evaluator, creating if needed."""
        if self._evaluator is None:
            from .evaluator import ExpansionEvaluator
            self._evaluator = ExpansionEvaluator(self.shell)
        return self._evaluator

    def expand_arguments(self, command: SimpleCommand) -> List[str]:
        """
        Expand all arguments in a command using Word AST nodes.

        This method orchestrates all expansions in the correct order:
        1. Brace expansion (handled by tokenizer)
        2. Tilde expansion
        3. Variable expansion
        4. Command substitution
        5. Arithmetic expansion
        6. Word splitting
        7. Pathname expansion (globbing)
        8. Quote removal
        """
        return self._expand_word_ast_arguments(command)

    def _expand_word_ast_arguments(self, command: SimpleCommand) -> List[str]:
        """Expand arguments using Word AST nodes.

        Process substitutions need no pre-pass: they are ProcessSubstitution
        expansion parts inside Words (whole-word ``<(cmd)`` and embedded
        ``pre<(cmd)post`` alike) and are performed by _expand_word(). The
        fds/pids register with the ProcessSubstitutionHandler; the enclosing
        process_sub_scope() (CommandExecutor) closes the parent fds and
        reaps the children when the command finishes.
        """
        args = []

        # Debug: show pre-expansion words
        if self.state.options.get('debug-expansion'):
            print(f"[EXPANSION] Expanding Word AST command: {[str(w) for w in command.words]}", file=self.state.stderr)

        for word in command.words:
            expanded = self._expand_word(word)
            if isinstance(expanded, list):
                args.extend(expanded)
            else:
                args.append(expanded)

        # Debug: show post-expansion args
        if self.state.options.get('debug-expansion'):
            print(f"[EXPANSION] Word AST Result: {args}", file=self.state.stderr)

        return args

    def expand_word_to_fields(self, word) -> List[str]:
        """Expand a Word into zero or more fields (array-initializer semantics).

        Runs the same pipeline as command arguments — tilde, variable and
        command expansion, IFS word splitting of unquoted expansions, and
        quote-aware pathname expansion honoring noglob/nullglob/dotglob —
        but WITHOUT the assignment-word splitting suppression, because bash
        word-splits ``k=$x`` inside ``a=(...)`` initializers.

        Returns a list: an unquoted expansion of an empty/unset value
        contributes zero fields; a quoted empty string contributes one.
        """
        expanded = self._expand_word(word, suppress_assignment_splitting=False)
        if isinstance(expanded, list):
            return expanded
        return [expanded]

    def _expand_word(self, word, *,
                     suppress_assignment_splitting: bool = True) -> Union[str, List[str]]:
        """Expand a Word AST node using per-part quote context.

        Uses structural information from Word parts instead of \\x00
        markers to determine glob suppression, word splitting, and
        tilde expansion behavior.

        Args:
            word: The Word AST node to expand.
            suppress_assignment_splitting: When True (command-argument
                context), a word that looks like ``VAR=value`` skips word
                splitting (POSIX; used by declare/export/local arguments).
                Array initializers pass False — bash splits there.

        Returns:
            Either a single string or a list of strings (for word splitting
            or ``$@`` expansion).
        """
        from ..ast_nodes import (
            ExpansionPart,
            LiteralPart,
            ProcessSubstitution,
            Word,
        )

        if not isinstance(word, Word):
            return str(word)

        # Single-quoted word: no expansion at all
        if word.quote_type == "'":
            return self._word_to_string(word)

        # ANSI-C quoted word ($'...'): lexer already processed escapes, treat as literal
        if word.quote_type == "$'":
            return self._word_to_string(word)

        # Double-quoted word (uniform quote_type on the Word itself):
        # expand variables/commands but no word splitting or globbing
        if word.quote_type == '"':
            return self._expand_double_quoted_word(word)

        # --- Composite / unquoted word ---
        # Track properties needed for post-expansion steps
        has_unquoted_glob = False
        has_expansion = False
        has_unquoted_expansion = False
        all_parts_quoted = True
        result_parts: list = []
        # Indices in result_parts holding unquoted-expansion text — the only
        # text field splitting may break (POSIX).
        splittable_idx: set = set()

        for part in word.parts:
            if isinstance(part, LiteralPart):
                text = part.text
                if part.quoted and part.quote_char == "'":
                    # Single-quoted literal: completely literal
                    result_parts.append(text)
                elif part.quoted and part.quote_char == "$'":
                    # ANSI-C quoted literal: lexer already processed escapes
                    result_parts.append(text)
                elif part.quoted and part.quote_char == '"':
                    # Double-quoted literal: after WordBuilder decomposition,
                    # expansions are separate ExpansionPart nodes, so this
                    # LiteralPart is purely literal text.  But backslash
                    # escapes (\$, \\, \", \`) still need processing.
                    if '\\' in text:
                        text = self.process_dquote_escapes(text)
                    result_parts.append(text)
                else:
                    all_parts_quoted = False
                    had_escapes = False
                    # Process escape sequences in unquoted text
                    if '\\' in text:
                        had_escapes = True
                        text, escaped_globs = self._process_unquoted_escapes(text)
                        # If glob chars remain that weren't escaped, track them
                        if any(c in text for c in '*?[') and not escaped_globs:
                            has_unquoted_glob = True
                    else:
                        # Track unquoted glob chars
                        if any(c in text for c in '*?['):
                            has_unquoted_glob = True
                    # Unquoted literal: tilde on first part if leading ~
                    # Only suppress tilde expansion if the ~ itself was
                    # escaped (\~), not if some later char was escaped.
                    tilde_escaped = had_escapes and part.text.startswith('\\~')
                    if (not has_expansion and not result_parts
                            and text.startswith('~') and not tilde_escaped):
                        text = self.expand_tilde(text)
                    result_parts.append(text)

            elif isinstance(part, ExpansionPart):
                has_expansion = True

                # Process substitution (<(cmd) / >(cmd)) — whole-word or
                # embedded. Perform it and splice the /dev/fd/N path into
                # the word at this position. The path is NOT subject to
                # word splitting or globbing (bash: process substitution
                # is not a parameter/command/arithmetic expansion, so its
                # result never field-splits, even with a pathological IFS).
                if isinstance(part.expansion, ProcessSubstitution):
                    all_parts_quoted = False
                    path = self.shell.io_manager.create_process_substitution_for_expansion(
                        part.expansion.direction, part.expansion.command)
                    result_parts.append(path)
                    continue

                # Handle quoted field expansions ("$@", "${a[@]}", ...) in
                # composite words: pre"$@"post with params (a,b,c) →
                # [prea, b, cpost]
                if part.quoted:
                    fields = self._field_expansion_fields(part)
                    if fields is not None:
                        return self._expand_at_with_affixes(
                            word, part, result_parts, in_double_quote=False,
                            first_fields=fields)

                # An unquoted field expansion standing alone ($@, ${a[@]}):
                # expand to fields FIRST, then IFS-split each field, so
                # parameter/element boundaries survive a custom IFS (bash).
                if not part.quoted and len(word.parts) == 1:
                    ufields = self._field_expansion_fields(part)
                    if ufields is not None:
                        out: list = []
                        for f in ufields:
                            out.extend(self._split_with_ifs(f, None))
                        if (any(any(c in f for c in '*?[') for f in out)
                                and not self.state.options.get('noglob', False)):
                            return self._glob_words(out)
                        return out

                expanded = self.expand_expansion(part.expansion)
                if part.quoted:
                    # Quoted expansion: no word splitting, no globbing on result
                    result_parts.append(expanded)
                else:
                    all_parts_quoted = False
                    has_unquoted_expansion = True
                    # Glob chars from unquoted expansion trigger globbing
                    if any(c in expanded for c in '*?['):
                        has_unquoted_glob = True
                    splittable_idx.add(len(result_parts))
                    result_parts.append(expanded)

        result = ''.join(result_parts)

        # Word splitting: only if there are unquoted expansion results
        # but NOT for assignment words (VAR=value) per POSIX.
        # While the executor strips true command-prefix assignments before
        # calling expand_arguments(), builtins like declare/export/local
        # receive their VAR=value arguments through this path.
        is_assignment = (suppress_assignment_splitting and
                         len(word.parts) >= 1 and
                         isinstance(word.parts[0], LiteralPart) and
                         '=' in word.parts[0].text and
                         not word.parts[0].text.startswith('='))
        if has_unquoted_expansion and not is_assignment:
            words = self._split_part_fields(result_parts, splittable_idx)
            if len(words) > 1:
                # Glob each split word if there are unquoted glob chars
                if has_unquoted_glob and not self.state.options.get('noglob', False):
                    return self._glob_words(words)
                return words
            elif len(words) == 1:
                result = words[0]
            else:
                # A purely unquoted expansion that splits to nothing (e.g.
                # `set -- $unset`) contributes zero fields, not one empty one.
                return []

        # Check for extglob patterns in unquoted text
        if not has_unquoted_glob and not all_parts_quoted and self.state.options.get('extglob', False):
            from .extglob import contains_extglob
            if contains_extglob(result):
                has_unquoted_glob = True

        # Glob expansion on the single result
        if has_unquoted_glob and not self.state.options.get('noglob', False):
            globbed = self._glob_words([result])
            if len(globbed) == 1:
                return globbed[0]
            return globbed

        return result

    def _field_expansion_fields(self, part) -> Optional[List[str]]:
        """Fields if this ExpansionPart is field-producing in double quotes.

        Returns the list of fields for ``$@``, ``${a[@]}``, ``${@:2}``,
        ``${a[@]:1:2}``, ``${a[@]@Q}`` etc., or None when the expansion has
        scalar semantics (everything else, including ``$*``/``${a[*]}``).
        """
        from ..ast_nodes import ParameterExpansion, VariableExpansion
        exp = part.expansion
        if isinstance(exp, VariableExpansion):
            if exp.name == '@':
                return list(self.state.positional_params)
            if '[@]' in exp.name:
                # Unquoted ${a[@]} arrives as VariableExpansion('a[@]')
                # (the quoted form parses as ParameterExpansion).
                return self.variable_expander.expand_to_fields(exp.name, None, None)
            return None
        if isinstance(exp, ParameterExpansion):
            return self.variable_expander.expand_to_fields(
                exp.parameter, exp.operator, exp.word)
        return None

    def _expand_double_quoted_word(self, word) -> Union[str, List[str]]:
        """Expand a uniformly double-quoted Word (quote_type='"').

        Handles multi-field expansion ("$@", "${a[@]}", slices, transforms)
        and variable/command expansion but suppresses word splitting and
        globbing.
        """
        from ..ast_nodes import ExpansionPart, LiteralPart

        result_parts: list = []
        for part in word.parts:
            if isinstance(part, LiteralPart):
                # After WordBuilder decomposition, expansions are separate
                # ExpansionPart nodes, so LiteralPart text is purely literal.
                # But backslash escapes (\$, \\, \", \`) still need processing.
                text = part.text
                if '\\' in text:
                    text = self.process_dquote_escapes(text)
                result_parts.append(text)
            elif isinstance(part, ExpansionPart):
                fields = self._field_expansion_fields(part)
                if fields is not None:
                    return self._expand_at_with_affixes(
                        word, part, result_parts, in_double_quote=True,
                        first_fields=fields)

                expanded = self.expand_expansion(part.expansion)
                result_parts.append(expanded)

        return ''.join(result_parts)

    def _expand_at_with_affixes(self, word, at_part, result_parts_before,
                                in_double_quote: bool,
                                first_fields: Optional[List[str]] = None):
        """Distribute expansion fields across prefix/suffix text.

        Used by both ``_expand_word()`` (composite words) and
        ``_expand_double_quoted_word()`` to handle field-producing
        expansions ("$@", "${a[@]}", ...) with surrounding literal text.
        Supports multiple field expansions in a single word.

        Algorithm: walk parts left to right, accumulating text.  On each
        field expansion, splice the fields into the result — the last
        field becomes the seed for continued accumulation.

        Example with params ``(1 2)``::

            "a$@b$@c"  →  a1  2b1  2c

        Args:
            word: The Word AST node being expanded.
            at_part: The first field-producing ExpansionPart in word.parts.
            result_parts_before: Parts accumulated before ``at_part``.
            in_double_quote: True when called from the double-quoted path
                (all suffix literals are treated as double-quoted).
            first_fields: Pre-computed fields for ``at_part`` (avoids
                evaluating its expansion twice).

        Returns:
            A single string, a list of strings, or [] — a word consisting
            solely of empty field expansions produces ZERO fields (bash:
            ``"$@"`` with no parameters vanishes).
        """
        from ..ast_nodes import ExpansionPart, LiteralPart

        # current_seed: text accumulated so far that becomes the prefix
        # of the next word.  We start with everything before the first
        # field expansion. has_content distinguishes "one empty field"
        # (some literal/scalar text was present) from "zero fields".
        current_seed = ''.join(result_parts_before)
        has_content = bool(result_parts_before)
        result_words: list = []
        found_first_at = False

        def splice(fields: List[str]):
            nonlocal current_seed, has_content
            if not fields:
                return
            has_content = True
            if len(fields) == 1:
                current_seed += fields[0]
            else:
                result_words.append(current_seed + fields[0])
                result_words.extend(fields[1:-1])
                current_seed = fields[-1]

        for p in word.parts:
            if not found_first_at:
                if p is at_part:
                    found_first_at = True
                    splice(first_fields if first_fields is not None else [])
                # Parts before the first field expansion are already in
                # result_parts_before
                continue

            # Process parts after the first field expansion
            if isinstance(p, ExpansionPart) and (in_double_quote or p.quoted):
                fields = self._field_expansion_fields(p)
                if fields is not None:
                    splice(fields)
                    continue
            if isinstance(p, LiteralPart):
                t = p.text
                if in_double_quote or (p.quoted and p.quote_char == '"'):
                    if '\\' in t:
                        t = self.process_dquote_escapes(t)
                elif not p.quoted:
                    if '\\' in t:
                        t, _ = self._process_unquoted_escapes(t)
                current_seed += t
                has_content = True
            elif isinstance(p, ExpansionPart):
                current_seed += self.expand_expansion(p.expansion)
                has_content = True

        # Finalize: the current seed becomes the last word
        result_words.append(current_seed)

        if len(result_words) == 1:
            if result_words[0] == '' and not has_content:
                # Only empty field expansions: zero fields (bash)
                return []
            return result_words[0]
        return result_words

    @staticmethod
    def process_dquote_escapes(text: str) -> str:
        """Process backslash escapes in double-quoted literal text.

        In double quotes, only ``\\$``, ``\\\\``, ``\\"``, and ``\\``` are
        special escapes.  All other ``\\X`` sequences are kept literally.
        """
        result = []
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text):
                nxt = text[i + 1]
                if nxt in ('$', '\\', '"', '`'):
                    result.append(nxt)
                    i += 2
                    continue
                elif nxt == '\n':
                    # Line continuation — drop both chars
                    i += 2
                    continue
            result.append(text[i])
            i += 1
        return ''.join(result)

    @staticmethod
    def _process_unquoted_escapes(text: str) -> tuple:
        """Process backslash escapes in unquoted literal text.

        Returns (processed_text, all_globs_escaped) where all_globs_escaped
        is True when glob chars were present but ALL were escaped (meaning
        the result should NOT trigger globbing).
        """
        result = []
        had_glob_chars = False
        all_globs_escaped = True
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text):
                nxt = text[i + 1]
                if nxt in ('$', '\\', '`', '"', "'", '~', ' ', '\n'):
                    result.append(nxt)
                    i += 2
                    continue
                elif nxt in ('*', '?', '['):
                    # Escaped glob char: emit the literal char
                    had_glob_chars = True
                    result.append(nxt)
                    i += 2
                    continue
                else:
                    # Other backslash: remove backslash, keep char
                    result.append(nxt)
                    i += 2
                    continue
            if text[i] in ('*', '?', '['):
                # Unescaped glob char
                had_glob_chars = True
                all_globs_escaped = False
            result.append(text[i])
            i += 1
        return ''.join(result), had_glob_chars and all_globs_escaped

    def _glob_words(self, words: List[str]) -> List[str]:
        """Apply glob expansion to a list of words."""
        result = []
        check_extglob = self.state.options.get('extglob', False)
        for w in words:
            is_glob = any(c in w for c in '*?[')
            if not is_glob and check_extglob:
                from .extglob import contains_extglob
                is_glob = contains_extglob(w)
            if is_glob:
                matches = self.glob_expander.expand(w)
                if matches:
                    result.extend(sorted(matches))
                elif self.state.options.get('nullglob', False):
                    pass  # nullglob: no matches -> nothing
                else:
                    result.append(w)
            else:
                result.append(w)
        return result

    def _word_to_string(self, word) -> str:
        """Convert a Word AST node to a string without expansion."""
        from ..ast_nodes import ExpansionPart, LiteralPart

        parts = []
        for part in word.parts:
            if isinstance(part, LiteralPart):
                parts.append(part.text)
            elif isinstance(part, ExpansionPart):
                # In single quotes, expansions are literal
                parts.append(self._expansion_to_literal(part.expansion))
        return ''.join(parts)

    def _expansion_to_literal(self, expansion) -> str:
        """Convert an expansion to its literal representation."""
        from ..ast_nodes import ArithmeticExpansion, CommandSubstitution, ParameterExpansion, VariableExpansion

        if isinstance(expansion, VariableExpansion):
            return f"${expansion.name}"
        elif isinstance(expansion, CommandSubstitution):
            if expansion.backtick_style:
                return f"`{expansion.command}`"
            else:
                return f"$({expansion.command})"
        elif isinstance(expansion, ParameterExpansion):
            # Reconstruct parameter expansion syntax
            result = f"${{{expansion.parameter}"
            if expansion.operator:
                result += expansion.operator
                if expansion.word:
                    result += expansion.word
            result += "}"
            return result
        elif isinstance(expansion, ArithmeticExpansion):
            return f"$(({expansion.expression}))"
        else:
            # ProcessSubstitution and any future expansion types render via
            # their __str__ (e.g. '<(cmd)')
            return str(expansion)

    def expand_expansion(self, expansion) -> str:
        """Evaluate a single expansion AST node to a string (public API).

        Used by the executor when building an assignment value from Word parts;
        kept public so callers need not reach into a private method.
        """
        # Use ExpansionEvaluator for clean evaluation. Errors propagate:
        # user-facing failures arrive as ExpansionError/UnboundVariableError
        # (e.g. ${var:?msg}, nounset, bad slice offsets), and anything else
        # (AttributeError/TypeError/ValueError) is an implementation defect
        # that must fail loudly rather than silently degrade to the literal
        # text of the expansion (the pre-v0.300 fallback returned
        # str(expansion), turning internal bugs into garbage output).
        return self.evaluator.evaluate(expansion)

    def _split_with_ifs(self, text: Optional[str], quote_type: Optional[str]) -> List[str]:
        """Split text using the current IFS, preserving quoting rules."""
        if text is None:
            return []

        if quote_type is not None:
            return [text]

        ifs = self.state.get_variable('IFS', ' \t\n')
        return self.word_splitter.split(text, ifs)

    def expand_word_as_pattern(self, word) -> str:
        """Expand a Word into a glob-pattern string (case patterns).

        Quoted text and quoted-expansion results are escaped so they match
        literally; unquoted text and unquoted-expansion results keep their
        glob power — the same quoting rule as ${x#pat} operands.

        Process substitution parts stay as their literal ``<(cmd)`` text:
        psh does not perform process substitution in case patterns.
        """
        from ..ast_nodes import ExpansionPart, LiteralPart, ProcessSubstitution
        ve = self.variable_expander
        out = []
        for part in word.parts:
            if isinstance(part, LiteralPart):
                if part.quoted:
                    out.append(ve.glob_escape(part.text))
                else:
                    out.append(part.text)
            elif isinstance(part, ExpansionPart):
                if isinstance(part.expansion, ProcessSubstitution):
                    out.append(str(part.expansion))
                    continue
                expanded = self.expand_expansion(part.expansion)
                out.append(ve.glob_escape(expanded) if part.quoted else expanded)
        return ''.join(out)

    def _split_part_fields(self, parts: List[str], splittable_idx: set) -> List[str]:
        """Field-split a composite word part-by-part (POSIX).

        Only the text of unquoted expansion results (the indices in
        *splittable_idx*) can produce field boundaries. Literal and quoted
        text never splits — even if it contains IFS characters that arrived
        via escape processing (``pre\\ post$x`` stays one field) — but it
        merges with adjacent expansion fragments into a single field.
        """
        ifs = self.state.get_variable('IFS', ' \t\n')
        fields: List[str] = []
        current: Optional[str] = None  # None = no field currently open
        for idx, text in enumerate(parts):
            if idx not in splittable_idx:
                current = (current or '') + text
                continue
            pieces, leading, trailing = self.word_splitter.split_with_edges(text, ifs)
            if leading and current is not None:
                fields.append(current)
                current = None
                # A leading non-whitespace delimiter both closed the open
                # field and produced an empty first piece — same boundary,
                # drop the duplicate (pre$x with x=':a' is [pre, a]).
                if pieces and pieces[0] == '' and text[0] not in ' \t\n':
                    pieces = pieces[1:]
            for k, piece in enumerate(pieces):
                if k == 0 and current is not None:
                    current += piece
                else:
                    if current is not None:
                        fields.append(current)
                    current = piece
            if trailing and current is not None:
                fields.append(current)
                current = None
        if current is not None:
            fields.append(current)
        return fields

    def expand_string_variables(self, text: str) -> str:
        """
        Expand variables and arithmetic in a string.
        Used for here strings and double-quoted strings.
        """
        return self.variable_expander.expand_string_variables(text)

    def expand_variable(self, var_expr: str) -> str:
        """Expand a variable expression."""
        return self.variable_expander.expand_variable(var_expr)

    def set_var_or_array_element(self, name: str, value) -> None:
        """Assign to a plain variable or an ``arr[index]`` element.

        Public entry point used by the scope manager to route a nameref whose
        target is an array element (declare -n e=arr[1]) to the array-aware
        setter.
        """
        self.variable_expander.set_var_or_array_element(name, value)

    def expand_tilde(self, path: str) -> str:
        """Expand tilde in a path."""
        return self.tilde_expander.expand(path)

    def execute_command_substitution(self, cmd_sub: str) -> str:
        """Execute command substitution and return output."""
        return self.command_sub.execute(cmd_sub)

    def execute_arithmetic_expansion(self, expr: str) -> int:
        """Execute arithmetic expansion and return result.

        Raises:
            ExpansionError: If arithmetic evaluation fails
        """
        # Remove $(( and ))
        if expr.startswith('$((') and expr.endswith('))'):
            arith_expr = expr[3:-2]
        else:
            return 0

        # NOTE: no pre-expansion pass here. evaluate_arithmetic() expands
        # $-constructs itself (via expand_string_variables, which delegates
        # to the shared _expand_one_dollar scanner), substituting each
        # value verbatim exactly once. A second pass here would rescan
        # substituted text for further $-expansion, which bash does not do
        # (x='$y' makes $(($x)) a syntax error, not the value of y).

        from .arithmetic import ArithmeticError, evaluate_arithmetic

        try:
            result = evaluate_arithmetic(arith_expr, self.shell)
            return result
        except ArithmeticError as e:
            import sys
            print(f"psh: arithmetic error: {e}", file=sys.stderr)
            # Raise exception to stop command execution (like bash)
            raise ExpansionError(f"arithmetic error: {e}")
        except (ValueError, TypeError) as e:
            import sys
            print(f"psh: unexpected arithmetic error: {e}", file=sys.stderr)
            # Raise exception to stop command execution (like bash)
            raise ExpansionError(f"unexpected arithmetic error: {e}")

