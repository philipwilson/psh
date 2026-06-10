# Code Review Observations

Observations from a review of the lexer, parser, expansion, and evaluation subsystems. Roughly ordered by impact.

## Bugs / Correctness (all fixed)

### ~~1. Command substitution strips only one trailing newline~~ FIXED

**File**: `psh/expansion/command_sub.py`

Now uses `output.rstrip('\n')` to strip all trailing newlines per POSIX.

### ~~2. SIGCHLD handler not restored on exception~~ FIXED

**File**: `psh/expansion/command_sub.py`

Signal restore is now in a `finally` block.

### ~~3. WordSplitter doesn't distinguish IFS whitespace from IFS non-whitespace~~ FIXED

**File**: `psh/expansion/word_splitter.py`

Now properly separates IFS into whitespace and non-whitespace sets, collapses consecutive whitespace delimiters, and preserves empty fields for non-whitespace delimiters (e.g. `a::b` with `IFS=:` yields three fields).

### ~~4. WordSplitter swallows backslashes~~ FIXED

**File**: `psh/expansion/word_splitter.py`

Backslashes are now preserved during word splitting rather than being stripped.

### ~~5. GlobExpander doesn't handle dotfiles~~ FIXED

**File**: `psh/expansion/glob.py`

Now reads the `dotglob` shell option and passes it to `glob.glob(pattern, include_hidden=dotglob)`.

### ~~6. CommentRecognizer `_is_comment_start` has redundant logic~~ FIXED

**File**: `psh/lexer/recognizers/comment.py`

Dead code removed; logic is now clean and non-redundant.

## Structural / Design (all fixed)

### ~~7. WhitespaceRecognizer does unnecessary work~~ FIXED

**File**: `psh/lexer/recognizers/whitespace.py`

Simplified to just advance past whitespace and return `(None, new_pos)`. No longer builds a whitespace string or creates a discarded Token object.

### ~~8. `hasattr` checks for token types~~ FIXED

**Files**: `psh/lexer/recognizers/whitespace.py`, `psh/lexer/recognizers/comment.py`

Removed the `hasattr(TokenType, 'COMMENT')` / `hasattr(TokenType, 'WHITESPACE')` guards and the unused Token construction. Neither `TokenType.COMMENT` nor `TokenType.WHITESPACE` exist, and the tokens were never emitted.

### ~~9. CommentRecognizer returns inconsistent type~~ FIXED

**Files**: `psh/lexer/recognizers/comment.py`, `psh/lexer/recognizers/whitespace.py`

Both recognizers now consistently return `(None, new_pos)` to indicate "skip this region." WhitespaceRecognizer previously returned bare `None`; it now matches CommentRecognizer's convention.

### ~~10. ExpansionComponent base class isn't used consistently~~ FIXED

**File**: `psh/expansion/base.py`

Removed the unused `ExpansionComponent` abstract base class. The expansion components (`GlobExpander`, `CommandSubstitution`, `VariableExpander`, `TildeExpander`) all take a `Shell` instance and have method signatures tailored to their needs (e.g., `GlobExpander.expand` returns `List[str]`). The ABC did not fit and was never inherited.

## Low Priority / Robustness (all fixed)

### ~~11. `output_bytes` concatenation is O(n^2)~~ FIXED

**File**: `psh/expansion/command_sub.py`

Now collects chunks in a list and joins with `b''.join(chunks)` for O(n) performance.

### ~~12. Hardcoded errno~~ FIXED

**File**: `psh/expansion/command_sub.py`

Now uses `errno.ECHILD` instead of the hardcoded literal `10`.
