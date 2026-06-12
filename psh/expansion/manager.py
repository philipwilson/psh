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
import re
from typing import TYPE_CHECKING, List, Optional

from ..ast_nodes import SimpleCommand
from .command_sub import CommandSubstitution
from .glob import GlobExpander
from .tilde import TildeExpander
from .variable import VariableExpander
from .word_expander import (
    COMMAND_ARGUMENT,
    DECLARATION_ASSIGNMENT,
    WordExpander,
    WordExpansionPolicy,
)
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
        self.word_expander = WordExpander(self)

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

        for i, word in enumerate(command.words):
            declaration_assignment = (
                is_declaration and i > 0
                and self.assignment_word_prefix(word) is not None)
            policy = (DECLARATION_ASSIGNMENT if declaration_assignment
                      else COMMAND_ARGUMENT)
            expanded = self.word_expander.expand(word, policy)
            if isinstance(expanded, list):
                args.extend(expanded)
            else:
                args.append(expanded)

        # Debug: show post-expansion args
        if self.state.options.get('debug-expansion'):
            print(f"[EXPANSION] Word AST Result: {args}", file=self.state.stderr)

        return args

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
        """
        expanded = self.word_expander.expand(word, policy)
        if isinstance(expanded, list):
            return expanded
        return [expanded]

    def expand_assignment_value_word(self, word) -> str:
        """Expand a Word holding an assignment VALUE (the text after ``=``).

        Delegates to the scalar walker in ``word_expander.py`` — bash
        assignment-value semantics (all expansions, NO splitting, NO
        globbing, tilde at value start and after each ``:``), shared by
        scalar assignments, array element assignments, and explicit-index
        initializer entries.
        """
        return self.word_expander.expand_assignment_value_word(word)

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
        """Execute a ``$((expr))`` arithmetic expansion and return its value.

        Thin delegate; the strip-and-adapt logic lives next to the
        evaluator in ``arithmetic.py``.

        Raises:
            ExpansionError: If arithmetic evaluation fails
        """
        from .arithmetic import execute_arithmetic_expansion
        return execute_arithmetic_expansion(expr, self.shell)
