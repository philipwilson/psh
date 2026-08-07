"""History state machine vs bash 5.2 (slot 4B.3, MEDIUM-7 + LEDGER #25/#32).

End-to-end cells for the `-r/-n/-d/-s/-a/-w/-c` state machine. The history
builtins are interactive-gated, so every cell drives a piped `--norc -i` shell
through the typed oracle runner with its own $HISTFILE under the test's
tmp_path. The state machine is harness-independent: every face here was also
reproduced under a real PTY during Phase A, in the same direction.

`HISTIGNORE` suppresses the cells' own scaffolding from being RECORDED, so the
in-memory list holds only what the cell deliberately put there. That is not a
convenience: `history -s`'s store bypasses the invocation pattern (HISTIGNORE
is matched against the STORED text), so the suppression cannot mask the very
behaviour under test.

TWO FAMILIES LIVE HERE:

* **parity rows** — psh must match bash.
* **declared-deviation rows** — psh deliberately differs, and BOTH sides are
  asserted so an accidental move on either fails. bash's `-a` is not a marker:
  it writes the LAST N entries of the list BY POSITION, where N counts
  session-recorded lines plus `-n`-read lines. When a read or a `-d` lands
  between recording and saving, bash therefore writes the wrong entries —
  losing typed commands and leaking read ones. psh keeps v0.447's
  no-loss/no-duplicate guarantee instead. The state-machine observables (the
  in-memory list, cursor behaviour, exit status) still match bash.
"""

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

# Suppress the cells' own scaffolding from the recorded history.
HI = "history*:echo ===*:cat *:exit:printf *:true SCAFFOLD*"


def _drive(runner, script, tmp_path, name, seed=None, env=None, named=None):
    """Run *script* in a piped interactive shell; return (sections, file)."""
    hf = tmp_path / f"hist_{name}"
    hf.write_text("".join(line + "\n" for line in (seed or [])))
    for base, lines in (named or {}).items():
        (tmp_path / base).write_text("".join(x + "\n" for x in lines))
    case_env = {"HISTFILE": str(hf), "TERM": "dumb", "HISTIGNORE": HI}
    case_env.update(env or {})
    result = runner(["--norc", "-i"],
                    stdin_data=script.replace("$OTHER", str(tmp_path)),
                    stdin_mode="pipe", env=case_env, timeout=30)
    assert is_comparable(result), result
    sections, cur = {}, None
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if line.startswith("===") and line.endswith("===") and len(line) > 6:
            cur = line.strip("=")
            sections[cur] = []
        elif cur is not None and line:
            sections[cur].append(line)
    after = [x.rstrip("\n") for x in hf.read_text().splitlines() if x.strip()] \
        if hf.exists() else []
    return sections, after


def _listing(lines):
    """Entry text from ``NNNN  text`` listing lines."""
    out = []
    for line in lines:
        head = line.split("  ", 1)
        out.append(head[1] if len(head) == 2 and head[0].strip().isdigit()
                   else "?" + line)
    return out


OBSERVE = 'echo ===MEM===\nhistory\n'


def both(script, tmp_path, name, **kw):
    """Drive bash and psh over the same cell; return (bash, psh) pairs."""
    b = _drive(run_bash, script, tmp_path, name + "_b", **kw)
    p = _drive(run_psh, script, tmp_path, name + "_p", **kw)
    return b, p


class TestCursorConflationLegA:
    """MEDIUM-7 leg A: `-d` must not rewind the FILE read position."""

    def test_delete_then_external_append_then_read_new(self, tmp_path):
        script = ('history -d 1\n'
                  'printf "seedD\\n" >> "$HISTFILE"\n'
                  'history -n\n' + OBSERVE + 'exit\n')
        (bs, _), (ps, _) = both(script, tmp_path, "legA",
                                seed=["seedA", "seedB", "seedC"])
        assert _listing(bs["MEM"]) == ["seedB", "seedC", "seedD"]
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])

    @pytest.mark.parametrize("spec", ["1", "1-2", "3"])
    def test_delete_shapes_do_not_rewind_the_cursor(self, tmp_path, spec):
        """Below the cursor, spanning it, and at it."""
        script = (f'history -d {spec}\n'
                  'printf "EXT\\n" >> "$HISTFILE"\n'
                  'history -n\n' + OBSERVE + 'exit\n')
        (bs, _), (ps, _) = both(script, tmp_path, f"legA{spec}",
                                seed=["s1", "s2", "s3"])
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])
        assert _listing(ps["MEM"])[-1] == "EXT"


