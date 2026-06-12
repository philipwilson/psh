"""Central expansion manager that orchestrates all shell expansions."""
import re
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

#: Builtins whose ``NAME=value`` arguments get bash's declaration-argument
#: expansion: no word splitting and no pathname expansion of the value
#: (``declare foo=$x`` keeps "$x" intact; ordinary commands split it).
#: Matches bash 5.2: alias, declare, typeset, export, local, readonly.
#: NOT in the set: ``env`` (a regular command), and ``command``/``builtin``
#: prefixes (bash 5.2 loses declaration semantics through them — verified).
DECLARATION_BUILTINS = frozenset(
    {'alias', 'declare', 'typeset', 'export', 'local', 'readonly'})

#: ``NAME=`` / ``NAME+=`` at the start of a word (valid identifier only).
_ASSIGNMENT_PREFIX_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\+?=')


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

    def expand_arguments(self, command: SimpleCommand, *,
                         declaration_eligible: bool = True) -> List[str]:
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

        Args:
            declaration_eligible: When False the command word can never be
                recognized as a declaration builtin (used for the ``\\cmd``
                backslash bypass — bash treats ``\\export foo=$x`` as an
                ordinary command and word-splits the value).
        """
        return self._expand_word_ast_arguments(
            command, declaration_eligible=declaration_eligible)

    def is_declaration_builtin_command(self, command: SimpleCommand) -> bool:
        """True if the command word literally names a declaration builtin.

        bash recognizes declaration builtins *syntactically*: the command
        word must be an unquoted literal (``"export" foo=$x`` and
        ``$d foo=$x`` with d=declare both word-split their arguments).
        """
        if not command.words:
            return False
        first = command.words[0]
        return (first.is_unquoted_literal
                and str(first) in DECLARATION_BUILTINS)

    @staticmethod
    def assignment_word_prefix(word) -> Optional[str]:
        """Return the ``NAME=`` / ``NAME+=`` prefix of an assignment-shaped word.

        The name and the ``=`` must come from *unquoted literal* text at the
        start of the word (bash: ``declare "foo"=$x`` and ``declare "foo="$x``
        word-split — quoting any part of the name/= breaks recognition), and
        the name must be a valid identifier (``declare foo-bar=$x`` splits).
        Returns None when the word is not assignment-shaped.
        """
        from ..ast_nodes import LiteralPart
        text = ''
        for part in word.parts:
            if isinstance(part, LiteralPart) and not part.quoted:
                text += part.text
                if '=' in text:
                    break
            else:
                break
        if '=' not in text:
            return None
        m = _ASSIGNMENT_PREFIX_RE.match(text)
        return m.group(0) if m else None

    def _expand_word_ast_arguments(self, command: SimpleCommand, *,
                                   declaration_eligible: bool = True) -> List[str]:
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

        # Declaration builtins (declare/export/local/...) give their
        # assignment-shaped arguments bash's declaration semantics: the
        # value is not word-split or pathname-expanded.
        is_declaration = (declaration_eligible
                          and self.is_declaration_builtin_command(command))

        for i, word in enumerate(command.words):
            declaration_assignment = (
                is_declaration and i > 0
                and self.assignment_word_prefix(word) is not None)
            expanded = self._expand_word(
                word, declaration_assignment=declaration_assignment)
            if isinstance(expanded, list):
                args.extend(expanded)
            else:
                args.append(expanded)

        # Debug: show post-expansion args
        if self.state.options.get('debug-expansion'):
            print(f"[EXPANSION] Word AST Result: {args}", file=self.state.stderr)

        return args

    def expand_word_to_fields(self, word, *,
                              assignment_tilde: bool = False,
                              suppress_split_glob: bool = False) -> List[str]:
        """Expand a Word into zero or more fields.

        Runs the same pipeline as command arguments — tilde, variable and
        command expansion, IFS word splitting of unquoted expansions, and
        quote-aware pathname expansion honoring noglob/nullglob/dotglob —
        WITHOUT declaration-argument semantics: bash word-splits ``k=$x``
        both inside ``a=(...)`` initializers and in for/select item lists.

        Args:
            assignment_tilde: Expand tilde after ``=``/``:`` in words shaped
                like assignments (``for i in P=~/x`` does in bash; array
                initializer elements like ``a=(P=~/x)`` do NOT).
            suppress_split_glob: Skip IFS word splitting and pathname
                expansion (bash assignment-context words: associative array
                initializer elements like ``h=($x)`` stay whole). Multi-field
                expansions ("$@", "${a[@]}") still produce multiple fields.

        Returns a list: an unquoted expansion of an empty/unset value
        contributes zero fields; a quoted empty string contributes one.
        """
        expanded = self._expand_word(word, assignment_tilde=assignment_tilde,
                                     declaration_assignment=suppress_split_glob)
        if isinstance(expanded, list):
            return expanded
        return [expanded]

    def _expand_word(self, word, *,
                     assignment_tilde: bool = True,
                     declaration_assignment: bool = False) -> Union[str, List[str]]:
        """Expand a Word AST node using per-part quote context.

        Uses structural information from Word parts instead of \\x00
        markers to determine glob suppression, word splitting, and
        tilde expansion behavior.

        Args:
            word: The Word AST node to expand.
            assignment_tilde: When True and the word is shaped like an
                assignment (``NAME=...``/``NAME+=...``), expand unquoted
                tilde prefixes after the first ``=`` and after each ``:``
                in the value (bash does this for command arguments and
                for/select items; array initializers pass False).
            declaration_assignment: True only for assignment-shaped
                arguments of declaration builtins (declare/export/local/
                readonly/typeset/alias): the value is not word-split and
                not pathname-expanded (bash declaration-argument
                semantics). The CALLER decides this — it knows the command
                name; this method never guesses from the presence of '='.

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

        # Fallback audit 2026-06-12: every caller passes a Word built by a
        # parser; coercing other types to str() masked type bugs as
        # literal text. Fail loudly (v0.300 policy).
        if not isinstance(word, Word):
            raise TypeError(
                f"_expand_word expects a Word AST node, got "
                f"{type(word).__name__}: {word!r}")

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

        # Assignment-shaped word (NAME=... / NAME+=...): bash expands tilde
        # prefixes in the value after the first '=' and after each ':'
        # (for command arguments and for/select items; array initializers
        # pass assignment_tilde=False).
        assign_prefix = None
        if assignment_tilde or declaration_assignment:
            assign_prefix = self.assignment_word_prefix(word)
        assign_seen = 0       # chars of assign_prefix consumed so far
        value_len = 0         # value chars emitted before the current part
        prev_char = ''        # last unquoted-literal char ('' after others)

        for part_index, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                text = part.text
                if assign_prefix is not None and part.quoted:
                    # Quoted text never extends the assignment prefix and
                    # never triggers value-tilde expansion.
                    prev_char = ''
                    value_len += 1
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
                    if assign_prefix is not None:
                        parts_follow = part_index < len(word.parts) - 1
                        remaining = len(assign_prefix) - assign_seen
                        if remaining > 0:
                            take = min(remaining, len(text))
                            assign_seen += take
                            head, chunk = text[:take], text[take:]
                            # A non-empty chunk directly follows the '='.
                            trigger = bool(chunk)
                        else:
                            head, chunk = '', text
                            # ':' always re-triggers; the assignment '='
                            # only when no value text has intervened.
                            trigger = (prev_char == ':'
                                       or (prev_char == '=' and value_len == 0))
                        if chunk:
                            expanded_chunk = self._expand_assignment_value_tildes(
                                chunk, trigger, parts_follow)
                            value_len += len(chunk)
                            text = head + expanded_chunk
                        prev_char = text[-1] if text else prev_char
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
                if assign_prefix is not None:
                    # Expansion results never trigger value-tilde expansion
                    # (the check is syntactic, on the pre-expansion word).
                    prev_char = ''
                    value_len += 1

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

        # Word splitting: only if there are unquoted expansion results,
        # but NOT for declaration-builtin assignment arguments
        # (``declare foo=$x`` keeps the value whole; ordinary commands
        # like ``printf '%s' foo=$x`` split it — bash 5.2).
        if has_unquoted_expansion and not declaration_assignment:
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

        # Glob expansion on the single result. Declaration-builtin
        # assignment arguments are exempt (``declare foo=*`` keeps the
        # literal '*' in bash even when files would match).
        if (has_unquoted_glob and not declaration_assignment
                and not self.state.options.get('noglob', False)):
            globbed = self._glob_words([result])
            if len(globbed) == 1:
                return globbed[0]
            return globbed

        return result

    def expand_assignment_value_word(self, word) -> str:
        """Expand a Word holding an assignment VALUE (the text after ``=``).

        Implements bash assignment-value semantics, shared by scalar
        assignments (``v=...``, via CommandExecutor._expand_assignment_word)
        and array element assignments (``a[i]=...``, ``a=([i]=...)``):

        - all expansions are performed (parameter, command, arithmetic,
          process substitution),
        - NO word splitting and NO pathname expansion of the result,
        - unquoted tilde prefixes expand at the start of the value and
          after each ``:`` (``P=a:~:b``), but a prefix running into
          quoted/expansion text stays literal (``P=~"x"``),
        - quoted parts keep their text literal (with double-quote
          backslash-escape processing).
        """
        from ..ast_nodes import (
            ExpansionPart,
            LiteralPart,
            ProcessSubstitution,
            Word,
        )
        # Fallback audit 2026-06-12: callers always pass a Word (executor
        # assignment paths build them); str() coercion masked type bugs.
        if not isinstance(word, Word):
            raise TypeError(
                f"expand_assignment_value_word expects a Word AST node, "
                f"got {type(word).__name__}: {word!r}")

        result_parts = []
        value_len = 0   # value chars seen so far (pre-expansion)
        prev_char = '='  # last unquoted-literal char ('' after others)

        for index, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                if part.quoted and part.quote_char in ("'", "$'"):
                    # Single-quoted / ANSI-C: completely literal (the lexer
                    # already processed $'...' escapes)
                    result_parts.append(part.text)
                    prev_char = ''
                elif part.quoted and part.quote_char == '"':
                    # Double-quoted: literal text (expansions are separate
                    # ExpansionParts); process \$ \\ \" \` escapes
                    text = part.text
                    if '\\' in text:
                        text = self.process_dquote_escapes(text)
                    result_parts.append(text)
                    prev_char = ''
                else:
                    # Unquoted literal: tilde directly after the assignment
                    # '=' (only when no value text intervened) or after a ':'
                    text = part.text
                    trigger = (prev_char == ':'
                               or (prev_char == '=' and value_len == 0))
                    parts_follow = index < len(word.parts) - 1
                    text = self._expand_assignment_value_tildes(
                        text, trigger, parts_follow)
                    # Process backslash escapes (v=a\ b assigns "a b")
                    if '\\' in text:
                        text, _ = self._process_unquoted_escapes(text)
                    if part.text:
                        prev_char = part.text[-1]
                    result_parts.append(text)
                value_len += len(part.text)
            elif isinstance(part, ExpansionPart):
                if isinstance(part.expansion, ProcessSubstitution):
                    path = self.shell.io_manager.create_process_substitution_for_expansion(
                        part.expansion.direction, part.expansion.command)
                    result_parts.append(path)
                else:
                    result_parts.append(self.expand_expansion(part.expansion))
                prev_char = ''
                value_len += 1

        return ''.join(result_parts)

    def _expand_assignment_value_tildes(self, text: str, first_trigger: bool,
                                        parts_follow: bool) -> str:
        """Expand tilde prefixes inside a chunk of an assignment value.

        bash checks assignment-shaped words for unquoted tilde prefixes
        following the first ``=`` and each ``:``; the prefix runs to the
        next ``/``, ``:`` or end of word, and must be wholly unquoted.

        Args:
            text: raw unquoted literal text belonging to the value.
            first_trigger: True when the chunk directly follows the
                assignment ``=`` or a ``:`` (so a leading ``~`` counts).
            parts_follow: True when more word parts follow this literal.
                A tilde prefix still open at the chunk's end then continues
                into quoted/expansion text — bash does not expand it
                (``P=~"x"`` stays literal; ``P=~/"x"`` expands).
        """
        segments = text.split(':')
        last = len(segments) - 1
        out = []
        for idx, seg in enumerate(segments):
            if seg.startswith('~') and (idx > 0 or first_trigger):
                prefix_open = (idx == last and parts_follow
                               and '/' not in seg)
                if not prefix_open:
                    seg = self.tilde_expander.expand(seg)
            out.append(seg)
        return ':'.join(out)

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

