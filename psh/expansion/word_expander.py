"""The Word expansion engine: the field-splicing algebra and the scalar walker.

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

Two producers live side by side and are intentionally SEPARATE:

* :meth:`WordExpander.expand_to_word` — the field-producing engine for command
  arguments, loop items and array initializer elements. A Word goes in, an
  :class:`ExpandedWord` (zero or more explicit fields, each an ordered run of
  homogeneous-protection :class:`FieldRun`s) comes out. One terminal boundary,
  :meth:`WordExpander.materialize`, turns that back into ``argv`` strings after
  field splitting and pathname generation — the SOLE ``ExpandedWord`` -> strings
  conversion (reappraisal #20 H5/H6: no ``str``/``list[str]`` walker, no ``$@``
  shortcut, no join before splitting/globbing).
* :meth:`WordExpander.expand_assignment_value_word` — the scalar walker for
  assignment VALUES (``v=...``, ``a[i]=...``, ``h=([k]=...)``). It never
  produces fields and never globs (an assignment value is one string), so it
  legitimately materializes to a ``str`` directly; its tilde trigger differs
  (the value *starts* in tilde-trigger position). Merging it with the field
  engine would re-tangle what the policy table just untangled.

The field-splicing algebra (``expand_to_word``):

1. **walk** each Word part -> runs appended to an open field. A multi-field
   ``$@``/``[@]`` expansion SPLICES: its first field's runs attach to the open
   field, its middle fields commit, and its last field becomes the new open
   field, so an adjacent unquoted fragment (``"$@"$x``) lands in the right
   field and still splits. No-split policies join the fields with one space
   instead (bash ``declare v="$@"``).
2. **field-split** each committed field (split policies): ``IFS_ELIGIBLE`` runs
   split on IFS, ``NEVER`` runs edge-join; an all-eligible field that splits to
   nothing elides.
3. **materialize** each field: pathname-expand when an ACTIVE run carries a
   glob/extglob metacharacter (the pattern is compiled from the runs, PROTECTED
   metacharacters bracket-escaped so a quoted/escaped ``*`` stays literal beside
   an active one), otherwise join the runs. This is the terminal boundary.

The escape processors (:meth:`WordExpander.process_dquote_escapes`,
:meth:`WordExpander._process_unquoted_escapes`) live here WITH the walkers, not
in ``utils/escapes.py`` — that module's dialect map deliberately excludes
word-level (quote-context) escape processing.
"""
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..ast_nodes import (
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    ProcessSubstitution,
    VariableExpansion,
    Word,
    WordPart,
)
from ..core import TopLevelAbort
from .glob import GLOB_METACHARS, has_glob_metacharacters
from .operands import DQ_WORD
from .word_expansion_types import (
    ExpandedField,
    ExpandedWord,
    FieldRun,
    Protection,
    Split,
    WordExpansionPolicy,
)

if TYPE_CHECKING:
    from .manager import ExpansionManager

_ACTIVE = Protection.ACTIVE
_PROTECTED = Protection.PROTECTED
_NEVER = Split.NEVER
_ELIGIBLE = Split.IFS_ELIGIBLE

#: Characters that must be neutralised for a PROTECTED run to be a literal in a
#: pathname pattern. The pathname glob engine treats backslash as a LITERAL
#: character (a deliberate prior refactor — see ``glob._compile_component``), so
#: protection is carried with single-character brackets (``[*]`` matches a
#: literal ``*``) instead. Escaping ``(`` neutralises every extglob group, since
#: an ``@(...)``/``?(...)``/... group cannot form without its ``(``.
_PATHNAME_ESCAPE = frozenset('*?[(')


