def test_merge_streams(psh_cmd):
    r = psh_cmd("{ printf out; printf err 1>&2; } 2>&1")
    assert "out" in r.stdout
    assert "err" in r.stdout


def test_dup_stdin(psh_cmd):
    r = psh_cmd("printf 'hi' | { exec 3<&0; cat <&3; }")
    assert r.stdout == "hi"


def test_close_fd(psh_cmd):
    r = psh_cmd("{ exec 3<&-; cat <&3; }")
    assert r.returncode != 0


def test_here_string_quotes(psh_cmd):
    r = psh_cmd("v=1; cat <<< '$v'")
    assert r.stdout.strip() == "$v"
    r = psh_cmd('v=1; cat <<< "$v"')
    assert r.stdout.strip() == "1"
