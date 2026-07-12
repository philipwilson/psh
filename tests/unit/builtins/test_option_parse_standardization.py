"""T3a/T3d: option-parse standardization for the parse_flags-migrated builtins.

`read`, `mapfile`, `wait`, `trap`, `ulimit` and `cd` now share the one
getopt-style walker (`Builtin.parse_flags` / `parse_flags_ordered`), so their
invalid-option and missing-value diagnostics carry bash's shape:

  * error line   -> `<name>: -x: invalid option`  (location-prefixed)
  * usage line   -> UNPREFIXED `<name>: usage: <synopsis>`  (bash builtin_usage)
  * exit status  -> 2 for a usage error, 1 for a bad option VALUE

These are pinned in a subprocess because the diagnostics are multi-line stderr
with the `psh: line N:` location prefix (the golden harness compares only
stdout/rc). Each test notes the pre-fix behavior it is red-on-base against.
"""
import os
import subprocess
import sys


def _run(script, stdin="", cwd=None):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        input=stdin, capture_output=True, text=True, cwd=cwd)


# ----- wait: exact-word loop -> shared cluster walk -----------------------

class TestWaitOptions:
    def test_invalid_option_is_usage_error(self):
        # Red-on-base: `wait -x` used to be rc 127 "wait: -x: not a valid
        # process id"; bash reports an invalid option (rc 2) + usage.
        r = _run('wait -x')
        assert r.returncode == 2
        assert 'wait: -x: invalid option' in r.stderr
        assert 'wait: usage: wait [-fn] [-p var] [id ...]' in r.stderr

    def test_missing_p_value_prints_usage(self):
        # Red-on-base: `wait -p` printed the error but NO usage line.
        r = _run('wait -p')
        assert r.returncode == 2
        assert 'wait: -p: option requires an argument' in r.stderr
        assert 'wait: usage:' in r.stderr

    def test_clusters_n_and_p(self):
        # Red-on-base: the exact-word loop rejected the cluster `-np`.
        r = _run('sleep 0.1 & wait -np V; echo "V=$V"')
        assert r.returncode == 0
        assert r.stdout.startswith('V=')
        assert r.stdout.strip()[2:].isdigit()

    def test_dash_f_accepted(self):
        # Red-on-base: `-f` was "not a valid process id"; bash accepts it.
        r = _run('sleep 0.05 & wait -f $!; echo rc=$?')
        assert r.returncode == 0
        assert r.stdout.strip() == 'rc=0'
        assert r.stderr == ''


# ----- read: hand loop -> shared walk (usage line was missing) ------------

class TestReadOptions:
    def test_invalid_option_prints_usage(self):
        # Red-on-base: `read -Z` printed the error but NO usage line.
        r = _run('read -Z', stdin='x\n')
        assert r.returncode == 2
        assert 'read: -Z: invalid option' in r.stderr
        assert 'read: usage:' in r.stderr

    def test_missing_value_prints_usage(self):
        r = _run('read -n', stdin='x\n')
        assert r.returncode == 2
        assert 'read: -n: option requires an argument' in r.stderr
        assert 'read: usage:' in r.stderr

    def test_bad_value_is_rc1_not_rc2(self):
        # Preserved: a bad option VALUE stays status 1 (bash), not a usage 2.
        r = _run('read -t abc x', stdin='v\n')
        assert r.returncode == 1
        assert 'read: abc: invalid timeout specification' in r.stderr


# ----- mapfile: hand loop -> shared walk ----------------------------------

class TestMapfileOptions:
    def test_invalid_option_prints_usage(self):
        # Red-on-base: `mapfile -Z` printed the error but NO usage line.
        r = _run('mapfile -Z arr', stdin='a\nb\n')
        assert r.returncode == 2
        assert 'mapfile: -Z: invalid option' in r.stderr
        assert 'mapfile: usage:' in r.stderr

    def test_callback_still_unsupported(self):
        # Preserved divergence: psh does not implement -C/-c callbacks.
        r = _run("mapfile -C 'echo cb' arr", stdin='a\n')
        assert r.returncode == 2
        assert 'callback option not supported' in r.stderr

    def test_bad_value_is_rc1(self):
        r = _run('mapfile -n xx arr', stdin='a\n')
        assert r.returncode == 1
        assert 'mapfile: xx: invalid line count' in r.stderr