class _FieldBuilder:
    """Accumulates :class:`FieldRun`s into fields under the splicing algebra.

    ``current`` is the open field (``None`` until the word contributes its first
    run) that adjacent literal/scalar text and the last field of a spliced
    ``$@``/``[@]`` extend. Committed fields are hard boundaries produced by a
    multi-field expansion; per-field IFS splitting happens afterwards.
    """

    __slots__ = ('committed', 'current')

    def __init__(self) -> None:
        self.committed: List[ExpandedField] = []
        self.current: Optional[ExpandedField] = None

    @property
    def has_content(self) -> bool:
        """True once any run has been emitted (gates the leading-tilde rule)."""
        return self.current is not None or bool(self.committed)

    def add(self, run: FieldRun) -> None:
        if self.current is None:
            self.current = ExpandedField([])
        self.current.runs.append(run)

    def add_runs(self, runs: List[FieldRun]) -> None:
        for run in runs:
            self.add(run)

    def splice(self, fields: List[ExpandedField]) -> None:
        """Splice a multi-field ``$@``/``[@]`` expansion into the word.

        The first field's runs attach to the open field; middle fields commit
        as their own fields; the last field becomes the new open field so a
        following fragment continues it. An empty ``fields`` (empty ``$@``) is a
        no-op on field boundaries — ``pre"$@"post`` with no positionals stays
        one field ``prepost``.
        """
        if not fields:
            return
        if self.current is None:
            self.current = ExpandedField([])
        self.current.runs.extend(fields[0].runs)
        if len(fields) == 1:
            return
        self.committed.append(self.current)
        self.committed.extend(fields[1:-1])
        self.current = ExpandedField(list(fields[-1].runs))

    def finish(self) -> List[ExpandedField]:
        if self.current is not None:
            self.committed.append(self.current)
            self.current = None
        return self.committed


