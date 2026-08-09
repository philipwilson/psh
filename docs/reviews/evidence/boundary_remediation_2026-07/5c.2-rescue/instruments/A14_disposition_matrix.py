#!/usr/bin/env python3
"""A14 — the 60-row transaction mapping + disposition matrix, GENERATED.

The mapping below is my judgement (one entry per census row); the TABLE and
every COUNT are derived from it by this script, never hand-tallied (4a.1 §Rules,
discharge audit). The script also asserts the mapping covers the census exactly
— a row I forgot, or invented, fails loudly here rather than in the report.

Disposition vocabulary:
  DECOMPOSE       - proposed for the executed set
  JUSTIFIED-KEEP  - length is the honest shape; reason must be specific
  POINTER         - a nested def whose body is already dispositioned at its
                    parent row (never two dispositions for one body)

Usage: A14_disposition_matrix.py <census.json> <anatomy-not-needed>
"""
import json
import sys
from collections import Counter
from pathlib import Path

# (file, qualname): (transaction, shape, disposition, reason)
M = {
 # ---- state construction
 ("psh/core/state.py", "ShellState.__init__"): ("state construction", "FIELD-INIT", "JUSTIFIED-KEEP", "94 exec lines carrying 191 comment lines of env/locale/option ordering provenance; the ordering IS the contract and grouping hides it"),
 ("psh/core/state.py", "ShellState.clone_for_child"): ("state construction", "FIELD-INIT", "JUSTIFIED-KEEP", "41 exec lines; correctness property is EXHAUSTIVENESS over __init__'s field set, pinned by test_state_clone_completeness.py — grouping makes a missing field harder to spot"),
 ("psh/core/scope.py", "ScopeManager.set_variable"): ("state construction", "DISPATCH-HUB", "JUSTIFIED-KEEP", "86 exec; five early-return write routes whose ORDER is the masking semantics (nameref/temp-env/dynamic-special); pinned by the variable-truth guard"),
 ("psh/core/scope.py", "ScopeManager.create_local"): ("state construction", "SEQUENCE", "JUSTIFIED-KEEP", "46 exec under 67 comment lines; four readonly rejections are scattered but each cites a distinct bash rule — consolidation is a behaviour-risk edit, not a move"),
 ("psh/builtins/function_support.py", "DeclareBuiltin._declare_bare_name"): ("state construction", "DISPATCH-HUB", "JUSTIFIED-KEEP", "72 exec; two array arms are structurally parallel but differ in ArrayKind/container/slot-key — parameterising is an edit, not a move"),
 ("psh/builtins/shell_state.py", "LocalBuiltin._declare_one_local"): ("state construction", "DISPATCH-HUB", "JUSTIFIED-KEEP", "61 exec; arms are one-liners already, the length is the six-way declaration cross-product"),
 ("psh/executor/array.py", "ArrayOperationExecutor.execute_array_element_assignment"): ("state construction", "SEQUENCE", "JUSTIFIED-KEEP", "61 exec; clean seams exist but sit on the array write path (1.3b-adjacent state), value does not clear the risk bar this slot"),
 ("psh/executor/function.py", "FunctionOperationExecutor._function_frame"): ("state construction", "FIELD-INIT", "JUSTIFIED-KEEP", "35 exec; docstring states the invariant — save/restore pairs must stay ADJACENT and countable; splitting defeats the one property enforced"),
 ("psh/invocation.py", "parse_invocation"): ("state construction", "DISPATCH-HUB", "DECOMPOSE", "93 exec, PURE (no Shell, never prints/exits), guarded by test_invocation_argv_guard.py; three tail InvocationConfig(...) constructions share ~10 kwargs — the forget-a-field-in-one-of-three defect class"),

 # ---- command preparation / dispatch
 ("psh/executor/command.py", "CommandExecutor._run_command"): ("command prep/dispatch", "SEQUENCE", "JUSTIFIED-KEEP", "NAMED GROWER. 92 exec under 138 comment lines; phase1/resolve/phase2 ordering is the authority-timing contract (#20 H10) pinned by test_resolution_timing_ratchet_3_4.py; 1.3b child-status territory"),
 ("psh/executor/strategies.py", "ExternalExecutionStrategy.execute"): ("command prep/dispatch", "SEQUENCE", "JUSTIFIED-KEEP", "79 exec; fork + os._exit + pgid + terminal transfer in one body; integration-weighted coverage only — worst fast-feedback net in the census"),
 ("psh/executor/command_assignments.py", "CommandAssignments.commit_prefix"): ("command prep/dispatch", "SEQUENCE", "JUSTIFIED-KEEP", "63 exec under 29 doc + 38 comment; the _pop_staging_scope ordering is explicitly load-bearing (an install exception must not be masked by an ownership error)"),
 ("psh/executor/function.py", "FunctionOperationExecutor.execute_function_call"): ("command prep/dispatch", "SEQUENCE", "JUSTIFIED-KEEP", "40 exec; length is an except-ladder whose CLAUSE ORDER is the semantics (FunctionReturn inside the frame, Loop* outside); a terminal-handler ledger key lives here"),
 ("psh/parser/combinators/commands/simple.py", "SimpleCommandMixin._build_simple_command_parser"): ("command prep/dispatch", "CASE-TABLE", "JUSTIFIED-KEEP", "88 exec; builder whose body is one nested closure — the grammar production is the unit"),
 ("psh/parser/combinators/commands/simple.py", "SimpleCommandMixin._build_simple_command_parser.parse_simple_command"): ("command prep/dispatch", "CASE-TABLE", "POINTER", "nested inside _build_simple_command_parser — dispositioned at the parent"),
 ("psh/parser/combinators/commands/pipelines.py", "PipelineMixin._build_pipeline_parser"): ("command prep/dispatch", "CASE-TABLE", "JUSTIFIED-KEEP", "59 exec; same builder+closure shape; the time-prefix and |-tail are grammar clauses, not responsibilities"),

 # ---- job lifecycle
 ("psh/executor/pipeline.py", "PipelineExecutor._execute_pipeline"): ("job lifecycle", "SEQUENCE", "JUSTIFIED-KEEP", "95 exec under 89 comment; fork + SIGTTOU/SIGTTIN + pgid + sync pipes + fd setup in one transaction; must-not-flip names every one of these"),
 ("psh/executor/process_launcher.py", "ProcessLauncher._child_setup_and_exec"): ("job lifecycle", "SEQUENCE", "JUSTIFIED-KEEP", "66 exec; child-side body ending in os._exit inside finally — the fork discipline must-not-flip; terminal-handler ledger key at :374"),
 ("psh/executor/job_control.py", "JobManager.wait_for_job"): ("job lifecycle", "SEQUENCE", "JUSTIFIED-KEEP", "55 exec; waitpid(-pgid) EINTR/ECHILD policy; CR-D1 lives in this territory"),
 ("psh/builtins/job_control.py", "WaitBuiltin._wait_for_specific"): ("job lifecycle", "DISPATCH-HUB", "JUSTIFIED-KEEP", "80 exec; five-way pid resolution ladder over reap-registry state; CR-D1-adjacent"),
 ("psh/executor/subshell.py", "SubshellExecutor._execute_foreground_subshell"): ("job lifecycle", "SEQUENCE", "JUSTIFIED-KEEP", "47 exec; fork + terminal transfer + raw os.write(2,...) post-fork; highest-risk row in the census"),

 # ---- history expansion
 ("psh/interactive/history_expansion.py", "HistoryExpander.expand_history"): ("history expansion", "ALGORITHM", "JUSTIFIED-KEEP", "101 exec — one of only TWO genuine >=100-exec rows. Single-pass scanner over six coupled cursor variables; the forward suppression feed REPLACED three backward rescans, so splitting reintroduces the state-passing that design deleted"),
 ("psh/builtins/shell_state.py", "HistoryBuiltin._dispatch_options"): ("history expansion", "DISPATCH-HUB", "JUSTIFIED-KEEP", "42 exec; the flag ORDER is a single indivisible bash-measured fact (4B.3's own subject), pinned by the M8 locks"),

 # ---- input execution
 ("psh/builtins/read_builtin.py", "ReadBuiltin.execute"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "PROPOSED 7th GROWER, ARGUED OUT. 81 exec under 93 comment; 5C.1's +11 was -3 exec/+14 comment. Real seams exist but the InputCursor contract (4B.3/4B.4) is pinned to this body"),
 ("psh/parser/session.py", "ParseSession.feed"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "57 exec; the phase ORDER is the specification (I3 session guards); extraction turns ordered fall-through into a handled/not-handled return protocol"),
 ("psh/interactive/repl_loop.py", "REPLLoop.run"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "47 exec under 58 comment; SIGCHLD + stopped-job notices + terminal reads; PTY-test cost, no unit net"),
 ("psh/scripting/source_processor.py", "SourceProcessor._execute_buffered_command"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "40 exec; the function IS the error model — clause order is the content; terminal-handler ledger key lives here"),
 ("psh/expansion/command_sub.py", "CommandSubstitutionExecutor.execute"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "64 exec; four resource sentinels whose only correctness property is that ONE finally sees all four; fork + SIGCHLD swap"),
 ("psh/executor/control_flow.py", "ControlFlowExecutor.execute_select"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "64 exec; interactive read loop, PTY-adjacent coverage cost"),
 ("psh/executor/control_flow.py", "ControlFlowExecutor.execute_case"): ("input execution", "SEQUENCE", "JUSTIFIED-KEEP", "46 exec; DEBUG-trap + legacy-AST fallback provenance dominates the length"),
 ("psh/scripting/input_preprocessing.py", "process_line_continuations"): ("input execution", "ALGORITHM", "JUSTIFIED-KEEP", "40 exec under a 44-line bash-measured docstring; context rules ALREADY extracted to five helpers — what remains is the irreducible cursor loop"),

 # ---- redirect acquisition
 ("psh/io_redirect/file_redirect.py", "FileRedirector.apply_permanent_redirections"): ("redirect acquisition", "SEQUENCE", "JUSTIFIED-KEEP", "58 exec; exec-path fd transaction with lease acquire/rollback (4A.1 territory); terminal-handler ledger keys at :1327"),
 ("psh/io_redirect/file_redirect.py", "FileRedirector.apply_var_fd_redirect"): ("redirect acquisition", "DISPATCH-HUB", "DECOMPOSE", "NAMED GROWER. 50 exec; the allocate-and-record tail (F_DUPFD>=10 + set_variable + scope_fd) repeats VERBATIM in three arms — that triplication IS the named-fd allocation contract, and it has no single owner"),
 ("psh/parser/combinators/commands/redirections.py", "RedirectionMixin._parse_redirection"): ("redirect acquisition", "DISPATCH-HUB", "JUSTIFIED-KEEP", "81 exec, parse-only (no fd work); the heredoc arm is a real seam but heredoc parse state is 2.3/S2 pinned territory"),

 # ---- grammar construction (OTHER)
 ("psh/parser/combinators/control_structures/conditionals.py", "ConditionalParserMixin._build_case_statement"): ("grammar construction", "CASE-TABLE", "JUSTIFIED-KEEP", "87 exec; one grammar production; _parse_case_item is a real seam but parser-combinator shape change is RESUMABLE-PARSER successor territory"),
 ("psh/parser/combinators/control_structures/conditionals.py", "ConditionalParserMixin._build_case_statement.parse_case_statement"): ("grammar construction", "CASE-TABLE", "POINTER", "nested inside _build_case_statement — dispositioned at the parent"),
 ("psh/parser/combinators/control_structures/conditionals.py", "ConditionalParserMixin._build_if_statement"): ("grammar construction", "CASE-TABLE", "JUSTIFIED-KEEP", "100 exec — the OTHER genuine >=100-exec row. Already internally decomposed into two nested productions; if/elif/else/fi are four grammar clauses that cannot collapse"),
 ("psh/parser/combinators/control_structures/loops.py", "LoopParserMixin._build_c_style_for_loop"): ("grammar construction", "CASE-TABLE", "JUSTIFIED-KEEP", "85 exec; same builder+closure grammar shape"),
 ("psh/parser/combinators/control_structures/loops.py", "LoopParserMixin._build_c_style_for_loop.parse_c_style_for"): ("grammar construction", "CASE-TABLE", "POINTER", "nested inside _build_c_style_for_loop — dispositioned at the parent"),

 # ---- lexical scanning (OTHER)
 ("psh/lexer/recognizers/literal.py", "LiteralRecognizer._collect_literal_value"): ("lexical scanning", "ALGORITHM", "JUSTIFIED-KEEP", "88 exec; every branch mutates the same three trackers and the branch ORDER is the semantics; separable sub-decisions already extracted"),
 ("psh/lexer/pure_helpers.py", "handle_ansi_c_escape"): ("lexical scanning", "CASE-TABLE", "JUSTIFIED-KEEP", "82 exec; the length is the escape alphabet's length; arms differ in failure text and new_pos on the empty case"),
 ("psh/lexer/keyword_normalizer.py", "KeywordNormalizer.normalize"): ("lexical scanning", "DISPATCH-HUB", "JUSTIFIED-KEEP", "50 exec; golden-fixture pinned reclassification pass, arms carry per-arm bash rationale"),
 ("psh/lexer/token_stream.py", "TokenStream.collect_arithmetic_expression"): ("lexical scanning", "ALGORITHM", "JUSTIFIED-KEEP", "41 exec; mutates the shared token stream in place (_split_double_rparen) — extraction would move a splice away from its depth accounting"),
 ("psh/lexer/quote_parser.py", "UnifiedQuoteParser.parse_quoted_string"): ("lexical scanning", "ALGORITHM", "JUSTIFIED-KEEP", "65 exec; weakest DIRECT test coverage in the census (no test names it) — refactoring the least-netted row is the wrong trade"),
 ("psh/lexer/cmdsub_scanner.py", "find_command_substitution_end"): ("lexical scanning", "OTHER", "JUSTIFIED-KEEP", "MEASUREMENT ARTEFACT: a ONE-STATEMENT body under a ~96-line maintenance contract. The decomposition this row asks for already happened (_CmdSubScanner); removing lines here deletes the contract, not complexity"),
 ("psh/lexer/command_position.py", "advance_lexical_state"): ("lexical scanning", "SEQUENCE", "JUSTIFIED-KEEP", "42 exec; three labelled sections with a documented cross-section data dependency; the docstring explicitly FORBIDS the tempting larger refactor"),
 ("psh/lexer/recognizers/operator.py", "OperatorRecognizer.recognize"): ("lexical scanning", "DISPATCH-HUB", "DECOMPOSE", "59 exec, PURE, zero deferred imports, strong direct coverage (5 lexer suites); the ~35-line VETO block (extglob !, {} reserved-word rules) is unrelated to longest-match and has its own bash provenance"),

 # ---- expansion / pattern (OTHER)
 ("psh/expansion/variable.py", "VariableExpander._expand_array_parameter"): ("expansion/pattern", "DISPATCH-HUB", "JUSTIFIED-KEEP", "63 exec; the real decomposition is a UNIFIED operator table shared with _apply_operator — a cross-row design, too big for this slot's zero-delta budget"),
 ("psh/expansion/operators.py", "OperatorOpsMixin._apply_operator"): ("expansion/pattern", "DISPATCH-HUB", "JUSTIFIED-KEEP", "73 exec; scalar twin of the row above — same reason, same cross-row seam"),
 ("psh/expansion/glob.py", "GlobExpander._expand_globstar"): ("expansion/pattern", "ALGORITHM", "JUSTIFIED-KEEP", "78 exec; the (text, still-verbatim) tuple invariant is only meaningful relative to position in the component walk — it cannot cross a function boundary intact"),
 ("psh/expansion/pattern_engine.py", "_BashMatcher._match"): ("expansion/pattern", "ALGORITHM", "JUSTIFIED-KEEP", "83 exec; a deliberate glibc sm_loop.c port whose control flow IS the semantics being reproduced; comments pin per-arm glibc provenance"),
 ("psh/expansion/extglob.py", "_convert_pattern"): ("expansion/pattern", "ALGORITHM", "JUSTIFIED-KEEP", "49 exec; production-dead — a PERMANENT reference oracle for the differential against pattern_engine; refactoring an oracle destroys its independence"),
 ("psh/builtins/environment.py", "UnsetBuiltin._unset_array_element"): ("expansion/pattern", "DISPATCH-HUB", "JUSTIFIED-KEEP", "60 exec; array-unset shape routing with nameref provenance; seams exist but sit on the array mutation path"),

 # ---- builtin option / operand handling (OTHER)
 ("psh/builtins/environment.py", "ExportBuiltin.execute_in_context"): ("builtin option/operand", "SEQUENCE", "JUSTIFIED-KEEP", "91 exec; option walk is a real seam but the option-walker ratchet (Q2) pins this shape — re-pointing it is cost without behaviour value"),
 ("psh/builtins/positional.py", "GetoptsBuiltin.execute"): ("builtin option/operand", "ALGORITHM", "JUSTIFIED-KEEP", "84 exec; ONE cursor transition — six exit arms each call advance() once with a different pair; splitting passes the whole state tuple to every helper"),
 ("psh/builtins/test_command.py", "TestBuiltin.evaluate_unary"): ("builtin option/operand", "CASE-TABLE", "DECOMPOSE", "99 exec (2nd-highest in the census), PURE, zero deferred imports; TEN arms are the identical stat-and-predicate shape and THREE are the identical access-mode shape — a jump table written as a chain"),
 ("psh/builtins/navigation.py", "CdBuiltin.execute"): ("builtin option/operand", "SEQUENCE", "JUSTIFIED-KEEP", "71 exec; clean seams, but cd's CDPATH/logical-path rules are conformance-pinned and the value is cosmetic"),
 ("psh/builtins/function_support.py", "DeclareBuiltin._declare_assignment"): ("builtin option/operand", "DISPATCH-HUB", "JUSTIFIED-KEEP", "89 exec; the array-kind cross-product is the declaration family's core semantics"),
 ("psh/builtins/parse_tree.py", "ParseTreeBuiltin.execute"): ("builtin option/operand", "DISPATCH-HUB", "DECOMPOSE", "71 exec; the CLEANEST cut in the census — two independent hubs (option scan, renderer dispatch), zero risk, direct unit test, and it is the SECOND named grower (E2), so decomposing it demonstrates the ledger on a row the brief cares about"),
 ("psh/builtins/print_builtin.py", "PrintBuiltin._parse_options"): ("builtin option/operand", "DISPATCH-HUB", "DECOMPOSE", "86 exec, PURE, zero deferred imports; -u and -f duplicate an attached-or-separate operand read VERBATIM, and that duplication is the only place the outer index is mutated from the inner loop — a real coupling defect, not cosmetics"),
}

