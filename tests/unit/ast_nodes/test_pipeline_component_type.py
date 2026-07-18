"""PipelineComponent — the exhaustive typed sum of pipeline members (S5, #20 H9).

Drift-locks the PipelineComponent union against reflection: it must name EXACTLY
the concrete Command subclasses, and FunctionDef must be among them (it joined
the sum in S5). A Statement-only node (AndOrList) must NOT be a pipeline
component. Also pins FunctionDef's dual Statement+Command identity and its inert
`background` field.
"""
import dataclasses
import inspect
import typing

import psh.ast_nodes as ast_mod
from psh.ast_nodes import (
    AndOrList,
    ASTNode,
    Command,
    FunctionDef,
    Pipeline,
    PipelineComponent,
    SimpleCommand,
    Statement,
    StatementList,
)


def _concrete_command_classes():
    out = set()
    for obj in vars(ast_mod).values():
        if (inspect.isclass(obj) and issubclass(obj, ASTNode)
                and obj.__module__ == 'psh.ast_nodes'
                and dataclasses.is_dataclass(obj) and issubclass(obj, Command)):
            out.add(obj)
    return out


def test_pipeline_component_union_is_exhaustive():
    """PipelineComponent names EXACTLY the concrete Command subclasses (drift-lock).

    A new compound command (or a new pipeline-able node) added without updating
    the union fails here.
    """
    union_members = set(typing.get_args(PipelineComponent))
    concrete_commands = _concrete_command_classes()
    assert union_members == concrete_commands, (
        f"PipelineComponent drift: union-only={union_members - concrete_commands}, "
        f"missing-from-union={concrete_commands - union_members}"
    )


def test_function_def_is_in_the_pipeline_component_sum():
    assert FunctionDef in typing.get_args(PipelineComponent)


def test_function_def_is_both_statement_and_command():
    """A function def is a Statement (standalone) AND a Command (pipeline member)."""
    assert issubclass(FunctionDef, Statement)
    assert issubclass(FunctionDef, Command)


def test_statement_only_node_is_not_a_pipeline_component():
    """AndOrList is Statement-only — above pipelines, never a member (offender)."""
    assert issubclass(AndOrList, Statement)
    assert not issubclass(AndOrList, Command)
    assert AndOrList not in typing.get_args(PipelineComponent)


def test_pipeline_can_hold_a_function_def():
    """A Pipeline may contain a FunctionDef member (type + runtime)."""
    fd = FunctionDef(name='f', body=StatementList(statements=[]))
    pipe = Pipeline(commands=[fd, SimpleCommand()])
    assert isinstance(pipe.commands[0], (Command, FunctionDef))
    assert pipe.commands[0] is fd


def test_function_def_background_field_is_inert_false_by_default():
    """FunctionDef carries the Command `background` field (so the pipeline
    executor's uniform `commands[-1].background` read is safe); it defaults False
    and is never set True for a def (background routes to the and-or list)."""
    fd = FunctionDef(name='f', body=StatementList(statements=[]))
    assert fd.background is False
    assert hasattr(fd, 'redirects')
