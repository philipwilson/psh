"""Frozen token-stream corpus for the lexer (Textbook B6).

``lexer_stream_corpus.json`` freezes the complete token stream — types,
values, positions, quote types, adjacency, fd, parts metadata, and
exceptions — for a systematic battery over the word-shape classes the
B6 refactor touched: assignment prefixes (``a[k]=v``, ``a[k]+=v`` over a
matrix of subscripts and values), inline ANSI-C (``v=$'x'``,
``pre$'x'post``), glob bracket classes, extglob groups, operator-debris
fallback words (``]``, ``+=``, ``=c``, case patterns), and the
adversarial escape/quote/boundary corners where the lexer-level
assignment map and the recognizer's local subscript scan disagree by
design.

Provenance: the table was generated from the PRE-refactor lexer (v0.320.0)
at the moment ``LiteralRecognizer``'s four retro-scanning heuristics were
replaced by the forward WordShape state and the ``word_scanners.py``
mini-scanners; a 15k-input characterization harness (this battery plus
every string literal in tests/ and the golden cases) verified the
refactor produced ZERO stream changes. Several frozen streams pin
behavior that intentionally differs from bash at the TOKEN level and is
reconciled later in the pipeline (the parser re-joins adjacent tokens:
``a=b=c`` lexes as WORD ``a=b`` + WORD ``=c``; ``vars+=`` as WORD ``vars``
+ WORD ``+=``) — see ``OperatorDebrisWordRecognizer``.

If the lexer's behavior deliberately changes, re-verify the affected rows
against bash and update those entries (never regenerate the whole table
blindly from the lexer under test).
"""

import json
from pathlib import Path

import pytest

from psh.lexer import tokenize, tokenize_with_heredocs

CORPUS_PATH = Path(__file__).parent / 'lexer_stream_corpus.json'


def build_corpus():
    """The deterministic input battery (must not depend on the lexer)."""
    out = []

    # --- memo anchors, verbatim ---
    out += [
        "a=b=c$'x'", 'x[a"b"]=v', "pre$'x'post", 'a[$(echo 1)]=y',
        'echo ]', 'echo +x', 'a]b', 'echo *[[:upper:]]*',
    ]

    names = ['a', 'arr']
    subscripts = ['0', 'key', '"k"', "'k'", '$v', '${v}', '$(echo 1)',
                  '$(echo 1 + 1)', '`echo 2`', 'a"b"', "a'b'c", 'x+1',
                  '@', '*', 'i][j', '$((1+2))']
    values = ['v', '$x', '"q v"', "'s'", "$'x\\ny'", 'a$x', 'v$(echo c)',
              '', '(1 2 3)', '("a" "b")', 'a]b', 'a[b]']

    # Assignment shapes: NAME[sub]=value / NAME[sub]+=value
    for n in names:
        for s in subscripts:
            for op in ('=', '+='):
                for v in values:
                    out.append(f'{n}[{s}]{op}{v}')
    # Scalar assignments with tricky values
    for v in values + ["a=$'x'", "b$'q'c", "$'n'"]:
        out.append(f'v={v}')
        out.append(f'v+={v}')
    # Inline ANSI-C in concatenation / values
    out += ["pre$'a'post", "p$'a'$'b'q", "x=$'a'b$'c'", "echo pre$'x'post",
            "a=b=c$'x'd", "PATH=/x:$'y'", "./rel$'t'", "~/p$'q'",
            "v$'a'=x", "v=$'='y", "v$'+'=x", "v$'\\n'=x", "x=$'a'$'b'",
            "p$'q'[0]=v"]
    # Non-assignment bracket words (glob classes, test commands)
    for b in ['x[ab]', 'x[a-z]*', '*[[:upper:]]*', 'x[!a]', 'x[^b]y',
              'x["ok"]', "x['ok']", 'x[$v]', 'x[$(echo 1)]', 'x[`echo q`]',
              'x[a b]', 'x[', 'x[]', '[ab]', '][', 'a[b][c]=d']:
        out.append(f'echo {b}')
        out.append(b)
    # Operator-debris fallback words (census classes, bash-verified)
    for c in [']', '+', '=', '[', '}', '{', '!', '+x', '=x', ']x',
              'a+b', 'a=b', '+=', ']]', '[[']:
        out.append(f'echo {c}')
        out.append(c)
    out += ['vars+=("$k=$v")', 'a=([1]=x [3]=y z)', 'declare -A h=([a]=1)',
            '[ "$1" = "yes" ]', 'set +x', 'a=b=c', 'v=a=b', 'echo a=b=c',
            'case $x in [0-9]*) echo d;; [a-z]) :;; esac']
    # Extglob shapes (frozen under extglob-enabled config too)
    for e in ['?(a|b)', '+(x)', '!(y)', '@(p|q)', '*(z)', 'a@(b|c(d))e',
              'f+(a|@(b|c))g', '+(', '+()', 'x!(y)z', 'ls *.@(jpg|png)',
              '?(a|b)*(c)+(d)']:
        out.append(f'echo {e}')
        out.append(e)
    # Adversarial corners: escape/quote/boundary asymmetries between the
    # lexer-level assignment map and the recognizer's local subscript scan.
    out += [
        'a[x\\]=v', 'a[\\]]=v', 'a[\\[x]=v', 'a[x\\]]=v', 'a[$(x])]=v',
        '"q"a[0]=v', '"q"a["k"]=v', '${v}a[0]=v', "a[i;'q'j]=v",
        'a[i;j]=v', 'a[i|j]=v', 'a[i&j]=v', 'a[i(j]=v', 'a[\\]=v',
        'v=a[0]=b', 'a[x=1]=v', 'a[i]j=k', ']a=b', ']=x',
        'a[i][j]=v', 'a[i][j]+=v', 'a[0]$x=y',
    ]
    # Context interactions: arithmetic, [[ ]], case, braces, heredocs
    out += [
        '(( a[0]+=1 ))', '(( a["x"] ))', '(( a+=1 ))', "(( a[$'q'] ))",
        '(( x < 3 ))', '[[ a < b ]]', '[[ -f /x ]]',
        'case x in a) echo 1;; esac',
        'echo $(case y in y) echo hi;; esac)',
        'echo {a,b}', 'echo {1..3}', 'echo a{b,c}d',
        'echo $((1 + 2))', 'a[$((1+1))]=v',
        'cat <<EOF\nbody $x\nEOF', "cat <<'EOF'\nliteral $x\nEOF",
        'cat <<-EOF\n\tbody\n\tEOF',
        'echo $"hello"', 'pre$"mid"post', 'echo $', 'echo $%x',
        'echo a$', 'echo $1x', 'x=$', 'a[$]=v',
    ]
    # Dedup, preserving order
    seen = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def _encode_part(part):
    return [part.value, part.quote_type, part.is_variable, part.is_expansion,
            part.expansion_type, part.error_message]


