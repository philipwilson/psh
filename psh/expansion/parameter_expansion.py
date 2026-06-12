"""Advanced parameter expansion operations.

String operations behind the ``${var<op>...}`` operators (pattern removal,
substitution, substring, case modification, name matching). Parsing of the
``${...}`` syntax itself lives in param_parser.py.
"""
import re
from typing import TYPE_CHECKING, List, Optional, Union

# Canonical pattern engine lives in pattern.py; re-exported here because
# many call sites import PatternMatcher from this module.
from .pattern import PatternMatcher

if TYPE_CHECKING:
    from ..shell import Shell

# Sentinel marking "the matched text" in a prepared replacement template
# (bash 5.2 patsub_replacement: an unquoted & in the replacement).
PATSUB_MATCH = object()


class ParameterExpansion:
    """Advanced parameter expansion operations."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.pattern_matcher = PatternMatcher()

    @property
    def _extglob(self) -> bool:
        """Whether extglob is currently enabled."""
        return self.state.options.get('extglob', False)

    @staticmethod
    def render_replacement(replacement: Union[str, list], matched: str) -> str:
        """Render the replacement text for one match.

        A prepared template (list built by VariableExpander) may contain
        PATSUB_MATCH entries standing for the matched text; a plain string
        is inserted literally (never interpreted as a regex template).
        """
        if isinstance(replacement, str):
            return replacement
        return ''.join(matched if part is PATSUB_MATCH else part
                       for part in replacement)

    # Length operations
    def get_length(self, value: str) -> str:
        """Get the length of a string."""
        return str(len(value))

    # Pattern removal
    def remove_shortest_prefix(self, value: str, pattern: str) -> str:
        """Remove shortest matching prefix."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=True, extglob_enabled=self._extglob)
        # Make the regex non-greedy for shortest match
        regex = regex.replace('.*', '.*?')
        match = re.match(regex, value)
        if match:
            return value[match.end():]
        return value

    def remove_longest_prefix(self, value: str, pattern: str) -> str:
        """Remove longest matching prefix."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=True, extglob_enabled=self._extglob)
        # For longest match, use greedy regex (default behavior)
        # Try to find the longest prefix that matches
        match = re.match(regex, value)
        if match:
            # The regex will naturally find the longest match due to greedy quantifiers
            return value[match.end():]
        return value

    def remove_shortest_suffix(self, value: str, pattern: str) -> str:
        """Remove shortest matching suffix."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex
        regex = regex.rstrip('$') + '$'

        # Find shortest match from end
        for i in range(len(value), -1, -1):
            if re.match(regex, value[i:]):
                return value[:i]
        return value

    def remove_longest_suffix(self, value: str, pattern: str) -> str:
        """Remove longest matching suffix."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex
        regex = regex.rstrip('$') + '$'

        # Find longest match from end
        for i in range(len(value) + 1):
            if re.match(regex, value[i:]):
                return value[:i]
        return value

    # Pattern substitution
    def substitute_first(self, value: str, pattern: str,
                         replacement: Union[str, list]) -> str:
        """Replace first match."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob)
        return re.sub(regex,
                      lambda m: self.render_replacement(replacement, m.group(0)),
                      value, count=1)

    def substitute_all(self, value: str, pattern: str,
                       replacement: Union[str, list]) -> str:
        """Replace all matches."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=False, extglob_enabled=self._extglob)
        return re.sub(regex,
                      lambda m: self.render_replacement(replacement, m.group(0)),
                      value)

    def substitute_prefix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace prefix match."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=True, extglob_enabled=self._extglob)
        match = re.match(regex, value)
        if match:
            return (self.render_replacement(replacement, match.group(0))
                    + value[match.end():])
        return value

    def substitute_suffix(self, value: str, pattern: str,
                          replacement: Union[str, list]) -> str:
        """Replace suffix match."""
        regex = self.pattern_matcher.shell_pattern_to_regex(pattern, anchored=True, from_start=False, extglob_enabled=self._extglob)
        # Convert to end-anchored regex
        regex = regex.rstrip('$') + '$'

        # Find match at end
        match = re.search(regex, value)
        if match:
            return (value[:match.start()]
                    + self.render_replacement(replacement, match.group(0)))
        return value

    # Substring extraction
    def extract_substring(self, value: str, offset: int, length: Optional[int] = None) -> str:
        """Extract substring with offset and optional length."""
        # Handle negative offset
        if offset < 0:
            # Negative offset counts from end. If it is still negative after
            # adjusting, bash yields the empty string (not the whole value).
            offset = len(value) + offset
            if offset < 0:
                return ''

        # Handle out of bounds
        if offset >= len(value):
            return ''

        if length is None:
            # No length specified, return from offset to end
            return value[offset:]
        else:
            # Handle negative length
            if length < 0:
                # Negative length means "up to N chars from the end". If the
                # endpoint falls before the offset, bash treats it as an error
                # (e.g. `${x:0:-5}` on a short string).
                end = len(value) + length
                if end < offset:
                    raise ValueError(f"{length}: substring expression < 0")
                return value[offset:end]
            else:
                # Normal positive length
                return value[offset:offset + length]

    # Variable name matching
    def match_variable_names(self, prefix: str) -> List[str]:
        """Find all variable names starting with prefix (for ${!prefix@})."""
        # Get all variables from both shell variables and environment
        all_vars = set(self.state.variables.keys()) | set(self.state.env.keys())

        # Filter by prefix
        return sorted([var for var in all_vars if var.startswith(prefix)])

    # Case modification. bash matches the pattern against individual
    # characters: ${v^^pat} examines each char, ${v^pat} only the first.
    def _char_matches(self, char: str, pattern: str) -> bool:
        regex = self.pattern_matcher.shell_pattern_to_regex(
            pattern, anchored=False, extglob_enabled=self._extglob)
        return re.fullmatch(regex, char) is not None

    def uppercase_first(self, value: str, pattern: str = '?') -> str:
        """Uppercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            return value[0].upper() + value[1:]
        return value

    def uppercase_all(self, value: str, pattern: str = '?') -> str:
        """Uppercase every char matching the pattern."""
        return ''.join(c.upper() if self._char_matches(c, pattern) else c
                       for c in value)

    def lowercase_first(self, value: str, pattern: str = '?') -> str:
        """Lowercase the first char if it matches the pattern."""
        if value and self._char_matches(value[0], pattern):
            return value[0].lower() + value[1:]
        return value

    def lowercase_all(self, value: str, pattern: str = '?') -> str:
        """Lowercase every char matching the pattern."""
        return ''.join(c.lower() if self._char_matches(c, pattern) else c
                       for c in value)