# ----- ulimit: hand loop -> shared walk; usage line now UNPREFIXED --------

class TestUlimitOptions:
    def test_invalid_option_usage_line_is_unprefixed(self):
        # Red-on-base: the usage line went through the location-prefixed
        # error() channel (`psh: line N: ulimit: usage: ...`); bash's
        # builtin_usage line is UNPREFIXED.
        r = _run('ulimit -Z')
        assert r.returncode == 2
        assert 'ulimit: -Z: invalid option' in r.stderr
        usage_lines = [ln for ln in r.stderr.splitlines()
                       if 'usage:' in ln]
        assert usage_lines, r.stderr
        assert usage_lines[0].startswith('ulimit: usage: ulimit ')

    def test_pipe_size_still_honest_error(self):
        # Preserved divergence: -p has no portable API.
        r = _run('ulimit -p')
        assert r.returncode == 2
        assert 'pipe size' in r.stderr and 'not supported' in r.stderr


# ----- cd: reports the offending CHAR, not the whole cluster --------------

class TestCdOptions:
    def test_invalid_in_cluster_reports_char(self):
        # Red-on-base: `cd -Lx` reported the whole cluster "-Lx"; bash reports
        # the offending char "-x".
        r = _run('cd -Lx /tmp')
        assert r.returncode == 2
        assert 'cd: -x: invalid option' in r.stderr
        assert '-Lx' not in r.stderr

    def test_lp_last_wins(self, tmp_path):
        # -LP is physical (last=P), -PL logical (last=L). Needs a symlink.
        real = tmp_path / 'real'
        real.mkdir()
        link = tmp_path / 'link'
        link.symlink_to(real)
        physical = os.path.realpath(str(real))
        r_lp = _run(f'cd -LP {link}; pwd')
        assert r_lp.stdout.strip() == physical
        r_pl = _run(f'cd -PL {link}; pwd')
        assert r_pl.stdout.strip() == str(link)


# ----- exec/hash: collateral bash-match from the shared usage-on-missing ---

class TestExecHashMissingValueUsage:
    def test_exec_missing_a_prints_usage(self):
        # Red-on-base: `exec -a` (missing value) printed no usage line.
        r = _run('exec -a')
        assert 'exec: -a: option requires an argument' in r.stderr
        assert 'exec: usage:' in r.stderr

    def test_hash_missing_p_prints_usage(self):
        # Red-on-base: `hash -p` (missing value) printed no usage line.
        r = _run('hash -p')
        assert r.returncode == 2
        assert 'hash: -p: option requires an argument' in r.stderr
        assert 'hash: usage:' in r.stderr


# ----- source: third PATH walk -> resolver.search_path(mode=R_OK) ---------

class TestSourcePathWalk:
    def test_empty_path_component_is_cwd(self, tmp_path):
        # Red-on-base: source SKIPPED empty PATH components, so `PATH=":/dir"`
        # wrongly preferred /dir over the cwd. bash (and search_path) maps an
        # empty component to the cwd and searches it IN ORDER.
        d = tmp_path / 'dir'
        d.mkdir()
        (d / 'scr.sh').write_text('echo FROM_DIR\n')
        (tmp_path / 'scr.sh').write_text('echo FROM_CWD\n')
        r = _run(f'PATH=":{d}" source scr.sh', cwd=str(tmp_path))
        assert r.returncode == 0
        assert r.stdout.strip() == 'FROM_CWD'

    def test_slashless_name_searches_path(self, tmp_path):
        # Preserved: a slash-less name earlier on PATH wins over the cwd.
        d = tmp_path / 'dir'
        d.mkdir()
        (d / 'scr.sh').write_text('echo FROM_DIR\n')
        r = _run(f'PATH="{d}" source scr.sh', cwd=str(tmp_path))
        assert r.returncode == 0
        assert r.stdout.strip() == 'FROM_DIR'
