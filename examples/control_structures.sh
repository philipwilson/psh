#!/usr/bin/env psh
#
# control_structures.sh — if / while / for / case, plus loop control.
#
# This script is intentionally rich in nested structure, which makes it a
# good subject for the AST-visualization tools:
#
#   psh --debug-ast examples/control_structures.sh   # show the parsed tree
#   psh --metrics   examples/control_structures.sh   # nesting depth, etc.
#
# Run it with:  psh examples/control_structures.sh

# --- if / elif / else -----------------------------------------------------
classify() {
    local n="$1"
    if [ "$n" -lt 0 ]; then
        echo "negative"
    elif [ "$n" -eq 0 ]; then
        echo "zero"
    else
        echo "positive"
    fi
}

for sample in -3 0 42; do
    echo "$sample is $(classify "$sample")"
done

# --- while with break / continue ------------------------------------------
# Print the first few even numbers, skipping odds with `continue` and
# stopping with `break`.
echo "First even numbers:"
n=0
while true; do
    n=$((n + 1))
    if [ $((n % 2)) -ne 0 ]; then
        continue
    fi
    printf '%s ' "$n"
    if [ "$n" -ge 8 ]; then
        break
    fi
done
echo

# --- case -----------------------------------------------------------------
# Pattern matching on a string, with glob-style patterns and a default.
describe_file() {
    case "$1" in
        *.sh)         echo "shell script" ;;
        *.py)         echo "python source" ;;
        *.txt | *.md) echo "text document" ;;
        *)            echo "something else" ;;
    esac
}

for f in run.sh notes.md image.png; do
    echo "$f -> $(describe_file "$f")"
done

# --- C-style for with nesting ---------------------------------------------
# A multiplication table — two nested loops, the deepest point in the AST.
echo "3x3 multiplication table:"
for ((row = 1; row <= 3; row++)); do
    for ((col = 1; col <= 3; col++)); do
        printf '%3d' "$((row * col))"
    done
    echo
done
