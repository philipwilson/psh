"""Central expansion manager that orchestrates all shell expansions.

The Word expansion ENGINE (the part walkers, splitting, globbing, escape
processing) lives in :mod:`psh.expansion.word_expander` together with the
named :class:`~psh.expansion.word_expander.WordExpansionPolicy` table.
This module is the orchestrator: it owns the sub-expanders, recognizes
declaration builtins, picks the policy for each context, and keeps the
public entry points (`expand_arguments`, `expand_word_to_fields`,
`expand_assignment_value_word`, `expand_word_as_pattern`,
`expand_string_variables`) that the executor calls.
"""
from typing import TYPE_CHECKING, List, Optional

from ..ast_nodes import SimpleCommand, Word
from ..core.assignment_utils import ASSIGNMENT_PREFIX_RE
from .brace_expansion_words import WordBraceExpander
from .command_sub import CommandSubstitution
from .glob import GlobExpander
from .tilde import TildeExpander
from .variable import VariableExpander
from .word_expander import WordExpander
from .word_expansion_types import (
    COMMAND_ARGUMENT,
    DECLARATION_ASSIGNMENT,
    WordExpansionPolicy,
)
from .word_splitter import WordSplitter

if TYPE_CHECKING:
    from ..shell import Shell
    from .evaluator import ExpansionEvaluator