def _encode_token(tok):
    enc = [tok.type.name, tok.value, tok.position, tok.end_position,
           tok.quote_type, tok.adjacent_to_previous, tok.is_keyword,
           tok.fd, tok.combined_redirect]
    if tok.parts:
        enc.append([_encode_part(p) for p in tok.parts])
    return enc


def _snap(fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — exceptions are part of the contract
        return ['EXC', type(e).__name__, str(e)]
    if isinstance(result, tuple):  # tokenize_with_heredocs
        tokens, heredoc_map = result
        return [[_encode_token(t) for t in tokens],
                sorted(heredoc_map.items())]
    return [_encode_token(t) for t in result]


def snapshot_input(text):
    """Token streams for one input, across the lexer's entry points."""
    entry = {'t': _snap(tokenize, text)}
    ext = _snap(tokenize, text, shell_options={'extglob': True})
    if ext != entry['t']:
        entry['x'] = ext
    if '<<' in text:
        entry['h'] = _snap(tokenize_with_heredocs, text)
    # Canonicalize via JSON round-trip (tuples → lists).
    return json.loads(json.dumps(entry, ensure_ascii=False))


@pytest.fixture(scope='module')
def frozen():
    return json.loads(CORPUS_PATH.read_text())


def test_corpus_size(frozen):
    """The battery had 900+ inputs; shrinkage means a generator bug."""
    corpus = build_corpus()
    assert len(corpus) >= 900
    assert set(corpus) == set(frozen)


def test_frozen_streams(frozen):
    """Every corpus input tokenizes to its frozen stream."""
    mismatches = []
    for text in build_corpus():
        got = snapshot_input(text)
        if got != frozen[text]:
            mismatches.append(
                f"  input {text!r}:\n"
                f"    frozen: {json.dumps(frozen[text])[:300]}\n"
                f"    got:    {json.dumps(got)[:300]}")
    assert not mismatches, (
        f"{len(mismatches)} corpus inputs changed token streams "
        f"(re-verify against bash before updating the table):\n"
        + "\n".join(mismatches))
