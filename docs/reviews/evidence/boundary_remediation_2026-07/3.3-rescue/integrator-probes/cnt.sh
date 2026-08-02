#!/bin/sh
printf 'n=%s' "$#"
for a in "$@"; do printf ' [%s]' "$a"; done
printf '\n'
