#!/usr/bin/env python3
"""MEDIUM-10 red-on-base: the executable heredoc type and the lexed value
graph can both REPRESENT states they document as impossible.

(a) A bare token-level parse manufactures an EXECUTABLE HeredocRedirect with
    heredoc_content=None on BOTH parsers; execution discovers it only at
    io_redirect/file_redirect.py#FileRedirector.redirect_heredoc.
(b) LexedUnit is "immutable", but every Token in it hands out a live mutable
    `parts` list of mutable TokenPart objects -- so a lexed value can be
    rewritten after the lexer returned it.

Structural dumps only (no free-text greps). Usage: python3 medium10_probe.py
"""
import dataclasses
import sys

sys.path.insert(0, "/Users/pwilson/src/psh-r2-5")

from psh.lexer import tokenize                                    # noqa: E402
from psh.lexer.heredoc_lexer import HeredocLexer                  # noqa: E402
from psh.parser.recursive_descent.parser import Parser            # noqa: E402
from psh.parser.combinators.parser import ParserCombinatorShellParser  # noqa: E402

SRC = "cat <<EOF"
print("=== (a) executable heredoc with heredoc_content=None ===")

# --- RD bare parse (heredocs=None: the unit-test / bare-token path) ---
toks = tokenize(SRC)
prog = Parser(list(toks), source_text=SRC).parse()
rd_redir = prog.statements[0].pipelines[0].commands[0].redirects[0]
print("RD    :", dataclasses.asdict(rd_redir).__class__.__name__,
      {k: v for k, v in dataclasses.asdict(rd_redir).items()
       if k in ("type", "target", "heredoc_content", "heredoc_id")})

# --- Combinator: heredocs map PRESENT but the operator token carries no id
#     (the missing-operator-ID fallback at combinators/commands/redirections.py) ---
unit = HeredocLexer(SRC, warn_unterminated=False).tokenize_with_heredocs()
stripped = [dataclasses.replace(t, heredoc_id=None) for t in unit.tokens]
cprog = ParserCombinatorShellParser().parse_with_heredocs(stripped, unit.heredocs)
c_redir = cprog.statements[0].pipelines[0].commands[0].redirects[0]
print("COMBI :", {k: v for k, v in dataclasses.asdict(c_redir).items()
                  if k in ("type", "target", "heredoc_content", "heredoc_id")})
print("both heredoc_content is None:",
      rd_redir.heredoc_content is None and c_redir.heredoc_content is None)

# --- where execution discovers it ---
print("\n--- execution's late discovery ---")
from psh.shell import Shell                                       # noqa: E402
sh = Shell(norc=True)
try:
    sh.io_manager.file_redirector.redirect_heredoc(rd_redir)
    print("NO ERROR (unexpected)")
except RuntimeError as e:
    import traceback
    tb = traceback.extract_tb(sys.exc_info()[2])[-1]
    print(f"RuntimeError at {tb.filename.split('/psh/')[-1]}:{tb.lineno} -> {e}")

print("\n=== (b) the 'immutable' lexed value graph is writable ===")
unit2 = HeredocLexer('echo "a$b"c', warn_unterminated=False).tokenize_with_heredocs()
tok = next(t for t in unit2.tokens if t.parts)
print("token frozen?      ", tok.__dataclass_params__.frozen)
print("TokenPart frozen?  ", type(tok.parts[0]).__dataclass_params__.frozen)
before = [(p.value, p.quote_type) for p in tok.parts]

tok.parts[0].value = "PWNED"          # mutate a TokenPart field
tok.parts[0].quote_type = "'"         # ... and another
tok.parts.append(tok.parts[0])        # mutate the LIST inside a frozen Token
tok.parts.clear() if False else None

after = [(p.value, p.quote_type) for p in tok.parts]
print("parts before:", before)
print("parts after :", after)
print("MUTATION SUCCEEDED:", before != after)
print("container edge: type(Token.parts) =", type(tok.parts).__name__,
      "| type(LexedUnit.tokens) =", type(unit2.tokens).__name__,
      "| type(LexedUnit.heredocs) =", type(unit2.heredocs).__name__)
