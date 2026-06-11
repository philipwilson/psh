# ModularLexer Developer Guide

## Overview

PSH is transitioning to a new modular lexer architecture that provides better performance and extensibility. This guide explains how to use and test the ModularLexer during development.

## Enabling ModularLexer

### Method 1: Environment Variable
```bash
export PSH_USE_MODULAR_LEXER=true
python -m psh
```

### Method 2: Development Script
```bash
./scripts/dev_with_modular_lexer.sh
```

### Method 3: In Python Code
```python
import os
os.environ['PSH_USE_MODULAR_LEXER'] = 'true'
from psh.shell import Shell
```

## Testing with ModularLexer

### Run Validation Suite
```bash
python scripts/validate_modular_lexer.py
```

### Run Specific Tests
```bash
PSH_USE_MODULAR_LEXER=true python -m pytest tests/test_specific.py
```

### Compare Lexer Outputs
```python
from psh.lexer.core import StateMachineLexer
from psh.lexer.modular_lexer import ModularLexer

# Compare tokenization
input_str = "echo hello $VAR"
old_tokens = StateMachineLexer(input_str).tokenize()
new_tokens = ModularLexer(input_str).tokenize()
```

## Known Differences

### 1. Composite Tokens
- **Old**: `text$VAR` → Single WORD token with parts
- **New**: `text$VAR` → Separate WORD and VARIABLE tokens
- **Impact**: Parser sees more granular tokens

### 2. Keyword Context
- **Issue**: `in` keyword in `for` loops not always recognized
- **Workaround**: Parser handles WORD tokens in keyword positions

### 3. Error Handling
- **Old**: Throws LexerError for unclosed quotes
- **New**: More graceful handling, returns partial tokens
- **Impact**: Better interactive experience

## Performance

The ModularLexer is approximately **1.7x faster** than the original StateMachineLexer:
- Mean performance improvement: ~41%
- Consistent across different input types
- No performance regression cases found

## Architecture Benefits

1. **Modular Design**: Easy to extend with new token types
2. **Pure Functions**: Better testability and predictability
3. **Unified Parsing**: Consistent handling of quotes and expansions
4. **Priority System**: Efficient token recognition dispatch

## Debugging

### Enable Debug Output
```bash
# Show token details
PSH_USE_MODULAR_LEXER=true python -m psh --debug-tokens -c "echo hello"

# Compare lexers side by side
python -c "
import os
from psh.lexer import tokenize

# Test with old lexer
os.environ['PSH_USE_MODULAR_LEXER'] = 'false'
old_tokens = tokenize('echo hello')
print('Old:', [t.type for t in old_tokens])

# Test with new lexer
os.environ['PSH_USE_MODULAR_LEXER'] = 'true'
new_tokens = tokenize('echo hello')
print('New:', [t.type for t in new_tokens])
"
```

### Common Issues

1. **Parameter Expansion**: Fixed - was adding extra `$`
2. **Bracket Depth**: Fixed - now tracks `[[ ]]` correctly
3. **For Loops**: Known issue - `in` tokenized as WORD

## Contributing

When working on lexer-related features:

1. Test with both lexers to ensure compatibility
2. Add tests to `test_lexer_compatibility.py` for new patterns
3. Document any new differences in this guide
4. Run the validation suite before committing

## Migration Timeline

- **Phase A** ✅ Complete: Development and testing
- **Phase B** ✅ Complete: Enable for interactive mode
- **Phase C** ✅ Complete: ModularLexer is now the default
- **Phase D** (Next): Deprecate and remove old lexer

## Using Legacy Lexer

If you need to revert to the old StateMachineLexer for any reason:

```bash
export PSH_USE_LEGACY_LEXER=true
python -m psh
```

Or to disable ModularLexer completely:

```bash
export PSH_USE_MODULAR_LEXER=false
python -m psh
```

## Questions?

- Check `LEXER_COMPATIBILITY_ISSUES.md` for detailed technical differences
- Run `scripts/validate_modular_lexer.py` to test common scenarios
- File issues with the `lexer` label for any problems