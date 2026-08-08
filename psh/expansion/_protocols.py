"""Type-only Protocol for the VariableExpander mixins.

``VariableExpander`` (variable.py) is composed from four mixins —
``ArrayOpsMixin`` (arrays.py), ``OperatorOpsMixin`` (operators.py),
``OperandOpsMixin`` (operands.py), and ``FieldExpansionMixin``
(fields.py). Each mixin references ``self.state`` / ``self.shell`` /
``self.param_expansion`` (set in ``VariableExpander.__init__``) and
methods defined on *sibling* mixins or on ``VariableExpander`` itself.
mypy cannot see those when checking a mixin in isolation.

``VariableExpanderProtocol`` declares exactly that shared surface so the
mixins type-check. It is purely a typing artifact: each mixin declares it
as a base **only** under ``TYPE_CHECKING`` (so there is no runtime MRO or
behavior change), and ``VariableExpander`` structurally satisfies it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from ..core.state import ShellState
    from ..shell import Shell
    from .operands import OperandOrStr, OperandValue
    from .parameter_expansion import ParameterExpansionOps


class VariableExpanderProtocol(Protocol):
    """The attributes and cross-mixin methods the expander mixins use."""

    #: The whole ``Shell``, reached at 11 sites: eight
    #: ``self.shell.expansion_manager`` hops, and three that forward the shell
    #: WHOLE (``evaluate_arithmetic(expr, self.shell)`` twice and
    #: ``PromptExpander(self.shell)`` once, all in ``operators.py``).
    #:
    #: Remediation 5B.2 was chartered to REMOVE this member and did not.
    #: Migrating the eight manager hops to ``protocols.ExpansionRuntime``
    #: fails on measurement: they reach ``.subscript`` (4), ``.command_sub``
    #: (2), ``.execute_arithmetic_expansion`` and ``.tilde_expander`` — and
    #: ``ExpansionRuntime`` declares none of those. Its four members
    #: (``expand_string_variables``, ``expand_assignment_value_word``,
    #: ``variable_expander``, ``word_expander``) fit the SUBSCRIPT authority,
    #: which consumes it, but not these mixins, whose reaches are to the
    #: manager's sub-expanders. The twelfth site — a ``state.locale`` read —
    #: did migrate, to the ``state`` member below. The census is pinned by
    #: ``tests/unit/expansion/test_variable_expander_reach_5b2.py`` so the
    #: remainder stays a measured quantity; successor row D-5B.2-s2.
    shell: "Shell"

    #: The whole ``ShellState``. Remediation 5B.2 measured whether this could
    #: narrow to the campaign's three-member variable value-surface protocol
    #: (``get_variable``/``set_variable``/``get_special_variable``): it cannot.
    #: The four mixins reach ELEVEN distinct state members across 47 sites, and
    #: 44 of those sites use one of the EIGHT outside that surface —
    #: ``scope_manager`` (12),
    #: ``last_exit_code`` (11), ``error_location_prefix`` (10),
    #: ``positional_params`` (5), ``stderr`` (3), ``options``,
    #: ``ifs_star_separator``, ``last_bg_pid``. Widening that protocol to fit
    #: would have absorbed most of ``ShellState`` into a surface whose entire
    #: point was NOT being ``ShellState``, so it was deleted instead and this
    #: member stays as it is, with the census as its justification. A future
    #: value-surface protocol designs against the 11 members above, not against
    #: the deleted three (successor row D-5B.2-s1).
    state: "ShellState"

    param_expansion: "ParameterExpansionOps"

    # --- variable.py entry points ---
    def expand_variable(self, var_expr: str,
                        quote_ctx: Optional[str] = None) -> 'OperandOrStr': ...
    def expand_string_variables(self, text: str,
                                quote_ctx: Optional[str] = None) -> str: ...

    # --- arrays.py (ArrayOpsMixin) ---
    @staticmethod
    def split_subscript(name: str) -> Optional["tuple[str, str]"]: ...
    def _resolve_array_name(self, array_name: str) -> str: ...
    def _eval_array_index(self, index_expr: str) -> int: ...
    def set_var_or_array_element(self, var_name: str, value: str) -> None: ...
    def array_fields(self, array_name: str, keys: bool = False) -> list: ...
    def _array_keyvalue_form(self, op: str, var) -> str: ...
    def _array_keyvalue_fields(self, var) -> list: ...

    # --- operands.py (OperandOpsMixin) ---
    def _expand_operand(self, operand: str,
                        quote_ctx: Optional[str] = None) -> 'OperandValue': ...
    def _expand_pattern_operand(self, operand: str) -> str: ...
    def _expand_replacement_operand(self, operand: str) -> list: ...
    def _split_pattern_replacement(self, operand: str): ...

    # --- operators.py (OperatorOpsMixin) ---
    def _ifs_star_separator(self) -> str: ...
    def _var_attr_flags(self, var_name: str) -> str: ...
    def _shell_quote(self, s: str) -> str: ...
    def _apply_op_per_element(self, operator, value, operand, var_name): ...
    def _view_conditional(self, operator: str, elements: list, joiner: str,
                          operand, qmark_subject: str,
                          assign_error: str,
                          quote_ctx: Optional[str] = None) -> list: ...
    def _positional_slice_elements(self) -> list: ...
    def _parse_slice_operand(self, operand: str, what: str) -> tuple: ...
    def _slice_elements(self, elements: list, offset: int,
                        length, indices=None) -> list: ...
    def _slice_scalar_subscript(self, value: str, offset: int, length) -> list: ...

    # --- fields.py (FieldExpansionMixin) ---
    def expand_to_fields(self, parameter: str, operator, operand,
                         quote_ctx: Optional[str] = None): ...
