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
                  StatementList (alias CommandList), TopLevel.
- ``tests``     — ``[[ ... ]]`` test-expression nodes.
- ``control``   — FunctionDef, break/continue, case nodes, and the unified
                  control structures (loops, if, case, select, arithmetic).

Each node class' ``__module__`` is rewritten to ``psh.ast_nodes`` below, so
introspection that filters on the module name (e.g. the AST coverage-matrix
meta-test) sees the package as a single module, exactly as before the split.
"""

# Re-export the typing/stdlib names that were importable from the original
# flat module (it did ``from typing import ...`` at top level). No code
# relies on them today, but keeping them preserves drop-in parity.
from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from .arrays import (
    ArrayAssignment,
    ArrayElementAssignment,
    ArrayInitialization,
    _word_element_type,
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
    CommandList,
    Pipeline,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    TopLevel,
)
from .control import (
    ArithmeticEvaluation,
    BreakStatement,
    CaseConditional,
    CaseItem,
    CasePattern,
    ContinueStatement,
    CStyleForLoop,
    ForLoop,
    FunctionDef,
    IfConditional,
    SelectLoop,
    UntilLoop,
    WhileLoop,
)
from .redirects import Redirect
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
    _expansion_literal_text,
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
    'CommandList',
    'FunctionDef',
    'BreakStatement',
    'ContinueStatement',
    'CasePattern',
    'CaseItem',
    'TopLevel',
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
    # module-level helpers (were public in the flat module)
    '_expansion_literal_text',
    '_word_element_type',
]
