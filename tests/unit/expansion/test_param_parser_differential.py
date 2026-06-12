"""Differential pin for THE parameter-expansion parser (Textbook B5).

param_parser_corpus.json freezes the (parameter, operator, word) triple for
every distinct ``${...}`` content harvested from the test corpus (all of
tests/, the conformance fixtures, golden_cases.yaml — 737 entries), plus
the probe-anchor battery from the migration brief.

Provenance: the table was generated at the moment the four legacy parser
copies (WordBuilder's operator scan, ParameterExpansion.parse_expansion,
expand_variable's pre-dispatch ladder, fields._parse_trailing_op) were
unified into psh/expansion/param_parser.py. A differential harness ran
every entry through both the old parsers and the new one: 719/737 were
identical or equivalent under three documented representational mappings
(word None == '', the legacy invented case-mod '?' default == '', and the
legacy trailing-'/' on substitutions without a replacement). The remaining
18 were divergences BETWEEN the old copies; each was adjudicated against
bash 5.2 probes and frozen with the bash-matching reading:

  F1 ':-'/':='/':?'/':+' after [@]/[*] are conditional operators, not a
     slice with a signed offset (bash: unset a => ${a[@]:-def} is 'def')
  F2 non-colon '-'/'='/'+'/'?' after a closed ']' are operators
     (bash: ${arr[0]-d} is the element)
  F3 the scan is earliest-position-first, so ${v:-x@Q} is ':-' with the
     literal operand 'x@Q', not an '@Q' transform of 'v:-x'
  F4 ${#rest} is a length form only when rest is a whole parameter spec
     (${#-} is the length of $-; ${#-d} is $# with default 'd')
  F5 ${!arr[idx]} (non-@/*) is element indirection (a=(HOME); ${!a[0]}
     is the value of $HOME)

This test pins the new parser against that frozen table — NOT against the
deleted legacy code. If the grammar deliberately changes, re-verify the
affected rows against bash and update the table entry (never regenerate
the whole table blindly from the parser under test).
"""

import json
from pathlib import Path

from psh.expansion.param_parser import parse_parameter_expansion

_CORPUS = json.loads(
    (Path(__file__).parent / 'param_parser_corpus.json').read_text())


def test_corpus_size():
    """The harvest had 737 distinct contents; shrinkage means a load bug."""
    assert len(_CORPUS) >= 737


def test_frozen_triples():
    """Every corpus row parses to its frozen (parameter, operator, word)."""
    mismatches = []
    for content in sorted(_CORPUS):
        expected = tuple(_CORPUS[content])
        node = parse_parameter_expansion(content)
        got = (node.parameter, node.operator, node.word)
        if got != expected:
            mismatches.append(f"  ${{{content}}}: expected {expected}, "
                              f"got {got}")
    assert not mismatches, (
        f"{len(mismatches)} corpus rows changed parse "
        f"(re-verify against bash before updating the table):\n"
        + "\n".join(mismatches))