class TestStorePolicyLegB:
    """MEDIUM-7 leg B: `history -s` runs the SAME recording policy as a typed
    line — filters AND the HISTSIZE cap — not a raw append."""

    @pytest.mark.parametrize("histsize,expected", [
        ("3", ["s3", "s4", "s5"]),
        ("1", ["s5"]),
        ("0", []),
    ])
    def test_histsize_caps_the_store(self, tmp_path, histsize, expected):
        script = "".join(f"history -s s{i}\n" for i in range(1, 6)) \
            + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, f"legB{histsize}",
                                env={"HISTSIZE": histsize})
        assert _listing(bs["MEM"]) == expected
        assert _listing(ps["MEM"]) == expected

    def test_negative_histsize_is_unlimited(self, tmp_path):
        script = "".join(f"history -s s{i}\n" for i in range(1, 6)) \
            + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "legBneg",
                                env={"HISTSIZE": "-1"})
        assert _listing(bs["MEM"]) == [f"s{i}" for i in range(1, 6)]
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])

    @pytest.mark.parametrize("histcontrol,script_body,expected", [
        ("ignoredups", "history -s dup\nhistory -s dup\n", ["dup"]),
        ("erasedups", "history -s aaa\nhistory -s bbb\nhistory -s aaa\n",
         ["bbb", "aaa"]),
        ("ignorespace", 'history -s " spaced"\n', []),
    ])
    def test_histcontrol_applies_to_the_store(self, tmp_path, histcontrol,
                                              script_body, expected):
        (bs, _), (ps, _) = both(script_body + OBSERVE + "exit\n", tmp_path,
                                f"legB{histcontrol}",
                                env={"HISTCONTROL": histcontrol})
        assert _listing(bs["MEM"]) == expected
        assert _listing(ps["MEM"]) == expected

    def test_histignore_matches_the_stored_text_not_the_invocation(self, tmp_path):
        script = "history -s blocked\nhistory -s kept\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "legBhi",
                                env={"HISTIGNORE": "blocked:" + HI})
        assert _listing(bs["MEM"]) == ["kept"]
        assert _listing(ps["MEM"]) == ["kept"]

    def test_multiple_args_become_one_entry(self, tmp_path):
        script = "history -s echo hello world\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "legBjoin")
        assert _listing(bs["MEM"]) == ["echo hello world"]
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])


class TestClearCounterLegC:
    """MEDIUM-7 leg C / LEDGER carry #32: `-c` clears MEMORY, not the record of
    what has been read from the file."""

    def test_clear_then_read_new_does_not_rematerialise(self, tmp_path):
        script = ('echo seedX\n'
                  'history -a\nhistory -c\nhistory -n\n' + OBSERVE + 'exit\n')
        (bs, _), (ps, _) = both(script, tmp_path, "legC", env={"HISTIGNORE": ""})
        assert "echo seedX" not in _listing(bs["MEM"])
        assert "echo seedX" not in _listing(ps["MEM"])

    def test_clear_then_read_new_with_a_seeded_file(self, tmp_path):
        script = "history -c\nhistory -n\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "legC2",
                                seed=["a", "b", "c"])
        assert _listing(bs["MEM"]) == []
        assert _listing(ps["MEM"]) == []


class TestProducersRespectHistsize:
    """The exit criterion's "respect memory limits" clause, per producer."""

    def test_read_respects_the_cap(self, tmp_path):
        script = "history -r $OTHER/big\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "capr",
                                env={"HISTSIZE": "4"},
                                named={"big": [f"B{i}" for i in range(1, 11)]})
        assert _listing(bs["MEM"]) == ["B7", "B8", "B9", "B10"]
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])

    def test_read_new_respects_the_cap(self, tmp_path):
        script = ('printf "'
                  + "\\n".join(f"X{i}" for i in range(1, 11))
                  + '\\n" >> "$HISTFILE"\nhistory -n\n' + OBSERVE + 'exit\n')
        (bs, _), (ps, _) = both(script, tmp_path, "capn", seed=["s1"],
                                env={"HISTSIZE": "4"})
        assert _listing(bs["MEM"]) == ["X7", "X8", "X9", "X10"]
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])

    def test_startup_load_respects_the_cap(self, tmp_path):
        (bs, _), (ps, _) = both(OBSERVE + "exit\n", tmp_path, "capload",
                                seed=[f"L{i}" for i in range(1, 11)],
                                env={"HISTSIZE": "4"})
        assert _listing(bs["MEM"]) == ["L7", "L8", "L9", "L10"]
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])


