"""
Array operations support for the PSH executor.

This module handles array initialization and element assignment operations,
including indexed and associative arrays.
"""

import glob
import re
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from ..core import AssociativeArray, IndexedArray, VarAttributes
from ..expansion.arithmetic import evaluate_arithmetic

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
            return self._initialize_associative_array(node, var_obj.value)

        # Handle append mode
        if node.is_append:
            # Get existing array or create new one
            if var_obj and isinstance(var_obj.value, IndexedArray):
                array = var_obj.value
                # Find next index for appending
                start_index = array.next_index()
            else:
                array = IndexedArray()
                start_index = 0
        else:
            # Create new array
            array = IndexedArray()
            start_index = 0

        # Expand and add elements
        next_sequential_index = start_index

        for i, element in enumerate(node.elements):
            element_type = node.element_types[i] if i < len(node.element_types) else 'WORD'
            word = node.words[i] if i < len(node.words) else None

            # Check for an explicit-index assignment element: [index]=value
            # or [index]+=value (recognized only when the brackets and '='
            # are unquoted — bash treats "[0]=x" as a literal element).
            explicit = self._split_explicit_element(word) if word is not None else None
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
            elif element_type in ('COMPOSITE', 'COMPOSITE_QUOTED') and \
                    self._is_explicit_array_assignment(element):
                # Legacy fallback (no Word AST on the node): parse explicit
                # index assignment from the raw element string
                index, value = self._parse_explicit_array_assignment(element)
                if index is not None:
                    try:
                        evaluated_index = evaluate_arithmetic(str(index), self.shell)
                        array.set(evaluated_index, value)
                        next_sequential_index = max(next_sequential_index, evaluated_index + 1)
                    except (ValueError, Exception):
                        next_sequential_index = self._add_expanded_element_to_array(
                            array, element, next_sequential_index, split_words=False)
                else:
                    next_sequential_index = self._add_expanded_element_to_array(
                        array, element, next_sequential_index, split_words=False)
            elif word is not None:
                next_sequential_index = self._add_word_fields_to_array(
                    array, word, next_sequential_index)
            elif element_type in ('WORD', 'COMPOSITE', 'COMMAND_SUB',
                                  'ARITH_EXPANSION', 'VARIABLE'):
                # Legacy fallback (no Word AST on the node): split unquoted
                # words and expansion results on whitespace, with globbing.
                next_sequential_index = self._add_expanded_element_to_array(
                    array, element, next_sequential_index, split_words=True)
            else:
                # Legacy fallback: keep as single element (STRING, etc.)
                # Quoted strings should not be glob expanded or word split
                next_sequential_index = self._add_expanded_element_to_array(
                    array, element, next_sequential_index, split_words=False)

        # Set array in shell state
        self.state.scope_manager.set_variable(node.name, array, attributes=VarAttributes.ARRAY)
        return 0

    def _initialize_associative_array(self, node: 'ArrayInitialization',
                                      existing: AssociativeArray) -> int:
        """Initialize a declare -A variable: h=([k]=v ...) or h+=(...).

        bash 5.2 semantics: explicit [key]=value / [key]+=value elements set
        string keys; other elements alternate key/value pairs WITHOUT word
        splitting or pathname expansion (``h=($x)`` with x="k v" creates the
        single key "k v"); an odd trailing key gets an empty value.
        """
        from ..ast_nodes import Word

        array = existing if node.is_append else AssociativeArray()

        pending_key: Optional[str] = None
        for i, element in enumerate(node.elements):
            word = node.words[i] if i < len(node.words) else None
            if word is None:
                # Legacy fallback: expand the raw element text as one field
                field = self.expansion_manager.expand_string_variables(element)
                if pending_key is None:
                    pending_key = field
                else:
                    array.set(pending_key, field)
                    pending_key = None
                continue

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
                        word, suppress_split_glob=True):
                    if pending_key is None:
                        pending_key = field
                    else:
                        array.set(pending_key, field)
                        pending_key = None

        if pending_key is not None:
            # bash: a trailing key without a value gets the empty string
            array.set(pending_key, '')

        self.state.scope_manager.set_variable(
            node.name, array,
            attributes=VarAttributes.ARRAY | VarAttributes.ASSOC_ARRAY)
        return 0

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

        # Get the variable to check if it's an associative array
        var_obj = self.state.scope_manager.get_variable_object(node.name)

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
        # '='/':' (shared policy with scalar assignments).
        if node.value_word is not None:
            expanded_value = self.expansion_manager.expand_assignment_value_word(
                node.value_word)
        else:
            # Legacy fallback (no Word AST — combinator parser edge paths)
            expanded_value = self.expansion_manager.expand_string_variables(node.value)

        # Get or create array
        if var_obj and (isinstance(var_obj.value, IndexedArray) or isinstance(var_obj.value, AssociativeArray)):
            array = var_obj.value
        else:
            # Create new array based on index type
            if is_numeric_index:
                # Numeric index, create indexed array
                array = IndexedArray()
                self.state.scope_manager.set_variable(node.name, array, attributes=VarAttributes.ARRAY)
            else:
                # String index, create associative array
                array = AssociativeArray()
                self.state.scope_manager.set_variable(node.name, array, attributes=VarAttributes.ARRAY | VarAttributes.ASSOC_ARRAY)

        # Handle append mode
        if node.is_append:
            # Get current value and append
            current = array.get(index)
            if current is not None:
                expanded_value = current + expanded_value

        # Set element
        array.set(index, expanded_value)
        return 0

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
        for field in self.expansion_manager.expand_word_to_fields(word):
            array.set(next_index, field)
            next_index += 1
        return next_index

    def _add_expanded_element_to_array(self, array: IndexedArray, element: str,
                                       start_index: int, split_words: bool = True) -> int:
        """
        Add expanded element to array with glob expansion.

        Args:
            array: The array to add elements to
            element: The element to expand and add
            start_index: Starting index for sequential assignment
            split_words: Whether to split on whitespace after expansion

        Returns:
            Next available index after adding elements
        """
        # Expand variables first (don't process escape sequences in array context)
        expanded = self.expansion_manager.expand_string_variables(element)

        if split_words:
            # Split on whitespace for WORD and command substitution elements
            words = expanded.split()
        else:
            # Keep as single element for STRING and composite elements
            words = [expanded] if expanded else ['']

        # Handle glob expansion on each word (like for loops do)
        next_index = start_index
        for word in words:
            matches = glob.glob(word)
            if matches:
                # Glob pattern matched files - add all matches (already sorted)
                for match in sorted(matches):
                    array.set(next_index, match)
                    next_index += 1
            else:
                # No matches, add literal word
                array.set(next_index, word)
                next_index += 1

        return next_index

    def _is_explicit_array_assignment(self, element: str) -> bool:
        """Check if element has explicit array assignment syntax: [index]=value"""
        # Match [anything]=anything pattern
        return bool(re.match(r'^\[[^\]]*\]=', element))

    def _parse_explicit_array_assignment(self, element: str) -> Tuple[Optional[Union[str, int]], Optional[str]]:
        """
        Parse explicit array assignment: [index]=value

        Returns:
            tuple: (index, value) or (None, None) if parsing fails
        """
        match = re.match(r'^\[([^\]]*)\]=(.*)$', element)
        if match:
            index_str = match.group(1)
            value = match.group(2)

            # Expand any variables in the index
            expanded_index = self.expansion_manager.expand_string_variables(index_str)
            expanded_value = self.expansion_manager.expand_string_variables(value)

            return expanded_index, expanded_value

        return None, None
