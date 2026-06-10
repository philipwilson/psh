# Architecture Improvement Recommendations

## Lexing

- **Unify post-lexing pipeline**: Wrap `KeywordNormalizer`, `TokenTransformer`, and `CompositeTokenProcessor` behind a single façade so downstream components can opt into a consistent token pipeline. This also provides a common hook for tracing or profiling.
- **Push keyword metadata into recognizers**: Instead of relying on helper functions to annotate `SemanticType.KEYWORD`, make the lexer’s recognizers or token factory set canonical metadata. That guarantee would survive even if new code bypasses the helper utilities.

## Parsing

- **Share keyword-aware collectors**: Extract helpers such as “collect until keyword” into a shared module so both recursive-descent and combinator parsers consume the same logic, reducing the divergence we continually reconcile.
- **Expose a keyword view on ParserContext**: Provide an API (e.g., `context.keyword_guard`) that caches keyword matches, removing repeated imports and making it easier to instrument parsing hotspots.

## Expansion

- **Separate orchestration from transformation**: Let `ExpansionManager` focus on ordering/debug logic while individual expanders implement a narrow interface. That split simplifies testing (stub expanders) and future extension points.
- **Formalize Word AST contracts**: Introduce a lightweight interface or dataclass for words so string-based and AST-based expansion modes share the same contract, eliminating feature-flag branches inside expanders.

## Execution & Job Control

- **Break JobManager into roles**: Split responsibilities into state storage, notifier, and terminal-control helpers. This makes features like persistent job tables or remote job observation less risky and clarifies ownership of TTY manipulation.
- **Extract process-group helpers**: Consolidate the repeated signal/pgid boilerplate across pipeline, subshell, and builtin background execution into a reusable utility (e.g., `ProcessGroupManager`) to avoid future regressions.

## Documentation & Tooling

- **Add subsystem cookbooks**: Mirror the keyword helper cookbook with short guides for expansion ordering, job control, and process groups so incoming contributors see expectations and tracing hooks in one place.
- **Extend static guardrails**: Introduce similar tooling checks for other fragile domains (e.g., direct `os.tcsetpgrp` calls) to enforce the shared helpers and keep lifecycle-sensitive code paths consistent.
