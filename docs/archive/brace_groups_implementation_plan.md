# Implementation Plan for POSIX-style Brace Command Groups in PSH

## Overview

This document outlines the implementation plan for adding POSIX-compliant brace command groups `{ ... }` to the Python Shell (psh) project. This feature was identified as a missing core functionality during POSIX conformance testing.

## Background

Brace groups `{ command1; command2; }` are a fundamental POSIX shell construct that groups commands for execution in the **current shell environment**. This differs from subshells `( command1; command2 )` which execute in an isolated subprocess.

### Key Differences from Subshells

| Feature | Brace Groups `{ }` | Subshells `( )` |
|---------|-------------------|-----------------|
| Process | Current shell | Forked subprocess |
| Variable changes | Persist to parent | Isolated |
| Directory changes | Persist to parent | Isolated |
| Performance | No fork overhead | Fork overhead |
| Signal handlers | Inherited | Reset |

## Current State Analysis

### Lexer ✅
- `LBRACE` and `RBRACE` tokens already exist in `token_types.py`
- Tokens are properly recognized in `lexer/constants.py`
- No changes needed to lexer

### Parser ❌
- Currently treats `{` and `}` as `WORD` tokens (commands)
- No parsing logic for brace groups
- No AST node for brace groups

### Executor ❌
- No visitor method for brace groups
- No execution logic

## Implementation Plan

### Phase 1: AST Node Definition

Add to `psh/ast_nodes.py` after `SubshellGroup`:

```python
@dataclass
class BraceGroup(CompoundCommand):
    """Represents a brace group {...} that executes in the current shell environment.
    
    Unlike subshells, brace groups:
    - Execute in the current shell process (no fork)
    - Variable assignments persist to the parent environment
    - Directory changes (cd) affect the parent shell
    - Are more efficient (no subprocess overhead)
    
    POSIX syntax requirements:
    - Must have space after opening brace: { command
    - Must have semicolon or newline before closing brace: command; }
    """
    statements: 'CommandList'
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False
```

### Phase 2: Parser Updates

#### 2.1 Fix Token Classification

In `psh/parser/commands.py`, remove lines that treat braces as words:

```python
# Remove these lines (currently around line 263-264):
TokenType.LBRACE: ('WORD', lambda t: t.value),
TokenType.RBRACE: ('WORD', lambda t: t.value),
```

#### 2.2 Add Brace Group Parsing Method

Add to `psh/parser/commands.py`:

```python
def parse_brace_group(self) -> BraceGroup:
    """Parse brace group {...} that executes in current environment.
    
    POSIX syntax rules:
    - Space required after {
    - Semicolon or newline required before }
    """
    self.parser.expect(TokenType.LBRACE)
    
    # POSIX requires space after opening brace
    if not self.parser.last_had_whitespace:
        self.parser.error("syntax error: space required after '{'")
    
    self.parser.skip_newlines()
    
    # Parse statements inside the brace group
    statements = self.parser.statements.parse_command_list_until(TokenType.RBRACE)
    
    # POSIX requires semicolon or newline before closing brace
    if not statements.trailing_separator and not self.parser.last_was_newline:
        self.parser.error("syntax error: ';' or newline required before '}'")
    
    self.parser.skip_newlines()
    self.parser.expect(TokenType.RBRACE)
    
    # Parse any redirections after the brace group
    redirects = self.parser.redirections.parse_redirects()
    
    # Check for background operator
    background = self.parser.match(TokenType.AMPERSAND)
    if background:
        self.parser.advance()
    
    return BraceGroup(
        statements=statements,
        redirects=redirects,
        background=background
    )
```

#### 2.3 Update Pipeline Component Parser

In `parse_pipeline_component()` method, add after line 194:

```python
elif self.parser.match(TokenType.LBRACE):
    return self.parse_brace_group()
```

### Phase 3: Executor Implementation

Add to `psh/visitor/executor_visitor.py`:

