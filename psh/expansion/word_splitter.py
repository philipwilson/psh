"""Word splitting implementation for shell expansions."""

from typing import List, Optional, Tuple


class WordSplitter:
    """Split words according to the shell's IFS rules.

    Implements POSIX-compliant IFS word splitting:
    - IFS whitespace characters (space, tab, newline) are trimmed from
      start/end and consecutive occurrences collapse into one delimiter.
    - Non-whitespace IFS characters always produce a field boundary,
      preserving empty fields (e.g., 'a::b' with IFS=':' yields ['a', '', 'b']).
    - Each non-whitespace IFS char, along with any adjacent IFS whitespace,
      delimits a field (POSIX 2.6.5).
    - A backslash is ordinary data: expansion results are split without
      regard to backslashes (``x='a\\ b'; $x`` is two fields in bash), and
      backslash escapes in *literal* word text are protected structurally
      (only expansion results are ever split).
    - If IFS is None (unset), default ' \\t\\n' is used.
    - If IFS is '' (empty string), no splitting occurs.
    """

    def split(self, text: str, ifs: Optional[str]) -> List[str]:
        """Split text using IFS characters.

        Args:
            text: The string to split.
            ifs: The shell's IFS value. None means unset (use default),
                 empty string means no splitting.

        Returns:
            List of resulting fields after splitting.
        """
        if text is None:
            return []

        # Unset IFS uses default splitting
        if ifs is None:
            ifs = ' \t\n'

        # Empty IFS means no splitting
        if ifs == '':
            return [text]

        # Separate IFS into whitespace and non-whitespace characters
        ifs_whitespace = set(c for c in ifs if c in ' \t\n')
        ifs_non_whitespace = set(c for c in ifs if c not in ' \t\n')

        fields: List[str] = []
        current_field: List[str] = []
        i = 0

        # Skip leading IFS whitespace (but not backslash-escaped whitespace)
        while i < len(text) and text[i] in ifs_whitespace:
            i += 1

        while i < len(text):
            char = text[i]

            if char in ifs_non_whitespace:
                # Non-whitespace IFS character - always a separator.
                # Append current field (even if empty, to produce empty fields).
                fields.append(''.join(current_field))
                current_field = []
                i += 1
                # Skip adjacent IFS whitespace after non-whitespace delimiter
                while i < len(text) and text[i] in ifs_whitespace:
                    i += 1
            elif char in ifs_whitespace:
                # IFS whitespace - skip it, then check what follows.
                j = i
                while j < len(text) and text[j] in ifs_whitespace:
                    j += 1
                if j < len(text) and text[j] in ifs_non_whitespace:
                    # Whitespace is adjacent to a non-whitespace IFS char.
                    # Per POSIX, they form a single delimiter together.
                    # Advance past the whitespace AND the non-ws delimiter,
                    # finalizing current field as part of this combined delimiter.
                    fields.append(''.join(current_field))
                    current_field = []
                    i = j + 1
                    # Skip any IFS whitespace after the non-ws delimiter too
                    while i < len(text) and text[i] in ifs_whitespace:
                        i += 1
                else:
                    # Pure whitespace delimiter (or trailing whitespace).
                    # Only produces a field boundary if current_field is non-empty.
                    if current_field:
                        fields.append(''.join(current_field))
                        current_field = []
                    i = j
            else:
                # Regular character
                current_field.append(char)
                i += 1

        # Add last field if any
        if current_field:
            fields.append(''.join(current_field))

        # If no fields were found, return empty list
        if not fields:
            return []

        return fields

    def split_with_edges(self, text: str, ifs: Optional[str]) -> Tuple[List[str], bool, bool]:
        """Split text, also reporting delimiters at its edges.

        Returns (fields, leading, trailing) where *leading*/*trailing* say
        whether the text begins/ends with an IFS delimiter. Callers merging
        fields across the parts of a composite word need this: in
        ``pre$x``, a leading delimiter in ``$x`` closes the ``pre`` field.
        """
        if not text:
            return [], False, False
        if ifs is None:
            ifs = ' \t\n'
        if ifs == '':
            return [text], False, False
        return self.split(text, ifs), text[0] in ifs, text[-1] in ifs
