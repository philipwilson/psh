# Chapter 17: Differences from Bash

While PSH implements many shell features compatible with Bash, there are important differences due to its educational focus and Python implementation. Understanding these differences helps you write portable scripts and use PSH effectively.

## 17.1 Supported Features Overview

PSH has near-complete compatibility with Bash for core shell programming. Most common Bash scripts run without modification. This section highlights what is fully supported before discussing the remaining gaps. Every "Full support" claim in the compatibility table below is backed by a conformance test that compares PSH against live bash (enforced by `tests/conformance/test_claims_have_tests.py`).

### Shell Options

PSH supports an extensive set of shell options matching Bash behavior:

```bash
# Core error-handling options
set -e              # Exit on error (errexit)
set -u              # Error on undefined variables (nounset)
set -x              # Print commands before execution (xtrace)
set -o pipefail     # Pipeline fails if any command fails

# Additional POSIX/Bash options
set -o allexport    # Export all variables on assignment
set -o braceexpand  # Enable brace expansion (on by default)
set -o noclobber    # Prevent overwriting files with >
set -o noglob       # Disable filename globbing
set -o noexec       # Read commands but do not execute
set -o notify       # Report finished background jobs at the next prompt (see 17.3)
set -o verbose      # Print input lines as they are read
set -o ignoreeof    # Prevent Ctrl-D from exiting the shell
set -o monitor      # Enable job control
set -o posix        # Enable POSIX compliance mode

# Short-form combinations work, including a trailing 'o' that takes
# the next argument as a long option name (as of v0.242.0):
set -eu             # Enable errexit and nounset
set -eux            # Enable errexit, nounset, and xtrace
set -euo pipefail   # Strict mode, exactly like bash

# View all options
set -o              # Show all option settings
set +o              # Show settings as re-enterable commands
```

### Glob Options (shopt)

PSH provides several glob-related options via `shopt`:

```bash
# Available shopt options
shopt -s dotglob     # Include hidden files in glob expansion
shopt -s nullglob    # Non-matching globs expand to nothing
shopt -s globstar    # Enable ** recursive globbing
shopt -s nocaseglob  # Case-insensitive globbing
shopt -s extglob     # Enable extended glob patterns: ?(p) *(p) +(p) @(p) !(p)
shopt globasciiranges # ON by default (bash 5): [a-z] ranges use ASCII bounds
```

### Extended Glob Patterns (extglob)

Extended glob patterns are supported once `extglob` is enabled, in globbing,
`[[ ]]`, and `case`:

```bash
shopt -s extglob
ls !(*.txt)          # Everything except .txt files
[[ abc == @(abc|xyz) ]] && echo match
case "$x" in +(a)) echo "one or more a" ;; esac
```

As in Bash, `extglob` must be enabled *before* the line that uses an extended
pattern is parsed. In a single `-c` string the whole line is parsed at once, so
`shopt -s extglob; ls !(*.txt)` will not work — enable it on an earlier line
(for example in your rc file or a preceding command).

### Regex Matching and BASH_REMATCH

```bash
# The =~ operator matches and populates BASH_REMATCH with capture groups:
[[ "hello123" =~ ([a-z]+)([0-9]+) ]]
echo "${BASH_REMATCH[0]}"   # hello123 (whole match)
echo "${BASH_REMATCH[1]}"   # hello    (group 1)
echo "${BASH_REMATCH[2]}"   # 123      (group 2)
```

### Parameter Transformation Operators (${var@OP})

```bash
x="a b"
echo "${x@Q}"        # 'a b'        - quote for reuse as shell input
echo "${x@U}"        # A B          - uppercase all
echo "${x@u}"        # A b          - uppercase first character
echo "${x@L}"        # a b          - lowercase all
y='a\tb'
echo "${y@E}"        # a<TAB>b      - expand ANSI-C backslash escapes
p='\u@\h'
echo "${p@P}"        # user@host    - prompt-string expansion
echo "${x@A}"        # x='a b'      - assignment/declare form
declare -i n=5
echo "${n@a}"        # i            - attribute-flag letters

# Per-element across arrays and positional parameters:
arr=(one "two three")
echo "${arr[@]@Q}"   # 'one' 'two three'
echo "${arr[@]@A}"   # declare -a arr=([0]="one" [1]="two three")
```

The associative key/value operators `@K` (quoted key/value pairs) and `@k`
(bare key/value pairs) are also supported; associative pairs iterate in
insertion order rather than bash's hash order.

### Arrays and Associative Arrays

```bash
# Indexed arrays
declare -a array=(one two three)
echo ${array[0]}         # First element
echo ${array[@]}         # All elements
echo ${#array[@]}        # Number of elements
fruits=(apple banana cherry)
fruits[3]="orange"       # Add element
fruits+=(grape)          # Append to array
echo ${fruits[@]:1:2}    # Slice from index 1, length 2
echo ${!fruits[@]}       # All indices

# Array element operations
files=(doc.txt img.txt data.txt)
echo ${files[@]/.txt/.bak}  # Replace in all elements
echo ${files[@]^^}          # Uppercase all elements

# Sparse arrays
unset fruits[2]
echo ${!fruits[@]}       # Shows remaining indices

# Associative arrays
declare -A colors=([red]="#FF0000" [green]="#00FF00")
colors[blue]="#0000FF"
echo ${colors[red]}      # Access by key
echo ${!colors[@]}       # All keys
echo ${colors[@]}        # All values
```

### Trap Command

```bash
# Signal handling
trap 'echo "Cleaning up..."' EXIT
trap 'echo "Interrupted"' INT TERM

# List current traps
trap -p
trap -p INT            # Show specific trap

# Reset traps to default
trap - EXIT INT
```

PSH handles standard signals and the `EXIT`, `DEBUG`, `ERR`, and `RETURN`
pseudo-signals (`EXIT`/`DEBUG`/`ERR` as of v0.263.0, `RETURN` as of v0.617;
see 17.2).

