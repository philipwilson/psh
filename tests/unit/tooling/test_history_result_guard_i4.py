"""Drift-lock guard for the typed history-expansion boundary (campaign I4).

The triad's guard: (b) `expand_history` is the sole history-expansion producer
and returns a typed `HistoryExpansionResult`; consumers branch on `result.kind`
rather than re-deriving the outcome from the old `contains_history_reference`
regex or from `expanded_text != original_text`. A synthetic offender resurrecting
either inference is RUN here and must be detected.
"""

import io
import re
import tokenize
from pathlib import Path

from psh.interactive.history_result import HistoryExpansionResult
from psh.shell import Shell

_PSH = Path(__file__).resolve().parents[3] / "psh"
_SOURCE_PROCESSOR = _PSH / "scripting" / "source_processor.py"
_ACCUMULATOR = _PSH / "scripting" / "command_accumulator.py"
_EXPANSION = _PSH / "interactive" / "history_expansion.py"
_CONSUMERS = (_SOURCE_PROCESSOR, _ACCUMULATOR)


def _code_only(source: str) -> str:
    """*source* with comments and string literals stripped (comment/string
    immunity — the detector must inspect CODE, not the prose that describes it,
    so this guard's own explanatory comments never trip it)."""
    tokens = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING,
                            tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            tokens.append(tok.string)
    except tokenize.TokenError:
        return source  # partial/synthetic snippet: fall back to raw text
    return " ".join(tokens)


def _infers_outcome_by_regex_or_stringcompare(source: str) -> bool:
    """The guard's detector: does *source* re-derive the history-expansion
    outcome instead of consuming the typed result?

    Fires on the retired regex predicate OR an `expanded... != ...original`
    string comparison used to decide 'did expansion happen'. Comment/string
    immune (via :func:`_code_only`)."""
    code = _code_only(source)
    if "contains_history_reference" in code or "HISTORY_REFERENCE_RE" in code:
        return True
    # An `expanded_text != original_text`-style inference (the H-finding).
    if re.search(r"expand\w*\s*!=\s*\w*(command|original|raw|text)", code):
        return True
    return False


def test_producer_returns_typed_result():
    sh = Shell(norc=True)
    sh.state.options["histexpand"] = True
    sh.state.history[:] = ["echo hi"]
    result = sh.history_expander.expand_history("!!")
    assert isinstance(result, HistoryExpansionResult)


def test_retired_regex_predicate_is_gone():
    import psh.interactive.history_expansion as he
    assert not hasattr(he, "contains_history_reference")
    assert not hasattr(he, "HISTORY_REFERENCE_RE")


def test_consumers_do_not_reinfer_the_outcome():
    for path in _CONSUMERS:
        source = path.read_text()
        assert not _infers_outcome_by_regex_or_stringcompare(source), (
            f"{path.name} re-derives the history-expansion outcome instead of "
            f"consuming the typed HistoryExpansionResult")


def test_consumers_consume_the_typed_result_kind():
    # Both consumers reference the typed result's kind-authority surface.
    src = _SOURCE_PROCESSOR.read_text()
    assert "result.is_error" in src and "result.is_print_only" in src
    acc = _ACCUMULATOR.read_text()
    assert "_last_history_result" in acc and ".is_error" in acc


def test_synthetic_regex_offender_is_detected():
    # A consumer resurrecting the regex predicate MUST be flagged.
    offender = (
        "if not contains_history_reference(command_string):\n"
        "    self.shell.add_history(command_string)\n"
    )
    assert _infers_outcome_by_regex_or_stringcompare(offender)


def test_synthetic_stringcompare_offender_is_detected():
    # A consumer inferring 'did it expand' from string identity MUST be flagged.
    offender = "if expanded_text != original_text:\n    record(expanded_text)\n"
    assert _infers_outcome_by_regex_or_stringcompare(offender)


def test_clean_consumer_snippet_is_not_flagged():
    # A consumer that branches on the typed kind is NOT flagged (no false positive).
    clean = (
        "result = expander.expand_history(cmd)\n"
        "if result.is_error:\n    return None\n"
        "record_text = result.recordable_text\n"
    )
    assert not _infers_outcome_by_regex_or_stringcompare(clean)


def test_expand_history_is_the_only_public_expansion_entry():
    # The producer file exposes exactly one public expansion method; no second
    # module reimplements the !!/!n scanner (grep for a rival event resolver).
    import psh.interactive.history_expansion as he
    publics = [n for n in dir(he.HistoryExpander)
               if n.startswith("expand") and not n.startswith("_")]
    assert publics == ["expand_history"]
