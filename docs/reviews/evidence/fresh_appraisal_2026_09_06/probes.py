"""Fresh appraisal probes; run from the repository root."""

import argparse
import errno
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import process_time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "harness"))

from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh  # noqa: E402

CASES = {
    "array_descending_index": "a=([5]=five [1]=one next); declare -p a",
    "array_append_explicit_index": "a=([5]=five); a+=([1]=one next); declare -p a",
    "array_self_reference": 'a=(old); a=(new "${a[0]}"); declare -p a',
    "integer_array_sequential": "i=0; declare -ia a; a=(i++ i++); declare -p a; echo i=$i",
    "integer_array_read_previous": "declare -ia a; a=(1 'a[0]+1'); declare -p a",
    "integer_array_append": "declare -ia a=(1); a+=([0]+=2); declare -p a",
    "arithmetic_scalar_promotion": "a=7; (( a[2]=9 )); declare -p a",
    "arithmetic_nounset_element": "set -u; a=(1); echo $((a[3])); echo survived",
    "arithmetic_nounset_assoc": "set -u; declare -A a=([yes]=1); echo $((a[no])); echo survived",
    "path_scope_hash": "f(){ local PATH=/usr/bin:/bin; hash ls; }; f; hash -t ls",
    "path_scope_dispatch": "mkdir a b; printf '#!/bin/sh\\necho A\\n' > a/probe; printf '#!/bin/sh\\necho B\\n' > b/probe; chmod +x a/probe b/probe; PATH=$PWD/a; f(){ local PATH=$PWD/b; probe; }; f; probe",
    "array_negative_initializer": "a=([5]=five [-1]=last next); declare -p a",
    "assoc_empty_initializer": 'declare -A a; a=([""]=bad); declare -p a; echo survived',
    "assoc_mixed_initializer": "declare -A a=([x]=one two three); declare -p a",
    "array_element_overwrite_visible": 'a=(old); a=([0]=new [1]="${a[0]}"); declare -p a',
    "errexit_function_test": "set -e; f(){ false; echo ok; }; f && echo done",
    "pipeline_status": "set -o pipefail; false | true; printf '%s\\n' \"$? ${PIPESTATUS[*]}\"",
    "redirect_order": "{ echo one; echo two >&2; } 2>&1 >out; cat out",
    "quoted_export": 'x="a b"; "export" y=$x; printf "<%s>\\n" "$y"',
    "expansion_export": 'x="a b"; cmd=export; $cmd y=$x; printf "<%s>\\n" "$y"',
    "command_export": 'x="a b"; command export y=$x; printf "<%s>\\n" "$y"',
    "quoted_alias": 'x="a b"; alias y=$x; alias y',
    "case_pattern_protection": 'x="*"; case abc in "$x") echo bad;; *) echo ok;; esac',
    "ifs_splice": 'set -- "a b" c; IFS=:; x=":x:"; printf "<%s>\\n" "pre$@"$x"post"',
    "arithmetic_short_circuit": 'x=0; echo $((0 && ++x)) $((1 || ++x)) $((1 ? 7 : ++x)); echo "$x"',
    "nested_case_substitution": 'printf "%s\\n" "$(case x in x) printf ok;; esac)"',
    "herestring_bytes": "read -r x <<< $'a\\tb'; printf '<%s>\\n' \"$x\"",
    "source_positionals": 'printf "set -- changed\\n" > s; set -- outer; . ./s inner; printf "%s\\n" "$@"',
    "return_trap_status": "trap 'echo return:$?' RETURN; f(){ return 7; }; f; echo status:$?",
    "readonly_array_no_value_side_effect": "a=(old); readonly a; a+=($(echo side >&2)); declare -p a",
    "cd_logical_parent": 'mkdir -p real/child logical; ln -s ../real/child logical/link; cd logical/link; cd ..; p=$(pwd -P); printf "%s %s\\n" "${PWD##*/}" "${p##*/}"',
    "cd_empty_cdpath": "mkdir child; CDPATH=:/nonexistent; cd child; echo done",
    "read_nan_timeout": "read -t nan x < /dev/null; echo status:$?",
    "read_infinite_timeout": "read -t inf x < /dev/null; echo status:$?",
    "read_huge_fd": "read -u 999999999999999999999 x; echo status:$?",
    "mapfile_readonly_consumption": 'printf "one\\ntwo\\n" > data; exec 3<data; readonly a; mapfile -u 3 a; read -u 3 line; printf "<%s>\\n" "$line"',
    "mapfile_assoc_target": "declare -A a=([x]=old); mapfile -t a <<< new; declare -p a",
}