### Select Statement

```bash
select option in "Option 1" "Option 2" "Quit"; do
    case $option in
        "Option 1") echo "You chose 1" ;;
        "Option 2") echo "You chose 2" ;;
        "Quit") break ;;
        *) echo "Invalid selection" ;;
    esac
done
```

### Command History

```bash
# The `history` builtin lists previous commands in interactive mode:
history          # Show the whole command history
history 10       # Show the last 10 commands

# History-file synchronization and editing flags are supported:
history -c              # Clear the in-memory history list
history -d 3            # Delete entry 3 (negative counts from the end;
                        #   3-5 deletes a range)
history -w [file]       # Write the whole list to FILE (default: $HISTFILE)
history -r [file]       # Read (append) FILE's lines into the list
history -a [file]       # Append entries new since the last write/append
history -n [file]       # Read only FILE lines not yet read this session
history -s cmd args     # Store "cmd args" as one entry without running it
# `history -p` (expand-and-print without storing) is not supported.
```

History *expansion* is supported in interactive mode: event
designators (`!!`, `!n`, `!-n`, `!string`, `!?string?`), word designators
(`!$`, `!^`, `!*`, `!!:n`, `!!:n-m`), the `:h`/`:t`/`:r`/`:e`/`:s`/`:g&`/`:p`
modifiers, and `^old^new` quick substitution all match bash. The `:q`/`:x`
word-quoting modifiers and the `!#` (current-line) event designator are not
yet supported.

### Job Control

PSH provides full job control in interactive mode including `disown`:

```bash
# All standard job control
jobs           # List jobs
fg %1          # Bring job to foreground
bg %1          # Resume job in background
wait           # Wait for background jobs
kill %1        # Send signal to job
disown %1      # Remove job from job table
disown -h %1   # Mark job to not receive SIGHUP
disown -a      # Remove all jobs
```

For an ambiguous `%prefix` (one matching more than one job), PSH prints
`ambiguous job spec` followed by `no such job` and returns 1 in every mode —
this matches **interactive** bash. Bash is mode-inconsistent here: a
non-interactive `bash -c` prints only the `ambiguous job spec` line and returns
0. PSH deliberately renders the interactive-style diagnostic regardless of mode.

### Process Substitution

```bash
# Input process substitution
diff <(sort file1.txt) <(sort file2.txt)

# Output process substitution
echo "data" | tee >(grep pattern > matches.txt)
```

### mapfile / readarray

```bash
# Read lines of input into an indexed array (readarray is a synonym):
mapfile -t lines < file.txt        # -t strips trailing newlines
readarray -t lines < file.txt
echo "${lines[0]} (${#lines[@]} lines)"

# Options: -d delim, -n count, -O origin (no clear), -s skip, -t, -u fd.
mapfile -t -s 1 -n 2 first_two < data.txt
```

The `-C callback` / `-c quantum` options are not supported.

### let

```bash
# Evaluate arithmetic expressions (equivalent to ((...)) per argument):
let x=5+3              # x=8
let "a = 2" "b = a+1" # b=3; side effects apply (++x, x+=2, etc.)
let "count > 0"       # exit 0 if the last expression is non-zero, else 1
```

### Name References and Indirect Expansion

```bash
# Namerefs (declare -n / local -n): a variable that refers to another by name.
x=5
declare -n r=x
echo "$r"             # 5      (read-through)
r=9; echo "$x"        # 9      (write-through; creates the target if unset)
declare -n a=b b=c    # chains resolve transitively
echo "${!r}"          # x      (for a nameref, ${!r} is the target NAME)

# Pass-by-reference into functions:
inc() { local -n n=$1; n=$((n + 1)); }
count=5; inc count; echo "$count"   # 6

# unset follows the nameref; unset -n removes the nameref itself:
unset r               # unsets the target (x)
unset -n r            # unsets the nameref, leaving the target

# Classic indirect expansion (when the name is NOT a nameref):
name=HOME
echo "${!name}"       # value of $HOME
```

Namerefs may also target an array element:

```bash
arr=(p q r)
declare -n e=arr[1]
echo "$e"             # q
e=Q; echo "${arr[@]}" # p Q r
```

## 17.2 Unimplemented Features

The following Bash features are not available in PSH.

### Coprocesses

```bash
# NOT implemented
coproc { command; }           # Command not found
coproc NAME { command; }      # Command not found
```

### RETURN Traps

```bash
# EXIT, DEBUG, ERR, and RETURN all fire (DEBUG before each simple command;
# ERR after failures, with the same exemptions as set -e). RETURN fires at
# every function return and end of `source`, honoring bash's hiding model
# (hidden for a function's extent unless `set -T` / `declare -ft`):
trap 'echo ret' RETURN
f(){ trap 'echo ret' RETURN; }; f   # prints: ret
# Deliberate divergence: a `return N` *inside* the RETURN action adopts N
# once here; bash 5.2 recurses forever on that construct.
```

### Programmable Completion

```bash
# The complete/compgen builtins do not exist
complete -F _my_func mycommand  # Command not found
compgen -W "words" -- prefix    # Command not found

# Basic tab completion for files and directories IS available in
# interactive mode; command-name and variable-name completion are not.
```

### Missing Builtins

```bash
# These Bash builtins are not available:
caller                       # Call-stack introspection - not a builtin
```

(`let`, `mapfile`, and `readarray` **are** supported — see 17.1.)

### Read Builtin Limitations

```bash
# The read builtin supports -r, -d, -p, -t, -n, -N, -s, -a, and -u:
read -r var             # Raw mode (no backslash processing)
read -d ':' var         # Custom delimiter
read -p "prompt: " var  # Prompt (interactive only)
read -t 5 var           # Timeout
read -n 4 var           # Read up to N characters
read -N 4 var           # Read EXACTLY N characters
read -s var             # Silent mode (passwords)
read -a arr             # Read words into an array
read -u 3 var           # Read from file descriptor 3

# Only the readline-editing options are unsupported:
read -e var             # Error: invalid option (readline line editing)
read -i text var        # Error: invalid option (initial readline text)
```

