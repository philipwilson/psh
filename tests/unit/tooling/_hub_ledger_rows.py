"""Hub-ledger rows for :mod:`test_hub_ledger_5c2` — data only, no logic.

Kept in its own module so the guard reads as a guard: the arms live next to
the metric they enforce, and the 60-row table does not bury them. See that
module's docstring for membership/entry/exit and why the threshold is
EXECUTABLE lines rather than raw source lines.

Key: (file, qualname). Value: (disposition, reason). Every figure is measured
by the guard, never frozen here — a count written into this table would be a
stale-figure hazard of exactly the kind the ledger exists to catch.
"""

LEDGER = {
    ('psh/builtins/environment.py',
     'ExportBuiltin.execute_in_context'):
        ('JUSTIFIED-KEEP',
         'Option walk is a real seam but the option-walker ratchet (Q2) pins '
         'this shape — re-pointing it is cost without behaviour value'),
    ('psh/builtins/environment.py',
     'UnsetBuiltin._unset_array_element'):
        ('JUSTIFIED-KEEP',
         'Array-unset shape routing with nameref provenance; seams exist but '
         'sit on the array mutation path'),
    ('psh/builtins/function_support.py',
     'DeclareBuiltin._declare_assignment'):
        ('JUSTIFIED-KEEP',
         "The array-kind cross-product is the declaration family's core "
         'semantics'),
    ('psh/builtins/function_support.py',
     'DeclareBuiltin._declare_bare_name'):
        ('JUSTIFIED-KEEP',
         'Two array arms are structurally parallel but differ in '
         'ArrayKind/container/slot-key — parameterising is an edit, not a '
         'move'),
    ('psh/builtins/job_control.py',
     'WaitBuiltin._wait_for_specific'):
        ('JUSTIFIED-KEEP',
         'Five-way pid resolution ladder over reap-registry state; '
         'CR-D1-adjacent'),
    ('psh/builtins/navigation.py',
     'CdBuiltin.execute'):
        ('JUSTIFIED-KEEP',
         "Clean seams, but cd's CDPATH/logical-path rules are "
         'conformance-pinned and the value is cosmetic'),
    ('psh/builtins/positional.py',
     'GetoptsBuiltin.execute'):
        ('JUSTIFIED-KEEP',
         'ONE cursor transition — six exit arms each call advance() once '
         'with a different pair; splitting passes the whole state tuple to '
         'every helper'),
    ('psh/builtins/read_builtin.py',
     'ReadBuiltin.execute'):
        ('JUSTIFIED-KEEP',
         "PROPOSED 7th GROWER, ARGUED OUT. 81 exec under 93 comment; 5C.1's "
         '+11 was -3 exec/+14 comment. Real seams exist but the InputCursor '
         'contract (4B.3/4B.4) is pinned to this body'),
    ('psh/builtins/shell_state.py',
     'HistoryBuiltin._dispatch_options'):
        ('JUSTIFIED-KEEP',
         "The flag ORDER is a single indivisible bash-measured fact (4B.3's "
         'own subject), pinned by the M8 locks'),
    ('psh/builtins/shell_state.py',
     'LocalBuiltin._declare_one_local'):
        ('JUSTIFIED-KEEP',
         'Arms are one-liners already, the length is the six-way declaration '
         'cross-product'),
    ('psh/core/scope.py',
     'ScopeManager.create_local'):
        ('JUSTIFIED-KEEP',
         '46 exec under 67 comment lines; four readonly rejections are '
         'scattered but each cites a distinct bash rule — consolidation is a '
         'behaviour-risk edit, not a move'),
    ('psh/core/scope.py',
     'ScopeManager.set_variable'):
        ('JUSTIFIED-KEEP',
         'Five early-return write routes whose ORDER is the masking '
         'semantics (nameref/temp-env/dynamic-special); pinned by the '
         'variable-truth guard'),
    ('psh/core/state.py',
     'ShellState.__init__'):
        ('JUSTIFIED-KEEP',
         '94 exec lines carrying 191 comment lines of env/locale/option '
         'ordering provenance; the ordering IS the contract and grouping '
         'hides it'),
    ('psh/core/state.py',
     'ShellState.clone_for_child'):
        ('JUSTIFIED-KEEP',
         '41 exec lines; correctness property is EXHAUSTIVENESS over '
         "__init__'s field set, pinned by test_state_clone_completeness.py — "
         'grouping makes a missing field harder to spot'),
    ('psh/executor/array.py',
     'ArrayOperationExecutor.execute_array_element_assignment'):
        ('JUSTIFIED-KEEP',
         'Clean seams exist but sit on the array write path (1.3b-adjacent '
         'state), value does not clear the risk bar this slot'),
    ('psh/executor/command.py',
     'CommandExecutor._run_command'):
        ('JUSTIFIED-KEEP',
         'NAMED GROWER. 92 exec under 138 comment lines; '
         'phase1/resolve/phase2 ordering is the authority-timing contract '
         '(#20 H10) pinned by test_resolution_timing_ratchet_3_4.py; 1.3b '
         'child-status territory'),
    ('psh/executor/command_assignments.py',
     'CommandAssignments.commit_prefix'):
        ('JUSTIFIED-KEEP',
         '63 exec under 29 doc + 38 comment; the _pop_staging_scope ordering '
         'is explicitly load-bearing (an install exception must not be '
         'masked by an ownership error)'),
    ('psh/executor/control_flow.py',
     'ControlFlowExecutor.execute_case'):
        ('JUSTIFIED-KEEP',
         'DEBUG-trap + legacy-AST fallback provenance dominates the length'),
    ('psh/executor/control_flow.py',
     'ControlFlowExecutor.execute_select'):
        ('JUSTIFIED-KEEP',
         'Interactive read loop, PTY-adjacent coverage cost'),
    ('psh/executor/function.py',
     'FunctionOperationExecutor._function_frame'):
        ('JUSTIFIED-KEEP',
         'Docstring states the invariant — save/restore pairs must stay '
         'ADJACENT and countable; splitting defeats the one property '
         'enforced'),
    ('psh/executor/function.py',
     'FunctionOperationExecutor.execute_function_call'):
        ('JUSTIFIED-KEEP',
         'Length is an except-ladder whose CLAUSE ORDER is the semantics '
         '(FunctionReturn inside the frame, Loop* outside); a '
         'terminal-handler ledger key lives here'),
    ('psh/executor/job_control.py',
     'JobManager.wait_for_job'):
        ('JUSTIFIED-KEEP',
         'Waitpid(-pgid) EINTR/ECHILD policy; CR-D1 lives in this territory'),
    ('psh/executor/pipeline.py',
     'PipelineExecutor._execute_pipeline'):
        ('JUSTIFIED-KEEP',
         '95 exec under 89 comment; fork + SIGTTOU/SIGTTIN + pgid + sync '
         'pipes + fd setup in one transaction; must-not-flip names every one '
         'of these'),
    ('psh/executor/process_launcher.py',
     'ProcessLauncher._child_setup_and_exec'):
        ('JUSTIFIED-KEEP',
         'Child-side body ending in os._exit inside finally — the fork '
         'discipline must-not-flip; terminal-handler ledger key at :374'),
    ('psh/executor/strategies.py',
     'ExternalExecutionStrategy.execute'):
        ('JUSTIFIED-KEEP',
         'Fork + os._exit + pgid + terminal transfer in one body; '
         'integration-weighted coverage only — worst fast-feedback net in '
         'the census'),
    ('psh/executor/subshell.py',
     'SubshellExecutor._execute_foreground_subshell'):
        ('JUSTIFIED-KEEP',
         'Fork + terminal transfer + raw os.write(2,...) post-fork; '
         'highest-risk row in the census'),
    ('psh/expansion/command_sub.py',
     'CommandSubstitutionExecutor.execute'):
        ('JUSTIFIED-KEEP',
         'Four resource sentinels whose only correctness property is that '
         'ONE finally sees all four; fork + SIGCHLD swap'),
    ('psh/expansion/extglob.py',
     '_convert_pattern'):
        ('JUSTIFIED-KEEP',
         'Production-dead — a PERMANENT reference oracle for the '
         'differential against pattern_engine; refactoring an oracle '
         'destroys its independence'),
    ('psh/expansion/glob.py',
     'GlobExpander._expand_globstar'):
        ('JUSTIFIED-KEEP',
         'The (text, still-verbatim) tuple invariant is only meaningful '
         'relative to position in the component walk — it cannot cross a '
         'function boundary intact'),
    ('psh/expansion/operators.py',
     'OperatorOpsMixin._apply_operator'):
        ('JUSTIFIED-KEEP',
         'Scalar twin of the row above — same reason, same cross-row seam'),
    ('psh/expansion/pattern_engine.py',
     '_BashMatcher._match'):
        ('JUSTIFIED-KEEP',
         'A deliberate glibc sm_loop.c port whose control flow IS the '
         'semantics being reproduced; comments pin per-arm glibc provenance'),
    ('psh/expansion/variable.py',
     'VariableExpander._expand_array_parameter'):
        ('JUSTIFIED-KEEP',
         'The real decomposition is a UNIFIED operator table shared with '
         "_apply_operator — a cross-row design, too big for this slot's "
         'zero-delta budget'),
    ('psh/interactive/history_expansion.py',
     'HistoryExpander.expand_history'):
        ('JUSTIFIED-KEEP',
         '101 exec — one of only TWO genuine >=100-exec rows. Single-pass '
         'scanner over six coupled cursor variables; the forward suppression '
         'feed REPLACED three backward rescans, so splitting reintroduces '
         'the state-passing that design deleted'),
    ('psh/interactive/repl_loop.py',
     'REPLLoop.run'):
        ('JUSTIFIED-KEEP',
         '47 exec under 58 comment; SIGCHLD + stopped-job notices + terminal '
         'reads; PTY-test cost, no unit net'),
    ('psh/invocation.py',
     'parse_invocation'):
        ('DECOMPOSED-THIS-SLOT',
         'Invocation-config construction. The three tail InvocationConfig '
         'constructions shared ten kwargs and were folded into _config '
         '(the forget-a-field-in-one-of-three class). It STAYS a row: what '
         'remains is the option-transition walk plus the exclusivity and '
         'parser validations, which are ordered rules over one accumulating '
         'parse state, not separable responsibilities — and the ordering is '
         'the contract (validate before any Shell can exist). PURE: no '
         'Shell, never prints, never exits; guarded by '
         'test_invocation_argv_guard.py'),
    ('psh/io_redirect/file_redirect.py',
     'FileRedirector.apply_permanent_redirections'):
        ('JUSTIFIED-KEEP',
         'Exec-path fd transaction with lease acquire/rollback (4A.1 '
         'territory); terminal-handler ledger keys at :1327'),
    ('psh/io_redirect/file_redirect.py',
     'FileRedirector.apply_var_fd_redirect'):
        ('DECOMPOSE-PENDING',
         'NAMED GROWER. 50 exec; the allocate-and-record tail (F_DUPFD>=10 + '
         'set_variable + scope_fd) repeats VERBATIM in three arms — that '
         'triplication IS the named-fd allocation contract, and it has no '
         'single owner'),
    ('psh/lexer/cmdsub_scanner.py',
     'find_command_substitution_end'):
        ('JUSTIFIED-KEEP',
         'MEASUREMENT ARTEFACT: a ONE-STATEMENT body under a ~96-line '
         'maintenance contract. The decomposition this row asks for already '
         'happened (_CmdSubScanner); removing lines here deletes the '
         'contract, not complexity'),
    ('psh/lexer/command_position.py',
     'advance_lexical_state'):
        ('JUSTIFIED-KEEP',
         'Three labelled sections with a documented cross-section data '
         'dependency; the docstring explicitly FORBIDS the tempting larger '
         'refactor'),
    ('psh/lexer/keyword_normalizer.py',
     'KeywordNormalizer.normalize'):
        ('JUSTIFIED-KEEP',
         'Golden-fixture pinned reclassification pass, arms carry per-arm '
         'bash rationale'),
    ('psh/lexer/pure_helpers.py',
     'handle_ansi_c_escape'):
        ('JUSTIFIED-KEEP',
         "The length is the escape alphabet's length; arms differ in failure "
         'text and new_pos on the empty case'),
    ('psh/lexer/quote_parser.py',
     'UnifiedQuoteParser.parse_quoted_string'):
        ('JUSTIFIED-KEEP',
         'Weakest DIRECT test coverage in the census (no test names it) — '
         'refactoring the least-netted row is the wrong trade'),
    ('psh/lexer/recognizers/literal.py',
     'LiteralRecognizer._collect_literal_value'):
        ('JUSTIFIED-KEEP',
         'Every branch mutates the same three trackers and the branch ORDER '
         'is the semantics; separable sub-decisions already extracted'),
    ('psh/lexer/token_stream.py',
     'TokenStream.collect_arithmetic_expression'):
        ('JUSTIFIED-KEEP',
         'Mutates the shared token stream in place (_split_double_rparen) — '
         'extraction would move a splice away from its depth accounting'),
    ('psh/parser/combinators/commands/pipelines.py',
     'PipelineMixin._build_pipeline_parser'):
        ('JUSTIFIED-KEEP',
         'Same builder+closure shape; the time-prefix and |-tail are grammar '
         'clauses, not responsibilities'),
    ('psh/parser/combinators/commands/redirections.py',
     'RedirectionMixin._parse_redirection'):
        ('JUSTIFIED-KEEP',
         'Parse-only (no fd work); the heredoc arm is a real seam but '
         'heredoc parse state is 2.3/S2 pinned territory'),
    ('psh/parser/combinators/commands/simple.py',
     'SimpleCommandMixin._build_simple_command_parser'):
        ('JUSTIFIED-KEEP',
         'Builder whose body is one nested closure — the grammar production '
         'is the unit'),
    ('psh/parser/combinators/commands/simple.py',
     'SimpleCommandMixin._build_simple_command_parser.parse_simple_command'):
        ('POINTER',
         'Nested inside _build_simple_command_parser — dispositioned at the '
         'parent'),
    ('psh/parser/combinators/control_structures/conditionals.py',
     'ConditionalParserMixin._build_case_statement'):
        ('JUSTIFIED-KEEP',
         'One grammar production; _parse_case_item is a real seam but '
         'parser-combinator shape change is RESUMABLE-PARSER successor '
         'territory'),
    ('psh/parser/combinators/control_structures/conditionals.py',
     'ConditionalParserMixin._build_case_statement.parse_case_statement'):
        ('POINTER',
         'Nested inside _build_case_statement — dispositioned at the parent'),
    ('psh/parser/combinators/control_structures/conditionals.py',
     'ConditionalParserMixin._build_if_statement'):
        ('JUSTIFIED-KEEP',
         '100 exec — the OTHER genuine >=100-exec row. Already internally '
         'decomposed into two nested productions; if/elif/else/fi are four '
         'grammar clauses that cannot collapse'),
    ('psh/parser/combinators/control_structures/loops.py',
     'LoopParserMixin._build_c_style_for_loop'):
        ('JUSTIFIED-KEEP',
         'Grammar construction: one production, built as a combinator '
         'builder whose body is its nested parser closure. The arithmetic '
         'header and the do/brace body are grammar clauses, not separable '
         'responsibilities; reshaping this family belongs to the '
         'RESUMABLE-PARSER successor, not to hub decomposition'),
    ('psh/parser/combinators/control_structures/loops.py',
     'LoopParserMixin._build_c_style_for_loop.parse_c_style_for'):
        ('POINTER',
         'Nested inside _build_c_style_for_loop — dispositioned at the '
         'parent'),
    ('psh/parser/session.py',
     'ParseSession.feed'):
        ('JUSTIFIED-KEEP',
         'The phase ORDER is the specification (I3 session guards); '
         'extraction turns ordered fall-through into a handled/not-handled '
         'return protocol'),
    ('psh/scripting/input_preprocessing.py',
     'process_line_continuations'):
        ('JUSTIFIED-KEEP',
         '40 exec under a 44-line bash-measured docstring; context rules '
         'ALREADY extracted to five helpers — what remains is the '
         'irreducible cursor loop'),
    ('psh/scripting/source_processor.py',
     'SourceProcessor._execute_buffered_command'):
        ('JUSTIFIED-KEEP',
         'The function IS the error model — clause order is the content; '
         'terminal-handler ledger key lives here'),
}
