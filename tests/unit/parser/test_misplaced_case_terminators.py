"""Misplaced case terminators (`;;`, `;&`, `;;&`) are parse errors.

These are rejected by the PARSER (statements/commands parsers), matching
bash's "syntax error near unexpected token" — there is no lexer-level
validation pass (the old `TokenTransformer`, which appeared to validate
this, was removed as dead code: it appended every token unchanged).
All behaviors below were probed against bash 5.2.
"""

import sys
from pathlib import Path

import pytest

PSH_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PSH_ROOT))

from psh.lexer import tokenize
from psh.parser import ParseError, parse


def parse_str(text):
    return parse(list(tokenize(text)))


class TestMisplacedCaseTerminators:
    @pytest.mark.parametrize("text,token", [
        ("echo a ;; echo b", ";;"),
        (";; echo b", ";;"),
        ("echo a ;& echo b", ";&"),
        ("echo a ;;& echo b", ";;&"),
        ("if true; then echo a ;; fi", ";;"),
        ("while true; do echo a ;; done", ";;"),
    ])
    def test_rejected_outside_case(self, text, token):
        with pytest.raises(ParseError) as excinfo:
            parse_str(text)
        assert f"syntax error near unexpected token '{token}'" in str(excinfo.value)

    @pytest.mark.parametrize("text", [
        "case x in x) echo ok;; esac",
        "case x in x) echo a;& y) echo b;; esac",
        "case x in x) echo a;;& *) echo b;; esac",
        "case x in x) echo ok;; esac; echo after",
    ])
    def test_valid_inside_case(self, text):
        assert parse_str(text) is not None