### Other Missing Features

```bash
# wait -n (wait for any single job)
wait -n                 # Waits for the next background job to finish

# time keyword (reserved word; times pipelines/compounds, default & -p formats)
time echo hello         # Times the command; `time while ...; done`, `time { ...; }` work too
TIMEFORMAT='elapsed=%R'; time echo hi   # Custom TIMEFORMAT is honored (%R/%U/%S/%P, %l long form, empty = no report)

# Call-stack introspection arrays
echo ${BASH_SOURCE[0]}  # Not available (empty)
echo ${BASH_LINENO[0]}  # Not available (empty)

# FUNCNAME itself IS fully populated for nested function calls:
a() { b; }; b() { c; }
c() { echo "${FUNCNAME[@]}"; }
a                       # c b a — same as bash
# Only the bash-specific base frames are missing: bash appends `main`
# for the top-level script frame and `source` frames for sourced files
# (they arrive with the BASH_SOURCE/BASH_LINENO work), so in a script
# bash prints `c b a main` where PSH prints `c b a`.
```

## 17.3 Behavioral Differences

Some features work differently in PSH compared to Bash.

### Alias Expansion in Scripts

PSH deliberately keeps alias expansion ON in every mode; bash turns the
`expand_aliases` shopt option off in non-interactive shells (scripts and
`-c` strings):

```bash
# In a script or with -c:
alias ll='ls -la'
ll          # PSH: runs ls -la      bash: ll: command not found

# bash needs an explicit opt-in (and the alias on an EARLIER line):
shopt -s expand_aliases

# PSH supports the reverse toggle — turn expansion off for
# subsequently parsed commands, exactly like bash's option:
shopt -u expand_aliases
ll          # command not found in both shells
shopt -s expand_aliases   # ...and back on

# One further PSH nicety: an alias defined on the SAME line can be used
# immediately. Bash never expands it (the line was read before the
# alias command ran):
alias hi='echo hello'; hi   # PSH: hello    bash: hi: command not found
```

This is an intentional educational choice (aliases behave the same
everywhere, so examples work in scripts), not an oversight. If you are
porting a PSH script to bash, either add `shopt -s expand_aliases` near
the top or replace aliases with shell functions (which bash expands in
all modes).

### Background Job Notification Timing (`set -o notify`)

`set -b` / `set -o notify` reports the completion of a background job
*before the next prompt* in PSH. Bash reports it *immediately* — the
instant the child is reaped, interrupting an idle prompt line to print the
`[N]+  Done` notice asynchronously. PSH cannot match that immediacy while
it is blocked in the line editor waiting for a keystroke: the editor's
`select()` multiplexes only standard input and the terminal-resize pipe,
not the `SIGCHLD` self-pipe, so a completion that arrives while you sit at
an empty prompt is announced at the next reaping opportunity (the next
command boundary) rather than the moment it happens. Without `notify`, PSH
already reports completions at the next prompt, so in practice the two
notify states differ only in that `notify` also announces a job reaped by
an in-progress `wait` immediately. Making the notice truly immediate would
require a line-editor redesign to watch the `SIGCHLD` pipe; it is
deliberately out of scope.

The completion-notice marker itself is now bash-faithful: psh marks a
finishing background job `[N]+  Done …` only when it is the current job
(`%+`), and `[N]   Done …` (a blank marker, never `-`) otherwise. A
foreground command no longer overwrites the background job's `%+`, so a bg
job keeps its current/previous (`%+`/`%-`) standing across intervening
foreground commands — matching bash for `jobs`, `kill %+`, `wait %+`, and
bare `fg`/`bg`.

### Quote Handling

```bash
# Single quote handling follows POSIX rules:
echo 'It'"'"'s a test'  # Concatenate quoted strings
echo "It's a test"      # Use double quotes
echo 'It'\''s a test'   # End-quote, escaped quote, start-quote
```

### Variable Assignment

```bash
# PSH follows Bash rules for variable assignment:
VAR=value         # Correct - no spaces around =
VAR= value        # Sets VAR to empty, then runs "value" as command
VAR =value        # Tries to run "VAR" as command with arg "=value"
```

### Temporary-Environment Prefix Assignments (`VAR=x cmd`)

A `VAR=x cmd` prefix over a builtin or external command places `VAR` in a
*separate temporary environment* for that command's duration, exactly as bash
does: name lookup consults it but whole-table enumerations skip it, and it is
not a shell variable.

```bash
V=hi env | grep '^V='          # V=hi        (in the child's environment)
V=hi printf '%s\n' "$V"        # (empty)     — the command's own words expand first
V=hi declare -p V              # declare -x V="hi"          (name lookup sees it)
FOO=bar export -p | grep FOO   # (nothing)   — enumerations do NOT list it
FOO=bar set | grep '^FOO='     # (nothing)
declare -i n=5; n=abc env      # n=abc in the env — NOT a shell var, so no -i
W=1 true; echo "${W-unset}"    # unset       — temporary
V=hi export V; declare -p V    # declare -x V="hi" — export PROMOTES it (persists)
```

Because the binding is not a shell variable it does not inherit a shadowed
variable's attributes; a plain assignment inside an `eval`'d body updates the
temporary binding (discarded afterward) and `unset` peels it to reveal the
shell variable underneath. Naming the binding with `export` / `readonly`
promotes it to a real, persistent variable (the temporary value wins over any
existing same-name variable).

The one remaining difference is a deep corner: when the prefixed command is
`eval` (or `source`) whose body then runs a *whole-table enumerator*, bash makes
the outer prefix visible to that nested enumeration (`FOO=bar eval 'export -p'`
lists `FOO`), asymmetrically — a nested inner prefix is still hidden. PSH
consistently hides the temporary environment from all enumerations. This is
vanishingly rare in practice.

