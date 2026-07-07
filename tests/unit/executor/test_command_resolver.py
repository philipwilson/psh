"""Unit tests for the shared CommandResolver (builtins appraisal finding 5)."""

import os
import stat

from psh.executor.command_resolver import (
    Candidate,
    CandidateKind,
    ResolveQuery,
)


def _mkexe(path: str) -> None:
    with open(path, "w") as f:
        f.write("#!/bin/sh\necho hi\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class TestSearchPath:
    """The one PATH walk: empty component = cwd, slash name as given."""

    def test_first_match(self, captured_shell, tmp_path):
        _mkexe(str(tmp_path / "prog"))
        r = captured_shell.command_resolver
        assert r.search_path("prog", str(tmp_path)) == [str(tmp_path / "prog")]

    def test_all_matches(self, captured_shell, tmp_path):
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()
        _mkexe(str(d1 / "prog"))
        _mkexe(str(d2 / "prog"))
        r = captured_shell.command_resolver
        found = r.search_path("prog", f"{d1}:{d2}", all_matches=True)
        assert found == [str(d1 / "prog"), str(d2 / "prog")]

    def test_empty_component_is_cwd(self, captured_shell, tmp_path, monkeypatch):
        _mkexe(str(tmp_path / "prog"))
        monkeypatch.chdir(tmp_path)
        r = captured_shell.command_resolver
        assert r.search_path("prog", ":/usr/bin") == ["./prog"]
        assert r.search_path("prog", "/usr/bin:") == ["./prog"]

    def test_slash_name_kept_as_given(self, captured_shell, tmp_path, monkeypatch):
        _mkexe(str(tmp_path / "prog"))
        monkeypatch.chdir(tmp_path)
        r = captured_shell.command_resolver
        # A relative slash name is returned verbatim, not canonicalised.
        assert r.search_path("./prog", "/ignored") == ["./prog"]

    def test_non_executable_skipped(self, captured_shell, tmp_path):
        p = tmp_path / "prog"
        p.write_text("data")  # not +x
        r = captured_shell.command_resolver
        assert r.search_path("prog", str(tmp_path)) == []


class TestResolveOrder:
    """resolve() reports candidates in bash's lookup precedence order."""

    def test_builtin(self, captured_shell):
        res = captured_shell.command_resolver.resolve("echo")
        assert res.first.kind is CandidateKind.BUILTIN

    def test_keyword(self, captured_shell):
        res = captured_shell.command_resolver.resolve("while")
        assert res.first.kind is CandidateKind.KEYWORD

    def test_function_over_builtin(self, captured_shell):
        captured_shell.run_command("cd() { :; }")
        res = captured_shell.command_resolver.resolve("cd")
        assert res.first.kind is CandidateKind.FUNCTION

    def test_function_bypass(self, captured_shell):
        captured_shell.run_command("cd() { :; }")
        q = ResolveQuery(use_functions=False)
        res = captured_shell.command_resolver.resolve("cd", q)
        # cd is a builtin, so with functions bypassed the builtin wins.
        assert res.first.kind is CandidateKind.BUILTIN

    def test_not_found(self, captured_shell):
        res = captured_shell.command_resolver.resolve("zzznope_cmd_xyz")
        assert not res.found
        assert res.first is None

    def test_special_builtin_flag(self, captured_shell):
        res = captured_shell.command_resolver.resolve("export")
        assert res.first.kind is CandidateKind.BUILTIN
        assert res.first.is_special_builtin is True


class TestHashCandidate:
    """The hash participates as a completed PATH search (bash)."""

    def test_hash_first_over_path(self, captured_shell):
        captured_shell.run_command("hash -p /tmp/custom customcmd")
        res = captured_shell.command_resolver.resolve("customcmd")
        assert res.first == Candidate(
            CandidateKind.HASHED, "customcmd", path="/tmp/custom")

    def test_all_matches_ignores_hash(self, captured_shell):
        captured_shell.run_command("hash -p /tmp/custom customcmd")
        q = ResolveQuery(all_matches=True)
        res = captured_shell.command_resolver.resolve("customcmd", q)
        # -a walks PATH only; the (nonexistent) hashed path is not a candidate.
        assert not res.found

    def test_introspection_does_not_populate(self, captured_shell):
        # A default resolve of a real command must not remember it (only the
        # executor's exec path populates the hash).
        captured_shell.command_resolver.resolve("sh")
        assert len(captured_shell.state.command_hash) == 0
