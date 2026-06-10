# Repository Guidelines

## Project Structure & Module Organization
Core implementation lives in `psh/`, organized by subsystem:
- `lexer/`, `parser/`, `expansion/`, `executor/`, `io_redirect/`, `interactive/`, `builtins/`, `core/`, and `visitor/`.
- Entry points: `psh/__main__.py` (CLI) and `psh/shell.py` (orchestration).
- Tests are under `tests/` by scope: `tests/unit/`, `tests/integration/`, `tests/system/`, `tests/regression/`, `tests/conformance/`, and `tests/performance/`.
- POSIX/bash compatibility tests live in `tests/conformance/`. Architecture and design notes are in `README.md`, `ARCHITECTURE.md`, and subsystem `CLAUDE.md` files.

## Build, Test, and Development Commands
- Canonical command set is maintained in `docs/testing_source_of_truth.md`.
- `pip install -e .` installs PSH in editable mode.
- `pip install -e ".[dev]"` installs test dependencies.
- `python -m psh -c "echo hello"` runs a one-shot command.
- `python run_tests.py` runs the recommended multi-phase test flow (handles subshell capture edge cases).
- `python run_tests.py --quick` skips slow tests during iteration.
- `python -m pytest tests/` runs pytest directly.
- Subshell tests pass under normal capture (`-s` no longer required as of v0.195.0).
- `python -m pytest tests/ --cov=psh --cov-report=html` generates a coverage report.

## Coding Style & Naming Conventions
- Python, 4-space indentation, and max line length `120` (configured in `pyproject.toml`).
- Prefer clear, modular functions over dense logic; keep subsystem boundaries intact.
- Naming: `snake_case` for functions/modules, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Ruff rules are configured in `pyproject.toml`; run `ruff check .` when available.

## Testing Guidelines
- Framework: `pytest` with markers (`unit`, `integration`, `conformance`, `performance`, `slow`, etc.) from `pytest.ini`.
- Test files/functions should follow `test_*.py` and `test_*` naming.
- Add or update tests with every behavior change, especially integration tests for shell semantics.
- Use `run_tests.py` for full validation before opening a PR.

## Commit & Pull Request Guidelines
- Follow existing history style: `fix: ...`, `refactor: ...`, `docs: ...`, `chore: ...` with concise imperative summaries.
- Keep commits focused by subsystem (parser, expansion, executor, etc.).
- PRs should include: purpose, key behavior changes, tests run (exact commands), and doc updates when behavior/architecture changes.
- For release-oriented changes, update `psh/version.py`; tagging is handled at release time.