class _AssignCtx:
    """Assignment-shaped word (``NAME=...``) value-tilde walk bookkeeping."""

    __slots__ = ('has_expansion', 'assign_prefix', 'assign_seen',
                 'value_len', 'prev_char')

    def __init__(self) -> None:
        self.has_expansion = False
        #: The unquoted ``NAME=``/``NAME+=`` prefix, or None when the word is
        #: not assignment-shaped (or the policy disables assignment_tilde).
        self.assign_prefix: Optional[str] = None
        self.assign_seen = 0    # chars of assign_prefix consumed so far
        self.value_len = 0      # value chars emitted before the current part
        self.prev_char = ''     # last unquoted-literal char ('' after others)


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

    def expand_to_word(self, word: Word,
                       policy: WordExpansionPolicy) -> ExpandedWord:
        """Expand a Word AST node to an :class:`ExpandedWord`.

        Uses per-part quote context to decide protection and split
        eligibility; *policy* names what the surrounding context permits.
        Field splitting is applied here (for split policies); pathname
        generation and the final flatten to strings happen in
        :meth:`materialize`, the sole terminal boundary.
        """
        # Fallback audit 2026-06-12: every caller passes a Word built by a
        # parser; coercing other types to str() masked type bugs as literal
        # text. Fail loudly (v0.300 policy).
        if not isinstance(word, Word):
            raise TypeError(
                f"WordExpander.expand_to_word expects a Word AST node, got "
                f"{type(word).__name__}: {word!r}")

        # Single-quoted / ANSI-C quoted word: pure quote removal, one
        # protected field (the lexer already resolved $'...' escapes).
        if word.quote_type in ("'", "$'"):
            return ExpandedWord([ExpandedField(
                [FieldRun(word.to_literal_string(), _PROTECTED, _NEVER,
                          'quoted')])])

        # Everything else (a wholly double-quoted word — whose parts are each
        # marked quoted='"' — and composite/unquoted words) walks one algebra.
        return self._walk_word(word, policy)

    def _walk_word(self, word: Word,
                   policy: WordExpansionPolicy) -> ExpandedWord:
        builder = _FieldBuilder()
        ctx = _AssignCtx()
        # Assignment-shaped word (NAME=... / NAME+=...): bash expands tilde
        # prefixes in the value after the first '=' and after each ':'.
        if policy.assignment_tilde:
            ctx.assign_prefix = self.manager.assignment_word_prefix(word)

        # A colon-bounded leading tilde extent spilling into following parts
        # (``~:$X`` -> ``$HOME:$X``, $X verbatim): pre-expand into one literal.
        extent_parts = self._collapse_leading_tilde_extent(word)
        if extent_parts is not None:
            word = Word(parts=extent_parts)
            ctx.assign_prefix = None  # synthetic word is not assignment-shaped

        for part_index, part in enumerate(word.parts):
            if isinstance(part, LiteralPart):
                self._walk_literal_part(word, part_index, part, ctx, builder)
            elif isinstance(part, ExpansionPart):
                self._walk_expansion_part(part, ctx, builder, policy)

        raw_fields = builder.finish()
        if policy.split:
            return ExpandedWord(self._field_split(raw_fields))
        return ExpandedWord(raw_fields)

    def _walk_literal_part(self, word: Word, part_index: int,
                           part: LiteralPart, ctx: _AssignCtx,
                           builder: _FieldBuilder) -> None:
        """Walk one LiteralPart: quote-aware escape processing, assignment
        value-tilde tracking, leading-tilde expansion, per-character glob
        protection."""
        text = part.text
        if ctx.assign_prefix is not None and part.quoted:
            # Quoted text never extends the assignment prefix and never
            # triggers value-tilde expansion.
            ctx.prev_char = ''
            ctx.value_len += 1
        if part.quoted and part.quote_char == "'":
            builder.add(FieldRun(text, _PROTECTED, _NEVER, 'single'))
        elif part.quoted and part.quote_char == "$'":
            builder.add(FieldRun(text, _PROTECTED, _NEVER, 'ansi'))
        elif part.quoted and part.quote_char == '"':
            # Double-quoted literal: the lexer already resolved the dquote
            # escapes; only the deferred \$ still needs stripping.
            if '\\' in text:
                text = self.process_dquote_escapes(text)
            builder.add(FieldRun(text, _PROTECTED, _NEVER, 'double'))
        else:
            # Unquoted literal.
            if ctx.assign_prefix is not None:
                text = self._assignment_value_chunk(word, part_index, part,
                                                    ctx, text)
            # Unquoted literal: tilde on first part if leading ~ and the tilde
            # word is wholly unquoted literal (bash) — see
            # _leading_tilde_expandable for the boundary rule.
            if (not ctx.has_expansion and not builder.has_content
                    and text.startswith('~')
                    and self._leading_tilde_expandable(
                        part.text,
                        parts_follow=part_index < len(word.parts) - 1)):
                text = self.manager.expand_tilde(text)
            builder.add_runs(self._unquoted_literal_runs(text))

    def _assignment_value_chunk(self, word: Word, part_index: int,
                                part: LiteralPart, ctx: _AssignCtx,
                                text: str) -> str:
        """Apply assignment value-tilde expansion to an unquoted literal chunk.

        Splits ``text`` into the ``NAME=`` prefix chars still owed and the
        value chunk after them; value-tildes expand after the first ``=`` and
        after each ``:``. Mutates ``ctx`` (prefix consumed, value length,
        previous char). Returns the (possibly tilde-expanded) text.
        """
        parts_follow = part_index < len(word.parts) - 1
        remaining = len(ctx.assign_prefix or '') - ctx.assign_seen
        if remaining > 0:
            take = min(remaining, len(text))
            ctx.assign_seen += take
            head, chunk = text[:take], text[take:]
            # A non-empty chunk directly follows the '='.
            trigger = bool(chunk)
        else:
            head, chunk = '', text
            # ':' always re-triggers; the assignment '=' only when no value
            # text has intervened.
            trigger = (ctx.prev_char == ':'
                       or (ctx.prev_char == '=' and ctx.value_len == 0))
        if chunk:
            expanded_chunk = self._expand_assignment_value_tildes(
                chunk, trigger, parts_follow)
            ctx.value_len += len(chunk)
            text = head + expanded_chunk
        ctx.prev_char = text[-1] if text else ctx.prev_char
        return text

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

    def _collapse_leading_tilde_extent(
            self, word: Word) -> Optional[List[WordPart]]:
        """Collapse a colon-bounded leading tilde extent spanning parts.

        bash's tilde WORD runs from a word-leading ``~`` to the first
        UNQUOTED ``/`` (or word end); a ``:`` inside it delimits the
        expandable prefix, and the remainder of the tilde word is taken
        VERBATIM — the parameter/command/arithmetic expansions in it do NOT
        run (``~:$X`` -> ``$HOME:$X`` with the ``$X`` intact; probed bash
        5.2). ``_walk_literal_part`` handles a tilde word confined to the
        leading literal part; this handles the remainder spilling into the
        following parts.

        Returns a new parts list — the expanded prefix and verbatim
        remainder collapsed into one pre-expanded unquoted ``LiteralPart``,
        followed by any parts past the tilde-word boundary — or ``None``
        when the special case does not apply (the normal walk then owns the
        word). Bails to ``None`` wherever bash would NOT tilde-expand: an
        unexpandable prefix, or a quote/backslash anywhere in the tilde
        word.
        """
        parts = word.parts
        if len(parts) < 2:
            # 0/1 parts: nothing spills; _walk_literal_part owns the tilde.
            return None
        first = parts[0]
        if (not isinstance(first, LiteralPart) or first.quoted
                or not first.text.startswith('~')):
            return None

        # The prefix must be ':'-bounded, with NO '/' anywhere in the leading
        # literal: a '/' bounds the tilde word within this literal, so the
        # remainder never spills into following parts (the single-part case,
        # owned by _walk_literal_part). A backslash is a quoted char that
        # disables tilde expansion entirely.
        lead = first.text
        colon = -1
        for i in range(1, len(lead)):
            ch = lead[i]
            if ch == '\\' or ch == '/':
                return None
            if ch == ':' and colon == -1:
                colon = i
        if colon == -1:
            return None  # prefix runs into following parts with no ':' bound

        # The prefix must actually expand; an unknown user or out-of-range
        # dirstack index leaves the word literal in bash (and the rest then
        # expands normally, which the ordinary walk already does).
        expanded_lead = self.manager.expand_tilde(lead)
        if expanded_lead == lead:
            return None

        # Consume following parts as verbatim source until the first
        # unquoted '/' in a literal part (the tilde-word boundary). Any
        # quoted part or backslash disables tilde -> bail to the normal walk.
        verbatim: List[str] = []
        resume: List[WordPart] = []
        for idx in range(1, len(parts)):
            part = parts[idx]
            if getattr(part, 'quoted', False):
                return None
            if isinstance(part, ExpansionPart):
                # str(part) is psh's canonical pre-expansion source rendering
                # (the same one display_text/SimpleCommand.args use).
                verbatim.append(str(part))
                continue
            if isinstance(part, LiteralPart):
                text = part.text
                slash = -1
                for j, ch in enumerate(text):
                    if ch == '\\':
                        return None
                    if ch == '/':
                        slash = j
                        break
                if slash == -1:
                    verbatim.append(text)
                    continue
                verbatim.append(text[:slash])
                resume = [LiteralPart(text[slash:], quoted=False)]
                resume.extend(parts[idx + 1:])
                break
            return None  # unknown WordPart kind: stay conservative

        collapsed = LiteralPart(expanded_lead + ''.join(verbatim),
                                quoted=False)
        return [collapsed] + resume

    def _walk_expansion_part(self, part: ExpansionPart, ctx: _AssignCtx,
                             builder: _FieldBuilder,
                             policy: WordExpansionPolicy) -> None:
        """Walk one ExpansionPart: append its run(s), or splice its fields."""
        ctx.has_expansion = True
        if ctx.assign_prefix is not None:
            # Expansion results never trigger value-tilde expansion (the
            # check is syntactic, on the pre-expansion word).
            ctx.prev_char = ''
            ctx.value_len += 1

        # Process substitution (<(cmd) / >(cmd)) — whole-word or embedded.
        # The /dev/fd/N path is spliced in unquoted-but-unsplittable: it is not
        # a parameter/command/arithmetic expansion, so it never field-splits or
        # globs (and it never carries a glob metacharacter anyway).
        if isinstance(part.expansion, ProcessSubstitution):
            path = self.shell.io_manager.create_process_substitution_for_expansion(
                part.expansion.direction, part.expansion.source)
            builder.add(FieldRun(path, _ACTIVE, _NEVER, 'procsub'))
            return

        # Field-producing expansion ("$@", "${a[@]}", "${@:2}", "${a[@]@Q}", …)
        # — quoted or unquoted. Route ALL of them through the same splice
        # algebra (no $@ shortcut). A quoted field is protected/unsplittable;
        # an unquoted field is active/split-eligible (each field further
        # IFS-splits). In no-split contexts bash joins the fields with a single
        # space instead of producing boundaries.
        fields = self._field_expansion_fields(part)
        if fields is not None:
            expanded = self._fields_to_expanded(fields, quoted=part.quoted)
            if policy.split:
                builder.splice(expanded)
            elif expanded:
                # No-split: join field texts with a single space (bash), one
                # protected run. Empty $@ contributes nothing.
                builder.add(FieldRun(' '.join(f.text for f in expanded),
                                     _PROTECTED, _NEVER, 'field-join'))
            return

        # Ordinary single-field expansion.
        result = self.manager.expand_expansion(
            part.expansion, quote_ctx=DQ_WORD if part.quoted else None)
        if part.quoted:
            builder.add(FieldRun(result, _PROTECTED, _NEVER, 'expansion'))
            return
        segs = getattr(result, 'segments', None)
        if segs is not None:
            # A value-operand result (${x:-word}): quoted/escaped regions of
            # the operand are protected from splitting and globbing; unquoted
            # regions stay active/split-eligible (bash: ${x:-'a b'} one field).
            runs = self._operand_runs(segs)
            if runs:
                builder.add_runs(runs)
            else:
                # Empty operand: keep the zero-field rule (an expansion that
                # vanishes contributes no surviving field on its own).
                builder.add(FieldRun('', _ACTIVE, _ELIGIBLE, 'operand'))
            return
        # Plain unquoted expansion: its text is the only split-eligible text,
        # and glob chars in it are active.
        builder.add(FieldRun(str(result), _ACTIVE, _ELIGIBLE, 'expansion'))

    def _fields_to_expanded(self, fields: List, quoted: bool
                            ) -> List[ExpandedField]:
        """Map ``$@``/``[@]`` field strings to :class:`ExpandedField`s.

        A quoted field is one PROTECTED, NEVER run. An unquoted field is
        ACTIVE and IFS_ELIGIBLE (each field further splits), unless it carries
        operand ``.segments`` (a triggered ``${a[@]:-'a b'}`` default), whose
        protected regions stay protected.
        """
        out: List[ExpandedField] = []
        for f in fields:
            segs = getattr(f, 'segments', None)
            if segs is not None and not quoted:
                out.append(ExpandedField(self._operand_runs(segs)))
            elif quoted:
                out.append(ExpandedField(
                    [FieldRun(str(f), _PROTECTED, _NEVER, 'field')]))
            else:
                out.append(ExpandedField(
                    [FieldRun(str(f), _ACTIVE, _ELIGIBLE, 'field')]))
        return out

    @staticmethod
    def _operand_runs(segs: Tuple[Tuple[str, bool], ...]) -> List[FieldRun]:
        """Map OperandResult (text, protected) pairs to :class:`FieldRun`s.

        Protected regions (quoted/escaped operand text) become PROTECTED,
        NEVER runs; unprotected regions stay ACTIVE, IFS_ELIGIBLE like any
        unquoted expansion result.
        """
        return [
            FieldRun(text, _PROTECTED, _NEVER, 'operand') if protected
            else FieldRun(text, _ACTIVE, _ELIGIBLE, 'operand')
            for text, protected in segs
        ]

    # ------------------------------------------------------------------
    # Field splitting (pass 2): per committed field, split IFS_ELIGIBLE runs
    # ------------------------------------------------------------------

    def _field_split(self,
                     raw_fields: List[ExpandedField]) -> List[ExpandedField]:
        """Split every committed field on IFS, preserving run protection.

        Each committed field (a ``$@`` boundary) is split independently; an
        all-eligible field that splits to nothing elides (zero surviving
        fields), which is how ``$unset`` alone contributes no argument.
        """
        ifs = self.state.get_variable('IFS', ' \t\n')
        out: List[ExpandedField] = []
        for field in raw_fields:
            out.extend(self._split_one_field(field.runs, ifs))
        return out

    def _split_one_field(self, runs: List[FieldRun],
                         ifs: str) -> List[ExpandedField]:
        """IFS-split one field's runs, edge-joining NEVER runs.

        Only ``IFS_ELIGIBLE`` runs (unquoted expansion text) produce field
        boundaries; ``NEVER`` runs merge with the neighbouring field. Uses
        :meth:`WordSplitter.split_with_edges` so a leading/trailing IFS run is
        reported and the join is correct (``a"$x"b``). Split pieces inherit the
        original run's protection so pathname generation still sees it.
        """
        fields: List[ExpandedField] = []
        current: Optional[ExpandedField] = None  # None = no field currently open
        for run in runs:
            if run.split is _NEVER:
                if current is None:
                    current = ExpandedField([])
                current.runs.append(run)
                continue
            text = run.text
            pieces, leading, trailing = \
                self.manager.word_splitter.split_with_edges(text, ifs)
            if leading and current is not None:
                fields.append(current)
                current = None
                # A leading non-whitespace delimiter both closed the open field
                # and produced an empty first piece — same boundary, drop the
                # duplicate (pre$x with x=':a' is [pre, a]).
                if pieces and pieces[0] == '' and text[0] not in ' \t\n':
                    pieces = pieces[1:]
            for k, piece in enumerate(pieces):
                piece_run = FieldRun(piece, run.protection, _NEVER, run.origin)
                if k == 0 and current is not None:
                    current.runs.append(piece_run)
                else:
                    if current is not None:
                        fields.append(current)
                    current = ExpandedField([piece_run])
            if trailing and current is not None:
                fields.append(current)
                current = None
        if current is not None:
            fields.append(current)
        return fields

    # ------------------------------------------------------------------
    # Materialization (terminal boundary): ExpandedWord -> argv strings
    # ------------------------------------------------------------------

    def materialize(self, expanded: ExpandedWord,
                    policy: WordExpansionPolicy) -> List[str]:
        """Turn an :class:`ExpandedWord` into ``argv`` fields (the SOLE place
        that converts the field IR back to strings).

        Each field is pathname-expanded when the policy permits it, noglob is
        off, and an ACTIVE run carries a glob/extglob metacharacter — the
        pattern is compiled from the runs so a PROTECTED metacharacter cannot
        act (H6). Otherwise the field's runs are joined (quote removal already
        happened per run). An empty ``fields`` list means word elision.
        """
        globbing = policy.glob and not self.state.options.get('noglob', False)
        extglob_on = self.state.options.get('extglob', False)
        result: List[str] = []
        for field in expanded.fields:
            if globbing and self._field_glob_eligible(field, extglob_on):
                result.extend(self._glob_field(field))
            else:
                result.append(field.text)
        return result

    @staticmethod
    def _field_glob_eligible(field: ExpandedField, extglob_on: bool) -> bool:
        """True when an ACTIVE run of *field* carries a live glob metacharacter.

        Only ACTIVE runs can introduce an active metacharacter; a PROTECTED
        run's metacharacters are bracket-escaped in the pattern and never act.
        Extglob detection scans the concatenated ACTIVE text so an operator and
        its group in adjacent active runs are seen together.
        """
        active_text = ''.join(
            r.text for r in field.runs if r.protection is _ACTIVE)
        if has_glob_metacharacters(active_text):
            return True
        if extglob_on and active_text:
            from .extglob import contains_extglob
            return contains_extglob(active_text)
        return False

    def _glob_field(self, field: ExpandedField) -> List[str]:
        """Pathname-expand one glob-eligible field, honoring protection.

        The pattern is compiled from the runs (PROTECTED metacharacters
        bracket-escaped); on a match its results are returned, on no match the
        field's LITERAL text (not the bracketed pattern) is the fallback, under
        nullglob/failglob rules — matching bash's word-level behavior.
        """
        pattern = self._pattern_from_runs(field.runs)
        matches = self.manager.glob_expander.expand(pattern)
        if matches and matches != [pattern]:
            # glob_expander already returns sorted results.
            return matches
        literal = field.text
        if self.state.options.get('failglob', False):
            # failglob: a no-match glob DISCARDS the rest of the current line
            # and resumes at the next one (bash 5.2), in every consumer of glob
            # expansion. Under set -e a non-interactive shell EXITS instead.
            print(f"{self.state.error_location_prefix()}no match: {literal}",
                  file=self.state.stderr)
            if (self.state.options.get('errexit')
                    and self.state.is_script_mode):
                raise SystemExit(1)
            raise TopLevelAbort(1)
        if self.state.options.get('nullglob', False):
            return []  # nullglob: no matches -> nothing
        return [literal]

    def _pattern_from_runs(self, runs: List[FieldRun]) -> str:
        """Compile a pathname pattern from a field's runs.

        ACTIVE run text passes through raw (its metacharacters act); PROTECTED
        run text is bracket-escaped so its metacharacters are literal in the
        same pattern (``"*"*`` -> ``[*]*`` matches names beginning with a
        literal ``*``).
        """
        return ''.join(
            run.text if run.protection is _ACTIVE
            else self._pathname_escape(run.text)
            for run in runs)

    @staticmethod
    def _pathname_escape(text: str) -> str:
        """Neutralise every glob/extglob metacharacter in a PROTECTED run.

        Uses single-character brackets (``[*]``, ``[?]``, ``[[]``, ``[(]``) and
        ``[]]`` for ``]`` — the pathname engine treats backslash as a literal
        character, so bracket-escaping is the portable way to a literal
        metacharacter.
        """
        out: List[str] = []
        for c in text:
            if c == ']':
                out.append('[]]')
            elif c in _PATHNAME_ESCAPE:
                out.append('[' + c + ']')
            else:
                out.append(c)
        return ''.join(out)

    def _unquoted_literal_runs(self, text: str) -> List[FieldRun]:
        """Escape-process unquoted literal text into protection runs.

        A backslash escape protects the following character (``\\*`` keeps the
        ``*`` literal); an unescaped glob metacharacter stays ACTIVE. Runs are
        homogeneous by protection, so ``a\\*b*`` yields ACTIVE ``a``, PROTECTED
        ``*``, ACTIVE ``b*`` — the per-character protection #20 H6 needs. All
        runs are NEVER-split (literal text never IFS-splits).
        """
        if '\\' not in text:
            # Fast path: no escapes -> one ACTIVE run (metacharacters, if any,
            # act; a plain word with no metacharacter never globs anyway).
            return [FieldRun(text, _ACTIVE, _NEVER, 'literal')]
        runs: List[FieldRun] = []
        buf: List[str] = []
        buf_prot: Optional[Protection] = None

        def flush() -> None:
            nonlocal buf, buf_prot
            if buf:
                runs.append(FieldRun(''.join(buf), buf_prot or _ACTIVE,
                                     _NEVER, 'literal'))
                buf = []
                buf_prot = None

        i, n = 0, len(text)
        while i < n:
            if text[i] == '\\' and i + 1 < n:
                # Every word-level escape strips the backslash and protects
                # the escaped character (\$ \\ \` \" \' \~ \<space> \<newline>,
                # an escaped glob metacharacter, or any other \<char>).
                ch, prot = text[i + 1], _PROTECTED
                i += 2
            else:
                ch, prot = text[i], _ACTIVE
                i += 1
            if buf and buf_prot is not prot:
                flush()
            buf.append(ch)
            buf_prot = prot
        flush()
        return runs

    # ------------------------------------------------------------------
    # The scalar assignment-value walker (kept SEPARATE — see module
    # docstring: it never fields/globs and its tilde trigger differs).
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
                    # ExpansionParts); strip only the lexer-deferred \$
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
                        part.expansion.direction, part.expansion.source)
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
    # Field-expansion helper ("$@", "${a[@]}" field detection)
    # ------------------------------------------------------------------

    def _field_expansion_fields(self,
                                part: ExpansionPart) -> Optional[List[str]]:
        """Fields if this ExpansionPart is field-producing.

        Returns the list of fields for ``$@``, ``${a[@]}``, ``${@:2}``,
        ``${a[@]:1:2}``, ``${a[@]@Q}`` etc., or None when the expansion has
        scalar semantics (everything else, including ``$*``/``${a[*]}``).
        """
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

    # ------------------------------------------------------------------
    # Word-level escape processors (deliberately NOT in utils/escapes.py:
    # its dialect map excludes quote-context word escapes).
    # ------------------------------------------------------------------

    @staticmethod
    def process_dquote_escapes(text: str) -> str:
        """Strip the ONE deferred ``\\$`` escape in already-lexed double-quoted
        literal text.

        The lexer FULLY resolves double-quote escapes into the STRING part value
        already — ``\\\\`` -> ``\\``, ``\\"`` -> ``"``, ``\\``` -> `` ` ``,
        ``\\<newline>`` dropped — EXCEPT ``\\$``, which it keeps verbatim so the
        ``$`` is not mistaken for an expansion start (expansions are separate
        ExpansionParts). This second pass removes only that backslash
        (``\\$`` -> ``$``). Every other backslash is already final and MUST be
        left untouched: re-applying the ``\\\\`` -> ``\\`` rule would collapse a
        run of backslashes a SECOND time (``"a\\\\\\b"`` lexes to ``a\\\\b`` and
        a re-collapse would wrongly yield ``a\\b``; bash keeps ``a\\\\b``).
        """
        if '\\$' not in text:
            return text
        result = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
                result.append('$')
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
        the result should NOT trigger globbing). Used by the scalar
        assignment-value walker (the field engine builds protection runs
        directly via :meth:`_unquoted_literal_runs`).
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
