#!/usr/bin/env psh
#
# fibonacci.sh — compute Fibonacci numbers two ways.
#
# A small, self-contained script used throughout the PSH docs to
# demonstrate the analysis tools:
#
#   psh --metrics   examples/fibonacci.sh   # complexity & command counts
#   psh --validate  examples/fibonacci.sh   # parse-only, no execution
#   psh --debug-ast examples/fibonacci.sh   # show the parsed syntax tree
#   psh examples/fibonacci.sh 10            # actually run it
#
# It deliberately uses a function, a loop, and conditionals so that the
# metrics report has something interesting to say.

# Recursive definition — the textbook formula, slow but clear.
fib_recursive() {
    local n="$1"
    if [ "$n" -lt 2 ]; then
        echo "$n"
    else
        echo $(( $(fib_recursive $((n - 1))) + $(fib_recursive $((n - 2))) ))
    fi
}

# Iterative definition — linear time, the version you'd actually use.
fib_iterative() {
    local n="$1"
    local a=0 b=1
    while [ "$n" -gt 0 ]; do
        local next="$((a + b))"
        a="$b"
        b="$next"
        n="$((n - 1))"
    done
    echo "$a"
}

# Default to the first 10 numbers; allow an override on the command line.
count=${1:-10}

echo "First $count Fibonacci numbers (recursive then iterative):"
for ((i = 0; i < count; i++)); do
    printf '%s ' "$(fib_recursive "$i")"
done
echo

for ((i = 0; i < count; i++)); do
    printf '%s ' "$(fib_iterative "$i")"
done
echo
