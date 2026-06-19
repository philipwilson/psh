#!/usr/bin/env psh
#
# shell_basics.sh — a guided tour of everyday shell expansion.
#
# Run it:        psh examples/shell_basics.sh
# Inspect it:    psh --format examples/shell_basics.sh
#
# Each section is a self-contained demonstration of one expansion rule.
# The comments explain *why* the output is what it is — the parts of
# shell behaviour that surprise newcomers.

# --- Variables and quoting ------------------------------------------------
# Assignment never has spaces around '='. A bare value needs no quotes; a
# value with spaces does.
name="world"
greeting="Hello, $name!"
echo "$greeting"

# Single quotes are literal: no expansion happens inside them.
echo 'Literally $name, untouched'

# --- Parameter expansion --------------------------------------------------
# ${var:-default} supplies a fallback when var is unset or empty.
echo "Editor: ${EDITOR:-none configured}"

# ${#var} is the length; ${var^^} upper-cases (a bash extension psh supports).
echo "The word '$name' has ${#name} letters: ${name^^}"

# --- Command substitution -------------------------------------------------
# $(...) captures a command's stdout. Here we count the files in the cwd.
file_count="$(ls -1 | wc -l)"
echo "This directory holds $file_count entries."

# --- Arithmetic -----------------------------------------------------------
# $(( ... )) evaluates integer arithmetic. No '$' is needed on the names
# inside the parentheses.
width=7
height=6
echo "A ${width}x${height} grid has $((width * height)) cells."

# --- Pipelines ------------------------------------------------------------
# Each stage runs concurrently; stdout of one feeds stdin of the next.
echo "Three two one go" | tr ' ' '\n' | sort | head -n 2

# --- Word splitting: the classic gotcha -----------------------------------
# An unquoted expansion is split on whitespace into multiple words; a
# quoted one stays a single word. This is the single most common source
# of shell bugs, so it is worth seeing directly.
spaced="a b c"
printf 'unquoted gives %s arguments\n' "$(set -- $spaced; echo $#)"
printf 'quoted   gives %s argument\n'  "$(set -- "$spaced"; echo $#)"