sys.path.insert(0, str(Path(__file__).resolve().parent))
from A15_fn_anatomy_targeted import anatomy  # noqa: E402

TREE = sys.argv[2] if len(sys.argv) > 2 else "/Users/pwilson/src/psh-r5c-2"

census = json.loads(Path(sys.argv[1]).read_text())
rows = {(r["file"], r["fn"]): r["len"] for r in census["ge100"]}

missing = sorted(set(rows) - set(M))
invented = sorted(set(M) - set(rows))
assert not missing, f"census rows with NO disposition: {missing}"
assert not invented, f"dispositions for rows NOT in the census: {invented}"

print(f"census rows: {len(rows)}   dispositioned: {len(M)}   (exact cover asserted)\n")

by_txn = Counter(v[0] for v in M.values())
by_disp = Counter(v[2] for v in M.values())

print("=== rows per NAMED TRANSACTION")
for k, n in sorted(by_txn.items(), key=lambda t: -t[1]):
    print(f"    {n:3d}  {k}")
print(f"    {sum(by_txn.values()):3d}  TOTAL")

print("\n=== rows per DISPOSITION")
for k, n in sorted(by_disp.items(), key=lambda t: -t[1]):
    print(f"    {n:3d}  {k}")
print(f"    {sum(by_disp.values()):3d}  TOTAL")