#: Builtins whose ``NAME=value`` arguments get bash's declaration-argument
#: expansion: no word splitting and no pathname expansion of the value
#: (``declare foo=$x`` keeps "$x" intact; ordinary commands split it).
#: Matches bash 5.2: alias, declare, typeset, export, local, readonly.
#: NOT in the set: ``env`` (a regular command), and ``command``/``builtin``
#: prefixes (bash 5.2 loses declaration semantics through them — verified).
DECLARATION_BUILTINS = frozenset(
    {'alias', 'declare', 'typeset', 'export', 'local', 'readonly'})


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
        self.word_expander = WordExpander(self)
        self.brace_expander = WordBraceExpander()

        # Initialize expansion evaluator (lazy import to avoid circular dependencies)
        self._evaluator: Optional['ExpansionEvaluator'] = None

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
        1. Brace expansion (per word, via brace_expand_word — Word → List[Word])
        2. Tilde expansion
        3. Variable expansion
        4. Command substitution
        5. Arithmetic expansion
        6. Word splitting
        7. Pathname expansion (globbing)
        8. Quote removal

        Process substitutions need no pre-pass: they are ProcessSubstitution
        expansion parts inside Words (whole-word ``<(cmd)`` and embedded
        ``pre<(cmd)post`` alike) and are performed by the word expander. The
        fds/pids register with the ProcessSubstitutionHandler; the enclosing
        process_sub_scope() (CommandExecutor) closes the parent fds and
        reaps the children when the command finishes.

        Args:
            declaration_eligible: When False the command word can never be
                recognized as a declaration builtin (used for the ``\\cmd``
                backslash bypass — bash treats ``\\export foo=$x`` as an
                ordinary command and word-splits the value).
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

        # Brace expansion (bash's first word-expansion step) runs here, per
        # command, reading the LIVE braceexpand option — so a `set +B` that
        # actually ran already updated it. `{a,b}` becomes MULTIPLE Words
        # before variable expansion; declaration-builtin assignment args are
        # brace-expanded too (bash: `declare foo={a,b}` sets foo twice). The
        # command word is the first EMITTED field, so only fields past it can
        # be declaration assignments.
        first_field = True
        for word in command.words:
            for bword in self.brace_expand_word(word):
                declaration_assignment = (
                    is_declaration and not first_field
                    and self.assignment_word_prefix(bword) is not None)
                policy = (DECLARATION_ASSIGNMENT if declaration_assignment
                          else COMMAND_ARGUMENT)
                expanded = self.word_expander.expand(bword, policy)
                if isinstance(expanded, list):
                    args.extend(expanded)
                else:
                    args.append(expanded)
                first_field = False

        # Debug: show post-expansion args
        if self.state.options.get('debug-expansion'):
            print(f"[EXPANSION] Word AST Result: {args}", file=self.state.stderr)

        return args

    def brace_expand_word(self, word: Word) -> List[Word]:
        """Brace-expand one Word into the Words it produces (bash step 1).

        Gated on the LIVE ``braceexpand`` option (``set -B``/``+B``,
        ``set ±o braceexpand``, CLI ``-B``/``+B``): when off, ``{a,b}`` stays a
        single literal Word. Reading the option HERE — at word-expansion time,
        per command — is what makes a runtime toggle correct without the
        parse-time look-ahead the token-stream expander needed. Returns
        ``[word]`` unchanged when the option is off or nothing expands.
        """
        if not self.state.options.get('braceexpand', True):
            return [word]
        return self.brace_expander.expand(word)

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
        m = ASSIGNMENT_PREFIX_RE.match(text)
        return m.group(0) if m else None

    def expand_word_to_fields(self, word,
                              policy: WordExpansionPolicy) -> List[str]:
        """Expand a Word into zero or more fields under a named policy.

        Runs the same pipeline as command arguments — tilde, variable and
        command expansion, IFS word splitting of unquoted expansions, and
        quote-aware pathname expansion honoring noglob/nullglob/dotglob —
        with *policy* (a named :class:`WordExpansionPolicy` from
        ``word_expander.py``: LOOP_ITEM, ARRAY_INIT_ELEMENT,
        ASSOC_INIT_ELEMENT, ...) selecting what the context permits.

        Returns a list: an unquoted expansion of an empty/unset value
        contributes zero fields; a quoted empty string contributes one.

        This is the single funnel for the field-producing non-argument
        contexts — for/select loop items, indexed/associative array-init
        elements, and redirect targets — so brace expansion (bash step 1,
        live-option-gated) applies to all of them here. A redirect target that
        brace-expands to more than one field then trips the caller's
        "ambiguous redirect" rule, matching bash.
        """
        fields: List[str] = []
        for bword in self.brace_expand_word(word):
            expanded = self.word_expander.expand(bword, policy)
            if isinstance(expanded, list):
                fields.extend(expanded)
            else:
                fields.append(expanded)
        return fields

    def expand_assignment_value_word(self, word) -> str:
        """Expand a Word holding an assignment VALUE (the text after ``=``).

        Delegates to the scalar walker in ``word_expander.py`` — bash
        assignment-value semantics (all expansions, NO splitting, NO
        globbing, tilde at value start and after each ``:``), shared by
        scalar assignments, array element assignments, and explicit-index
        initializer entries.
        """
        return self.word_expander.expand_assignment_value_word(word)

    def expand_expansion(self, expansion, quote_ctx=None) -> str:
        """Evaluate a single expansion AST node to a string (public API).

        Used by the executor when building an assignment value from Word parts;
        kept public so callers need not reach into a private method.
        ``quote_ctx`` (expansion.operands: None / DQ_WORD / DQ_STRING) is
        the quote context enclosing the expansion — pass DQ_WORD for a
        part inside double quotes so ``${x:-'q'}`` keeps bash's
        context-dependent quoting rules.
        """
        # Use ExpansionEvaluator for clean evaluation. Errors propagate:
        # user-facing failures arrive as ExpansionError/UnboundVariableError
        # (e.g. ${var:?msg}, nounset, bad slice offsets), and anything else
        # (AttributeError/TypeError/ValueError) is an implementation defect
        # that must fail loudly rather than silently degrade to the literal
        # text of the expansion (the pre-v0.300 fallback returned
        # str(expansion), turning internal bugs into garbage output).
        return self.evaluator.evaluate(expansion, quote_ctx=quote_ctx)

    def expand_word_as_subject(self, word) -> str:
        """Expand a ``case`` subject Word to a single string.

        bash applies tilde (leading only), parameter, command and arithmetic
        expansion plus quote removal to a case subject, but NO word splitting
        and NO pathname expansion — so a single-quoted subject (``case '$x'
        in``) stays literal. Delegates to the canonical Word engine under the
        :data:`CASE_SUBJECT` policy; a standalone ``$@``/array subject (which
        the no-split engine returns as a list) is joined with spaces.
        """
        from .word_expansion_types import CASE_SUBJECT
        result = self.word_expander.expand(word, CASE_SUBJECT)
        return ' '.join(result) if isinstance(result, list) else result

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
                from .operands import DQ_WORD
                expanded = self.expand_expansion(
                    part.expansion,
                    quote_ctx=DQ_WORD if part.quoted else None)
                out.append(ve.glob_escape(expanded) if part.quoted else expanded)
        return ''.join(out)

    def expand_string_variables(self, text: str, quote_ctx=None,
                                lexed: bool = False) -> str:
        """
        Expand variables and arithmetic in a string.
        Used for here strings and double-quoted strings. ``quote_ctx``
        (expansion.operands) tells nested ``${x:-word}`` operands what
        quoting context encloses them (heredoc bodies pass DQ_STRING).
        ``lexed=True`` (``[[ ]]`` string operands) single-decodes backslashes
        — the text was already escape-decoded by the lexer, so only ``\\$`` is
        stripped and a ``\\``-run is not collapsed a second time.
        """
        return self.variable_expander.expand_string_variables(
            text, quote_ctx=quote_ctx, lexed=lexed)

    def expand_ps4(self) -> str:
        """Expand the ``PS4`` xtrace prefix like bash.

        Every ``set -x`` trace line is prefixed with ``PS4`` (default ``+ ``).
        bash expands it on each use with parameter, command, and arithmetic
        expansion (but no word splitting or globbing) — so a common
        ``PS4='+ ${LINENO}: '`` reports the traced line. The SINGLE PS4
        expansion helper: every xtrace emission site routes through here.
        A value with no expansion sigil is returned untouched (the fast,
        overwhelmingly common case), and an expansion that raises falls back
        to the raw value so tracing itself never aborts the shell.
        """
        ps4 = self.shell.state.get_variable('PS4', '+ ')
        if '$' not in ps4 and '`' not in ps4:
            return ps4
        # Disable xtrace while expanding PS4: a command/arithmetic
        # substitution INSIDE PS4 would otherwise be traced too, and tracing
        # it re-expands PS4, recursing forever (`PS4='$(cmd) '`). bash
        # suppresses tracing during PS4 expansion for the same reason.
        options = self.shell.state.options
        saved_xtrace = options.get('xtrace', False)
        options['xtrace'] = False
        try:
            return self.expand_string_variables(ps4)
        except Exception:
            return ps4
        finally:
            options['xtrace'] = saved_xtrace

    def expand_string_tildes(self, text: str) -> str:
        """Value-context tilde expansion of a raw string: an unquoted ``~``/
        ``~user`` prefix at the start and after each ``:`` is expanded
        (``~:~`` -> both, ``x~y`` -> unchanged). Used by unquoted here-strings,
        which tilde-expand like an assignment value but are not word-split.
        Apply BEFORE variable expansion (POSIX order)."""
        return self.word_expander.expand_value_tildes(text)

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
        """Execute a ``$((expr))`` arithmetic expansion and return its value.

        Thin delegate; the strip-and-adapt logic lives next to the
        evaluator in ``arithmetic.py``.

        Raises:
            ExpansionError: If arithmetic evaluation fails
        """
        from .arithmetic import execute_arithmetic_expansion
        return execute_arithmetic_expansion(expr, self.shell)

    def arithmetic_expansion_value(self, expr: str) -> int:
        """Evaluate a BARE arithmetic expression (no ``$(( ))`` wrapper).

        For the Word-AST evaluator, which holds the raw expression text and
        would otherwise wrap it in ``$(( ))`` just to have it stripped again.

        Raises:
            ExpansionError: If arithmetic evaluation fails
        """
        from .arithmetic import arithmetic_expansion_value
        return arithmetic_expansion_value(expr, self.shell)
