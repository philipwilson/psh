#!/opt/homebrew/bin/bash
# Q2-resurrection: independent sweeps over the worktree at ae871a16 (v0.773.0).
# Each section is an INDEPENDENT instrument (grep/find census), deliberately not
# reusing the committed guards' own scanner code (instrument-mirror discipline).
# Axis: REGRESSION vs the slot-close claims (the deleted-boundary record).
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q2/wt

section() { echo; echo "######## $1 ########"; }

section "S0: worktree identity"
git -C "$WT" rev-parse HEAD
grep -n "__version__" "$WT/psh/version.py" | head -1

section "S1: HIGH-1 raw spawns in oracle-bearing trees (conformance/ + harness/)"
echo "--- subprocess/os spawn calls under tests/conformance + tests/harness ---"
grep -rn "subprocess\.\(run\|Popen\|call\|check_output\|check_call\|getoutput\|getstatusoutput\)\|os\.system(\|os\.popen(" \
  "$WT/tests/conformance" "$WT/tests/harness" --include="*.py" || echo "NONE"
echo "--- pexpect/pty spawns under tests/conformance + tests/harness ---"
grep -rn "pexpect\.\(spawn\|spawnu\|run\|runu\)(\|pty\.\(spawn\|fork\|openpty\)(" \
  "$WT/tests/conformance" "$WT/tests/harness" --include="*.py" || echo "NONE"
echo "--- shell_oracle-importing modules elsewhere that also mention subprocess. ---"
grep -rln "shell_oracle" "$WT/tests" --include="*.py" | grep -v "tests/conformance\|tests/harness" | while read -r f; do
  if grep -qn "subprocess\.\(run\|Popen\|call\|check_output\|check_call\)(\|os\.system(\|os\.popen(\|pexpect\.spawn" "$f"; then
    echo "SPAWNER: ${f#"$WT"/}"
    grep -n "subprocess\.\(run\|Popen\|call\|check_output\|check_call\)(\|os\.system(\|os\.popen(\|pexpect\.spawn" "$f" | head -5
  fi
done

section "S2: HIGH-2 per-visitor child enumeration (def visit( overrides in psh/visitor)"
grep -rn "    def visit(self" "$WT/psh/visitor" --include="*.py" || echo "NONE"
echo "--- generic_visit overrides in psh/visitor ---"
grep -rn "def generic_visit" "$WT/psh/visitor" --include="*.py" || echo "NONE (base only expected)"

section "S3: HIGH-5 facade wrappers"
echo "--- _ParserWrapper anywhere ---"
grep -rn "_ParserWrapper" "$WT/psh" "$WT/tests" "$WT/tools" --include="*.py" || echo "NONE"
echo "--- tests/support/utils.py ---"
ls "$WT/tests/support/utils.py" 2>&1 || true
echo "--- ParseInputs( construction sites in psh (sanctioned set = 4 + defn module) ---"
grep -rln "ParseInputs(" "$WT/psh" --include="*.py"

section "S4: MEDIUM-3 heredoc detection outside the lexer-event authority"
echo "--- completeness oracle asks the lexer ---"
grep -n "_lexer_pending_heredocs" "$WT/psh/parser/session.py"
echo "--- session.py must NOT use the text scanner for completeness ---"
grep -n "open_heredoc_specs\|scan_line_heredoc_markers\|HEREDOC_MARKER_RE" "$WT/psh/parser/session.py" || echo "NONE (good)"
echo "--- '<<'-matching regexes compiled outside utils/heredoc_detection.py ---"
grep -rn "re\.compile(.*<<" "$WT/psh" --include="*.py" | grep -v "utils/heredoc_detection.py" || echo "NONE"
echo "--- text-scanner consumer modules (compare to declared list in heredoc_detection.py docstring) ---"
grep -rln "scan_line_heredoc_markers\|open_heredoc_specs\|contains_heredoc\|HEREDOC_MARKER_RE\|has_unclosed_heredoc" \
  "$WT/psh" --include="*.py"

section "S5: arg_types/quote_types parallel metadata"
grep -rn "arg_types\|quote_types" "$WT/psh" --include="*.py" || echo "NONE"

section "S6: retired members - _file_synced_len / _pushback / with_redirections"
echo "--- _file_synced_len in psh ---"
grep -rn "_file_synced_len" "$WT/psh" --include="*.py" || echo "NONE"
echo "--- _pushback in psh (non-comment lines only) ---"
grep -rn "_pushback" "$WT/psh" --include="*.py" | grep -v ":[0-9]*: *#" || echo "NONE (comment-only or absent)"
echo "--- with_redirections CALL sites (definition excluded) ---"
grep -rn "\.with_redirections(" "$WT/psh" "$WT/tests" "$WT/tools" --include="*.py" || echo "NONE"
echo "--- with_redirections definition still present (dead API) ---"
grep -n "def with_redirections" "$WT/psh/io_redirect/manager.py"

section "S7: broad except at the closed sites (subscript.py, param_parser.py, manager.py, arithmetic/evaluator.py)"
for f in expansion/subscript.py expansion/param_parser.py expansion/manager.py expansion/arithmetic/evaluator.py; do
  echo "--- psh/$f ---"
  grep -n "except Exception\|except BaseException\|except *:" "$WT/psh/$f" || echo "CLEAN"
done

section "S8: OperandValue scalar projection census"
echo "--- .as_scalar( call sites in psh ---"
grep -rn "\.as_scalar(" "$WT/psh" --include="*.py"
echo "--- OperandResult (retired str-subclass) in psh ---"
grep -rn "OperandResult" "$WT/psh" --include="*.py" || echo "NONE"
echo "--- ExpandedField( constructor sites by module (two named producers expected) ---"
grep -rln "ExpandedField(" "$WT/psh" --include="*.py"

section "S9: env materialization + command resolution"
echo "--- direct os.environ writes in psh ---"
grep -rn "os\.environ\[[^]]*\] *=\|os\.environ\.update\|os\.environ\.pop\|os\.environ\.setdefault\|del os\.environ" \
  "$WT/psh" --include="*.py" || echo "NONE"
echo "--- _materialize_env_name definition + callers ---"
grep -rn "_materialize_env_name" "$WT/psh" --include="*.py"
echo "--- get_function( reads in psh/executor outside resolver/resolution machinery ---"
grep -rn "get_function(" "$WT/psh/executor" --include="*.py" | grep -v "command_resolver.py\|command_resolution.py" || echo "NONE"
echo "--- POSIX_SPECIAL_BUILTINS reads in psh/executor outside resolution machinery ---"
grep -rn "POSIX_SPECIAL_BUILTINS" "$WT/psh/executor" --include="*.py" | grep -v "command_resolver.py\|command_resolution.py" || echo "NONE"
echo "--- PATH-walk (os.access X_OK) sites in psh ---"
grep -rn "X_OK" "$WT/psh" --include="*.py" || echo "NONE"

section "S10: retired heredoc plumbing identifiers (independent of guard)"
grep -rn "heredoc_key\|_close_heredocs_matching\|HeredocProcessor\|populate_heredocs\|open_heredoc_delimiters" \
  "$WT/psh" --include="*.py" || echo "NONE"

echo; echo "######## SWEEPS COMPLETE ########"