print("\n=== PROPOSED EXECUTED SET (disposition = DECOMPOSE)")
for (f, q), (txn, shape, disp, why) in sorted(M.items()):
    if disp == "DECOMPOSE":
        print(f"    [{rows[(f,q)]:4d}] {f}::{q}\n           {txn} / {shape}\n           {why}")

print("\n=== POINTER rows (nested; body dispositioned at parent)")
for (f, q), v in sorted(M.items()):
    if v[2] == "POINTER":
        print(f"    {f}::{q}")

# R1 c-2 / §3: the matrix carries exec / comment / nominal per row, so
# "JUSTIFIED-KEEP: length is documentation" is a MEASURED reason, not an
# assertion. Columns come from the ONE anatomy implementation (imported).
print("\n=== FULL MATRIX with exec/comment/nominal columns (R1 §3)")
print(f"{'nom':>4} {'exec':>5} {'cmt':>4} {'doc':>4}  {'disposition':<15} file::fn")
enriched = []
for (f, q), (txn, shape, disp, why) in M.items():
    a = anatomy(f, q, TREE)
    enriched.append((a["exec"], a["len"], a["comment"], a["doc"], disp, f, q, txn, why))
for ex, nom, cmt, doc, disp, f, q, txn, why in sorted(enriched, key=lambda r: -r[0]):
    print(f"{nom:4d} {ex:5d} {cmt:4d} {doc:4d}  {disp:<15} {f}::{q}")

ge100_exec = [r for r in enriched if r[0] >= 100]
print(f"\n  rows with >=100 EXECUTABLE lines: {len(ge100_exec)}")
for ex, nom, cmt, doc, disp, f, q, txn, why in sorted(ge100_exec, key=lambda r: -r[0]):
    print(f"    exec={ex} nominal={nom}  {disp}  {f}::{q}")

doc_heavy = [r for r in enriched if r[2] + r[3] > r[0]]
print(f"\n  rows where doc+comment lines EXCEED executable lines: "
      f"{len(doc_heavy)} of {len(enriched)}")
