"""AST node definitions for psh.

This package replaces the former single ``psh/ast_nodes.py`` module. It is
split into cohesive submodules but presents a FLAT namespace: every name
that was importable from ``psh.ast_nodes`` before is still importable from
it (``from psh.ast_nodes import SimpleCommand, Word, ...``). The submodules:

- ``base``      — ASTNode/Statement/Command/CompoundCommand bases + the
                  UnifiedControlStructure mixin.
- ``redirects`` — Redirect.
- ``words``     — Expansion nodes, WordPart/LiteralPart/ExpansionPart, Word.
- ``arrays``    — ArrayAssignment / ArrayInitialization / ArrayElementAssignment
                  (depend on Word).
- ``commands``  — SimpleCommand, SubshellGroup/BraceGroup, Pipeline, AndOrList,
                  StatementList, Program.
- ``tests``     — ``[[ ... ]]`` test-expression nodes.
- ``control``   — FunctionDef, case nodes, and the unified control
                  structures (loops, if, case, select, arithmetic).

Each node class' ``__module__`` is rewritten to ``psh.ast_nodes`` below, so
introspection that filters on the module name (e.g. the AST coverage-matrix
meta-test) sees the package as a single module, exactly as before the split.
"""

from .arrays import (
    ArrayAssignment,
    ArrayElementAssignment,
    ArrayInitialization,
)
from .base import (
    ASTNode,
    Command,
    CompoundCommand,
    Statement,
    UnifiedControlStructure,
)
from .commands import (
    AndOrList,
    BraceGroup,
    Pipeline,
    Program,
    SimpleCommand,
    StatementList,
    SubshellGroup,
)
from .control import (
    ArithmeticEvaluation,
    CaseConditional,
    CaseItem,
    CasePattern,
    CStyleForLoop,
    ForLoop,
    FunctionDef,
    IfConditional,
    SelectLoop,
    UntilLoop,
    WhileLoop,
)
from .redirects import Redirect

# Syntax templates (campaign S3) — plain frozen carriers, NOT ASTNode
# subclasses (so the AST coverage matrix / walk_ast schema, owned by S5, do not
# enumerate them; they are carried BY nodes, not traversed as nodes). Imported
# after .words because they reference Expansion/CommandSubstitution.
from .syntax_templates import (
    ArithmeticTemplate,
    NestedSub,
    SubscriptSpec,
    SyntaxTemplate,
    WordTemplate,
)
from .tests import (
    BinaryTestExpression,
    CompoundTestExpression,
    EnhancedTestStatement,
    NegatedTestExpression,
    TestExpression,
    UnaryTestExpression,
)
from .words import (
    ArithmeticExpansion,
    CommandSubstitution,
    Expansion,
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    ProcessSubstitution,
    VariableExpansion,
    Word,
    WordPart,
)


# ---------------------------------------------------------------------------
# Present the package as a single logical module for introspection.
#
# The AST coverage-matrix meta-test enumerates node classes by filtering on
# ``cls.__module__ == 'psh.ast_nodes'``. Each class is physically defined in
# a submodule, so its ``__module__`` would otherwise be e.g.
# ``psh.ast_nodes.words``. Rewrite it on the public node classes so the flat
# package looks exactly like the old single module.
# ---------------------------------------------------------------------------
def _reparent_to_package() -> None:
    import inspect
    for _obj in list(globals().values()):
        if (inspect.isclass(_obj)
                and issubclass(_obj, ASTNode)
                and _obj.__module__.startswith('psh.ast_nodes.')):
            _obj.__module__ = 'psh.ast_nodes'


_reparent_to_package()


# Public names, in the original definition order of the flat module.
__all__ = [
    # base
    'ASTNode',
    'Statement',
    # redirects
    'Redirect',
    # expansions
    'Expansion',
    'ProcessSubstitution',
    'CommandSubstitution',
    'ParameterExpansion',
    'VariableExpansion',
    'ArithmeticExpansion',
    # words
    'WordPart',
    'LiteralPart',
    'ExpansionPart',
    'Word',
    # syntax templates (S3)
    'SyntaxTemplate',
    'WordTemplate',
    'ArithmeticTemplate',
    'SubscriptSpec',
    'NestedSub',
    # arrays
    'ArrayAssignment',
    'ArrayInitialization',
    'ArrayElementAssignment',
    # commands / containers
    'Command',
    'SimpleCommand',
    'CompoundCommand',
    'SubshellGroup',
    'BraceGroup',
    'Pipeline',
    'AndOrList',
    'StatementList',
    'Program',
    'FunctionDef',
    'CasePattern',
    'CaseItem',
    # test expressions
    'TestExpression',
    'BinaryTestExpression',
    'UnaryTestExpression',
    'CompoundTestExpression',
    'NegatedTestExpression',
    'EnhancedTestStatement',
    # unified control structures
    'UnifiedControlStructure',
    'WhileLoop',
    'UntilLoop',
    'ForLoop',
    'CStyleForLoop',
    'IfConditional',
    'CaseConditional',
    'SelectLoop',
    'ArithmeticEvaluation',
]