class TestSequenceParity:
    """State-machine sequences where psh must MATCH bash."""

    def test_clear_then_read(self, tmp_path):
        script = "history -c\nhistory -r\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "seqcr", seed=["a", "b"])
        assert _listing(ps["MEM"]) == _listing(bs["MEM"]) == ["a", "b"]

    def test_read_twice_appends_twice(self, tmp_path):
        """`-r` re-appends the whole file each time in BOTH shells (it does not
        de-duplicate), so the startup load's copy plus two `-r`s make three."""
        script = "history -r\nhistory -r\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "seqrr", seed=["a", "b"])
        assert _listing(ps["MEM"]) == _listing(bs["MEM"])
        assert _listing(ps["MEM"]) == ["a", "b"] * 3

    def test_read_new_twice_is_idempotent(self, tmp_path):
        script = "history -n\nhistory -n\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "seqnn", seed=["a", "b"])
        assert _listing(ps["MEM"]) == _listing(bs["MEM"]) == ["a", "b"]

    def test_external_truncate_then_read_new(self, tmp_path):
        script = ('printf "only1\\n" > "$HISTFILE"\nhistory -n\n'
                  + OBSERVE + "exit\n")
        (bs, _), (ps, _) = both(script, tmp_path, "sequnder",
                                seed=["a", "b", "c"])
        assert _listing(ps["MEM"]) == _listing(bs["MEM"]) == ["a", "b", "c"]

    def test_clear_then_record_still_persists(self, tmp_path):
        script = "true SCAFFOLDkeep\nhistory -c\ntrue AFTER\nexit\n"
        (_, bf), (_, pf) = both(script, tmp_path, "seqcrec", seed=["a"])
        assert "true AFTER" in bf and "true AFTER" in pf


class TestDeclaredDeviations:
    """psh deliberately differs; BOTH sides asserted so either moving fails.

    bash's `-a` writes the last N entries BY POSITION, so a read or a `-d`
    between recording and saving makes it write the wrong ones.
    """

    def test_read_new_then_append_bash_duplicates_psh_does_not(self, tmp_path):
        script = ('printf "EXT\\n" >> "$HISTFILE"\n'
                  'history -n\nhistory -a\nexit\n')
        (_, bf), (_, pf) = both(script, tmp_path, "devdup", seed=["a", "b"])
        assert bf.count("EXT") == 2, "bash re-appends the line it just read"
        assert pf.count("EXT") == 1, "psh does not duplicate it"

    def test_read_named_then_append_bash_keeps_psh_keeps_too(self, tmp_path):
        """The leak face. bash writes its tail (which here is the READ lines);
        psh writes the typed entry and never the other file's lines."""
        script = ('true SCAFFOLDx\ntrue typed1\n'
                  'history -r $OTHER/other\nhistory -a\nexit\n')
        (_, bf), (_, pf) = both(script, tmp_path, "devleak", seed=["a"],
                                named={"other": ["oth1", "oth2"]})
        assert "oth2" in bf, "bash leaks the other file's line into $HISTFILE"
        assert "oth1" not in pf and "oth2" not in pf, "psh does not leak"
        assert "true typed1" in pf, "psh keeps the typed command"

    def test_delete_then_append_bash_drops_the_pending_entry(self, tmp_path):
        """bash's counter is positional, so deleting an UNRELATED old entry
        silently drops a pending one from the save."""
        script = "true typed1\nhistory -d 1\nhistory -a\nexit\n"
        (_, bf), (_, pf) = both(script, tmp_path, "devdel",
                                seed=["old1", "old2"])
        assert "true typed1" not in bf, "bash drops it"
        assert "true typed1" in pf, "psh keeps it (v0.447 no-loss family)"

    def test_write_then_read_new_bash_rereads_psh_does_not(self, tmp_path):
        script = ('true typed1\nhistory -w\n'
                  'printf "EXT\\n" >> "$HISTFILE"\nhistory -n\n'
                  + OBSERVE + "exit\n")
        (bs, _), (ps, _) = both(script, tmp_path, "devw", seed=["a"])
        assert _listing(bs["MEM"]).count("true typed1") == 2, "bash re-reads it"
        assert _listing(ps["MEM"]).count("true typed1") == 1, "psh does not"

    def test_write_to_a_named_file_still_saves_the_session(self, tmp_path):
        """P5, now a PARITY row: psh used to lose the command entirely."""
        script = "true typed1\nhistory -w $OTHER/out\nexit\n"
        (_, bf), (_, pf) = both(script, tmp_path, "devwn", seed=["a"],
                                named={"out": []})
        assert "true typed1" in bf
        assert "true typed1" in pf


