# Parser Combinator Expansions - Visual Guide

## Feature Interaction Diagram

```
                    ┌─────────────────────┐
                    │   Token Stream      │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴───────────────┐
                │         Lexer                │
                │  ┌───────────────────────┐  │
                │  │ Command Substitution  │  │
                │  │ $(...) or `...`       │  │
                │  ├───────────────────────┤  │
                │  │ Parameter Expansion   │  │
                │  │ ${var:-default}       │  │
                │  ├───────────────────────┤  │
                │  │ Here Document         │  │
                │  │ <<EOF ... EOF         │  │
                │  └───────────────────────┘  │
                └──────────────┬───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Enhanced Tokens    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Parser Combinator  │
                    └─────────────────────┘
```

## Command Substitution Flow

```
Input: echo "Today is $(date +%Y-%m-%d)"
         │
         ▼
┌─────────────────┐
│     Lexer       │
├─────────────────┤
│ 1. WORD: echo   │
│ 2. STRING with: │
│    - "Today is "│
│    - CMDSUB:    │
│      $(date...) │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│    Parser Combinator    │
├─────────────────────────┤
│ 1. Parse outer command  │
│ 2. Detect CMDSUB token  │
│ 3. Recursively parse:   │
│    "date +%Y-%m-%d"     │
│ 4. Build AST:           │
│    SimpleCommand(       │
│      args=["echo",      │
│        StringWithSubs(  │
│          parts=[        │
│            "Today is ", │
│            CmdSub(...)  │
│          ])]            │
│    )                    │
└─────────────────────────┘
```

## Here Document Processing

```
Input: cat <<EOF
       Line 1
       Line 2
       EOF

Step 1: Command Line Parsing
┌──────────────────────┐
│ cat <<EOF            │
├──────────────────────┤
│ Tokens:              │
│ - WORD: cat          │
│ - HEREDOC_START: <<  │
│ - WORD: EOF          │
│ - NEWLINE            │
└──────────┬───────────┘
           │
           ▼
Step 2: Content Collection
┌──────────────────────┐
│ Lexer State:         │
│ - In heredoc mode    │
│ - Delimiter: "EOF"   │
│ - Collect lines:     │
│   * "Line 1\n"       │
│   * "Line 2\n"       │
│ - Until: "EOF\n"     │
└──────────┬───────────┘
           │
           ▼
Step 3: AST Construction
┌──────────────────────┐
│ SimpleCommand(       │
│   args=["cat"],      │
│   redirects=[        │
│     Redirect(        │
│       type="<<",     │
│       target="EOF",  │
│       heredoc_content│
│         ="Line 1\n"+ │
│          "Line 2\n"  │
│     )]               │
│ )                    │
└──────────────────────┘
```

## Parameter Expansion Parsing

```
Input: echo ${PATH:-/usr/bin}

Token Analysis:
┌─────────────────────────────┐
│ ${PATH:-/usr/bin}           │
├─────────────────────────────┤
│ Components:                 │
│ 1. Start: ${                │
│ 2. Variable: PATH           │
│ 3. Operator: :-             │
│ 4. Value: /usr/bin          │
│ 5. End: }                   │
└──────────────┬──────────────┘
               │
               ▼
Parser State Machine:
┌──────┐     ┌──────┐     ┌────────┐     ┌───────┐
│Start │────▶│ Var  │────▶│   Op   │────▶│ Value │
│  ${  │     │ Name │     │ :- := ?│     │ Text  │
└──────┘     └──────┘     └────────┘     └───┬───┘
                                              │
                                              ▼
                                         ┌────────┐
                                         │  End } │
                                         └────────┘
```

## Complex Nesting Examples

### 1. Command Substitution in Parameter Expansion
```bash
${var:-$(default_command)}

Parse Tree:
ParameterExpansion
├── variable: "var"
├── operator: ":-"
└── value: CommandSubstitution
           └── command: "default_command"
```

### 2. Parameter Expansion in Here Document
```bash
cat <<EOF
User: ${USER}
Home: ${HOME:-/tmp}
EOF

Parse Tree:
SimpleCommand
├── args: ["cat"]
└── redirects: [Redirect
                ├── type: "<<"
                ├── target: "EOF"
                └── heredoc_content: (with expansions)
                    ├── "User: "
                    ├── ParameterExpansion(variable="USER")
                    ├── "\nHome: "
                    └── ParameterExpansion(variable="HOME", operator=":-", value="/tmp")]
```

### 3. Nested Command Substitutions
```bash
echo $(echo $(date))

Parse Tree:
SimpleCommand
├── args: ["echo"]
└── args: [CommandSubstitution
           └── command: SimpleCommand
                       ├── args: ["echo"]
                       └── args: [CommandSubstitution
                                  └── command: SimpleCommand(args=["date"])]]
```

## Lexer State Management

```
┌─────────────────────────────────────┐
│          Lexer States               │
├─────────────────────────────────────┤
│ NORMAL: Regular tokenization        │
│    ↓                                │
│ HEREDOC_DELIMITER: After <<         │
│    ↓                                │
│ HEREDOC_CONTENT: Collecting lines   │
│    ↓                                │
│ COMMAND_SUB: Inside $(...)          │
│    ↓                                │
│ PARAM_EXPANSION: Inside ${...}      │
└─────────────────────────────────────┘

State Transitions:
NORMAL ──<<──▶ HEREDOC_DELIMITER
       ──$(──▶ COMMAND_SUB
       ──${──▶ PARAM_EXPANSION

COMMAND_SUB ──)──▶ NORMAL
           ──$(──▶ COMMAND_SUB (nested)

PARAM_EXPANSION ──}──▶ NORMAL
                ──$(──▶ COMMAND_SUB
```

## Parser Combinator Integration

```python
# Enhanced word parser with expansions
self.expansion = (
    self.command_substitution
    .or_else(self.parameter_expansion)
    .or_else(self.arithmetic_expansion)
)

self.word_component = (
    self.plain_text
    .or_else(self.expansion)
)

self.word_with_expansions = many1(self.word_component).map(
    lambda parts: Word(parts=parts) if len(parts) > 1 
                  else parts[0]
)

# Enhanced redirection parser
self.redirection = (
    self.file_redirect
    .or_else(self.heredoc_redirect)
    .or_else(self.fd_redirect)
)

# Command with all features
self.simple_command = sequence(
    many1(self.word_with_expansions),
    many(self.redirection)
).map(lambda pair: SimpleCommand(
    args=pair[0],
    redirects=pair[1]
))
```

## Error Recovery Strategies

```
┌────────────────────────────────┐
│   Unclosed Constructs          │
├────────────────────────────────┤
│ $( without )                   │
│   → Error: Unclosed command    │
│     substitution               │
│                                │
│ ${ without }                   │
│   → Error: Unclosed parameter  │
│     expansion                  │
│                                │
│ << without delimiter match     │
│   → Error: Here document       │
│     delimiter 'X' not found    │
└────────────────────────────────┘

Recovery Actions:
1. Clear partial state
2. Synchronize to next statement
3. Report clear error with location
```

## Performance Considerations

```
Optimization Strategies:

1. Token Caching
   ┌─────────────┐
   │ Token Cache │
   ├─────────────┤
   │ $(date)     │──→ Cached result
   │ ${USER}     │──→ Cached result
   └─────────────┘

2. Lazy Evaluation
   - Don't parse substitution content until needed
   - Stream here document content

3. Early Termination
   - Stop parsing on syntax errors
   - Skip expansion in single quotes
```

This visual guide illustrates the complexity and interaction of command substitution, here documents, and parameter expansion features in the parser combinator implementation.