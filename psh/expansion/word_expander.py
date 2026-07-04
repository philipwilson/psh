"""The Word expansion engine: named policies and the two word walkers.

Every context that expands a Word AST node has a NAME here. The policy
table at the top maps each context to the three axes that actually vary
between contexts (verified against every caller, 2026-06-12):

| Policy                  | split | glob | assignment_tilde |
|-------------------------|-------|------|------------------|
| ``COMMAND_ARGUMENT``    |  yes  | yes  | yes              |
| ``LOOP_ITEM``           |  (alias of COMMAND_ARGUMENT)    |
| ``DECLARATION_ASSIGNMENT`` | no | no   | yes              |
| ``ARRAY_INIT_ELEMENT``  |  yes  | yes  | no               |
| ``ASSOC_INIT_ELEMENT``  |  no   | no   | no               |

Two walkers live side by side and are intentionally SEPARATE:

* :meth:`WordExpander.expand` — the field-producing engine for command
  arguments, loop items and array initializer elements. A Word goes in,
  zero or more fields come out (IFS splitting, globbing, ``$@`` field
  semantics, the zero-field rule for vanished unquoted expansions).
* :meth:`WordExpander.expand_assignment_value_word` — the scalar walker
  for assignment VALUES (``v=...``, ``a[i]=...``, ``h=([k]=...)``).
  It never produces fields, and its tilde trigger is different: the
  value *starts* in tilde-trigger position (``v=~`` expands), whereas
  the field engine only reaches tilde-trigger position after walking an
  unquoted ``NAME=`` prefix. Merging them would re-tangle what the
  policy table just untangled.

The escape processors (:meth:`WordExpander.process_dquote_escapes`,
:meth:`WordExpander._process_unquoted_escapes`) live here WITH the
walkers, not in ``utils/escapes.py`` — that module's dialect map
deliberately excludes word-level (quote-context) escape processing.
"""
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Union

from ..ast_nodes import (
    ExpansionPart,
    LiteralPart,
    ProcessSubstitution,
    Word,
)
from .glob import GLOB_METACHARS, has_glob_metacharacters
from .operands import DQ_WORD
from .word_expansion_types import (
    ExpandedSegment,
    WordExpansionPolicy,
    _WalkState,
)

if TYPE_CHECKING:
    from .manager import ExpansionManager


#: Sentinel: the expansion-part walker handled the part normally; keep
#: walking. (A real return value — str or list, including '' and [] —
#: means the part took over the whole word.)
_CONTINUE_WALK = object()


