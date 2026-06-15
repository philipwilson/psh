"""
Array operations support for the PSH executor.

This module handles array initialization and element assignment operations,
including indexed and associative arrays.
"""

from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from ..core import (
    ArraySubscriptError,
    AssociativeArray,
    IndexedArray,
    VarAttributes,
)
from ..expansion.arithmetic import evaluate_arithmetic
from ..expansion.word_expansion_types import ARRAY_INIT_ELEMENT, ASSOC_INIT_ELEMENT

if TYPE_CHECKING:
    from ..ast_nodes import ArrayElementAssignment, ArrayInitialization, Word, WordPart
    from ..shell import Shell


class ArrayOperationExecutor:
    """
    Handles array initialization and element operations.

    This class encapsulates all logic for array operations including:
    - Array initialization (indexed and associative)
    - Array element assignment
    - Array expansion and indexing
    - Append mode operations
    """

    def __init__(self, shell: 'Shell'):
        """Initialize the array operation executor with a shell instance."""
        self.shell = shell
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager

    def execute_array_initialization(self, node: 'ArrayInitialization') -> int:
        """
        Execute array initialization: arr=(a b c)

        Args:
            node: The ArrayInitialization AST node

        Returns:
            Exit status code (0 for success)
        """
        # A variable declared associative (declare -A) keeps string keys:
        # arr=([k]=v ...) populates an AssociativeArray, not an IndexedArray.
        var_obj = self.state.scope_manager.get_variable_object(node.name)
        if var_obj and isinstance(var_obj.value, AssociativeArray):
            assoc = self.build_associative_array(
                node.words, into=(var_obj.value if node.is_append else None))
            self.state.scope_manager.set_variable(
                node.name, assoc,
                attributes=VarAttributes.ARRAY | VarAttributes.ASSOC_ARRAY)
            return 0

        existing = (var_obj.value
                    if node.is_append and var_obj is not None
                    and isinstance(var_obj.value, IndexedArray) else None)
        indexed = self.build_indexed_array(node.words, into=existing)

        # Set array in shell state
        self.state.scope_manager.set_variable(node.name, indexed, attributes=VarAttributes.ARRAY)
        return 0

    # ------------------------------------------------------------------ #
    # Shared value-computation helpers (the single implementation used by
    # BOTH the bare ``a=(...)`` path here AND the declaration builtins
    # ``declare``/``local``/``export``/``readonly``/``typeset`` via the
    # structured ArrayInitialization attached to the argument Word). They
    # expand the element Words through the SAME WordExpansionPolicy the
    # bare path always used — no string re-parsing.
    # ------------------------------------------------------------------ #

    def build_indexed_array(self, words: List['Word'],
                            into: Optional[IndexedArray] = None) -> IndexedArray:
        """Resolve indexed-array initializer element Words into an IndexedArray.

        ``into`` is the existing array to append into (``a+=(...)`` /
        ``declare -a a+=(...)``); when None a fresh array is built. Explicit
        ``[i]=v`` / ``[i]+=v`` elements set/append at the evaluated arithmetic
        index; bare elements expand through ARRAY_INIT_ELEMENT (split + glob)
        and take sequential indices after the highest index seen so far.
        """
        if into is not None:
            array = into
            next_sequential_index = array.next_index()
        else:
            array = IndexedArray()
            next_sequential_index = 0

        for word in words:
            # Check for an explicit-index assignment element: [index]=value
            # or [index]+=value (recognized only when the brackets and '='
            # are unquoted — bash treats "[0]=x" as a literal element).
            explicit = self._split_explicit_element(word)
            if explicit is not None:
                index_parts, value_word, elem_append = explicit
                # bash always evaluates indexed-array subscripts as arithmetic
                index_text = ''.join(str(p) for p in index_parts)
                try:
                    expanded_index = self.expansion_manager.expand_string_variables(index_text)
                    evaluated_index = evaluate_arithmetic(expanded_index, self.shell)
                except (ValueError, Exception):
                    # If index evaluation fails, treat as regular sequential element
                    next_sequential_index = self._add_word_fields_to_array(
                        array, word, next_sequential_index)
                    continue
                value = self.expansion_manager.expand_assignment_value_word(value_word)
                if elem_append:
                    current = array.get(evaluated_index)
                    if current is not None:
                        value = current + value
                array.set(evaluated_index, value)
                # Update next sequential index to be after this explicit index
                next_sequential_index = max(next_sequential_index, evaluated_index + 1)
            else:
                next_sequential_index = self._add_word_fields_to_array(
                    array, word, next_sequential_index)

        return array

    def build_associative_array(self, words: List['Word'],
                                into: Optional[AssociativeArray] = None
                                ) -> AssociativeArray:
        """Resolve associative-array initializer element Words.

        ``into`` is the existing array to merge into (``h+=(...)`` /
        ``declare -A h+=(...)``); when None a fresh array is built.

        bash 5.2 semantics: explicit [key]=value / [key]+=value elements set
        string keys; other elements alternate key/value pairs WITHOUT word
        splitting or pathname expansion (``h=($x)`` with x="k v" creates the
        single key "k v"); an odd trailing key gets an empty value.
        """
        from ..ast_nodes import Word

        array = into if into is not None else AssociativeArray()

        pending_key: Optional[str] = None
        for word in words:
            explicit = self._split_explicit_element(word)
            if explicit is not None:
                index_parts, value_word, elem_append = explicit
                key = self.expansion_manager.expand_assignment_value_word(
                    Word(parts=list(index_parts)))
                value = self.expansion_manager.expand_assignment_value_word(value_word)
                if elem_append:
                    current = array.get(key)
                    if current is not None:
                        value = current + value
                array.set(key, value)
            else:
                # Alternating key/value fields (no splitting, no globbing)
                for field in self.expansion_manager.expand_word_to_fields(
                        word, ASSOC_INIT_ELEMENT):
                    if pending_key is None:
                        pending_key = field
                    else:
                        array.set(pending_key, field)
                        pending_key = None

        if pending_key is not None:
            # bash: a trailing key without a value gets the empty string
            array.set(pending_key, '')

        return array

    def execute_array_element_assignment(self, node: 'ArrayElementAssignment') -> int:
        """
        Execute array element assignment: arr[i]=value

        Args:
            node: The ArrayElementAssignment AST node

        Returns:
            Exit status code (0 for success)
        """
        # Handle index - can be string or list of tokens
        if isinstance(node.index, list):
            # Expand each token if it's a variable
            expanded_parts = []
            for token in node.index:
                if hasattr(token, 'type') and str(token.type) == 'TokenType.VARIABLE':
                    # This is a variable token, expand it
                    var_name = token.value
                    expanded_parts.append(self.state.get_variable(var_name, ''))
                else:
                    # Regular token, use its value
                    expanded_parts.append(token.value if hasattr(token, 'value') else str(token))
            index_str = ''.join(expanded_parts)
        else:
            index_str = node.index

        # Expand any remaining variables in the index (e.g., ${var})
        expanded_index = self.expansion_manager.expand_string_variables(index_str)

        # Resolve a nameref array target so ``declare -n r=arr; r[3]=x`` writes
        # arr[3] (bash). resolve_nameref_name returns the name unchanged for a
        # plain (non-nameref) variable, so non-nameref arrays are unaffected.
        from ..core import NamerefCycleError
        try:
            name = self.state.scope_manager.resolve_nameref_name(node.name)
        except NamerefCycleError as e:
            self.state.scope_manager.warn_nameref_cycle(e.name)
            name = node.name

        # Get the variable to check if it's an associative array
        var_obj = self.state.scope_manager.get_variable_object(name)

        # Determine index type - first check if it's numeric or string
        is_numeric_index = False
        cleaned_index = expanded_index
        was_quoted = False

        # Remove quotes if present to check the actual key
        if len(cleaned_index) >= 2:
            if (cleaned_index.startswith('"') and cleaned_index.endswith('"')) or \
               (cleaned_index.startswith("'") and cleaned_index.endswith("'")):
                was_quoted = True
                cleaned_index = cleaned_index[1:-1]

        # ``index`` is a string key for associative arrays and an int subscript
        # for indexed arrays; the two stay correlated with ``is_numeric_index``
        # and the array's concrete type below.
        index: Union[int, str]
        if was_quoted:
            # Quoted index — treat as string key (associative array).
            # In bash, declare -A is needed for associative arrays, but PSH
            # uses quoting to infer associative intent.
            index = cleaned_index
            is_numeric_index = False
        else:
            # Unquoted index — always evaluate in arithmetic context (bash behavior).
            # evaluate_arithmetic handles bare variable names, expressions, and literals.
            try:
                index = evaluate_arithmetic(cleaned_index, self.shell)
                is_numeric_index = True
            except (ValueError, ArithmeticError, TypeError):
                # Arithmetic eval failed — treat as string key (associative array)
                index = cleaned_index
                is_numeric_index = False

        # Handle existing arrays
        if var_obj and isinstance(var_obj.value, AssociativeArray):
            # Already an associative array, use string index
            index = cleaned_index
        elif var_obj and isinstance(var_obj.value, IndexedArray):
            # Already an indexed array
            if not is_numeric_index:
                # Bash compatibility: string index on indexed array uses 0
                index = 0
            # else: use the numeric index computed above

        # Expand value with bash assignment-value semantics: all expansions
        # performed, NO word splitting, NO pathname expansion, tilde after
        # '='/':' (shared policy with scalar assignments). value_word is a
        # REQUIRED field (A2, 2026-06-13): both parsers always build it, and
        # a manually constructed node without it is a TypeError at
        # construction — so there is no None case to guard here.
        expanded_value = self.expansion_manager.expand_assignment_value_word(
            node.value_word)

        # Identify an existing array (None if we'd be creating a fresh one).
        existing = var_obj.value if (var_obj and isinstance(
            var_obj.value, (IndexedArray, AssociativeArray))) else None

        # Resolve a negative subscript to a concrete write index up front so
        # that append-mode reads and the final write target the SAME slot
        # (bash maps a[-1] to one-past-highest; see IndexedArray docs). For
        # associative arrays the key is a string and passes through unchanged.
        # An out-of-range negative index is a shell error (bash:
        # "NAME[SUB]: bad array subscript"), not an internal defect — and is
        # resolved BEFORE creating/registering a new array variable, so a
        # failed `unset b; b[-1]=x` leaves b unset (bash behavior).
        if is_numeric_index and isinstance(index, int):
            resolver = existing if isinstance(existing, IndexedArray) \
                else IndexedArray()
            try:
                index = resolver.resolve_write_index(index)
            except ArraySubscriptError as e:
                print(f"psh: {name}[{e.subscript}]: {e}",
                      file=self.state.stderr)
                return 1

        # Get or create array
        if existing is not None:
            array = existing
        else:
            # Create new array based on index type
            if is_numeric_index:
                # Numeric index, create indexed array
                array = IndexedArray()
                self.state.scope_manager.set_variable(name, array, attributes=VarAttributes.ARRAY)
            else:
                # String index, create associative array
                array = AssociativeArray()
                self.state.scope_manager.set_variable(name, array, attributes=VarAttributes.ARRAY | VarAttributes.ASSOC_ARRAY)

        is_integer = var_obj is not None and bool(
            var_obj.attributes & VarAttributes.INTEGER)

        # ``array`` and ``index`` are correlated by construction: an
        # IndexedArray always pairs with an int subscript, an AssociativeArray
        # with a string key (kept consistent above). Branch on the concrete
        # array type so the key type narrows for the union ``get``/``set``
        # calls. ``_compute_element_value`` is shared so the integer/append
        # arithmetic is written once — no behavior change.
        if isinstance(array, IndexedArray):
            idx = index if isinstance(index, int) else 0
            array.set(idx, self._compute_element_value(
                array.get(idx), expanded_value, is_integer, node.is_append))
        else:
            akey = str(index)
            array.set(akey, self._compute_element_value(
                array.get(akey), expanded_value, is_integer, node.is_append))
        return 0

    def _compute_element_value(self, current: Optional[str], expanded_value: str,
                               is_integer: bool, is_append: bool) -> str:
        """Resolve the final element string for an ``a[i]=`` write.

        Shared by the indexed/associative branches of element assignment.
        Integer (-i) elements arithmetic-evaluate the RHS and, for ``+=``, do
        a NUMERIC add against the current element (mirrors scalar ``x+=EXPR``
        on an -i var); empty RHS = 0. Non-integer ``+=`` is string
        concatenation onto the current value.
        """
        if is_integer:
            rhs = evaluate_arithmetic(expanded_value or '0', self.shell)
            if is_append:
                base = evaluate_arithmetic(current, self.shell) if current else 0
                rhs = base + rhs
            return str(rhs)
        if is_append and current is not None:
            return current + expanded_value
        return expanded_value

    # Helper methods

    def _split_explicit_element(self, word: 'Word') -> Optional[
            Tuple[List['WordPart'], 'Word', bool]]:
        """Split an initializer element of the form [index]=value.

        Recognizes ``[index]=value`` and ``[index]+=value`` when the
        brackets and the ``=`` come from *unquoted literal* text (bash:
        ``"[0]=x"`` is a literal element, not an assignment). The index may
        contain expansions and quoted segments (``[$key]=v``, ``["a b"]=v``).

        Returns (index_parts, value_word, is_append), or None when the
        element is not an explicit-index assignment.
        """
        from ..ast_nodes import LiteralPart, Word

        parts = word.parts
        if not parts:
            return None
        first = parts[0]
        if not (isinstance(first, LiteralPart) and not first.quoted
                and first.text.startswith('[')):
            return None

        depth = 0
        for i, part in enumerate(parts):
            if not (isinstance(part, LiteralPart) and not part.quoted):
                # Quoted text / expansions inside the brackets belong to
                # the index; keep scanning for the unquoted closing ']'.
                continue
            text = part.text
            start = 1 if i == 0 else 0  # skip the opening '['
            for j in range(start, len(text)):
                ch = text[j]
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    if depth > 0:
                        depth -= 1
                        continue
                    # Closing bracket: '=' or '+=' must follow immediately
                    rest = text[j + 1:]
                    if rest.startswith('+='):
                        eq_len = 2
                    elif rest.startswith('='):
                        eq_len = 1
                    else:
                        return None
                    # Index: parts before this one (minus the opening '[')
                    # plus this part's text up to the ']'
                    index_parts: List['WordPart'] = []
                    if i > 0 and len(first.text) > 1:
                        index_parts.append(LiteralPart(
                            first.text[1:], quoted=first.quoted,
                            quote_char=first.quote_char))
                    index_parts.extend(parts[1:i])
                    head = text[start:j] if i == 0 else text[:j]
                    if head:
                        index_parts.append(LiteralPart(head))
                    # Value: this part's text after '='/'+=' plus the rest
                    tail = text[j + 1 + eq_len:]
                    value_parts: List['WordPart'] = []
                    if tail:
                        value_parts.append(LiteralPart(tail))
                    value_parts.extend(parts[i + 1:])
                    return (index_parts, Word(parts=value_parts), eq_len == 2)
        return None

    def _add_word_fields_to_array(self, array: IndexedArray, word: 'Word',
                                  start_index: int) -> int:
        """Add a Word's expanded fields to the array sequentially.

        Expands through the same Word pipeline command arguments use:
        quote-aware tilde/variable/command expansion, IFS splitting of
        unquoted expansion results, and globbing that honors quoting and
        noglob/nullglob/dotglob. Each resulting field becomes one array
        element (an unquoted expansion of an empty value contributes none).
        """
        next_index = start_index
        for field in self.expansion_manager.expand_word_to_fields(
                word, ARRAY_INIT_ELEMENT):
            array.set(next_index, field)
            next_index += 1
        return next_index

