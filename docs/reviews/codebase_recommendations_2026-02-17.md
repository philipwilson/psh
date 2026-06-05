# PSH Codebase Improvement Recommendations

Date: 2026-02-17
Repository: `/Users/pwilson/src/psh`

## Scope

This review covered core runtime paths and developer workflows:
- Shell orchestration (`shell`, `scripting`)
- Parser interfaces (recursive descent and combinator selection)
- Expansion, command execution, and redirection paths
- Interactive line editor and job control
- Test and lint tooling/docs alignment

## Prioritized Recommendations

1. Fix parser `source_text` plumbing (likely bug).
   - `psh/scripting/source_processor.py:305` passes `source_text`, but `psh/parser/__init__.py:54` and `psh/parser/__init__.py:87` drop it for recursive descent.
   - `psh/parser/recursive_descent/parser.py:85` supports `source_text`, so this appears to be an integration gap.

2. Replace string-matching parse heuristics with structured parse error codes.
   - `psh/scripting/source_processor.py:168` and `psh/scripting/source_processor.py:190` classify incomplete input by matching error text.
   - `psh/parser/recursive_descent/helpers.py:93` already has `error_code`; use that consistently from parser emitters (for example via `psh/parser/recursive_descent/context.py:249`) and consume codes in `SourceProcessor`.

3. Remove silent fallback behavior in expansion failures.
   - `psh/expansion/manager.py:496` catches internal evaluation errors and returns `str(expansion)` at `psh/expansion/manager.py:508`.
   - This can mask defects and produce surprising runtime behavior.

4. Tighten broad exception boundaries in hot runtime paths.
   - `psh/executor/command.py:183` and `psh/scripting/source_processor.py:381` catch generic `Exception`.
   - Narrowing these handlers will improve diagnosability and reduce hidden regressions.

5. Clean up I/O redirection layering boundaries.
   - `psh/io_redirect/manager.py:72` and `psh/io_redirect/manager.py:185` call many `FileRedirector` private methods (`_expand_redirect_target`, `_redirect_*`).
   - Promote a public API on `FileRedirector` and keep `IOManager` focused on orchestration.

6. Reduce orchestration complexity in the largest control modules.
   - `psh/shell.py:21`, `psh/scripting/source_processor.py:19`, and `psh/line_editor.py:126` hold broad responsibilities.
   - Split into focused subcomponents to reduce coupling and regression surface.

7. Close the remaining active runtime TODOs.
   - `psh/parser/recursive_descent/support/word_builder.py:288`
   - `psh/builtins/job_control.py:31`
   - `psh/builtins/type_builtin.py:90`

8. Improve local developer ergonomics and runtime determinism.
   - `run_tests.py:156` shells out with `python` instead of `sys.executable`.
   - CI installs `ruff` (`.github/workflows/test_migration.yml:19`) but `pyproject.toml:33` dev extras do not include it.

9. Resolve documentation status drift.
   - `README.md:7` reports ~98% POSIX compliance while `docs/improvement_recommendations.md:5` reports 51.9%.
   - Maintain one canonical status source and date-stamp it.

10. Add an automated combinator-parser smoke lane.
    - Combinator mode is available via `run_tests.py:135`, but CI currently exercises the default path only (`.github/workflows/test_migration.yml:42`).
    - A small periodic combinator smoke job would catch parser drift earlier.

## Validation Notes

Commands run during this review:
- `python -m psh -c "echo hello"`: success.
- `python run_tests.py --quick`: failed in this environment because `pytest` is not installed.
- `ruff check .`: could not run in this environment because `ruff` is not installed.