def outcome(result):
    return {
        "kind": type(result).__name__,
        "comparable": is_comparable(result),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": getattr(result, "returncode", None),
    }


def emit(**record):
    print(json.dumps(record, ensure_ascii=True), flush=True)


def differential(name_filter=""):
    for name, source in CASES.items():
        if name_filter and name_filter not in name:
            continue
        outcomes = {}
        for label, runner in (("bash", run_bash), ("psh", run_psh)):
            result = runner(["--norc", "-c", source], timeout=5, env={"PSH_STRICT_ERRORS": "1"})
            outcomes[label] = outcome(result)
        equal = all(outcomes[k]["comparable"] for k in outcomes) and (
            outcomes["bash"]["stdout"],
            outcomes["bash"]["returncode"],
        ) == (outcomes["psh"]["stdout"], outcomes["psh"]["returncode"])
        emit(case=name, source=source, stdout_status_equal=equal, **outcomes)


def formatting():
    sources = [
        'v=X; v1=A; v2=B; printf "%s\\n" ${v}{1,2}',
        'v=X; v1=A; v2=B; f(){ printf "%s\\n" ${v}{1,2}; }; eval "$(declare -f f)"; f',
        'v=X; printf "%s\\n" "${v}tail"',
        "cat <<< $'a\\tb'",
        "cat <<'EOF'\n$x\nEOF\n",
    ]
    for source in sources:
        formatted = run_psh(["--format", "-c", source])
        if not is_comparable(formatted) or formatted.returncode:
            emit(case="format_failure", source=source, result=outcome(formatted))
            continue
        original = run_bash(["-c", source])
        reparsed = run_bash(["-c", formatted.stdout])
        psh_original = run_psh(["-c", source])
        psh_reparsed = run_psh(["-c", formatted.stdout])
        emit(
            case="format_roundtrip",
            source=source,
            formatted=formatted.stdout,
            bash_original=outcome(original),
            bash_formatted=outcome(reparsed),
            psh_original=outcome(psh_original),
            psh_formatted=outcome(psh_reparsed),
        )


def resources():
    from psh.io_redirect.process_sub import create_process_substitution
    from psh.scripting.input_sources import LazyFileInput

    real_pipe = os.pipe
    acquired = []

    def tracked_pipe():
        pair = real_pipe()
        acquired.extend(pair)
        return pair

    try:
        with (
            patch("psh.io_redirect.process_sub.os.pipe", side_effect=tracked_pipe),
            patch("psh.executor.fork_with_signal_window", side_effect=OSError(errno.EAGAIN, "injected fork failure")),
        ):
            try:
                create_process_substitution("true", "in", SimpleNamespace())
            except OSError:
                pass
        open_fds = []
        for fd in acquired:
            try:
                os.fstat(fd)
                open_fds.append(fd)
            except OSError:
                pass
        emit(case="procsub_fork_failure", acquired=len(acquired), leaked=len(open_fds))
    finally:
        for fd in acquired:
            try:
                os.close(fd)
            except OSError:
                pass

    with tempfile.TemporaryDirectory(prefix="psh-appraisal-") as directory:
        fifo_dir = Path(directory) / "substitution"
        fifo_dir.mkdir()
        with (
            patch("psh.io_redirect.process_sub.tempfile.mkdtemp", return_value=str(fifo_dir)),
            patch("psh.executor.fork_with_signal_window", side_effect=OSError(errno.EAGAIN, "injected fork failure")),
        ):
            try:
                create_process_substitution("true", "out", SimpleNamespace())
            except OSError:
                pass
        emit(case="procsub_write_fork_failure", fifo_left=(fifo_dir / "pipe").exists())

    source = LazyFileInput("unused")
    source._fd = 99
    with patch("psh.scripting.input_sources.os.read", side_effect=OSError(errno.EIO, "injected read failure")):
        try:
            result = source.read_line()
            emit(case="script_read_eio", result=result, raised=False)
        except OSError:
            emit(case="script_read_eio", raised=True)