### Identifier (Name) Rules — Unicode Extension

A single policy decides what counts as a valid variable/function *name*
everywhere it matters — assignments, `declare`/`export`/`readonly`/`local`,
`read`, `for`, function definitions, and `${NAME}`. Bash restricts names to the
POSIX/ASCII set `[A-Za-z_][A-Za-z0-9_]*` in every mode. PSH is more lenient by
default:

```bash
# DEFAULT MODE — PSH accepts Unicode-letter names (a deliberate extension):
é=1;      echo "$é"          # PSH: 1     | Bash: "é=1: command not found"
naïve=hi; echo "$naïve"      # PSH: hi    | Bash: rejects
for π in a b; do echo $π; done   # PSH: loops | Bash: "not a valid identifier"

# Names that never start legally are rejected by BOTH shells, in BOTH modes:
9x=1                         # command not found (9 is not a name start)
a-b=1                        # command not found

# POSIX MODE restores bash's ASCII-only rule exactly:
set -o posix
é=1                          # not an assignment -> "é=1: command not found"
declare é=1                  # declare: `é=1': not a valid identifier (status 1)
read é                       # read: `é': not a valid identifier (status 1)
foo=1; echo $foo             # plain ASCII names still work (1)
```

So the *only* behavioral change `set -o posix` makes to names is switching
OFF the Unicode extension; ASCII names behave identically in both modes.

Note on `for`/`function` error flow: in DEFAULT mode both shells simply report
"not a valid identifier" (status 1) and CONTINUE — PSH matches bash here. The
flow differs only under `set -o posix`: bash then treats the invalid name as a
*parse* error and aborts the whole input (exit 2), whereas PSH — which parses the
entire program before executing, so a runtime `set -o posix` cannot influence
parsing — still rejects it at *execution* time (status 1) and continues. Both
reject the name; only the posix abort-vs-continue flow differs.

### Case Modification and Unicode

The case-mods `${var^}` `${var^^}` `${var,}` `${var,,}` `${var~}` `${var~~}`
(and the `declare -u`/`-l` attributes) map each character to at most one
character, so they never change a string's length — `${x^^}` on `straße`
gives `STRAßE`, not `STRASSE`. This matches bash, and is the fix for a former
PSH bug where `ß` expanded to `SS`.

PSH's case conversion is **locale-gated**, like bash: in a `*.UTF-8` locale it
is Unicode-aware (`${x,,}` on `İ` yields `i`; accented letters, Greek, and
Cyrillic map correctly), while in the `C`/`POSIX` locale it maps ASCII only and
leaves every non-ASCII codepoint unchanged (`${x^^}` on `café` is `CAFé`, as in
bash-C). The two shells can still differ on rare/recent codepoints (titlecase
digraphs like `ǅ`, polytonic Greek, Roman numerals, circled letters), which are
host-libc-dependent in bash itself. See "Locale Support" below.

### Locale Support (LC_CTYPE / LC_COLLATE)

PSH resolves the effective locale from the environment — bash's precedence
`LC_ALL > LC_{CTYPE,COLLATE} > LANG`, empty values skipped, an unusable name
warned-and-ignored (falling back to `C`) — at startup **and again whenever
`LC_ALL`/`LC_CTYPE`/`LC_COLLATE`/`LANG` is assigned, unset, or laid over a
command (`LC_ALL=C cmd`)**, exactly like bash's reactive special variables. It
honours the effective locale for:

- **Collation** (`LC_COLLATE`): glob-result ordering (`echo *`) and the
  `[[ < ]]` / `[[ > ]]` string comparisons use `strcoll`/`strxfrm`, so under a
  UTF-8 locale `echo *` is dictionary-ordered and `[[ a < B ]]` is true, matching
  bash. (bash's `test`/`[` `<`/`>` use byte order in *every* locale — PSH matches
  that too.)
- **Case conversion** (`LC_CTYPE`): see above.
- **POSIX character classes** (`LC_CTYPE`): `[[:alpha:]]`, `[[:digit:]]`, etc.
  in `[[ == ]]`, `case`, `${var#pat}`, `[[ =~ ]]`, and pathname expansion match
  according to the locale (so `[[ é == [[:alpha:]] ]]` is true under a UTF-8
  locale). Membership is resolved through the host C library's `iswctype`, so it
  is byte-faithful to the same `bash` on the same machine — including places
  where platforms genuinely disagree (macOS treats `٣`/`３` as `[[:digit:]]`;
  glibc does not).

`shopt globasciiranges` is recognized and defaults **on** (bash 5): bracket
*ranges* like `[a-z]` use ASCII/codepoint bounds regardless of locale.

**Deliberate limitations** (documented differences):

- **`shopt -u globasciiranges`** (collation-ordered ranges in a UTF-8 locale) is
  accepted but its off-behaviour is not implemented; ranges stay ASCII.
- **Non-UTF-8 8-bit locales** (e.g. `ISO8859-1`): collation is honoured, but
  character classes and case fall back to ASCII tables (full 8-bit ctype
  fidelity is a non-goal).
- **Byte vs. character model.** In the `C` locale bash processes input as
  *bytes*, so a multibyte character like `é` counts as two "characters"
  (`[[ é == ?? ]]` is true in bash-C). PSH is Unicode-native — `é` is always one
  character — so single-character patterns (`?`, `[^[:digit:]]`) can differ from
  bash in the `C` locale. This is a pre-existing shell-wide model difference, not
  specific to character classes. The same principle governs `read`/`mapfile`
  counts and delimiters: `read -N1`/`-n1` reads one *character* (a multibyte `é`
  arrives whole, not split across two reads), and `read -d`/`mapfile -d` treats
  the first *character* of the delimiter argument as the terminator. bash, by
  contrast, terminates on the first *byte* of the `-d` argument, so a multibyte
  delimiter like `-d é` splits on `0xC3` and leaves the trailing `0xA9` byte
  stuck to the next field; PSH splits on the whole character. For the ordinary
  ASCII delimiters (newline, `:`, `,`, `;`, NUL) byte and character coincide, so
  this only surfaces with a multibyte `-d` delimiter.
- **PEP 538 residual (`PYTHONUTF8`).** In a bare or `LANG=C` environment
  CPython's PEP 538 coercion rewrites `LC_CTYPE` to a UTF-8 target before PSH
  starts; PSH detects and strips that phantom, so it presents bash's C locale
  under those environments — `[[ é == [[:alpha:]] ]]` is false, `$LC_CTYPE` is
  empty, and no `LC_CTYPE` is passed to children, all matching bash. The strip
  follows a conservative provenance rule: it fires only when the coercion is
  *provable*. A nonempty inherited `LC_ALL` (which disables CPython's
  coercion), `PYTHONCOERCECLOCALE=0`, or an explicit UTF-8-mode request
  (`PYTHONUTF8=1` / `-X utf8`) each mark the inherited `LC_CTYPE` as genuine
  (or unknowable), and PSH then KEEPS it exactly as bash does. The one
  residual is the unknowable corner: under an explicit `PYTHONUTF8=1` (or
  `PYTHONUTF8=0`, which leaves `utf8_mode` off while the coercion still
  rewrites the environment) in an otherwise effectively-C environment the
  coercion still runs, and PSH keeps the resulting `LC_CTYPE` where bash
  (never seeing it) shows nothing.
  `PYTHONUTF8` is a Python runtime knob, not a shell-user path; every pure
  shell-visible environment — including `LC_ALL=C` combined with an inherited
  terminal `LC_CTYPE` — is fully bash-faithful.

### Here Document Behavior

```bash
# Tab suppression with <<- works correctly:
cat <<-EOF
	This has a tab
	This too
EOF
# Output has leading tabs removed

# Quoted vs unquoted delimiter:
cat <<'EOF'      # No expansion
$HOME
EOF

cat <<EOF        # With expansion
$HOME
EOF
```

### Permanent `exec` fd close, then reopen

Closing a standard descriptor with `exec >&-` (or `exec 2>&-`) and later
reopening it is handled to bash parity for command **output**:

```bash
exec 3>&1; exec >&-; echo LEAK; exec >&3 3>&-; echo end   # -> only `end`
```

The `echo LEAK` write fails (`write error: Bad file descriptor`) and is
discarded; it never reappears when fd 1 is reopened — matching bash. A
compound or function body that reopens the fd for its own duration still works
(`exec 1>&-; f(){ echo a; }; f 1>&2` prints `a` on stderr).

**Deliberate divergence — buffered *diagnostics* across a stderr close+reopen.**
When a builtin's *error message* (not its normal output) is written to a stderr
closed with `exec 2>&-` and stderr is then reopened, bash resurrects the
buffered message onto the reopened descriptor (a C-stdio buffering artifact):

```bash
exec 3>&2; exec 2>&-; cd /nonexistent; exec 2>&3 3>&-; echo end >&2
# bash stderr:  end<newline>cd: /nonexistent: No such file or directory
# psh  stderr:  end
```

psh writes diagnostics straight to the descriptor, so a message that cannot be
delivered (the fd is closed) is simply lost rather than re-emitted onto whatever
later reuses that descriptor. Normal command output never leaks in either shell.

### Script on Standard Input

When psh reads its script from standard input — `cmds | psh`, `psh < file`, or
`psh -s` — it reads fd 0 lazily, one command's lines at a time, exactly like
bash. A `read`, `cat`, or `mapfile` inside the script therefore consumes the
*subsequent* physical lines as data, because the shell's command source and the
runtime input are the same lazily-consumed descriptor:

```bash
printf '%s\n' 'read a' 'X' 'echo got:$a' | psh   # -> got:X  (read ate the 'X' line)
printf '%s\n' 'echo START' 'cat' 'echo END' | psh  # -> START then 'echo END' (cat's data)
```

**Deliberate divergence — `mapfile` on a *seekable* stdin (`psh < file`).**
`mapfile`/`readarray` with no line count reads to end-of-file. On a seekable fd,
bash reads `mapfile` from the *end* of the file (it captures nothing and the
rest of the script runs as commands) — a bash quirk that is inconsistent with
bash's own `read`, `read -d ''`, and `cat` on the same seekable fd, and with its
own `mapfile` on a *pipe*. psh is internally consistent instead: `mapfile`
shares the fd position like every other consumer, on a seekable file and a pipe
alike, so it captures the remaining lines. (On a pipe, psh and bash agree.)

### Debug Option Runtime Behavior

```bash
# Command-line debug flags produce visible output:
psh --debug-ast -c 'echo hello'     # Shows AST tree
psh --debug-tokens -c 'echo hello'  # Shows token list

# Runtime set -o debug-* options can be set but
# some may not produce the same output format:
set -o debug-expansion   # Works - shows expansion trace
set -o debug-exec        # Works - shows execution trace
set -o debug-ast         # Can be set but may not produce output
set -o debug-tokens      # Can be set but may not produce output

# Use command-line flags for reliable debug output
```

### Recursion Depth

```bash
# PSH has limited recursion depth due to Python's call stack
# Deep recursion that works in Bash may fail in PSH:

factorial() {
    local n=$1
    if [ $n -le 1 ]; then
        echo 1
    else
        echo $((n * $(factorial $((n - 1)))))
    fi
}
factorial 1000  # May fail with stack overflow

# Workaround: Use iteration
factorial_iter() {
    local n=$1 result=1
    while [ $n -gt 1 ]; do
        result=$((result * n))
        n=$((n - 1))
    done
    echo $result
}
```

### Brace Expansion Item Limit

Bash imposes no limit on brace expansion. As a resource guard (like the
recursion-depth limit above), PSH caps a single brace expansion at 100,000
generated items. Ordinary bash-style usage is unaffected and matches bash
exactly — even large ranges such as `{1..20000}` (108,894 bytes) or
`{1..100000}` expand normally. Only a genuinely runaway expansion is rejected,
and it fails **loudly and immediately** — PSH computes the cardinality before
generating, so a pathological range is an O(1) diagnostic, not a hang:

```bash
echo {1..100000}          # Works (matches bash)
echo {1..1000000000}      # PSH: error, exit 2 (bash would try to build it)
# psh: brace expansion: 1000000000 items exceeds the limit of 100000
```

This is a deliberate divergence: bash would attempt the full (enormous)
expansion. PSH never silently falls back to the literal text on overflow.

## 17.4 PSH-Specific Features

PSH includes features not found in Bash, designed for education and development.

### Debug Flags

```bash
# Command-line debug flags
psh --debug-ast script.sh           # Show parsed AST before execution
psh --debug-ast=tree script.sh      # Tree format (default)
psh --debug-ast=compact script.sh   # Compact format
psh --debug-ast=sexp script.sh      # S-expression format
psh --debug-ast=dot script.sh       # Graphviz DOT format
psh --debug-tokens script.sh        # Show tokenization
psh --debug-scopes script.sh        # Show variable scope operations
psh --debug-expansion script.sh     # Show expansion process
psh --debug-expansion-detail script.sh  # Detailed expansion steps
psh --debug-exec script.sh          # Show execution flow
psh --debug-exec-fork script.sh     # Show fork/exec details

# Runtime debug options (via set -o)
set -o debug-expansion    # Enable expansion tracing
set -o debug-exec         # Enable execution tracing
set -o debug-parser       # Enable parser tracing

# Custom PS4 for xtrace
PS4='[trace] '
set -x
echo hello               # Shows: [trace] echo hello
```

### Script Analysis Tools

```bash
# Validate script without executing
psh --validate script.sh    # Check for parse errors

# Format script
psh --format script.sh      # Pretty-print formatted script

# Lint analysis
psh --lint script.sh        # Check for common issues

# Security analysis
psh --security script.sh    # Check for security concerns

# Code metrics
psh --metrics script.sh     # Show complexity and statistics
```

### Parser Selection

```bash
# PSH includes two parsers for educational comparison:
psh --parser rd script.sh         # Recursive descent (default)
psh --parser combinator script.sh # Combinator parser (experimental)

# Switch at runtime (interactive mode):
parser-select combinator
parser-select rd
```

### Shell Version Detection

```bash
# PSH sets PSH_VERSION (not BASH_VERSION):
echo $PSH_VERSION    # Shows: 0.221.0

# Detect PSH:
if [ -n "$PSH_VERSION" ]; then
    echo "Running in PSH $PSH_VERSION"
fi
```

## 17.5 Feature Compatibility Reference

| Feature | Bash | PSH | Notes |
|---------|------|-----|-------|
| **Basic Features** |
| Command execution | Yes | Yes | Full support |
| Pipelines | Yes | Yes | Full support |
| I/O redirection | Yes | Yes | All forms supported |
| Background jobs | Yes | Yes | Interactive only |
| Subshells | Yes | Yes | Full support |
| **Variables** |
| Simple variables | Yes | Yes | Full support |
| Arrays | Yes | Yes | Full support |
| Associative arrays | Yes | Yes | Full support |
| Local variables | Yes | Yes | Full support |
| Variable attributes | Yes | Yes | declare -i, -r, -x, etc. |
| **Expansions** |
| Parameter expansion | Yes | Yes | All features |
| Command substitution | Yes | Yes | Both $() and backticks, including `case` statements with bare `pattern)` forms inside `$()` |
| Arithmetic expansion | Yes | Yes | Full support |
| Brace expansion | Yes | Yes | Full support |
| Process substitution | Yes | Yes | Full support |
| Tilde expansion | Yes | Yes | Full support |
| Case modification | Yes | Yes | ${var^^}, ${var,,}, ${var~~} toggle, patterns, arrays; length-safe Unicode |
| **Control Structures** |
| if/then/else/fi | Yes | Yes | Full support |
| while/until/do/done | Yes | Yes | Full support |
| for/do/done | Yes | Yes | Full support |
| C-style for loops | Yes | Yes | Full support |
| case/esac | Yes | Yes | Full support |
| select | Yes | Yes | Full support |
| Arithmetic commands (( )) | Yes | Yes | Full support |
| Control structures in pipelines | Yes | Yes | Full support |
| **Functions** |
| Function definition | Yes | Yes | Both syntaxes |
| Local variables | Yes | Yes | Full support |
| Return values | Yes | Yes | Full support |
| **Job Control** |
| jobs command | Yes | Yes | Interactive only |
| fg/bg commands | Yes | Yes | Interactive only |
| Job specifications | Yes | Yes | %1, %+, %-, %string |
| wait builtin | Yes | Yes | Full support |
| disown builtin | Yes | Yes | Full support |
| **Shell Options** |
| set -e (errexit) | Yes | Yes | Full support |
| set -u (nounset) | Yes | Yes | Full support |
| set -x (xtrace) | Yes | Yes | Full support |
| set -o pipefail | Yes | Yes | Full support |
| set -o noclobber | Yes | Yes | Full support |
| set -o allexport | Yes | Yes | Full support |
| set -o noglob | Yes | Yes | Full support |
| set -o verbose | Yes | Yes | Full support |
| set -o posix / POSIXLY_CORRECT | Yes | Yes | Full support (posix mode via `set -o posix`, the `--posix` startup flag, or the `POSIXLY_CORRECT` variable/environment; two-way coupled to `POSIXLY_CORRECT` like bash — enabling binds it to `y`, disabling unsets it) |
| **Signal Handling** |
| trap command | Yes | Yes | Standard signals + EXIT/DEBUG/ERR/RETURN |
| Signal handling | Yes | Yes | All standard signals |
| DEBUG/ERR/RETURN traps | Yes | Full support | DEBUG/ERR (v0.263) + RETURN (v0.617); RETURN honors bash's hiding model (`set -T`/`declare -ft`). Deliberate divergence: a `return N` *inside* a RETURN action adopts N once (bash 5.2 recurses forever). |
| **Advanced Features** |
| Here documents | Yes | Yes | Full support |
| Here strings | Yes | Yes | Full support |
| Enhanced test [[ ]] | Yes | Yes | Full support |
| Regex matching =~ | Yes | Yes | BASH_REMATCH capture groups populated |
| eval builtin | Yes | Yes | Full support |
| getopts builtin | Yes | Yes | Full support |
| printf builtin | Yes | Yes | Full support (incl. %q) |
| pushd/popd/dirs | Yes | Yes | Full support |
| shopt options | Yes | Partial | checkhash, dotglob, expand_aliases, extglob, failglob, globstar, inherit_errexit, nocaseglob, nocasematch, nullglob |
| Extended glob patterns | Yes | Yes | ?() *() +() @() !() (enable extglob before the line) |
| read options | Yes | Partial | -r -d -p -t -n -N -s -a -u supported; -e/-i (readline editing) not |
| command history (`history`) | Yes | Yes | Listing (interactive) + file-sync/edit flags -c/-d/-w/-r/-a/-n/-s; -p (expand-and-print) not supported |
| Aliases | Yes | Yes | Expanded in scripts/`-c` too by default (bash: interactive-only); `shopt -u expand_aliases` disables — see 17.3 |
| History expansion (!!, !n) | Yes | Yes | Full support for interactive event/word designators + :h/:t/:r/:e/:s/:g& modifiers + ^old^new; :q/:x modifiers and !# designator not yet supported |
| Coprocesses | Yes | No | Not implemented |
| Programmable completion | Yes | No | Basic tab completion only |
| Namerefs (declare -n / local -n) | Yes | Yes | Scalar and array-element targets; chains; local -n |
| Indirect expansion ${!var} | Yes | Yes | Scalar; ${!arr[@]} indices and ${!prefix*}/${!prefix@} name-listing all work |
| Parameter transforms ${var@Q/U/u/L/E/P/A/a} | Yes | Yes | Scalar, array, and positional |
| Assoc key/value transforms ${var@K} / ${var@k} | Yes | Yes | Full support (assoc pairs iterate in insertion order, not bash hash order) |
| ulimit builtin | Yes | Yes | Full support for every resource Python's `resource` module exposes (-c/-d/-f/-l/-m/-n/-s/-t/-u/-v and Linux -e/-i/-q/-r/-x), soft/hard via -S/-H, keywords `unlimited`/`hard`/`soft`, and -a; the non-rlimit pipe size -p is unsupported. Sets the psh process's own limits (inherited by children), unlike the external binary psh formerly fell through to |
| let builtin | Yes | Yes | Equivalent to ((...)) per argument |
| mapfile/readarray | Yes | Yes | -d/-n/-O/-s/-t/-u (no -C/-c) |
| caller builtin | Yes | No | Not implemented |
| BASH_SOURCE / BASH_LINENO | Yes | No | Not populated |
| FUNCNAME | Yes | Yes | Full support (nested call stack, `c b a`); only the bash `main`/`source` base frames are absent — they arrive with BASH_SOURCE/BASH_LINENO |
| wait -n | Yes | Yes | Waits for the next job; `-n` / `-p VAR` |
| time keyword | Yes | Yes | Full support (times pipelines/compounds; default, `-p`, and custom `TIMEFORMAT` formats) |
| ${!prefix*} name matching | Yes | Yes | Full support |
| **PSH-Specific** |
| --debug-ast | No | Yes | Multiple output formats |
| --debug-tokens | No | Yes | PSH only |
| --debug-scopes | No | Yes | PSH only |
| --debug-expansion | No | Yes | PSH only |
| --validate | No | Yes | Syntax validation |
| --format | No | Yes | Script formatting |
| --lint | No | Yes | Lint analysis |
| --security | No | Yes | Security analysis |
| --metrics | No | Yes | Code metrics |

## 17.6 Writing Portable Scripts

When writing scripts that need to work in both PSH and Bash, follow these guidelines.

### Stick to Common Features

```bash
#!/bin/sh
# For maximum portability, use POSIX features:

# POSIX test command
if [ -f "$file" ]; then
    echo "File exists"
fi

# Standard arithmetic
result=$((a + b))

# For PSH+Bash portability, these features are safe:
# - [[ ]] enhanced test, including =~ with BASH_REMATCH capture groups
# - (( )) arithmetic commands
# - Arrays and associative arrays
# - Process substitution <() and >()
# - Parameter expansion (all forms, incl. ${var^^}/${var,,} case mod)
# - Brace expansion (including expansion items like {$((1)),$((2))})
# - Extended glob patterns (with shopt -s extglob enabled beforehand)
# - Here documents and here strings
# - trap command (standard signals + EXIT/DEBUG/ERR/RETURN)
# - All control structures
```

### Detect the Shell

```bash
#!/bin/sh
# Detect which shell is running
if [ -n "$BASH_VERSION" ]; then
    echo "Running in Bash $BASH_VERSION"
elif [ -n "$PSH_VERSION" ]; then
    echo "Running in PSH $PSH_VERSION"
else
    echo "Unknown shell"
fi
```

### Strict Mode Portability

```bash
# Bash strict mode works identically in PSH (as of v0.253.0):
set -euo pipefail

# errexit honours the POSIX exemptions exactly as bash does:
# if/while/until conditions, non-final && / || members, and ! negation
# do not trigger an exit; subshells inherit set -e and $?.
# Command substitutions clear set -e in the child, as in bash:
# `set -e; x=$(false; echo hi)` sets x=hi. Use `shopt -s inherit_errexit`
# (or POSIX mode) to keep set -e inside $(...).
```

## 17.7 Migration Guide

### From Bash to PSH

Most Bash scripts work without modification. Check for these issues:

```bash
# 1. Check for unsupported builtins / features
grep -E 'coproc|complete |compgen |caller' script.sh
grep -E 'read .*-[ei]' script.sh              # read -e/-i (readline editing) unsupported
# (EXIT/DEBUG/ERR/RETURN traps all fire as of v0.617 — no trap migration needed.)
```

### Script Compatibility Checklist

```bash
#!/usr/bin/env psh
# PSH v0.221.0 Compatibility Checklist

# Fully supported:
# - Variables, arrays, associative arrays
# - All control structures (if, while, for, case, select)
# - C-style for loops
# - Functions with local variables
# - Command substitution $() and backticks
# - Process substitution <() and >()
# - All I/O redirection forms (incl. arithmetic fd targets, e.g. >&$((n)))
# - Parameter expansion (most bash forms; case mod ${var^^}/${var,,};
#   transforms ${var@Q/U/u/L/E/P/A/a})
# - Arithmetic expansion and commands
# - Brace expansion, incl. expansion items {$((1)),$((2))} and ranges
# - Extended glob patterns (shopt -s extglob, enabled beforehand)
# - Regex matching =~ with BASH_REMATCH capture groups
# - Job control (jobs, fg, bg, wait, disown)
# - Shell options (errexit, nounset, xtrace, pipefail, etc.)
# - eval, trap (standard signals + EXIT + DEBUG + ERR), getopts, printf (incl. %q)
# - read -r/-d/-p/-t/-n/-N/-s/-a/-u
# - Subshells with variable isolation
# - Control structures in pipelines
# - Here documents and here strings
# - shopt: checkhash, dotglob, expand_aliases, extglob, failglob, globstar,
#   inherit_errexit, nocaseglob, nocasematch, nullglob
# - pushd, popd, dirs
# - history builtin (interactive)
# - History expansion (interactive): !!, !n, !-n, !str, !?str?, word
#   designators (!$, !!:1, !!:*), :h/:t/:r/:e/:s/:g& modifiers, ^old^new
# - mapfile / readarray (-d/-n/-O/-s/-t/-u)
# - let (arithmetic evaluation)
# - namerefs (declare -n / local -n), scalar & array-element targets; ${!var}
# - FUNCNAME call stack (nested function frames, innermost first)
# - aliases — NOTE: expanded in scripts too (bash needs shopt -s expand_aliases)
# - ${!prefix*} / ${!prefix@} variable-name prefix matching
# - Associative key/value transforms ${var@K} / ${var@k}
#   (assoc pairs iterate in insertion order, not bash hash order)
# - EXIT/DEBUG/ERR/RETURN pseudo-signal traps (RETURN honors bash's
#   set -T / declare -ft hiding model)

# Not supported:
# - History expansion :q/:x word-quoting modifiers and the !# event designator
# - Coprocesses (coproc)
# - Programmable completion (complete, compgen)
# - caller builtin
# - read -e / read -i (readline line editing)
# - BASH_SOURCE/BASH_LINENO (and FUNCNAME's `main`/`source` base frames;
#   the nested function call stack in FUNCNAME IS fully populated)
# - Very deep recursion (Python stack limits)
```

## 17.8 Design Philosophy

PSH is built with educational priorities:

```
1. Code clarity over performance
2. Educational value over feature completeness
3. Correct behavior over optimization
4. Helpful errors over terse messages
5. Built-in debugging over external tools
```

This means:
- Some rarely-used Bash features may never be implemented
- Error messages are more descriptive than Bash
- Built-in debugging tools (AST, token, expansion tracing) provide visibility into shell internals
- The Python implementation enables script analysis tools (lint, security, metrics) not available in Bash
- Performance is adequate for interactive use and scripting but not optimized for high-throughput workloads

## Summary

PSH v0.221.0 provides near-complete Bash compatibility for everyday shell programming:

1. **Comprehensive Feature Support**: Arrays, associative arrays, trap, wait, disown, all control structures, all expansions, extended globs, `=~` with BASH_REMATCH
2. **Full Shell Options**: errexit, nounset, xtrace, pipefail, noclobber, allexport, and many more
3. **Remaining Gaps**: coprocesses, programmable completion, `caller`, `read -e`/`read -i` (readline editing), `BASH_SOURCE`/`BASH_LINENO`
4. **Educational Tools**: Debug flags, script analysis, multiple parser implementations
5. **High Compatibility**: Most Bash scripts run without modification

Key differences to remember:
- Use `set -eu -o pipefail` instead of `set -euo pipefail`
- Namerefs (`declare -n`/`local -n`) support scalar and array-element targets, chains, and `local -n` pass-by-reference; `${!var}` indirect expansion works too
- All `${var@...}` transform operators are supported, including `${var@K}`/`${var@k}` (associative key/value display)
- DEBUG, ERR, and RETURN traps and interactive history expansion (`!!`, `!n`, word designators, modifiers) all work (RETURN as of v0.617, honoring bash's `set -T`/`declare -ft` hiding model)
- `caller` is not available (`let`, `mapfile`, `readarray` are supported)
- Use `$PSH_VERSION` instead of `$BASH_VERSION` to detect PSH
- Aliases expand in scripts and `-c` strings by default (bash: interactive only); `shopt -u expand_aliases` turns that off
- Deep recursion may hit Python stack limits

---

[Previous: Chapter 16 - Advanced Features](16_advanced_features.md) | [Next: Chapter 18 - Troubleshooting](18_troubleshooting.md)
