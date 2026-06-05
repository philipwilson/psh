def test_process_substitution_basic(psh_cmd):
    r = psh_cmd("cat <(printf 'hi')")
    assert r.stdout == "hi"
    assert r.returncode == 0


def test_process_substitution_out(psh_cmd):
    r = psh_cmd("echo hi > >(cat)")
    assert "hi" in r.stdout
    assert r.returncode == 0


def test_process_substitution_eof(psh_cmd):
    r = psh_cmd("cat <(printf 'x') | cat")
    assert r.stdout == "x"
    assert r.returncode == 0