def interactive():
    from psh.interactive.edit_buffer import EditBuffer
    from psh.interactive.key_decoder import KeyDecoder
    from psh.interactive.line_editor import LineEditor
    from psh.interactive.line_layout import visible_prompt_length
    from psh.interactive.tab_completion import CompletionEngine

    engine = CompletionEngine()
    for source in (r"cat some\ fi", 'cat "some fi', "cat 'some fi"):
        start = engine.find_word_start(source, len(source))
        emit(case="completion_boundary", source=source, start=start, fragment=source[start:])

    source = 'printf "%s\\n" "'
    buffer = EditBuffer()
    buffer.replace_all(source)
    editor = SimpleNamespace(edit_buffer=buffer, completion_engine=engine, _redraw=lambda: None)
    LineEditor._apply_completion(editor, "report$HOME.txt", len(source))
    command = buffer.text + '"'
    emit(
        case="quoted_completion",
        generated=command,
        result=outcome(run_psh(["-c", command], env={"HOME": "/review-home"})),
    )
    for prompt in ("abc", "\u754c", "e\u0301"):
        emit(case="prompt_columns", prompt=prompt, measured=visible_prompt_length(prompt))
    decoder = KeyDecoder(fd=99)
    with patch("psh.interactive.key_decoder.os.read", side_effect=[b"\xc3", b"\xa9", b""]):
        events = [decoder.read_key() for _ in range(3)]
    emit(case="split_utf8_input", events=[repr(event) for event in events])


def analysis():
    from psh.lexer import tokenize
    from psh.parser import parse
    from psh.visitor.metrics_visitor import MetricsVisitor

    for source in ('eval "$payload"', 'X=1 eval "$payload"', 'command eval "$payload"'):
        emit(case="security_analysis", source=source, result=outcome(run_psh(["--security", "-c", source])))
    for source in ("echo $(true)", "echo ${x:-$(true)}", "cat <(true)"):
        visitor = MetricsVisitor()
        visitor.visit(parse(tokenize(source)))
        emit(case="metrics_analysis", source=source, result=visitor.get_report())


def performance():
    from psh.lexer import tokenize

    for size in (10000, 20000, 40000, 80000, 160000):
        source = "echo " + "x" * size
        samples = []
        for _ in range(3):
            start = process_time()
            tokenize(source)
            samples.append(process_time() - start)
        emit(case="long_literal_lexing", characters=size, median_cpu_seconds=median(samples), samples=samples)


def main():
    sections = {
        "differential": differential,
        "formatting": formatting,
        "resources": resources,
        "interactive": interactive,
        "analysis": analysis,
        "performance": performance,
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("section", choices=["all", *sections], nargs="?", default="all")
    parser.add_argument("--filter", default="")
    args = parser.parse_args()
    emit(oracle=resolve_bash().__dict__, python=sys.version, platform=platform.platform())
    for name, run in sections.items():
        if args.section in ("all", name):
            if name == "differential":
                differential(args.filter)
            else:
                run()


if __name__ == "__main__":
    main()
