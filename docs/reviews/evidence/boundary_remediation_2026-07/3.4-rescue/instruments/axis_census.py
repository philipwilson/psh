#!/usr/bin/env python3
"""SLOT INSTRUMENT — prove every A8 axis actually has cells.

R11 warned, and R14's B5 fired: an axis can be dropped from the matrix while
the done-list still claims "matrix complete". Twice now a dropped axis hid a
divergent row. So the done-list carries this next to its checked boxes: a
mechanical count of COLLECTED TESTS per axis, not a grep over source lines
(a grep counts the mention, which is the thing that was never in doubt).
"""
import re
import subprocess
import sys

BATTERY = 'tests/conformance/bash/test_resolution_timing_conformance.py'

AXES = {
    'side-effect KIND (posix flip)': 'store_kind_flips_posix or store_nested_inside',
    'side-effect KIND (generated family)':
        'evaluates_no_side_effect_kind or DOES_evaluate_each_kind or '
        'fatal_kinds_do_not_abort or command_substitution_never_runs or '
        'is_not_traced',
    'nameref spelling': 'nameref_spelled or nameref_name_level',
    'position in prefix list': 'store_position_in_the_prefix_list',
    'resolution TARGET KIND': 'function_shadowing_a_special_builtin or target_kinds_posix',
    'POSIX direction': 'posix_OFF or already_posix or name_level_zero',
    'persistence': 'own_flip_makes or persistence or side_effect_itself_persists',
    'temp-env visibility': 'temp_env_visibility',
    'carry #7 (dynamic special)': 'carry7',
    'arithmetic-context special read': 'arithmetic_context_read',
    'INPUT MODE (-c / script / stdin)': 'script_mode or stdin_mode',
    'PARSER (rd / combinator)': 'combinator_parser',
    "command's own name variable": 'command_own_name_variable',
    'readonly refusal (RO1)': 'ro1 or refused_prefix or readonly_refusal',
    'enumeration surface (F-family)': 'invisible_to_enumeration',
    'command substitution (excluded)': 'command_substitution_is_not_a_resolution_input',
    'left-to-right visibility': 'left_to_right_value_visibility',
    'not-found / redirection': 'command_not_found or redirection_error',
}


def count(expr: str) -> int:
    out = subprocess.run(
        [sys.executable, '-m', 'pytest', BATTERY, '--collect-only', '-q',
         '-p', 'no:randomly', '-k', expr],
        capture_output=True, text=True).stdout
    m = re.search(r'(\d+)/?\d* tests? collected', out)
    return int(m.group(1)) if m else 0


empty = []
print(f"{'axis':36s} {'cells':>5s}")
for axis, expr in AXES.items():
    n = count(expr)
    if n == 0:
        empty.append(axis)
    print(f"{axis:36s} {n:>5d}{'   <-- EMPTY' if n == 0 else ''}")
print(f"\n{len(AXES)} axes, {sum(1 for a in AXES if a not in empty)} populated, "
      f"{len(empty)} EMPTY")
sys.exit(1 if empty else 0)