class TestClusteredFlagsRider:
    """LEDGER carry #25. bash parses clustered flags with getopt (`-d` takes an
    ARGUMENT) and applies them in a FIXED INTERNAL ORDER, not left to right."""

    def _rc(self, tmp_path, spec, name, seed=("S1", "S2", "S3")):
        script = f'history {spec} >/dev/null 2>&1; rc=$?\necho ===RC===\necho "$rc"\nexit\n'
        (bs, _), (ps, _) = both(script, tmp_path, name, seed=list(seed))
        return bs["RC"], ps["RC"]

    @pytest.mark.parametrize("spec,name", [
        ("-ps hello", "rcps"), ("-sp hello", "rcsp"), ("-ps", "rcpsbare"),
        ("-cw", "rccw"), ("-ca", "rcca"), ("-cd 1", "rccd"),
        ("-an", "rcan"), ("-rw", "rcrw"), ("-nr", "rcnr"),
        ("-pz x", "rcpz"), ("-zs x", "rczs"),
    ])
    def test_cluster_exit_status_matches_bash(self, tmp_path, spec, name):
        b, p = self._rc(tmp_path, spec, name)
        assert p == b, f"history {spec}: bash rc={b} psh rc={p}"

    def test_ps_stores_and_does_not_print(self, tmp_path):
        script = "true SCAFFOLDprev\nhistory -ps hello\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "psstore")
        assert _listing(bs["MEM"]) == ["hello"]
        assert _listing(ps["MEM"]) == ["hello"]

    def test_sp_is_identical_to_ps(self, tmp_path):
        """Flags are not applied left to right — the reversed cluster is the
        same in every observable."""
        a = both("history -ps hello\n" + OBSERVE + "exit\n", tmp_path, "ord1")
        b = both("history -sp hello\n" + OBSERVE + "exit\n", tmp_path, "ord2")
        assert _listing(a[0][0]["MEM"]) == _listing(b[0][0]["MEM"])   # bash
        assert _listing(a[1][0]["MEM"]) == _listing(b[1][0]["MEM"])   # psh
        assert _listing(a[1][0]["MEM"]) == _listing(a[0][0]["MEM"])

    def test_separate_option_words_parse_as_options(self, tmp_path):
        """`history -p -s hello` is `-p` AND `-s`, not `-p` with operands."""
        script = "history -p -s hello\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "sepwords")
        assert _listing(bs["MEM"]) == ["hello"]
        assert _listing(ps["MEM"]) == ["hello"]

    def test_double_dash_ends_options_for_store(self, tmp_path):
        script = "history -s -- x\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "dashdash")
        assert _listing(bs["MEM"]) == ["x"]
        assert _listing(ps["MEM"]) == ["x"]

    def test_d_consumes_the_cluster_remainder_as_its_argument(self, tmp_path):
        """`-da 1` is `-d a` — an invalid offset — not `-d` plus `-a`."""
        b, p = self._rc(tmp_path, "-da 1", "dargcluster")
        assert b == ["1"] and p == ["1"]

    def test_d_takes_the_next_word_when_the_cluster_ends(self, tmp_path):
        """`-ad 1` IS `-a` plus `-d 1`, so both run."""
        script = "history -ad 1\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "adnext",
                                seed=["S1", "S2", "S3"])
        assert _listing(bs["MEM"]) == ["S2", "S3"]
        assert _listing(ps["MEM"]) == ["S2", "S3"]

    def test_attached_delete_argument(self, tmp_path):
        script = "history -d1\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "dattached",
                                seed=["S1", "S2", "S3"])
        assert _listing(bs["MEM"]) == ["S2", "S3"]
        assert _listing(ps["MEM"]) == ["S2", "S3"]

    def test_clear_suppresses_delete(self, tmp_path):
        """`-cd 9` is rc 0 and silent although the offset is invalid, while a
        bare `-d 9` fails loudly — the clear wins and the delete never runs."""
        b_bad, p_bad = self._rc(tmp_path, "-cd 9", "cdbad")
        assert b_bad == ["0"] and p_bad == ["0"]
        b_ok, p_ok = self._rc(tmp_path, "-d 9", "dbad")
        assert b_ok == ["1"] and p_ok == ["1"]

    def test_store_short_circuits_the_file_op(self, tmp_path):
        """`-sw FILE STORED` stores the whole operand list as ONE entry and
        never writes the file."""
        script = "history -sw $OTHER/out STORED\n" + OBSERVE + "exit\n"
        (bs, _), (ps, _) = both(script, tmp_path, "sshort",
                                named={"out": []})
        assert _listing(bs["MEM"]) == _listing(ps["MEM"])
        assert len(_listing(ps["MEM"])) == 1
        assert _listing(ps["MEM"])[0].endswith(" STORED")
        assert (tmp_path / "out").read_text() == ""

    def test_invalid_letter_in_a_cluster_is_still_rejected(self, tmp_path):
        """MUST-HOLD control: accepting clusters must not accept junk."""
        for spec, name in (("-pz x", "junk1"), ("-zs x", "junk2")):
            b, p = self._rc(tmp_path, spec, name)
            assert b == ["2"] and p == ["2"]
