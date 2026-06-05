# Contract Tests (Draft)

These tests assert observable shell behavior for job control, process substitution, and redirections.

## How to run
pytest contract_tests_draft

## Optional dependency
Job-control tests use `pexpect` for PTY interaction.
Install with:
`pip install pexpect`
