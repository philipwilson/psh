# PSH POSIX Compliance Documentation

This directory contains documentation and analysis of PSH's POSIX compliance.

## Contents

### Core Documents

1. **[posix_spec_reference.md](posix_spec_reference.md)**
   - Key requirements from POSIX.1-2017 specification
   - Shell grammar, built-ins, expansions, and behavior
   - Reference for implementing POSIX features

2. **[posix_compliance_analysis.md](posix_compliance_analysis.md)**
   - Detailed analysis of PSH's current POSIX compliance
   - Feature-by-feature compliance status
   - Identifies gaps and provides recommendations
   - Overall compliance score: ~80%

3. **[posix_compatibility_guide.md](posix_compatibility_guide.md)**
   - Practical guide for writing POSIX-compatible scripts
   - PSH extensions to avoid for portability
   - Migration guide from bash to POSIX
   - Best practices and testing strategies

## Quick Summary

### PSH POSIX Compliance: ~80%

**Strengths:**
- ✅ Core shell grammar (95% compliant)
- ✅ Parameter expansion (90% compliant)
- ✅ I/O redirections (95% compliant)
- ✅ Control structures (100% compliant)
- ✅ Quoting and escaping (100% compliant)

**Gaps:**
- ❌ Missing built-ins: `trap`, `shift`, `exec`, `wait`, `getopts`
- ❌ Signal handling (no `trap` command)
- ⚠️ Some special parameter flags (`$-`)
- ❌ Read-write redirection (`<>`)

**Extensions (Not POSIX):**
- Arrays (indexed and associative)
- Enhanced test `[[ ]]`
- Brace expansion
- Process substitution
- C-style for loops
- Local variables in functions

## Testing POSIX Compliance

### Run Compliance Tests
```bash
# Run POSIX compliance test suite
pytest tests/posix_compliance/

# Run compliance checker script
python scripts/check_posix_compliance.py -v
```

### Test Infrastructure
- `tests/posix_compliance/` - POSIX-specific test suites
- `posix_comparison_framework.py` - Compare PSH with POSIX shells
- `check_posix_compliance.py` - Automated compliance checking

## Improving POSIX Compliance

Priority improvements for better POSIX compliance:

1. **High Priority**
   - Implement `trap` command for signal handling
   - Implement `shift` for positional parameter manipulation
   - Implement `exec` special built-in

2. **Medium Priority**
   - Add `wait` command for process synchronization
   - Implement `getopts` for option parsing
   - Complete `set` command options

3. **Low Priority**
   - Add `<>` read-write redirection
   - Implement remaining built-ins
   - Complete `$-` special parameter

## Resources

- [POSIX.1-2017 Shell Command Language](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html)
- [POSIX Shell and Utilities](https://pubs.opengroup.org/onlinepubs/9699919799/idx/shell.html)
- [Bash POSIX Mode](https://www.gnu.org/software/bash/manual/html_node/Bash-POSIX-Mode.html)