class WordExpander:
    """Expands Word AST nodes under a named :class:`WordExpansionPolicy`.

    Constructed by :class:`ExpansionManager` with itself, mirroring the
    TildeExpander/GlobExpander constructor idiom one level up: this class
    needs the manager's evaluator and sibling expanders, not raw shell
    state alone.
    """

    def __init__(self, manager: 'ExpansionManager'):
        self.manager = manager
        self.shell = manager.shell
        self.state = manager.state

    # ------------------------------------------------------------------
    # The field-producing engine
    # ------------------------------------------------------------------

    def expand(self, word: Word,
               policy: WordExpansionPolicy) -> Union[str, List[str]]:
        """Expand a Word AST node using per-part quote context.

        Uses structural information from Word parts to determine glob
        suppression, word splitting, and tilde expansion behavior; the
        *policy* names what the surrounding context permits.

        Returns:
            Either a single string or a list of strings (for word
            splitting or ``$@`` expansion).
        """
        # Fallback audit 2026-06-12: every caller passes a Word built by a
        # parser; coercing other types to str() masked type bugs as
        # literal text. Fail loudly (v0.300 policy).
        if not isinstance(word, Word):
            raise TypeError(
                f"WordExpander.expand expects a Word AST node, got "
                f"{type(word).__name__}: {word!r}")

        # Single-quoted word: no expansion at all.
        # ANSI-C quoted word ($'...'): lexer already processed escapes,
        # treat as literal. Both are pure quote removal.
        if word.quote_type in ("'", "$'"):
            return word.to_literal_string()

        # Double-quoted word (uniform quote_type on the Word itself):
        # expand variables/commands but no word splitting or globbing
        if word.quote_type == '"':
            return self._expand_double_quoted_word(word, policy)

        # --- Composite / unquoted word: walk parts, then finish ---
        st = _WalkState()
        # Assignment-shaped word (NAME=... / NAME+=...): bash expands
        # tilde prefixes in the value after the first '=' and after each
        # ':' (command arguments and for/select items; indexed-array
        # initializer elements use a tilde-free policy).
        if policy.assignment_tilde:
            st.assign_prefix = self.manager.assignment_word_prefix(word)

        for part_index, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                self._walk_literal_part(word, part_index, part, st)
            elif isinstance(part, ExpansionPart):
                early = self._walk_expansion_part(word, part, st, policy)
                if early is not _CONTINUE_WALK:
                    return early

        return self._finish(st, policy)

    def _walk_literal_part(self, word: Word, part_index: int,
                           part: LiteralPart, st: _WalkState) -> None:
        """Walk one LiteralPart: quote-aware escape processing,
        assignment value-tilde tracking, leading-tilde expansion, and
        unquoted-glob detection."""
        text = part.text
        if st.assign_prefix is not None and part.quoted:
            # Quoted text never extends the assignment prefix and
            # never triggers value-tilde expansion.
            st.prev_char = ''
            st.value_len += 1
        if part.quoted and part.quote_char == "'":
            # Single-quoted literal: completely literal
            st.segments.append(ExpandedSegment(text, quoted=True))
        elif part.quoted and part.quote_char == "$'":
            # ANSI-C quoted literal: lexer already processed escapes
            st.segments.append(ExpandedSegment(text, quoted=True))
        elif part.quoted and part.quote_char == '"':
            # Double-quoted literal: after WordBuilder decomposition,
            # expansions are separate ExpansionPart nodes, so this
            # LiteralPart is purely literal text.  But backslash
            # escapes (\$, \\, \", \`) still need processing.
            if '\\' in text:
                text = self.process_dquote_escapes(text)
            st.segments.append(ExpandedSegment(text, quoted=True))
        else:
            seg_has_glob = False
            if st.assign_prefix is not None:
                parts_follow = part_index < len(word.parts) - 1
                remaining = len(st.assign_prefix) - st.assign_seen
                if remaining > 0:
                    take = min(remaining, len(text))
                    st.assign_seen += take
                    head, chunk = text[:take], text[take:]
                    # A non-empty chunk directly follows the '='.
                    trigger = bool(chunk)
                else:
                    head, chunk = '', text
                    # ':' always re-triggers; the assignment '='
                    # only when no value text has intervened.
                    trigger = (st.prev_char == ':'
                               or (st.prev_char == '=' and st.value_len == 0))
                if chunk:
                    expanded_chunk = self._expand_assignment_value_tildes(
                        chunk, trigger, parts_follow)
                    st.value_len += len(chunk)
                    text = head + expanded_chunk
                st.prev_char = text[-1] if text else st.prev_char
            # Process escape sequences in unquoted text
            if '\\' in text:
                text, escaped_globs = self._process_unquoted_escapes(text)
                # If glob chars remain that weren't escaped, track them
                if has_glob_metacharacters(text) and not escaped_globs:
                    seg_has_glob = True
            else:
                # Track unquoted glob chars
                if has_glob_metacharacters(text):
                    seg_has_glob = True
            # Unquoted literal: tilde on first part if leading ~ and the
            # tilde word is wholly unquoted literal (bash) — see
            # _leading_tilde_expandable for the boundary rule.
            if (not st.has_expansion and not st.segments
                    and text.startswith('~')
                    and self._leading_tilde_expandable(
                        part.text,
                        parts_follow=part_index < len(word.parts) - 1)):
                text = self.manager.expand_tilde(text)
            st.segments.append(ExpandedSegment(
                text, quoted=False, glob_eligible=seg_has_glob))

    @staticmethod
    def _leading_tilde_expandable(raw_text: str, parts_follow: bool) -> bool:
        """Whether a word-leading ``~`` literal starts an expandable prefix.

        bash expands a word-leading tilde-prefix (delimited at the first
        unquoted ``/`` or ``:`` — TildeExpander.prefix_end) only when every
        character of the tilde WORD (``~`` up to the first unquoted ``/``,
        or the whole word) is an unquoted literal. Scanning the RAW literal
        text up to its first ``/``:

        - a backslash escape is a quoted character inside the tilde word
          (``echo ~\\:x`` / ``~\\/x`` / ``~b\\in`` all stay literal), and an
          escaped ``~`` itself never expands;
        - running off the literal's end into a following part — quoted text
          or an expansion — means the prefix is not self-contained
          (``echo ~"x"`` → ``~x``, ``echo ~$USER`` → ``~pwilson``,
          ``echo ~:"x"`` → ``~:x``; probed bash 5.2);
        - a ``/`` bounds the tilde word inside this literal, so following
          parts are irrelevant (``echo ~/x"y"`` expands).

        Known documented divergence: when a ``:``-bounded prefix runs into
        an expansion part (``echo ~:$X``), bash 5.2 expands the tilde AND
        pastes the rest verbatim ($X unexpanded — a tilde_find_word quirk);
        psh keeps the whole word literal-then-normal (``~:<value of X>``).
        """
        if raw_text.startswith('\\~'):
            return False
        for ch in raw_text[1:]:
            if ch == '/':
                return True
            if ch == '\\':
                return False
        return not parts_follow

    def _walk_expansion_part(self, word: Word, part: ExpansionPart,
                             st: _WalkState,
                             policy: WordExpansionPolicy) -> Any:
        """Walk one ExpansionPart.

        Returns ``_CONTINUE_WALK`` when the part was accumulated normally;
        otherwise the part took over the whole word and the return value
        (a str or list, possibly ``''`` or ``[]``) is the final result —
        quoted field expansions with affixes ("pre$@post") and a
        standalone unquoted ``$@``/``${a[@]}`` short-circuit this way.
        """
        st.has_expansion = True
        if st.assign_prefix is not None:
            # Expansion results never trigger value-tilde expansion
            # (the check is syntactic, on the pre-expansion word).
            st.prev_char = ''
            st.value_len += 1

        # Process substitution (<(cmd) / >(cmd)) — whole-word or
        # embedded. Perform it and splice the /dev/fd/N path into
        # the word at this position. The path is NOT subject to
        # word splitting or globbing (bash: process substitution
        # is not a parameter/command/arithmetic expansion, so its
        # result never field-splits, even with a pathological IFS).
        if isinstance(part.expansion, ProcessSubstitution):
            path = self.shell.io_manager.create_process_substitution_for_expansion(
                part.expansion.direction, part.expansion.command)
            # The /dev/fd/N path is unquoted-but-unsplittable: it counts
            # against all_parts_quoted (so extglob may still be detected on
            # the joined word) yet is never field-split or globbed.
            st.segments.append(ExpandedSegment(path, quoted=False))
            return _CONTINUE_WALK

        # Handle quoted field expansions ("$@", "${a[@]}", ...) in
        # composite words: pre"$@"post with params (a,b,c) →
        # [prea, b, cpost]. In NO-SPLIT contexts (assoc-init elements,
        # declaration assignment values) bash instead joins the fields
        # into one word with single spaces — always spaces, regardless
        # of IFS (probed 2026-06-13: `h=("$@" v)` with params ("a b", c)
        # creates the single key "a b c"; `declare v="$@"` joins too).
        if part.quoted:
            fields = self._field_expansion_fields(part)
            if fields is not None:
                if not policy.split:
                    if fields:
                        st.segments.append(
                            ExpandedSegment(' '.join(fields), quoted=True))
                    # Zero fields contribute nothing. (bash goes on to
                    # reject the then-empty word as an assoc key — "bad
                    # array subscript" — but psh accepts empty assoc
                    # keys generally; that pre-existing divergence is
                    # independent of this path.)
                    return _CONTINUE_WALK
                return self._expand_at_with_affixes(
                    word, part, [s.text for s in st.segments],
                    in_double_quote=False, first_fields=fields)

        # An unquoted field expansion standing alone ($@, ${a[@]}):
        # expand to fields FIRST, then IFS-split each field, so
        # parameter/element boundaries survive a custom IFS (bash).
        # In no-split contexts the fields join with spaces instead and
        # are never split or globbed (bash: `h=($@)` with params
        # ("a b", c) creates the single key "a b c"; a literal `*`
        # parameter stays literal). Until v0.326 this path ignored the
        # policy — the flip to bash is Tier B10a, 2026-06-13.
        if not part.quoted and len(word.parts) == 1:
            ufields = self._field_expansion_fields(part)
            if ufields is not None:
                if not policy.split:
                    return ' '.join(ufields) if ufields else []
                out: List[str] = []
                globby = False
                for f in ufields:
                    # A field carrying operand segments (a triggered
                    # ${a[@]:-'a b'} default) splits and globs only its
                    # unprotected regions (bash).
                    fsegs = getattr(f, 'segments', None)
                    if fsegs is None:
                        pieces = self._split_with_ifs(f)
                        out.extend(pieces)
                        globby = globby or any(
                            has_glob_metacharacters(piece) for piece in pieces)
                    else:
                        out.extend(self._field_split_pass(
                            self._operand_segments_to_expanded(fsegs)))
                        globby = globby or any(
                            not protected and has_glob_metacharacters(text)
                            for text, protected in fsegs)
                if globby and not self.state.options.get('noglob', False):
                    return self._glob_words(out)
                return out

        expanded = self.manager.expand_expansion(
            part.expansion, quote_ctx=DQ_WORD if part.quoted else None)
        if part.quoted:
            # Quoted expansion: no word splitting, no globbing on result
            st.segments.append(ExpandedSegment(expanded, quoted=True))
        else:
            segs = getattr(expanded, 'segments', None)
            if segs is not None:
                # A value-operand result (${x:-word}): quoted/escaped
                # regions of the operand are protected from splitting
                # and globbing (bash: ${x:-'a b'} stays one field).
                for seg in self._operand_segments_to_expanded(segs):
                    st.segments.append(seg)
                if not segs:
                    # Empty operand: keep the zero-field rule (an
                    # expansion that vanishes contributes no field).
                    st.segments.append(ExpandedSegment(
                        '', quoted=False, splittable=True))
            else:
                # Unquoted expansion: its text is the only splittable
                # text, and glob chars in it trigger globbing.
                has_glob = has_glob_metacharacters(expanded)
                st.segments.append(ExpandedSegment(
                    expanded, quoted=False, splittable=True,
                    glob_eligible=has_glob))
        return _CONTINUE_WALK

    @staticmethod
    def _operand_segments_to_expanded(
            segs: Tuple[Tuple[str, bool], ...]) -> List[ExpandedSegment]:
        """Map OperandResult (text, protected) pairs to ExpandedSegments.

        Protected regions (quoted/escaped operand text) become quoted
        segments — never split, never globbed; unprotected regions stay
        splittable and glob-eligible, like any unquoted expansion result.
        """
        return [
            ExpandedSegment(text, quoted=True) if protected
            else ExpandedSegment(text, quoted=False, splittable=True,
                                 glob_eligible=has_glob_metacharacters(text))
            for text, protected in segs
        ]

    def _finish(self, st: _WalkState,
                policy: WordExpansionPolicy) -> Union[str, List[str]]:
        """Turn the walked segment list into the final str-or-list.

        Three visibly separate passes over ``st.segments``:

        1. **field-splitting pass** (:meth:`_field_split_pass`) — split the
           splittable segments on IFS, edge-joining literal/quoted text;
           runs only for splitting policies with an unquoted expansion
           present. May settle the result to a multi-field list (then we
           glob each field), a single field, or zero fields.
        2. **glob pass** (:meth:`_glob_pass`) — pathname-expand when
           unquoted glob metacharacters (or, in unquoted text, extglob
           patterns) are present and the policy permits it.
        3. **join/quote-removal** — concatenate any remaining segments
           into the scalar result.

        Quote removal already happened part-by-part during the walk (each
        segment's ``text`` is post-quote-removal), so pass 3 is a plain
        join.
        """
        has_unquoted_glob = st.has_unquoted_glob

        # --- Pass 1: field splitting -----------------------------------
        if st.has_unquoted_expansion and policy.split:
            words = self._field_split_pass(st.segments)
            if len(words) > 1:
                return self._glob_pass(words, has_unquoted_glob, policy)
            elif len(words) == 1:
                result = words[0]
            else:
                # A purely unquoted expansion that splits to nothing (e.g.
                # `set -- $unset`) contributes zero fields, not one empty one.
                return []
        else:
            result = ''.join(s.text for s in st.segments)

        # extglob patterns in unquoted text also count as glob-eligible.
        if (not has_unquoted_glob and not st.all_parts_quoted
                and self.state.options.get('extglob', False)):
            from .extglob import contains_extglob
            if contains_extglob(result):
                has_unquoted_glob = True

        # --- Pass 2: globbing (single word) + Pass 3: join -------------
        globbed = self._glob_pass([result], has_unquoted_glob, policy)
        if len(globbed) == 1:
            return globbed[0]
        return globbed

    def _field_split_pass(self,
                          segments: List[ExpandedSegment]) -> List[str]:
        """Pass 1: IFS-split the splittable segments, edge-joining the rest.

        Only the text of unquoted expansion segments
        (``segment.splittable``) can produce field boundaries; literal and
        quoted text never splits — even if it contains IFS characters that
        arrived via escape processing (``pre\\ post$x`` stays one field) —
        but it merges with adjacent expansion fragments into a single
        field (``a"$x"b``). Uses :meth:`WordSplitter.split_with_edges` so a
        leading/trailing IFS run is reported and the join is correct.
        """
        ifs = self.state.get_variable('IFS', ' \t\n')
        fields: List[str] = []
        current: Optional[str] = None  # None = no field currently open
        for seg in segments:
            text = seg.text
            if not seg.splittable:
                current = (current or '') + text
                continue
            pieces, leading, trailing = \
                self.manager.word_splitter.split_with_edges(text, ifs)
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

    def _glob_pass(self, words: List[str], has_unquoted_glob: bool,
                   policy: WordExpansionPolicy) -> List[str]:
        """Pass 2: pathname-expand *words* when the word is glob-eligible.

        A no-op (returns *words* unchanged) unless unquoted glob
        metacharacters are present, the policy permits globbing, and
        noglob is off — so ``declare foo=*`` keeps the literal ``*`` even
        when files would match.
        """
        if (has_unquoted_glob and policy.glob
                and not self.state.options.get('noglob', False)):
            return self._glob_words(words)
        return words

    # ------------------------------------------------------------------
    # The scalar assignment-value walker (kept SEPARATE — see module
    # docstring: its tilde trigger and no-field semantics differ).
    # ------------------------------------------------------------------

    def expand_assignment_value_word(self, word: Word) -> str:
        """Expand a Word holding an assignment VALUE (the text after ``=``).

        Implements bash assignment-value semantics, shared by scalar
        assignments (``v=...``, via CommandAssignments._expand_value)
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
        # Fallback audit 2026-06-12: callers always pass a Word (executor
        # assignment paths build them); str() coercion masked type bugs.
        if not isinstance(word, Word):
            raise TypeError(
                f"expand_assignment_value_word expects a Word AST node, "
                f"got {type(word).__name__}: {word!r}")

        result_parts: List[str] = []
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
                    result_parts.append(str(self.manager.expand_expansion(
                        part.expansion,
                        quote_ctx=DQ_WORD if part.quoted else None)))
                prev_char = ''
                value_len += 1

        return ''.join(result_parts)

    def expand_value_tildes(self, text: str) -> str:
        """Value-context tilde expansion of a raw string (public).

        Expands an unquoted ``~``/``~user`` prefix at the START and after each
        ``:`` (``~:~`` -> both, ``a:~`` -> the second, ``x~y`` -> unchanged) —
        bash's assignment-value rule. Used for here-strings, which tilde-expand
        like a value but are not word-split.
        """
        return self._expand_assignment_value_tildes(
            text, first_trigger=True, parts_follow=False)

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
        prefix_end = self.manager.tilde_expander.prefix_end
        out = []
        for idx, seg in enumerate(segments):
            if seg.startswith('~') and (idx > 0 or first_trigger):
                # Shared boundary rule (TildeExpander.prefix_end); the
                # colon-split segments contain no ':', so this reduces to
                # "does a '/' bound the prefix inside this segment".
                prefix_open = (idx == last and parts_follow
                               and prefix_end(seg) == len(seg))
                if not prefix_open:
                    seg = self.manager.tilde_expander.expand(seg)
            out.append(seg)
        return ':'.join(out)

    # ------------------------------------------------------------------
    # Field-expansion helpers ("$@", "${a[@]}", affix distribution)
    # ------------------------------------------------------------------

    def _field_expansion_fields(self,
                                part: ExpansionPart) -> Optional[List[str]]:
        """Fields if this ExpansionPart is field-producing in double quotes.

        Returns the list of fields for ``$@``, ``${a[@]}``, ``${@:2}``,
        ``${a[@]:1:2}``, ``${a[@]@Q}`` etc., or None when the expansion has
        scalar semantics (everything else, including ``$*``/``${a[*]}``).
        """
        from ..ast_nodes import ParameterExpansion, VariableExpansion
        exp = part.expansion
        quote_ctx = DQ_WORD if part.quoted else None
        if isinstance(exp, VariableExpansion):
            if exp.name == '@':
                return list(self.state.positional_params)
            if '[@]' in exp.name:
                # Unquoted ${a[@]} arrives as VariableExpansion('a[@]')
                # (the quoted form parses as ParameterExpansion).
                return self.manager.variable_expander.expand_to_fields(
                    exp.name, None, None)
            return None
        if isinstance(exp, ParameterExpansion):
            return self.manager.variable_expander.expand_to_fields(
                exp.parameter, exp.operator, exp.word, quote_ctx=quote_ctx)
        return None

    def _expand_double_quoted_word(self, word: Word,
                                   policy: WordExpansionPolicy
                                   ) -> Union[str, List[str]]:
        """Expand a uniformly double-quoted Word (quote_type='"').

        Handles multi-field expansion ("$@", "${a[@]}", slices, transforms)
        and variable/command expansion but suppresses word splitting and
        globbing. In NO-split contexts, field expansions join into one
        word with single spaces instead of producing fields (bash:
        `h=("$@")` with params ("a b", c) creates the single key "a b c";
        see _walk_expansion_part).
        """
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
                    if not policy.split:
                        if fields:
                            result_parts.append(' '.join(fields))
                        continue
                    return self._expand_at_with_affixes(
                        word, part, result_parts, in_double_quote=True,
                        first_fields=fields)

                expanded = self.manager.expand_expansion(part.expansion,
                                                          quote_ctx=DQ_WORD)
                result_parts.append(expanded)

        return ''.join(result_parts)

    def _expand_at_with_affixes(self, word: Word, at_part: ExpansionPart,
                                result_parts_before: List[str],
                                in_double_quote: bool,
                                first_fields: Optional[List[str]] = None):
        """Distribute expansion fields across prefix/suffix text.

        Used by both :meth:`expand` (composite words) and
        :meth:`_expand_double_quoted_word` to handle field-producing
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
                current_seed += self.manager.expand_expansion(p.expansion)
                has_content = True

        # Finalize: the current seed becomes the last word
        result_words.append(current_seed)

        if len(result_words) == 1:
            if result_words[0] == '' and not has_content:
                # Only empty field expansions: zero fields (bash)
                return []
            return result_words[0]
        return result_words

    # ------------------------------------------------------------------
    # Word-level escape processors (deliberately NOT in utils/escapes.py:
    # its dialect map excludes quote-context word escapes).
    # ------------------------------------------------------------------

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
    def _process_unquoted_escapes(text: str) -> Tuple[str, bool]:
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
                elif nxt in GLOB_METACHARS:
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
            if text[i] in GLOB_METACHARS:
                # Unescaped glob char
                had_glob_chars = True
                all_globs_escaped = False
            result.append(text[i])
            i += 1
        return ''.join(result), had_glob_chars and all_globs_escaped

    # ------------------------------------------------------------------
    # Splitting and globbing helpers
    # ------------------------------------------------------------------

    def _split_with_ifs(self, text: Optional[str]) -> List[str]:
        """Split unquoted text using the current IFS.

        Only ever called on already-unquoted field text (quoted segments are
        kept intact by the segment walk before they reach here).
        """
        if text is None:
            return []

        ifs = self.state.get_variable('IFS', ' \t\n')
        return self.manager.word_splitter.split(text, ifs)

    def _glob_words(self, words: List[str]) -> List[str]:
        """Apply glob expansion to a list of words."""
        result = []
        check_extglob = self.state.options.get('extglob', False)
        for w in words:
            is_glob = has_glob_metacharacters(w)
            if not is_glob and check_extglob:
                from .extglob import contains_extglob
                is_glob = contains_extglob(w)
            if is_glob:
                matches = self.manager.glob_expander.expand(w)
                if matches:
                    # glob_expander.expand() already returns sorted results.
                    result.extend(matches)
                elif self.state.options.get('failglob', False):
                    # failglob: a no-match glob fails the command (bash). Not
                    # fatal to the shell — the command-error handler returns 1.
                    from ..core import GlobNoMatchError
                    raise GlobNoMatchError(w)
                elif self.state.options.get('nullglob', False):
                    pass  # nullglob: no matches -> nothing
                else:
                    result.append(w)
            else:
                result.append(w)
        return result