```python
def visit_BraceGroup(self, node: BraceGroup) -> int:
    """Execute brace group {...} in current shell environment.
    
    Key differences from subshells:
    - No fork() - executes in current process
    - Variable assignments persist
    - Directory changes persist
    - More efficient (no subprocess overhead)
    """
    # Save pipeline context
    old_pipeline = self._in_pipeline
    self._in_pipeline = False
    
    try:
        # Apply redirections
        with self._apply_redirections(node.redirects):
            # Execute statements in current environment
            exit_code = self.visit(node.statements)
            
            # Handle background execution
            if node.background:
                # For background brace groups, we need to fork
                # Only the execution needs to be backgrounded
                return self._execute_background_brace_group(node)
            
            return exit_code
    finally:
        self._in_pipeline = old_pipeline

def _execute_background_brace_group(self, node: BraceGroup) -> int:
    """Execute brace group in background.
    
    Note: Background execution requires forking, but the brace group
    semantics are preserved within the forked process.
    """
    pid = os.fork()
    
    if pid == 0:
        # Child process
        try:
            # Create new process group
            os.setpgid(0, 0)
            
            # Execute the brace group
            exit_code = self.visit(node.statements)
            os._exit(exit_code)
        except Exception as e:
            print(f"psh: {e}", file=sys.stderr)
            os._exit(1)
    else:
        # Parent process
        # Register background job
        self.job_manager.add_job(pid, str(node), background=True)
        return 0
```

### Phase 4: Import Updates

Add `BraceGroup` to imports in:
- `psh/parser/commands.py`
- `psh/visitor/executor_visitor.py`
- Any other files that import AST nodes

### Phase 5: Edge Cases and Validation

#### 5.1 Syntax Validation
- Enforce space after `{`
- Enforce `;` or newline before `}`
- Proper error messages

#### 5.2 Nesting Support
- Brace groups within brace groups
- Brace groups within subshells
- Subshells within brace groups
- Brace groups in pipelines

#### 5.3 Context Conflicts
- Function bodies (already use `{ }`)
- Avoid confusion with brace expansion `{a,b,c}`

### Phase 6: Testing Strategy

#### 6.1 Basic Tests
```bash
# Simple grouping
{ echo hello; echo world; }

# Variable persistence
{ x=10; }; echo $x  # Should print 10

# Directory persistence  
{ cd /tmp; }; pwd  # Should show /tmp

# Exit status
{ false; }; echo $?  # Should print 1
```

#### 6.2 Advanced Tests
```bash
# Redirections
{ echo out; echo err >&2; } > output.txt 2> error.txt

# Pipelines
echo "5 8" | { read a b; echo $((a * b)); }  # Should print 40

# Background
{ sleep 1; echo done; } &

# Nesting
{ { echo nested; }; }
```

#### 6.3 Error Tests
```bash
# Missing space
{echo bad;}  # Should error

# Missing semicolon
{ echo bad }  # Should error

# Unclosed brace
{ echo unclosed  # Should error
```

## Implementation Order

1. **Step 1**: Add BraceGroup AST node (5 minutes)
2. **Step 2**: Update parser token handling (10 minutes)
3. **Step 3**: Implement parse_brace_group method (30 minutes)
4. **Step 4**: Update parse_pipeline_component (5 minutes)
5. **Step 5**: Implement visit_BraceGroup (20 minutes)
6. **Step 6**: Add syntax validation (30 minutes)
7. **Step 7**: Create comprehensive test suite (1-2 hours)
8. **Step 8**: Update documentation (20 minutes)

## Estimated Timeline

- **Core Implementation**: 2-3 hours
- **Testing & Debugging**: 1-2 hours
- **Documentation**: 30 minutes
- **Total**: 3-5 hours

## Success Criteria

1. All POSIX syntax requirements met
2. Variable and directory changes persist
3. Proper exit status propagation
4. Redirections work correctly
5. Background execution supported
6. Pipeline integration works
7. No regression in existing tests
8. Conformance test `test_function_inheritance.input` passes

## Future Enhancements

1. Optimize background execution
2. Better error recovery for syntax errors
3. Enhanced debugging output for brace groups
4. Performance benchmarking vs subshells

## References

- POSIX.1-2017 Shell Command Language specification
- Bash manual section on Compound Commands
- PSH architecture documentation

---

Document created: December 2024
Author: Claude (Anthropic)