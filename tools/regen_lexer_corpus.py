#!/usr/bin/env python3
"""Mechanical re-freeze of the lexer stream corpus for Phase D (WordToken).

The lexer now composites a maximal run of adjacent word-like tokens into ONE
``WORD`` token carrying the run's parts (``psh.lexer.word_fusion.fuse_words``).
This tool re-freezes ``tests/unit/lexer/lexer_stream_corpus.json`` by applying
that adjacency-collapse as a MECHANICAL TRANSFORM of the OLD frozen table — NOT
by re-running the new lexer blind (the freeze policy forbids blind regen). A
reviewer can diff old→new and confirm every changed row is purely a run being
merged into a WORD-with-parts.

The GROUPING (which tokens fuse, arithmetic-interior suppression) is
re-implemented here independently from the encoded token rows, so it is a true
spec: the corpus test then runs the NEW lexer and must byte-match this output.
A disagreement is a real boundary move (needs bash proof) or a fusion bug — it
is NEVER papered over by hand-editing a row or tweaking this generator to match
the lexer.

The per-part CONTENT is produced by reconstructing each sub-token and calling
the lexer's ``sub_token_to_parts`` (the single definition of what a word part
is), so the transform stays transparent rather than duplicating that logic; the
part→AST equivalence is pinned separately (test_word_fusion_helpers.py) and by
the base-vs-branch execution differential.

Usage:
    python tools/regen_lexer_corpus.py            # rewrite the JSON in place
    python tools/regen_lexer_corpus.py --verify   # diff transform vs new lexer,
                                                   # report disagreements, no write
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from psh.lexer.token_parts import TokenPart  # noqa: E402
from psh.lexer.token_types import Token, TokenType  # noqa: E402
from psh.lexer.word_fusion import WORD_LIKE_TYPES, sub_token_to_parts  # noqa: E402

CORPUS = REPO / 'tests' / 'unit' / 'lexer' / 'lexer_stream_corpus.json'

# Word-like type NAMES (the encoded rows carry type.name strings). Kept in
# lock-step with the lexer's WORD_LIKE_TYPES via the assertion below.
_WORD_LIKE_NAMES = frozenset(t.name for t in WORD_LIKE_TYPES)


def _decode_part(enc):
    """Encoded part list -> a TokenPart (only the encoded fields matter)."""
    value, quote_type, is_variable, is_expansion, expansion_type, error = enc
    return TokenPart(value=value, quote_type=quote_type, is_variable=is_variable,
                     is_expansion=is_expansion, expansion_type=expansion_type,
                     error_message=error)


def _decode_token(enc):
    """Reconstruct the minimal Token that sub_token_to_parts needs."""
    parts = [_decode_part(p) for p in enc[9]] if len(enc) > 9 else []
    return Token(type=TokenType[enc[0]], value=enc[1], position=enc[2],
                 end_position=enc[3], quote_type=enc[4],
                 adjacent_to_previous=enc[5], is_keyword=enc[6],
                 parts=parts, fd=enc[7], combined_redirect=enc[8])


def _encode_part(part):
    return [part.value, part.quote_type, part.is_variable, part.is_expansion,
            part.expansion_type, part.error_message]


def fuse_encoded(tokens, source):
    """Adjacency-collapse a list of ENCODED tokens (mechanical transform).

    Mirrors word_fusion.fuse_words on the encoded rows: maximal runs of
    adjacent word-like tokens (length >= 2) become one WORD encoding; fusion is
    suppressed inside ``(( ))`` / C-style-for headers (DOUBLE_LPAREN depth).
    """
    result = []
    i = 0
    n = len(tokens)
    arith_depth = 0
    while i < n:
        tok = tokens[i]
        name = tok[0]
        if name == 'DOUBLE_LPAREN':
            arith_depth += 1
            result.append(tok)
            i += 1
            continue
        if name == 'DOUBLE_RPAREN':
            arith_depth = max(0, arith_depth - 1)
            result.append(tok)
            i += 1
            continue
        if arith_depth == 0 and name in _WORD_LIKE_NAMES:
            j = i + 1
            while j < n and tokens[j][0] in _WORD_LIKE_NAMES and tokens[j][5]:
                j += 1
            if j - i >= 2:
                run = tokens[i:j]
                start, end = run[0][2], run[-1][3]
                parts = []
                for enc in run:
                    parts.extend(sub_token_to_parts(_decode_token(enc)))
                result.append([
                    'WORD', source[start:end], start, end, None,
                    run[0][5], False, None, False,
                    [_encode_part(p) for p in parts],
                ])
                i = j
                continue
        result.append(tok)
        i += 1
    return result


def transform_stream(stream, source):
    """Fuse a snapshot stream: a token list, or an EXC row, or a heredoc pair."""
    if not stream or stream[0] == 'EXC':
        return stream
    # Heredoc form: [[tokens], sorted(heredoc_map.items())].
    if (len(stream) == 2 and isinstance(stream[0], list) and stream[0]
            and isinstance(stream[0][0], list)):
        return [fuse_encoded(stream[0], source), stream[1]]
    return fuse_encoded(stream, source)


def transform(old):
    new = {}
    for source, entry in old.items():
        row = {}
        for key in ('t', 'x', 'h'):
            if key in entry:
                row[key] = transform_stream(entry[key], source)
        # An 'x' variant that collapses to equal 't' loses its reason to exist.
        if 'x' in row and row['x'] == row['t']:
            del row['x']
        new[source] = row
    return json.loads(json.dumps(new, ensure_ascii=False))  # canonicalize tuples


def main():
    verify = '--verify' in sys.argv[1:]
    old = json.loads(CORPUS.read_text())
    new = transform(old)

    if verify:
        # Cross-check: the NEW lexer's snapshot must byte-match this transform.
        sys.path.insert(0, str(REPO / 'tests' / 'unit' / 'lexer'))
        import test_lexer_stream_corpus as corpus_mod
        build_corpus = corpus_mod.build_corpus
        snapshot_input = corpus_mod.snapshot_input
        disagreements = []
        for text in build_corpus():
            got = snapshot_input(text)
            want = new.get(text)
            if got != want:
                disagreements.append(text)
        if disagreements:
            print(f"DISAGREEMENT on {len(disagreements)} rows "
                  f"(new lexer != mechanical transform) — STOP AND REPORT:")
            for text in disagreements[:40]:
                print(f"  input {text!r}")
                print(f"    transform: {json.dumps(new.get(text))[:200]}")
                print(f"    lexer:     {json.dumps(snapshot_input(text))[:200]}")
            return 1
        changed = sum(1 for k in old if old[k] != new[k])
        print(f"OK: new lexer matches the mechanical transform on all "
              f"{len(new)} rows ({changed} rows changed by fusion).")
        return 0

    CORPUS.write_text(json.dumps(new, ensure_ascii=False, indent=0) + '\n')
    changed = sum(1 for k in old if old[k] != new[k])
    print(f"Re-froze {CORPUS} — {changed}/{len(new)} rows changed by fusion.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
