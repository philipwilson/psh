"""Quotes and expansions inside bracket-looking words.

bash gives quotes/expansions their normal meaning inside a non-assignment
bracket word: `echo x["ok"]` prints `x[ok]`, `echo x[$v]` expands, and
`echo x["oops` is an unterminated-quote error. Quote/expansion parsing is
suppressed ONLY inside confirmed array-assignment subscripts
(`NAME[...]=` / `NAME[...]+=`), where `h["k 1"]=v` keeps the quoted key
literal in one word. All behaviors below were probed against bash 5.2.
"""

import sys
from pathlib import Path

import pytest

PSH_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PSH_ROOT))

from psh.lexer import tokenize


class TestUnterminatedQuoteInBracketWord:
    """Unterminated quotes in bracket words are lexer errors (bash: rc 2)."""

    @pytest.mark.parametrize("text", [
        'echo x["unterminated',
        "echo x['unterm",
        'echo arr["x$USER]',     # the ] is inside the quote: still unclosed
        'echo ["unterminated',   # bracket at word start
    ])
    def test_unclosed_quote_raises(self, text):
        with pytest.raises(SyntaxError, match="Unclosed"):
            tokenize(text)


class TestArrayAssignmentSubscriptsStayLiteral:
    """Confirmed NAME[...]= subscripts keep quotes/expansions in one word."""

    @pytest.mark.parametrize("text,word", [
        ('a[0]=v', 'a[0]=v'),
        ('h["key"]=v', 'h["key"]=v'),
        ("h['key']=v", "h['key']=v"),
        ('h["k 1"]=v', 'h["k 1"]=v'),
        ('a[0]+=v', 'a[0]+=v'),
        ('h["k 1"]+=v', 'h["k 1"]+=v'),
    ])
    def test_single_word_token(self, text, word):
        tokens = [t for t in tokenize(text) if t.type.name != 'EOF']
        assert len(tokens) == 1
        assert tokens[0].type.name == 'WORD'
        assert tokens[0].value == word

    def test_command_substitution_subscript_with_spaces(self):
        # a[$(echo 1 + 1)]=v is ONE assignment word in bash; the spaces
        # inside $() must not end it.
        tokens = [t for t in tokenize('a[$(echo 1 + 1)]=v') if t.type.name != 'EOF']
        assert tokens[0].value.startswith('a[$(echo 1 + 1)]')

    def test_glob_class_word_not_split(self):
        # Unquoted glob classes keep lexing as single words.
        for text in ('echo [abc]*', 'echo x[abc]', 'echo x[!a]z',
                     'echo *[[:upper:]]*'):
            tokens = [t for t in tokenize(text) if t.type.name != 'EOF']
            assert len(tokens) == 2, f"{text}: {[(t.type.name, t.value) for t in tokens]}"


class TestQuotesInsideNonAssignmentBrackets:
    """Quotes/expansions in non-assignment bracket words behave normally."""

    def test_quoted_segment_splits_into_composite(self):
        # x["ok"] lexes as adjacent parts that the parser re-joins; the
        # quoted segment must NOT be a literal `"ok"` inside the word.
        tokens = [t for t in tokenize('echo x["ok"]') if t.type.name != 'EOF']
        values = [t.value for t in tokens]
        assert '"ok"' not in ' '.join(values)
        assert any(t.type.name == 'STRING' and t.value == 'ok' for t in tokens)

    def test_expansion_in_bracket_word_is_a_variable_token(self):
        tokens = [t for t in tokenize('echo x[$v]') if t.type.name != 'EOF']
        assert any(t.type.name == 'VARIABLE' and t.value == 'v' for t in tokens)

    def test_escaped_quote_in_bracket_stays_literal(self):
        # bash: echo x[\"] prints x["] — the escaped quote is literal.
        tokens = [t for t in tokenize('echo x[\\"]') if t.type.name != 'EOF']
        assert len(tokens) == 2
        assert tokens[1].value == 'x[\\"]'


class TestBracketWordBehavior:
    """End-to-end output matches bash (probed; words chosen to never glob-match)."""

    @pytest.mark.parametrize("cmd,expected", [
        ('echo zqz["ok"]', 'zqz[ok]\n'),
        ('v=abc; echo zqz[$v]', 'zqz[abc]\n'),
        ('echo zqz[$((1+1))]', 'zqz[2]\n'),
        ('echo zqz[b"c"d]e', 'zqz[bcd]e\n'),
        ("echo zqz[b'c'd]e", 'zqz[bcd]e\n'),
        ('echo zqz[\\"]', 'zqz["]\n'),
        ('echo ["a"]zqz', '[a]zqz\n'),
    ])
    def test_output(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected
        assert captured_shell.get_stderr() == ""


class TestAssocSubscriptQuoteRemoval:
    """Assoc lookups apply quote removal to subscripts, like assignments."""

    @pytest.mark.parametrize("cmd,expected", [
        ('declare -A h; h["key"]=v; echo ${h["key"]}', 'v\n'),
        ("declare -A h; h[key]=v; echo ${h['key']}", 'v\n'),
        ('declare -A h; h["k 1"]=v; echo "${h["k 1"]}"', 'v\n'),
        ('declare -A h; k=key; h[key]=v; echo ${h["$k"]}', 'v\n'),
        ('declare -A h; h["key"]=v; echo ${h[key]}', 'v\n'),
        ('declare -A h; h["key"]=abc; echo ${#h["key"]}', '3\n'),
        ('a[0]=v; echo ${a["0"]}', 'v\n'),
    ])
    def test_lookup(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected
        assert captured_shell.get_stderr() == ""
