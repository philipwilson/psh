#!/bin/sh
# Slot 1.4 probe: when does a shell warn about a failed setlocale?
# Usage: locale-warn-matrix.sh <shell invocation...>
#   e.g. locale-warn-matrix.sh /opt/homebrew/bin/bash
#        locale-warn-matrix.sh /path/to/python3 -m psh
# Prints, per case, the STDERR the shell produced (or "<silent>").
BOGUS=xx_BOGUS.UTF-8

run_case() {
    label=$1; shift
    envspec=$1; shift
    script=$1; shift
    err=$(env -i PATH="$PATH" HOME="$HOME" $envspec "$@" -c "$script" 2>&1 >/dev/null)
    if [ -z "$err" ]; then err="<silent>"; fi
    printf '%-34s %s\n' "$label" "$err"
}

echo "### shell: $* ###"
run_case "A unset-exposes-bogus-CTYPE" "LC_ALL=C LC_CTYPE=$BOGUS" \
    'unset LC_ALL; echo done' "$@"
run_case "B assign-bogus-LC_ALL"       "" \
    "LC_ALL=$BOGUS; echo done" "$@"
run_case "C assign-bogus-LC_CTYPE"     "" \
    "LC_CTYPE=$BOGUS; echo done" "$@"
run_case "D startup-bogus-LC_ALL"      "LC_ALL=$BOGUS" \
    'echo done' "$@"
run_case "E startup-bogus-LC_CTYPE"    "LC_CTYPE=$BOGUS" \
    'echo done' "$@"
run_case "F empty-LC_ALL-exposes-bogus" "LC_ALL=C LC_CTYPE=$BOGUS" \
    'LC_ALL=; echo done' "$@"
run_case "G tempenv-prefix-bogus"      "" \
    "LC_CTYPE=$BOGUS echo done" "$@"
